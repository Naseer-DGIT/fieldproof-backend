"""Restore an encrypted database backup.

Verifies the SHA-256 sidecar before decrypting. Refuses to restore into
a database whose name does not start with 'fieldproof' unless --force
is passed. Default target is a temporary DB named
`fieldproof_restore_test` so a developer can verify a backup without
touching the live database.

Usage:

    python scripts/restore_db.py backups/fieldproof-dev-20260924T120000Z.sql.gpg \
        --environment dev \
        --target fieldproof_restore_test

    python scripts/restore_db.py backups/... --environment dev --target fieldproof --force
"""

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.secrets import load_secrets  # noqa: E402


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_sha(backup: Path) -> bool:
    sha_file = backup.with_suffix("")  # strip .gpg
    sha_file = sha_file.parent / (sha_file.name.rsplit(".sql", 1)[0] + ".sha256")

    if not sha_file.exists():
        print(f"warn: no sha256 sidecar ({sha_file.name}); skipping integrity check")
        return True

    expected = sha_file.read_text().split()[0]
    actual = _sha256(backup)
    if expected != actual:
        print(f"error: sha256 mismatch", file=sys.stderr)
        print(f"  expected: {expected}", file=sys.stderr)
        print(f"  actual:   {actual}", file=sys.stderr)
        return False
    print(f"sha256 ok: {actual}")
    return True


def _parse_db_url(url: str) -> dict:
    scheme, rest = url.split("://", 1)
    auth, hostpart = rest.split("@", 1)
    user, _password = auth.split(":", 1)
    hostport, dbname = hostpart.split("/", 1)
    if ":" in hostport:
        host, port = hostport.rsplit(":", 1)
    else:
        host, port = hostport, "5432"
    return {"user": user, "host": host, "port": port, "dbname": dbname}


def _ensure_target_exists(conn_str: str, target: str) -> None:
    """Create the target database if it does not exist."""
    with psycopg.connect(conn_str, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target,))
            if cur.fetchone() is None:
                from psycopg import sql
                cur.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target))
                )
                print(f"created database: {target}")


def restore(
    backup: Path,
    environment: str,
    target: str,
    force: bool,
) -> int:
    if not backup.exists():
        print(f"error: {backup} does not exist", file=sys.stderr)
        return 1

    if not target.startswith("fieldproof") and not force:
        print(
            f"error: refusing to restore into {target!r}. "
            "Target must start with 'fieldproof'. Pass --force to override.",
            file=sys.stderr,
        )
        return 1

    if not _verify_sha(backup):
        return 1

    secrets = load_secrets(environment)
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:devsecret@localhost:5432/fieldproof",
    )
    if environment in ("staging", "prod"):
        db_url = db_url.replace("__DB_PASSWORD__", secrets.database_password)

    db = _parse_db_url(db_url)
    admin_url = f"postgresql://{db['user']}:{secrets.database_password}@{db['host']}:{db['port']}/postgres"

    print(f"restoring into: {target}")
    _ensure_target_exists(admin_url, target)

    # Decrypt to a temporary file, then psql it in.
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".sql", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        gpg_cmd = [
            "gpg",
            "--batch",
            "--yes",
            "--pinentry-mode", "loopback",
            "--decrypt",
            "--passphrase", secrets.backup_passphrase,
            "--output", str(tmp_path),
            str(backup),
        ]
        result = subprocess.run(gpg_cmd, capture_output=True)
        if result.returncode != 0:
            print(f"error: gpg decrypt failed: {result.stderr.decode()}", file=sys.stderr)
            return 1

        env = os.environ.copy()
        env["PGPASSWORD"] = secrets.database_password

        psql_cmd = [
            "psql",
            "-h", db["host"],
            "-p", str(db["port"]),
            "-U", db["user"],
            "-d", target,
            "-f", str(tmp_path),
            "-q",
        ]
        result = subprocess.run(psql_cmd, env=env, capture_output=True)
        if result.returncode != 0:
            print(f"error: psql failed: {result.stderr.decode()}", file=sys.stderr)
            return 1

        print("restore complete")
        return 0
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", type=Path)
    parser.add_argument("--environment", required=True,
                        choices=["dev", "lab", "staging", "prod"])
    parser.add_argument("--target", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    return restore(
        backup=args.backup,
        environment=args.environment,
        target=args.target,
        force=args.force,
    )


if __name__ == "__main__":
    raise SystemExit(main())
