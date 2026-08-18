from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OrderItemRequest(BaseModel):
    product_id: str
    quantity: int = Field(gt=0, le=100)


class OrderCreateRequest(BaseModel):
    items: list[OrderItemRequest] = Field(min_length=1, max_length=20)


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    product_name: str
    quantity: int
    unit_price: Decimal


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    status: str
    total_amount: Decimal
    currency: str
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse]