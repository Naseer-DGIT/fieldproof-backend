"""Two-phase database password rotation.

Phase 1 (--prepare): generate a new password and write it to Secrets
Manager under `database_password_next`. Does not touch the database.

Phase 2 (--commit): update the Postgres role with the new password,
then promote `database_password_next` to `database_password`.

Between phase 1 and phase 2, rolling-restart the app so every instance
is running with the new password. In a single-instance deployment
(dev), phase 2 causes a brief disconnect.

Usage:

    python scripts/rotate_db_password.py --environment staging --prepare
    # restart the app
    python scripts/rotate_db_password.py --environment staging --commit
"""

import argparse
import json
import os
import secrets
import sys

import boto3
import psycopg
from botocore.exceptions import ClientError
from psycopg import sql

DB_ROLE = "postgres"


def _client():
    return boto3.client(
        "secretsmanager",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        endpoint_url=os.getenv("AWS_ENDPOINT_URL"),
    )


def _secret_name(environment: str) -> str:
    return f"fieldproof/{environment}/app"


def _read_secret(client, name: str) -> dict:
    try:
        response = client.get_secret_value(SecretId=name)
    except ClientError as exc:
        raise RuntimeError(f"cannot read {name}: {exc}") from exc

    body = response.get("SecretString")
    if not body:
        raise RuntimeError(f"{name} has no SecretString")
    return json.loads(body)


def _write_secret(client, name: str, data: dict) -> None:
    client.put_secret_value(SecretId=name, SecretString=json.dumps(data))


def _new_password() -> str:
    return secrets.token_urlsafe(32)


def prepare(environment: str) -> int:
    """Phase 1: generate a new password, stage it in Secrets Manager."""
    client = _client()
    name = _secret_name(environment)

    data = _read_secret(client, name)
    new_password = _new_password()
    data["database_password_next"] = new_password
    _write_secret(client, name, data)

    print(f"staged: {name}.database_password_next")
    print("next: restart the app, then run --commit")
    return 0


def commit(environment: str) -> int:
    """Phase 2: update the DB role, then promote the password."""
    client = _client()
    name = _secret_name(environment)

    data = _read_secret(client, name)
    if "database_password_next" not in data:
        print("error: no database_password_next in the secret", file=sys.stderr)
        print("run --prepare first", file=sys.stderr)
        return 1

    new_password = data["database_password_next"]

    # Connect with the *current* password to run ALTER ROLE.
    current_password = data["database_password"]
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    dbname = os.getenv("DB_NAME", "fieldproof")

    conn_str = (
        f"host={host} port={port} dbname={dbname} "
        f"user={DB_ROLE} password={current_password}"
    )

    try:
        with psycopg.connect(conn_str, autocommit=True) as conn:
            with conn.cursor() as cur:
                # Postgres rejects `ALTER ROLE ... PASSWORD $1` because
                # utility statements do not go through the extended query
                # protocol. Compose the statement client-side with
                # psycopg.sql: Identifier quotes the role name, Literal
                # quotes and escapes the password.
                cur.execute(
                    sql.SQL("ALTER ROLE {} WITH PASSWORD {}").format(
                        sql.Identifier(DB_ROLE),
                        sql.Literal(new_password),
                    )
                )
    except psycopg.Error as exc:
        print(f"error: could not update DB role: {exc}", file=sys.stderr)
        return 1

    print(f"DB role {DB_ROLE} updated")

    data["database_password"] = new_password
    del data["database_password_next"]
    _write_secret(client, name, data)
    print(f"promoted: {name}.database_password")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", required=True,
                        choices=["staging", "prod"])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    if args.prepare:
        return prepare(args.environment)
    return commit(args.environment)


if __name__ == "__main__":
    raise SystemExit(main())
