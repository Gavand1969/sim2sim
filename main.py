"""
Sim2Sim — Operations Research Simulator
Entry point: FastAPI app that serves both the REST API and the static frontend.
"""
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.api.middleware import limiter, add_security_headers
from src.api.routes import router
from src.billing import db as billing_db

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialise the billing DB so license activation works
    # immediately on first boot (Replit's filesystem persists across runs).
    billing_db.init_db()
    yield
    # Shutdown: nothing to clean up


app = FastAPI(
    title="Sim2Sim",
    description="Operations Research Simulator with AI-powered explanations",
    version="1.0.0",
    # We serve our own /api/docs below so the bootstrap script can live in
    # an external file and clear our strict CSP (no inline scripts).  The
    # OpenAPI schema is still auto-generated at /openapi.json.
    docs_url=None,
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# ── Rate limiter ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
# In production the frontend is served from the same origin, so wildcard
# CORS is only needed in local development.  In production we REQUIRE an
# ALLOWED_ORIGIN so we never silently ship with no CORS policy.
_env = os.getenv("ENVIRONMENT", "development")
if _env == "development":
    _origins: list[str] = ["*"]
else:
    _allowed = os.getenv("ALLOWED_ORIGIN", "").strip()
    if not _allowed:
        raise RuntimeError(
            "ENVIRONMENT=production requires ALLOWED_ORIGIN to be set "
            "(comma-separated list of allowed origins)."
        )
    _origins = [o.strip() for o in _allowed.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ── Security headers (custom middleware) ─────────────────────────────────────
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    add_security_headers(response)
    return response

# ── API routes ────────────────────────────────────────────────────────────────
app.include_router(router, prefix="/api")

# ── Static frontend ───────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", include_in_schema=False)
async def serve_frontend():
    return FileResponse("static/index.html")


@app.get("/pricing", include_in_schema=False)
async def serve_pricing():
    return FileResponse("static/pricing.html")


@app.get("/account", include_in_schema=False)
async def serve_account():
    return FileResponse("static/account.html")


# Custom Swagger UI — keeps the bootstrap script in /static/js/ so our CSP
# (script-src 'self' https://cdn.jsdelivr.net) does not block it.
_SWAGGER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Sim2Sim API · Swagger UI</title>
  <link rel="shortcut icon" href="/static/favicon.ico" />
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css" />
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script src="/static/js/swagger-init.js"></script>
</body>
</html>
"""


@app.get("/api/docs", include_in_schema=False)
async def serve_api_docs():
    return HTMLResponse(_SWAGGER_HTML)


# Catch-all so that client-side navigation always returns index.html
@app.get("/{full_path:path}", include_in_schema=False)
async def catch_all(full_path: str):
    # Let /api/* fall through to the router; only serve the SPA for everything else
    if full_path.startswith("api/"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404)
    return FileResponse("static/index.html")
