"""Decimal money helpers and line-item total computation shared by quotes and invoices."""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, List, Optional, Sequence

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")


def D(value) -> Decimal:
    """Coerce str/int/float/Decimal/None to a Decimal (None -> 0)."""
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def q2(value) -> Decimal:
    """Round half-up to 2 decimal places."""
    return D(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def to_str(value) -> str:
    return str(q2(value))


@dataclass
class LineInput:
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate_pct: Decimal
    product_id: Optional[str] = None
    plan_id: Optional[str] = None


@dataclass
class LineComputed:
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_rate_pct: Decimal
    amount: Decimal
    position: int
    product_id: Optional[str] = None
    plan_id: Optional[str] = None


@dataclass
class Totals:
    subtotal: Decimal
    discount_pct: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total: Decimal
    lines: List[LineComputed]


def compute_totals(lines: Iterable[LineInput], discount_pct=0) -> Totals:
    """Apply the contract's rounding rules.

    amount          = quantity * unit_price                (2dp)
    subtotal        = sum(amount)
    discount_amount = subtotal * discount_pct / 100        (2dp)
    tax_amount      = sum((amount - amount*discount_pct/100) * tax_rate_pct / 100) (2dp per line)
    total           = subtotal - discount_amount + tax_amount
    """
    disc = D(discount_pct)
    if disc < 0 or disc > 100:
        raise ValueError("discount_pct must be between 0 and 100")
    computed: List[LineComputed] = []
    subtotal = Decimal("0")
    tax_total = Decimal("0")
    for idx, line in enumerate(lines):
        qty = D(line.quantity)
        price = D(line.unit_price)
        rate = D(line.tax_rate_pct)
        if qty <= 0:
            raise ValueError(f"Line {idx + 1}: quantity must be greater than zero")
        if price < 0:
            raise ValueError(f"Line {idx + 1}: unit price cannot be negative")
        if rate < 0 or rate > 100:
            raise ValueError(f"Line {idx + 1}: tax rate must be between 0 and 100")
        amount = q2(qty * price)
        taxable = amount - q2(amount * disc / 100)
        tax_total += q2(taxable * rate / 100)
        subtotal += amount
        computed.append(
            LineComputed(
                description=line.description.strip(),
                quantity=qty,
                unit_price=q2(price),
                tax_rate_pct=q2(rate),
                amount=amount,
                position=idx,
                product_id=line.product_id,
                plan_id=line.plan_id,
            )
        )
    if not computed:
        raise ValueError("At least one line item is required")
    discount_amount = q2(subtotal * disc / 100)
    total = q2(subtotal - discount_amount + tax_total)
    return Totals(
        subtotal=q2(subtotal),
        discount_pct=q2(disc),
        discount_amount=discount_amount,
        tax_amount=q2(tax_total),
        total=total,
        lines=computed,
    )


def sum_amounts(values: Sequence) -> Decimal:
    return q2(sum((D(v) for v in values), Decimal("0")))
