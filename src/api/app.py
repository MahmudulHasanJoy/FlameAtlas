"""FastAPI server: POST /predict for the microgravity fire-safety explorer.

Deterministic science lives in src/compute/model.py. This layer only
serializes inputs, calls predict(), and returns the competition object.
Never extrapolates: out-of-range requests return no prediction.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

try:
    # Run as: python -m src.api.app  (src on sys.path)
    from compute.model import FlameAtlasModel, ModelNotTrainedError
except ImportError:
    # Run from repo root
    from src.compute.model import FlameAtlasModel, ModelNotTrainedError

app = FastAPI(title="FlameAtlas Fire-Safety Explorer", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_model: FlameAtlasModel | None = None


def get_model() -> FlameAtlasModel:
    global _model
    if _model is None:
        try:
            _model = FlameAtlasModel()
        except ModelNotTrainedError as exc:
            raise HTTPException(
                status_code=503,
                detail=str(exc) + " Run: python src/compute/model.py",
            ) from exc
    return _model


class PredictRequest(BaseModel):
    oxygen_pct: float = Field(..., description="Oxygen concentration in percent")
    pressure_kpa: float = Field(..., description="Pressure in kilopascals")
    flow_cm_s: float = Field(..., description="Airflow velocity in cm/s")
    material: str = Field(..., description="Material identifier (e.g. 'sibal')")


@app.get("/")
def root():
    return {"name": "FlameAtlas", "endpoint": "POST /predict"}


@app.post("/predict")
def predict(req: PredictRequest):
    """Return the flame-spread regime prediction with limits attached.

    If the requested conditions fall outside the training envelope, returns
    in_training_range=false with no prediction and an explanation.
    """
    model = get_model()
    return model.predict(
        oxygen_pct=req.oxygen_pct,
        pressure_kpa=req.pressure_kpa,
        flow_cm_s=req.flow_cm_s,
        material=req.material,
    )


@app.get("/boundary")
def boundary(material: str = "sibal", pressure_kpa: float = 101.3, n: int = 160):
    """Decision-boundary grid: P(spread) over O2 x airflow for a material."""
    model = get_model()
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
