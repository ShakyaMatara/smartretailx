"""Unit tests for password hashing. No running services required."""
import pytest

pytestmark = pytest.mark.unit


def test_hash_is_not_the_plaintext():
    from security import hash_password
    password = "CorrectHorseBattery"
    assert hash_password(password) != password


def test_hash_uses_argon2id():
    """The stored format encodes the algorithm and its parameters."""
    from security import hash_password
    digest = hash_password("CorrectHorseBattery")
    assert digest.startswith("$argon2id$")
    assert "m=" in digest and "t=" in digest and "p=" in digest


def test_identical_passwords_produce_different_hashes():
    """A unique salt per password defeats rainbow-table attacks and
    hides the fact that two users share a password."""
    from security import hash_password
    assert hash_password("SamePassword123") != hash_password("SamePassword123")


def test_correct_password_verifies():
    from security import hash_password, verify_password
    digest = hash_password("CorrectHorseBattery")
    assert verify_password("CorrectHorseBattery", digest) is True


def test_wrong_password_rejected():
    from security import hash_password, verify_password
    digest = hash_password("CorrectHorseBattery")
    assert verify_password("WrongPassword", digest) is False


def test_malformed_hash_rejected_without_raising():
    """A corrupted stored value must fail closed, not crash the service."""
    from security import verify_password
    assert verify_password("anything", "not-a-valid-hash") is False
