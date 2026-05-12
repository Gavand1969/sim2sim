"""
Analytical queuing models: M/M/1, M/M/c, M/D/1, M/G/1,
M/M/c/K, M/M/1/K, M/M/∞, G/G/1, M[X]/M/1.

All results use exact closed-form solutions where available.
Heavy-traffic approximations (Kingman, bulk arrivals) are clearly noted.
Little's Law (L = λW) is verified numerically as a built-in sanity check.

References
----------
- Kleinrock, L. (1975). Queueing Systems, Vol. 1.
- Gross, D. & Harris, C. (1998). Fundamentals of Queueing Theory, 3rd ed.
- Tijms, H. (2003). A First Course in Stochastic Models.
- Kingman, J.F.C. (1962). Some inequalities for the queue G/G/1.
- Neuts, M.F. (1981). Matrix-Geometric Solutions in Stochastic Models.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class QueuingResult:
    model:             str
    utilization:       float
    L:                 float
    Lq:                float
    W:                 float
    Wq:                float
    P0:                float
    P_wait:            Optional[float]
    prob_dist:         list[float]
    little_law_check:  float
    # Finite-capacity models
    blocking_prob:     Optional[float] = None   # P(K) — probability of loss
    effective_lam:     Optional[float] = None   # λ(1-P_K) — actual throughput
    # Model-specific notes
    notes:             Optional[str]   = None


# ── Internal helpers ──────────────────────────────────────────────────────────

def _little_law_residual(L: float, lam: float, W: float) -> float:
    """Relative residual |L − λW| / max(|L|, 1).
    Using a relative scale keeps the diagnostic meaningful at high
    utilisation where L can be very large in absolute terms.
    Values near 0 confirm Little's Law holds for this model.
    """
    return abs(L - lam * W) / max(abs(L), 1.0)


def _erlang_c(c: int, a: float) -> float:
    """
    Erlang-C probability C(c, a) = P(arriving customer must wait).
    Numerically stable recursive formula (log-space, no factorial overflow).
    a = λ/μ is offered load; ρ = a/c is per-server utilization.
    """
    rho   = a / c
    log_a = math.log(a) if a > 0 else -math.inf
    log_terms = [k * log_a - math.lgamma(k + 1) for k in range(c)]
    max_log   = max(log_terms)
    partial   = sum(math.exp(t - max_log) for t in log_terms) * math.exp(max_log)
    log_last  = c * log_a - math.lgamma(c + 1) - math.log(1.0 - rho)
    last_term = math.exp(log_last)
    p0        = 1.0 / (partial + last_term)
    return float(last_term * p0)


def _mm1_prob_dist(rho: float, n_max: int = 20) -> list[float]:
    """P(N=n) = (1-ρ)·ρⁿ for M/M/1."""
    return [(1.0 - rho) * (rho ** n) for n in range(n_max + 1)]


def _mmc_prob_dist(c: int, a: float, P0: float, n_max: int = 20) -> list[float]:
    log_a    = math.log(a) if a > 0 else -math.inf
    log_cfact = math.lgamma(c + 1)
    dist = []
    for n in range(n_max + 1):
        if n < c:
            log_p = n * log_a - math.lgamma(n + 1)
        else:
            log_p = n * log_a - log_cfact - (n - c) * math.log(c)
        dist.append(P0 * math.exp(log_p))
    return dist


# ── M/M/1 ─────────────────────────────────────────────────────────────────────

def solve_mm1(lam: float, mu: float) -> QueuingResult:
    """Exact M/M/1. ρ = λ/μ < 1."""
    rho = lam / mu
    L   = rho / (1.0 - rho)
    Lq  = rho ** 2 / (1.0 - rho)
    W   = 1.0 / (mu - lam)
    Wq  = lam / (mu * (mu - lam))
    return QueuingResult(
        model="M/M/1", utilization=rho, L=L, Lq=Lq, W=W, Wq=Wq,
        P0=1.0 - rho, P_wait=None, prob_dist=_mm1_prob_dist(rho),
        little_law_check=_little_law_residual(L, lam, W),
    )


# ── M/M/c ─────────────────────────────────────────────────────────────────────

def solve_mmc(lam: float, mu: float, c: int) -> QueuingResult:
    """Exact M/M/c via Erlang-C formula."""
    a   = lam / mu
    rho = a / c
    ec  = _erlang_c(c, a)
    log_a    = math.log(a)
    log_last = c * log_a - math.lgamma(c + 1) - math.log(1.0 - rho)
    P0 = ec / math.exp(log_last)
    Lq = ec * rho / (1.0 - rho)
    L  = Lq + a
    Wq = Lq / lam
    W  = Wq + 1.0 / mu
    return QueuingResult(
        model=f"M/M/{c}", utilization=rho, L=L, Lq=Lq, W=W, Wq=Wq,
        P0=P0, P_wait=ec, prob_dist=_mmc_prob_dist(c, a, P0),
        little_law_check=_little_law_residual(L, lam, W),
    )


# ── M/D/1 ─────────────────────────────────────────────────────────────────────

def solve_md1(lam: float, mu: float) -> QueuingResult:
    """Exact M/D/1 via P-K formula with Cs² = 0. Lq exactly half of M/M/1."""
    rho = lam / mu
    Lq  = rho ** 2 / (2.0 * (1.0 - rho))
    L   = Lq + rho
    Wq  = Lq / lam
    W   = Wq + 1.0 / mu
    return QueuingResult(
        model="M/D/1", utilization=rho, L=L, Lq=Lq, W=W, Wq=Wq,
        P0=1.0 - rho, P_wait=None, prob_dist=_mm1_prob_dist(rho),
        little_law_check=_little_law_residual(L, lam, W),
    )


# ── M/G/1 ─────────────────────────────────────────────────────────────────────

def solve_mg1(lam: float, mu: float, cs_sq: float) -> QueuingResult:
    """
    Exact mean-value M/G/1 via Pollaczek-Khinchine formula.
    cs_sq = Cs² = Var(S)/E[S]²; 1→M/M/1, 0→M/D/1, >1→high-variance.
    """
    rho  = lam / mu
    E_S2 = (1.0 / mu) ** 2 * (1.0 + cs_sq)
    Lq   = (lam ** 2 * E_S2) / (2.0 * (1.0 - rho))
    L    = Lq + rho
    Wq   = Lq / lam
    W    = Wq + 1.0 / mu
    return QueuingResult(
        model=f"M/G/1 (Cs²={cs_sq:.2f})", utilization=rho, L=L, Lq=Lq, W=W, Wq=Wq,
        P0=1.0 - rho, P_wait=None, prob_dist=_mm1_prob_dist(rho),
        little_law_check=_little_law_residual(L, lam, W),
    )


# ── M/M/c/K ───────────────────────────────────────────────────────────────────

def solve_mmck(lam: float, mu: float, c: int, K: int) -> QueuingResult:
    """
    Exact M/M/c/K queue: c servers, maximum K customers in system (c ≤ K).
    Arriving customers are blocked (lost) when system is full.

    P(n) = P0 · aⁿ/n!              for 0 ≤ n ≤ c
    P(n) = P0 · aⁿ/(c! · c^(n-c)) for c < n ≤ K
    Blocking probability = P(K).
    Effective throughput λ_eff = λ·(1 − P(K)).
    """
    a    = lam / mu
    log_a = math.log(a) if a > 0 else -math.inf
    log_cfact = math.lgamma(c + 1)

    unnorm = []
    for n in range(K + 1):
        if n <= c:
            lp = n * log_a - math.lgamma(n + 1)
        else:
            lp = n * log_a - log_cfact - (n - c) * math.log(c)
        unnorm.append(math.exp(lp))

    total = sum(unnorm)
    P     = [u / total for u in unnorm]
    P0    = P[0]
    P_K   = P[K]

    lam_eff = lam * (1.0 - P_K)

    L   = sum(n * P[n] for n in range(K + 1))
    Lq  = sum((n - c) * P[n] for n in range(c + 1, K + 1))
    W   = L  / lam_eff if lam_eff > 0 else 0.0
    Wq  = Lq / lam_eff if lam_eff > 0 else 0.0
    rho = lam_eff / (c * mu)   # actual utilization

    prob_dist = P[:21] + [0.0] * max(0, 21 - len(P))

    return QueuingResult(
        model=f"M/M/{c}/{K}", utilization=rho, L=L, Lq=Lq, W=W, Wq=Wq,
        P0=P0, P_wait=None, prob_dist=prob_dist,
        little_law_check=_little_law_residual(L, lam_eff, W),
        blocking_prob=P_K, effective_lam=lam_eff,
    )


# ── M/M/1/K ───────────────────────────────────────────────────────────────────

def solve_mm1k(lam: float, mu: float, K: int) -> QueuingResult:
    """
    Exact M/M/1/K queue: 1 server, capacity K (queue + server).
    Closed-form solution via finite geometric series.
    """
    rho = lam / mu

    if abs(rho - 1.0) < 1e-10:
        # ρ = 1: uniform distribution
        P = [1.0 / (K + 1)] * (K + 1)
    else:
        # P(n) = (1-ρ)·ρⁿ / (1-ρ^(K+1))
        denom = 1.0 - rho ** (K + 1)
        P = [(1.0 - rho) * rho ** n / denom for n in range(K + 1)]

    P0  = P[0]
    P_K = P[K]
    lam_eff = lam * (1.0 - P_K)

    L   = sum(n * P[n] for n in range(K + 1))
    Lq  = sum((n - 1) * P[n] for n in range(2, K + 1))
    W   = L  / lam_eff if lam_eff > 0 else 0.0
    Wq  = Lq / lam_eff if lam_eff > 0 else 0.0
    util = lam_eff / mu

    prob_dist = P[:21] + [0.0] * max(0, 21 - len(P))

    return QueuingResult(
        model=f"M/M/1/{K}", utilization=util, L=L, Lq=Lq, W=W, Wq=Wq,
        P0=P0, P_wait=None, prob_dist=prob_dist,
        little_law_check=_little_law_residual(L, lam_eff, W),
        blocking_prob=P_K, effective_lam=lam_eff,
    )


# ── M/M/∞ ─────────────────────────────────────────────────────────────────────

def solve_mminf(lam: float, mu: float) -> QueuingResult:
    """
    Exact M/M/∞ (infinite-server / self-service) queue.
    Every arrival finds a free server; no queuing ever occurs.
    Steady-state queue length is Poisson(a), a = λ/μ.
    """
    a  = lam / mu
    P0 = math.exp(-a)
    L  = a
    Lq = 0.0
    W  = 1.0 / mu
    Wq = 0.0
    # rho per server → 0 in the limit; report a/∞ as 0 by convention
    rho = 0.0

    # P(N=n) = e^{-a} · aⁿ/n! — Poisson PMF
    prob_dist = [math.exp(-a) * a ** n / math.exp(math.lgamma(n + 1))
                 for n in range(21)]

    return QueuingResult(
        model="M/M/∞", utilization=rho, L=L, Lq=Lq, W=W, Wq=Wq,
        P0=P0, P_wait=0.0, prob_dist=prob_dist,
        little_law_check=_little_law_residual(L, lam, W),
        notes="No queuing: every customer finds a free server immediately.",
    )


# ── G/G/1 — Kingman's formula ─────────────────────────────────────────────────

def solve_gg1(lam: float, mu: float, ca_sq: float, cs_sq: float) -> QueuingResult:
    """
    Heavy-traffic approximation for G/G/1 via Kingman's (VCA) formula.

    E[Wq] ≈ (ρ/(1−ρ)) · (Ca² + Cs²)/2 · (1/μ)

    where Ca² = squared CV of interarrival times (1 = Poisson/exponential),
          Cs² = squared CV of service times     (1 = exponential, 0 = deterministic).

    Exact for M/M/1 (Ca²=Cs²=1) and asymptotically correct in heavy traffic.
    Accuracy degrades at low utilization — use M/G/1 for light traffic.

    Reference: Kingman (1962); Whitt (1993) for the full interpolation.
    """
    rho = lam / mu
    Wq  = (rho / (1.0 - rho)) * (ca_sq + cs_sq) / 2.0 / mu
    W   = Wq + 1.0 / mu
    Lq  = lam * Wq
    L   = lam * W

    return QueuingResult(
        model=f"G/G/1 (Ca²={ca_sq:.2f}, Cs²={cs_sq:.2f})",
        utilization=rho, L=L, Lq=Lq, W=W, Wq=Wq,
        P0=1.0 - rho, P_wait=None, prob_dist=_mm1_prob_dist(rho),
        little_law_check=_little_law_residual(L, lam, W),
        notes="Kingman heavy-traffic approximation. Most accurate when ρ > 0.7.",
    )


# ── M[X]/M/1 — bulk arrivals ──────────────────────────────────────────────────

def solve_bulk_mm1(lam: float, mu: float, batch_size: int) -> QueuingResult:
    """
    M[X]/M/1: batches of fixed size b arrive at Poisson rate λ.
    Total arrival rate of individuals: λ_ind = λ·b.
    ρ = λ·b/μ  (caller guarantees ρ < 1).

    P-K mean-value formula for bulk arrivals:
      Lq = ρ²/(1−ρ) + λ·b·(b−1)/(2·μ·(1−ρ))

    The first term is the standard M/M/1 Lq; the second accounts for
    within-batch correlation.

    Reference: Gross & Harris (1998), §3.4.
    """
    b       = batch_size
    rho     = lam * b / mu
    lam_ind = lam * b          # effective individual arrival rate

    Lq = rho ** 2 / (1.0 - rho) + lam * b * (b - 1) / (2.0 * mu * (1.0 - rho))
    L  = Lq + rho
    Wq = Lq / lam_ind
    W  = Wq + 1.0 / mu

    return QueuingResult(
        model=f"M[{b}]/M/1", utilization=rho, L=L, Lq=Lq, W=W, Wq=Wq,
        P0=1.0 - rho, P_wait=None, prob_dist=_mm1_prob_dist(rho),
        little_law_check=_little_law_residual(L, lam_ind, W),
        notes=f"Batches of {b} arrive at rate λ={lam}. "
              f"Individual arrival rate = {lam_ind:.2f}.",
    )


# ── Dispatcher ────────────────────────────────────────────────────────────────

def solve_queue(
    model:      str,
    lam:        float,
    mu:         float,
    c:          int   = 1,
    cs_sq:      float = 1.0,
    ca_sq:      float = 1.0,
    K:          int   = 10,
    batch_size: int   = 1,
) -> QueuingResult:
    """Route to the correct analytical solver."""
    match model:
        case "MM1":     return solve_mm1(lam, mu)
        case "MMC":     return solve_mmc(lam, mu, c)
        case "MD1":     return solve_md1(lam, mu)
        case "MG1":     return solve_mg1(lam, mu, cs_sq)
        case "MMCK":    return solve_mmck(lam, mu, c, K)
        case "MM1K":    return solve_mm1k(lam, mu, K)
        case "MMINF":   return solve_mminf(lam, mu)
        case "GG1":     return solve_gg1(lam, mu, ca_sq, cs_sq)
        case "BULK":    return solve_bulk_mm1(lam, mu, batch_size)
        case _:         raise ValueError(f"Unknown queue model: {model!r}")
