import pytest
from pydantic import ValidationError
from voice_api.schemas.contact import ContactBody


def test_contact_normalization_and_unknown_timezone():
    contact = ContactBody(name="Test", phone_number="+1 (555) 555-0100")
    assert contact.phone_number == "+15555550100" and contact.timezone is None
    assert (
        ContactBody(name="Test", phone_number="+15555550100", timezone="Asia/Kolkata").timezone
        == "Asia/Kolkata"
    )


def test_contact_name_parts_compose_full_name_and_legacy_names_are_split():
    parts = ContactBody(first_name="  Omkar ", last_name=" Pawar ", phone_number="+15555550100")
    legacy = ContactBody(name="Omkar   Pawar", phone_number="+15555550100")

    assert (parts.name, parts.first_name, parts.last_name) == ("Omkar Pawar", "Omkar", "Pawar")
    assert (legacy.name, legacy.first_name, legacy.last_name) == (
        "Omkar Pawar",
        "Omkar",
        "Pawar",
    )


@pytest.mark.parametrize(
    "change",
    [{"phone_number": "5555550100"}, {"timezone": "Moon/Base"}, {"phone_number": "+123;ATH"}],
)
def test_invalid_contact_rejected(change):
    with pytest.raises(ValidationError):
        ContactBody(**{"name": "Test", "phone_number": "+15555550100", **change})
