# src/billing/licenses.py (stub — real implementation in another branch)
from fastapi import Header, HTTPException


async def require_pro(x_license_key: str = Header(default="")) -> str:
    # In dev, accept the bypass key
    import os
    if os.getenv("ENVIRONMENT", "development") == "development" and x_license_key in ("dev", ""):
        return "dev"
    # Real validation will be added later
    if not x_license_key:
        raise HTTPException(403, "Pro license key required")
    return x_license_key
