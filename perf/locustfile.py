"""Locust load-test definitions for SmartRetailX.

Four user classes, selected by name on the command line:

    BrowsingUser   read-heavy catalogue traffic (the realistic majority)
    OrderingUser   authenticated write path that triggers the saga
    MixedUser      weighted blend of both — the load-test profile
    HealthUser     health probes only, used for the baseline latency floor

All requests use absolute URLs so a single user class can span several
services without host confusion.
"""
import os
import random
import uuid

from locust import HttpUser, between, constant_throughput, events, task

USER_URL = os.getenv("USER_URL", "http://localhost:8001")
CATALOGUE_URL = os.getenv("CATALOGUE_URL", "http://localhost:8002")
ORDER_URL = os.getenv("ORDER_URL", "http://localhost:8003")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:8004")

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "shakya@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "CorrectHorseBattery")

# Populated once before the run starts and shared by every simulated user.
CATALOGUE = {"product_ids": [], "customer_token": None}


@events.test_start.add_listener
def seed_test_data(environment, **kwargs):
    """Create products with deep stock so the test measures service
    throughput rather than exhausting inventory partway through."""
    import requests

    login = requests.post(
        f"{USER_URL}/api/v1/auth/login",
        data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    login.raise_for_status()
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    CATALOGUE["product_ids"].clear()
    for i in range(10):
        product = requests.post(
            f"{CATALOGUE_URL}/api/v1/products",
            headers=headers,
            json={
                "name": f"Load Test Product {i}",
                "description": "Seeded for performance testing",
                "category": "load-test",
                "price": round(random.uniform(5, 200), 2),
                "currency": "EUR",
                "sku": f"LT-{uuid.uuid4().hex[:8]}",
            },
            timeout=10,
        )
        product_id = product.json()["product_id"]
        CATALOGUE["product_ids"].append(product_id)

        requests.put(
            f"{INVENTORY_URL}/api/v1/inventory/{product_id}",
            headers=headers,
            json={"product_id": product_id, "available": 1000000},
            timeout=10,
        )

    # A single pre-registered customer, shared by every simulated user in
    # the scaling scenario. Registering per user would spend the entire
    # load budget on Argon2id hashing in the User Service, moving the
    # bottleneck away from the component under test.
    shared_email = f"scale-{uuid.uuid4().hex[:12]}@example.com"
    shared_password = "ScaleTestPassword2026"
    requests.post(f"{USER_URL}/api/v1/users/register",
                  json={"email": shared_email, "full_name": "Scaling Test User",
                        "password": shared_password}, timeout=15)
    shared_login = requests.post(f"{USER_URL}/api/v1/auth/login",
                                 data={"username": shared_email,
                                       "password": shared_password}, timeout=15)
    CATALOGUE["customer_token"] = shared_login.json()["access_token"]

    print(f"[seed] {len(CATALOGUE['product_ids'])} products created with deep stock")
    print("[seed] shared customer token issued")


# ── shared request helpers ────────────────────────────────
# Defined once and called from several user classes, so the browsing
# behaviour measured in isolation is identical to the browsing portion
# of the mixed profile.

def _list_products(u):
    u.client.get(f"{CATALOGUE_URL}/api/v1/products?limit=25", name="GET /products")


def _filter_by_category(u):
    u.client.get(f"{CATALOGUE_URL}/api/v1/products?category=load-test&limit=25",
                 name="GET /products?category")


def _view_product(u):
    if not CATALOGUE["product_ids"]:
        return
    pid = random.choice(CATALOGUE["product_ids"])
    u.client.get(f"{CATALOGUE_URL}/api/v1/products/{pid}", name="GET /products/{id}")


def _check_stock(u):
    if not CATALOGUE["product_ids"]:
        return
    pid = random.choice(CATALOGUE["product_ids"])
    with u.client.get(f"{INVENTORY_URL}/api/v1/inventory/{pid}",
                      name="GET /inventory/{id}", catch_response=True) as response:
        if response.status_code in (200, 404):
            response.success()


def _authenticate(u):
    """Register and log in a distinct account, so token verification and
    per-user data paths are exercised realistically."""
    email = f"load-{uuid.uuid4().hex[:12]}@example.com"
    password = "LoadTestPassword2026"

    u.client.post(f"{USER_URL}/api/v1/users/register",
                  json={"email": email, "full_name": "Load Test User",
                        "password": password},
                  name="POST /users/register")

    login = u.client.post(f"{USER_URL}/api/v1/auth/login",
                          data={"username": email, "password": password},
                          name="POST /auth/login")
    u.token = login.json()["access_token"] if login.status_code == 200 else None


def _auth_header(u):
    return {"Authorization": f"Bearer {u.token}"}


def _place_order(u):
    if not getattr(u, "token", None) or not CATALOGUE["product_ids"]:
        return
    u.client.post(
        f"{ORDER_URL}/api/v1/orders",
        headers={**_auth_header(u),
                 "Idempotency-Key": f"load-{uuid.uuid4().hex[:16]}"},
        json={"items": [{"product_id": random.choice(CATALOGUE["product_ids"]),
                         "quantity": random.randint(1, 3)}]},
        name="POST /orders",
    )


def _list_my_orders(u):
    if not getattr(u, "token", None):
        return
    u.client.get(f"{ORDER_URL}/api/v1/orders", headers=_auth_header(u),
                 name="GET /orders")


def _read_own_profile(u):
    if not getattr(u, "token", None):
        return
    u.client.get(f"{USER_URL}/api/v1/users/me", headers=_auth_header(u),
                 name="GET /users/me")


# ── user classes ──────────────────────────────────────────

class BrowsingUser(HttpUser):
    """Anonymous catalogue browsing — the dominant retail traffic pattern.
    Read-only and served by the Catalogue Service against DynamoDB."""

    host = CATALOGUE_URL
    wait_time = between(0.5, 2.0)

    @task(5)
    def list_products(self):
        _list_products(self)

    @task(3)
    def filter_by_category(self):
        _filter_by_category(self)

    @task(4)
    def view_product(self):
        _view_product(self)

    @task(1)
    def check_stock(self):
        _check_stock(self)


class OrderingUser(HttpUser):
    """Authenticated customer placing orders.

    Each order triggers the saga: a synchronous catalogue lookup, then
    asynchronous stock reservation and payment. The response time
    measured here covers only the synchronous portion."""

    host = ORDER_URL
    wait_time = between(1.0, 3.0)

    def on_start(self):
        _authenticate(self)

    @task(4)
    def place_order(self):
        _place_order(self)

    @task(2)
    def list_my_orders(self):
        _list_my_orders(self)

    @task(1)
    def read_own_profile(self):
        _read_own_profile(self)


class MixedUser(HttpUser):
    """Realistic blend: mostly browsing, some ordering.

    Task weights approximate observed e-commerce traffic, where reads
    outnumber writes by roughly an order of magnitude. This is the
    profile used for the headline load and stress tests."""

    host = CATALOGUE_URL
    wait_time = between(0.5, 2.5)

    def on_start(self):
        _authenticate(self)

    # Browsing — weight 45 of 55
    @task(20)
    def list_products(self):
        _list_products(self)

    @task(12)
    def view_product(self):
        _view_product(self)

    @task(9)
    def filter_by_category(self):
        _filter_by_category(self)

    @task(4)
    def check_stock(self):
        _check_stock(self)

    # Ordering — weight 10 of 55
    @task(5)
    def place_order(self):
        _place_order(self)

    @task(3)
    def list_my_orders(self):
        _list_my_orders(self)

    @task(2)
    def read_own_profile(self):
        _read_own_profile(self)


class HealthUser(HttpUser):
    """Health probes only — establishes the latency floor, being framework
    and network overhead with no application work."""

    host = ORDER_URL
    wait_time = constant_throughput(1)

    @task
    def readiness(self):
        self.client.get(f"{ORDER_URL}/health/ready", name="GET /health/ready")


class ScalingUser(HttpUser):
    """Order-path load using a single shared, pre-issued token.

    Authentication is deliberately excluded: Argon2id hashing is
    memory-hard by design and would otherwise dominate the measurement,
    relocating the bottleneck to the User Service rather than the
    Order Service under test. Every request here exercises the
    synchronous order path — token verification, catalogue lookup,
    database write and event publication."""

    host = ORDER_URL
    wait_time = between(0.5, 1.5)

    def on_start(self):
        # No registration or login: the token is issued once at test start.
        self.token = CATALOGUE["customer_token"]

    @task(6)
    def place_order(self):
        _place_order(self)

    @task(3)
    def list_my_orders(self):
        _list_my_orders(self)

    @task(2)
    def view_product(self):
        _view_product(self)

    @task(1)
    def check_stock(self):
        _check_stock(self)
