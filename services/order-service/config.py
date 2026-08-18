from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "order-service"
    database_url: str = "postgresql+psycopg://smartretailx:changeme@order-db:5432/orderdb"

    catalogue_url: str = "http://catalogue-service:8000"

    jwks_url: str = "http://user-service:8000/.well-known/jwks.json"
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "smartretailx-user-service"
    jwt_audience: str = "smartretailx-api"

    queue_name: str = "order-service-queue"


settings = Settings()