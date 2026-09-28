"""Rotate the JWT secret in AWS Secrets Manager.

Runs against LocalStack or real AWS. Reads the existing secret, replaces
the `jwt_secret` field with a freshly generated value, writes it back.

Does not touch the database. Does not restart the app. Running
processes keep the old secret until restart.

Usage:

    python scripts/rotate_jwt_secret.py --environment staging
    python scripts/rotate_jwt_secret.py --environment staging --dry-run
"""

import argparse
import json
import os
import secrets
import sys

import boto3
from botocore.exceptions import ClientError


def _client():
    return boto3.client(
        "secretsmanager",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
        endpoint_url=os.getenv("AWS_ENDPOINT_URL"),
    )


def _secret_name(environment: str) -> str:
    return f"fieldproof/{environment}/app"


def _new_jwt_secret() -> str:
    """64 bytes of URL-safe randomness, 86 characters."""
    return secrets.token_urlsafe(64)


def rotate(environment: str, dry_run: bool) -> int:
    client = _client()
    name = _secret_name(environment)

    try:
        response = client.get_secret_value(SecretId=name)
    except ClientError as exc:
        print(f"error: cannot read {name}: {exc}", file=sys.stderr)
        return 1

    body = response.get("SecretString")
    if not body:
        print(f"error: {name} has no SecretString", file=sys.stderr)
        return 1

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        print(f"error: {name} is not valid JSON", file=sys.stderr)
        return 1

    if "jwt_secret" not in data:
        print(f"error: {name} has no jwt_secret field", file=sys.stderr)
        return 1

    new_secret = _new_jwt_secret()

    if dry_run:
        print(f"dry run: would rotate {name}")
        print(f"  old length: {len(data['jwt_secret'])}")
        print(f"  new length: {len(new_secret)}")
        return 0

    data["jwt_secret"] = new_secret
    client.put_secret_value(SecretId=name, SecretString=json.dumps(data))
    print(f"rotated: {name}")
    print("restart the app for the new secret to take effect")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", required=True,
                        choices=["staging", "prod"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return rotate(args.environment, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
