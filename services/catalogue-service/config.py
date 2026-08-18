from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "catalogue-service"

    aws_endpoint_url: str = "http://localstack:4566"
    aws_default_region: str = "eu-west-1"
    products_table: str = "products"

    jwks_url: str = "http://user-service:8000/.well-known/jwks.json"
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "smartretailx-user-service"
    jwt_audience: str = "smartretailx-api"


settings = Settings()