"""Disaster recovery drill.

Proves the backup and restore procedure works end to end without
touching the live database.

Phases:

    1. Take a backup of the source DB (dev by default)
    2. Start a throwaway Postgres container on port 15432
    3. Restore the backup into the throwaway
    4. Verify row counts match the source
    5. Tear down the container and the temp files

The throwaway container is named `fieldproof-dr-drill`. If a container
with that name exists, the script refuses to run — leftover state is a
sign a previous drill crashed and needs inspection.

Usage:

    python scripts/dr_drill.py --environment dev
    python scripts/dr_drill.py --environment dev --keep-container
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.secrets import load_secrets  # noqa: E402

DRILL_CONTAINER = "fieldproof-dr-drill"
DRILL_PORT = 15432
DRILL_PASSWORD = "drillsecret"
DRILL_DB = "fieldproof"

SOURCE_URL_DEFAULT = "postgresql://postgres:devsecret@localhost:5432/fieldproof"


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def _docker_available() -> bool:
    return _run(["docker", "info"]).returncode == 0


def _container_exists(name: str) -> bool:
    r = _run(["docker", "ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Names}}"])
    return r.stdout.strip() == name


def _wait_for_postgres(port: int, timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = _run([
            "pg_isready", "-h", "localhost", "-p", str(port), "-U", "postgres"
        ])
        if r.returncode == 0:
            return True
        time.sleep(1)
    return False


def _phase(number: int, label: str) -> None:
    print(f"phase {number}: {label}")


def _count_rows(url: str, table: str) -> int:
    import psycopg
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            row = cur.fetchone()
            assert row is not None
            return int(row[0])


def _list_tables(url: str) -> list[str]:
    import psycopg
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            return [r[0] for r in cur.fetchall()]


def drill(environment: str, keep_container: bool) -> int:
    if not _docker_available():
        print("error: docker daemon is not running", file=sys.stderr)
        return 1

    if _container_exists(DRILL_CONTAINER):
        print(
            f"error: container {DRILL_CONTAINER!r} already exists. "
            "Remove it with `docker rm -f " + DRILL_CONTAINER + "` "
            "before running the drill.",
            file=sys.stderr,
        )
        return 1

    source_url = os.getenv("SOURCE_DATABASE_URL", SOURCE_URL_DEFAULT)
    if environment in ("staging", "prod"):
        secrets = load_secrets(environment)
        source_url = source_url.replace("__DB_PASSWORD__", secrets.database_password)

    tmpdir = Path(f"/tmp/fieldproof-drill-{int(time.time())}")
    tmpdir.mkdir(parents=True, exist_ok=True)

    drill_url = (
        f"postgresql://postgres:{DRILL_PASSWORD}@localhost:{DRILL_PORT}/{DRILL_DB}"
    )

    try:
        # Phase 1: backup
        _phase(1, "backup source DB")
        env = os.environ.copy()
        env["DATABASE_URL"] = source_url
        rc = subprocess.run(
            [sys.executable, "scripts/backup_db.py",
             "--environment", environment,
             "--output-dir", str(tmpdir)],
            capture_output=True, text=True, env=env,
        )
        if rc.returncode != 0:
            print(f"error: backup failed: {rc.stderr}", file=sys.stderr)
            return 1
        backup = next(tmpdir.glob("*.sql.gpg"), None)
        if backup is None:
            print("error: no backup file produced", file=sys.stderr)
            return 1
        print(f"  backup: {backup.name}")

        # Phase 2: throwaway container
        _phase(2, f"start throwaway container on port {DRILL_PORT}")
        rc = _run([
            "docker", "run", "-d",
            "--name", DRILL_CONTAINER,
            "-e", f"POSTGRES_PASSWORD={DRILL_PASSWORD}",
            "-e", f"POSTGRES_DB={DRILL_DB}",
            "-p", f"{DRILL_PORT}:5432",
            "postgres:16-alpine",
        ])
        if rc.returncode != 0:
            print(f"error: docker run failed: {rc.stderr}", file=sys.stderr)
            return 1

        if not _wait_for_postgres(DRILL_PORT):
            print("error: throwaway postgres did not become ready", file=sys.stderr)
            return 1
        print(f"  container: {DRILL_CONTAINER}")

        # Phase 3: restore
        _phase(3, "restore into the throwaway")
        env = os.environ.copy()
        env["DATABASE_URL"] = drill_url
        env["ENVIRONMENT"] = environment
        rc = subprocess.run(
            [sys.executable, "scripts/restore_db.py", str(backup),
             "--environment", environment,
             "--target", DRILL_DB],
            capture_output=True, text=True, env=env,
        )
        if rc.returncode != 0:
            print(f"error: restore failed: {rc.stderr}", file=sys.stderr)
            return 1

        # Phase 4: verify
        _phase(4, "verify row counts")
        src_users = _count_rows(source_url, "users")
        dst_users = _count_rows(drill_url, "users")
        print(f"  users: source={src_users} restored={dst_users}")
        if src_users != dst_users:
            print("error: row count mismatch", file=sys.stderr)
            return 1

        src_tables = set(_list_tables(source_url))
        dst_tables = set(_list_tables(drill_url))
        if not src_tables.issubset(dst_tables):
            missing = src_tables - dst_tables
            print(f"error: missing tables in restore: {missing}", file=sys.stderr)
            return 1
        print(f"  tables: {len(dst_tables)} present")

        return 0

    finally:
        # Phase 5: tear down
        _phase(5, "tear down")
        if not keep_container:
            _run(["docker", "rm", "-f", DRILL_CONTAINER])
        else:
            print(f"  kept container: {DRILL_CONTAINER} (--keep-container)")

        for f in tmpdir.glob("*"):
            f.unlink(missing_ok=True)
        try:
            tmpdir.rmdir()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", default="dev",
                        choices=["dev", "lab", "staging", "prod"])
    parser.add_argument("--keep-container", action="store_true",
                        help="leave the throwaway container running for inspection")
    args = parser.parse_args()

    rc = drill(args.environment, args.keep_container)
    if rc == 0:
        print("OK: drill passed")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
