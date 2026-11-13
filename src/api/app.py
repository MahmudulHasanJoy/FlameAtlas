"""FastAPI server for the microgravity fire-safety explorer.

Serves the dashboard at / and the JSON API at /predict, /boundary, /health.

Deterministic science lives in src/compute/model.py. This layer only
serializes inputs, calls predict(), and returns the competition object.
Never extrapolates: out-of-range requests return no prediction.

Security controls:
  - API key (X-API-Key header, from FLAMEATLAS_API_KEY) required for direct
    API calls. The key is never sent to the browser: the dashboard served from
    this same origin is let through by the browser-set Sec-Fetch-Site header.
    This stops casual cross-site and scripted use; it is not strong auth, since
    the dashboard itself is public by design.
  - Per-IP rate limiting (300 requests/minute; run uvicorn with
    --proxy-headers behind a proxy so the real client IP is used).
  - Security headers: CSP, X-Frame-Options, X-Content-Type-Options, etc.
  - Input bounds enforced in Pydantic model and re-checked in compute layer.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
from collections import defaultdict
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

try:
    # Run as: python -m src.api.app  (src on sys.path)
    from compute.model import FlameAtlasModel, ModelNotTrainedError, ModelTamperError
except ImportError:
    # Run from repo root
    from src.compute.model import FlameAtlasModel, ModelNotTrainedError, ModelTamperError

try:
    from dotenv import load_dotenv

    load_dotenv()  # local .env; real environment variables take precedence
except ImportError:
    pass

log = logging.getLogger("flameatlas")

REPO = Path(__file__).resolve().parent.parent.parent
DASHBOARD = REPO / "frontend" / "dashboard.html"
CARDS_FILE = REPO / "data" / "processed" / "cards.json"
CARDS_VERIFICATION_FILE = REPO / "data" / "processed" / "cards_verification.json"

app = FastAPI(title="FlameAtlas Fire-Safety Explorer", version="2.0.0")

# CORS: open so other tools can call the API with a key. Access control is
# the X-API-Key check, not the origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["content-type", "x-api-key"],
)

# ---------------------------------------------------------------------------
# API key: set via FLAMEATLAS_API_KEY (env var or .env). If unset, a random
# key is generated per process so there is never a guessable default.
# ---------------------------------------------------------------------------
API_KEY = os.getenv("FLAMEATLAS_API_KEY") or ""
if not API_KEY:
    API_KEY = secrets.token_urlsafe(32)
    log.warning("FLAMEATLAS_API_KEY not set; using a random key for this process.")

# ---------------------------------------------------------------------------
# Rate limiting: simple in-memory sliding window (300 requests / 60 s per IP).
# The dashboard sends about 2 requests per slider pause plus a health check
# every 10 s, so 60/min was too tight for normal use.
# Not distributed; for single-instance deployment. Add Redis for multi-node.
# ---------------------------------------------------------------------------
_REQUEST_WINDOWS: defaultdict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 300
RATE_WINDOW_SECONDS = 60


def _clean_window(timestamps: list[float], now: float) -> None:
    cutoff = now - RATE_WINDOW_SECONDS
    while timestamps and timestamps[0] < cutoff:
        timestamps.pop(0)


def verify_api_key(
    request: Request, x_api_key: str | None = Header(None)
) -> str | None:
    # The dashboard served from this origin needs no key; browsers set
    # Sec-Fetch-Site themselves and page scripts cannot change it.
    if request.headers.get("sec-fetch-site") == "same-origin":
        return None
    if x_api_key is None or not secrets.compare_digest(x_api_key, API_KEY):
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
    ] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.plot.ly; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    )
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


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(DASHBOARD, media_type="text/html")


@app.get("/health")
def health():
    return {"name": "FlameAtlas", "status": "ok", "version": "2.0.0"}


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
    if material not in model.materials_with_data:
        raise HTTPException(
            status_code=422,
            detail=f"No outcome data for '{material}'; no boundary can be drawn.",
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


_cards: dict | None = None


def load_cards() -> dict:
    """Evidence cards plus the stored result of scripts/verify_cards.py."""
    global _cards
    if _cards is None:
        data = json.loads(CARDS_FILE.read_text(encoding="utf-8"))
        verification = None
        if CARDS_VERIFICATION_FILE.exists():
            v = json.loads(CARDS_VERIFICATION_FILE.read_text(encoding="utf-8"))
            verification = {
                k: v[k] for k in ("checked_on", "method", "quotes", "quotes_verified", "all_passed")
            }
        _cards = {
            "sources": data["sources"],
            "cards": data["cards"],
            "verification": verification,
        }
    return _cards


def _public_sources(sources: dict) -> dict:
    # The local file path is a build detail, not part of the API.
    return {k: {f: v for f, v in s.items() if f != "file"} for k, s in sources.items()}


@app.get("/cards", dependencies=[Depends(verify_api_key)])
def list_cards(material: str | None = Query(None, max_length=40)):
    """All evidence cards, optionally filtered by material id."""
    data = load_cards()
    cards = data["cards"]
    if material:
        cards = [c for c in cards if material in c["material_ids"]]
    return {
        "cards": cards,
        "sources": _public_sources(data["sources"]),
        "verification": data["verification"],
    }


@app.get("/cards/{card_id}", dependencies=[Depends(verify_api_key)])
def get_card(card_id: str):
    data = load_cards()
    for c in data["cards"]:
        if c["card_id"] == card_id:
            sources = {sid: data["sources"][sid] for sid in c["source_ids"]}
            return {"card": c, "sources": _public_sources(sources), "verification": data["verification"]}
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No card '{card_id}'")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
