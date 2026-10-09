import pytest
from pydantic import ValidationError
from voice_runtime.contracts.referrals import SaveReferralArguments, referral_parameters
from voice_runtime.contracts.registry import registered_handler_specs
from voice_runtime.contracts.tools import ToolConfig


def test_handler_and_aliased_tools_have_canonical_schema():
    spec = next(item for item in registered_handler_specs() if item.name == "save_referral")
    tool = ToolConfig(name="capture_referral", handler="save_referral", parameters={})
    assert tool.parameters == spec.parameters == referral_parameters()
    assert "read" in tool.description and "never calls" in tool.description
    assert tool.parameters["required"] == ["first_name"]


def test_referral_never_guesses_phone_country_and_trims_unknown_fields():
    args = SaveReferralArguments(first_name=" Asha ", phone_number="9876543210", last_name=" ")
    assert args.first_name == "Asha" and args.last_name is None
    assert args.phone_number == "9876543210"
    with pytest.raises(ValidationError):
        SaveReferralArguments(first_name=" ")
    with pytest.raises(ValidationError):
        SaveReferralArguments(first_name="Asha", phone_verified=True)
