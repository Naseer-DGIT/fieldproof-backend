"""Encrypted database backup.

Runs pg_dump, pipes it through GPG symmetric encryption (AES-256),
writes the encrypted file plus a SHA-256 sidecar.

Usage:

    python scripts/backup_db.py --environment dev
    python scripts/backup_db.py --environment dev --output-dir /tmp/backups
    python scripts/backup_db.py --environment staging --upload-s3
"""

import argparse
import hashlib
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.secrets import load_secrets  # noqa: E402

DEFAULT_OUTPUT_DIR = Path("backups")


def _parse_db_url(url: str) -> dict:
    """Extract host, port, user, dbname from a SQLAlchemy URL.

    Format: postgresql+psycopg://user:password@host:port/dbname
    """
    scheme, rest = url.split("://", 1)
    auth, hostpart = rest.split("@", 1)
    user, _password = auth.split(":", 1)
    hostport, dbname = hostpart.split("/", 1)

    if ":" in hostport:
        host, port = hostport.rsplit(":", 1)
    else:
        host, port = hostport, "5432"

    return {"user": user, "host": host, "port": port, "dbname": dbname}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def backup(
    environment: str,
    output_dir: Path,
    upload_s3: bool = False,
) -> int:
    secrets = load_secrets(environment)
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:devsecret@localhost:5432/fieldproof",
    )
    # In staging and prod, the DB password comes from the secret.
    if environment in ("staging", "prod"):
        db_url = db_url.replace("__DB_PASSWORD__", secrets.database_password)

    db = _parse_db_url(db_url)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"fieldproof-{environment}-{timestamp}"
    sql_gpg = output_dir / f"{stem}.sql.gpg"
    sha_file = output_dir / f"{stem}.sha256"

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"dumping {db['dbname']} on {db['host']}:{db['port']}")
    print(f"output:  {sql_gpg}")

    dump_cmd = [
        "pg_dump",
        "-h", db["host"],
        "-p", str(db["port"]),
        "-U", db["user"],
        "-d", db["dbname"],
        "--no-owner",
        "--no-acl",
    ]
    gpg_cmd = [
        "gpg",
        "--batch",
        "--yes",
        "--symmetric",
        "--cipher-algo", "AES256",
        "--passphrase-fd", "0",
        "--output", str(sql_gpg),
    ]

    env = os.environ.copy()
    env["PGPASSWORD"] = secrets.database_password

    gpg_cmd = [
        "gpg",
        "--batch",
        "--yes",
        "--pinentry-mode", "loopback",
        "--symmetric",
        "--cipher-algo", "AES256",
        "--passphrase", secrets.backup_passphrase,
        "--output", str(sql_gpg),
    ]

    try:
        # dump_cmd is a list, not a string; no shell is invoked. Args
        # come from DATABASE_URL, a deployment-controlled env var.
        # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
        with subprocess.Popen(dump_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env) as pg:
            with subprocess.Popen(gpg_cmd, stdin=pg.stdout, stderr=subprocess.PIPE) as gpg:
                assert pg.stdout is not None
                pg.stdout.close()
                _, gpg_err = gpg.communicate()
                pg_err = pg.stderr.read() if pg.stderr else b""
                pg.wait()

        if pg.returncode != 0:
            print(f"error: pg_dump failed: {pg_err.decode()}", file=sys.stderr)
            return 1
        if gpg.returncode != 0:
            print(f"error: gpg failed: {gpg_err.decode()}", file=sys.stderr)
            return 1

    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    digest = _sha256(sql_gpg)
    sha_file.write_text(f"{digest}  {sql_gpg.name}\n")
    print(f"sha256:  {digest}")

    if upload_s3:
        bucket = os.getenv("BACKUP_S3_BUCKET")
        if not bucket:
            print("error: --upload-s3 requires BACKUP_S3_BUCKET", file=sys.stderr)
            return 1
        import boto3
        s3 = boto3.client(
            "s3",
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            endpoint_url=os.getenv("AWS_ENDPOINT_URL"),
        )
        s3.upload_file(str(sql_gpg), bucket, sql_gpg.name)
        s3.upload_file(str(sha_file), bucket, sha_file.name)
        print(f"uploaded: s3://{bucket}/{sql_gpg.name}")

    print("done")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", required=True,
                        choices=["dev", "lab", "staging", "prod"])
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--upload-s3", action="store_true")
    args = parser.parse_args()

    return backup(
        environment=args.environment,
        output_dir=Path(args.output_dir),
        upload_s3=args.upload_s3,
    )


if __name__ == "__main__":
    raise SystemExit(main())
