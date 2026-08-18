from decimal import Decimal

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=2000)
    category: str = Field(min_length=2, max_length=64)
    price: Decimal = Field(gt=0, decimal_places=2)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    sku: str = Field(min_length=3, max_length=64)


class ProductPriceUpdate(BaseModel):
    price: Decimal = Field(gt=0, decimal_places=2)


class ProductResponse(BaseModel):
    product_id: str
    name: str
    description: str
    category: str
    price: Decimal
    currency: str
    sku: str
    is_active: bool
    created_at: str