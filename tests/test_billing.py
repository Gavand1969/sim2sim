"""
Tests for src/billing/* — license generation, activation, status, webhook
signature verification, and the end-to-end webhook → license-creation flow.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ── Shared fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """
    Every test gets its own SQLite file plus a known license secret.
    We also force development-mode env so dev bypasses don't trip prod paths.
    """
    db_file = tmp_path / "test_sim2sim.db"
    monkeypatch.setenv("SIM2SIM_DB", str(db_file))
    monkeypatch.setenv("SIM2SIM_LICENSE_SECRET", "test-secret-key")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_secret")
    # Disable Resend so tests never make network calls.
    monkeypatch.delenv("RESEND_API_KEY", raising=False)

    # Re-init the DB module against the new path.
    from src.billing import db
    db.init_db()
    yield
    if db_file.exists():
        db_file.unlink()


@pytest.fixture
def client():
    # main.py reads env at import time for CORS, so we re-import to pick up env.
    import importlib
    import main as main_mod
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


# ── Key generation + validation ───────────────────────────────────────────────


class TestKeyFormat:
    def test_generate_pro_key_format(self):
        from src.billing import licenses
        key = licenses.generate_key("pro")
        assert key.startswith("LIC-")
        parts = key.split("-")
        assert len(parts) == 5
        assert all(len(p) == 4 for p in parts[1:])

    def test_generate_team_key_format(self):
        from src.billing import licenses
        key = licenses.generate_key("team")
        assert licenses._key_is_well_formed(key)

    def test_generate_invalid_tier_raises(self):
        from src.billing import licenses
        with pytest.raises(ValueError):
            licenses.generate_key("enterprise")

    def test_keys_are_unique(self):
        from src.billing import licenses
        keys = {licenses.generate_key("pro") for _ in range(50)}
        assert len(keys) == 50

    def test_malformed_key_rejected(self):
        from src.billing import licenses
        assert not licenses._key_is_well_formed("not-a-key")
        assert not licenses._key_is_well_formed("LIC-XXXX")
        assert not licenses._key_is_well_formed("LIC-XXXX-XXXX-XXXX-XXXX-XXXX")
        # 'I' is not in our alphabet
        assert not licenses._key_is_well_formed("LIC-IIII-IIII-IIII-IIII")


# ── Create / validate / activate licenses ─────────────────────────────────────


class TestLicenseLifecycle:
    def test_create_and_validate_pro(self):
        from src.billing import licenses
        info = licenses.create_license(tier="pro", email="a@b.com")
        validated = licenses.validate_license(info.key)
        assert validated is not None
        assert validated.tier == "pro"
        assert validated.email == "a@b.com"

    def test_create_idempotent_on_session_id(self):
        from src.billing import licenses
        first = licenses.create_license(
            tier="pro", email="a@b.com", stripe_session_id="cs_test_1",
        )
        second = licenses.create_license(
            tier="pro", email="a@b.com", stripe_session_id="cs_test_1",
        )
        assert first.key == second.key

    def test_unknown_key_fails_validation(self):
        from src.billing import licenses
        assert licenses.validate_license("LIC-0000-0000-0000-0000") is None

    def test_activate_records_count(self):
        from src.billing import licenses
        info = licenses.create_license(tier="pro", email="a@b.com")
        assert info.activation_count == 0
        a = licenses.activate_license(info.key)
        assert a is not None and a.activation_count == 1
        b = licenses.activate_license(info.key)
        assert b is not None and b.activation_count == 2


# ── HTTP: activate / status ───────────────────────────────────────────────────


class TestBillingEndpoints:
    def test_activate_valid_key(self, client):
        from src.billing import licenses
        info = licenses.create_license(tier="pro", email="paid@example.com")
        resp = client.post("/api/billing/activate", json={"key": info.key})
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["tier"] == "pro"
        assert body["email"] == "paid@example.com"

    def test_activate_invalid_key(self, client):
        resp = client.post(
            "/api/billing/activate",
            json={"key": "LIC-ZZZZ-ZZZZ-ZZZZ-ZZZZ"},
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is False

    def test_status_with_valid_header(self, client):
        from src.billing import licenses
        info = licenses.create_license(tier="team", email="t@example.com")
        resp = client.get("/api/billing/status", headers={"X-License-Key": info.key})
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is True
        assert body["tier"] == "team"

    def test_status_without_header(self, client):
        resp = client.get("/api/billing/status")
        assert resp.status_code == 200
        assert resp.json()["valid"] is False


# ── HTTP: Pro gate honours real keys ──────────────────────────────────────────


class TestProGate:
    """Make sure export endpoints accept a real Pro key (not just 'dev')."""

    def test_export_with_real_pro_key(self, client, monkeypatch):
        # Force non-dev gating so the dev bypass is OFF.
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ALLOWED_ORIGIN", "https://example.com")

        # Re-import main with prod env.
        import importlib
        import main as main_mod
        importlib.reload(main_mod)
        prod_client = TestClient(main_mod.app)

        from src.billing import licenses
        info = licenses.create_license(tier="pro", email="paid@example.com")

        # Bogus key → 403
        body = {
            "result": {
                "model": "M/M/1", "utilization": 0.5, "L": 1.0, "Lq": 0.5,
                "W": 1.0, "Wq": 0.5, "P0": 0.5, "P_wait": 0.5,
                "prob_dist": [], "little_law_check": True,
            },
            "params": {"arrival_rate": 1.0, "service_rate": 2.0},
        }
        bogus = prod_client.post(
            "/api/export/queuing/xlsx", json=body,
            headers={"X-License-Key": "LIC-0000-0000-0000-0000"},
        )
        assert bogus.status_code == 403

        # Real key → 200 with xlsx mime type
        good = prod_client.post(
            "/api/export/queuing/xlsx", json=body,
            headers={"X-License-Key": info.key},
        )
        assert good.status_code == 200
        assert "spreadsheetml" in good.headers.get("content-type", "")


# ── Webhook signature verification ────────────────────────────────────────────


def _sign(payload: bytes, secret: str, ts: int) -> str:
    signed = f"{ts}.".encode("utf-8") + payload
    sig = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


class TestWebhookSignature:
    def test_valid_signature(self):
        from src.billing.webhook import verify_signature
        secret = "whsec_test_secret"
        payload = b'{"hello":"world"}'
        ts = int(time.time())
        header = _sign(payload, secret, ts)
        assert verify_signature(payload, header, secret, now=ts) is True

    def test_tampered_payload_fails(self):
        from src.billing.webhook import verify_signature
        secret = "whsec_test_secret"
        ts = int(time.time())
        header = _sign(b'{"hello":"world"}', secret, ts)
        assert verify_signature(b'{"hello":"evil"}', header, secret, now=ts) is False

    def test_stale_timestamp_fails(self):
        from src.billing.webhook import verify_signature
        secret = "whsec_test_secret"
        old_ts = int(time.time()) - 3600
        header = _sign(b"{}", secret, old_ts)
        assert verify_signature(b"{}", header, secret, now=int(time.time())) is False

    def test_missing_signature_fails(self):
        from src.billing.webhook import verify_signature
        assert verify_signature(b"{}", "", "secret", now=1) is False


# ── End-to-end webhook flow ───────────────────────────────────────────────────


class TestWebhookFlow:
    def _build_event(self, *, amount_total: int = 4900, email: str = "buyer@example.com"):
        return {
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_test_abc123",
                "amount_total": amount_total,
                "customer_details": {"email": email},
                "metadata": {},
            }},
        }

    def test_pro_purchase_creates_license(self, client):
        evt = self._build_event(amount_total=4900)
        payload = json.dumps(evt).encode("utf-8")
        ts = int(time.time())
        header = _sign(payload, "whsec_test_secret", ts)

        resp = client.post(
            "/api/billing/webhook",
            content=payload,
            headers={
                "stripe-signature": header,
                "content-type": "application/json",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["action"] == "license_created"
        assert body["license_key"].startswith("LIC-")

        # The license now validates.
        from src.billing import licenses
        info = licenses.validate_license(body["license_key"])
        assert info is not None and info.tier == "pro"

    def test_team_purchase_creates_team_license(self, client):
        evt = self._build_event(amount_total=24900, email="team@example.com")
        payload = json.dumps(evt).encode("utf-8")
        ts = int(time.time())
        header = _sign(payload, "whsec_test_secret", ts)
        resp = client.post(
            "/api/billing/webhook",
            content=payload,
            headers={"stripe-signature": header},
        )
        assert resp.status_code == 200
        assert resp.json()["action"] == "license_created"
        from src.billing import licenses
        info = licenses.validate_license(resp.json()["license_key"])
        assert info is not None and info.tier == "team"

    def test_webhook_idempotent(self, client):
        evt = self._build_event(amount_total=4900)
        payload = json.dumps(evt).encode("utf-8")
        ts = int(time.time())
        header = _sign(payload, "whsec_test_secret", ts)

        r1 = client.post("/api/billing/webhook", content=payload,
                         headers={"stripe-signature": header})
        r2 = client.post("/api/billing/webhook", content=payload,
                         headers={"stripe-signature": header})
        assert r1.json()["license_key"] == r2.json()["license_key"]

    def test_webhook_ignores_unknown_event(self, client):
        evt = {"type": "customer.created", "data": {"object": {}}}
        payload = json.dumps(evt).encode("utf-8")
        ts = int(time.time())
        header = _sign(payload, "whsec_test_secret", ts)
        resp = client.post("/api/billing/webhook", content=payload,
                           headers={"stripe-signature": header})
        assert resp.status_code == 200
        assert resp.json()["action"].startswith("ignored:")

    def test_webhook_skips_when_email_missing(self, client):
        evt = {
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_test_no_email", "amount_total": 4900,
                "customer_details": {}, "metadata": {},
            }},
        }
        payload = json.dumps(evt).encode("utf-8")
        ts = int(time.time())
        header = _sign(payload, "whsec_test_secret", ts)
        resp = client.post("/api/billing/webhook", content=payload,
                           headers={"stripe-signature": header})
        assert resp.json()["action"] == "skipped:missing_email_or_tier"

    def test_webhook_tier_via_metadata(self, client):
        evt = {
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_test_meta", "amount_total": 9999,
                "customer_details": {"email": "meta@example.com"},
                "metadata": {"tier": "team"},
            }},
        }
        payload = json.dumps(evt).encode("utf-8")
        ts = int(time.time())
        header = _sign(payload, "whsec_test_secret", ts)
        resp = client.post("/api/billing/webhook", content=payload,
                           headers={"stripe-signature": header})
        assert resp.json()["action"] == "license_created"
        from src.billing import licenses
        info = licenses.validate_license(resp.json()["license_key"])
        assert info.tier == "team"
