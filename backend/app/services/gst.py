"""Indian GST: place of supply, intra/inter-state determination and CGST/SGST/IGST split.

A tax invoice issued in India must show the tax broken into the correct heads,
not a single combined figure:

- **Intra-state** (supplier and place of supply in the same state): the rate is
  split in half into CGST and SGST.
- **Inter-state** (different states), or an export: the whole rate is IGST.

The place of supply is derived from the first two digits of the recipient's
GSTIN, which encode the state. When the customer is unregistered (no GSTIN) we
fall back to their billing state name, and finally to the supplier's own state,
which makes the supply intra-state — the conservative default, because charging
CGST/SGST when IGST was due is a correctable error, whereas failing to charge
the state components understates the supplier's liability.

Only India (`country == "IN"`) is treated as GST territory. Anything else is an
export/overseas supply: zero-rated here and reported as such, with no split.

No GSTIN, no GST (product decision, BUG-07): a supplier without a GSTIN is not
registered and cannot charge GST, so its documents carry no tax at all (titled
"Bill of Supply") whatever the line tax rates say.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from backend.app.services.money import D, q2

# GST state codes (first two digits of a GSTIN) -> state/UT name.
GST_STATE_CODES: dict[str, str] = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
    "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "25": "Daman and Diu", "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra", "28": "Andhra Pradesh", "29": "Karnataka", "30": "Goa",
    "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh",
    "38": "Ladakh", "97": "Other Territory", "99": "Centre Jurisdiction",
}

_STATE_NAME_TO_CODE = {name.casefold(): code for code, name in GST_STATE_CODES.items()}
# Common aliases and older spellings people actually type into address fields.
_STATE_NAME_TO_CODE.update({
    "pondicherry": "34", "orissa": "21", "uttaranchal": "05", "new delhi": "07",
    "delhi ncr": "07", "nct of delhi": "07", "j&k": "01", "andaman & nicobar islands": "35",
    "dadra and nagar haveli": "26", "daman & diu": "26", "tamilnadu": "33",
})

# 15 chars: 2 state digits, 10-char PAN, 1 entity digit, 1 'Z', 1 checksum.
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

SUPPLY_INTRA = "intra_state"
SUPPLY_INTER = "inter_state"
SUPPLY_EXPORT = "export"


def is_valid_gstin(gstin: Optional[str]) -> bool:
    """Structural validation (format + known state code). Not a checksum verification."""
    if not gstin:
        return False
    value = gstin.strip().upper()
    return bool(GSTIN_RE.match(value)) and value[:2] in GST_STATE_CODES


def state_code_from_gstin(gstin: Optional[str]) -> Optional[str]:
    if not gstin:
        return None
    code = gstin.strip()[:2]
    return code if code in GST_STATE_CODES else None


def state_code_from_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    return _STATE_NAME_TO_CODE.get(name.strip().casefold())


def state_name(code: Optional[str]) -> Optional[str]:
    return GST_STATE_CODES.get(code) if code else None


def resolve_state_code(gstin: Optional[str], state: Optional[str]) -> Optional[str]:
    """GSTIN is authoritative; the typed state name is the fallback."""
    return state_code_from_gstin(gstin) or state_code_from_name(state)


@dataclass(frozen=True)
class SupplyContext:
    """Where a supply comes from and goes to, and therefore how it is taxed."""

    supply_type: str                      # intra_state | inter_state | export
    supplier_state_code: Optional[str]
    place_of_supply_code: Optional[str]
    place_of_supply_name: Optional[str]
    customer_gstin: Optional[str]
    is_gst_registered: bool               # recipient holds a GSTIN (B2B)
    supplier_registered: bool = True      # supplier holds a GSTIN; False -> no GST is charged

    @property
    def charges_gst(self) -> bool:
        return self.supplier_registered and not self.is_export

    @property
    def is_intra_state(self) -> bool:
        return self.supply_type == SUPPLY_INTRA

    @property
    def is_export(self) -> bool:
        return self.supply_type == SUPPLY_EXPORT


def resolve_supply(organization, customer) -> SupplyContext:
    """Determine place of supply and supply type for an organization -> customer sale."""
    supplier_country = (getattr(organization, "country", None) or "IN").upper()
    customer_country = (getattr(customer, "billing_country", None) or supplier_country).upper()
    customer_gstin = (getattr(customer, "gstin", None) or "").strip().upper() or None

    supplier_code = resolve_state_code(getattr(organization, "gstin", None), getattr(organization, "state", None))
    supplier_registered = bool((getattr(organization, "gstin", None) or "").strip())

    # Outside India (either side) is an export / overseas supply: no CGST/SGST/IGST split.
    if supplier_country != "IN" or customer_country != "IN":
        return SupplyContext(
            supply_type=SUPPLY_EXPORT,
            supplier_state_code=supplier_code,
            place_of_supply_code=None,
            place_of_supply_name=None,
            customer_gstin=customer_gstin,
            is_gst_registered=bool(customer_gstin),
            supplier_registered=supplier_registered,
        )

    pos_code = resolve_state_code(customer_gstin, getattr(customer, "billing_state", None))
    if pos_code is None:
        # Unknown recipient state: treat as the supplier's own state (intra-state),
        # which charges CGST+SGST rather than under-charging.
        pos_code = supplier_code

    intra = bool(supplier_code and pos_code and supplier_code == pos_code)
    return SupplyContext(
        supply_type=SUPPLY_INTRA if intra else SUPPLY_INTER,
        supplier_state_code=supplier_code,
        place_of_supply_code=pos_code,
        place_of_supply_name=state_name(pos_code),
        customer_gstin=customer_gstin,
        is_gst_registered=bool(customer_gstin),
        supplier_registered=supplier_registered,
    )


@dataclass(frozen=True)
class TaxSplit:
    """One line's (or one document's) tax broken into GST heads."""

    cgst: Decimal
    sgst: Decimal
    igst: Decimal

    @property
    def total(self) -> Decimal:
        return q2(self.cgst + self.sgst + self.igst)


ZERO_SPLIT = TaxSplit(Decimal("0.00"), Decimal("0.00"), Decimal("0.00"))


def split_tax(tax_amount, supply: SupplyContext) -> TaxSplit:
    """Split a line's tax into CGST/SGST/IGST.

    For intra-state supplies CGST takes the rounded half and SGST the remainder,
    so the two halves always add back to exactly `tax_amount` — halving a value
    like 4.05 independently would otherwise lose or gain a paisa.
    """
    tax = q2(tax_amount)
    if tax == 0 or not supply.charges_gst:
        return ZERO_SPLIT
    if supply.is_intra_state:
        cgst = q2(tax / 2)
        return TaxSplit(cgst=cgst, sgst=q2(tax - cgst), igst=Decimal("0.00"))
    return TaxSplit(cgst=Decimal("0.00"), sgst=Decimal("0.00"), igst=tax)


def split_rate(tax_rate_pct, supply: SupplyContext) -> TaxSplit:
    """Split a *rate* (e.g. 18 -> 9 CGST + 9 SGST) for display on the document."""
    rate = D(tax_rate_pct)
    if rate == 0 or not supply.charges_gst:
        return ZERO_SPLIT
    if supply.is_intra_state:
        half = q2(rate / 2)
        return TaxSplit(cgst=half, sgst=half, igst=Decimal("0.00"))
    return TaxSplit(cgst=Decimal("0.00"), sgst=Decimal("0.00"), igst=q2(rate))


__all__ = [
    "GST_STATE_CODES", "SUPPLY_INTRA", "SUPPLY_INTER", "SUPPLY_EXPORT",
    "SupplyContext", "TaxSplit", "ZERO_SPLIT",
    "is_valid_gstin", "state_code_from_gstin", "state_code_from_name", "state_name",
    "resolve_state_code", "resolve_supply", "split_tax", "split_rate",
]
