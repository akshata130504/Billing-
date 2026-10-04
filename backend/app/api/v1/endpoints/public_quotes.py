"""Public hosted quote page. Mounted at /public/quotes.

No staff session: the unguessable per-quote link token emailed to the customer is the credential.
It resolves exactly one quote (so its tenant and customer), and the page exposes no internal ids.
"""
from fastapi import APIRouter, Body, Depends, Request
from sqlalchemy.orm import Session

from backend.app.api.deps import client_ip, get_db
from backend.app.core.rate_limit import limiter, public_action_rate_limit, public_rate_limit
from backend.app.schemas.quotes import PublicQuote, PublicQuoteAcceptIn, PublicQuoteDeclineIn, PublicQuoteStatusOut
from backend.app.services import org_lifecycle
from backend.app.services import quote_service as svc

router = APIRouter()


def _ua(request: Request):
    return (request.headers.get("user-agent") or "")[:400] or None


@router.get("/{token}", response_model=PublicQuote, summary="Hosted quote page data")
@limiter.limit(public_rate_limit)
def get_public_quote(request: Request, token: str, db: Session = Depends(get_db)):
    quote = svc.get_public_quote_or_404(db, token)
    org_lifecycle.assert_customer_pages_visible(db, quote.organization_id)
    quote = svc.mark_public_viewed(db, quote)
    out = svc.serialize_public_quote(db, quote)
    if not org_lifecycle.customer_actions_allowed(db, quote.organization_id):
        out["actions_unavailable_reason"] = org_lifecycle.CUSTOMER_UNAVAILABLE_MESSAGE
    return out


@router.post("/{token}/accept", response_model=PublicQuoteStatusOut, summary="Customer accepts the quote")
@limiter.limit(public_action_rate_limit)
def accept_public_quote(request: Request, token: str, body: PublicQuoteAcceptIn, db: Session = Depends(get_db)):
    org_lifecycle.assert_customer_actions_allowed(db, svc.get_public_quote_or_404(db, token).organization_id)
    quote = svc.public_accept(
        db, token, body.accepted_by_name, ip_address=client_ip(request), user_agent=_ua(request)
    )
    return {"status": quote.status.value}


@router.post("/{token}/decline", response_model=PublicQuoteStatusOut, summary="Customer declines the quote")
@limiter.limit(public_action_rate_limit)
def decline_public_quote(
    request: Request,
    token: str,
    body: PublicQuoteDeclineIn = Body(default=PublicQuoteDeclineIn()),
    db: Session = Depends(get_db),
):
    org_lifecycle.assert_customer_actions_allowed(db, svc.get_public_quote_or_404(db, token).organization_id)
    quote = svc.public_decline(
        db, token, body.reason, ip_address=client_ip(request), user_agent=_ua(request)
    )
    return {"status": quote.status.value}
