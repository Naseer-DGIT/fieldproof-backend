"""Lab test: Insecure Deserialization on POST /lab/pickle/load.

Before the fix: a pickle payload runs a shell command when the server
deserializes it. After the fix: only JSON is accepted and the payload
is rejected at the parse step.

Run only with RUN_LAB_TESTS=1 against a lab-mode backend.
"""

import base64
import os
import pickle
import sys
import uuid

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LAB_TESTS") != "1",
    reason="lab tests run only with RUN_LAB_TESTS=1",
)


def _marker_path() -> str:
    return f"/tmp/pickle_lab_test_{uuid.uuid4().hex}.txt"


def _payload(command: str) -> str:
    class Exploit:
        def __reduce__(self):
            return (os.system, (command,))

    return base64.b64encode(pickle.dumps(Exploit())).decode()


def test_pickle_rce_is_blocked():
    """The critical test.

    BEFORE fix: the marker file is created (test FAILS).
    AFTER fix: the request is rejected and no marker exists (test PASSES).
    """
    marker = _marker_path()
    command = f"touch {marker}"

    if os.path.exists(marker):
        os.unlink(marker)

    payload = _payload(command)

    r = httpx.post(
        f"{BASE}/lab/pickle/load",
        json={"data_b64": payload},
    )

    # After the fix: 400 (payload is not JSON).
    # Before the fix: 200 and the marker exists.
    if r.status_code in (400, 422):
        assert not os.path.exists(marker), (
            f"marker {marker!r} was created despite rejection"
        )
        return

    assert not os.path.exists(marker), (
        f"RCE: server ran {command!r} (status {r.status_code})"
    )


def test_benign_pickle_is_rejected():
    """After the fix, pickle is not accepted at all.

    BEFORE fix: this returns 200 (test FAILS).
    AFTER fix: this returns 400 (test PASSES).
    """
    benign = base64.b64encode(pickle.dumps({"safe": True})).decode()
    r = httpx.post(
        f"{BASE}/lab/pickle/load",
        json={"data_b64": benign},
    )
    assert r.status_code == 400, (
        f"benign pickle should be rejected after the fix, got {r.status_code}"
    )
    assert "json" in r.json()["detail"].lower() or "not valid" in r.json()["detail"].lower()
