"""Backup and restore round-trip tests.

Creates a backup of the dev database, restores it into a temporary
database, and asserts the row counts match. Cleans up the temp DB
afterward.

These tests are opt-in:

    RUN_BACKUP_TEST=1 pytest tests/test_backup.py -v

They need pg_dump, gpg, and a running Postgres.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import psycopg
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_BACKUP_TEST"),
    reason="set RUN_BACKUP_TEST=1 to run backup round-trip tests",
)


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


@pytest.fixture(scope="module")
def require_tools():
    for tool in ("pg_dump", "pg_restore", "psql", "gpg"):
        if not _have(tool):
            pytest.skip(f"{tool} not on PATH")


@pytest.fixture(scope="module")
def source_count() -> int:
    conn_str = "postgresql://postgres:devsecret@localhost:5432/fieldproof"
    with psycopg.connect(conn_str) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            row = cur.fetchone()
            assert row is not None
            return int(row[0])


@pytest.fixture(scope="module")
def backup_file(require_tools) -> Path:
    tmpdir = Path(tempfile.mkdtemp(prefix="fieldproof-backup-"))
    rc = subprocess.run(
        [sys.executable, "scripts/backup_db.py", "--environment", "dev",
         "--output-dir", str(tmpdir)],
        capture_output=True,
        cwd=str(Path(__file__).parent.parent),
    )
    if rc.returncode != 0:
        pytest.fail(f"backup_db.py failed: {rc.stderr.decode()}")

    files = list(tmpdir.glob("*.sql.gpg"))
    assert len(files) == 1, f"expected one .sql.gpg, got {files}"
    yield files[0]
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_backup_creates_encrypted_file(backup_file: Path):
    assert backup_file.exists()
    assert backup_file.stat().st_size > 0

    sha_file = backup_file.parent / (backup_file.name.replace(".sql.gpg", ".sha256"))
    assert sha_file.exists(), "sha256 sidecar missing"


def test_backup_is_encrypted(backup_file: Path):
    """The file must not be readable as plaintext. Look for a table
    name that would appear in an unencrypted pg_dump."""
    content = backup_file.read_bytes()
    assert b"CREATE TABLE" not in content
    assert b"users" not in content[:4096]


def test_restore_round_trip(backup_file: Path, source_count: int):
    target = "fieldproof_restore_pytest"

    # Clean up any leftover from a previous run
    with psycopg.connect(
        "postgresql://postgres:devsecret@localhost:5432/postgres", autocommit=True
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {target}")

    rc = subprocess.run(
        [sys.executable, "scripts/restore_db.py", str(backup_file),
         "--environment", "dev", "--target", target],
        capture_output=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert rc.returncode == 0, rc.stderr.decode()

    try:
        with psycopg.connect(
            f"postgresql://postgres:devsecret@localhost:5432/{target}"
        ) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM users")
                row = cur.fetchone()
                assert row is not None
                assert int(row[0]) == source_count
    finally:
        with psycopg.connect(
            "postgresql://postgres:devsecret@localhost:5432/postgres",
            autocommit=True,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS {target}")


def test_restore_refuses_unsafe_target(backup_file: Path):
    """A target that does not start with 'fieldproof' must be refused
    without --force."""
    rc = subprocess.run(
        [sys.executable, "scripts/restore_db.py", str(backup_file),
         "--environment", "dev", "--target", "postgres"],
        capture_output=True,
        cwd=str(Path(__file__).parent.parent),
    )
    assert rc.returncode == 1
    assert b"refusing to restore" in rc.stderr
