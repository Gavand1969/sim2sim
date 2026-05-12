"""
All API route handlers.

Error handling:
  422 — Pydantic validation failures (automatic).
  400 — Domain logic errors (e.g. unstable queue, infeasible LP).
  503 — AI key missing.
  500 — Unexpected exceptions (logged, not leaked).

Rate limiting: global default (20/minute per IP) via app.state.limiter.
No per-route @limiter.limit() decorators — they conflict with FastAPI body injection.
"""
from __future__ import annotations

import asyncio
import logging

import anthropic
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from src.ai.explainer import explain
from src.api.schemas import (
    BaseStockRequest, BaseStockResponse,
    CPMRequest, CPMResponse,
    EOQBackorderRequest, EOQBackorderResponse,
    EOQRequest, EOQResponse,
    EPQRequest, EPQResponse,
    ExplainRequest, ExplainResponse,
    ExportInventoryRequest, ExportLPRequest, ExportQueuingRequest,
    LPRequest, LPResponse,
    NewsvendorRequest, NewsvendorResponse,
    QueuingRequest, QueuingResponse,
    ReorderPointRequest, ReorderPointResponse,
    ScenarioCompareRequest, ScenarioCompareResponse,
    SimulationRequest, SimulationResponse,
)
from src.billing import licenses as billing_licenses
from src.billing.licenses import require_pro
from src.billing.schemas import (
    ActivateRequest, ActivateResponse, LicenseStatusResponse, WebhookAck,
)
from src.billing.webhook import handle_stripe_webhook
from src.export.excel import build_inventory_xlsx, build_lp_xlsx, build_queuing_xlsx
from src.export.pdf import build_inventory_pdf, build_lp_pdf, build_queuing_pdf
from src.models.inventory import (
    solve_base_stock, solve_eoq, solve_eoq_backorder,
    solve_epq, solve_newsvendor, solve_reorder_point,
)
from src.models.optimization import solve_cpm, solve_lp
from src.models.queuing import solve_queue
from src.models.simulation import run_simulation

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _queuing_response(result) -> QueuingResponse:
    return QueuingResponse(
        model=result.model,
        utilization=result.utilization,
        L=result.L, Lq=result.Lq, W=result.W, Wq=result.Wq,
        P0=result.P0, P_wait=result.P_wait,
        prob_dist=result.prob_dist,
        little_law_check=result.little_law_check,
        blocking_prob=result.blocking_prob,
        effective_lam=result.effective_lam,
        notes=result.notes,
    )


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}


# ── Queuing ───────────────────────────────────────────────────────────────────

