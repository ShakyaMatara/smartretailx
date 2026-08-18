"""API contract tests: status codes, versioning and error shape."""
import uuid

import pytest
from conftest import CATALOGUE_URL, ORDER_URL, USER_URL

pytestmark = pytest.mark.api


def test_all_routes_are_version_prefixed(client):
    """Versioning allows the API to evolve without breaking clients."""
    spec = client.get(f"{USER_URL}/openapi.json").json()
    business_paths = [p for p in spec["paths"]
                      if not p.startswith(("/health", "/.well-known"))]
    assert business_paths
    assert all(p.startswith("/api/v1/") for p in business_paths), business_paths


def test_creation_returns_201(client):
    response = client.post(
        f"{USER_URL}/api/v1/users/register",
        json={"email": f"api-{uuid.uuid4().hex[:12]}@example.com",
              "full_name": "API Test", "password": "ValidPassword2026"},
    )
    assert response.status_code == 201


def test_conflict_returns_409_not_400(client):
    """A duplicate resource is a conflict, not a malformed request."""
    email = f"api-{uuid.uuid4().hex[:12]}@example.com"
    payload = {"email": email, "full_name": "API Test", "password": "ValidPassword2026"}
    client.post(f"{USER_URL}/api/v1/users/register", json=payload)
    assert client.post(f"{USER_URL}/api/v1/users/register",
                       json=payload).status_code == 409


def test_validation_failure_returns_422_with_a_field_reference(client):
    response = client.post(
        f"{USER_URL}/api/v1/users/register",
        json={"email": "a@example.com", "full_name": "X", "password": "tooshort"},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any("password" in str(item.get("loc", "")) for item in detail)


def test_missing_resource_returns_404(client):
    response = client.get(
        f"{CATALOGUE_URL}/api/v1/products/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert "detail" in response.json()


def test_error_envelope_is_consistent_across_services(client, customer_headers):
    """Clients should not need per-service error handling."""
    responses = [
        client.get(f"{CATALOGUE_URL}/api/v1/products/{uuid.uuid4()}"),
        client.get(f"{ORDER_URL}/api/v1/orders/{uuid.uuid4()}", headers=customer_headers),
    ]
    for r in responses:
        assert r.status_code in (403, 404)
        assert isinstance(r.json().get("detail"), str)


def test_list_endpoint_is_paginated(client):
    """An unbounded list endpoint is a denial-of-service vector."""
    response = client.get(f"{CATALOGUE_URL}/api/v1/products", params={"limit": 2})
    assert response.status_code == 200
    assert len(response.json()) <= 2


def test_limit_above_the_maximum_is_rejected(client):
    response = client.get(f"{CATALOGUE_URL}/api/v1/products", params={"limit": 5000})
    assert response.status_code == 422


def test_order_creation_requires_an_idempotency_key(client, customer_headers,
                                                    seeded_product):
    response = client.post(
        f"{ORDER_URL}/api/v1/orders", headers=customer_headers,
        json={"items": [{"product_id": seeded_product, "quantity": 1}]},
    )
    assert response.status_code == 422


def test_correlation_id_is_returned_to_the_caller(client, customer_headers,
                                                  seeded_product, idem_key):
    """The caller can quote this identifier when reporting a problem."""
    response = client.post(
        f"{ORDER_URL}/api/v1/orders",
        headers={**customer_headers, "Idempotency-Key": idem_key},
        json={"items": [{"product_id": seeded_product, "quantity": 1}]},
    )
    assert response.status_code == 201
    assert response.headers.get("x-correlation-id")


def test_supplied_correlation_id_is_propagated(client, customer_headers,
                                               seeded_product, idem_key):
    supplied = str(uuid.uuid4())
    response = client.post(
        f"{ORDER_URL}/api/v1/orders",
        headers={**customer_headers, "Idempotency-Key": idem_key,
                 "X-Correlation-ID": supplied},
        json={"items": [{"product_id": seeded_product, "quantity": 1}]},
    )
    assert response.headers.get("x-correlation-id") == supplied
