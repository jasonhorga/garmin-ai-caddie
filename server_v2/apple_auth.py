# server_v2/apple_auth.py
"""Verify a 'Sign in with Apple' identity token (native flow). No Apple secret needed —
we only verify the RS256 signature against Apple's public JWKS + the standard claims."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import jwt
from jwt import PyJWKClient

APPLE_ISSUER = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"


class AppleAuthError(Exception):
    """Raised when an Apple identity token fails verification."""


@dataclass(frozen=True)
class AppleIdentity:
    subject: str  # Apple `sub` — the stable per-user id
    email: str | None


_jwks_client: PyJWKClient | None = None


def _default_signing_key(token: str):
    global _jwks_client
    if _jwks_client is None:
        # Not thread-safe on first init, but PyJWKClient init is idempotent so a dual init is benign.
        _jwks_client = PyJWKClient(APPLE_JWKS_URL)  # caches keys internally
    return _jwks_client.get_signing_key_from_jwt(token).key


def verify_apple_identity_token(
    token: str, *, audience: str | list[str],
    signing_key_resolver: Callable[[str], object] = _default_signing_key,
) -> AppleIdentity:
    """Verify signature + aud/iss/exp; return the Apple identity. Raise AppleAuthError on any failure."""
    if not audience:
        raise AppleAuthError("apple audience (bundle id) not configured")
    try:
        key = signing_key_resolver(token)
        claims = jwt.decode(
            token, key, algorithms=["RS256"], audience=audience, issuer=APPLE_ISSUER,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except AppleAuthError:
        raise  # don't double-wrap if a custom signing_key_resolver raised this directly
    except Exception as exc:  # PyJWT errors, key fetch errors, etc.
        raise AppleAuthError(f"apple token verification failed: {exc}") from exc
    subject = claims.get("sub")
    if not subject:
        raise AppleAuthError("apple token missing sub")
    return AppleIdentity(subject=subject, email=claims.get("email"))
