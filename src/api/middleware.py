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
from slowapi.util import get_remote_address

_rate = os.getenv("RATE_LIMIT_PER_MINUTE", "20")

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{_rate}/minute"],
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
        "style-src 'self' https://fonts.googleapis.com 'unsafe-inline'; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
