"""End-to-end tests: the full order journey across five services."""
import time
import uuid

import pytest
from conftest import CATALOGUE_URL, INVENTORY_URL, ORDER_URL, PAYMENT_URL

pytestmark = pytest.mark.e2e

SAGA_TIMEOUT = 25


@pytest.fixture
def make_product(client, admin_headers):
    """Factory fixture to spin up dedicated products with custom stock levels."""
    def _create(available=100, price=10.00):
        product_id = client.post(
            f"{CATALOGUE_URL}/api/v1/products",
            headers=admin_headers,
            json={
                "name": "Fixture Widget",
                "description": "Single-test fixture",
                "category": "test-fixtures",
                "price": price,
                "currency": "EUR",
                "sku": f"FW-{uuid.uuid4().hex[:8]}",
            },
        ).json()["product_id"]

        client.put(
            f"{INVENTORY_URL}/api/v1/inventory/{product_id}",
            headers=admin_headers,
            json={
                "product_id": product_id,
                "available": available,
            },
        )
        return product_id

    return _create


@pytest.fixture
def exclusive_product(make_product):
    """Default exclusive product with 100 available stock."""
    return make_product(available=100)


def _await_status(client, headers, order_id, target, timeout=SAGA_TIMEOUT):
    """Poll until the saga reaches the expected terminal state.

    Polling is necessary because the API responds before the saga
    completes: order state advances through asynchronous events.
    """
    deadline = time.time() + timeout
    last = None

    while time.time() < deadline:
        response = client.get(
            f"{ORDER_URL}/api/v1/orders/{order_id}",
            headers=headers,
        )
        last = response.json()["status"]

        if last == target:
            return last

        time.sleep(0.5)

    pytest.fail(
        f"order {order_id} reached {last}, "
        f"expected {target} within {timeout}s"
    )


def test_full_purchase_journey(
    client,
    customer_headers,
    exclusive_product,
    idem_key,
):
    """Register, browse, order, reserve stock, pay, confirm."""
    product = client.get(
        f"{CATALOGUE_URL}/api/v1/products/{exclusive_product}"
    )
    assert product.status_code == 200
    unit_price = float(product.json()["price"])

    before = client.get(
        f"{INVENTORY_URL}/api/v1/inventory/{exclusive_product}"
    ).json()

    created = client.post(
        f"{ORDER_URL}/api/v1/orders",
        headers={**customer_headers, "Idempotency-Key": idem_key},
        json={
            "items": [
                {
                    "product_id": exclusive_product,
                    "quantity": 2,
                }
            ]
        },
    )
    assert created.status_code == 201

    order = created.json()
    order_id = order["id"]

    # The order is accepted before the saga runs.
    assert order["status"] == "PENDING"
    assert float(order["total_amount"]) == pytest.approx(unit_price * 2)

    # Price is captured at order time, not read back from the catalogue.
    assert float(order["items"][0]["unit_price"]) == pytest.approx(unit_price)

    assert (
        _await_status(
            client,
            customer_headers,
            order_id,
            "CONFIRMED",
        )
        == "CONFIRMED"
    )

    after = client.get(
        f"{INVENTORY_URL}/api/v1/inventory/{exclusive_product}"
    ).json()

    assert after["available"] == before["available"] - 2
    assert after["reserved"] == before["reserved"] + 2

    payment = client.get(
        f"{PAYMENT_URL}/api/v1/payments/order/{order_id}",
        headers=customer_headers,
    )
    assert payment.status_code == 200
    assert payment.json()["status"] == "SUCCEEDED"


def test_payment_record_holds_no_card_data(
    client,
    customer_headers,
    exclusive_product,
    idem_key,
):
    """PCI-DSS: only an opaque gateway token and the last four digits."""
    created = client.post(
        f"{ORDER_URL}/api/v1/orders",
        headers={**customer_headers, "Idempotency-Key": idem_key},
        json={
            "items": [
                {
                    "product_id": exclusive_product,
                    "quantity": 1,
                }
            ]
        },
    )

    assert created.status_code == 201
    order_id = created.json()["id"]

    _await_status(
        client,
        customer_headers,
        order_id,
        "CONFIRMED",
    )

    body = client.get(
        f"{PAYMENT_URL}/api/v1/payments/order/{order_id}",
        headers=customer_headers,
    ).json()

    assert len(body["card_last_four"]) == 4

    for forbidden in (
        "card_number",
        "pan",
        "cvv",
        "expiry",
        "gateway_token",
    ):
        assert forbidden not in body


def test_insufficient_stock_cancels_the_order(
    client,
    customer_headers,
    make_product,
    idem_key,
):
    """The saga fails at the first step, so there is nothing to compensate."""
    product = make_product(available=1, price=5.00)

    created = client.post(
        f"{ORDER_URL}/api/v1/orders",
        headers={**customer_headers, "Idempotency-Key": idem_key},
        json={
            "items": [
                {
                    "product_id": product,
                    "quantity": 99,
                }
            ]
        },
    )

    assert created.status_code == 201
    order_id = created.json()["id"]

    _await_status(
        client,
        customer_headers,
        order_id,
        "CANCELLED",
    )

    final = client.get(
        f"{ORDER_URL}/api/v1/orders/{order_id}",
        headers=customer_headers,
    ).json()

    assert "stock" in final["failure_reason"].lower()

    stock = client.get(
        f"{INVENTORY_URL}/api/v1/inventory/{product}"
    ).json()

    assert stock["available"] == 1, "no stock should have been consumed"


def test_idempotent_replay_returns_the_original_order(
    client,
    customer_headers,
    exclusive_product,
    idem_key,
):
    """A client retry after a timeout must not place a second order."""
    body = {
        "items": [
            {
                "product_id": exclusive_product,
                "quantity": 1,
            }
        ]
    }

    headers = {
        **customer_headers,
        "Idempotency-Key": idem_key,
    }

    first = client.post(
        f"{ORDER_URL}/api/v1/orders",
        headers=headers,
        json=body,
    )

    assert first.status_code == 201
    order_id = first.json()["id"]

    _await_status(
        client,
        customer_headers,
        order_id,
        "CONFIRMED",
    )

    before = client.get(
        f"{INVENTORY_URL}/api/v1/inventory/{exclusive_product}"
    ).json()

    replay = client.post(
        f"{ORDER_URL}/api/v1/orders",
        headers=headers,
        json=body,
    )

    assert replay.status_code == 201
    assert replay.json()["id"] == order_id

    after = client.get(
        f"{INVENTORY_URL}/api/v1/inventory/{exclusive_product}"
    ).json()

    assert after["available"] == before["available"], (
        "replay must not reserve stock again"
    )


def test_order_for_a_missing_product_is_rejected(
    client,
    customer_headers,
    idem_key,
):
    response = client.post(
        f"{ORDER_URL}/api/v1/orders",
        headers={**customer_headers, "Idempotency-Key": idem_key},
        json={
            "items": [
                {
                    "product_id": str(uuid.uuid4()),
                    "quantity": 1,
                }
            ]
        },
    )

    assert response.status_code == 404