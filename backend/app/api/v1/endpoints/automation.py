"""/automation — minimal WHEN/IF/THEN rule engine over real billing events."""
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.api.deps import CurrentContext, get_db, require_admin, require_viewer
from backend.app.schemas.automation import (
    AutomationDashboardOut,
    AutomationExecutionOut,
    AutomationRuleActiveIn,
    AutomationRuleIn,
    AutomationRuleOut,
)
from backend.app.schemas.common import PaginatedResponse
from backend.app.services import automation_service
from backend.app.services.pagination import PageParams, page_params

router = APIRouter()


@router.get("/dashboard", response_model=AutomationDashboardOut, summary="Automation dashboard")
def get_dashboard(ctx: CurrentContext = Depends(require_viewer), db: Session = Depends(get_db)):
    return automation_service.dashboard(db, ctx.organization_id)


@router.get("/rules", response_model=PaginatedResponse[AutomationRuleOut], summary="List automation rules")
def list_rules(
    is_active: Optional[bool] = Query(None),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = automation_service.list_rules(db, ctx.organization_id, params, is_active=is_active)
    return page.to_response(automation_service.serialize_rule)


@router.post("/rules", response_model=AutomationRuleOut, status_code=status.HTTP_201_CREATED, summary="Create an automation rule")
def create_rule(body: AutomationRuleIn, ctx: CurrentContext = Depends(require_admin), db: Session = Depends(get_db)):
    rule = automation_service.create_rule(db, ctx, body)
    return automation_service.serialize_rule(rule)


@router.patch("/rules/{rule_id}", response_model=AutomationRuleOut, summary="Enable/disable a rule")
def set_active(
    rule_id: str,
    body: AutomationRuleActiveIn,
    ctx: CurrentContext = Depends(require_admin),
    db: Session = Depends(get_db),
):
    rule = automation_service.get_rule(db, ctx.organization_id, rule_id)
    rule = automation_service.set_rule_active(db, ctx, rule, body.is_active)
    return automation_service.serialize_rule(rule)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, summary="Delete a rule")
def delete_rule(rule_id: str, ctx: CurrentContext = Depends(require_admin), db: Session = Depends(get_db)):
    rule = automation_service.get_rule(db, ctx.organization_id, rule_id)
    automation_service.delete_rule(db, ctx, rule)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/executions", response_model=PaginatedResponse[AutomationExecutionOut], summary="Execution history")
def list_executions(
    rule_id: Optional[str] = Query(None),
    params: PageParams = Depends(page_params),
    ctx: CurrentContext = Depends(require_viewer),
    db: Session = Depends(get_db),
):
    page = automation_service.list_executions(db, ctx.organization_id, params, rule_id=rule_id)
    return page.to_response(automation_service.serialize_execution)
