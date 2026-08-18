"""Shared fixtures for the SmartRetailX test suite.

Integration, API, end-to-end and security tests run against the running
Docker Compose stack. Unit tests run in-process and need no containers.
"""
import os
import sys
import uuid
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent

# Service base URLs. Overridable so the same suite can run against a
# deployed environment by exporting different values.
USER_URL = os.getenv("USER_URL", "http://localhost:8001")
CATALOGUE_URL = os.getenv("CATALOGUE_URL", "http://localhost:8002")
ORDER_URL = os.getenv("ORDER_URL", "http://localhost:8003")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:8004")
PAYMENT_URL = os.getenv("PAYMENT_URL", "http://localhost:8005")
NOTIFICATION_URL = os.getenv("NOTIFICATION_URL", "http://localhost:8006")

# An account that already holds the admin role. Created during
# development and promoted directly in the database, because the API
# deliberately refuses to accept a role from client input.
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "shakya@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "CorrectHorseBattery")


def _unique_email(prefix="test"):
    """Every run uses fresh addresses so repeated runs cannot collide."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


def _login(email, password):
    response = httpx.post(
        f"{USER_URL}/api/v1/auth/login",
        data={"username": email, "password": password},
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()["access_token"]


# ── unit-test support ──────────────────────────────────────
@pytest.fixture(scope="session", autouse=True)
def _unit_test_paths():
    """Expose the user service modules and point key paths at the repo
    copies, so token and hashing logic can be tested in-process."""
    sys.path.insert(0, str(ROOT / "services" / "user-service"))
    os.environ.setdefault("JWT_PRIVATE_KEY_PATH", str(ROOT / "keys" / "jwt-private.pem"))
    os.environ.setdefault("JWT_PUBLIC_KEY_PATH", str(ROOT / "keys" / "jwt-public.pem"))
    yield


# ── shared HTTP fixtures ───────────────────────────────────
@pytest.fixture(scope="session")
def client():
    with httpx.Client(timeout=15.0) as c:
        yield c


@pytest.fixture(scope="session")
def admin_token():
    """Bearer token carrying the admin role."""
    try:
        return _login(ADMIN_EMAIL, ADMIN_PASSWORD)
    except Exception as exc:
        pytest.skip(f"admin account unavailable ({exc}) — set ADMIN_EMAIL / ADMIN_PASSWORD")


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def customer_credentials():
    """A freshly registered customer account."""
    email, password = _unique_email("customer"), "CustomerPassword2026"
    response = httpx.post(
        f"{USER_URL}/api/v1/users/register",
        json={"email": email, "full_name": "Test Customer", "password": password},
        timeout=10.0,
    )
    assert response.status_code == 201, response.text
    return {"email": email, "password": password, "id": response.json()["id"]}


@pytest.fixture(scope="session")
def customer_token(customer_credentials):
    return _login(customer_credentials["email"], customer_credentials["password"])


@pytest.fixture(scope="session")
def customer_headers(customer_token):
    return {"Authorization": f"Bearer {customer_token}"}


@pytest.fixture(scope="session")
def seeded_product(client, admin_headers):
    """A catalogue product with stock, used by the order tests."""
    product = client.post(
        f"{CATALOGUE_URL}/api/v1/products",
        headers=admin_headers,
        json={
            "name": "Test Widget",
            "description": "Created by the automated test suite",
            "category": "test-fixtures",
            "price": 10.00,
            "currency": "EUR",
            "sku": f"TW-{uuid.uuid4().hex[:8]}",
        },
    )
    assert product.status_code == 201, product.text
    product_id = product.json()["product_id"]

    stock = client.put(
        f"{INVENTORY_URL}/api/v1/inventory/{product_id}",
        headers=admin_headers,
        json={"product_id": product_id, "available": 500},
    )
    assert stock.status_code == 200, stock.text
    return product_id


@pytest.fixture
def idem_key():
    """A fresh idempotency key per test."""
    return f"test-{uuid.uuid4().hex[:16]}"
