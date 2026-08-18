import httpx
import pybreaker
from tenacity import retry, stop_after_attempt, wait_exponential_jitter

from config import settings

# Circuit breaker: after 3 consecutive failures the breaker OPENS and
# subsequent calls fail immediately for 30 seconds instead of waiting
# on a timeout. This stops a slow dependency from exhausting this
# service's own resources and cascading the failure upstream.
catalogue_breaker = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=30,
    name="catalogue-service",
)


@catalogue_breaker
@retry(
    stop=stop_after_attempt(3),
    # Exponential backoff with jitter. Jitter matters: without it, all
    # retrying clients retry at the same instant and hammer a
    # recovering service back down (the thundering herd problem).
    wait=wait_exponential_jitter(initial=0.2, max=2.0),
    reraise=True,
)
def fetch_product(product_id: str) -> dict | None:
    """
    Fetch a product from the Catalogue Service.

    An explicit timeout is essential: an unbounded call is the classic
    cause of cascading failure, because request handlers pile up
    waiting on a dependency that will never answer.
    """
    with httpx.Client(timeout=3.0) as client:
        response = client.get(
            f"{settings.catalogue_url}/api/v1/products/{product_id}"
        )

    if response.status_code == 404:
        return None

    response.raise_for_status()
    return response.json()