"""Ed25519 signature verification for attendance events."""

import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PublicKey,
)


def b64url_decode(value: str) -> bytes:
    """Decode base64url with or without padding.

    Dart's `base64Url.encode` produces padded output; some clients
    produce unpadded. Accept both.
    """
    stripped = value.rstrip("=")
    padding = "=" * (-len(stripped) % 4)
    return base64.urlsafe_b64decode(stripped + padding)


def verify_ed25519(
    public_key_b64: str,
    message: bytes,
    signature_b64: str,
) -> bool:
    """Verify an Ed25519 signature.

    Returns True on success, False on any failure. Never raises for
    malformed input — the caller decides how to respond.
    """
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            b64url_decode(public_key_b64)
        )
        signature = b64url_decode(signature_b64)
        public_key.verify(signature, message)
        return True
    except (InvalidSignature, ValueError):
        return False
