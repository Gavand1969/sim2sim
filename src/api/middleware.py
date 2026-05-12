"""
Security middleware: rate limiting + HTTP security headers.

Rate limiting uses slowapi (Starlette-compatible limiter backed by in-memory
storage). For multi-process production you'd swap the storage for Redis, but
for a single-process Replit deployment in-memory is correct.
"""
import os

from fastapi import Request
from fastapi.responses import Response
from slowapi import Limiter

_rate = os.getenv("RATE_LIMIT_PER_MINUTE", "60")


def _client_ip(request: Request) -> str:
    """
    Return the real client IP behind DigitalOcean's load balancer.

    DO App Platform sets `X-Forwarded-For: <client>, <internal-proxy>`. We take
    the first entry (the original client). Without this, slowapi keys on the
    proxy IP and all users share one bucket -> everyone gets rate-limited at
    once. Falls back to the direct peer if no XFF header is present.
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


limiter = Limiter(
    key_func=_client_ip,
    default_limits=[f"{_rate}/minute"],
    # /api/billing/status is polled by the SPA on every page load. We still
    # rate-limit it but at a much higher per-IP threshold so legitimate use
    # never trips the limiter, while abusive enumeration still gets blocked.
)


def add_security_headers(response: Response) -> None:
    """
    Attach defence-in-depth HTTP headers to every response.

    - Content-Security-Policy: restricts what resources the browser will load.
      We allow CDN scripts/styles by their known hostnames only — no 'unsafe-inline'
      for scripts (Chart.js is loaded via defer, no inline handlers).
    - X-Content-Type-Options: prevents MIME-type sniffing attacks.
    - X-Frame-Options: blocks clickjacking.
    - Referrer-Policy: limits information leakage in the Referer header.
    - Permissions-Policy: disables browser APIs the app never uses.
    """
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "geolocation=(), microphone=(), camera=(), payment=()"
    )
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' https://fonts.googleapis.com https://cdn.jsdelivr.net 'unsafe-inline'; "
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net data:; "
        "img-src 'self' https://cdn.jsdelivr.net data: blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
