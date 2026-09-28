"""Disaster recovery drill test.

Creates a small source DB, backs it up, and runs the drill against it.
Cleans up afterward. Opt-in:

    RUN_DR_DRILL_TEST=1 pytest tests/test_dr_drill.py -v

Requires Docker, pg_dump, psql, and gpg.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_DR_DRILL_TEST"),
    reason="set RUN_DR_DRILL_TEST=1 to run the DR drill test",
)

REPO = Path(__file__).parent.parent
SOURCE_DB = "fieldproof_dr_test_source"
LIVE_ADMIN_URL = "postgresql://postgres:devsecret@localhost:5432/postgres"


def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


@pytest.fixture(scope="module")
def require_tools():
    for tool in ("pg_dump", "psql", "gpg", "docker"):
        if not _have(tool):
            pytest.skip(f"{tool} not on PATH")


@pytest.fixture(scope="module")
def source_db(require_tools):
    """Create a small source DB with two tables and a known row count."""
    with psycopg.connect(LIVE_ADMIN_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {SOURCE_DB}")

    with psycopg.connect(LIVE_ADMIN_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            from psycopg import sql
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(SOURCE_DB)))

    src_url = f"postgresql://postgres:devsecret@localhost:5432/{SOURCE_DB}"
    with psycopg.connect(src_url) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE users (
                    id SERIAL PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE
                )
            """)
            cur.execute("""
                CREATE TABLE attendance_events (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL
                )
            """)
            for i in range(5):
                cur.execute(
                    "INSERT INTO users (email) VALUES (%s)",
                    (f"dr-{i}@example.com",),
                )
            for _ in range(3):
                cur.execute(
                    "INSERT INTO attendance_events (user_id, event_type) VALUES (%s, %s)",
                    (1, "check_in"),
                )
        conn.commit()

    yield src_url

    with psycopg.connect(LIVE_ADMIN_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {SOURCE_DB}")


def test_drill_passes_against_small_source(source_db):
    env = os.environ.copy()
    env["SOURCE_DATABASE_URL"] = source_db
    env["DATABASE_URL"] = source_db
    env["ENVIRONMENT"] = "dev"
    env["BACKUP_PASSPHRASE"] = "test-drill-passphrase"

    rc = subprocess.run(
        [sys.executable, "scripts/dr_drill.py", "--environment", "dev"],
        capture_output=True, text=True, cwd=str(REPO), env=env,
    )

    assert rc.returncode == 0, (
        f"drill failed\nstdout:\n{rc.stdout}\nstderr:\n{rc.stderr}"
    )
    assert "OK: drill passed" in rc.stdout
    assert "phase 1" in rc.stdout
    assert "phase 5" in rc.stdout
