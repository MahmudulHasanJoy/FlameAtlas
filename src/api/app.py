"""FastAPI server: POST /predict for the microgravity fire-safety explorer.

Deterministic science lives in src/compute/model.py. This layer only
serializes inputs, calls predict(), and returns the competition object.
Never extrapolates: out-of-range requests return no prediction.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

try:
    # Run as: python -m src.api.app  (src on sys.path)
    from compute.model import FlameAtlasModel, ModelNotTrainedError
except ImportError:
    # Run from repo root
    from src.compute.model import FlameAtlasModel, ModelNotTrainedError

app = FastAPI(title="FlameAtlas Fire-Safety Explorer", version="1.0.0")

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
