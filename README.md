# Sim2Sim — Operations Research Platform

[![Tests](https://github.com/Gavand1969/sim2sim/actions/workflows/ci.yml/badge.svg)](https://github.com/Gavand1969/sim2sim/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)

**Live demo:** *(coming soon — deployment in progress)*

PhD-level operations research in your browser — queuing theory, inventory optimization, Monte Carlo simulation, and linear programming with AI-generated insights powered by Claude.

Arena costs $5,000/year. AnyLogic costs $7,000/year. Sim2Sim is free to use and has an optional one-time **Pro** upgrade for advanced features (scenario library, Excel/PDF export, batch API).

![Sim2Sim Screenshot](docs/screenshot.png)

---

## What It Does

You input system parameters, get exact analytical results with interactive charts, and Claude Haiku explains what the numbers mean in plain English with formula citations, reliability warnings, and specific recommendations.

---

## Models

### Queuing Theory — 9 Models

| Model | Method | Key Output |
|-------|--------|------------|
| **M/M/1** | Closed-form | W, Wq, L, Lq, P(N=n) |
| **M/M/c** | Erlang-C formula | P(wait), multi-server utilization |
| **M/D/1** | P-K formula (Cs²=0) | Lq = ρ²/2(1−ρ) — half of M/M/1 |
| **M/G/1** | Pollaczek-Khinchine | Lq from service-time variance |
| **G/G/1** | Kingman heavy-traffic | Approx Wq for general distributions |
| **M/M/c/K** | Finite buffer, c servers | Blocking probability, effective throughput |
| **M/M/1/K** | Finite capacity, 1 server | Closed-form geometric series |
| **M/M/∞** | Infinite servers | Poisson steady-state, Wq = 0 always |
| **M[X]/M/1** | Batch arrivals | P-K bulk formula |

All models include: utilization (ρ), L, Lq, W, Wq, P₀, Little's Law sanity check, queue-length distribution chart.

### Inventory — 6 Models

| Model | Type | Key Formula |
|-------|------|-------------|
| **EOQ** | Deterministic | Q* = √(2KD/h), TC* = √(2KDh) |
| **EOQ + Backorders** | Planned shortages | Q* = EOQ · √((h+π)/π) |
| **EPQ** | Production run | Q* = √(2KD / h(1−D/P)) |
| **Newsvendor** | Stochastic, single-period | Q* = F⁻¹(CR), CR = (p−c)/(p−s) |
| **Reorder Point (Q,r)** | Stochastic, continuous review | r = DL + z·σ_L |
| **Base Stock** | Stochastic, order-up-to | S* = μ_L + z·σ_L |

### Optimization

| Model | Description |
|-------|-------------|
| **Linear Programming** | HiGHS solver via SciPy — shadow prices, reduced costs, RHS ranging, objective ranging |
| **CPM / PERT** | Critical path, float, earliest/latest start & finish, PERT variance |

### Monte Carlo Simulation
Discrete-event simulation built from scratch (no SimPy):
- Independent replications with warm-up period
- 95% confidence intervals via t-distribution
- Empirical wait-time histogram overlaid with analytical solution

### Scenario Comparison
Run 2–8 queuing parameter sets in parallel and compare Wq, utilization, and queue length side-by-side in a grouped bar chart.

---

## AI Insights

Every result is explained by Claude Haiku. The AI:
- Cites exact formulas (Little's Law, P-K, Kingman, Wilson)
- Flags reliability warnings (ρ > 0.85, near-degenerate LP, small D/P ratio)
- Gives 2–3 specific, actionable recommendations
- Cross-references results across models

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, Pydantic v2 |
| Math | NumPy, SciPy (HiGHS LP solver) |
| AI | Anthropic Claude Haiku |
| Frontend | Vanilla JS, Chart.js 4, KaTeX (LaTeX formulas) |
| Security | slowapi rate limiting, CSP headers, input validation |
| Tests | pytest — 57 tests, 100% passing |
| Deploy | Replit |

---

## Running Locally

```bash
git clone https://github.com/Gavand1969/sim2sim.git
cd sim2sim
pip install -r requirements.txt
cp .env.example .env        # add your ANTHROPIC_API_KEY
uvicorn main:app --reload --port 8080
```

Open `http://localhost:8080`

The app runs fully without an API key — AI insights are simply disabled.

---

## API

Interactive docs at `/api/docs` when running.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/queuing` | POST | Analytical queuing (9 models) |
| `/api/queuing/compare` | POST | Parallel scenario comparison |
| `/api/inventory/eoq` | POST | EOQ model |
| `/api/inventory/eoq-backorder` | POST | EOQ with planned backorders |
| `/api/inventory/epq` | POST | Economic Production Quantity |
| `/api/inventory/newsvendor` | POST | Newsvendor critical ratio |
| `/api/inventory/reorder-point` | POST | (Q,r) continuous review |
| `/api/inventory/base-stock` | POST | Base stock order-up-to policy |
| `/api/simulation` | POST | Monte Carlo simulation |
| `/api/optimize/lp` | POST | Linear program with sensitivity |
| `/api/optimize/cpm` | POST | CPM/PERT project scheduling |
| `/api/explain` | POST | Claude AI explanation |
| `/api/health` | GET | Health check |

---

## Project Structure

```
sim2sim/
├── main.py                    # FastAPI app + static file serving
├── src/
│   ├── models/
│   │   ├── queuing.py         # 9 queuing models
│   │   ├── inventory.py       # 6 inventory models
│   │   ├── optimization.py    # LP + CPM/PERT
│   │   └── simulation.py      # Monte Carlo engine
│   ├── api/
│   │   ├── routes.py          # All REST endpoints
│   │   ├── schemas.py         # Pydantic request/response models
│   │   └── middleware.py      # Rate limiting + security headers
│   └── ai/
│       └── explainer.py       # Claude API integration
├── static/                    # Single-page frontend (no build step)
│   ├── index.html             # KaTeX + Chart.js + 4-tab layout
│   ├── css/style.css
│   └── js/
│       ├── app.js             # All model handlers + builders
│       ├── charts.js          # Chart.js wrappers
│       └── api.js             # Fetch wrapper
└── tests/                     # 57 unit + integration tests
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | No | Enables AI insights (Claude Haiku) |
| `RATE_LIMIT_PER_MINUTE` | No | Default: 20/min per IP |
| `ENVIRONMENT` | No | `development` or `production` |

---

## License

MIT — see [LICENSE](LICENSE)
