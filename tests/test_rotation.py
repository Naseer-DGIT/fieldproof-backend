"""Rotation script tests.

The JWT rotation script is tested with a mocked boto3 client. The DB
rotation script is tested both with a mock (for the Secrets Manager
side) and against the local Postgres (for the ALTER ROLE side).

The local-DB test is skipped when the database is unreachable.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import psycopg
import pytest
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the scripts as modules
import importlib.util
from pathlib import Path


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


rotate_jwt = _load(
    "rotate_jwt",
    str(Path(__file__).parent.parent / "scripts" / "rotate_jwt_secret.py"),
)
rotate_db = _load(
    "rotate_db",
    str(Path(__file__).parent.parent / "scripts" / "rotate_db_password.py"),
)


def _mock_client(existing: dict):
    """Stateful mock: put_secret_value updates what get_secret_value
    returns next. Real Secrets Manager behaves this way; a stateless
    mock would make the two-phase test meaningless."""
    store = {"SecretString": json.dumps(existing)}

    client = MagicMock()

    def _get(SecretId=None):
        return dict(store)

    def _put(SecretId=None, SecretString=None):
        store["SecretString"] = SecretString

    client.get_secret_value.side_effect = _get
    client.put_secret_value.side_effect = _put
    client._store = store  # expose for assertions if needed
    return client


# --- JWT rotation ---

def test_jwt_rotation_replaces_secret():
    existing = {"jwt_secret": "old-jwt", "database_password": "db-pw"}
    client = _mock_client(existing)

    with patch.object(rotate_jwt, "_client", return_value=client):
        rc = rotate_jwt.rotate("staging", dry_run=False)

    assert rc == 0
    client.put_secret_value.assert_called_once()
    call = client.put_secret_value.call_args
    assert call.kwargs["SecretId"] == "fieldproof/staging/app"
    written = json.loads(call.kwargs["SecretString"])
    assert written["jwt_secret"] != "old-jwt"
    assert len(written["jwt_secret"]) >= 64
    assert written["database_password"] == "db-pw"  # untouched


def test_jwt_rotation_dry_run_does_not_write():
    existing = {"jwt_secret": "old-jwt"}
    client = _mock_client(existing)

    with patch.object(rotate_jwt, "_client", return_value=client):
        rc = rotate_jwt.rotate("staging", dry_run=True)

    assert rc == 0
    client.put_secret_value.assert_not_called()


def test_jwt_rotation_missing_secret_fails():
    client = MagicMock()
    client.get_secret_value.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "no"}},
        "GetSecretValue",
    )
    with patch.object(rotate_jwt, "_client", return_value=client):
        rc = rotate_jwt.rotate("staging", dry_run=False)
    assert rc == 1


def test_jwt_rotation_missing_field_fails():
    existing = {"database_password": "only-db"}  # no jwt_secret
    client = _mock_client(existing)

    with patch.object(rotate_jwt, "_client", return_value=client):
        rc = rotate_jwt.rotate("staging", dry_run=False)

    assert rc == 1
    client.put_secret_value.assert_not_called()


# --- DB rotation ---

def test_db_prepare_stages_next_password():
    existing = {"jwt_secret": "j", "database_password": "old-db"}
    client = _mock_client(existing)

    with patch.object(rotate_db, "_client", return_value=client):
        rc = rotate_db.prepare("staging")

    assert rc == 0
    call = client.put_secret_value.call_args
    written = json.loads(call.kwargs["SecretString"])
    assert "database_password_next" in written
    assert written["database_password_next"] != "old-db"
    assert written["database_password"] == "old-db"  # not yet changed


def test_db_commit_without_prepare_fails():
    existing = {"jwt_secret": "j", "database_password": "old-db"}
    client = _mock_client(existing)

    with patch.object(rotate_db, "_client", return_value=client):
        rc = rotate_db.commit("staging")

    assert rc == 1
    client.put_secret_value.assert_not_called()


@pytest.mark.skipif(
    not os.getenv("RUN_DB_ROTATION_TEST"),
    reason="set RUN_DB_ROTATION_TEST=1 to run the ALTER ROLE test",
)
def test_db_commit_against_local_postgres():
    """Full two-phase rotation against the local DB.

    Run with:

        RUN_DB_ROTATION_TEST=1 pytest tests/test_rotation.py -v

    Restores the original password at the end so the developer's
    environment is unchanged.
    """
    original = "devsecret"
    existing = {"jwt_secret": "j", "database_password": original}
    client = _mock_client(existing)

    with patch.object(rotate_db, "_client", return_value=client):
        # Phase 1
        rc = rotate_db.prepare("staging")
        assert rc == 0
        prepared = json.loads(client.put_secret_value.call_args.kwargs["SecretString"])
        new_password = prepared["database_password_next"]

        # Phase 2
        rc = rotate_db.commit("staging")
        assert rc == 0

    # Prove the new password works
    with psycopg.connect(
        host="localhost", port=5432, dbname="fieldproof",
        user="postgres", password=new_password,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            assert cur.fetchone() == (1,)

    # Restore
    with psycopg.connect(
        host="localhost", port=5432, dbname="fieldproof",
        user="postgres", password=new_password, autocommit=True,
    ) as conn:
        from psycopg import sql
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("ALTER ROLE {} WITH PASSWORD {}").format(
                    sql.Identifier("postgres"),
                    sql.Literal(original),
                )
            )
