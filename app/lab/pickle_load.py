"""Lab: Insecure Deserialization — FIXED version.

The vulnerable version accepted base64-encoded pickle bytes and called
`pickle.loads` on them. That is arbitrary code execution: any
`__reduce__` in the payload runs on the server.

The fix removes pickle entirely. The endpoint accepts only base64
encoded JSON. JSON cannot construct arbitrary objects, cannot invoke
callables, and cannot execute code. There is no "safe pickle" for
untrusted input — the format itself is the problem.

CWE-502, OWASP A08:2021 Software and Data Integrity Failures.
"""

import base64
import json

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

router = APIRouter(prefix="/lab/pickle", tags=["lab"])


class LoadRequest(BaseModel):
    data_b64: str


@router.post("/load")
def load_json(body: LoadRequest) -> dict:
    """Deserialize base64-encoded JSON.

    Only JSON is accepted. A base64-encoded pickle payload raises
    JSONDecodeError at the parse step, before any object construction.
    """
    try:
        raw = base64.b64decode(body.data_b64)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="data_b64 is not valid base64",
        )

    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="payload is not valid JSON",
        )

    return {
        "type": type(obj).__name__,
        "repr": repr(obj)[:200],
    }
