"""0010_gst_tax_heads

Adds the GST tax heads (CGST/SGST/IGST), place of supply and HSN/SAC to
invoices, quotes and their line items, so the documents this system issues are
valid Indian tax invoices rather than showing a single combined tax figure.

Existing rows are backfilled: the supply type is recomputed from the current
organization and customer GSTIN/state, and the stored tax_amount is split
accordingly. That is the best available reconstruction — historic addresses are
not versioned — and it is strictly better than leaving issued documents with a
zero split.

Revision ID: c1d2e3f4a5b6
Revises: b8c9d0e1f2a3
Create Date: 2026-09-08 23:40:00.000000
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DOC_COLUMNS = [
    ("cgst_amount", sa.Numeric(14, 2), "0"),
    ("sgst_amount", sa.Numeric(14, 2), "0"),
    ("igst_amount", sa.Numeric(14, 2), "0"),
]
DOC_META = [
    ("supply_type", sa.String(16)),
    ("place_of_supply_code", sa.String(2)),
    ("place_of_supply_name", sa.String(120)),
]
ITEM_COLUMNS = [
    ("cgst_amount", sa.Numeric(14, 2), "0"),
    ("sgst_amount", sa.Numeric(14, 2), "0"),
    ("igst_amount", sa.Numeric(14, 2), "0"),
    ("cgst_rate_pct", sa.Numeric(5, 2), "0"),
    ("sgst_rate_pct", sa.Numeric(5, 2), "0"),
    ("igst_rate_pct", sa.Numeric(5, 2), "0"),
]


def _inspector():
    return sa.inspect(op.get_bind())


def _cols(table: str) -> set:
    insp = _inspector()
    if not insp.has_table(table):
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _add(table: str, name: str, type_, server_default=None, nullable=True) -> None:
    if not _inspector().has_table(table) or name in _cols(table):
        return
    op.add_column(table, sa.Column(name, type_, nullable=nullable, server_default=server_default))


def _drop(table: str, name: str) -> None:
    if _inspector().has_table(table) and name in _cols(table):
        op.drop_column(table, name)


def upgrade() -> None:
    for table in ("invoices", "quotes"):
        for name, type_, default in DOC_COLUMNS:
            _add(table, name, type_, server_default=default, nullable=False)
        for name, type_ in DOC_META:
            _add(table, name, type_)
    # GSTINs are frozen onto the invoice so a reissued PDF matches what was filed.
    _add("invoices", "customer_gstin", sa.String(15))
    _add("invoices", "supplier_gstin", sa.String(15))

    for table in ("invoice_items", "quote_items"):
        for name, type_, default in ITEM_COLUMNS:
            _add(table, name, type_, server_default=default, nullable=False)
        _add(table, name="hsn_sac_code", type_=sa.String(16))

    _backfill()


def _q2(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _backfill() -> None:
    """Split each existing document's stored tax into the correct heads."""
    from backend.app.services import gst

    conn = op.get_bind()
    if not _inspector().has_table("invoices"):
        return

    orgs = {
        r[0]: r
        for r in conn.execute(sa.text("SELECT id, gstin, state, country FROM organizations")).fetchall()
    }
    customers = {
        r[0]: r
        for r in conn.execute(
            sa.text("SELECT id, gstin, billing_state, billing_country FROM customers")
        ).fetchall()
    }

    class _Party:
        def __init__(self, gstin, state, country, customer=False):
            if customer:
                self.gstin, self.billing_state, self.billing_country = gstin, state, country or "IN"
            else:
                self.gstin, self.state, self.country = gstin, state, country or "IN"

    for doc_table, item_table, fk in (
        ("invoices", "invoice_items", "invoice_id"),
        ("quotes", "quote_items", "quote_id"),
    ):
        if not _inspector().has_table(doc_table):
            continue
        rows = conn.execute(
            sa.text(f"SELECT id, organization_id, customer_id, tax_amount FROM {doc_table}")
        ).fetchall()
        for doc_id, org_id, customer_id, tax_amount in rows:
            org_row, cust_row = orgs.get(org_id), customers.get(customer_id)
            if org_row is None or cust_row is None:
                continue
            supply = gst.resolve_supply(
                _Party(org_row[1], org_row[2], org_row[3]),
                _Party(cust_row[1], cust_row[2], cust_row[3], customer=True),
            )
            split = gst.split_tax(_q2(tax_amount), supply)
            params = {
                "cgst": str(split.cgst), "sgst": str(split.sgst), "igst": str(split.igst),
                "stype": supply.supply_type, "pos": supply.place_of_supply_code,
                "posn": supply.place_of_supply_name, "id": doc_id,
            }
            extra = ""
            if doc_table == "invoices":
                extra = ", customer_gstin = :cgstin, supplier_gstin = :sgstin"
                params["cgstin"] = supply.customer_gstin
                params["sgstin"] = org_row[1]
            conn.execute(
                sa.text(
                    f"UPDATE {doc_table} SET cgst_amount = :cgst, sgst_amount = :sgst, "
                    f"igst_amount = :igst, supply_type = :stype, place_of_supply_code = :pos, "
                    f"place_of_supply_name = :posn{extra} WHERE id = :id"
                ),
                params,
            )

            if not _inspector().has_table(item_table):
                continue
            items = conn.execute(
                sa.text(
                    f"SELECT id, amount, tax_rate_pct FROM {item_table} WHERE {fk} = :doc"
                ),
                {"doc": doc_id},
            ).fetchall()
            for item_id, amount, rate in items:
                line_tax = _q2(_q2(amount) * Decimal(str(rate or 0)) / Decimal("100"))
                lsplit = gst.split_tax(line_tax, supply)
                rsplit = gst.split_rate(Decimal(str(rate or 0)), supply)
                conn.execute(
                    sa.text(
                        f"UPDATE {item_table} SET cgst_amount = :ca, sgst_amount = :sa, igst_amount = :ia, "
                        f"cgst_rate_pct = :cr, sgst_rate_pct = :sr, igst_rate_pct = :ir WHERE id = :id"
                    ),
                    {
                        "ca": str(lsplit.cgst), "sa": str(lsplit.sgst), "ia": str(lsplit.igst),
                        "cr": str(rsplit.cgst), "sr": str(rsplit.sgst), "ir": str(rsplit.igst),
                        "id": item_id,
                    },
                )

    # HSN/SAC is copied from the product so reissued documents carry it.
    if _inspector().has_table("products"):
        for item_table in ("invoice_items", "quote_items"):
            if _inspector().has_table(item_table):
                conn.execute(
                    sa.text(
                        f"UPDATE {item_table} SET hsn_sac_code = ("
                        f"SELECT p.hsn_sac_code FROM products p WHERE p.id = {item_table}.product_id"
                        f") WHERE product_id IS NOT NULL AND hsn_sac_code IS NULL"
                    )
                )


def downgrade() -> None:
    for table in ("invoice_items", "quote_items"):
        for name, _t, _d in ITEM_COLUMNS:
            _drop(table, name)
        _drop(table, "hsn_sac_code")
    _drop("invoices", "customer_gstin")
    _drop("invoices", "supplier_gstin")
    for table in ("invoices", "quotes"):
        for name, _t in DOC_META:
            _drop(table, name)
        for name, _t, _d in DOC_COLUMNS:
            _drop(table, name)
