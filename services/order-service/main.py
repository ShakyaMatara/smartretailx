import uuid
from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from auth import get_claims
from catalogue_client import fetch_product
from config import settings
from consumer import start_consumer
from database import get_db, init_db
from models import Order, OrderItem
from schemas import OrderCreateRequest, OrderResponse
from shared.events import ORDER_CREATED, publish
from shared.logging_config import configure_logging, correlation_id_var

logger = configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_consumer()
    yield


app = FastAPI(
    title="SmartRetailX Order Service",
    description="Order placement and saga orchestration.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """
    Accept a correlation id from the caller or generate one, then make
    it available to every log call in this request and return it to the
    client. This is what allows one business transaction to be traced
    across every service it touches.
    """
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    correlation_id_var.set(correlation_id)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


@app.get("/health/live", tags=["Health"])
def liveness():
    return {"status": "alive", "service": "order-service"}


@app.get("/health/ready", tags=["Health"])
def readiness(db: Session = Depends(get_db)):
    from sqlalchemy import text
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ready", "service": "order-service"}


@app.post(
    "/api/v1/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Orders"],
)
def create_order(
    payload: OrderCreateRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    claims: dict = Depends(get_claims),
    db: Session = Depends(get_db),
):
    """
    Place an order. Starts the saga.

    Requires an Idempotency-Key header. Resubmitting the same key
    returns the original order rather than creating a duplicate,
    which prevents double charging on a retried request.
    """
    existing = db.query(Order).filter(
        Order.idempotency_key == idempotency_key
    ).first()
    if existing is not None:
        logger.info(f"Idempotent replay for key {idempotency_key}")
        return existing

    order = Order(
        user_id=claims["sub"],
        idempotency_key=idempotency_key,
        total_amount=Decimal("0.00"),
    )

    total = Decimal("0.00")

    for line in payload.items:
        product = fetch_product(line.product_id)
        if product is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {line.product_id} not found.",
            )

        unit_price = Decimal(str(product["price"]))
        total += unit_price * line.quantity

        order.items.append(OrderItem(
            product_id=line.product_id,
            product_name=product["name"],
            quantity=line.quantity,
            unit_price=unit_price,
        ))

    order.total_amount = total
    db.add(order)
    db.commit()
    db.refresh(order)

    logger.info(f"Order {order.id} created, starting saga")

    publish(ORDER_CREATED, {
        "order_id": order.id,
        "user_id": order.user_id,
        "total_amount": str(order.total_amount),
        "items": [
            {"product_id": i.product_id, "quantity": i.quantity}
            for i in order.items
        ],
    }, correlation_id_var.get())

    return order


@app.get("/api/v1/orders/{order_id}", response_model=OrderResponse, tags=["Orders"])
def get_order(
    order_id: str,
    claims: dict = Depends(get_claims),
    db: Session = Depends(get_db),
):
    """Retrieve an order. Users see only their own; admins see any."""
    order = db.query(Order).filter(Order.id == order_id).first()

    if order is None:
        raise HTTPException(status_code=404, detail="Order not found.")

    # Object-level authorisation. Without this check any authenticated
    # user could read any order by guessing its id - OWASP API1,
    # Broken Object Level Authorisation.
    if order.user_id != claims["sub"] and claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your order.")

    return order


@app.get("/api/v1/orders", response_model=list[OrderResponse], tags=["Orders"])
def list_my_orders(
    claims: dict = Depends(get_claims),
    db: Session = Depends(get_db),
    limit: int = 25,
):
    """List the authenticated user's own orders."""
    return (
        db.query(Order)
        .filter(Order.user_id == claims["sub"])
        .order_by(Order.created_at.desc())
        .limit(limit)
        .all()
    )