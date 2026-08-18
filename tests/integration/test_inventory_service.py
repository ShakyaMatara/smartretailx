"""Integration tests: inventory service stock handling."""
import pytest
from conftest import INVENTORY_URL

pytestmark = pytest.mark.integration


def test_stock_level_can_be_set_and_read(client, admin_headers, seeded_product):
    response = client.get(f"{INVENTORY_URL}/api/v1/inventory/{seeded_product}")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] >= 0
    assert body["reserved"] >= 0


def test_unstocked_product_returns_404(client):
    response = client.get(
        f"{INVENTORY_URL}/api/v1/inventory/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_negative_stock_is_rejected_by_validation(client, admin_headers, seeded_product):
    response = client.put(
        f"{INVENTORY_URL}/api/v1/inventory/{seeded_product}",
        headers=admin_headers,
        json={"product_id": seeded_product, "available": -10},
    )
    assert response.status_code == 422
