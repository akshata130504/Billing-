"""Usage meters, event ingestion, and rating API endpoints."""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_finance, require_viewer
from backend.app.schemas.common_refs import money_str, paginated_of
from backend.app.schemas.meters import (
    BillingCycleOut,
    UsageAggregateOut,
    UsageEventBatchIn,
    UsageEventIn,
    UsageEventOut,
    UsageMeterCreateIn,
    UsageMeterOut,
    UsageMeterSummaryOut,
    UsageMeterUpdateIn,
)
from backend.app.services import meter_service
from backend.app.services.pagination import PageParams, page_params, paginate

router = APIRouter()


def _serialize_event(ev) -> dict:
    return {
        "id": ev.id,
        "meter_id": ev.meter_id,
        "customer_id": ev.customer_id,
        "subscription_id": ev.subscription_id,
        "quantity": str(ev.quantity),
        "timestamp": ev.timestamp,
        "idempotency_key": ev.idempotency_key,
        "status": ev.status,
        "created_at": ev.created_at,
    }


def _serialize_aggregate(agg) -> dict:
    return {
        "id": agg.id,
        "meter_id": agg.meter_id,
        "subscription_id": agg.subscription_id,
        "billing_cycle_id": agg.billing_cycle_id,
        "period_start": agg.period_start,
        "period_end": agg.period_end,
        "total_quantity": str(agg.total_quantity),
        "rated_amount": money_str(agg.rated_amount),
        "status": agg.status,
        "finalized_at": agg.finalized_at,
        "invoice_id": agg.invoice_id,
    }


@router.post(
    "",
    response_model=UsageMeterOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new usage meter",
)
def create_meter(
    body: UsageMeterCreateIn,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return meter_service.create_meter(
        db,
        organization_id=ctx.organization_id,
        code=body.code,
        name=body.name,
        unit_name=body.unit_name,
        aggregation_type=body.aggregation_type,
        description=body.description,
        unit_price=body.unit_price,
    )


@router.get(
    "",
    response_model=List[UsageMeterOut],
    summary="List all usage meters for the organization",
)
def list_meters(
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return meter_service.list_meters(db, ctx.organization_id)


@router.get(
    "/billing-cycles",
    response_model=List[BillingCycleOut],
    summary="List a subscription's billing cycles (newest first) for usage finalization",
)
def list_billing_cycles(
    subscription_id: str = Query(..., min_length=1),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    cycles = meter_service.list_billing_cycles(db, ctx.organization_id, subscription_id)
    return [
        {
            "id": c.id,
            "subscription_id": c.subscription_id,
            "cycle_number": c.cycle_number,
            "period_start": c.period_start,
            "period_end": c.period_end,
            "status": c.status.value if hasattr(c.status, "value") else str(c.status),
            "invoice_id": c.invoice_id,
            "finalized_at": c.finalized_at,
        }
        for c in cycles
    ]


@router.get(
    "/events",
    response_model=paginated_of(UsageEventOut),
    summary="List recorded usage events (newest first), filterable by meter, customer, subscription and date",
)
def list_events(
    meter_id: Optional[str] = Query(None, description="Meter id or code"),
    customer_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
    date_from: Optional[date] = Query(None, description="Inclusive, organization-local day"),
    date_to: Optional[date] = Query(None, description="Inclusive, organization-local day"),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    stmt = meter_service.list_usage_events_query(
        db,
        ctx.organization_id,
        meter_id_or_code=meter_id,
        customer_id=customer_id,
        subscription_id=subscription_id,
        date_from=date_from,
        date_to=date_to,
    )
    return paginate(db, stmt, params).to_response(
        lambda ev: {
            **_serialize_event(ev),
            "customer_name": ev.customer.display_name if ev.customer else None,
            "subscription_number": ev.subscription.subscription_number if ev.subscription else None,
        }
    )


@router.get(
    "/usage-summary",
    response_model=List[UsageMeterSummaryOut],
    summary="Per-meter running totals of recorded usage for a period",
)
def usage_summary(
    meter_id: Optional[str] = Query(None, description="Meter id or code"),
    customer_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
    date_from: Optional[date] = Query(None, description="Inclusive, organization-local day"),
    date_to: Optional[date] = Query(None, description="Inclusive, organization-local day"),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    rows = meter_service.usage_summary(
        db,
        ctx.organization_id,
        meter_id_or_code=meter_id,
        customer_id=customer_id,
        subscription_id=subscription_id,
        date_from=date_from,
        date_to=date_to,
    )
    return [{**r, "total_quantity": str(r["total_quantity"])} for r in rows]


@router.get(
    "/{meter_id}",
    response_model=UsageMeterOut,
    summary="Get usage meter details",
)
def get_meter(
    meter_id: str,
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    return meter_service.get_meter(db, ctx.organization_id, meter_id)


@router.patch(
    "/{meter_id}",
    response_model=UsageMeterOut,
    summary="Update a usage meter (name, unit, per-unit price, active flag)",
)
def update_meter(
    meter_id: str,
    body: UsageMeterUpdateIn,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return meter_service.update_meter(db, ctx.organization_id, meter_id, body.model_dump(exclude_unset=True))


@router.post(
    "/events",
    response_model=UsageEventOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a single raw usage event (idempotent)",
)
def record_event(
    body: UsageEventIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    ev = meter_service.record_usage_event(
        db,
        organization_id=ctx.organization_id,
        meter_id_or_code=body.meter_code,
        customer_id=body.customer_id,
        quantity=body.quantity,
        idempotency_key=body.idempotency_key,
        subscription_id=body.subscription_id,
        timestamp=body.timestamp,
        properties=body.properties,
    )
    return _serialize_event(ev)


@router.post(
    "/events/batch",
    response_model=List[UsageEventOut],
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a batch of raw usage events (idempotent)",
)
def record_batch_events(
    body: UsageEventBatchIn,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    # Atomic: one commit for the whole batch; any invalid event rejects all of them.
    events = meter_service.record_usage_events_batch(
        db,
        ctx.organization_id,
        [
            {
                "meter_id_or_code": ev_in.meter_code,
                "customer_id": ev_in.customer_id,
                "quantity": ev_in.quantity,
                "idempotency_key": ev_in.idempotency_key,
                "subscription_id": ev_in.subscription_id,
                "timestamp": ev_in.timestamp,
                "properties": ev_in.properties,
            }
            for ev_in in body.events
        ],
    )
    return [_serialize_event(ev) for ev in events]


@router.post(
    "/subscriptions/{subscription_id}/billing-cycles/{cycle_id}/finalize-usage",
    response_model=List[UsageAggregateOut],
    summary="Finalize rated usage for a subscription billing cycle (one aggregate per meter)",
)
def finalize_cycle_usage(
    subscription_id: str,
    cycle_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    aggregates = meter_service.finalize_usage_for_cycle(
        db, ctx=ctx, subscription_id=subscription_id, billing_cycle_id=cycle_id
    )
    return [_serialize_aggregate(agg) for agg in aggregates]
