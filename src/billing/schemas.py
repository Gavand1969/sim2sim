"""Pydantic schemas for the billing endpoints."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ActivateRequest(BaseModel):
    """POST /api/billing/activate body."""
    key: str = Field(..., min_length=1, max_length=64, description="License key to activate")


class ActivateResponse(BaseModel):
    valid: bool
    tier: Optional[str] = None
    email: Optional[str] = None
    activated_at: Optional[str] = None
    message: Optional[str] = None


class LicenseStatusResponse(BaseModel):
    """GET /api/billing/status response."""
    valid: bool
    tier: Optional[str] = None
    email: Optional[str] = None
    activation_count: Optional[int] = None
    message: Optional[str] = None


class WebhookAck(BaseModel):
    received: bool
    action: str
    license_key: Optional[str] = None
