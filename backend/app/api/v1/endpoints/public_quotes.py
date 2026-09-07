"""Public hosted quote page (no auth). Mounted at /public/quotes."""
from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from backend.app.api.deps import get_db
from backend.app.schemas.quotes import PublicQuote, PublicQuoteAcceptIn, PublicQuoteDeclineIn, PublicQuoteStatusOut
from backend.app.services import quote_service as svc

router = APIRouter()


@router.get("/{token}", response_model=PublicQuote, summary="Hosted quote page data")
def get_public_quote(token: str, db: Session = Depends(get_db)):
    quote = svc.get_public_quote_or_404(db, token)
    return svc.serialize_public_quote(db, quote)


@router.post("/{token}/accept", response_model=PublicQuoteStatusOut, summary="Customer accepts the quote")
def accept_public_quote(token: str, body: PublicQuoteAcceptIn, db: Session = Depends(get_db)):
    quote = svc.public_accept(db, token, body.accepted_by_name)
    return {"status": quote.status.value}


@router.post("/{token}/decline", response_model=PublicQuoteStatusOut, summary="Customer declines the quote")
def decline_public_quote(
    token: str,
    body: PublicQuoteDeclineIn = Body(default=PublicQuoteDeclineIn()),
    db: Session = Depends(get_db),
):
    quote = svc.public_decline(db, token, body.reason)
    return {"status": quote.status.value}
