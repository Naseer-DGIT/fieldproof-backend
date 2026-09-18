"""One-time backfill of the audit chain.

Walks authorization_events in id order, recomputes previous_hash and
self_hash for each row, and commits in batches. Safe to run once. Do
not run after new rows have been written with valid chains — it would
break them.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import SessionLocal
from app.models import AuthorizationEvent
from app.services.audit import GENESIS, _canonical, _hash


def main() -> int:
    db = SessionLocal()
    try:
        rows = (
            db.query(AuthorizationEvent)
            .order_by(AuthorizationEvent.id.asc())
            .all()
        )
        expected_previous = GENESIS
        updated = 0

        for row in rows:
            canonical = _canonical(
                expected_previous,
                row.user_id,
                row.tenant_id,
                row.status_code,
                row.reason,
                row.method,
                row.endpoint,
                row.created_at.isoformat(),
            )
            new_hash = _hash(canonical)
            if row.previous_hash != expected_previous or row.self_hash != new_hash:
                row.previous_hash = expected_previous
                row.self_hash = new_hash
                updated += 1
            expected_previous = new_hash

        db.commit()
        print(f"backfilled {updated} of {len(rows)} rows")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
