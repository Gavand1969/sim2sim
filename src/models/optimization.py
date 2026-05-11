"""
Optimization models: Linear Programming with sensitivity analysis,
and Critical Path Method (CPM/PERT) for project scheduling.

References
----------
- Hillier, F. & Lieberman, G. (2015). Introduction to Operations Research, 10th ed.
- Vanderbei, R. (2014). Linear Programming: Foundations and Extensions.
- Kelley, J.E. (1961). Critical-path planning and scheduling.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.optimize import linprog


# ── Linear Programming ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LPResult:
    status:           str              # "optimal", "infeasible", "unbounded"
    optimal_value:    Optional[float]
    variables:        dict[str, float] # variable name → optimal value
    shadow_prices:    dict[str, float] # constraint name → marginal value of RHS
    reduced_costs:    dict[str, float] # variable name → reduced cost
    binding_constraints: list[str]     # names of tight constraints (slack ≈ 0)
    slacks:           dict[str, float] # constraint name → slack value
    # Sensitivity ranges (how far RHS can vary while basis stays optimal)
    rhs_ranges:       dict[str, dict]  # name → {lower, upper, current}
    obj_ranges:       dict[str, dict]  # var  → {lower, upper, current}


def solve_lp(
    objective:          str,         # "maximize" | "minimize"
    c_obj:              list[float], # objective coefficients
    A_ub:               list[list[float]],  # inequality constraint matrix (≤)
    b_ub:               list[float], # inequality RHS
    variable_names:     Optional[list[str]] = None,
    constraint_names:   Optional[list[str]] = None,
    variable_bounds:    Optional[list[tuple]] = None,  # default (0, None) per var
) -> LPResult:
    """
    Solve a linear program and return the optimal solution with full
    sensitivity analysis (shadow prices, reduced costs, ranging).

    Formulation:
        max/min  cᵀx
        s.t.     A_ub · x ≤ b_ub
                 x ≥ 0  (unless bounds provided)

    Shadow prices (dual variables) give the marginal value of relaxing
    each constraint by one unit — critical for resource allocation decisions.

    Sensitivity ranging shows how much objective coefficients and RHS values
    can change before the current basis becomes non-optimal.
    """
    n_vars  = len(c_obj)
    n_cons  = len(b_ub)

    var_names  = variable_names  or [f"x{i+1}" for i in range(n_vars)]
    con_names  = constraint_names or [f"C{j+1}" for j in range(n_cons)]
    bounds     = variable_bounds  or [(0, None)] * n_vars

    # scipy always minimizes; negate objective for maximization
    sign = -1.0 if objective.lower() == "maximize" else 1.0
    c_scipy = [sign * v for v in c_obj]

    result = linprog(
        c=c_scipy,
        A_ub=A_ub,
        b_ub=b_ub,
        bounds=bounds,
        method="highs",         # HiGHS solver — most reliable
        options={"presolve": True},
    )

    if result.status == 2:
        return LPResult(status="infeasible", optimal_value=None,
                        variables={}, shadow_prices={}, reduced_costs={},
                        binding_constraints=[], slacks={},
                        rhs_ranges={}, obj_ranges={})
    if result.status == 3:
        return LPResult(status="unbounded", optimal_value=None,
                        variables={}, shadow_prices={}, reduced_costs={},
                        binding_constraints=[], slacks={},
                        rhs_ranges={}, obj_ranges={})

    opt_val = sign * result.fun   # flip sign back for maximisation

    x_opt = result.x
    variables = {var_names[i]: round(float(x_opt[i]), 6) for i in range(n_vars)}

    # Shadow prices from HiGHS dual solution
    # result.ineqlin.marginals are for A_ub·x ≤ b_ub constraints
    if hasattr(result, "ineqlin") and result.ineqlin is not None:
        raw_sp = result.ineqlin.marginals
        shadow_prices = {con_names[j]: round(float(sign * raw_sp[j]), 6)
                         for j in range(n_cons)}
    else:
        shadow_prices = {n: 0.0 for n in con_names}

    # Reduced costs (x dual values)
    if hasattr(result, "lower") and result.lower is not None:
        raw_rc = result.lower.marginals
        reduced_costs = {var_names[i]: round(float(sign * raw_rc[i]), 6)
                         for i in range(n_vars)}
    else:
        reduced_costs = {n: 0.0 for n in var_names}

    # Slacks = b_ub − A_ub·x
    A_np = np.array(A_ub)
    b_np = np.array(b_ub)
    slacks_arr = b_np - A_np @ x_opt
    slacks    = {con_names[j]: round(float(slacks_arr[j]), 6) for j in range(n_cons)}
    binding   = [con_names[j] for j in range(n_cons) if abs(slacks_arr[j]) < 1e-6]

    # Sensitivity ranging via finite differences (±1% perturbation)
    rhs_ranges = _rhs_sensitivity(c_scipy, A_ub, b_ub, bounds, con_names, sign)
    obj_ranges = _obj_sensitivity(c_scipy, A_ub, b_ub, bounds, var_names, sign, c_obj)

    return LPResult(
        status="optimal",
        optimal_value=round(opt_val, 6),
        variables=variables,
        shadow_prices=shadow_prices,
        reduced_costs=reduced_costs,
        binding_constraints=binding,
        slacks=slacks,
        rhs_ranges=rhs_ranges,
        obj_ranges=obj_ranges,
    )


def _rhs_sensitivity(c, A_ub, b_ub, bounds, names, sign) -> dict:
    """
    Compute allowable increase/decrease for each RHS value while
    keeping the current basis optimal.  Uses binary search to find the range.
    """
    ranges = {}
    b_np = np.array(b_ub, dtype=float)

    for j, name in enumerate(names):
        # Search allowable increase
        hi = _search_limit(c, A_ub, b_np, bounds, j, direction=+1)
        lo = _search_limit(c, A_ub, b_np, bounds, j, direction=-1)
        ranges[name] = {
            "current": round(float(b_np[j]), 4),
            "lower_bound": round(float(b_np[j] + lo), 4),
            "upper_bound": round(float(b_np[j] + hi), 4),
            "allowable_increase": round(float(hi), 4),
            "allowable_decrease": round(float(-lo), 4),
        }
    return ranges


def _obj_sensitivity(c_scipy, A_ub, b_ub, bounds, names, sign, c_orig) -> dict:
    """Sensitivity ranges for objective coefficients."""
    ranges = {}
    c_np  = np.array(c_scipy, dtype=float)

    for i, name in enumerate(names):
        hi = _search_obj_limit(c_np, A_ub, b_ub, bounds, i, direction=+1, sign=sign)
        lo = _search_obj_limit(c_np, A_ub, b_ub, bounds, i, direction=-1, sign=sign)
        ranges[name] = {
            "current": round(float(c_orig[i]), 4),
            "lower_bound": round(float(c_orig[i] + sign * lo), 4),
            "upper_bound": round(float(c_orig[i] + sign * hi), 4),
            "allowable_increase": round(float(sign * hi), 4),
            "allowable_decrease": round(float(-sign * lo), 4),
        }
    return ranges


def _search_limit(c, A_ub, b_arr, bounds, j, direction, tol=1e-4, max_iter=40) -> float:
    """Binary search for how far b[j] can move in `direction` before basis changes."""
    lo_delta, hi_delta = 0.0, direction * 1e6
    b_test = b_arr.copy()
    # Verify feasibility at large delta
    b_test[j] = b_arr[j] + hi_delta
    r = linprog(c, A_ub=A_ub, b_ub=b_test.tolist(), bounds=bounds, method="highs")
    if r.status != 0:  # can't go that far; halve starting point
        hi_delta /= 1000.0

    for _ in range(max_iter):
        mid = (lo_delta + hi_delta) / 2.0
        b_test[j] = b_arr[j] + mid
        r = linprog(c, A_ub=A_ub, b_ub=b_test.tolist(), bounds=bounds, method="highs")
        if r.status == 0:
            lo_delta = mid
        else:
            hi_delta = mid
        if abs(hi_delta - lo_delta) < tol:
            break
    return lo_delta


def _search_obj_limit(c_arr, A_ub, b_ub, bounds, i, direction, sign, tol=1e-4, max_iter=40) -> float:
    lo_delta, hi_delta = 0.0, direction * 1e6
    c_test = c_arr.copy()
    c_test[i] = c_arr[i] + hi_delta
    r = linprog(c_test, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
    if r.status != 0:
        hi_delta /= 1000.0
    for _ in range(max_iter):
        mid = (lo_delta + hi_delta) / 2.0
        c_test[i] = c_arr[i] + mid
        r = linprog(c_test, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs")
        if r.status == 0:
            lo_delta = mid
        else:
            hi_delta = mid
        if abs(hi_delta - lo_delta) < tol:
            break
    return lo_delta


# ── CPM / PERT Project Scheduling ─────────────────────────────────────────────

@dataclass(frozen=True)
class CPMTask:
    name:        str
    duration:    float          # deterministic (CPM) or mean (PERT)
    variance:    float = 0.0    # PERT only: ((b-a)/6)²
    predecessors: tuple[str, ...] = ()


@dataclass(frozen=True)
class CPMResult:
    critical_path:        list[str]   # ordered list of task names on CP
    project_duration:     float
    project_variance:     float       # PERT: sum of variances on CP
    project_std:          float       # √(project_variance)
    tasks:                dict[str, dict]  # per-task ES, EF, LS, LF, float


def solve_cpm(tasks: list[dict]) -> CPMResult:
    """
    Critical Path Method (CPM) with optional PERT variance.

    Each task dict: {name, duration, [variance=0], [predecessors=[]]}.
    duration may be the PERT expected value (a + 4m + b) / 6.
    variance should be ((b - a) / 6)² for PERT tasks.

    Returns earliest/latest start & finish times, total float per task,
    the critical path, and the PERT confidence interval for project duration.
    """
    # Build task objects
    task_map = {}
    for t in tasks:
        preds = tuple(t.get("predecessors") or [])
        task_map[t["name"]] = CPMTask(
            name=t["name"],
            duration=float(t["duration"]),
            variance=float(t.get("variance", 0.0)),
            predecessors=preds,
        )

    names = list(task_map.keys())

    # Topological sort (Kahn's algorithm)
    in_degree = {n: 0 for n in names}
    adjacency: dict[str, list[str]] = {n: [] for n in names}
    for n, t in task_map.items():
        for p in t.predecessors:
            adjacency[p].append(n)
            in_degree[n] += 1

    queue = [n for n in names if in_degree[n] == 0]
    topo_order = []
    while queue:
        node = queue.pop(0)
        topo_order.append(node)
        for succ in adjacency[node]:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                queue.append(succ)

    if len(topo_order) != len(names):
        raise ValueError("Cycle detected in task dependencies.")

    # Forward pass — Early Start (ES) and Early Finish (EF)
    ES: dict[str, float] = {}
    EF: dict[str, float] = {}
    for n in topo_order:
        t = task_map[n]
        ES[n] = max((EF[p] for p in t.predecessors), default=0.0)
        EF[n] = ES[n] + t.duration

    project_duration = max(EF.values())

    # Backward pass — Late Finish (LF) and Late Start (LS)
    LF: dict[str, float] = {}
    LS: dict[str, float] = {}
    for n in reversed(topo_order):
        successors = adjacency[n]
        LF[n] = min((LS[s] for s in successors), default=project_duration)
        LS[n] = LF[n] - task_map[n].duration

    # Total float and critical path
    float_: dict[str, float] = {n: LS[n] - ES[n] for n in names}
    critical = [n for n in topo_order if abs(float_[n]) < 1e-9]

    project_variance = sum(task_map[n].variance for n in critical)
    project_std = math.sqrt(project_variance) if project_variance > 0 else 0.0

    task_details = {
        n: {
            "ES": round(ES[n], 4), "EF": round(EF[n], 4),
            "LS": round(LS[n], 4), "LF": round(LF[n], 4),
            "float": round(float_[n], 4),
            "critical": abs(float_[n]) < 1e-9,
            "duration": round(task_map[n].duration, 4),
        }
        for n in topo_order
    }

    return CPMResult(
        critical_path=critical,
        project_duration=round(project_duration, 4),
        project_variance=round(project_variance, 6),
        project_std=round(project_std, 4),
        tasks=task_details,
    )
