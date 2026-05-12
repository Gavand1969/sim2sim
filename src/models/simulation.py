"""
Monte Carlo discrete-event simulation engine for queuing systems.

Design
------
Each replication is a full, independent simulation of N customers through a
c-server FCFS queue with Poisson arrivals and (optionally) exponential or
deterministic service.  We use the standard batch-means estimator across
replications to form 95% confidence intervals.

The simulation uses the event-list (next-event) approach:
  - Events: {ARRIVAL, DEPARTURE}
  - State: number in system, time each server becomes free

This is intentionally written in pure Python + NumPy (no SimPy) so there are
zero hidden abstractions that could mask bugs.

References
----------
- Law, A. & Kelton, D. (2000). Simulation Modeling and Analysis, 3rd ed.
- Nelson, B. (2016). Foundations and Methods of Stochastic Simulation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy import stats


@dataclass
class SimulationResult:
    utilization_mean: float
    L_mean:           float
    Lq_mean:          float
    W_mean:           float
    Wq_mean:          float
    W_ci_hw:          float   # 95% CI half-width for W
    Wq_ci_hw:         float   # 95% CI half-width for Wq
    wait_histogram_bins:   list[float]
    wait_histogram_counts: list[int]
    analytical_W:     Optional[float] = None
    analytical_Wq:    Optional[float] = None


def _run_single_replication(
    lam: float,
    mu: float,
    c: int,
    n_customers: int,
    rng: np.random.Generator,
    deterministic_service: bool = False,
) -> tuple[float, float, float, float, list[float]]:
    """
    Simulate one replication.  Returns (util, L, Lq, W, Wq, wait_times_in_queue).

    Algorithm (event-list, next-event):
    ------------------------------------
    server_free_at[j] = earliest time server j is free (j = 0..c-1)
    We advance customer-by-customer because with Poisson arrivals and FCFS
    we can compute each customer's arrival, queue-entry, and departure
    analytically without maintaining a full event heap.
    """
    # Burn-in: discard first 20% of customers (or at least 100) to reach
    # steady state.  10% was too aggressive for ρ > 0.8 systems.
    n_warmup    = max(100, n_customers // 5)
    n_total     = n_customers + n_warmup

    server_free = np.zeros(c)   # time each server becomes free
    arrival     = 0.0           # current arrival time

    wait_times  = []            # Wq per customer (post warmup)
    sojourn     = []            # W per customer (post warmup)
    busy_total  = 0.0           # total server-busy time (post warmup)
    sim_start   = None          # clock at start of measurement window

    for k in range(n_total):
        # Inter-arrival: Exponential(lam)
        ia_time  = rng.exponential(1.0 / lam)
        arrival += ia_time

        # Service time: Exponential(mu) or Deterministic 1/mu
        if deterministic_service:
            svc = 1.0 / mu
        else:
            svc = rng.exponential(1.0 / mu)

        # Assign to earliest-free server
        j          = int(np.argmin(server_free))
        start_svc  = max(arrival, server_free[j])
        depart     = start_svc + svc
        server_free[j] = depart

        wq = start_svc - arrival   # wait in queue
        w  = depart    - arrival   # sojourn time

        if k == n_warmup:
            # First post-warmup customer: this arrival starts the
            # measurement window for utilisation accounting.
            sim_start  = arrival
            busy_total = 0.0

        if k >= n_warmup:
            wait_times.append(wq)
            sojourn.append(w)
            busy_total += svc

    sim_duration = arrival - sim_start if sim_start is not None else 1.0

    W_rep  = float(np.mean(sojourn))
    Wq_rep = float(np.mean(wait_times))
    L_rep  = float(np.mean(sojourn)) * lam   # Little's Law
    Lq_rep = float(np.mean(wait_times)) * lam
    util   = busy_total / (c * sim_duration) if sim_duration > 0 else 0.0

    return util, L_rep, Lq_rep, W_rep, Wq_rep, wait_times


def run_simulation(
    model:           str,
    lam:             float,
    mu:              float,
    c:               int,
    n_customers:     int,
    n_replications:  int,
    seed:            Optional[int] = None,
    analytical_W:    Optional[float] = None,
    analytical_Wq:   Optional[float] = None,
) -> SimulationResult:
    """
    Run `n_replications` independent replications and pool results.
    Returns point estimates + 95% CI half-widths (t-distribution).
    """
    deterministic = (model == "MD1")
    rng_seed = seed if seed is not None else np.random.SeedSequence().entropy

    W_reps   = []
    Wq_reps  = []
    util_reps = []
    L_reps   = []
    Lq_reps  = []
    all_waits: list[float] = []

    # Each replication gets its own independent RNG stream (SeedSequence child)
    ss = np.random.SeedSequence(rng_seed)
    child_seeds = ss.spawn(n_replications)

    for i in range(n_replications):
        rng = np.random.default_rng(child_seeds[i])
        util, L, Lq, W, Wq, waits = _run_single_replication(
            lam, mu, c, n_customers, rng, deterministic
        )
        W_reps.append(W)
        Wq_reps.append(Wq)
        util_reps.append(util)
        L_reps.append(L)
        Lq_reps.append(Lq)
        all_waits.extend(waits[:500])   # cap histogram data

    # Point estimates
    W_mean   = float(np.mean(W_reps))
    Wq_mean  = float(np.mean(Wq_reps))
    L_mean   = float(np.mean(L_reps))
    Lq_mean  = float(np.mean(Lq_reps))
    util_mean = float(np.mean(util_reps))

    # 95% CI half-widths via t-distribution (n_replications - 1 df)
    t_crit = stats.t.ppf(0.975, df=max(1, n_replications - 1))
    W_ci   = t_crit * float(np.std(W_reps,  ddof=1)) / math.sqrt(n_replications)
    Wq_ci  = t_crit * float(np.std(Wq_reps, ddof=1)) / math.sqrt(n_replications)

    # Histogram of queue wait times (all_waits pooled)
    waits_arr = np.array(all_waits, dtype=float)
    n_bins    = min(40, max(10, len(waits_arr) // 50))
    counts, edges = np.histogram(waits_arr, bins=n_bins)

    return SimulationResult(
        utilization_mean=round(util_mean, 6),
        L_mean=round(L_mean, 6),
        Lq_mean=round(Lq_mean, 6),
        W_mean=round(W_mean, 6),
        Wq_mean=round(Wq_mean, 6),
        W_ci_hw=round(W_ci, 6),
        Wq_ci_hw=round(Wq_ci, 6),
        wait_histogram_bins=edges.tolist(),
        wait_histogram_counts=counts.tolist(),
        analytical_W=analytical_W,
        analytical_Wq=analytical_Wq,
    )
