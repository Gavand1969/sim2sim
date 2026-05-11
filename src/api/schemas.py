"""
Pydantic schemas for all API request and response payloads.
Strict field constraints prevent bad data from ever reaching the math layer.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ── Enumerations ──────────────────────────────────────────────────────────────

class QueueModel(str, Enum):
    MM1  = "MM1"
    MMC  = "MMC"
    MD1  = "MD1"
    MG1  = "MG1"


class DemandDistribution(str, Enum):
    NORMAL  = "normal"
    POISSON = "poisson"
    UNIFORM = "uniform"


# ── Queuing: analytical ───────────────────────────────────────────────────────

class QueuingRequest(BaseModel):
    model:          QueueModel = Field(..., description="Queue model type")
    arrival_rate:   float      = Field(..., gt=0, le=10_000, description="λ: mean arrivals per time unit")
    service_rate:   float      = Field(..., gt=0, le=10_000, description="μ: mean services per time unit (per server)")
    num_servers:    int        = Field(1, ge=1, le=100,      description="c: number of parallel servers (M/M/c only)")
    # M/G/1 only
    service_cv_sq:  float      = Field(1.0, ge=0, le=1_000, description="Cs²: squared coefficient of variation of service time")

    @model_validator(mode="after")
    def check_stability(self) -> "QueuingRequest":
        rho = self.arrival_rate / (self.num_servers * self.service_rate)
        if rho >= 1.0:
            raise ValueError(
                f"System is unstable: traffic intensity ρ = {rho:.4f} ≥ 1. "
                "Increase service_rate or num_servers, or reduce arrival_rate."
            )
        return self


class QueuingResponse(BaseModel):
    model:           str
    utilization:     float  = Field(..., description="ρ: server utilization (0–1)")
    L:               float  = Field(..., description="Average number in system")
    Lq:              float  = Field(..., description="Average number in queue")
    W:               float  = Field(..., description="Average time in system")
    Wq:              float  = Field(..., description="Average time in queue")
    P0:              float  = Field(..., description="Probability system is empty")
    P_wait:          Optional[float] = Field(None, description="P(wait>0) — Erlang C, M/M/c only")
    # P(N=n) for n = 0..20 for the distribution chart
    prob_dist:       list[float] = Field(..., description="P(N=n) for n=0..20")
    little_law_check: float = Field(..., description="|L - λW| should be ≈ 0 (sanity check)")


# ── Inventory: EOQ ────────────────────────────────────────────────────────────

class EOQRequest(BaseModel):
    annual_demand:   float = Field(..., gt=0, le=1_000_000, description="D: units demanded per year")
    ordering_cost:   float = Field(..., gt=0, le=1_000_000, description="K: fixed cost per order ($)")
    unit_cost:       float = Field(..., gt=0, le=100_000,   description="c: purchase cost per unit ($)")
    holding_rate:    float = Field(..., gt=0, le=1,         description="i: annual holding cost as fraction of unit cost")


class EOQResponse(BaseModel):
    eoq:              float  = Field(..., description="Economic order quantity (units)")
    orders_per_year:  float  = Field(..., description="Number of orders placed per year")
    cycle_time_days:  float  = Field(..., description="Average days between orders")
    total_annual_cost: float = Field(..., description="Minimum total annual cost ($)")
    reorder_point:    Optional[float] = None
    # Arrays for the TC-vs-Q chart (Q from 1 to 3*EOQ)
    cost_curve_q:     list[float] = Field(..., description="Order quantities for cost curve")
    cost_curve_tc:    list[float] = Field(..., description="Total cost at each Q")
    cost_curve_holding: list[float]
    cost_curve_ordering: list[float]


# ── Inventory: Newsvendor ─────────────────────────────────────────────────────

class NewsvendorRequest(BaseModel):
    selling_price:   float = Field(..., gt=0, le=1_000_000, description="p: revenue per unit sold ($)")
    unit_cost:       float = Field(..., gt=0, le=1_000_000, description="c: cost per unit ordered ($)")
    salvage_value:   float = Field(...,       le=1_000_000, description="s: salvage value per unsold unit ($)")
    demand_mean:     float = Field(..., gt=0, le=1_000_000, description="μ: mean demand")
    demand_std:      float = Field(..., gt=0, le=1_000_000, description="σ: std dev of demand (normal dist)")
    demand_dist:     DemandDistribution = Field(DemandDistribution.NORMAL)

    @model_validator(mode="after")
    def cost_ordering(self) -> "NewsvendorRequest":
        if self.unit_cost <= self.salvage_value:
            raise ValueError("unit_cost must be greater than salvage_value (otherwise never salvage).")
        if self.selling_price <= self.unit_cost:
            raise ValueError("selling_price must be greater than unit_cost (otherwise never profitable).")
        return self


class NewsvendorResponse(BaseModel):
    critical_ratio:    float = Field(..., description="(p-c)/(p-s) — optimal service level")
    optimal_quantity:  float = Field(..., description="Q*: optimal order quantity")
    expected_profit:   float = Field(..., description="E[Profit] at Q*")
    expected_sales:    float = Field(..., description="E[min(D, Q*)]")
    expected_leftover: float = Field(..., description="E[max(Q*-D, 0)]")
    expected_stockout: float = Field(..., description="E[max(D-Q*, 0)]")
    fill_rate:         float = Field(..., description="Fraction of demand met from stock")
    # Profit curve: Q vs E[Profit]
    profit_curve_q:    list[float]
    profit_curve_ep:   list[float]


# ── Monte Carlo simulation ────────────────────────────────────────────────────

class SimulationRequest(BaseModel):
    model:          QueueModel = Field(..., description="Queue model to simulate")
    arrival_rate:   float      = Field(..., gt=0, le=10_000)
    service_rate:   float      = Field(..., gt=0, le=10_000)
    num_servers:    int        = Field(1, ge=1, le=50)
    num_customers:  int        = Field(5_000, ge=100, le=50_000, description="Simulation length")
    num_replications: int      = Field(10, ge=1, le=50, description="Independent runs for CI")
    seed:           Optional[int] = Field(None, ge=0, le=2**31 - 1)

    @model_validator(mode="after")
    def check_stability(self) -> "SimulationRequest":
        rho = self.arrival_rate / (self.num_servers * self.service_rate)
        if rho >= 0.99:
            raise ValueError(
                f"ρ = {rho:.4f}: system too close to or past saturation for simulation."
            )
        return self


class SimulationResponse(BaseModel):
    # Point estimates (mean across replications)
    utilization_mean:  float
    L_mean:            float
    Lq_mean:           float
    W_mean:            float
    Wq_mean:           float
    # 95% confidence interval half-widths
    W_ci_hw:           float
    Wq_ci_hw:          float
    # Histogram data: wait times in queue
    wait_histogram_bins:  list[float]
    wait_histogram_counts: list[int]
    # Analytical comparison (if available)
    analytical_W:      Optional[float] = None
    analytical_Wq:     Optional[float] = None


# ── AI Explanation ────────────────────────────────────────────────────────────

class ExplainRequest(BaseModel):
    model_type:  str   = Field(..., max_length=50)
    parameters:  dict  = Field(..., description="Raw input parameters")
    results:     dict  = Field(..., description="Computed results to explain")

    @model_validator(mode="after")
    def sanitize(self) -> "ExplainRequest":
        # Restrict parameter dict size to prevent prompt injection via huge payloads
        if len(str(self.parameters)) > 2_000 or len(str(self.results)) > 5_000:
            raise ValueError("Payload too large for explanation endpoint.")
        return self


class ExplainResponse(BaseModel):
    explanation: str
    model_used:  str
