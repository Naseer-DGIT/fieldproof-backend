"""Authorization audit writer.

Called from the FastAPI exception handler for every 401, 403, and 404.
Uses its own session so a failure to audit never affects the response
the caller sees.

Design rules:
  - Never records the request body, query string, headers, or IP.
  - Never raises. An audit failure is logged and swallowed.
  - Fire-and-forget write inside the request handler. If this becomes
    a latency problem, move it to a background queue in S14.
"""

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import SessionLocal
import logging

log = logging.getLogger("fieldproof.audit")
from app.models import AuthorizationEvent

AUDITED_STATUS = {401, 403, 404}


def record_denial(
    request: Request,
    status_code: int,
    reason: str,
) -> None:
    if status_code not in AUDITED_STATUS:
        return

    user_id = getattr(request.state, "user_id", None)
    tenant_id = getattr(request.state, "tenant_id", None)

    # Truncate to the column width. A long reason is not worth a 500.
    reason = (reason or "")[:128]

    db = SessionLocal()
    try:
        db.add(
            AuthorizationEvent(
                user_id=user_id,
                tenant_id=tenant_id,
                status_code=status_code,
                reason=reason,
                method=request.method[:8],
                endpoint=request.url.path[:128],
            )
        )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        log.warning("audit.write_failed", error=str(exc))
    finally:
        db.close()
