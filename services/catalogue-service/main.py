import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal

from boto3.dynamodb.conditions import Key
from fastapi import Depends, FastAPI, HTTPException, Query, status

from auth import get_claims, require_roles
from db import init_table, products_table
from schemas import ProductCreate, ProductPriceUpdate, ProductResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_table()
    yield


app = FastAPI(
    title="SmartRetailX Product Catalogue Service",
    description="Manages the product catalogue, backed by Amazon DynamoDB.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health/live", tags=["Health"])
def liveness():
    return {"status": "alive", "service": "catalogue-service"}


@app.get("/health/ready", tags=["Health"])
def readiness():
    """Ready only if the DynamoDB table is reachable."""
    try:
        products_table().table_status
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="datastore unavailable",
        )
    return {"status": "ready", "service": "catalogue-service"}


@app.post(
    "/api/v1/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Products"],
)
def create_product(
    payload: ProductCreate,
    claims: dict = Depends(require_roles("admin")),
):
    """Add a product to the catalogue. Administrators only."""
    item = {
        "product_id": str(uuid.uuid4()),
        "name": payload.name,
        "description": payload.description,
        "category": payload.category,
        # DynamoDB stores decimals natively; float would lose precision
        # on monetary values.
        "price": Decimal(str(payload.price)),
        "currency": payload.currency.upper(),
        "sku": payload.sku,
        "is_active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    products_table().put_item(Item=item)
    return item


@app.get(
    "/api/v1/products/{product_id}",
    response_model=ProductResponse,
    tags=["Products"],
)
def get_product(product_id: str):
    """Retrieve a single product. Public - browsing needs no account."""
    result = products_table().get_item(Key={"product_id": product_id})
    item = result.get("Item")

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )
    return item


@app.get("/api/v1/products", response_model=list[ProductResponse], tags=["Products"])
def list_products(
    category: str | None = Query(default=None),
    limit: int = Query(default=25, le=100),
):
    """
    List products, optionally filtered by category.

    With a category this performs an indexed Query against the GSI.
    Without one it falls back to a Scan, which reads the whole table -
    acceptable for a catalogue of this size, but the reason production
    catalogues are always queried by an indexed access pattern.
    """
    table = products_table()

    if category:
        response = table.query(
            IndexName="category-index",
            KeyConditionExpression=Key("category").eq(category),
            Limit=limit,
        )
    else:
        response = table.scan(Limit=limit)

    return response.get("Items", [])


@app.put(
    "/api/v1/products/{product_id}/price",
    response_model=ProductResponse,
    tags=["Products"],
)
def update_price(
    product_id: str,
    payload: ProductPriceUpdate,
    claims: dict = Depends(require_roles("admin")),
):
    """Update a product price. Administrators only.
    Publishes a price-change event in a later iteration (Task 4)."""
    try:
        result = products_table().update_item(
            Key={"product_id": product_id},
            UpdateExpression="SET price = :p",
            ExpressionAttributeValues={":p": Decimal(str(payload.price))},
            # Fails rather than silently creating a new item if the
            # product does not exist.
            ConditionExpression="attribute_exists(product_id)",
            ReturnValues="ALL_NEW",
        )
    except products_table().meta.client.exceptions.ConditionalCheckFailedException:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )

    return result["Attributes"]


@app.delete(
    "/api/v1/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Products"],
)
def delete_product(
    product_id: str,
    claims: dict = Depends(require_roles("admin")),
):
    """Soft delete: marks the product inactive rather than removing it,
    preserving referential integrity with historical orders."""
    products_table().update_item(
        Key={"product_id": product_id},
        UpdateExpression="SET is_active = :f",
        ExpressionAttributeValues={":f": False},
    )
    return None