@router.post("/queuing", response_model=QueuingResponse, tags=["queuing"])
async def queuing_endpoint(body: QueuingRequest):
    """
    Exact analytical results for all supported queue models:
    M/M/1, M/M/c, M/D/1, M/G/1, M/M/c/K, M/M/1/K, M/M/∞, G/G/1, M[X]/M/1.
    """
    try:
        result = solve_queue(
            model=body.model.value,
            lam=body.arrival_rate,
            mu=body.service_rate,
            c=body.num_servers,
            cs_sq=body.service_cv_sq,
            ca_sq=body.arrival_cv_sq,
            K=body.capacity,
            batch_size=body.batch_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Unexpected error in /queuing")
        raise HTTPException(status_code=500, detail="Internal computation error.")
    return _queuing_response(result)


@router.post("/queuing/compare", response_model=ScenarioCompareResponse, tags=["queuing"])
async def queuing_compare_endpoint(body: ScenarioCompareRequest):
    """
    Run 2–8 queuing scenarios in parallel and return all results for
    side-by-side comparison.  Labels default to 'Scenario 1', 'Scenario 2', …
    """
    labels = body.labels or [f"Scenario {i+1}" for i in range(len(body.scenarios))]

    async def _run(req: QueuingRequest) -> QueuingResponse:
        result = solve_queue(
            model=req.model.value,
            lam=req.arrival_rate,
            mu=req.service_rate,
            c=req.num_servers,
            cs_sq=req.service_cv_sq,
            ca_sq=req.arrival_cv_sq,
            K=req.capacity,
            batch_size=req.batch_size,
        )
        return _queuing_response(result)

    try:
        results = await asyncio.gather(*[_run(s) for s in body.scenarios])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Unexpected error in /queuing/compare")
        raise HTTPException(status_code=500, detail="Internal computation error.")

    return ScenarioCompareResponse(results=list(results), labels=labels)


# ── Inventory: EOQ ────────────────────────────────────────────────────────────

@router.post("/inventory/eoq", response_model=EOQResponse, tags=["inventory"])
async def eoq_endpoint(body: EOQRequest):
    try:
        r = solve_eoq(D=body.annual_demand, K=body.ordering_cost,
                      c=body.unit_cost, i=body.holding_rate)
    except Exception:
        logger.exception("Error in /inventory/eoq")
        raise HTTPException(status_code=500, detail="Internal computation error.")
    return EOQResponse(
        eoq=r.eoq, orders_per_year=r.orders_per_year,
        cycle_time_days=r.cycle_time_days, total_annual_cost=r.total_annual_cost,
        cost_curve_q=r.cost_curve_q, cost_curve_tc=r.cost_curve_tc,
        cost_curve_holding=r.cost_curve_holding, cost_curve_ordering=r.cost_curve_ordering,
    )


# ── Inventory: EOQ with Backorders ────────────────────────────────────────────

@router.post("/inventory/eoq-backorder", response_model=EOQBackorderResponse, tags=["inventory"])
async def eoq_backorder_endpoint(body: EOQBackorderRequest):
    try:
        r = solve_eoq_backorder(
            D=body.annual_demand, K=body.ordering_cost,
            c=body.unit_cost, i=body.holding_rate, pi=body.backorder_cost,
        )
    except Exception:
        logger.exception("Error in /inventory/eoq-backorder")
        raise HTTPException(status_code=500, detail="Internal computation error.")
    return EOQBackorderResponse(
        eoq=r.eoq, max_inventory=r.max_inventory, max_backorder=r.max_backorder,
        orders_per_year=r.orders_per_year, cycle_time_days=r.cycle_time_days,
        total_annual_cost=r.total_annual_cost, savings_vs_eoq=r.savings_vs_eoq,
        cost_curve_q=r.cost_curve_q, cost_curve_tc=r.cost_curve_tc,
    )


# ── Inventory: EPQ ────────────────────────────────────────────────────────────

@router.post("/inventory/epq", response_model=EPQResponse, tags=["inventory"])
async def epq_endpoint(body: EPQRequest):
    try:
        r = solve_epq(
            D=body.annual_demand, P=body.production_rate,
            K=body.setup_cost, c=body.unit_cost, i=body.holding_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Error in /inventory/epq")
        raise HTTPException(status_code=500, detail="Internal computation error.")
    return EPQResponse(
        epq=r.epq, max_inventory=r.max_inventory,
        production_run_time=r.production_run_time, cycle_time_days=r.cycle_time_days,
        uptime_fraction=r.uptime_fraction, orders_per_year=r.orders_per_year,
        total_annual_cost=r.total_annual_cost,
        cost_curve_q=r.cost_curve_q, cost_curve_tc=r.cost_curve_tc,
    )


# ── Inventory: Newsvendor ─────────────────────────────────────────────────────

@router.post("/inventory/newsvendor", response_model=NewsvendorResponse, tags=["inventory"])
async def newsvendor_endpoint(body: NewsvendorRequest):
    try:
        r = solve_newsvendor(
            p=body.selling_price, c=body.unit_cost, s=body.salvage_value,
            demand_mean=body.demand_mean, demand_std=body.demand_std,
            dist=body.demand_dist.value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Error in /inventory/newsvendor")
        raise HTTPException(status_code=500, detail="Internal computation error.")
    return NewsvendorResponse(
        critical_ratio=r.critical_ratio, optimal_quantity=r.optimal_quantity,
        expected_profit=r.expected_profit, expected_sales=r.expected_sales,
        expected_leftover=r.expected_leftover, expected_stockout=r.expected_stockout,
        fill_rate=r.fill_rate, profit_curve_q=r.profit_curve_q, profit_curve_ep=r.profit_curve_ep,
    )


# ── Inventory: Reorder Point ──────────────────────────────────────────────────

@router.post("/inventory/reorder-point", response_model=ReorderPointResponse, tags=["inventory"])
async def reorder_point_endpoint(body: ReorderPointRequest):
    try:
        r = solve_reorder_point(
            D=body.annual_demand, L_days=body.lead_time_days,
            sigma_d=body.demand_std_day,
            K=body.ordering_cost, c=body.unit_cost, i=body.holding_rate,
            service_level=body.service_level,
        )
    except Exception:
        logger.exception("Error in /inventory/reorder-point")
        raise HTTPException(status_code=500, detail="Internal computation error.")
    return ReorderPointResponse(
        order_quantity=r.order_quantity, reorder_point=r.reorder_point,
        safety_stock=r.safety_stock, service_level=r.service_level,
        z_score=r.z_score, annual_hold_cost=r.annual_hold_cost,
        annual_order_cost=r.annual_order_cost, total_annual_cost=r.total_annual_cost,
        demand_lead_time=r.demand_lead_time, std_lead_time=r.std_lead_time,
    )


# ── Inventory: Base Stock ─────────────────────────────────────────────────────

@router.post("/inventory/base-stock", response_model=BaseStockResponse, tags=["inventory"])
async def base_stock_endpoint(body: BaseStockRequest):
    try:
        r = solve_base_stock(
            D=body.annual_demand, L_days=body.lead_time_days,
            sigma_d=body.demand_std_day,
            c=body.unit_cost, i=body.holding_rate, service_level=body.service_level,
        )
    except Exception:
        logger.exception("Error in /inventory/base-stock")
        raise HTTPException(status_code=500, detail="Internal computation error.")
    return BaseStockResponse(
        base_stock_level=r.base_stock_level, safety_stock=r.safety_stock,
        z_score=r.z_score, expected_inventory=r.expected_inventory,
        expected_backorders=r.expected_backorders, fill_rate=r.fill_rate,
        annual_hold_cost=r.annual_hold_cost, demand_lead_time=r.demand_lead_time,
        std_lead_time=r.std_lead_time,
    )


# ── Monte Carlo Simulation ────────────────────────────────────────────────────

@router.post("/simulation", response_model=SimulationResponse, tags=["simulation"])
async def simulation_endpoint(body: SimulationRequest):
    analytical_W = analytical_Wq = None
    try:
        analytic = solve_queue(model=body.model.value, lam=body.arrival_rate,
                               mu=body.service_rate, c=body.num_servers)
        analytical_W  = analytic.W
        analytical_Wq = analytic.Wq
    except Exception:
        pass

    try:
        result = run_simulation(
            model=body.model.value, lam=body.arrival_rate, mu=body.service_rate,
            c=body.num_servers, n_customers=body.num_customers,
            n_replications=body.num_replications, seed=body.seed,
            analytical_W=analytical_W, analytical_Wq=analytical_Wq,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Error in /simulation")
        raise HTTPException(status_code=500, detail="Internal computation error.")

    return SimulationResponse(
        utilization_mean=result.utilization_mean,
        L_mean=result.L_mean, Lq_mean=result.Lq_mean,
        W_mean=result.W_mean, Wq_mean=result.Wq_mean,
        W_ci_hw=result.W_ci_hw, Wq_ci_hw=result.Wq_ci_hw,
        wait_histogram_bins=result.wait_histogram_bins,
        wait_histogram_counts=result.wait_histogram_counts,
        analytical_W=result.analytical_W, analytical_Wq=result.analytical_Wq,
    )


# ── Optimization: LP ──────────────────────────────────────────────────────────

@router.post("/optimize/lp", response_model=LPResponse, tags=["optimization"])
async def lp_endpoint(body: LPRequest):
    """
    Solve a linear program and return the optimal solution with full
    sensitivity analysis: shadow prices, reduced costs, and ranging.
    """
    try:
        r = solve_lp(
            objective=body.objective,
            c_obj=body.c_obj,
            A_ub=body.A_ub,
            b_ub=body.b_ub,
            variable_names=body.variable_names,
            constraint_names=body.constraint_names,
        )
    except Exception:
        logger.exception("Error in /optimize/lp")
        raise HTTPException(status_code=500, detail="Internal computation error.")

    if r.status == "infeasible":
        raise HTTPException(status_code=400, detail="LP is infeasible: no solution satisfies all constraints.")
    if r.status == "unbounded":
        raise HTTPException(status_code=400, detail="LP is unbounded: objective can grow without limit.")

    return LPResponse(
        status=r.status, optimal_value=r.optimal_value,
        variables=r.variables, shadow_prices=r.shadow_prices,
        reduced_costs=r.reduced_costs, binding_constraints=r.binding_constraints,
        slacks=r.slacks, rhs_ranges=r.rhs_ranges, obj_ranges=r.obj_ranges,
    )


# ── Optimization: CPM/PERT ────────────────────────────────────────────────────

@router.post("/optimize/cpm", response_model=CPMResponse, tags=["optimization"])
async def cpm_endpoint(body: CPMRequest):
    """
    Critical Path Method (CPM) and PERT project scheduling.
    Returns earliest/latest start & finish times, float, and the critical path.
    """
    try:
        tasks_input = [
            {"name": t.name, "duration": t.duration,
             "variance": t.variance, "predecessors": t.predecessors}
            for t in body.tasks
        ]
        r = solve_cpm(tasks_input)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("Error in /optimize/cpm")
        raise HTTPException(status_code=500, detail="Internal computation error.")

    return CPMResponse(
        critical_path=r.critical_path, project_duration=r.project_duration,
        project_variance=r.project_variance, project_std=r.project_std,
        tasks=r.tasks,
    )


# ── Pro: Exports ───────────────────────────────────────────────────────────────

@router.post("/export/queuing/xlsx", tags=["exports"])
async def export_queuing_xlsx(
    body: ExportQueuingRequest,
    _license: str = Depends(require_pro),
) -> Response:
    """Export queuing results as an Excel workbook (Pro)."""
    content = build_queuing_xlsx(result=body.result, params=body.params)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="sim2sim-queuing.xlsx"'},
    )


@router.post("/export/queuing/pdf", tags=["exports"])
async def export_queuing_pdf(
    body: ExportQueuingRequest,
    _license: str = Depends(require_pro),
) -> Response:
    """Export queuing results as a PDF report (Pro)."""
    content = build_queuing_pdf(result=body.result, params=body.params)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="sim2sim-queuing.pdf"'},
    )


@router.post("/export/inventory/xlsx", tags=["exports"])
async def export_inventory_xlsx(
    body: ExportInventoryRequest,
    _license: str = Depends(require_pro),
) -> Response:
    """Export inventory results as an Excel workbook (Pro)."""
    content = build_inventory_xlsx(result=body.result, params=body.params, model_kind=body.model_kind)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="sim2sim-inventory.xlsx"'},
    )


@router.post("/export/inventory/pdf", tags=["exports"])
async def export_inventory_pdf(
    body: ExportInventoryRequest,
    _license: str = Depends(require_pro),
) -> Response:
    """Export inventory results as a PDF report (Pro)."""
    content = build_inventory_pdf(result=body.result, params=body.params, model_kind=body.model_kind)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="sim2sim-inventory.pdf"'},
    )


