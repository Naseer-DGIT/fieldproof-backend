"""Lab: Path Traversal — FIXED version.

The vulnerable version joined the caller's input onto a base directory
and read the result. `..` sequences and absolute paths escaped the
base.

The fix:
  1. Rejects the input if it contains a null byte.
  2. Resolves both the base and the candidate with `.resolve()`.
  3. Confirms the resolved candidate is the base or is inside it.

Checking the resolved path matters. A check on the raw string
(`if ".." in path`) misses symlinks and URL-encoded forms. Resolving
follows symlinks and normalises `..`, so the check is on the final
target.

CWE-22, OWASP A01:2021 Broken Access Control.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status

router = APIRouter(prefix="/lab/files", tags=["lab"])

BASE_DIR = Path("/tmp/lab_files").resolve()


def _safe_resolve(user_path: str) -> Path:
    """Resolve `user_path` inside BASE_DIR or raise 400.

    Returns the resolved absolute path, guaranteed to be inside
    BASE_DIR.
    """
    if "\x00" in user_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="path contains a null byte",
        )

    if not user_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="path is empty",
        )

    # Resolve both sides. `.resolve()` follows symlinks and normalises
    # `..`, so the comparison is on the real target.
    candidate = (BASE_DIR / user_path).resolve()

    # is_relative_to returns True when candidate == BASE_DIR or when
    # candidate is nested inside it. Python 3.9+.
    if not candidate.is_relative_to(BASE_DIR):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="path escapes the base directory",
        )

    return candidate


@router.get("/read")
def read_file(
    path: str = Query(..., max_length=256),
) -> dict:
    """Read a file from the base directory. Traversal is rejected."""
    candidate = _safe_resolve(path)

    try:
        content = candidate.read_text()
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="file not found",
        )
    except IsADirectoryError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="path is a directory",
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="permission denied",
        )

    return {
        "path": path,
        "resolved": str(candidate),
        "content": content[:500],
    }
