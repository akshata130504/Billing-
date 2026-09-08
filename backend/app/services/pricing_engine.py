"""Pricing calculation engine for Catalog and CPQ.

Handles:
- Flat rate
- Per-unit rate
- Volume pricing (all units evaluated at bracket rate)
- Graduated tiered pricing (incremental units evaluated bracket-by-bracket)
- Price Book layer overrides
- Deterministic rules evaluation
- "Why This Price?" mathematical transparency tree
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from backend.app.models.catalog_cpq import (
    Offering,
    OfferingPricingModel,
    PriceBook,
    PriceBookEntry,
    PriceBookStatus,
    CPQRule,
    RuleType,
)


def round_money(val: Decimal) -> Decimal:
    """Round to 2 decimal places using standard financial half-up rule."""
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


from datetime import date

def calculate_line_item_pricing(
    offering: Offering,
    quantity: Decimal,
    price_book_entry: Optional[PriceBookEntry] = None,
    line_discount_pct: Decimal = Decimal("0"),
) -> Dict[str, Any]:
    """
    Computes unit price, discounts, subtotal, tax and detailed calculation step explanation.
    Enforces Decimal financial precision (ROUND_HALF_UP).
    """
    if not offering.is_active:
        raise ValueError(f"Offering '{offering.name}' is archived and cannot be priced.")

    qty = Decimal(str(quantity))
    if qty < Decimal("0"):
        raise ValueError("Quantity must be non-negative.")

    base_price = Decimal(str(offering.base_price))
    tax_rate = Decimal(str(offering.tax_rate_pct))

    if qty == Decimal("0"):
        return {
            "unit_price": Decimal("0.00"),
            "subtotal": Decimal("0.00"),
            "discount_pct": Decimal("0.00"),
            "discount_amount": Decimal("0.00"),
            "net_amount": Decimal("0.00"),
            "tax_rate_pct": tax_rate,
            "tax_amount": Decimal("0.00"),
            "total_amount": Decimal("0.00"),
            "explanation": {
                "catalog_base_price": str(round_money(base_price)),
                "price_book_adjustment": None,
                "pricing_model": offering.pricing_model.value if hasattr(offering.pricing_model, "value") else str(offering.pricing_model),
                "effective_unit_price": "0.00",
                "tier_explanation": "Zero quantity selected",
                "quantity": "0",
                "subtotal_pre_discount": "0.00",
                "discount_pct": "0",
                "discount_amount": "0.00",
                "net_line_amount": "0.00",
                "tax_rate_pct": str(tax_rate),
                "tax_amount": "0.00",
                "total_line_amount": "0.00",
            },
        }

    # Step 1: Base & Price Book Layer
    step_price = base_price
    price_book_info = None
    is_expired = False
    has_custom_pb_price = False
    pb_discount_pct = Decimal("0")

    if price_book_entry and price_book_entry.is_active:
        pb = getattr(price_book_entry, "price_book", None)
        today = date.today()
        if pb:
            if pb.status != PriceBookStatus.ACTIVE:
                is_expired = True
            elif pb.effective_from and pb.effective_from > today:
                is_expired = True
            elif pb.effective_until and pb.effective_until < today:
                is_expired = True

        if not is_expired:
            if price_book_entry.custom_price is not None:
                step_price = Decimal(str(price_book_entry.custom_price))
                has_custom_pb_price = True
                price_book_info = f"Price book custom price applied: ₹{step_price}"
            elif price_book_entry.discount_pct and price_book_entry.discount_pct > 0:
                pb_discount_pct = Decimal(str(price_book_entry.discount_pct))
                pb_discount = (base_price * pb_discount_pct) / Decimal("100")
                step_price = max(Decimal("0"), base_price - pb_discount)
                price_book_info = f"Price book discount ({price_book_entry.discount_pct}%) applied: -₹{round_money(pb_discount)}"
        else:
            price_book_info = "Price book is expired or inactive (standard base price used)"

    # Step 2: Pricing Model (Flat, Per-Unit, Volume, Tiered)
    pricing_model = offering.pricing_model
    tier_note = None
    subtotal_pre_discount = Decimal("0")
    effective_unit_price = step_price

    if has_custom_pb_price:
        subtotal_pre_discount = step_price * qty
        effective_unit_price = step_price
        tier_note = f"Price book custom price override: ₹{step_price}/unit"

    elif pricing_model == OfferingPricingModel.FLAT:
        subtotal_pre_discount = step_price
        effective_unit_price = step_price
        tier_note = "Flat pricing: fixed amount regardless of quantity"

    elif pricing_model == OfferingPricingModel.VOLUME:
        # Check volume brackets in pricing_tiers
        tiers = offering.pricing_tiers or []
        bracket_found = False
        for tier in tiers:
            min_q = Decimal(str(tier.get("min_qty", 0)))
            max_q = Decimal(str(tier.get("max_qty"))) if tier.get("max_qty") is not None else None
            t_price = Decimal(str(tier.get("unit_price", step_price)))
            if pb_discount_pct > 0:
                t_price = max(Decimal("0"), t_price * (Decimal("1") - pb_discount_pct / Decimal("100")))

            if qty >= min_q and (max_q is None or qty <= max_q):
                effective_unit_price = t_price
                bracket_found = True
                tier_note = f"Volume bracket [{min_q} - {max_q or '∞'}]: ₹{t_price}/unit for all {qty} units"
                break

        if not bracket_found:
            effective_unit_price = step_price
        subtotal_pre_discount = effective_unit_price * qty

    elif pricing_model == OfferingPricingModel.TIERED:
        # Graduated tier brackets
        tiers = offering.pricing_tiers or []
        if not tiers:
            effective_unit_price = step_price
            subtotal_pre_discount = step_price * qty
        else:
            accumulated_subtotal = Decimal("0")
            remaining_qty = qty
            sorted_tiers = sorted(tiers, key=lambda t: Decimal(str(t.get("min_qty", 0))))
            tier_logs = []

            for tier in sorted_tiers:
                min_q = Decimal(str(tier.get("min_qty", 0)))
                max_q = Decimal(str(tier.get("max_qty"))) if tier.get("max_qty") is not None else None
                t_price = Decimal(str(tier.get("unit_price", step_price)))
                if pb_discount_pct > 0:
                    t_price = max(Decimal("0"), t_price * (Decimal("1") - pb_discount_pct / Decimal("100")))

                if min_q == 0 and max_q is not None:
                    bracket_capacity = max_q
                elif max_q is not None:
                    bracket_capacity = max_q - min_q + Decimal("1")
                else:
                    bracket_capacity = remaining_qty

                units_in_bracket = min(remaining_qty, bracket_capacity)
                if units_in_bracket > 0:
                    tier_cost = units_in_bracket * t_price
                    accumulated_subtotal += tier_cost
                    remaining_qty -= units_in_bracket
                    tier_logs.append(f"{units_in_bracket} units @ ₹{t_price}")

                if remaining_qty <= 0:
                    break

            subtotal_pre_discount = accumulated_subtotal
            effective_unit_price = round_money(accumulated_subtotal / qty) if qty > 0 else step_price
            tier_note = f"Graduated tiers: " + ", ".join(tier_logs)

    elif pricing_model == OfferingPricingModel.PACKAGE:
        # Package / Block pricing: items sold in package blocks (e.g. 10 for ₹5k, 25 for ₹10k, 50 for ₹18k)
        tiers = offering.pricing_tiers or []
        if not tiers:
            effective_unit_price = step_price
            subtotal_pre_discount = step_price * qty
            tier_note = f"Package pricing (single default package rate): ₹{step_price} for {qty} units"
        else:
            # Parse package definitions
            parsed_packages = []
            for t in tiers:
                p_qty = None
                if t.get("package_qty") is not None:
                    p_qty = Decimal(str(t["package_qty"]))
                elif t.get("max_qty") is not None:
                    p_qty = Decimal(str(t["max_qty"]))
                elif t.get("min_qty") is not None and Decimal(str(t["min_qty"])) > Decimal("0"):
                    p_qty = Decimal(str(t["min_qty"]))
                else:
                    p_qty = Decimal("1")

                p_price = None
                if t.get("package_price") is not None:
                    p_price = Decimal(str(t["package_price"]))
                elif t.get("unit_price") is not None:
                    p_price = Decimal(str(t["unit_price"]))
                else:
                    p_price = step_price

                if pb_discount_pct > Decimal("0"):
                    p_price = max(Decimal("0"), p_price * (Decimal("1") - pb_discount_pct / Decimal("100")))
                if p_qty > Decimal("0"):
                    parsed_packages.append((p_qty, p_price))

            if not parsed_packages:
                parsed_packages.append((Decimal("1"), step_price))

            sorted_packages = sorted(parsed_packages, key=lambda x: x[0])
            largest_size, largest_price = sorted_packages[-1]

            # 1. Exact package match
            matched = next((p for p in sorted_packages if p[0] == qty), None)
            if matched:
                subtotal_pre_discount = matched[1]
                effective_unit_price = round_money(matched[1] / qty) if qty > Decimal("0") else matched[1]
                tier_note = f"Package option: exact {qty}-unit package @ ₹{matched[1]}"
            elif qty <= largest_size:
                # Select the smallest package tier that accommodates the requested quantity
                covering = next((p for p in sorted_packages if p[0] >= qty), sorted_packages[-1])
                subtotal_pre_discount = covering[1]
                effective_unit_price = round_money(covering[1] / qty) if qty > Decimal("0") else covering[1]
                tier_note = f"Package option: {qty} units covered by {covering[0]}-unit package @ ₹{covering[1]}"
            else:
                # Quantity exceeds largest package: combine multiple largest packages + remainder package
                num_large = int(qty // largest_size) if largest_size > Decimal("0") else int(qty)
                rem = qty % largest_size if largest_size > Decimal("0") else Decimal("0")
                accum_pkg_cost = num_large * largest_price
                rem_note = ""
                if rem > Decimal("0"):
                    rem_pkg = next((p for p in sorted_packages if p[0] >= rem), sorted_packages[-1])
                    accum_pkg_cost += rem_pkg[1]
                    rem_note = f" + 1x {rem_pkg[0]}-unit package"

                subtotal_pre_discount = accum_pkg_cost
                effective_unit_price = round_money(accum_pkg_cost / qty) if qty > Decimal("0") else largest_price
                tier_note = f"Package option: {qty} units covered by {num_large}x {largest_size}-unit package(s){rem_note} @ ₹{accum_pkg_cost}"

    else:  # PER_UNIT default
        effective_unit_price = step_price
        subtotal_pre_discount = step_price * qty

    # Step 3: Line Discount
    discount_pct = min(Decimal("100"), max(Decimal("0"), Decimal(str(line_discount_pct))))
    discount_amount = round_money((subtotal_pre_discount * discount_pct) / Decimal("100"))
    net_line_amount = max(Decimal("0"), subtotal_pre_discount - discount_amount)

    # Step 4: Tax
    tax_amount = round_money((net_line_amount * tax_rate) / Decimal("100"))
    total_line_amount = net_line_amount + tax_amount

    explanation = {
        "catalog_base_price": str(round_money(base_price)),
        "price_book_adjustment": price_book_info,
        "pricing_model": pricing_model.value if hasattr(pricing_model, "value") else str(pricing_model),
        "effective_unit_price": str(round_money(effective_unit_price)),
        "tier_explanation": tier_note,
        "quantity": str(qty),
        "subtotal_pre_discount": str(round_money(subtotal_pre_discount)),
        "discount_pct": str(discount_pct),
        "discount_amount": str(discount_amount),
        "net_line_amount": str(round_money(net_line_amount)),
        "tax_rate_pct": str(tax_rate),
        "tax_amount": str(tax_amount),
        "total_line_amount": str(round_money(total_line_amount)),
    }

    return {
        "unit_price": round_money(effective_unit_price),
        "subtotal": round_money(subtotal_pre_discount),
        "discount_pct": discount_pct,
        "discount_amount": discount_amount,
        "net_amount": round_money(net_line_amount),
        "tax_rate_pct": tax_rate,
        "tax_amount": tax_amount,
        "total_amount": round_money(total_line_amount),
        "explanation": explanation,
    }


def evaluate_cpq_rules(
    offerings_map: Dict[str, Offering],
    selected_items: List[Dict[str, Any]],
    active_rules: List[CPQRule],
    customer_segment: Optional[str] = None,
) -> Tuple[List[str], List[str], List[Dict[str, Any]]]:
    """
    Evaluates compatibility, requirements, exclusions, and suggestions.
    Returns:
    (warnings_or_errors, rule_messages, recommendations)
    """
    warnings = []
    messages = []
    recommendations = []

    selected_ids = {item["offering_id"] for item in selected_items}
    quantities = {item["offering_id"]: Decimal(str(item.get("quantity", 1))) for item in selected_items}

    # Sort rules by priority (lowest number = highest priority)
    sorted_rules = sorted(active_rules, key=lambda r: r.priority)

    for rule in sorted_rules:
        cond = rule.conditions or {}
        act = rule.actions or {}

        target_offering_id = cond.get("offering_id")
        min_qty = Decimal(str(cond.get("min_qty", 0)))
        rule_segment = cond.get("customer_segment")

        # Condition match check
        applies = True
        if target_offering_id and target_offering_id not in selected_ids:
            applies = False
        if target_offering_id and quantities.get(target_offering_id, Decimal("0")) < min_qty:
            applies = False
        if rule_segment and customer_segment and rule_segment.lower() != customer_segment.lower():
            applies = False

        if not applies:
            continue

        # Execute rule action
        if rule.rule_type == RuleType.REQUIRES:
            req_id = act.get("requires_offering_id")
            req_name = offerings_map.get(req_id).name if req_id in offerings_map else req_id
            if req_id and req_id not in selected_ids:
                warnings.append(f"Rule '{rule.name}': Selecting this offering requires '{req_name}'.")

        elif rule.rule_type == RuleType.EXCLUDES:
            exc_id = act.get("excludes_offering_id")
            exc_name = offerings_map.get(exc_id).name if exc_id in offerings_map else exc_id
            if exc_id and exc_id in selected_ids:
                warnings.append(f"Rule '{rule.name}': Incompatible selection — cannot bundle with '{exc_name}'.")

        elif rule.rule_type == RuleType.RECOMMENDS:
            rec_id = act.get("recommends_offering_id")
            if rec_id and rec_id not in selected_ids and rec_id in offerings_map:
                rec_offering = offerings_map[rec_id]
                recommendations.append({
                    "offering_id": rec_offering.id,
                    "name": rec_offering.name,
                    "sku": rec_offering.sku,
                    "base_price": str(rec_offering.base_price),
                    "reason": act.get("reason", f"Frequently paired under rule '{rule.name}'"),
                })

        if act.get("message"):
            messages.append(act.get("message"))

    return warnings, messages, recommendations