@router.post("/export/lp/xlsx", tags=["exports"])
async def export_lp_xlsx(
    body: ExportLPRequest,
    _license: str = Depends(require_pro),
) -> Response:
    """Export LP optimization results as an Excel workbook (Pro)."""
    content = build_lp_xlsx(result=body.result, params=body.params)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="sim2sim-lp.xlsx"'},
    )


@router.post("/export/lp/pdf", tags=["exports"])
async def export_lp_pdf(
    body: ExportLPRequest,
    _license: str = Depends(require_pro),
) -> Response:
    """Export LP optimization results as a PDF report (Pro)."""
    content = build_lp_pdf(result=body.result, params=body.params)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="sim2sim-lp.pdf"'},
    )


# ── Billing: license activation + Stripe webhook ──────────────────────────────

@router.post("/billing/activate", response_model=ActivateResponse, tags=["billing"])
async def billing_activate(body: ActivateRequest):
    """
    Activate a license key.  Returns tier/email and bumps the activation
    counter on the server.  Idempotent — a key can be activated repeatedly.
    """
    info = billing_licenses.activate_license(body.key)
    if info is None:
        return ActivateResponse(valid=False, message="Invalid or unknown license key.")
    return ActivateResponse(
        valid=True, tier=info.tier, email=info.email,
        activated_at=info.activated_at,
    )


