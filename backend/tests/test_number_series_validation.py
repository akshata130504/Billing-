"""BUG-50: custom number-series prefixes and suffixes cannot carry markup into document numbers."""
import pytest
from pydantic import ValidationError

from backend.app.schemas.customization import (
    NumberSeriesPreviewRequest,
    TransactionNumberSeriesCreate,
    TransactionNumberSeriesUpdate,
)


@pytest.mark.parametrize("affix", ["INV-", "INV-{YYYY}/", "{YYYY}{MM}{DD}-", "Q_2026", ""])
def test_valid_affixes_accepted(affix):
    assert TransactionNumberSeriesCreate(module="invoice", name="Main", prefix=affix, suffix=affix).prefix == affix


@pytest.mark.parametrize("affix", ["<b>X</b>", "INV #", "a b", "{YEAR}", "INV-{YYYY", "=1+1"])
def test_markup_and_unknown_tokens_rejected_on_create_update_and_preview(affix):
    with pytest.raises(ValidationError):
        TransactionNumberSeriesCreate(module="invoice", name="Main", prefix=affix)
    with pytest.raises(ValidationError):
        TransactionNumberSeriesUpdate(suffix=affix)
    with pytest.raises(ValidationError):
        NumberSeriesPreviewRequest(prefix=affix)
