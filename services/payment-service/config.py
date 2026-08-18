from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "payment-service"
    database_url: str = "postgresql+psycopg://smartretailx:changeme@payment-db:5432/paymentdb"

    jwks_url: str = "http://user-service:8000/.well-known/jwks.json"
    jwt_algorithm: str = "RS256"
    jwt_issuer: str = "smartretailx-user-service"
    jwt_audience: str = "smartretailx-api"

    queue_name: str = "payment-service-queue"

    # Test switch: when true every payment is declined, so the saga's
    # compensating transaction can be demonstrated on demand.
    force_payment_failure: bool = False


settings = Settings()
