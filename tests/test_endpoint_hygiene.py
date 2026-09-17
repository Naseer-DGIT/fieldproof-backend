"""Static check: every route handler must appear in the tenant audit.

The check reads the decorator path and combines it with the router
prefix in the same file. It then looks for the resulting full path in
docs/security/s3-tenant-audit.md.

Fails if a new handler appears without a matching audit entry.

This is a poor-man's policy-as-code check. It is a backstop, not a
guarantee. The real enforcement is code review + the audit doc.
"""

import re
from pathlib import Path

AUDIT = Path("docs/security/s3-tenant-audit.md")
API_DIR = Path("app/api")

# Paths that are intentionally public or unprivileged. Match against
# the router-local path (e.g. "/login"), not the mounted full path.
#
# /login  — public, no auth required
# /health — public, no auth required (defined in app/main.py)
# /logout — authenticated but unprivileged; any active user may log out,
#           no role or tenant check applies
ALLOWED_UNGATED = {
    ("POST", "/login"),
    ("GET", "/health"),
    ("POST", "/logout"),
}

_PREFIX_RE = re.compile(r'APIRouter\([^)]*prefix\s*=\s*"([^"]*)"')
_ROUTE_RE = re.compile(r'@router\.(get|post|put|patch|delete)\("([^"]+)"')


def _router_prefix(src: str) -> str:
    match = _PREFIX_RE.search(src)
    return match.group(1) if match else ""


def _routes():
    """Yield (method, local_path, full_path) for every decorated route."""
    for f in sorted(API_DIR.glob("*.py")):
        src = f.read_text()
        prefix = _router_prefix(src)
        for match in _ROUTE_RE.finditer(src):
            method = match.group(1).upper()
            local = match.group(2)
            full = f"{prefix}{local}" if local.startswith("/") else f"{prefix}/{local}"
            yield method, local, full


def test_audit_doc_exists():
    assert AUDIT.exists(), "s3-tenant-audit.md missing"


def test_every_route_is_in_the_audit():
    audit_text = AUDIT.read_text()
    missing = []
    for method, local, full in _routes():
        if (method, local) in ALLOWED_UNGATED:
            continue
        # Accept if the audit doc mentions either the local path or the
        # prefixed path. Prefer the full path in the doc, but do not
        # fail on a doc that lists the router-local form.
        if full in audit_text or local in audit_text:
            continue
        missing.append(f"{method} {full}")

    assert not missing, (
        "Route handlers not documented in s3-tenant-audit.md:\n  "
        + "\n  ".join(missing)
        + "\n\nAdd an entry to the audit table before merging."
    )
