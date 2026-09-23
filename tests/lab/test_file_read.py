"""Lab test: Path Traversal on GET /lab/files/read.

A file outside the base directory must not be readable.

Before the fix: `../lab_secret.txt` returns the file contents.
After the fix: the request is rejected and the secret is not returned.

Run only with RUN_LAB_TESTS=1 against a lab-mode backend.
"""

import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

BASE = os.getenv("BASE_URL", "http://localhost:8000/api/v1")

SECRET_PATH = "/tmp/lab_secret.txt"
SECRET_CONTENT = "secret contents outside the base"

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LAB_TESTS") != "1",
    reason="lab tests run only with RUN_LAB_TESTS=1",
)


@pytest.fixture(autouse=True)
def _ensure_files():
    os.makedirs("/tmp/lab_files", exist_ok=True)
    with open("/tmp/lab_files/public.txt", "w") as f:
        f.write("public file contents\n")
    with open(SECRET_PATH, "w") as f:
        f.write(SECRET_CONTENT + "\n")


def _read(path: str) -> httpx.Response:
    return httpx.get(
        f"{BASE}/lab/files/read",
        params={"path": path},
    )


def test_normal_read_works():
    r = _read("public.txt")
    assert r.status_code == 200, r.text
    assert "public file contents" in r.json()["content"]


def test_dotdot_escape_is_blocked():
    """The critical test.

    BEFORE fix: 200 with the secret contents.
    AFTER fix: 400 (path escapes base).
    """
    r = _read("../lab_secret.txt")

    if r.status_code == 200:
        body = r.json().get("content", "")
        if SECRET_CONTENT in body:
            pytest.fail(
                f"path traversal: read outside the base. content={body!r}"
            )
        return

    assert r.status_code in (400, 403, 404), r.text
    assert SECRET_CONTENT not in r.text


def test_absolute_path_is_blocked():
    r = _read("/etc/hosts")

    if r.status_code == 200:
        body = r.json().get("content", "")
        if "localhost" in body:
            pytest.fail(
                f"absolute path read succeeded. content={body[:120]!r}"
            )
        return

    assert r.status_code in (400, 403, 404), r.text


def test_nested_dotdot_is_blocked():
    """A path that pretends to descend before escaping."""
    r = _read("subdir/../../lab_secret.txt")

    if r.status_code == 200:
        body = r.json().get("content", "")
        if SECRET_CONTENT in body:
            pytest.fail(f"nested traversal succeeded. content={body!r}")
        return

    assert r.status_code in (400, 403, 404), r.text
