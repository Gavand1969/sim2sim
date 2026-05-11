"""
Unit tests for EOQ and Newsvendor inventory models.
"""
import math
import pytest
from src.models.inventory import solve_eoq, solve_newsvendor


class TestEOQ:
    def test_basic_correctness(self):
        """Wilson formula: EOQ = sqrt(2KD/h)."""
        D, K, c, i = 10_000, 200, 50, 0.25
        h = i * c  # = 12.5
        expected_eoq = math.sqrt(2 * K * D / h)
        r = solve_eoq(D=D, K=K, c=c, i=i)
        assert r.eoq == pytest.approx(expected_eoq, rel=1e-6)

    def test_total_cost_formula(self):
        """TC* = sqrt(2KDh)."""
        D, K, c, i = 5_000, 100, 20, 0.30
        h = i * c
        r = solve_eoq(D=D, K=K, c=c, i=i)
        assert r.total_annual_cost == pytest.approx(math.sqrt(2 * K * D * h), rel=1e-4)

    def test_ordering_equals_holding_at_eoq(self):
        """At EOQ, ordering cost = holding cost (fundamental property)."""
        D, K, c, i = 8_000, 150, 40, 0.20
        r = solve_eoq(D=D, K=K, c=c, i=i)
        h = i * c
        ordering = K * D / r.eoq
        holding  = h * r.eoq / 2
        assert ordering == pytest.approx(holding, rel=1e-4)

    def test_cost_curve_minimum_at_eoq(self):
        """The cost curve minimum should be at or very near the EOQ."""
        r = solve_eoq(D=10_000, K=200, c=50, i=0.25)
        q_vals = r.cost_curve_q
        tc_vals = r.cost_curve_tc
        min_idx = tc_vals.index(min(tc_vals))
        q_at_min = q_vals[min_idx]
        assert q_at_min == pytest.approx(r.eoq, rel=0.05)  # within 5%

    def test_orders_per_year(self):
        D = 10_000
        r = solve_eoq(D=D, K=200, c=50, i=0.25)
        assert r.orders_per_year == pytest.approx(D / r.eoq, rel=1e-5)

    def test_cycle_time_days(self):
        r = solve_eoq(D=10_000, K=200, c=50, i=0.25)
        assert r.cycle_time_days == pytest.approx(365 / r.orders_per_year, rel=1e-4)

    def test_cost_curve_has_correct_length(self):
        r = solve_eoq(D=1_000, K=50, c=10, i=0.20)
        assert len(r.cost_curve_q) == len(r.cost_curve_tc) == 200


class TestNewsvendor:
    # Normal distribution tests
    def test_normal_critical_ratio(self):
        """CR = (p-c)/(p-s)."""
        r = solve_newsvendor(p=100, c=60, s=20, demand_mean=500, demand_std=100)
        expected_cr = (100 - 60) / (100 - 20)
        assert r.critical_ratio == pytest.approx(expected_cr, rel=1e-6)

    def test_normal_optimal_quantity_above_mean_when_cr_above_half(self):
        """If CR >= 0.5 the optimal Q should be >= demand mean."""
        # p=100, c=60, s=20 → CR = (100-60)/(100-20) = 0.5 exactly
        r = solve_newsvendor(p=100, c=60, s=20, demand_mean=500, demand_std=100)
        assert r.critical_ratio >= 0.5
        assert r.optimal_quantity >= 500
        # Confirm with a strictly profitable margin: CR > 0.5 → Q > mu
        r2 = solve_newsvendor(p=120, c=60, s=20, demand_mean=500, demand_std=100)
        assert r2.critical_ratio > 0.5
        assert r2.optimal_quantity > 500

    def test_normal_expected_sales_le_mean_demand(self):
        """E[min(D,Q)] ≤ E[D] always."""
        r = solve_newsvendor(p=100, c=60, s=20, demand_mean=500, demand_std=100)
        assert r.expected_sales <= 500 + 1e-6  # tiny tolerance for float

    def test_normal_mass_balance(self):
        """E[sales] + E[leftover] ≈ Q*."""
        r = solve_newsvendor(p=100, c=60, s=20, demand_mean=500, demand_std=100)
        assert r.expected_sales + r.expected_leftover == pytest.approx(r.optimal_quantity, rel=1e-3)

    def test_normal_fill_rate_range(self):
        r = solve_newsvendor(p=100, c=60, s=20, demand_mean=500, demand_std=100)
        assert 0.0 <= r.fill_rate <= 1.0

    def test_normal_high_margin_high_service_level(self):
        """High margin (p >> c) → high CR → order more → high fill rate."""
        r_high = solve_newsvendor(p=200, c=10, s=0,  demand_mean=100, demand_std=20)
        r_low  = solve_newsvendor(p=100, c=90, s=0,  demand_mean=100, demand_std=20)
        assert r_high.critical_ratio > r_low.critical_ratio
        assert r_high.optimal_quantity > r_low.optimal_quantity

    # Poisson distribution tests
    def test_poisson_optimal_quantity_is_integer(self):
        r = solve_newsvendor(p=100, c=60, s=20, demand_mean=50, demand_std=50, dist='poisson')
        assert r.optimal_quantity == float(int(r.optimal_quantity))

    def test_poisson_cr_range(self):
        r = solve_newsvendor(p=50, c=20, s=5, demand_mean=30, demand_std=30, dist='poisson')
        assert 0.0 < r.critical_ratio < 1.0

    # Uniform distribution tests
    def test_uniform_cr(self):
        r = solve_newsvendor(p=100, c=60, s=20, demand_mean=500, demand_std=100, dist='uniform')
        expected_cr = (100 - 60) / (100 - 20)
        assert r.critical_ratio == pytest.approx(expected_cr, rel=1e-6)

    # Validation tests
    def test_invalid_cost_exceeds_price(self):
        with pytest.raises(ValueError, match="selling_price must be greater than unit_cost"):
            solve_newsvendor(p=50, c=60, s=0, demand_mean=100, demand_std=20)

    def test_invalid_salvage_exceeds_cost(self):
        with pytest.raises(ValueError, match="unit_cost must be greater than salvage_value"):
            solve_newsvendor(p=100, c=40, s=50, demand_mean=100, demand_std=20)
