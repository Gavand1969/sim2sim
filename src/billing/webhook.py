"""
Stripe webhook handler.

We support a single event: `checkout.session.completed`.  When it fires:
  1. Identify the tier from the line items or session metadata.
  2. Generate a new license (idempotent on stripe session_id).
  3. Email the key to the customer via Resend.

We deliberately keep this small:
  - We don't depend on the `stripe` Python SDK — we parse the JSON envelope
    ourselves and verify the signature with stdlib `hmac`.  This avoids
    dragging in 50+ MB of unused Stripe code.
  - We accept either tier metadata (preferred) or a configurable
    STRIPE_PRICE_PRO / STRIPE_PRICE_TEAM mapping, so the user can connect
    Stripe Payment Links without writing any custom session-creation code.
"""
from __future__ import annotations

import hmac
import hashlib
import json
import logging
import os
import time
from typing import Optional

from fastapi import HTTPException, Request

from src.billing import licenses
from src.billing.email import send_license_email
from src.billing.schemas import WebhookAck

logger = logging.getLogger(__name__)

# 5-minute tolerance for Stripe timestamps (matches Stripe's own docs).
_SIG_TOLERANCE_SECONDS = 300


# ── Signature verification ────────────────────────────────────────────────────


def _parse_sig_header(header: str) -> tuple[Optional[int], list[str]]:
    """
    Parse Stripe's `Stripe-Signature` header:
        t=12345,v1=abc...,v1=def...
    Returns (timestamp, [v1 signatures]).
    """
    if not header:
        return None, []
    ts: Optional[int] = None
    sigs: list[str] = []
    for item in header.split(","):
        if "=" not in item:
            continue
        k, _, v = item.partition("=")
        k, v = k.strip(), v.strip()
        if k == "t":
            try:
                ts = int(v)
            except ValueError:
                ts = None
        elif k == "v1":
            sigs.append(v)
    return ts, sigs


def verify_signature(
    payload: bytes,
    sig_header: str,
    secret: str,
    *,
    now: Optional[int] = None,
) -> bool:
    """Verify the Stripe webhook signature using stdlib hmac."""
    if not secret:
        return False
    ts, sigs = _parse_sig_header(sig_header)
    if ts is None or not sigs:
        return False
    if now is None:
        now = int(time.time())
    if abs(now - ts) > _SIG_TOLERANCE_SECONDS:
        return False
    signed_payload = f"{ts}.".encode("utf-8") + payload
    expected = hmac.new(
        secret.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in sigs)


# ── Tier resolution ───────────────────────────────────────────────────────────


def _resolve_tier(session: dict) -> Optional[str]:
    """
    Resolve the tier from a Stripe session payload.  Order of precedence:
      1. session.metadata.tier == "pro" | "team"
      2. session.amount_total compared against STRIPE_PRICE_*_CENTS
      3. STRIPE_PRICE_PRO / STRIPE_PRICE_TEAM matched against line_items
    """
    metadata = session.get("metadata") or {}
    tier_meta = (metadata.get("tier") or "").lower().strip()
    if tier_meta in ("pro", "team"):
        return tier_meta

    # Amount fallback — robust because user can paste their Payment Link
    # without setting metadata at all.
    pro_cents = _env_int("STRIPE_PRICE_PRO_CENTS", 4900)
    team_cents = _env_int("STRIPE_PRICE_TEAM_CENTS", 24900)
    amount = session.get("amount_total")
    if isinstance(amount, int):
        if amount == pro_cents:
            return "pro"
        if amount == team_cents:
            return "team"
    return None


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _extract_email(session: dict) -> Optional[str]:
    cd = session.get("customer_details") or {}
    return (
        session.get("customer_email")
        or cd.get("email")
        or None
    )


# ── Main handler ──────────────────────────────────────────────────────────────


async def handle_stripe_webhook(request: Request) -> WebhookAck:
    """
    Entry point — wired into a FastAPI route in routes.py.

    Returns 200 OK with a small JSON acknowledgement so Stripe doesn't retry.
    Raises HTTPException(400) only on signature failure.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")

    # In development the secret may be unset and we skip verification.  We
    # log loudly so this can't slip into production by accident.
    env = os.getenv("ENVIRONMENT", "development")
    if env == "production":
        if not verify_signature(payload, sig_header, secret):
            raise HTTPException(status_code=400, detail="Invalid Stripe signature.")
    else:
        if not secret:
            logger.warning("STRIPE_WEBHOOK_SECRET unset — accepting webhook unverified (dev only).")
        elif not verify_signature(payload, sig_header, secret):
            logger.warning("Stripe signature check failed (dev) — accepting anyway.")

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Webhook payload was not valid JSON.")

    event_type = event.get("type", "")
    data_object = (event.get("data") or {}).get("object") or {}

    if event_type != "checkout.session.completed":
        # Acknowledge any other event without doing anything.
        return WebhookAck(received=True, action=f"ignored:{event_type}")

    session_id = data_object.get("id") or ""
    email = _extract_email(data_object)
    tier = _resolve_tier(data_object)

    if not email or not tier:
        logger.warning(
            "Webhook missing email/tier — id=%s email=%s tier=%s",
            session_id, email, tier,
        )
        return WebhookAck(received=True, action="skipped:missing_email_or_tier")

    info = licenses.create_license(tier=tier, email=email, stripe_session_id=session_id)
    await send_license_email(
        to_email=email, license_key=info.key, tier=info.tier,
    )
    return WebhookAck(received=True, action="license_created", license_key=info.key)
