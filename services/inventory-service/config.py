from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "inventory-service"
    aws_endpoint_url: str = ""
    aws_default_region: str = "eu-west-1"
    inventory_table: str = "inventory"

    jwks_url: str = "http://user-service:8000/.well-known/jwks.json"
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "smartretailx-user-service"
    jwt_audience: str = "smartretailx-api"

    queue_name: str = "inventory-service-queue"


settings = Settings()
