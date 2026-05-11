"""
All API route handlers.

Each endpoint:
  1. Validates input via Pydantic (done automatically by FastAPI).
  2. Calls the pure math/simulation layer.
  3. Returns a typed response.

Error handling philosophy:
  - 422 Unprocessable Entity: Pydantic validation failures (automatic).
  - 400 Bad Request:          domain logic errors (e.g. unstable queue).
  - 503 Service Unavailable:  AI key missing.
  - 500 Internal Server Error: unexpected exceptions (logged, not leaked).

Rate limiting note: global default (20/minute per IP) is enforced by the
Limiter instance in middleware.py via app.state.limiter.  We do NOT use
@limiter.limit() per-route decorators because they conflict with FastAPI's
request-body injection when the function also accepts a Pydantic body param.
"""
from __future__ import annotations

import logging

import anthropic
from fastapi import APIRouter, HTTPException

from src.ai.explainer import explain
from src.api.schemas import (
    EOQRequest,
    EOQResponse,
    ExplainRequest,
    ExplainResponse,
    NewsvendorRequest,
    NewsvendorResponse,
    QueuingRequest,
    QueuingResponse,
    SimulationRequest,
    SimulationResponse,
)
from src.models.inventory import solve_eoq, solve_newsvendor
from src.models.queuing import solve_queue
from src.models.simulation import run_simulation

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Health check ──────────────────────────────────────────────────────────────

@router.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}


# ── Queuing ───────────────────────────────────────────────────────────────────

@router.post("/queuing", response_model=QueuingResponse, tags=["queuing"])
async def queuing_endpoint(body: QueuingRequest):
    """Compute exact analytical results for M/M/1, M/M/c, M/D/1, or M/G/1 queues."""
    try:
        result = solve_queue(
            model=body.model.value,
            lam=body.arrival_rate,
            mu=body.service_rate,
            c=body.num_servers,
            cs_sq=body.service_cv_sq,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Unexpected error in /queuing")
        raise HTTPException(status_code=500, detail="Internal computation error.")

    return QueuingResponse(
        model=result.model,
        utilization=result.utilization,
        L=result.L,
        Lq=result.Lq,
        W=result.W,
        Wq=result.Wq,
        P0=result.P0,
        P_wait=result.P_wait,
        prob_dist=result.prob_dist,
        little_law_check=result.little_law_check,
    )


# ── EOQ ───────────────────────────────────────────────────────────────────────

@router.post("/inventory/eoq", response_model=EOQResponse, tags=["inventory"])
async def eoq_endpoint(body: EOQRequest):
    """Economic Order Quantity model."""
    try:
        r = solve_eoq(
            D=body.annual_demand,
            K=body.ordering_cost,
            c=body.unit_cost,
            i=body.holding_rate,
        )
    except Exception:
        logger.exception("Unexpected error in /inventory/eoq")
        raise HTTPException(status_code=500, detail="Internal computation error.")

    return EOQResponse(
        eoq=r.eoq,
        orders_per_year=r.orders_per_year,
        cycle_time_days=r.cycle_time_days,
        total_annual_cost=r.total_annual_cost,
        cost_curve_q=r.cost_curve_q,
        cost_curve_tc=r.cost_curve_tc,
        cost_curve_holding=r.cost_curve_holding,
        cost_curve_ordering=r.cost_curve_ordering,
    )


# ── Newsvendor ────────────────────────────────────────────────────────────────

@router.post("/inventory/newsvendor", response_model=NewsvendorResponse, tags=["inventory"])
async def newsvendor_endpoint(body: NewsvendorRequest):
    """Single-period stochastic inventory (Newsvendor) model."""
    try:
        r = solve_newsvendor(
            p=body.selling_price,
            c=body.unit_cost,
            s=body.salvage_value,
            demand_mean=body.demand_mean,
            demand_std=body.demand_std,
            dist=body.demand_dist.value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Unexpected error in /inventory/newsvendor")
        raise HTTPException(status_code=500, detail="Internal computation error.")

    return NewsvendorResponse(
        critical_ratio=r.critical_ratio,
        optimal_quantity=r.optimal_quantity,
        expected_profit=r.expected_profit,
        expected_sales=r.expected_sales,
        expected_leftover=r.expected_leftover,
        expected_stockout=r.expected_stockout,
        fill_rate=r.fill_rate,
        profit_curve_q=r.profit_curve_q,
        profit_curve_ep=r.profit_curve_ep,
    )


# ── Monte Carlo Simulation ────────────────────────────────────────────────────

@router.post("/simulation", response_model=SimulationResponse, tags=["simulation"])
async def simulation_endpoint(body: SimulationRequest):
    """
    Run a Monte Carlo discrete-event simulation and return results with
    95% confidence intervals.
    """
    analytical_W = analytical_Wq = None
    try:
        analytic = solve_queue(
            model=body.model.value,
            lam=body.arrival_rate,
            mu=body.service_rate,
            c=body.num_servers,
        )
        analytical_W  = analytic.W
        analytical_Wq = analytic.Wq
    except Exception:
        pass  # comparison is optional; not all models have closed-form solutions

    try:
        result = run_simulation(
            model=body.model.value,
            lam=body.arrival_rate,
            mu=body.service_rate,
            c=body.num_servers,
            n_customers=body.num_customers,
            n_replications=body.num_replications,
            seed=body.seed,
            analytical_W=analytical_W,
            analytical_Wq=analytical_Wq,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Unexpected error in /simulation")
        raise HTTPException(status_code=500, detail="Internal computation error.")

    return SimulationResponse(
        utilization_mean=result.utilization_mean,
        L_mean=result.L_mean,
        Lq_mean=result.Lq_mean,
        W_mean=result.W_mean,
        Wq_mean=result.Wq_mean,
        W_ci_hw=result.W_ci_hw,
        Wq_ci_hw=result.Wq_ci_hw,
        wait_histogram_bins=result.wait_histogram_bins,
        wait_histogram_counts=result.wait_histogram_counts,
        analytical_W=result.analytical_W,
        analytical_Wq=result.analytical_Wq,
    )


# ── AI Explanation ────────────────────────────────────────────────────────────

@router.post("/explain", response_model=ExplainResponse, tags=["ai"])
async def explain_endpoint(body: ExplainRequest):
    """
    Send model results to Claude Haiku and return a plain-English explanation
    with actionable business recommendations.
    """
    try:
        text, model_used = await explain(
            model_type=body.model_type,
            parameters=body.parameters,
            results=body.results,
        )
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=503, detail="Invalid API key. Check your ANTHROPIC_API_KEY.")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="AI rate limit reached. Try again shortly.")
    except anthropic.APITimeoutError:
        raise HTTPException(status_code=504, detail="AI response timed out. Try again.")
    except anthropic.APIError:
        logger.exception("Anthropic API error")
        raise HTTPException(status_code=502, detail="AI service error.")
    except Exception:
        logger.exception("Unexpected error in /explain")
        raise HTTPException(status_code=500, detail="Internal error.")

    return ExplainResponse(explanation=text, model_used=model_used)
