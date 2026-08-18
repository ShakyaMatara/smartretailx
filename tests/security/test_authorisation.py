"""Security tests: authorisation and data-protection controls."""
import uuid

import pytest
from conftest import CATALOGUE_URL, INVENTORY_URL, ORDER_URL, USER_URL

pytestmark = pytest.mark.security


def test_customer_cannot_list_all_users(client, customer_headers):
    """Authenticated but not authorised — 403, not 401."""
    response = client.get(f"{USER_URL}/api/v1/users", headers=customer_headers)
    assert response.status_code == 403


def test_admin_can_list_all_users(client, admin_headers):
    response = client.get(f"{USER_URL}/api/v1/users", headers=admin_headers)
    assert response.status_code == 200


def test_customer_cannot_create_a_product(client, customer_headers):
    """The role claim is enforced independently at each service, using
    the public key published by the user service."""
    response = client.post(
        f"{CATALOGUE_URL}/api/v1/products", headers=customer_headers,
        json={"name": "Unauthorised", "description": "Should be refused",
              "category": "test", "price": 1.00, "currency": "EUR", "sku": "UN-1"},
    )
    assert response.status_code == 403


def test_customer_cannot_alter_stock(client, customer_headers, seeded_product):
    response = client.put(
        f"{INVENTORY_URL}/api/v1/inventory/{seeded_product}",
        headers=customer_headers,
        json={"product_id": seeded_product, "available": 99999},
    )
    assert response.status_code == 403


def test_a_user_cannot_read_another_users_order(client, customer_headers,
                                                seeded_product, idem_key):
    """OWASP API1 — broken object level authorisation."""
    created = client.post(
        f"{ORDER_URL}/api/v1/orders",
        headers={**customer_headers, "Idempotency-Key": idem_key},
        json={"items": [{"product_id": seeded_product, "quantity": 1}]},
    )
    order_id = created.json()["id"]

    other_email = f"other-{uuid.uuid4().hex[:12]}@example.com"
    client.post(f"{USER_URL}/api/v1/users/register",
                json={"email": other_email, "full_name": "Other User",
                      "password": "OtherPassword2026"})
    other_token = client.post(f"{USER_URL}/api/v1/auth/login",
                              data={"username": other_email,
                                    "password": "OtherPassword2026"}).json()["access_token"]

    response = client.get(f"{ORDER_URL}/api/v1/orders/{order_id}",
                          headers={"Authorization": f"Bearer {other_token}"})
    assert response.status_code == 403


def test_a_user_sees_only_their_own_orders(client, customer_headers,
                                           customer_credentials):
    response = client.get(f"{ORDER_URL}/api/v1/orders", headers=customer_headers)
    assert response.status_code == 200
    assert all(o["user_id"] == customer_credentials["id"] for o in response.json())


def test_right_to_erasure_anonymises_the_account(client):
    """GDPR Article 17. Personal data is irreversibly anonymised while
    referential integrity with historical orders is preserved."""
    email = f"erase-{uuid.uuid4().hex[:12]}@example.com"
    password = "ErasurePassword2026"
    client.post(f"{USER_URL}/api/v1/users/register",
                json={"email": email, "full_name": "To Be Erased", "password": password})
    token = client.post(f"{USER_URL}/api/v1/auth/login",
                        data={"username": email, "password": password}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert client.delete(f"{USER_URL}/api/v1/users/me", headers=headers).status_code == 204

    # The token is now useless: the account is deactivated.
    assert client.get(f"{USER_URL}/api/v1/users/me", headers=headers).status_code == 401

    # The original credentials no longer authenticate.
    assert client.post(f"{USER_URL}/api/v1/auth/login",
                       data={"username": email, "password": password}).status_code == 401


def test_erased_user_no_longer_appears_under_their_email(client, admin_headers):
    email = f"erase2-{uuid.uuid4().hex[:12]}@example.com"
    password = "ErasurePassword2026"
    client.post(f"{USER_URL}/api/v1/users/register",
                json={"email": email, "full_name": "To Be Erased", "password": password})
    token = client.post(f"{USER_URL}/api/v1/auth/login",
                        data={"username": email, "password": password}).json()["access_token"]
    client.delete(f"{USER_URL}/api/v1/users/me",
                  headers={"Authorization": f"Bearer {token}"})

    listed = client.get(f"{USER_URL}/api/v1/users", headers=admin_headers,
                        params={"limit": 100}).json()
    assert not any(u["email"] == email for u in listed)
