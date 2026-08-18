"""Integration tests: user service against its PostgreSQL database."""
import uuid

import pytest
from conftest import USER_URL

pytestmark = pytest.mark.integration


def _new_user(client, password="ValidPassword2026"):
    email = f"itest-{uuid.uuid4().hex[:12]}@example.com"
    response = client.post(
        f"{USER_URL}/api/v1/users/register",
        json={"email": email, "full_name": "Integration Test", "password": password},
    )
    return email, password, response


def test_registration_persists_and_returns_the_user(client):
    email, _, response = _new_user(client)
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == email
    assert body["is_active"] is True
    assert uuid.UUID(body["id"])


def test_registration_never_returns_credential_material(client):
    _, _, response = _new_user(client)
    body = response.json()
    assert "password" not in body
    assert "password_hash" not in body


def test_role_is_assigned_by_the_server_not_the_client(client):
    """Accepting a role from the request body would permit privilege
    escalation at registration."""
    email = f"itest-{uuid.uuid4().hex[:12]}@example.com"
    response = client.post(
        f"{USER_URL}/api/v1/users/register",
        json={"email": email, "full_name": "Escalation Attempt",
              "password": "ValidPassword2026", "role": "admin"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "customer"


def test_duplicate_email_is_rejected(client):
    email, password, first = _new_user(client)
    assert first.status_code == 201

    second = client.post(
        f"{USER_URL}/api/v1/users/register",
        json={"email": email, "full_name": "Duplicate", "password": password},
    )
    assert second.status_code == 409


def test_login_issues_an_access_and_refresh_token_pair(client):
    email, password, _ = _new_user(client)
    response = client.post(
        f"{USER_URL}/api/v1/auth/login",
        data={"username": email, "password": password},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] > 0


def test_jwks_endpoint_publishes_the_public_key(client):
    response = client.get(f"{USER_URL}/.well-known/jwks.json")
    assert response.status_code == 200
    key = response.json()["keys"][0]
    assert key["kty"] == "RSA" and key["use"] == "sig" and key["alg"] == "RS256"
    assert "d" not in key, "private exponent must never be published"
