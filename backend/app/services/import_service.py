"""CSV import of customers, products and plans.

Files are parsed with the csv module (utf-8 with optional BOM), each row is
validated independently and problems are collected as {row, error} where `row`
is the 1-based data row (header excluded). Valid rows are committed unless
dry_run; numbers are still reserved through services.numbering during a dry run
and released by the rollback.
"""
import csv
import io
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext
from backend.app.core.exceptions import ValidationAppError
from backend.app.core.security import generate_opaque_token
from backend.app.models import (
    BillingInterval,
    Customer,
    CustomerStatus,
    ImportEntity,
    ImportJob,
    ImportStatus,
    Plan,
    PricingModel,
    Product,
    ProductType,
)
from backend.app.schemas.common_refs import enum_value, iso_dt
from backend.app.schemas.customers import validate_email_format
from backend.app.services import audit
from backend.app.services.numbering import next_number
from backend.app.services.pagination import Page, PageParams, apply_sort, paginate

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 5000
MAX_ERRORS = 100
# Numeric(14, 2) holds < 10^12; bound imported money well inside it.
MAX_MONEY = Decimal("999999999999.99")
MAX_TRIAL_DAYS = 3650
PREVIEW_ROWS = 10

IMPORT_SORT_FIELDS = ("created_at", "entity", "status")

COLUMNS: Dict[ImportEntity, List[str]] = {
    ImportEntity.CUSTOMERS: [
        "display_name",
        "company_name",
        "email",
        "phone",
        "gstin",
        "pan",
        "currency",
        "payment_terms_days",
        "billing_address_line1",
        "billing_address_line2",
        "billing_city",
        "billing_state",
        "billing_postal_code",
        "billing_country",
        "notes",
    ],
    ImportEntity.PRODUCTS: ["name", "sku", "description", "type", "unit", "hsn_sac_code", "tax_rate_pct", "is_active"],
    ImportEntity.PLANS: [
        "product_sku",
        "name",
        "code",
        "billing_interval",
        "interval_count",
        "pricing_model",
        "unit_amount",
        "currency",
        "setup_fee",
        "trial_days",
        "is_active",
    ],
}

REQUIRED: Dict[ImportEntity, List[str]] = {
    ImportEntity.CUSTOMERS: ["display_name"],
    ImportEntity.PRODUCTS: ["name", "sku"],
    ImportEntity.PLANS: ["product_sku", "name", "code", "billing_interval", "unit_amount"],
}

TRUE_WORDS = {"true", "1", "yes", "y", "t"}
FALSE_WORDS = {"false", "0", "no", "n", "f"}


class RowError(Exception):
    pass


# --- templates -------------------------------------------------------------------------------


def template_csv(entity: ImportEntity) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator="\n").writerow(COLUMNS[entity])
    return buffer.getvalue()


# --- parsing helpers -----------------------------------------------------------------------------


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_int(value: Optional[str], field: str, default: int, minimum: int = 0) -> int:
    if value is None:
        return default
    try:
        number = int(Decimal(value))
    except (InvalidOperation, ValueError, OverflowError):
        raise RowError(f"{field} must be a whole number")
    if number < minimum:
        raise RowError(f"{field} must be >= {minimum}")
    return number


