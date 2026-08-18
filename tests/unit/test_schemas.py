"""Unit tests for request and response validation."""
import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def test_registration_rejects_a_short_password():
    from schemas import UserRegisterRequest
    with pytest.raises(ValidationError):
        UserRegisterRequest(email="a@example.com", full_name="Test", password="short")


def test_registration_rejects_a_malformed_email():
    from schemas import UserRegisterRequest
    with pytest.raises(ValidationError):
        UserRegisterRequest(email="not-an-email", full_name="Test",
                            password="LongEnoughPassword")


def test_registration_accepts_a_valid_payload():
    from schemas import UserRegisterRequest
    payload = UserRegisterRequest(email="a@example.com", full_name="Test User",
                                  password="LongEnoughPassword")
    assert payload.email == "a@example.com"


def test_user_response_cannot_expose_the_password_hash():
    """The response schema is an allow-list, so a sensitive column
    cannot leak through an endpoint by accident."""
    from schemas import UserResponse
    assert "password_hash" not in UserResponse.model_fields
    assert "password" not in UserResponse.model_fields
