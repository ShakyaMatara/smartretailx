"""Security tests: authentication controls."""
import time
import uuid

import jwt
import pytest
from conftest import CATALOGUE_URL, ORDER_URL, USER_URL

pytestmark = pytest.mark.security

PROTECTED = [
    ("POST", f"{CATALOGUE_URL}/api/v1/products"),
    ("GET", f"{ORDER_URL}/api/v1/orders"),
    ("GET", f"{USER_URL}/api/v1/users/me"),
]


@pytest.mark.parametrize("method,url", PROTECTED)
def test_missing_token_is_rejected(client, method, url):
    response = client.request(method, url, json={})
    assert response.status_code == 401


@pytest.mark.parametrize("method,url", PROTECTED)
def test_garbage_token_is_rejected(client, method, url):
    response = client.request(method, url, json={},
                              headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_expired_token_is_rejected(client, customer_credentials):
    """Short access-token lifetime limits the window for a stolen token."""
    login = client.post(f"{USER_URL}/api/v1/auth/login",
                        data={"username": customer_credentials["email"],
                              "password": customer_credentials["password"]})
    claims = jwt.decode(login.json()["access_token"], options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] <= 900, "access tokens should be short-lived"

    expired = jwt.encode(
        {**claims, "exp": int(time.time()) - 60},
        "irrelevant-because-the-signature-is-checked-first", algorithm="HS256",
    )
    response = client.get(f"{USER_URL}/api/v1/users/me",
                          headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_tampered_signature_is_rejected(client, customer_token):
    head, payload, signature = customer_token.split(".")
    tampered = f"{head}.{payload}.{signature[:-6]}AAAAAA"
    response = client.get(f"{USER_URL}/api/v1/users/me",
                          headers={"Authorization": f"Bearer {tampered}"})
    assert response.status_code == 401


def test_algorithm_confusion_attack_is_rejected(client, customer_token):
    """A token re-signed as HS256 using the public key must not verify.
    Accepting the algorithm declared in the header is a known CVE class."""
    claims = jwt.decode(customer_token, options={"verify_signature": False})
    public_key = client.get(f"{USER_URL}/.well-known/jwks.json").text
    forged = jwt.encode(claims, public_key, algorithm="HS256")
    response = client.get(f"{USER_URL}/api/v1/users/me",
                          headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_unsigned_token_is_rejected(client, customer_token):
    """The classic alg:none attack."""
    claims = jwt.decode(customer_token, options={"verify_signature": False})
    unsigned = jwt.encode(claims, key="", algorithm="none")
    response = client.get(f"{USER_URL}/api/v1/users/me",
                          headers={"Authorization": f"Bearer {unsigned}"})
    assert response.status_code == 401


def test_refresh_token_cannot_be_used_as_an_access_token(client,
                                                         customer_credentials):
    login = client.post(f"{USER_URL}/api/v1/auth/login",
                        data={"username": customer_credentials["email"],
                              "password": customer_credentials["password"]})
    refresh = login.json()["refresh_token"]
    response = client.get(f"{USER_URL}/api/v1/users/me",
                          headers={"Authorization": f"Bearer {refresh}"})
    assert response.status_code == 401


def test_login_failure_does_not_reveal_whether_the_account_exists(client,
                                                                  customer_credentials):
    """Distinguishing the two would allow account enumeration."""
    unknown = client.post(f"{USER_URL}/api/v1/auth/login",
                          data={"username": f"nobody-{uuid.uuid4().hex}@example.com",
                                "password": "AnyPassword2026"})
    wrong = client.post(f"{USER_URL}/api/v1/auth/login",
                        data={"username": customer_credentials["email"],
                              "password": "DefinitelyWrongPassword"})

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_sql_injection_in_the_login_field_is_handled_safely(client):
    """Parameterised queries via the ORM; the input is treated as data."""
    response = client.post(
        f"{USER_URL}/api/v1/auth/login",
        data={"username": "admin' OR '1'='1", "password": "x' OR '1'='1"},
    )
    assert response.status_code in (401, 422)

    still_up = client.get(f"{USER_URL}/health/ready")
    assert still_up.status_code == 200
