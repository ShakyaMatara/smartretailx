from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "notification-service"
    aws_endpoint_url: str = "http://localstack:4566"
    aws_default_region: str = "eu-west-1"
    queue_name: str = "notification-service-queue"


settings = Settings()