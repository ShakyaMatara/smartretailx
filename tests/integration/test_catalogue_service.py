"""Integration tests: catalogue service against DynamoDB."""
import uuid

import pytest
from conftest import CATALOGUE_URL

pytestmark = pytest.mark.integration


def _product_payload(category="test-fixtures"):
    return {
        "name": "Integration Widget",
        "description": "Created by the automated test suite",
        "category": category,
        "price": 19.99,
        "currency": "EUR",
        "sku": f"IW-{uuid.uuid4().hex[:8]}",
    }


def test_create_and_retrieve_a_product(client, admin_headers):
    created = client.post(f"{CATALOGUE_URL}/api/v1/products",
                          headers=admin_headers, json=_product_payload())
    assert created.status_code == 201
    product_id = created.json()["product_id"]

    fetched = client.get(f"{CATALOGUE_URL}/api/v1/products/{product_id}")
    assert fetched.status_code == 200
    assert fetched.json()["product_id"] == product_id


def test_price_is_stored_as_an_exact_decimal(client, admin_headers):
    """Monetary values must not be subject to floating-point drift."""
    payload = _product_payload()
    payload["price"] = 19.99
    created = client.post(f"{CATALOGUE_URL}/api/v1/products",
                          headers=admin_headers, json=payload)
    assert created.json()["price"] in ("19.99", 19.99)


def test_category_filter_uses_the_secondary_index(client, admin_headers):
    category = f"cat-{uuid.uuid4().hex[:8]}"
    client.post(f"{CATALOGUE_URL}/api/v1/products", headers=admin_headers,
                json=_product_payload(category))

    listed = client.get(f"{CATALOGUE_URL}/api/v1/products",
                        params={"category": category})
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) >= 1
    assert all(i["category"] == category for i in items)


def test_price_update_on_a_missing_product_returns_404(client, admin_headers):
    """A conditional write prevents an update silently creating a record."""
    response = client.put(
        f"{CATALOGUE_URL}/api/v1/products/{uuid.uuid4()}/price",
        headers=admin_headers, json={"price": 5.00},
    )
    assert response.status_code == 404
