"""Pure mathematical proration calculator following Zoho Billing calendar-day conventions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True)
class ProrationResult:
    period_start: date
    period_end: date
    change_date: date
    total_days: int
    days_used: int
    days_remaining: int
    old_unit_price: Decimal
    new_unit_price: Decimal
    old_quantity: Decimal
    new_quantity: Decimal
    old_total_rate: Decimal
    new_total_rate: Decimal
    unused_credit: Decimal
    remaining_charge: Decimal
    net_adjustment: Decimal  # >0: customer owes money (invoice); <0: customer gets credit (credit note)
    is_upgrade: bool
    is_downgrade: bool
    currency: str
    explanation: str


def calculate_proration(
    period_start: date,
    period_end: date,
    change_date: date,
    old_price: Decimal,
    new_price: Decimal,
    old_quantity: Decimal = Decimal("1"),
    new_quantity: Decimal = Decimal("1"),
    currency: str = "INR",
) -> ProrationResult:
    """Calculates calendar-day based prorated charge, credit, and net adjustment.

    Formula:
      Prorated Old Credit = (Old Rate / Total Days) * Days Remaining
      Prorated New Charge = (New Rate / Total Days) * Days Remaining
      Net Adjustment = Prorated New Charge - Prorated Old Credit
    """
    total_days = (period_end - period_start).days
    if total_days <= 0:
        total_days = 30  # fallback for edge cases where dates are equal

    # Clamp change date within period bounds
    if change_date < period_start:
        change_date = period_start
    elif change_date > period_end:
        change_date = period_end

    days_used = (change_date - period_start).days
    days_remaining = total_days - days_used

    old_total_rate = (Decimal(str(old_price)) * Decimal(str(old_quantity))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    new_total_rate = (Decimal(str(new_price)) * Decimal(str(new_quantity))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Prorated unused credit on old plan
    unused_credit = (
        (old_total_rate * Decimal(str(days_remaining))) / Decimal(str(total_days))
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # Prorated charge on new plan
    remaining_charge = (
        (new_total_rate * Decimal(str(days_remaining))) / Decimal(str(total_days))
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    net_adjustment = remaining_charge - unused_credit

    is_upgrade = new_total_rate > old_total_rate
    is_downgrade = new_total_rate < old_total_rate

    explanation = (
        f"Billing period from {period_start} to {period_end} ({total_days} days). "
        f"Change effective on {change_date} with {days_remaining} days remaining. "
        f"Credited unused portion of old plan: {currency} {unused_credit:.2f}. "
        f"Charged remaining portion of new plan: {currency} {remaining_charge:.2f}. "
        f"Net adjustment: {currency} {net_adjustment:.2f}."
    )

    return ProrationResult(
        period_start=period_start,
        period_end=period_end,
        change_date=change_date,
        total_days=total_days,
        days_used=days_used,
        days_remaining=days_remaining,
        old_unit_price=Decimal(str(old_price)).quantize(Decimal("0.01")),
        new_unit_price=Decimal(str(new_price)).quantize(Decimal("0.01")),
        old_quantity=Decimal(str(old_quantity)),
        new_quantity=Decimal(str(new_quantity)),
        old_total_rate=old_total_rate,
        new_total_rate=new_total_rate,
        unused_credit=unused_credit,
        remaining_charge=remaining_charge,
        net_adjustment=net_adjustment,
        is_upgrade=is_upgrade,
        is_downgrade=is_downgrade,
        currency=currency,
        explanation=explanation,
    )
