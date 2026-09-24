"""Secret loading.

Dev and lab read from environment variables (loaded from .env files).
Staging and prod read from AWS Secrets Manager.

One JSON secret per environment holds the fields the app needs:

    {
      "jwt_secret": "...",
      "database_password": "..."
    }

The secret name follows the convention:

    fieldproof/{environment}/app

LocalStack is used for local testing. Point AWS_ENDPOINT_URL at
http://localhost:4566 and the same code path runs against it.
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


def _secret_name(environment: str) -> str:
    return f"fieldproof/{environment}/app"


def _from_env(environment: str) -> AppSecrets:
    """Read secrets from environment variables.

    Dev and lab get known defaults so tests and local runs work without
    any setup. That is safe because those environments are not connected
    to real data. Staging and prod never reach this function — they use
    Secrets Manager.
    """
    jwt = os.getenv("JWT_SECRET")
    if not jwt:
        if environment in ("dev", "lab"):
            jwt = "dev-only-change-in-prod-and-load-from-kms"
        else:
            raise RuntimeError("JWT_SECRET is not set")

    db_pw = os.getenv("DATABASE_PASSWORD")
    if not db_pw:
        if environment in ("dev", "lab"):
            db_pw = "devsecret"
        else:
            raise RuntimeError("DATABASE_PASSWORD is not set")

    return AppSecrets(jwt_secret=jwt, database_password=db_pw)


def _from_secrets_manager(environment: str) -> AppSecrets:
    region = os.getenv("AWS_REGION", "us-east-1")
    endpoint = os.getenv("AWS_ENDPOINT_URL")  # LocalStack sets this

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

    try:
        return AppSecrets(
            jwt_secret=data["jwt_secret"],
            database_password=data["database_password"],
        )
    except KeyError as exc:
        raise RuntimeError(
            f"Secret {_secret_name(environment)!r} is missing field {exc}"
        ) from exc


@lru_cache(maxsize=8)
def load_secrets(environment: str) -> AppSecrets:
    """Load secrets for the given environment.

    Cached per process. Restart the process to pick up a rotated secret.
    Rotation without restart is a later concern (S14).
    """
    if environment in ("dev", "lab"):
        return _from_env(environment)
    if environment in ("staging", "prod"):
        return _from_secrets_manager(environment)
    raise ValueError(f"Unknown environment: {environment}")
