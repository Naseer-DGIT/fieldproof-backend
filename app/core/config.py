import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    cors_origins: list[str]
    jwt_secret: str
    force_https: bool = False
    hsts_enabled: bool = False
    hsts_max_age: int = 31536000  # 1 year

    @property
    def is_prod(self) -> bool:
        return self.environment == "prod"

    @property
    def is_lab(self) -> bool:
        return self.environment == "lab"


def _load() -> Settings:
    env = os.getenv("ENVIRONMENT", "dev")
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:devsecret@localhost:5432/fieldproof",
    )
    origins = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://10.0.2.2:8000",
    ).split(",")
    jwt_secret = os.getenv("JWT_SECRET", "dev-only-change-in-prod-and-load-from-kms")

    # TLS enforcement. Enabled in staging and prod only.
    # Dev and lab stay on plain HTTP so tests and local tooling work.
    tls_enforced = env in ("staging", "prod")

    return Settings(
        environment=env,
        database_url=db_url,
        cors_origins=origins,
        jwt_secret=jwt_secret,
        force_https=tls_enforced,
        hsts_enabled=tls_enforced,
    )


settings = _load()
