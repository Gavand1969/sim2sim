# Sim2Real — Operations Research Simulator

An interactive web application that solves operations research models analytically and via Monte Carlo simulation, with AI-generated business insights powered by Claude.

**Live demo:** *(add your Replit URL here)*

---

## What It Does

Most operations research tools are either ancient academic software or expensive enterprise products. Sim2Real makes these models fast, visual, and explainable to anyone.

You input your system parameters, get exact analytical results with interactive charts, and an AI explains what the numbers mean for your business in plain English.

---

## Models

### Queuing Theory
Exact closed-form solutions for four queue models:

| Model | Description |
|-------|-------------|
| **M/M/1** | Single server, Poisson arrivals, exponential service |
| **M/M/c** | Multi-server with Erlang-C formula |
| **M/D/1** | Deterministic service time (P-K formula, Cs²=0) |
| **M/G/1** | General service via Pollaczek-Khinchine mean-value formula |

Outputs: utilization (ρ), avg customers in system (L), avg queue length (Lq), avg sojourn time (W), avg wait time (Wq), P₀, Erlang-C probability, queue-length distribution chart.

### Inventory Models
| Model | Description |
|-------|-------------|
| **EOQ** | Wilson formula — minimises ordering + holding cost |
| **Newsvendor** | Single-period stochastic model with Normal, Poisson, or Uniform demand |

Outputs: optimal order quantity, total cost curve, expected profit curve, fill rate, stockout risk.

### Monte Carlo Simulation
Discrete-event simulation engine built from scratch (no SimPy):
- Independent replications with warm-up period
- 95% confidence intervals via t-distribution
- Empirical wait-time histogram
- Side-by-side comparison with analytical solution

---

## AI Insights

Every result can be explained in plain English by Claude Haiku. The AI summarises key metrics, flags bottlenecks, and gives concrete recommendations — bridging the gap between quantitative output and business decisions.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, FastAPI, Pydantic v2 |
| Math | NumPy, SciPy |
| AI | Anthropic Claude Haiku API |
| Frontend | Vanilla JS, Chart.js, CSS custom properties |
| Security | slowapi rate limiting, CSP headers, input validation |
| Tests | pytest — 57 tests, 100% passing |
| Deploy | Replit (`.replit` config included) |

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

---

## Project Structure

```
sim2real/
├── main.py                  # FastAPI app entry point
├── src/
│   ├── models/
│   │   ├── queuing.py       # M/M/1, M/M/c, M/D/1, M/G/1 solvers
│   │   ├── inventory.py     # EOQ and Newsvendor models
│   │   └── simulation.py    # Monte Carlo discrete-event engine
│   ├── api/
│   │   ├── routes.py        # REST API endpoints
│   │   ├── schemas.py       # Pydantic request/response models
│   │   └── middleware.py    # Rate limiting + security headers
│   └── ai/
│       └── explainer.py     # Claude API integration
├── static/                  # Single-page frontend (no build step)
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── app.js           # Main app logic
│       ├── charts.js        # Chart.js wrappers
│       └── api.js           # Frontend API client
└── tests/                   # 57 unit + integration tests
```

---

## API

Interactive docs available at `/api/docs` when running.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/queuing` | POST | Analytical queuing solution |
| `/api/inventory/eoq` | POST | EOQ model |
| `/api/inventory/newsvendor` | POST | Newsvendor model |
| `/api/simulation` | POST | Monte Carlo simulation |
| `/api/explain` | POST | AI explanation |
| `/api/health` | GET | Health check |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | No | Enables AI insights (Claude Haiku) |
| `RATE_LIMIT_PER_MINUTE` | No | Default: 20 requests/min per IP |
| `ENVIRONMENT` | No | `development` or `production` |

The app runs fully without an API key — AI features are simply disabled.

---

## License

MIT
