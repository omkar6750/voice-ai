import pytest
from pydantic import ValidationError
from voice_api.contact_contracts import ContactBody


def test_contact_normalization_and_unknown_timezone():
    contact = ContactBody(name="Test", phone_number="+1 (555) 555-0100")
    assert contact.phone_number == "+15555550100" and contact.timezone is None
    assert (
        ContactBody(name="Test", phone_number="+15555550100", timezone="Asia/Kolkata").timezone
        == "Asia/Kolkata"
    )


@pytest.mark.parametrize(
    "change",
    [{"phone_number": "5555550100"}, {"timezone": "Moon/Base"}, {"phone_number": "+123;ATH"}],
)
def test_invalid_contact_rejected(change):
    with pytest.raises(ValidationError):
        ContactBody(**{"name": "Test", "phone_number": "+15555550100", **change})
