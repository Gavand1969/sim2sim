"""
Transactional email via Resend (https://resend.com).

Resend was chosen because:
  - Single HTTPS POST, no SDK required (we use httpx).
  - Free tier of 100 emails/day is plenty for a paid-MVP launch.
  - Their API stays stable, so a generic httpx client is low-risk.

If RESEND_API_KEY is unset (typical in dev), `send_license_email` returns
a synthetic result with `delivered=False` and a reason — we do NOT raise,
because we never want a failed email to block a paid customer's webhook.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"


@dataclass
class EmailResult:
    delivered: bool
    provider_id: Optional[str] = None
    error: Optional[str] = None


def _from_address() -> str:
    return os.getenv("RESEND_FROM", "Sim2Sim <onboarding@resend.dev>")


def _build_license_html(license_key: str, tier: str, app_url: str) -> str:
    tier_label = "Team" if tier == "team" else "Pro"
    return f"""<!doctype html>
<html><body style="font-family: -apple-system, Segoe UI, sans-serif; color:#0f172a; max-width:560px; margin:0 auto; padding:32px 24px;">
  <h1 style="font-size:22px; margin:0 0 8px;">Thanks for buying Sim2Sim {tier_label}.</h1>
  <p style="font-size:15px; line-height:1.6; color:#334155;">
    Your lifetime license key is below. Paste it into the
    <a href="{app_url}/account" style="color:#2563eb; text-decoration:none;">Account page</a>
    on Sim2Sim and your account unlocks immediately.
  </p>
  <div style="font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size:18px;
              background:#0f172a; color:#f8fafc; padding:16px 20px; border-radius:8px;
              letter-spacing:0.5px; text-align:center; margin:20px 0;">
    {license_key}
  </div>
  <p style="font-size:14px; line-height:1.6; color:#475569;">
    Keep this email — your key never expires. If you switch browsers or devices,
    paste the same key on the account page to unlock {tier_label} again.
  </p>
  <p style="font-size:13px; color:#64748b; margin-top:32px;">
    Reply to this email if anything looks off.
  </p>
</body></html>"""


async def send_license_email(
    to_email: str,
    license_key: str,
    tier: str,
    app_url: Optional[str] = None,
) -> EmailResult:
    """Send a license-delivery email.  Never raises — returns EmailResult."""
    api_key = os.getenv("RESEND_API_KEY", "")
    if not api_key:
        logger.warning("RESEND_API_KEY not set — skipping license email to %s", to_email)
        return EmailResult(delivered=False, error="RESEND_API_KEY not configured")

    app_url = app_url or os.getenv("APP_BASE_URL", "https://sim2sim.app")
    payload = {
        "from": _from_address(),
        "to": [to_email],
        "subject": f"Your Sim2Sim {('Team' if tier == 'team' else 'Pro')} license key",
        "html": _build_license_html(license_key, tier, app_url),
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _RESEND_URL,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        if resp.status_code >= 400:
            logger.error("Resend %s: %s", resp.status_code, resp.text[:200])
            return EmailResult(delivered=False, error=f"HTTP {resp.status_code}")
        data = resp.json()
        return EmailResult(delivered=True, provider_id=data.get("id"))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Resend send failed")
        return EmailResult(delivered=False, error=str(exc))
