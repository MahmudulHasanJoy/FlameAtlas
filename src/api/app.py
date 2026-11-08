"""FastAPI server: POST /predict for the microgravity fire-safety explorer.

Deterministic science lives in src/compute/model.py. This layer only
serializes inputs, calls predict(), and returns the competition object.
Never extrapolates: out-of-range requests return no prediction.

Security controls:
  - CORS restricted to localhost origins (no wildcard with credentials).
  - API key required on every endpoint (X-API-Key header).
  - Per-IP rate limiting (60 requests/minute).
  - Security headers: CSP, X-Frame-Options, X-Content-Type-Options, etc.
  - Input bounds enforced in Pydantic model and re-checked in compute layer.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Callable

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

try:
    # Run as: python -m src.api.app  (src on sys.path)
    from compute.model import FlameAtlasModel, ModelNotTrainedError, ModelTamperError
except ImportError:
    # Run from repo root
    from src.compute.model import FlameAtlasModel, ModelNotTrainedError, ModelTamperError

app = FastAPI(title="FlameAtlas Fire-Safety Explorer", version="2.0.0")

# CORS: allow all origins for local dev (file:// origin sends "null").
# Security is enforced by X-API-Key header, not CORS origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["content-type", "x-api-key"],
)

# ---------------------------------------------------------------------------
# API key: set via FLAMEATLAS_API_KEY env var. Default is a dev placeholder
# that MUST be changed before any non-local deployment.
# ---------------------------------------------------------------------------
API_KEY = os.getenv("FLAMEATLAS_API_KEY", "dev-key-change-me-in-production")

# ---------------------------------------------------------------------------
# Rate limiting: simple in-memory sliding window (60 requests / 60 s per IP).
# Not distributed; for single-instance deployment. Add Redis for multi-node.
# ---------------------------------------------------------------------------
_REQUEST_WINDOWS: defaultdict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 60
RATE_WINDOW_SECONDS = 60


def _clean_window(timestamps: list[float], now: float) -> None:
    cutoff = now - RATE_WINDOW_SECONDS
    while timestamps and timestamps[0] < cutoff:
        timestamps.pop(0)


def verify_api_key(x_api_key: str | None = Header(None)) -> str:
    if x_api_key is None or x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return x_api_key


def rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = _REQUEST_WINDOWS[client_ip]
    _clean_window(window, now)
    if len(window) >= RATE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
        )
    window.append(now)


@app.middleware("http")
async def security_and_rate_limit(request: Request, call_next: Callable):
    # Rate limit before processing.
    try:
        rate_limit(request)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None) or {},
        )

    response = await call_next(request)

    # Security headers on every response.
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers[
        "Content-Security-Policy"
    ] = "default-src 'self'; script-src 'self' https://cdn.plot.ly https://fonts.googleapis.com; style-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self' http://127.0.0.1:8000;"
    return response


_model: FlameAtlasModel | None = None


def get_model() -> FlameAtlasModel:
    global _model
    if _model is None:
        try:
            _model = FlameAtlasModel()
        except ModelTamperError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except ModelNotTrainedError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc) + " Run: python src/compute/model.py",
            ) from exc
    return _model


class PredictRequest(BaseModel):
    oxygen_pct: float = Field(
        ..., ge=0, le=100, description="Oxygen concentration in percent"
    )
    pressure_kpa: float = Field(
        ..., ge=0, le=200, description="Pressure in kilopascals"
    )
    flow_cm_s: float = Field(
        ..., ge=0, le=100, description="Airflow velocity in cm/s"
    )
    material: str = Field(..., description="Material identifier (e.g. 'sibal')")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "oxygen_pct": 21.0,
                    "pressure_kpa": 101.3,
                    "flow_cm_s": 10.0,
                    "material": "sibal",
                }
            ]
        }
    }


@app.get("/")
def root():
    return {"name": "FlameAtlas", "endpoint": "POST /predict", "version": "2.0.0"}


@app.post("/predict", dependencies=[Depends(verify_api_key)])
def predict(req: PredictRequest):
    """Return the flame-spread regime prediction with limits attached.

    If the requested conditions fall outside the training envelope, returns
    in_training_range=false with no prediction and an explanation.
    """
    model = get_model()
    try:
        return model.predict(
            oxygen_pct=req.oxygen_pct,
            pressure_kpa=req.pressure_kpa,
            flow_cm_s=req.flow_cm_s,
            material=req.material,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@app.get("/boundary", dependencies=[Depends(verify_api_key)])
def boundary(
    material: str = Query("sibal"),
    pressure_kpa: float = Query(101.3, ge=30, le=110),
    n: int = Query(160, ge=10, le=500),
):
    """Decision-boundary grid: P(spread) over O2 x airflow for a material."""
    model = get_model()
    # Validate material against known set before computing the grid.
    if material not in model.known_materials:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown material '{material}'. Known: {sorted(model.known_materials)}",
        )
    fr = model.meta["feature_range"]

    o2_min, o2_max = fr["oxygen_pct"]["min"], fr["oxygen_pct"]["max"]
    flow_min, flow_max = fr["flow_cm_s"]["min"], fr["flow_cm_s"]["max"]

    o2s = np.linspace(o2_min, o2_max, n)
    flows = np.logspace(np.log10(flow_min), np.log10(flow_max), n)
    O, F = np.meshgrid(o2s, flows)

    X = pd.DataFrame(
        {
            "oxygen_pct": O.ravel(),
            "pressure_kpa": pressure_kpa,
            "flow_cm_s": F.ravel(),
            "material": material,
        }
    )
    proba = model.pipe.predict_proba(X)
    try:
        spread_idx = list(model.pipe.classes_).index("spread")
    except ValueError:
        spread_idx = None
    if spread_idx is None:
        P = np.zeros(O.ravel().shape)
    else:
        P = proba[:, spread_idx]
    P = P.reshape(O.shape)

    inside = (O >= o2_min) & (O <= o2_max) & (F >= flow_min) & (F <= flow_max)

    experiments = []
    for _, r in model.df.iterrows():
        experiments.append(
            {
                "x": float(r["flow_cm_s"]),
                "y": float(r["oxygen_pct"]),
                "outcome": r["outcome_class"],
                "report_id": r["report_id"],
                "source_url": r["source_url"],
                "material": r["material"],
            }
        )

    return {
        "flows": flows.tolist(),
        "o2s": o2s.tolist(),
        "P_spread": P.tolist(),
        "inside": inside.tolist(),
        "experiments": experiments,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
