from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    service_name: str = "user-service"
    database_url: str = "postgresql+psycopg://smartretailx:changeme@user-db:5432/userdb"

    jwt_private_key_path: str = "/run/keys/jwt-private.pem"
    jwt_public_key_path: str = "/run/keys/jwt-public.pem"

    # RS256: asymmetric. Only this service holds the private key and can
    # issue tokens; every other service verifies using the public key.
    jwt_algorithm: str = "RS256"

    # Who issued the token. Verifiers check this claim, so a token from
    # some other system cannot be replayed against SmartRetailX.
    jwt_issuer: str = "smartretailx-user-service"

    # Who the token is intended for. Same reasoning, opposite direction.
    jwt_audience: str = "smartretailx-api"

    # Short-lived access token limits the damage window if one is stolen.
    access_token_expire_minutes: int = 15

    # Long-lived refresh token, used only to obtain new access tokens.
    refresh_token_expire_days: int = 7


settings = Settings()