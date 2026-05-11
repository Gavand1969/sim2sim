"""
Integration tests for FastAPI endpoints.
Tests run against TestClient (no live server needed).
"""
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app, raise_server_exceptions=True)


class TestHealth:
    def test_health_ok(self):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestQueuingEndpoint:
    def test_mm1_valid(self):
        r = client.post("/api/queuing", json={
            "model": "MM1",
            "arrival_rate": 4.0,
            "service_rate": 6.0,
        })
        assert r.status_code == 200
        data = r.json()
        assert "utilization" in data
        assert "L" in data
        assert data["little_law_check"] < 1e-9

    def test_mmc_valid(self):
        r = client.post("/api/queuing", json={
            "model": "MMC",
            "arrival_rate": 8.0,
            "service_rate": 5.0,
            "num_servers": 3,
        })
        assert r.status_code == 200
        assert r.json()["P_wait"] is not None

    def test_md1_valid(self):
        r = client.post("/api/queuing", json={
            "model": "MD1",
            "arrival_rate": 3.0,
            "service_rate": 5.0,
        })
        assert r.status_code == 200

    def test_mg1_valid(self):
        r = client.post("/api/queuing", json={
            "model": "MG1",
            "arrival_rate": 4.0,
            "service_rate": 6.0,
            "service_cv_sq": 2.0,
        })
        assert r.status_code == 200

    def test_unstable_system_rejected(self):
        r = client.post("/api/queuing", json={
            "model": "MM1",
            "arrival_rate": 10.0,
            "service_rate": 5.0,
        })
        # Pydantic catches it at model_validator level → 422
        assert r.status_code == 422

    def test_negative_arrival_rate_rejected(self):
        r = client.post("/api/queuing", json={
            "model": "MM1",
            "arrival_rate": -1.0,
            "service_rate": 5.0,
        })
        assert r.status_code == 422

    def test_zero_service_rate_rejected(self):
        r = client.post("/api/queuing", json={
            "model": "MM1",
            "arrival_rate": 1.0,
            "service_rate": 0.0,
        })
        assert r.status_code == 422


class TestEOQEndpoint:
    def test_eoq_valid(self):
        r = client.post("/api/inventory/eoq", json={
            "annual_demand": 10000,
            "ordering_cost": 200,
            "unit_cost": 50,
            "holding_rate": 0.25,
        })
        assert r.status_code == 200
        data = r.json()
        assert "eoq" in data
        assert data["eoq"] > 0

    def test_eoq_cost_curve_lengths_match(self):
        r = client.post("/api/inventory/eoq", json={
            "annual_demand": 5000,
            "ordering_cost": 100,
            "unit_cost": 20,
            "holding_rate": 0.20,
        })
        data = r.json()
        assert len(data["cost_curve_q"]) == len(data["cost_curve_tc"])

    def test_eoq_negative_demand_rejected(self):
        r = client.post("/api/inventory/eoq", json={
            "annual_demand": -100,
            "ordering_cost": 200,
            "unit_cost": 50,
            "holding_rate": 0.25,
        })
        assert r.status_code == 422


class TestNewsvendorEndpoint:
    def test_newsvendor_normal_valid(self):
        r = client.post("/api/inventory/newsvendor", json={
            "selling_price": 100,
            "unit_cost": 60,
            "salvage_value": 20,
            "demand_mean": 500,
            "demand_std": 100,
        })
        assert r.status_code == 200
        data = r.json()
        assert 0 < data["critical_ratio"] < 1
        assert data["optimal_quantity"] > 0

    def test_newsvendor_invalid_cost_rejected(self):
        r = client.post("/api/inventory/newsvendor", json={
            "selling_price": 50,
            "unit_cost": 70,   # cost > price
            "salvage_value": 10,
            "demand_mean": 100,
            "demand_std": 20,
        })
        assert r.status_code == 422


class TestSimulationEndpoint:
    def test_simulation_valid(self):
        r = client.post("/api/simulation", json={
            "model": "MM1",
            "arrival_rate": 4.0,
            "service_rate": 6.0,
            "num_customers": 500,
            "num_replications": 3,
            "seed": 42,
        })
        assert r.status_code == 200
        data = r.json()
        assert "W_mean" in data
        assert "W_ci_hw" in data
        assert data["utilization_mean"] == pytest.approx(4/6, abs=0.15)  # loose for short run

    def test_simulation_seeded_reproducible(self):
        payload = {
            "model": "MM1",
            "arrival_rate": 3.0,
            "service_rate": 5.0,
            "num_customers": 500,
            "num_replications": 2,
            "seed": 99,
        }
        r1 = client.post("/api/simulation", json=payload)
        r2 = client.post("/api/simulation", json=payload)
        assert r1.json()["W_mean"] == r2.json()["W_mean"]

    def test_simulation_unstable_rejected(self):
        r = client.post("/api/simulation", json={
            "model": "MM1",
            "arrival_rate": 10.0,
            "service_rate": 5.0,
            "num_customers": 1000,
            "num_replications": 2,
        })
        assert r.status_code == 422


class TestSecurityHeaders:
    def test_security_headers_present(self):
        r = client.get("/api/health")
        assert "x-content-type-options" in r.headers
        assert r.headers["x-content-type-options"] == "nosniff"
        assert "x-frame-options" in r.headers
        assert r.headers["x-frame-options"] == "DENY"
        assert "content-security-policy" in r.headers

    def test_frontend_served(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
