"""
Inventory models: Economic Order Quantity (EOQ) and the Newsvendor model.

EOQ
---
Classic Wilson formula minimising the sum of fixed ordering cost and linear
holding cost under constant, deterministic demand.

Newsvendor
----------
Single-period stochastic model.  We support Normal, Poisson, and Uniform
demand distributions.  The critical-ratio optimality condition is solved
analytically; all performance measures are computed in closed form (Normal)
or via scipy (Poisson, Uniform).

References
----------
- Zipkin, P. (2000). Foundations of Inventory Management.
- Porteus, E. (2002). Foundations of Stochastic Inventory Theory.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats


# ── EOQ ───────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EOQResult:
    eoq:               float
    orders_per_year:   float
    cycle_time_days:   float
    total_annual_cost: float
    cost_curve_q:      list[float]
    cost_curve_tc:     list[float]
    cost_curve_holding: list[float]
    cost_curve_ordering: list[float]


def solve_eoq(
    D: float,   # annual demand (units/year)
    K: float,   # fixed ordering cost ($/order)
    c: float,   # unit purchase cost ($/unit)
    i: float,   # annual holding rate (fraction of unit cost)
) -> EOQResult:
    """
    Classic EOQ (Wilson formula).

    h = i * c  (holding cost per unit per year)
    Q* = sqrt(2KD / h)
    TC* = sqrt(2KDh)  =  KD/Q* + h*Q*/2
    """
    h    = i * c                        # holding cost per unit per year
    eoq  = math.sqrt(2.0 * K * D / h)
    opy  = D / eoq                      # orders per year
    ct   = 365.0 / opy                  # cycle time in days
    tc   = math.sqrt(2.0 * K * D * h)  # total annual cost at EOQ

    # Cost curve: Q from 1 to 3 * EOQ, 200 points
    q_vals = np.linspace(1.0, 3.0 * eoq, 200)
    holding_costs  = h * q_vals / 2.0
    ordering_costs = K * D / q_vals
    total_costs    = holding_costs + ordering_costs

    return EOQResult(
        eoq=round(eoq, 4),
        orders_per_year=round(opy, 4),
        cycle_time_days=round(ct, 4),
        total_annual_cost=round(tc, 4),
        cost_curve_q=q_vals.tolist(),
        cost_curve_tc=total_costs.tolist(),
        cost_curve_holding=holding_costs.tolist(),
        cost_curve_ordering=ordering_costs.tolist(),
    )


# ── Newsvendor ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class NewsvendorResult:
    critical_ratio:    float
    optimal_quantity:  float
    expected_profit:   float
    expected_sales:    float
    expected_leftover: float
    expected_stockout: float
    fill_rate:         float
    profit_curve_q:    list[float]
    profit_curve_ep:   list[float]


def _normal_newsvendor(
    p: float, c: float, s: float,
    mu: float, sigma: float,
) -> NewsvendorResult:
    """
    Closed-form Newsvendor solution under Normal(mu, sigma) demand.

    Critical ratio: CR = (p - c) / (p - s)
    Optimal Q*:     F(Q*) = CR  =>  Q* = mu + sigma * Phi^{-1}(CR)

    Performance measures (all in closed form using standard Normal):
      E[min(D, Q)] = mu * Phi(z) - sigma * phi(z) + Q * (1 - Phi(z))   [WRONG form below]

    Let z = (Q* - mu) / sigma, phi = std normal PDF, Phi = std normal CDF.

      E[D]           = mu
      E[min(D,Q*)]   = mu - sigma*(phi(z) - z*(1-Phi(z)))   ... "loss function" form
      E[max(Q*-D,0)] = Q* - mu + sigma*(phi(z) - z*(1-Phi(z)))
      E[max(D-Q*,0)] = sigma*(phi(z) - z*(1-Phi(z))) - (Q*-mu) + mu - E[min(D,Q*)]
                     = (mu - Q*)*(1-Phi(z)) + sigma*phi(z)    [standard lost-sales formula]

    E[Profit] = (p - s)*E[min(D,Q*)] - (c - s)*Q*
    """
    cr  = (p - c) / (p - s)
    z   = stats.norm.ppf(cr)
    Q   = mu + sigma * z

    phi_z = stats.norm.pdf(z)
    Phi_z = stats.norm.cdf(z)

    # Standard normal loss function L(z) = phi(z) - z*(1-Phi(z))
    L_z = phi_z - z * (1.0 - Phi_z)

    expected_sales    = mu - sigma * L_z
    expected_leftover = Q - expected_sales
    expected_stockout = sigma * L_z - (Q - mu) * (1.0 - Phi_z)
    # Simplified: E[max(D-Q,0)] = (mu - Q)*(1-Phi(z)) + sigma*phi(z)
    expected_stockout = (mu - Q) * (1.0 - Phi_z) + sigma * phi_z

    expected_profit   = (p - s) * expected_sales - (c - s) * Q
    fill_rate         = expected_sales / mu if mu > 0 else 0.0

    # Profit curve: Q from max(0, mu-3sigma) to mu+4sigma, 200 points
    q_lo = max(0.0, mu - 3 * sigma)
    q_hi = mu + 4 * sigma
    q_vals = np.linspace(q_lo, q_hi, 200)
    profits = []
    for q in q_vals:
        z_q    = (q - mu) / sigma
        L_zq   = stats.norm.pdf(z_q) - z_q * (1.0 - stats.norm.cdf(z_q))
        es     = mu - sigma * L_zq
        ep     = (p - s) * es - (c - s) * q
        profits.append(float(ep))

    return NewsvendorResult(
        critical_ratio=round(cr, 6),
        optimal_quantity=round(Q, 4),
        expected_profit=round(expected_profit, 4),
        expected_sales=round(expected_sales, 4),
        expected_leftover=round(expected_leftover, 4),
        expected_stockout=round(expected_stockout, 4),
        fill_rate=round(min(fill_rate, 1.0), 6),
        profit_curve_q=q_vals.tolist(),
        profit_curve_ep=profits,
    )


def _poisson_newsvendor(
    p: float, c: float, s: float, lam: float,
) -> NewsvendorResult:
    """
    Newsvendor under Poisson(lam) demand.  Optimal Q* is the smallest integer
    satisfying F(Q*) >= CR.
    """
    cr = (p - c) / (p - s)
    dist = stats.poisson(lam)
    Q = int(dist.ppf(cr))

    # All performance measures via pmf/cdf
    d_vals = np.arange(0, max(200, Q * 3))
    pmf    = dist.pmf(d_vals)

    expected_sales    = float(np.sum(np.minimum(d_vals, Q) * pmf))
    expected_leftover = float(np.sum(np.maximum(Q - d_vals, 0) * pmf))
    expected_stockout = float(np.sum(np.maximum(d_vals - Q, 0) * pmf))
    expected_profit   = (p - s) * expected_sales - (c - s) * Q
    fill_rate         = expected_sales / lam if lam > 0 else 0.0

    q_vals = np.arange(0, max(50, Q * 3))
    profits = []
    for q in q_vals:
        es = float(np.sum(np.minimum(d_vals, q) * pmf))
        profits.append((p - s) * es - (c - s) * q)

    return NewsvendorResult(
        critical_ratio=round(cr, 6),
        optimal_quantity=float(Q),
        expected_profit=round(expected_profit, 4),
        expected_sales=round(expected_sales, 4),
        expected_leftover=round(expected_leftover, 4),
        expected_stockout=round(expected_stockout, 4),
        fill_rate=round(min(fill_rate, 1.0), 6),
        profit_curve_q=q_vals.tolist(),
        profit_curve_ep=profits,
    )


def _uniform_newsvendor(
    p: float, c: float, s: float,
    mu: float, sigma: float,
) -> NewsvendorResult:
    """
    Newsvendor under Uniform[a, b] demand.
    a = mu - sqrt(3)*sigma, b = mu + sqrt(3)*sigma  (matches given mean/std).
    """
    half = math.sqrt(3.0) * sigma
    a = max(0.0, mu - half)
    b = mu + half
    cr = (p - c) / (p - s)
    Q  = a + cr * (b - a)   # F(Q) = (Q-a)/(b-a) => Q = a + CR*(b-a)

    dist = stats.uniform(loc=a, scale=b - a)

    # Closed-form for Uniform
    expected_sales    = Q - (Q - a) ** 2 / (2 * (b - a))   # when Q in [a,b]
    expected_leftover = Q - expected_sales
    expected_stockout = (b - Q) ** 2 / (2 * (b - a))
    expected_profit   = (p - s) * expected_sales - (c - s) * Q
    fill_rate         = expected_sales / mu if mu > 0 else 0.0

    q_vals = np.linspace(a, b, 200)
    profits = []
    for q in q_vals:
        es = q - max(0.0, (q - a)) ** 2 / (2 * (b - a)) if q <= b else mu
        profits.append((p - s) * es - (c - s) * q)

    return NewsvendorResult(
        critical_ratio=round(cr, 6),
        optimal_quantity=round(Q, 4),
        expected_profit=round(expected_profit, 4),
        expected_sales=round(expected_sales, 4),
        expected_leftover=round(expected_leftover, 4),
        expected_stockout=round(expected_stockout, 4),
        fill_rate=round(min(fill_rate, 1.0), 6),
        profit_curve_q=q_vals.tolist(),
        profit_curve_ep=profits,
    )


def solve_newsvendor(
    p: float, c: float, s: float,
    demand_mean: float, demand_std: float,
    dist: str = "normal",
) -> NewsvendorResult:
    """Dispatch to the appropriate demand-distribution solver."""
    if c <= s:
        raise ValueError("unit_cost must be greater than salvage_value (otherwise never salvage).")
    if p <= c:
        raise ValueError("selling_price must be greater than unit_cost (otherwise never profitable).")
    match dist:
        case "normal":
            return _normal_newsvendor(p, c, s, demand_mean, demand_std)
        case "poisson":
            return _poisson_newsvendor(p, c, s, demand_mean)
        case "uniform":
            return _uniform_newsvendor(p, c, s, demand_mean, demand_std)
        case _:
            raise ValueError(f"Unsupported distribution: {dist!r}")
