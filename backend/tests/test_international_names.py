"""BUG-09: international / punctuated business names must be accepted while
HTML-ish and spreadsheet-formula input stays rejected."""
import pytest
from pydantic import ValidationError

from backend.app.schemas.customers import CustomerCreate
from backend.app.schemas.validators import validate_sensible_name

ACCEPTED = [
    "Müller GmbH",
    "Société Générale QA",
    "شركة الاختبار",
    "测试公司",
    "José Ñúñez",
    "QA-Co_1 / Unit #2",
    "St. John's Hospital (Pvt) & Co.",
    "Acme+Partners @ HQ: Unit 4",
    "-Dash Leading Co",
]

REJECTED = [
    "<script>alert(1)</script>",
    "Acme <b>",
    'Acme "Quoted"',
    "Acme `tick`",
    "=HYPERLINK(\"x\")",
    "=SUM(A1)",
    "@SUM(A1)",
    "+Acme",
    "Acme = Co",
    "123456",
    "   ",
]


@pytest.mark.parametrize("name", ACCEPTED)
def test_international_and_punctuated_names_accepted(name):
    assert validate_sensible_name(name, "Customer name") == name
    assert CustomerCreate(display_name=name, company_name=name).display_name == name


@pytest.mark.parametrize("name", REJECTED)
def test_html_formula_and_numeric_names_rejected(name):
    with pytest.raises(ValidationError):
        CustomerCreate(display_name=name)
    if name.strip():  # a blank optional company name is simply "not provided"
        with pytest.raises(ValidationError):
            CustomerCreate(display_name="Valid Co", company_name=name)
