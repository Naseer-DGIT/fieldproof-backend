"""Lab test: XXE on POST /lab/xxe/parse.

Run only with RUN_LAB_TESTS=1 against a lab-mode backend.
"""

import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LAB_TESTS") != "1",
    reason="lab tests run only with RUN_LAB_TESTS=1",
)

LOCAL_FILE = "/etc/hosts"

PAYLOAD = f"""<?xml version="1.0"?>
<!DOCTYPE root [
  <!ENTITY xxe SYSTEM "file://{LOCAL_FILE}">
]>
<root>&xxe;</root>
"""


def test_normal_xml_parses():
    r = httpx.post(
        f"{BASE}/lab/xxe/parse",
        content=b'<?xml version="1.0"?><root>hello</root>',
        headers={"Content-Type": "application/xml"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["text"].strip() == "hello"


def test_xxe_does_not_leak_local_file():
    """Before the fix, the response contains /etc/hosts content.
    After the fix, the DOCTYPE is rejected or the entity is not resolved.
    """
    r = httpx.post(
        f"{BASE}/lab/xxe/parse",
        content=PAYLOAD.encode("utf-8"),
        headers={"Content-Type": "application/xml"},
    )

    if r.status_code != 200:
        assert r.status_code in (400, 422), r.text
        return

    text = r.json()["text"]
    assert "localhost" not in text, f"local file leaked: {text!r}"
    assert "127.0.0.1" not in text, f"local file leaked: {text!r}"
