"""Create the FieldProof secret in LocalStack.

Run once per LocalStack volume. Safe to run twice — puts a new value.
"""

import json
import os

import boto3
from botocore.exceptions import ClientError

REGION = os.getenv("AWS_REGION", "us-east-1")
ENDPOINT = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")

ENVIRONMENTS = {
    "staging": {
        "jwt_secret": "localstack-staging-jwt-secret-not-for-prod",
        "database_password": "staging-db-password",
    },
    "prod": {
        "jwt_secret": "localstack-prod-jwt-secret-not-for-prod",
        "database_password": "prod-db-password",
    },
}


def upsert(client, name: str, value: dict) -> None:
    body = json.dumps(value)
    try:
        client.create_secret(Name=name, SecretString=body)
        print(f"created: {name}")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ResourceExistsException":
            client.put_secret_value(SecretId=name, SecretString=body)
            print(f"updated: {name}")
        else:
            raise


def main() -> None:
    client = boto3.client("secretsmanager", region_name=REGION, endpoint_url=ENDPOINT)
    for env, payload in ENVIRONMENTS.items():
        upsert(client, f"fieldproof/{env}/app", payload)


if __name__ == "__main__":
    main()
