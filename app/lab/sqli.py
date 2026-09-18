"""Lab: SQL injection.

VULNERABILITY: the `q` parameter is interpolated directly into a raw
SQL string. Any input containing a quote and SQL keywords alters the
query.

This file is intentionally vulnerable. Do not copy this pattern into
production code. The fix is in the same file, commented and applied at
the end of the sprint.

CWE-89, OWASP A03:2021 Injection.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import get_db

router = APIRouter(prefix="/lab/sqli", tags=["lab"])


@router.get("/search")
def search_users(
    q: str = Query(default="", max_length=128),
    db: Session = Depends(get_db),
) -> dict:
    """Search users by email substring.

    BUG: the query string is interpolated. The fix uses a bound
    parameter (`text(...).bindparams(...)`), which the driver escapes.
    """
    # FIXED: bound parameter. The driver escapes the value; the SQL
    # string is constant regardless of input.
    sql = text(
        "SELECT id, email, role FROM users "
        "WHERE email LIKE :pattern ORDER BY id DESC LIMIT 500"
    )
    rows = db.execute(sql, {"pattern": f"%{q}%"}).fetchall()
    return {
        "query": q,
        "rows": [
            {"id": r[0], "email": r[1], "role": r[2]}
            for r in rows
        ],
    }