def _parse_decimal(value: Optional[str], field: str, default: Optional[Decimal], minimum=Decimal("0"), maximum=None) -> Optional[Decimal]:
    if value is None:
        return default
    try:
        number = Decimal(value.replace(",", ""))
    except InvalidOperation:
        raise RowError(f"{field} must be a number")
    if not number.is_finite():
        raise RowError(f"{field} must be a finite number")
    if number < minimum:
        raise RowError(f"{field} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise RowError(f"{field} must be <= {maximum}")
    return number


def _parse_bool(value: Optional[str], field: str, default: bool) -> bool:
    if value is None:
        return default
    lowered = value.lower()
    if lowered in TRUE_WORDS:
        return True
    if lowered in FALSE_WORDS:
        return False
    raise RowError(f"{field} must be true or false")


def _parse_enum(value: Optional[str], field: str, enum_cls, default):
    if value is None:
        if default is None:
            raise RowError(f"{field} is required")
        return default
    try:
        return enum_cls(value.lower())
    except ValueError:
        allowed = ", ".join(e.value for e in enum_cls)
        raise RowError(f"{field} must be one of: {allowed}")


def _parse_currency(value: Optional[str], default: str) -> str:
    if value is None:
        return default
    if len(value) != 3 or not value.isalpha():
        raise RowError("currency must be a 3-letter ISO code")
    return value.upper()


def _require(row: Dict[str, Optional[str]], fields: List[str]) -> None:
    missing = [f for f in fields if not row.get(f)]
    if missing:
        raise RowError(f"missing required value for {', '.join(missing)}")


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _read_rows(content: bytes, entity: ImportEntity) -> Tuple[List[str], List[Dict[str, Optional[str]]]]:
    if len(content) > MAX_FILE_BYTES:
        raise ValidationAppError("CSV file is larger than 5 MB.", {"fields": {"file": "too large"}})
    text = _decode(content)
    if not text.strip():
        raise ValidationAppError("CSV file is empty.", {"fields": {"file": "empty"}})
    reader = csv.DictReader(io.StringIO(text))
    header = [h.strip().lower() for h in (reader.fieldnames or []) if h is not None]
    reader.fieldnames = header  # normalise header casing
    missing = [c for c in REQUIRED[entity] if c not in header]
    if missing:
        raise ValidationAppError(
            f"CSV is missing required column(s): {', '.join(missing)}.",
            {"fields": {"file": f"missing columns: {', '.join(missing)}"}},
        )
    known = set(COLUMNS[entity])
    rows: List[Dict[str, Optional[str]]] = []
    for raw in reader:
        if raw is None:
            continue
        cleaned = {k: _clean(v) for k, v in raw.items() if k in known}
        if not any(cleaned.values()):
            continue  # skip blank lines
        rows.append(cleaned)
        if len(rows) > MAX_ROWS:
            raise ValidationAppError("CSV has more than 5,000 data rows.", {"fields": {"file": "too many rows"}})
    return header, rows


# --- per-entity row handlers -------------------------------------------------------------------------


def _import_customer(db: Session, ctx: CurrentContext, row: Dict[str, Optional[str]], seen: Set[str], existing: Set[str]) -> None:
    _require(row, REQUIRED[ImportEntity.CUSTOMERS])
    org = ctx.organization
    email = row.get("email")
    if email:
        try:
            email = validate_email_format(email)
        except ValueError:
            raise RowError("email is invalid")
        key = email.lower()
        if key in seen:
            raise RowError(f"duplicate email '{email}' within the file")
        if key in existing:
            raise RowError(f"a customer with email '{email}' already exists")
    gstin = row.get("gstin")
    if gstin and len(gstin) > 15:
        raise RowError("gstin must be at most 15 characters")
    pan = row.get("pan")
    if pan and len(pan) > 10:
        raise RowError("pan must be at most 10 characters")
    company_name = row.get("company_name")
    if company_name and len(company_name) > 200:
        raise RowError("company_name must be at most 200 characters")
    phone = row.get("phone")
    if phone:
        if len(phone) > 40:
            raise RowError("phone must be at most 40 characters")
        if not all(ch.isdigit() or ch in "+-() ." for ch in phone):
            raise RowError("phone may only contain digits, spaces and + - ( ) .")
    for field, limit in (
        ("billing_address_line1", 255),
        ("billing_address_line2", 255),
        ("billing_city", 120),
        ("billing_state", 120),
        ("billing_postal_code", 20),
    ):
        value = row.get(field)
        if value and len(value) > limit:
            raise RowError(f"{field} must be at most {limit} characters")
    country = row.get("billing_country") or org.country or "IN"
    if len(country) != 2 or not country.isalpha():
        raise RowError("billing_country must be a 2-letter ISO code")
    customer = Customer(
        organization_id=ctx.organization_id,
        customer_number=next_number(db, ctx.organization_id, "customer"),
        display_name=row["display_name"][:200],
        company_name=company_name,
        email=email,
        phone=phone,
        gstin=gstin.upper() if gstin else None,
        pan=pan.upper() if pan else None,
        currency=_parse_currency(row.get("currency"), org.default_currency or "INR"),
        payment_terms_days=_parse_int(row.get("payment_terms_days"), "payment_terms_days", org.default_payment_terms_days or 30),
        status=CustomerStatus.ACTIVE,
        billing_address_line1=row.get("billing_address_line1"),
        billing_address_line2=row.get("billing_address_line2"),
        billing_city=row.get("billing_city"),
        billing_state=row.get("billing_state"),
        billing_postal_code=row.get("billing_postal_code"),
        billing_country=country.upper(),
        notes=row.get("notes"),
        portal_token=generate_opaque_token(),
    )
    db.add(customer)
    db.flush()
    if email:
        seen.add(email.lower())


def _import_product(db: Session, ctx: CurrentContext, row: Dict[str, Optional[str]], seen: Set[str], existing: Set[str]) -> None:
    _require(row, REQUIRED[ImportEntity.PRODUCTS])
    sku = row["sku"]
    key = sku.lower()
    if key in seen:
        raise RowError(f"duplicate sku '{sku}' within the file")
    if key in existing:
        raise RowError(f"a product with sku '{sku}' already exists")
    if len(sku) > 64:
        raise RowError("sku must be at most 64 characters")
    product = Product(
        organization_id=ctx.organization_id,
        name=row["name"][:200],
        sku=sku,
        description=row.get("description"),
        type=_parse_enum(row.get("type"), "type", ProductType, ProductType.SERVICE),
        unit=(row.get("unit") or "unit")[:32],
        hsn_sac_code=(row.get("hsn_sac_code") or None),
        tax_rate_pct=_parse_decimal(
            row.get("tax_rate_pct"), "tax_rate_pct", Decimal(str(ctx.organization.default_tax_rate_pct or 0)), maximum=Decimal("100")
        ),
        is_active=_parse_bool(row.get("is_active"), "is_active", True),
    )
    db.add(product)
    db.flush()
    seen.add(key)


def _import_plan(
    db: Session,
    ctx: CurrentContext,
    row: Dict[str, Optional[str]],
    seen: Set[str],
    existing: Set[str],
    products_by_sku: Dict[str, str],
) -> None:
    _require(row, REQUIRED[ImportEntity.PLANS])
    code = row["code"]
    key = code.lower()
    if key in seen:
        raise RowError(f"duplicate code '{code}' within the file")
    if key in existing:
        raise RowError(f"a plan with code '{code}' already exists")
    if _parse_int(row.get("trial_days"), "trial_days", 0) > MAX_TRIAL_DAYS:
        raise RowError(f"trial_days must be <= {MAX_TRIAL_DAYS}")
    if _parse_int(row.get("interval_count"), "interval_count", 1, minimum=1) > 36:
        raise RowError("interval_count must be <= 36")
    if len(code) > 64:
        raise RowError("code must be at most 64 characters")
    product_id = products_by_sku.get(row["product_sku"].lower())
    if product_id is None:
        raise RowError(f"product with sku '{row['product_sku']}' was not found")
    plan = Plan(
        organization_id=ctx.organization_id,
        product_id=product_id,
        name=row["name"][:200],
        code=code,
        billing_interval=_parse_enum(row.get("billing_interval"), "billing_interval", BillingInterval, None),
        interval_count=_parse_int(row.get("interval_count"), "interval_count", 1, minimum=1),
        pricing_model=_parse_enum(row.get("pricing_model"), "pricing_model", PricingModel, PricingModel.FLAT),
        unit_amount=_parse_decimal(row.get("unit_amount"), "unit_amount", None, maximum=MAX_MONEY),
        currency=_parse_currency(row.get("currency"), ctx.organization.default_currency or "INR"),
        setup_fee=_parse_decimal(row.get("setup_fee"), "setup_fee", Decimal("0"), maximum=MAX_MONEY),
        trial_days=_parse_int(row.get("trial_days"), "trial_days", 0),
        is_active=_parse_bool(row.get("is_active"), "is_active", True),
    )
    db.add(plan)
    db.flush()
    seen.add(key)


# --- orchestration ----------------------------------------------------------------------------------------


def _existing_keys(db: Session, entity: ImportEntity, organization_id: str) -> Set[str]:
    if entity == ImportEntity.CUSTOMERS:
        column, model = Customer.email, Customer
    elif entity == ImportEntity.PRODUCTS:
        column, model = Product.sku, Product
    else:
        column, model = Plan.code, Plan
    values = db.scalars(select(column).where(model.organization_id == organization_id, column.is_not(None))).all()
    return {v.lower() for v in values if v}


def _status_for(total: int, imported: int, failed: int) -> ImportStatus:
    if total == 0 or (failed and not imported):
        return ImportStatus.FAILED
    if failed:
        return ImportStatus.COMPLETED_WITH_ERRORS
    return ImportStatus.COMPLETED


def run_import(
    db: Session,
    ctx: CurrentContext,
    entity: ImportEntity,
    file_name: str,
    content: bytes,
    dry_run: bool,
) -> Dict[str, Any]:
    _, rows = _read_rows(content, entity)
    existing = _existing_keys(db, entity, ctx.organization_id)
    seen: Set[str] = set()
    errors: List[Dict[str, Any]] = []
    imported = 0

    products_by_sku: Dict[str, str] = {}
    if entity == ImportEntity.PLANS:
        pairs = db.execute(select(Product.sku, Product.id).where(Product.organization_id == ctx.organization_id)).all()
        products_by_sku = {sku.lower(): pid for sku, pid in pairs if sku}

    handler: Callable[..., None]
    if entity == ImportEntity.CUSTOMERS:
        handler = _import_customer
    elif entity == ImportEntity.PRODUCTS:
        handler = _import_product
    else:
        handler = lambda db_, ctx_, row_, seen_, existing_: _import_plan(db_, ctx_, row_, seen_, existing_, products_by_sku)  # noqa: E731

    # Handlers validate a row completely before adding it to the session, so a
    # RowError never leaves partial state behind. (No SAVEPOINTs: pysqlite's legacy
    # transaction mode auto-commits a savepoint released outside an open transaction.)
    for index, row in enumerate(rows, start=1):
        try:
            handler(db, ctx, row, seen, existing)
            imported += 1
        except RowError as exc:
            errors.append({"row": index, "error": str(exc)})
        except Exception as exc:  # unexpected DB error: abandon the whole import
            db.rollback()
            raise ValidationAppError(
                f"Import aborted at row {index}: {exc.__class__.__name__}.",
                {"fields": {"file": f"row {index}"}},
            ) from exc

    total = len(rows)
    failed = len(errors)
    status = _status_for(total, imported, failed)
    preview = rows[:PREVIEW_ROWS]
    result: Dict[str, Any] = {
        "id": None,
        "entity": entity.value,
        "file_name": file_name,
        "status": status.value,
        "dry_run": dry_run,
        "total_rows": total,
        "imported_rows": imported,
        "failed_rows": failed,
        "errors": errors[:MAX_ERRORS],
        "preview": preview,
        "created_at": None,
    }

    if dry_run:
        db.rollback()
        return result

    job = ImportJob(
        organization_id=ctx.organization_id,
        entity=entity,
        file_name=file_name[:255],
        status=status,
        total_rows=total,
        imported_rows=imported,
        failed_rows=failed,
        errors=errors[:MAX_ERRORS],
        created_by_id=ctx.user.id,
    )
    db.add(job)
    db.flush()
    audit.record(
        db,
        ctx=ctx,
        action="IMPORT_COMPLETED",
        entity_type="import",
        entity_id=job.id,
        entity_label=file_name[:200],
        after={
            "entity": entity.value,
            "status": status.value,
            "total_rows": total,
            "imported_rows": imported,
            "failed_rows": failed,
        },
    )
    db.commit()
    db.refresh(job)
    result["id"] = job.id
    result["created_at"] = iso_dt(job.created_at)
    return result


def list_imports(db: Session, ctx: CurrentContext, params: PageParams) -> Page:
    stmt = select(ImportJob).where(ImportJob.organization_id == ctx.organization_id)
    stmt = apply_sort(stmt, ImportJob, params.sort, IMPORT_SORT_FIELDS, "-created_at")
    return paginate(db, stmt, params)


def serialize_job(job: ImportJob) -> Dict[str, Any]:
    return {
        "id": job.id,
        "entity": enum_value(job.entity),
        "file_name": job.file_name,
        "status": enum_value(job.status),
        "dry_run": False,
        "total_rows": int(job.total_rows or 0),
        "imported_rows": int(job.imported_rows or 0),
        "failed_rows": int(job.failed_rows or 0),
        "errors": list(job.errors or []),
        "preview": [],
        "created_at": iso_dt(job.created_at),
    }
