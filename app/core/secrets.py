"""Secret loading.

Dev and lab read from environment variables. Staging and prod read from
AWS Secrets Manager.

One JSON secret per environment:

    {
      "jwt_secret": "...",
      "database_password": "...",
      "backup_passphrase": "..."
    }

The secret name follows the convention:

    fieldproof/{environment}/app
"""

import json
import os
from dataclasses import dataclass
from functools import lru_cache

import boto3
from botocore.exceptions import BotoCoreError, ClientError


@dataclass(frozen=True)
class AppSecrets:
    jwt_secret: str
    database_password: str
    backup_passphrase: str


_DEV_JWT_DEFAULT = "dev-only-change-in-prod-and-load-from-kms"
_DEV_DB_DEFAULT = "devsecret"
_DEV_BACKUP_DEFAULT = "dev-backup-passphrase-change-me"


def _secret_name(environment: str) -> str:
    return f"fieldproof/{environment}/app"


def _from_env(environment: str) -> AppSecrets:
    """Read from environment variables.

    Dev and lab get known defaults so a fresh clone runs pytest with no
    setup. Staging and prod never reach this function.
    """
    jwt = os.getenv("JWT_SECRET") or (_DEV_JWT_DEFAULT if environment in ("dev", "lab") else None)
    if not jwt:
        raise RuntimeError("JWT_SECRET is not set")

    db_pw = os.getenv("DATABASE_PASSWORD") or (_DEV_DB_DEFAULT if environment in ("dev", "lab") else None)
    if not db_pw:
        raise RuntimeError("DATABASE_PASSWORD is not set")

    backup = os.getenv("BACKUP_PASSPHRASE") or (_DEV_BACKUP_DEFAULT if environment in ("dev", "lab") else None)
    if not backup:
        raise RuntimeError("BACKUP_PASSPHRASE is not set")

    return AppSecrets(
        jwt_secret=jwt,
        database_password=db_pw,
        backup_passphrase=backup,
    )


def _from_secrets_manager(environment: str) -> AppSecrets:
    region = os.getenv("AWS_REGION", "us-east-1")
    endpoint = os.getenv("AWS_ENDPOINT_URL")

    client = boto3.client(
        "secretsmanager",
        region_name=region,
        endpoint_url=endpoint,
    )

    try:
        response = client.get_secret_value(SecretId=_secret_name(environment))
    except (ClientError, BotoCoreError) as exc:
        raise RuntimeError(
            f"Failed to load secret {_secret_name(environment)!r}: {exc}"
        ) from exc

    body = response.get("SecretString")
    if not body:
        raise RuntimeError(f"Secret {_secret_name(environment)!r} has no SecretString")

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Secret {_secret_name(environment)!r} is not valid JSON"
        ) from exc

    for field in ("jwt_secret", "database_password", "backup_passphrase"):
        if field not in data:
            raise RuntimeError(
                f"Secret {_secret_name(environment)!r} is missing field {field!r}"
            )

    return AppSecrets(
        jwt_secret=data["jwt_secret"],
        database_password=data["database_password"],
        backup_passphrase=data["backup_passphrase"],
    )


@lru_cache(maxsize=8)
def load_secrets(environment: str) -> AppSecrets:
    if environment in ("dev", "lab"):
        return _from_env(environment)
    if environment in ("staging", "prod"):
        return _from_secrets_manager(environment)
    raise ValueError(f"Unknown environment: {environment}")
