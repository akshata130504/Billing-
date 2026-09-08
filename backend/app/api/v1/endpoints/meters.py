"""Usage meters, event ingestion, and rating API endpoints."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_finance, require_viewer
from backend.app.schemas.common_refs import money_str
from backend.app.schemas.meters import (
    UsageAggregateOut,
    UsageEventBatchIn,
    UsageEventIn,
    UsageEventOut,
    UsageMeterCreateIn,
    UsageMeterOut,
)
from backend.app.services import meter_service

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


@router.post(
    "/events",
    response_model=UsageEventOut,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a single raw usage event (idempotent)",
)
def record_event(
    body: UsageEventIn,
    ctx: CurrentContext = Depends(require_viewer),
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
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    results = []
    for ev_in in body.events:
        ev = meter_service.record_usage_event(
            db,
            organization_id=ctx.organization_id,
            meter_id_or_code=ev_in.meter_code,
            customer_id=ev_in.customer_id,
            quantity=ev_in.quantity,
            idempotency_key=ev_in.idempotency_key,
            subscription_id=ev_in.subscription_id,
            timestamp=ev_in.timestamp,
            properties=ev_in.properties,
        )
        results.append(_serialize_event(ev))
    return results


@router.post(
    "/subscriptions/{subscription_id}/billing-cycles/{cycle_id}/finalize-usage",
    response_model=UsageAggregateOut,
    summary="Finalize rated usage for a subscription billing cycle",
)
def finalize_cycle_usage(
    subscription_id: str,
    cycle_id: str,
    ctx: CurrentContext = Depends(require_finance),
    db: Session = Depends(get_db),
):
    agg = meter_service.finalize_usage_for_cycle(
        db, ctx=ctx, subscription_id=subscription_id, billing_cycle_id=cycle_id
    )
    return _serialize_aggregate(agg)
