from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from auth import get_claims
from consumer import start_consumer
from database import get_db, init_db
from models import Payment
from shared.logging_config import configure_logging

logger = configure_logging()


class PaymentResponse(BaseModel):
    """Note the absence of any card number field."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    amount: Decimal
    currency: str
    status: str
    card_last_four: str
    created_at: datetime


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_consumer()
    yield


app = FastAPI(
    title="SmartRetailX Payment Service",
    description="Payment processing. PCI-DSS: no card data is stored.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health/live", tags=["Health"])
def liveness():
    return {"status": "alive", "service": "payment-service"}


@app.get("/health/ready", tags=["Health"])
def readiness(db: Session = Depends(get_db)):
    from sqlalchemy import text
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"status": "ready", "service": "payment-service"}


@app.get("/api/v1/payments/order/{order_id}", response_model=PaymentResponse,
         tags=["Payments"])
def get_payment_for_order(
    order_id: str,
    claims: dict = Depends(get_claims),
    db: Session = Depends(get_db),
):
    payment = db.query(Payment).filter(Payment.order_id == order_id).first()

    if payment is None:
        raise HTTPException(status_code=404, detail="No payment for this order.")

    if payment.user_id != claims["sub"] and claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Not your payment.")

    return payment
