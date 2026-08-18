from contextlib import asynccontextmanager
from decimal import Decimal

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from auth import require_roles
from consumer import start_consumer
from db import init_table, inventory_table
from shared.logging_config import configure_logging

logger = configure_logging()


class StockUpsert(BaseModel):
    product_id: str
    available: int = Field(ge=0)


class StockResponse(BaseModel):
    product_id: str
    available: int
    reserved: int


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_table()
    start_consumer()
    yield


app = FastAPI(
    title="SmartRetailX Inventory Service",
    description="Stock levels, reservation and release.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health/live", tags=["Health"])
def liveness():
    return {"status": "alive", "service": "inventory-service"}


@app.get("/health/ready", tags=["Health"])
def readiness():
    try:
        inventory_table().table_status
    except Exception:
        raise HTTPException(status_code=503, detail="datastore unavailable")
    return {"status": "ready", "service": "inventory-service"}


@app.put("/api/v1/inventory/{product_id}", response_model=StockResponse,
         tags=["Inventory"])
def set_stock(
    product_id: str,
    payload: StockUpsert,
    claims: dict = Depends(require_roles("admin", "warehouse")),
):
    """Set the stock level for a product. Admin or warehouse staff only."""
    item = {
        "product_id": product_id,
        "available": Decimal(str(payload.available)),
        "reserved": Decimal("0"),
    }
    inventory_table().put_item(Item=item)
    return {"product_id": product_id, "available": payload.available, "reserved": 0}


@app.get("/api/v1/inventory/{product_id}", response_model=StockResponse,
         tags=["Inventory"])
def get_stock(product_id: str):
    """Public stock check."""
    result = inventory_table().get_item(Key={"product_id": product_id})
    item = result.get("Item")

    if item is None:
        raise HTTPException(status_code=404, detail="Product not stocked.")

    return {
        "product_id": item["product_id"],
        "available": int(item["available"]),
        "reserved": int(item["reserved"]),
    }
