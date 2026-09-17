import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    cors_origins: list[str]

    @property
    def is_prod(self) -> bool:
        return self.environment == "prod"


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
    return Settings(environment=env, database_url=db_url, cors_origins=origins)


settings = _load()
