"""
Pydantic schemas for all API request and response payloads.
Strict field constraints prevent bad data from reaching the math layer.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


# ── Enumerations ──────────────────────────────────────────────────────────────

class QueueModel(str, Enum):
    MM1   = "MM1"
    MMC   = "MMC"
    MD1   = "MD1"
    MG1   = "MG1"
    MMCK  = "MMCK"   # finite buffer, c servers
    MM1K  = "MM1K"   # finite capacity, 1 server
    MMINF = "MMINF"  # infinite servers / self-service
    GG1   = "GG1"    # Kingman heavy-traffic approximation
    BULK  = "BULK"   # M[X]/M/1 batch arrivals


class DemandDistribution(str, Enum):
    NORMAL  = "normal"
    POISSON = "poisson"
    UNIFORM = "uniform"


# ── Queuing: analytical ───────────────────────────────────────────────────────

class QueuingRequest(BaseModel):
    model:          QueueModel = Field(..., description="Queue model type")
    arrival_rate:   float      = Field(..., gt=0, le=10_000, description="λ: arrivals per time unit")
    service_rate:   float      = Field(..., gt=0, le=10_000, description="μ: services per server per time unit")
    num_servers:    int        = Field(1,   ge=1, le=200,    description="c: parallel servers (M/M/c, M/M/c/K)")
    service_cv_sq:  float      = Field(1.0, ge=0, le=1_000,  description="Cs²: squared CV of service time (M/G/1, G/G/1)")
    arrival_cv_sq:  float      = Field(1.0, ge=0, le=1_000,  description="Ca²: squared CV of interarrival time (G/G/1)")
    capacity:       int        = Field(10,  ge=1, le=10_000,  description="K: max customers in system (M/M/c/K, M/M/1/K)")
    batch_size:     int        = Field(2,   ge=2, le=1_000,   description="b: batch size (M[X]/M/1)")

    @model_validator(mode="after")
    def check_stability(self) -> "QueuingRequest":
        # Infinite-server and finite-capacity models never have stability issues
        if self.model in (QueueModel.MMINF, QueueModel.MMCK, QueueModel.MM1K):
            return self
        effective_c = self.num_servers if self.model == QueueModel.MMC else 1
        lam_eff = self.arrival_rate * (self.batch_size if self.model == QueueModel.BULK else 1)
        rho = lam_eff / (effective_c * self.service_rate)
        if rho >= 1.0:
            raise ValueError(
                f"System is unstable: ρ = {rho:.4f} ≥ 1. "
                "Increase service_rate or num_servers, or reduce arrival_rate."
            )
        return self


class QueuingResponse(BaseModel):
    model:            str
    utilization:      float  = Field(..., description="ρ: server utilization")
    L:                float  = Field(..., description="Average number in system")
    Lq:               float  = Field(..., description="Average number in queue")
    W:                float  = Field(..., description="Average time in system")
    Wq:               float  = Field(..., description="Average time in queue")
    P0:               float  = Field(..., description="Probability system is empty")
    P_wait:           Optional[float] = None
    prob_dist:        list[float]
    little_law_check: float
    blocking_prob:    Optional[float] = None   # P(K) for finite-capacity models
    effective_lam:    Optional[float] = None   # throughput after blocking
    notes:            Optional[str]   = None


# ── Queuing: scenario comparison ──────────────────────────────────────────────

class ScenarioCompareRequest(BaseModel):
    scenarios: list[QueuingRequest] = Field(..., min_length=2, max_length=8,
                                            description="2–8 parameter sets to compare")
    labels:    Optional[list[str]]  = Field(None, description="Optional scenario labels")


class ScenarioCompareResponse(BaseModel):
    results: list[QueuingResponse]
    labels:  list[str]


# ── Inventory: EOQ ────────────────────────────────────────────────────────────

class EOQRequest(BaseModel):
    annual_demand:  float = Field(..., gt=0, le=1_000_000)
    ordering_cost:  float = Field(..., gt=0, le=1_000_000)
    unit_cost:      float = Field(..., gt=0, le=100_000)
    holding_rate:   float = Field(..., gt=0, le=1)


class EOQResponse(BaseModel):
    eoq:               float
    orders_per_year:   float
    cycle_time_days:   float
    total_annual_cost: float
    reorder_point:     Optional[float] = None
    cost_curve_q:      list[float]
    cost_curve_tc:     list[float]
    cost_curve_holding: list[float]
    cost_curve_ordering: list[float]


# ── Inventory: EOQ with backorders ────────────────────────────────────────────

class EOQBackorderRequest(BaseModel):
    annual_demand:   float = Field(..., gt=0, le=1_000_000)
    ordering_cost:   float = Field(..., gt=0, le=1_000_000)
    unit_cost:       float = Field(..., gt=0, le=100_000)
    holding_rate:    float = Field(..., gt=0, le=1)
    backorder_cost:  float = Field(..., gt=0, le=1_000_000,
                                   description="π: backorder penalty cost per unit per year")


class EOQBackorderResponse(BaseModel):
    eoq:               float
    max_inventory:     float
    max_backorder:     float
    orders_per_year:   float
    cycle_time_days:   float
    total_annual_cost: float
    savings_vs_eoq:    float
    cost_curve_q:      list[float]
    cost_curve_tc:     list[float]


# ── Inventory: EPQ ────────────────────────────────────────────────────────────

class EPQRequest(BaseModel):
    annual_demand:       float = Field(..., gt=0, le=10_000_000)
    production_rate:     float = Field(..., gt=0, le=10_000_000,
                                       description="P: annual production rate (must exceed demand)")
    setup_cost:          float = Field(..., gt=0, le=1_000_000)
    unit_cost:           float = Field(..., gt=0, le=100_000)
    holding_rate:        float = Field(..., gt=0, le=1)

    @model_validator(mode="after")
    def check_feasibility(self) -> "EPQRequest":
        if self.production_rate <= self.annual_demand:
            raise ValueError("production_rate must exceed annual_demand (system must be able to keep up).")
        return self


class EPQResponse(BaseModel):
    epq:                  float
    max_inventory:        float
    production_run_time:  float
    cycle_time_days:      float
    uptime_fraction:      float
    orders_per_year:      float
    total_annual_cost:    float
    cost_curve_q:         list[float]
    cost_curve_tc:        list[float]


# ── Inventory: Newsvendor ─────────────────────────────────────────────────────

class NewsvendorRequest(BaseModel):
    selling_price:  float = Field(..., gt=0, le=1_000_000)
    unit_cost:      float = Field(..., gt=0, le=1_000_000)
    salvage_value:  float = Field(...,       le=1_000_000)
    demand_mean:    float = Field(..., gt=0, le=1_000_000)
    demand_std:     float = Field(..., gt=0, le=1_000_000)
    demand_dist:    DemandDistribution = DemandDistribution.NORMAL

    @model_validator(mode="after")
    def cost_ordering(self) -> "NewsvendorRequest":
        if self.unit_cost <= self.salvage_value:
            raise ValueError("unit_cost must be greater than salvage_value.")
        if self.selling_price <= self.unit_cost:
            raise ValueError("selling_price must be greater than unit_cost.")
        return self


class NewsvendorResponse(BaseModel):
    critical_ratio:    float
    optimal_quantity:  float
    expected_profit:   float
    expected_sales:    float
    expected_leftover: float
    expected_stockout: float
    fill_rate:         float
    profit_curve_q:    list[float]
    profit_curve_ep:   list[float]


# ── Inventory: Reorder Point ──────────────────────────────────────────────────

class ReorderPointRequest(BaseModel):
    annual_demand:  float = Field(..., gt=0, le=10_000_000, description="D: annual demand (units/year)")
    lead_time_days: float = Field(..., gt=0, le=730,        description="L: replenishment lead time, in DAYS (max 730 = 2 years)")
    demand_std_day: float = Field(..., ge=0, le=100_000,    description="σ_d: std dev of DAILY demand (must match lead-time unit)")
    ordering_cost:  float = Field(..., gt=0, le=1_000_000)
    unit_cost:      float = Field(..., gt=0, le=100_000)
    holding_rate:   float = Field(..., gt=0, le=1)
    service_level:  float = Field(0.95, gt=0, lt=1, description="Target cycle-service level (0–1)")


class ReorderPointResponse(BaseModel):
    order_quantity:    float
    reorder_point:     float
    safety_stock:      float
    service_level:     float
    z_score:           float
    annual_hold_cost:  float
    annual_order_cost: float
    total_annual_cost: float
    demand_lead_time:  float
    std_lead_time:     float


# ── Inventory: Base Stock ─────────────────────────────────────────────────────

class BaseStockRequest(BaseModel):
    annual_demand:  float = Field(..., gt=0, le=10_000_000, description="D: annual demand (units/year)")
    lead_time_days: float = Field(..., gt=0, le=730,        description="L: replenishment lead time, in DAYS")
    demand_std_day: float = Field(..., ge=0, le=100_000,    description="σ_d: std dev of DAILY demand")
    unit_cost:      float = Field(..., gt=0, le=100_000)
    holding_rate:   float = Field(..., gt=0, le=1)
    service_level:  float = Field(0.95, gt=0, lt=1)


class BaseStockResponse(BaseModel):
    base_stock_level:    float
    safety_stock:        float
    z_score:             float
    expected_inventory:  float
    expected_backorders: float
    fill_rate:           float
    annual_hold_cost:    float
    demand_lead_time:    float
    std_lead_time:       float


# ── Monte Carlo simulation ────────────────────────────────────────────────────

class SimulationRequest(BaseModel):
    model:            QueueModel = Field(..., description="Queue model to simulate")
    arrival_rate:     float      = Field(..., gt=0, le=10_000)
    service_rate:     float      = Field(..., gt=0, le=10_000)
    num_servers:      int        = Field(1, ge=1, le=50)
    num_customers:    int        = Field(5_000, ge=100, le=50_000)
    num_replications: int        = Field(10, ge=1, le=50)
    seed:             Optional[int] = Field(None, ge=0, le=2**31 - 1)

    @model_validator(mode="after")
    def check_stability(self) -> "SimulationRequest":
        rho = self.arrival_rate / (self.num_servers * self.service_rate)
        if rho >= 0.99:
            raise ValueError(f"ρ = {rho:.4f}: too close to saturation for stable simulation.")
        return self


class SimulationResponse(BaseModel):
    utilization_mean:      float
    L_mean:                float
    Lq_mean:               float
    W_mean:                float
    Wq_mean:               float
    W_ci_hw:               float
    Wq_ci_hw:              float
    wait_histogram_bins:   list[float]
    wait_histogram_counts: list[int]
    analytical_W:          Optional[float] = None
    analytical_Wq:         Optional[float] = None


# ── Optimization: LP ──────────────────────────────────────────────────────────

class LPRequest(BaseModel):
    objective:         str        = Field("maximize", pattern="^(maximize|minimize)$")
    c_obj:             list[float] = Field(..., min_length=1, max_length=20,
                                          description="Objective function coefficients")
    A_ub:              list[list[float]] = Field(..., description="Inequality constraint matrix (≤)")
    b_ub:              list[float]       = Field(..., description="Inequality RHS values")
    variable_names:    Optional[list[str]] = None
    constraint_names:  Optional[list[str]] = None

    @model_validator(mode="after")
    def check_dimensions(self) -> "LPRequest":
        n = len(self.c_obj)
        if len(self.A_ub) != len(self.b_ub):
            raise ValueError("A_ub must have the same number of rows as b_ub.")
        for row in self.A_ub:
            if len(row) != n:
                raise ValueError(f"Each row of A_ub must have {n} columns (one per variable).")
        if len(self.A_ub) > 50:
            raise ValueError("Maximum 50 constraints supported.")
        if self.variable_names and len(self.variable_names) != n:
            raise ValueError("variable_names length must match c_obj length.")
        if self.constraint_names and len(self.constraint_names) != len(self.b_ub):
            raise ValueError("constraint_names length must match b_ub length.")
        # Sanitize names to prevent injection
        if self.variable_names:
            self.variable_names = [str(v)[:50] for v in self.variable_names]
        if self.constraint_names:
            self.constraint_names = [str(c)[:50] for c in self.constraint_names]
        return self


class LPResponse(BaseModel):
    status:              str
    optimal_value:       Optional[float]
    variables:           dict[str, float]
    shadow_prices:       dict[str, float]
    reduced_costs:       dict[str, float]
    binding_constraints: list[str]
    slacks:              dict[str, float]
    rhs_ranges:          dict[str, Any]
    obj_ranges:          dict[str, Any]


# ── Optimization: CPM/PERT ────────────────────────────────────────────────────

class CPMTaskInput(BaseModel):
    name:         str   = Field(..., max_length=50)
    duration:     float = Field(..., gt=0, le=10_000)
    variance:     float = Field(0.0, ge=0, le=1_000_000, description="PERT: ((b-a)/6)²")
    predecessors: list[str] = Field(default_factory=list)


class CPMRequest(BaseModel):
    tasks: list[CPMTaskInput] = Field(..., min_length=1, max_length=200)


class CPMResponse(BaseModel):
    critical_path:     list[str]
    project_duration:  float
    project_variance:  float
    project_std:       float
    tasks:             dict[str, Any]


# ── AI Explanation ────────────────────────────────────────────────────────────

class ExplainRequest(BaseModel):
    model_type:  str  = Field(..., max_length=50)
    parameters:  dict = Field(...)
    results:     dict = Field(...)

    @model_validator(mode="after")
    def sanitize(self) -> "ExplainRequest":
        if len(str(self.parameters)) > 2_000 or len(str(self.results)) > 5_000:
            raise ValueError("Payload too large for explanation endpoint.")
        return self


class ExplainResponse(BaseModel):
    explanation: str
    model_used:  str