@router.get("/billing/status", response_model=LicenseStatusResponse, tags=["billing"])
async def billing_status(x_license_key: str = Header(default="")):
    """
    Check current license status without recording an activation.  The
    frontend calls this on page load to decide whether to show Pro UI.
    """
    info = billing_licenses.validate_license(x_license_key)
    if info is None:
        return LicenseStatusResponse(valid=False, message="No valid license key.")
    return LicenseStatusResponse(
        valid=True, tier=info.tier, email=info.email,
        activation_count=info.activation_count,
    )


@router.post("/billing/webhook", response_model=WebhookAck, tags=["billing"])
async def billing_webhook(request: Request):
    """Stripe webhook receiver — see src/billing/webhook.py for details."""
    return await handle_stripe_webhook(request)


# ── AI Explanation ────────────────────────────────────────────────────────────

@router.post("/explain", response_model=ExplainResponse, tags=["ai"])
async def explain_endpoint(body: ExplainRequest):
    try:
        text, model_used = await explain(
            model_type=body.model_type,
            parameters=body.parameters,
            results=body.results,
        )
    except EnvironmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=503, detail="Invalid API key.")
    except anthropic.RateLimitError:
        raise HTTPException(status_code=429, detail="AI rate limit reached. Try again shortly.")
    except anthropic.APITimeoutError:
        raise HTTPException(status_code=504, detail="AI response timed out.")
    except anthropic.APIError:
        logger.exception("Anthropic API error")
        raise HTTPException(status_code=502, detail="AI service error.")
    except Exception:
        logger.exception("Unexpected error in /explain")
        raise HTTPException(status_code=500, detail="Internal error.")

    return ExplainResponse(explanation=text, model_used=model_used)
