"""Authorization audit writer.

Called from the FastAPI exception handler for every 401, 403, and 404.
Uses its own session so a failure to audit never affects the response
the caller sees.

Every row is chained to the one before it. Modifying any field of any
row breaks the chain at that row. Verification walks the chain and
reports the first mismatch. See `verify_chain` in this module.

Design rules:
  - Never records the request body, query string, headers, or IP.
  - Never raises. An audit failure is logged and swallowed.
  - All chain operations run inside a single transaction with a row
    lock on the previous row to prevent two concurrent writers from
    forking the chain.
"""

import hashlib
import logging
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import SessionLocal
from app.models import AuthorizationEvent

log = logging.getLogger("fieldproof.audit")

AUDITED_STATUS = {401, 403, 404}
GENESIS = "GENESIS"


def _canonical(
    previous_hash: str,
    user_id: int | None,
    tenant_id: int | None,
    status_code: int,
    reason: str,
    method: str,
    endpoint: str,
    created_at_iso: str,
) -> str:
    """Stable string used for hashing. Order and separators matter."""
    return "|".join(
        [
            previous_hash or GENESIS,
            "" if user_id is None else str(user_id),
            "" if tenant_id is None else str(tenant_id),
            str(status_code),
            reason,
            method,
            endpoint,
            created_at_iso,
        ]
    )


def _hash(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def record_denial(
    request: Request,
    status_code: int,
    reason: str,
) -> None:
    if status_code not in AUDITED_STATUS:
        return

    user_id = getattr(request.state, "user_id", None)
    tenant_id = getattr(request.state, "tenant_id", None)
    reason = (reason or "")[:128]
    method = request.method[:8]
    endpoint = request.url.path[:128]
    created_at = datetime.now(timezone.utc)
    created_at_iso = created_at.isoformat()

    db = SessionLocal()
    try:
        # Lock the previous row so two concurrent writers cannot both
        # read the same previous_hash and produce two "next" rows.
        prev = (
            db.query(AuthorizationEvent)
            .order_by(AuthorizationEvent.id.desc())
            .with_for_update()
            .first()
        )
        previous_hash = prev.self_hash if prev is not None else GENESIS

        canonical = _canonical(
            previous_hash,
            user_id,
            tenant_id,
            status_code,
            reason,
            method,
            endpoint,
            created_at_iso,
        )
        self_hash = _hash(canonical)

        db.add(
            AuthorizationEvent(
                user_id=user_id,
                tenant_id=tenant_id,
                status_code=status_code,
                reason=reason,
                method=method,
                endpoint=endpoint,
                previous_hash=previous_hash,
                self_hash=self_hash,
                created_at=created_at,
            )
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        log.warning("audit.write_failed error=%s", exc)
    finally:
        db.close()


def verify_chain() -> dict:
    """Walk the chain in id order and report the first break.

    Returns a dict:
      { "rows_checked": int, "breaks": [ {id, reason}, ... ] }

    A break is reported when:
      - previous_hash does not equal the prior row's self_hash
      - self_hash does not match the recomputed hash

    Breaks are reported, not raised. The caller decides what to do.
    """
    db = SessionLocal()
    try:
        rows = (
            db.query(AuthorizationEvent)
            .order_by(AuthorizationEvent.id.asc())
            .all()
        )
        breaks: list[dict] = []
        expected_previous = GENESIS

        for row in rows:
            if row.previous_hash != expected_previous:
                breaks.append(
                    {
                        "id": row.id,
                        "reason": (
                            f"previous_hash {row.previous_hash!r} != "
                            f"expected {expected_previous!r}"
                        ),
                    }
                )

            canonical = _canonical(
                row.previous_hash,
                row.user_id,
                row.tenant_id,
                row.status_code,
                row.reason,
                row.method,
                row.endpoint,
                row.created_at.isoformat(),
            )
            recomputed = _hash(canonical)
            if recomputed != row.self_hash:
                breaks.append(
                    {
                        "id": row.id,
                        "reason": "self_hash does not match recomputed hash",
                    }
                )

            expected_previous = row.self_hash

        return {"rows_checked": len(rows), "breaks": breaks}
    finally:
        db.close()
