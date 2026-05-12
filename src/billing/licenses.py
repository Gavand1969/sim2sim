"""
License key generation, validation, and the FastAPI `require_pro` dependency.

Key format
----------
    LIC-XXXX-XXXX-XXXX-XXXX
where each X is from Crockford's base32 alphabet (no I, L, O, U).

Generation is HMAC-based:
    payload = "<tier>:<random_id>"
    sig     = HMAC-SHA256(SIM2SIM_LICENSE_SECRET, payload)[:10 bytes]
We then base32-encode `random_id || sig` and format with dashes.  This means
keys are self-signed: even before hitting the DB we can detect bogus keys
client-side typos and stop wasting DB queries.  The DB is still the source
of truth for tier, email, and revocation.

Dev convenience
---------------
In ENVIRONMENT=development, the bypass key "dev" and an empty header both
unlock Pro endpoints, so the demo still works without setting up Stripe.
"""
from __future__ import annotations

import base64
import datetime as dt
import hmac
import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException

from src.billing import db

# Crockford-ish base32 alphabet (no I, L, O, U to avoid confusion in printed keys).
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_TIER_FREE = "free"
_TIER_PRO = "pro"
_TIER_TEAM = "team"
_VALID_TIERS = {_TIER_PRO, _TIER_TEAM}


def _secret() -> bytes:
    """The HMAC secret used to sign license keys."""
    s = os.getenv("SIM2SIM_LICENSE_SECRET", "")
    if not s:
        # Development fallback so the demo runs out of the box.  Production
        # deployments MUST set this in the environment.
        env = os.getenv("ENVIRONMENT", "development")
        if env != "development":
            raise RuntimeError(
                "SIM2SIM_LICENSE_SECRET must be set in non-development environments."
            )
        s = "sim2sim-dev-license-secret-do-not-use-in-prod"
    return s.encode("utf-8")


def _b32_encode(data: bytes) -> str:
    """Encode bytes using our custom base32 alphabet (no padding)."""
    # Convert bytes to integer, then to base32 digits.
    n = int.from_bytes(data, "big")
    # Each byte ~ 1.6 base32 digits; we'll pad to a known length so decoding is unambiguous.
    digits = []
    if n == 0:
        digits.append(_ALPHABET[0])
    while n > 0:
        digits.append(_ALPHABET[n % 32])
        n //= 32
    digits.reverse()
    return "".join(digits)


def _format_key(raw: str) -> str:
    """Take a 16-char raw string and format as LIC-XXXX-XXXX-XXXX-XXXX."""
    assert len(raw) == 16, f"raw key must be 16 chars, got {len(raw)}"
    return f"LIC-{raw[0:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"


def _strip_key(key: str) -> str:
    """Normalise: remove dashes, uppercase, strip whitespace."""
    return key.strip().upper().replace("-", "").replace("LIC", "", 1)


def _hmac_sig(payload: str) -> bytes:
    return hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).digest()


def generate_key(tier: str) -> str:
    """
    Generate a new license key for the given tier.
    The key embeds a 5-byte random id and a 5-byte HMAC signature, encoded
    into 16 base32 characters total (10 bytes ≈ 16 base32 digits).
    """
    if tier not in _VALID_TIERS:
        raise ValueError(f"invalid tier: {tier!r}")

    random_id = secrets.token_bytes(5)  # 40 bits of entropy
    payload = f"{tier}:{random_id.hex()}"
    sig = _hmac_sig(payload)[:5]  # 40-bit truncated HMAC

    # 10 bytes → exactly 16 base32 digits (80 bits / 5).
    raw_bytes = random_id + sig
    encoded = _b32_encode(raw_bytes)
    # Pad with leading zeros up to 16 chars (encoding of small ints is short).
    encoded = encoded.rjust(16, _ALPHABET[0])
    return _format_key(encoded)


def _key_is_well_formed(key: str) -> bool:
    """Cheap syntactic check — does NOT verify signature."""
    if not key.startswith("LIC-"):
        return False
    parts = key.split("-")
    if len(parts) != 5:
        return False
    if any(len(p) != 4 for p in parts[1:]):
        return False
    body = "".join(parts[1:])
    return all(c in _ALPHABET for c in body)


# ── Domain dataclass ──────────────────────────────────────────────────────────


@dataclass
class LicenseInfo:
    key: str
    tier: str            # 'pro' | 'team'
    email: str
    created_at: str
    activated_at: Optional[str]
    activation_count: int


def _row_to_info(row) -> LicenseInfo:
    return LicenseInfo(
        key=row["key"],
        tier=row["tier"],
        email=row["email"],
        created_at=row["created_at"],
        activated_at=row["activated_at"],
        activation_count=row["activation_count"],
    )


# ── Public API ────────────────────────────────────────────────────────────────


def create_license(
    tier: str,
    email: str,
    stripe_session_id: Optional[str] = None,
) -> LicenseInfo:
    """
    Generate a new key and persist it.  Idempotent on stripe_session_id —
    if a license already exists for the session, returns the existing one.
    """
    if tier not in _VALID_TIERS:
        raise ValueError(f"invalid tier: {tier!r}")

    # Idempotency check
    if stripe_session_id:
        existing = db.find_by_stripe_session(stripe_session_id)
        if existing is not None:
            return _row_to_info(existing)

    key = generate_key(tier)
    created_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.insert_license(
        key=key, tier=tier, email=email, created_at=created_at,
        stripe_session_id=stripe_session_id,
    )
    row = db.find_by_key(key)
    assert row is not None
    return _row_to_info(row)


def validate_license(key: str) -> Optional[LicenseInfo]:
    """
    Validate a license key.  Returns LicenseInfo on success, None otherwise.
    Performs cheap syntactic check before DB lookup.
    """
    if not key:
        return None
    if not _key_is_well_formed(key):
        return None
    row = db.find_by_key(key.strip().upper())
    if row is None:
        return None
    if row["revoked"]:
        return None
    return _row_to_info(row)


def activate_license(key: str) -> Optional[LicenseInfo]:
    """
    Validate AND record an activation (bump counter, set activated_at).
    Returns LicenseInfo on success, None otherwise.
    """
    info = validate_license(key)
    if info is None:
        return None
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.record_activation(info.key, now)
    return validate_license(info.key)


# ── FastAPI dependency ────────────────────────────────────────────────────────


def _dev_bypass(key: str) -> bool:
    env = os.getenv("ENVIRONMENT", "development")
    return env == "development" and key in ("", "dev", "DEV")


async def require_pro(x_license_key: str = Header(default="")) -> str:
    """
    FastAPI dependency: gates Pro endpoints.  In development the bypass key
    "dev" (or an empty header) is accepted so the demo still runs without
    Stripe.  In production, the key must validate against the database.
    """
    if _dev_bypass(x_license_key):
        return "dev"
    info = validate_license(x_license_key)
    if info is None:
        raise HTTPException(
            status_code=403,
            detail="Valid Pro or Team license key required.",
        )
    if info.tier not in _VALID_TIERS:
        raise HTTPException(status_code=403, detail="License tier does not include this feature.")
    return info.key


async def require_team(x_license_key: str = Header(default="")) -> str:
    """Stricter dependency: only Team-tier license keys pass."""
    if _dev_bypass(x_license_key):
        return "dev"
    info = validate_license(x_license_key)
    if info is None or info.tier != _TIER_TEAM:
        raise HTTPException(
            status_code=403,
            detail="Team license key required.",
        )
    return info.key
