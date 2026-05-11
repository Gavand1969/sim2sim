"""
Unit tests for queuing model analytical solutions.

Tests verify correctness against known textbook values and internal
consistency (Little's Law, stability conditions, probability sums).
"""
import math
import pytest
from src.models.queuing import solve_mm1, solve_mmc, solve_md1, solve_mg1, solve_queue


class TestMM1:
    def test_basic_correctness(self):
        r = solve_mm1(lam=4.0, mu=6.0)
        assert r.utilization == pytest.approx(4/6, rel=1e-6)
        assert r.L  == pytest.approx((4/6) / (1 - 4/6), rel=1e-6)
        assert r.Lq == pytest.approx((4/6)**2 / (1 - 4/6), rel=1e-6)
        assert r.W  == pytest.approx(1 / (6 - 4), rel=1e-6)
        assert r.Wq == pytest.approx(4 / (6 * (6 - 4)), rel=1e-6)

    def test_littles_law(self):
        r = solve_mm1(lam=3.0, mu=5.0)
        # L = λ * W
        assert abs(r.L - 3.0 * r.W) < 1e-10
        # Lq = λ * Wq
        assert abs(r.Lq - 3.0 * r.Wq) < 1e-10

    def test_prob_sum_to_one(self):
        r = solve_mm1(lam=2.0, mu=5.0)
        # Geometric series: sum_{n=0}^{inf} = 1; our 21 terms should be close to 1
        # for low utilisation
        assert sum(r.prob_dist) == pytest.approx(1.0, rel=0.02)

    def test_p0_equals_1_minus_rho(self):
        r = solve_mm1(lam=1.0, mu=4.0)
        assert r.P0 == pytest.approx(1 - 1/4, rel=1e-10)

    def test_little_law_check_near_zero(self):
        r = solve_mm1(lam=5.0, mu=8.0)
        assert r.little_law_check < 1e-10

    def test_high_utilisation(self):
        r = solve_mm1(lam=9.9, mu=10.0)
        assert r.utilization == pytest.approx(0.99, rel=1e-4)
        assert r.Lq > 10   # queue blows up near saturation

    def test_model_label(self):
        assert solve_mm1(1, 2).model == "M/M/1"


class TestMMC:
    def test_mmc_reduces_to_mm1_when_c1(self):
        r1 = solve_mmc(lam=4.0, mu=6.0, c=1)
        r2 = solve_mm1(lam=4.0, mu=6.0)
        assert r1.L  == pytest.approx(r2.L,  rel=1e-5)
        assert r1.Lq == pytest.approx(r2.Lq, rel=1e-5)
        assert r1.W  == pytest.approx(r2.W,  rel=1e-5)

    def test_mmc_utilisation(self):
        r = solve_mmc(lam=8.0, mu=5.0, c=3)
        assert r.utilization == pytest.approx(8 / (3 * 5), rel=1e-6)

    def test_mmc_p_wait_range(self):
        r = solve_mmc(lam=4.0, mu=6.0, c=2)
        assert 0.0 <= r.P_wait <= 1.0

    def test_mmc_littles_law(self):
        r = solve_mmc(lam=6.0, mu=4.0, c=3)
        assert abs(r.L - 6.0 * r.W) < 1e-8

    def test_mmc_more_servers_reduces_wait(self):
        r1 = solve_mmc(lam=8.0, mu=5.0, c=2)
        r2 = solve_mmc(lam=8.0, mu=5.0, c=3)
        assert r1.Wq > r2.Wq


class TestMD1:
    def test_half_queue_vs_mm1(self):
        """M/D/1 Lq should be exactly half of M/M/1 Lq (same λ, μ)."""
        lam, mu = 3.0, 5.0
        r_mm1 = solve_mm1(lam, mu)
        r_md1 = solve_md1(lam, mu)
        assert r_md1.Lq == pytest.approx(r_mm1.Lq / 2, rel=1e-6)

    def test_md1_littles_law(self):
        r = solve_md1(lam=2.0, mu=4.0)
        assert abs(r.L - 2.0 * r.W) < 1e-10

    def test_md1_model_label(self):
        assert solve_md1(1, 2).model == "M/D/1"


class TestMG1:
    def test_mg1_cs2_1_equals_mm1(self):
        """M/G/1 with Cs²=1 is equivalent to M/M/1 (P-K formula)."""
        r_mg1 = solve_mg1(lam=4.0, mu=6.0, cs_sq=1.0)
        r_mm1 = solve_mm1(lam=4.0, mu=6.0)
        assert r_mg1.Lq == pytest.approx(r_mm1.Lq, rel=1e-6)
        assert r_mg1.W  == pytest.approx(r_mm1.W,  rel=1e-6)

    def test_mg1_cs2_0_equals_md1(self):
        """M/G/1 with Cs²=0 is equivalent to M/D/1."""
        r_mg1 = solve_mg1(lam=3.0, mu=5.0, cs_sq=0.0)
        r_md1 = solve_md1(lam=3.0, mu=5.0)
        assert r_mg1.Lq == pytest.approx(r_md1.Lq, rel=1e-6)

    def test_mg1_higher_variance_means_longer_queue(self):
        """Higher service variance → longer queue (variance amplification)."""
        r_low  = solve_mg1(lam=4.0, mu=6.0, cs_sq=0.5)
        r_high = solve_mg1(lam=4.0, mu=6.0, cs_sq=2.0)
        assert r_high.Lq > r_low.Lq

    def test_mg1_littles_law(self):
        r = solve_mg1(lam=5.0, mu=8.0, cs_sq=1.5)
        assert abs(r.L - 5.0 * r.W) < 1e-10


class TestDispatcher:
    def test_dispatcher_mm1(self):
        r = solve_queue("MM1", lam=2.0, mu=4.0)
        assert r.model == "M/M/1"

    def test_dispatcher_unknown(self):
        with pytest.raises(ValueError, match="Unknown queue model"):
            solve_queue("XYZ", lam=1.0, mu=2.0)
