"""Integration tests: every service is reachable and reports readiness."""
import pytest
from conftest import (CATALOGUE_URL, INVENTORY_URL, NOTIFICATION_URL,
                      ORDER_URL, PAYMENT_URL, USER_URL)

pytestmark = pytest.mark.integration

SERVICES = [
    ("user-service", USER_URL),
    ("catalogue-service", CATALOGUE_URL),
    ("order-service", ORDER_URL),
    ("inventory-service", INVENTORY_URL),
    ("payment-service", PAYMENT_URL),
    ("notification-service", NOTIFICATION_URL),
]


@pytest.mark.parametrize("name,url", SERVICES)
def test_liveness_probe(client, name, url):
    response = client.get(f"{url}/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "alive"


@pytest.mark.parametrize("name,url", SERVICES)
def test_readiness_probe(client, name, url):
    """Readiness additionally proves the service can reach its datastore."""
    response = client.get(f"{url}/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


@pytest.mark.parametrize("name,url", SERVICES)
def test_openapi_specification_is_published(client, name, url):
    spec = client.get(f"{url}/openapi.json")
    assert spec.status_code == 200
    body = spec.json()
    assert body["openapi"].startswith("3.")
    assert body["info"]["title"]
