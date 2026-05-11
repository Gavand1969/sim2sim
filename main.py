"""
Sim2Real — Operations Research Simulator
Entry point: FastAPI app that serves both the REST API and the static frontend.
"""
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.api.middleware import limiter, add_security_headers
from src.api.routes import router

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing to initialise beyond imports
    yield
    # Shutdown: nothing to clean up


app = FastAPI(
    title="Sim2Real",
    description="Operations Research Simulator with AI-powered explanations",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# ── Rate limiter ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
# In production (Replit) the frontend is served from the same origin, so
# wildcard CORS is only needed in local development.
_env = os.getenv("ENVIRONMENT", "development")
_origins = ["*"] if _env == "development" else [os.getenv("ALLOWED_ORIGIN", "")]

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

# Catch-all so that client-side navigation always returns index.html
@app.get("/{full_path:path}", include_in_schema=False)
async def catch_all(full_path: str):
    # Let /api/* fall through to the router; only serve the SPA for everything else
    if full_path.startswith("api/"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404)
    return FileResponse("static/index.html")
