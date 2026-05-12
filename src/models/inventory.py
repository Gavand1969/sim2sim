"""
Inventory models: EOQ, EOQ with backorders, EPQ, Newsvendor,
(Q,r) continuous-review reorder point, and base-stock policy.

References
----------
- Zipkin, P. (2000). Foundations of Inventory Management.
- Porteus, E. (2002). Foundations of Stochastic Inventory Theory.
- Silver, E., Pyke, D. & Thomas, D. (2017). Inventory and Production Management.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy import stats


# ── EOQ ───────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EOQResult:
    eoq:                float
    orders_per_year:    float
    cycle_time_days:    float
    total_annual_cost:  float
    cost_curve_q:       list[float]
    cost_curve_tc:      list[float]
    cost_curve_holding: list[float]
    cost_curve_ordering: list[float]


def solve_eoq(D: float, K: float, c: float, i: float) -> EOQResult:
    """
    Classic EOQ (Wilson formula).
    h = i·c  (holding cost per unit/year)
    Q* = √(2KD/h),   TC* = √(2KDh)
    """
    h   = i * c
    eoq = math.sqrt(2.0 * K * D / h)
    opy = D / eoq
    ct  = 365.0 / opy
    tc  = math.sqrt(2.0 * K * D * h)

    q_vals         = np.linspace(1.0, 3.0 * eoq, 200)
    holding_costs  = h * q_vals / 2.0
    ordering_costs = K * D / q_vals
    total_costs    = holding_costs + ordering_costs

    return EOQResult(
        eoq=round(eoq, 4), orders_per_year=round(opy, 4),
        cycle_time_days=round(ct, 4), total_annual_cost=round(tc, 4),
        cost_curve_q=q_vals.tolist(), cost_curve_tc=total_costs.tolist(),
        cost_curve_holding=holding_costs.tolist(),
        cost_curve_ordering=ordering_costs.tolist(),
    )


# ── EOQ with Backorders ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class EOQBackorderResult:
    eoq:                  float   # optimal order quantity
    max_inventory:        float   # S* — peak on-hand inventory
    max_backorder:        float   # b* = Q* − S*
    orders_per_year:      float
    cycle_time_days:      float
    total_annual_cost:    float   # always ≤ classic EOQ cost
    savings_vs_eoq:       float   # dollar savings from allowing backorders
    cost_curve_q:         list[float]
    cost_curve_tc:        list[float]


def solve_eoq_backorder(D: float, K: float, c: float, i: float, pi: float) -> EOQBackorderResult:
    """
    EOQ with planned backorders (lost-sales penalty = π $/unit/year).

    Q* = √(2KD/h) · √((h+π)/π)       [always ≥ classic EOQ]
    S* = Q* · π/(h+π)                  [max on-hand inventory]
    b* = Q* · h/(h+π)                  [max backorder level]
    TC* = √(2KDh) · √(π/(h+π))        [always ≤ classic EOQ TC]

    Insight: allowing backorders is always beneficial if π is finite —
    the larger π, the closer the solution approaches the classic EOQ.
    """
    h  = i * c
    Q  = math.sqrt(2.0 * K * D / h) * math.sqrt((h + pi) / pi)
    S  = Q * pi / (h + pi)
    b  = Q * h  / (h + pi)
    opy = D / Q
    ct  = 365.0 / opy
    tc  = math.sqrt(2.0 * K * D * h) * math.sqrt(pi / (h + pi))

    # Classic EOQ cost for comparison
    tc_classic = math.sqrt(2.0 * K * D * h)

    q_vals = np.linspace(max(1.0, Q * 0.1), Q * 3.0, 200)
    # Average inventory = S²/(2Q); average backorder = b²/(2Q)
    S_of_q = q_vals * pi / (h + pi)
    b_of_q = q_vals * h  / (h + pi)
    tc_vals = (h * S_of_q ** 2 / (2 * q_vals)
               + pi * b_of_q ** 2 / (2 * q_vals)
               + K * D / q_vals)

    return EOQBackorderResult(
        eoq=round(Q, 4), max_inventory=round(S, 4), max_backorder=round(b, 4),
        orders_per_year=round(opy, 4), cycle_time_days=round(ct, 4),
        total_annual_cost=round(tc, 4),
        savings_vs_eoq=round(tc_classic - tc, 4),
        cost_curve_q=q_vals.tolist(), cost_curve_tc=tc_vals.tolist(),
    )


# ── EPQ ───────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EPQResult:
    epq:                  float   # optimal production run size
    max_inventory:        float   # I_max = Q*(1 − D/P)
    production_run_time:  float   # t_p = Q/P (days)
    cycle_time_days:      float   # T = Q/D (days)
    uptime_fraction:      float   # D/P
    orders_per_year:      float   # production runs per year
    total_annual_cost:    float
    cost_curve_q:         list[float]
    cost_curve_tc:        list[float]


def solve_epq(D: float, P: float, K: float, c: float, i: float) -> EPQResult:
    """
    Economic Production Quantity (EPQ / ELS).
    Production rate P > demand rate D (system is feasible).

    Q* = √(2KD / (h·(1−D/P)))
    I_max = Q*(1−D/P)     [max inventory — less than EOQ because stock depletes during production]
    TC* = √(2KDh·(1−D/P)) [always ≤ classic EOQ cost]
    """
    h   = i * c
    uptime = D / P
    if uptime >= 1.0:
        raise ValueError("Production rate P must exceed demand rate D.")
    Q   = math.sqrt(2.0 * K * D / (h * (1.0 - uptime)))
    I_max = Q * (1.0 - uptime)
    t_p   = Q / P * 365.0
    T     = Q / D * 365.0
    opy   = D / Q
    tc    = math.sqrt(2.0 * K * D * h * (1.0 - uptime))

    q_vals  = np.linspace(max(1.0, Q * 0.1), Q * 3.0, 200)
    tc_vals = h * q_vals * (1.0 - uptime) / 2.0 + K * D / q_vals

    return EPQResult(
        epq=round(Q, 4), max_inventory=round(I_max, 4),
        production_run_time=round(t_p, 2), cycle_time_days=round(T, 2),
        uptime_fraction=round(uptime, 4), orders_per_year=round(opy, 4),
        total_annual_cost=round(tc, 4),
        cost_curve_q=q_vals.tolist(), cost_curve_tc=tc_vals.tolist(),
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


def _normal_newsvendor(p, c, s, mu, sigma) -> NewsvendorResult:
    cr  = (p - c) / (p - s)
    z   = stats.norm.ppf(cr)
    Q   = mu + sigma * z
    phi_z, Phi_z = stats.norm.pdf(z), stats.norm.cdf(z)
    L_z = phi_z - z * (1.0 - Phi_z)
    expected_sales    = mu - sigma * L_z
    expected_leftover = Q - expected_sales
    expected_stockout = (mu - Q) * (1.0 - Phi_z) + sigma * phi_z
    expected_profit   = (p - s) * expected_sales - (c - s) * Q
    fill_rate         = expected_sales / mu if mu > 0 else 0.0

    q_lo   = max(0.0, mu - 3 * sigma)
    q_vals = np.linspace(q_lo, mu + 4 * sigma, 200)
    profits = []
    for q in q_vals:
        z_q  = (q - mu) / sigma
        L_zq = stats.norm.pdf(z_q) - z_q * (1.0 - stats.norm.cdf(z_q))
        profits.append((p - s) * (mu - sigma * L_zq) - (c - s) * q)

    return NewsvendorResult(
        critical_ratio=round(cr, 6), optimal_quantity=round(Q, 4),
        expected_profit=round(expected_profit, 4), expected_sales=round(expected_sales, 4),
        expected_leftover=round(expected_leftover, 4), expected_stockout=round(expected_stockout, 4),
        fill_rate=round(min(fill_rate, 1.0), 6),
        profit_curve_q=q_vals.tolist(), profit_curve_ep=profits,
    )


def _poisson_newsvendor(p, c, s, lam) -> NewsvendorResult:
    cr   = (p - c) / (p - s)
    dist = stats.poisson(lam)
    Q    = int(dist.ppf(cr))
    d_vals = np.arange(0, max(200, Q * 3))
    pmf    = dist.pmf(d_vals)
    expected_sales    = float(np.sum(np.minimum(d_vals, Q) * pmf))
    expected_leftover = float(np.sum(np.maximum(Q - d_vals, 0) * pmf))
    expected_stockout = float(np.sum(np.maximum(d_vals - Q, 0) * pmf))
    expected_profit   = (p - s) * expected_sales - (c - s) * Q
    fill_rate         = expected_sales / lam if lam > 0 else 0.0
    q_vals  = np.arange(0, max(50, Q * 3))
    profits = [(p - s) * float(np.sum(np.minimum(d_vals, q) * pmf)) - (c - s) * q
               for q in q_vals]
    return NewsvendorResult(
        critical_ratio=round(cr, 6), optimal_quantity=float(Q),
        expected_profit=round(expected_profit, 4), expected_sales=round(expected_sales, 4),
        expected_leftover=round(expected_leftover, 4), expected_stockout=round(expected_stockout, 4),
        fill_rate=round(min(fill_rate, 1.0), 6),
        profit_curve_q=q_vals.tolist(), profit_curve_ep=profits,
    )


def _uniform_newsvendor(p, c, s, mu, sigma) -> NewsvendorResult:
    half = math.sqrt(3.0) * sigma
    a    = max(0.0, mu - half)
    b    = mu + half
    cr   = (p - c) / (p - s)
    Q    = a + cr * (b - a)
    expected_sales    = Q - (Q - a) ** 2 / (2 * (b - a))
    expected_leftover = Q - expected_sales
    expected_stockout = (b - Q) ** 2 / (2 * (b - a))
    expected_profit   = (p - s) * expected_sales - (c - s) * Q
    fill_rate         = expected_sales / mu if mu > 0 else 0.0
    q_vals  = np.linspace(a, b, 200)
    profits = [(p - s) * (q - max(0.0, (q - a)) ** 2 / (2 * (b - a)))
               - (c - s) * q for q in q_vals]
    return NewsvendorResult(
        critical_ratio=round(cr, 6), optimal_quantity=round(Q, 4),
        expected_profit=round(expected_profit, 4), expected_sales=round(expected_sales, 4),
        expected_leftover=round(expected_leftover, 4), expected_stockout=round(expected_stockout, 4),
        fill_rate=round(min(fill_rate, 1.0), 6),
        profit_curve_q=q_vals.tolist(), profit_curve_ep=profits,
    )


def solve_newsvendor(
    p: float, c: float, s: float,
    demand_mean: float, demand_std: float,
    dist: str = "normal",
) -> NewsvendorResult:
    if c <= s:
        raise ValueError("unit_cost must be greater than salvage_value.")
    if p <= c:
        raise ValueError("selling_price must be greater than unit_cost.")
    match dist:
        case "normal":  return _normal_newsvendor(p, c, s, demand_mean, demand_std)
        case "poisson": return _poisson_newsvendor(p, c, s, demand_mean)
        case "uniform": return _uniform_newsvendor(p, c, s, demand_mean, demand_std)
        case _:         raise ValueError(f"Unsupported distribution: {dist!r}")


# ── (Q, r) Continuous-Review Reorder Point ────────────────────────────────────

@dataclass(frozen=True)
class ReorderPointResult:
    order_quantity:    float   # Q = EOQ
    reorder_point:     float   # r = D·L + z·σ_L
    safety_stock:      float   # z·σ_L
    service_level:     float   # P(no stockout per cycle) = Φ(z)
    z_score:           float
    annual_hold_cost:  float   # EOQ holding + safety stock holding
    annual_order_cost: float
    total_annual_cost: float
    demand_lead_time:  float   # mean demand during lead time
    std_lead_time:     float   # std dev of demand during lead time


def solve_reorder_point(
    D: float,            # annual demand (units/year)
    L_days: float,       # lead time in DAYS
    sigma_d: float,      # std dev of DAILY demand (same time unit as L_days)
    K: float,            # ordering cost ($/order)
    c: float,            # unit cost ($/unit)
    i: float,            # holding rate (fraction/year)
    service_level: float = 0.95,  # target cycle-service level
) -> ReorderPointResult:
    """
    Continuous-review (Q, r) inventory policy.

    Units: annual demand D is converted to a daily rate (D/365) for the
    lead-time demand calculation, ensuring lead-time-day and daily-sigma
    units agree.  Holding cost h = i·c is annual, so the EOQ uses annual D.

    Order quantity Q = EOQ (Wilson formula).
    Reorder point  r = (D/365)·L_days + z·σ_L,  σ_L = σ_d·√L_days.

    The cycle-service level P(no stockout) = Φ(z).
    Safety stock SS = z·σ_L trades holding cost against stockout risk.
    """
    h       = i * c
    Q       = math.sqrt(2.0 * K * D / h)               # EOQ order quantity (annual)
    D_day   = D / 365.0                                 # daily demand rate
    mu_L    = D_day * L_days                            # mean demand during lead time (units)
    sigma_L = sigma_d * math.sqrt(L_days)               # std dev demand during lead time (units)
    z       = stats.norm.ppf(service_level)
    SS      = z * sigma_L
    r       = mu_L + SS

    annual_hold  = h * (Q / 2.0 + SS)
    annual_order = K * D / Q
    tc           = annual_hold + annual_order

    return ReorderPointResult(
        order_quantity=round(Q, 4), reorder_point=round(r, 4),
        safety_stock=round(SS, 4), service_level=round(service_level, 4),
        z_score=round(z, 4), annual_hold_cost=round(annual_hold, 4),
        annual_order_cost=round(annual_order, 4), total_annual_cost=round(tc, 4),
        demand_lead_time=round(mu_L, 4), std_lead_time=round(sigma_L, 4),
    )


# ── Base-Stock Policy ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BaseStockResult:
    base_stock_level:      float   # S* = μ_L + z·σ_L
    safety_stock:          float   # z·σ_L
    z_score:               float
    expected_inventory:    float   # E[on-hand] = SS + σ_L·φ(z) − (S−μ_L)·(1−Φ(z))
    expected_backorders:   float   # E[B] = σ_L·L(z)
    fill_rate:             float   # fraction of demand met from stock
    annual_hold_cost:      float
    demand_lead_time:      float
    std_lead_time:         float


def solve_base_stock(
    D: float,            # annual demand rate (units/year)
    L_days: float,       # replenishment lead time in DAYS
    sigma_d: float,      # std dev of DAILY demand
    c: float,            # unit cost
    i: float,            # annual holding rate
    service_level: float = 0.95,
) -> BaseStockResult:
    """
    Base-stock (order-up-to) policy for single-item, stochastic demand.

    Units: lead-time is in days and daily sigma is supplied directly, so all
    lead-time quantities (μ_L, σ_L) are in CONSISTENT day-based units.

    S* = μ_L + z·σ_L.
    Each period, order enough to bring inventory position back to S*.

    E[backorders per cycle] = σ_L · L(z)  where
    L(z) = φ(z) − z·(1−Φ(z)) is the standard-normal loss function.
    Type-II fill rate = 1 − E[B per cycle] / E[demand per cycle] = 1 − σ_L·L(z)/μ_L.
    """
    h       = i * c
    D_day   = D / 365.0
    mu_L    = D_day * L_days
    sigma_L = sigma_d * math.sqrt(L_days)
    z       = stats.norm.ppf(service_level)
    SS      = z * sigma_L
    S       = mu_L + SS

    phi_z = stats.norm.pdf(z)
    Phi_z = stats.norm.cdf(z)
    L_z   = phi_z - z * (1.0 - Phi_z)   # standard normal loss function

    E_B           = sigma_L * L_z              # expected backorders per cycle (units)
    E_inv_precise = (S - mu_L) * Phi_z + sigma_L * phi_z

    # Type-II (fill-rate) service level.
    # The standard expression for a base-stock policy with normal lead-time
    # demand is:  beta = 1 - E[B per cycle] / E[demand per cycle]
    # With a continuous-review base-stock policy the demand per cycle equals
    # the lead-time demand mu_L (one cycle = one lead-time interval), so:
    fill_rate = float(np.clip(1.0 - E_B / mu_L, 0.0, 1.0)) if mu_L > 0 else 1.0
    annual_hold = h * E_inv_precise

    return BaseStockResult(
        base_stock_level=round(S, 4), safety_stock=round(SS, 4),
        z_score=round(z, 4),
        expected_inventory=round(E_inv_precise, 4),
        expected_backorders=round(E_B, 4),
        fill_rate=round(fill_rate, 6),
        annual_hold_cost=round(annual_hold, 4),
        demand_lead_time=round(mu_L, 4),
        std_lead_time=round(sigma_L, 4),
    )
