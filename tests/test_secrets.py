"""Secrets loader tests.

Two backends:

1. env — dev and lab read from environment variables
2. secrets_manager — staging and prod read from AWS Secrets Manager

The secrets_manager tests mock boto3. They prove the loader parses the
JSON correctly and surfaces clear errors. They do not test the AWS SDK
itself; that is the SDK's own test suite.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import secrets as secrets_mod  # noqa: E402


@pytest.fixture(autouse=True)
def clear_cache():
    secrets_mod.load_secrets.cache_clear()
    yield
    secrets_mod.load_secrets.cache_clear()


# --- env backend ---

def test_env_backend_reads_from_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "from-env-jwt")
    monkeypatch.setenv("DATABASE_PASSWORD", "from-env-db")
    s = secrets_mod.load_secrets("dev")
    assert s.jwt_secret == "from-env-jwt"
    assert s.database_password == "from-env-db"


def test_env_backend_falls_back_in_dev(monkeypatch):
    """Dev without JWT_SECRET gets the well-known default. Staging
    and prod never reach this path (they use Secrets Manager)."""
    monkeypatch.delenv("JWT_SECRET", raising=False)
    s = secrets_mod.load_secrets("dev")
    assert s.jwt_secret.startswith("dev-only")


def test_lab_uses_env_backend(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "from-env-jwt")
    monkeypatch.setenv("DATABASE_PASSWORD", "from-env-db")
    s = secrets_mod.load_secrets("lab")
    assert s.jwt_secret == "from-env-jwt"


# --- unknown environment ---

def test_unknown_environment_raises():
    with pytest.raises(ValueError, match="Unknown environment"):
        secrets_mod.load_secrets("banana")


# --- secrets manager backend (mocked boto3) ---

def _mock_client_returning(body: dict):
    client = MagicMock()
    client.get_secret_value.return_value = {
        "SecretString": json.dumps(body),
    }
    return client


def test_secrets_manager_parses_json():
    body = {"jwt_secret": "s-jwt", "database_password": "s-db"}
    client = _mock_client_returning(body)
    with patch("app.core.secrets.boto3.client", return_value=client):
        s = secrets_mod.load_secrets("staging")
    assert s.jwt_secret == "s-jwt"
    assert s.database_password == "s-db"


def test_secrets_manager_prod_uses_same_path():
    body = {"jwt_secret": "p-jwt", "database_password": "p-db"}
    client = _mock_client_returning(body)
    with patch("app.core.secrets.boto3.client", return_value=client):
        s = secrets_mod.load_secrets("prod")
    assert s.jwt_secret == "p-jwt"


def test_missing_secret_raises_clear_error():
    client = MagicMock()
    client.get_secret_value.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "not found"}},
        "GetSecretValue",
    )
    with patch("app.core.secrets.boto3.client", return_value=client):
        with pytest.raises(RuntimeError, match="Failed to load secret"):
            secrets_mod.load_secrets("staging")


def test_invalid_json_raises_clear_error():
    client = MagicMock()
    client.get_secret_value.return_value = {"SecretString": "not json"}
    with patch("app.core.secrets.boto3.client", return_value=client):
        with pytest.raises(RuntimeError, match="not valid JSON"):
            secrets_mod.load_secrets("staging")


def test_missing_field_raises_clear_error():
    client = MagicMock()
    client.get_secret_value.return_value = {
        "SecretString": json.dumps({"jwt_secret": "only-jwt"})
    }
    with patch("app.core.secrets.boto3.client", return_value=client):
        with pytest.raises(RuntimeError, match="missing field"):
            secrets_mod.load_secrets("staging")
