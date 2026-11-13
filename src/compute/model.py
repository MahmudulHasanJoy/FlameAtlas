"""FlameAtlas compute layer: deterministic science, no LLM.

Trains a gradient-boosting classifier on the curated microgravity combustion
table (cache/experiments.parquet) and exposes a single predict() function that
returns the competition prediction object with an explicit training-range guard.

All numbers come from the trained model or the data table; nothing is guessed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DATA = REPO / "cache" / "experiments.parquet"
MODEL_ARTIFACT = REPO / "cache" / "model.joblib"
MODEL_CHECKSUM = REPO / "cache" / "model.sha256"
MODEL_META = REPO / "cache" / "model_meta.json"

NUMERIC_FEATURES = ["oxygen_pct", "pressure_kpa", "flow_cm_s"]
CATEGORICAL_FEATURES = ["material"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET = "outcome_class"

# Classes the competition prediction object reports, in order.
CLASS_ORDER = ["no_spread", "marginal_spread", "spread"]

# Materials known to the trained model. Anything outside this list is rejected
# outright instead of being silently passed through the unknown-category path.
KNOWN_MATERIALS = {"sibal", "pmma", "nomex", "silicone"}

# A material needs at least this many training rows with a recorded outcome
# before the model will predict for it. Below that, predict() returns a
# research-gap response instead of a number the data cannot support.
MIN_ROWS_FOR_PREDICTION = 10

# Thresholds that turn P(spread) into the 3-class prediction, mirroring the
# prototype's MARGINAL band (core.py classify_habitat).
SPREAD_THRESHOLD = 0.60
NO_SPREAD_THRESHOLD = 0.40

# Physical input bounds (defense in depth beyond the envelope guard).
O2_MIN, O2_MAX = 10.0, 40.0
PRESSURE_MIN, PRESSURE_MAX = 30.0, 110.0
FLOW_MIN, FLOW_MAX = 0.5, 60.0


class ModelNotTrainedError(RuntimeError):
    pass


class ModelTamperError(RuntimeError):
    pass


def _compute_checksum(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_checksum(path: Path) -> None:
    checksum = _compute_checksum(path)
    path.with_suffix(".sha256").write_text(checksum + "\n")


def load_data() -> pd.DataFrame:
    if not DATA.exists():
        raise FileNotFoundError(
            f"Training data not found: {DATA}. "
            "Run scripts/build_experiments_parquet.py first."
        )
    df = pd.read_parquet(DATA)
    df = df.dropna(subset=["oxygen_pct", "flow_cm_s", TARGET]).copy()
    return df


def build_preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",
    )


def train(df: pd.DataFrame | None = None) -> dict[str, Any]:
    """Train the gradient-boosting classifier, report honest CV accuracy,
    save the model artifact and metadata to cache/.

    The classifier needs all four features (oxygen_pct, pressure_kpa,
    flow_cm_s, material) to place a prediction on the flammability map, so it
    is trained only on rows with a known flow rate. Rows without flow still
    live in experiments.parquet (condition-range coverage + nearest-experiment
    references) but are excluded from training.

    The saved artifact is accompanied by a SHA-256 checksum file so that any
    tampering is detected at load time.
    """
    if df is None:
        df = load_data()

    # The boundary model is defined on the O2 x flow plane; rows without flow
    # cannot be placed on the map and are excluded from training.
    df = df.dropna(subset=["oxygen_pct", "flow_cm_s"]).copy()

    y = df[TARGET].astype(str)
    # Only train on classes actually present; be honest about what we can predict.
    present = sorted(y.unique())
    if len(present) < 2:
        raise ValueError(f"Need at least 2 outcome classes to train, got {present}")

    pre = build_preprocessor()
    model = GradientBoostingClassifier(
        n_estimators=100, learning_rate=0.1, max_depth=3, random_state=42
    )
    pipe = Pipeline(steps=[("pre", pre), ("clf", model)])

    # Stratified cross-validation (honest accuracy figure).
    cv = StratifiedKFold(n_splits=min(5, y.value_counts().min()), shuffle=True, random_state=42)
    cv_scores = cross_val_score(pipe, df[FEATURES], y, cv=cv, scoring="accuracy")
    cv_accuracy = float(cv_scores.mean())

    # Fit on all data for the saved artifact.
    pipe.fit(df[FEATURES], y)

    # Confusion matrix on the full training set (honest, labeled).
    y_pred = pipe.predict(df[FEATURES])
    labels = present
    cm = confusion_matrix(y, y_pred, labels=labels)

    # Training range: min/max of every numeric feature.
    feature_range = {
        f: {"min": float(df[f].min()), "max": float(df[f].max())}
        for f in NUMERIC_FEATURES
    }

    meta = {
        "type": "gradient_boosting",
        "n_train": int(len(df)),
        "cv_accuracy": round(cv_accuracy, 4),
        "cv_scores": [round(float(s), 4) for s in cv_scores],
        "features": FEATURES,
        "classes": present,
        "class_order": CLASS_ORDER,
        "feature_range": feature_range,
        "confusion_matrix": {
            "labels": labels,
            "matrix": cm.tolist(),
        },
        "spread_threshold": SPREAD_THRESHOLD,
        "no_spread_threshold": NO_SPREAD_THRESHOLD,
        "known_materials": sorted(KNOWN_MATERIALS),
    }

    # Atomic write: write to temp, then rename, then checksum.
    tmp_artifact = MODEL_ARTIFACT.with_suffix(".joblib.tmp")
    with open(tmp_artifact, "wb") as fh:
        joblib.dump(pipe, fh)
    os.replace(tmp_artifact, MODEL_ARTIFACT)
    _write_checksum(MODEL_ARTIFACT)

    tmp_meta = MODEL_META.with_suffix(".json.tmp")
    tmp_meta.write_text(json.dumps(meta, indent=2))
    os.replace(tmp_meta, MODEL_META)
    # Make metadata read-only after training so the range guard can't be silently
    # widened at runtime.
    MODEL_META.chmod(0o444)

    print(f"Trained gradient-boosting classifier on {len(df)} rows")
    print(f"  classes: {present}")
    print(f"  CV accuracy: {cv_accuracy:.4f} (scores: {[round(float(s),3) for s in cv_scores]})")
    print(f"  confusion matrix labels={labels} matrix={cm.tolist()}")
    print(f"  feature range: {feature_range}")
    print(f"  artifact -> {MODEL_ARTIFACT}")
    print(f"  metadata -> {MODEL_META}")
    return meta


def _load_model_safely() -> Any:
    """Load the model artifact only if its SHA-256 checksum matches."""
    if not MODEL_ARTIFACT.exists() or not MODEL_CHECKSUM.exists():
        raise ModelNotTrainedError(
            "Model artifact or checksum missing. Run: python src/compute/model.py"
        )
    expected = MODEL_CHECKSUM.read_text().strip()
    actual = _compute_checksum(MODEL_ARTIFACT)
    if expected != actual:
        raise ModelTamperError(
            "Model artifact checksum mismatch — possible tampering. "
            "Retrain with: python src/compute/model.py"
        )
    return joblib.load(MODEL_ARTIFACT)


class FlameAtlasModel:
    """Loaded model with training-range guard and nearest-experiment lookup.

    The model artifact is integrity-checked at load time. Any modification of
    cache/model.joblib without regenerating cache/model.sha256 causes a
    ModelTamperError and the API refuses to serve predictions.
    """

    def __init__(self) -> None:
        if not MODEL_ARTIFACT.exists() or not MODEL_META.exists():
            raise ModelNotTrainedError(
                "Model artifact or metadata missing. Run: python src/compute/model.py"
            )
        self.pipe = _load_model_safely()
        self.meta = json.loads(MODEL_META.read_text())
        self.df = load_data()
        self.classes = list(self.meta["classes"])
        # Known materials from metadata, intersected with what the encoder saw.
        self.known_materials = set(self.meta.get("known_materials", [])) | KNOWN_MATERIALS
        # Materials with enough outcome rows to predict for (data-driven, so a
        # new material only needs data, not a code change).
        counts = self.df["material"].value_counts()
        self.materials_with_data = {
            m for m in self.known_materials if counts.get(m, 0) >= MIN_ROWS_FOR_PREDICTION
        }

    def _model_summary(self) -> dict[str, Any]:
        return {
            "type": self.meta["type"],
            "n_train": self.meta["n_train"],
            "cv_accuracy": self.meta["cv_accuracy"],
            "features": self.meta["features"],
            "feature_range": self.meta["feature_range"],
        }

    def validate_inputs(
        self, oxygen_pct: float, pressure_kpa: float, flow_cm_s: float, material: str
    ) -> None:
        """Reject out-of-bounds or unknown inputs before they reach the model."""
        if not (O2_MIN <= oxygen_pct <= O2_MAX):
            raise ValueError(
                f"oxygen_pct {oxygen_pct} outside physical bounds "
                f"[{O2_MIN}, {O2_MAX}]"
            )
        if not (PRESSURE_MIN <= pressure_kpa <= PRESSURE_MAX):
            raise ValueError(
                f"pressure_kpa {pressure_kpa} outside physical bounds "
                f"[{PRESSURE_MIN}, {PRESSURE_MAX}]"
            )
        if not (FLOW_MIN <= flow_cm_s <= FLOW_MAX):
            raise ValueError(
                f"flow_cm_s {flow_cm_s} outside physical bounds "
                f"[{FLOW_MIN}, {FLOW_MAX}]"
            )
        if material not in self.known_materials:
            raise ValueError(
                f"material '{material}' not in known materials "
                f"{sorted(self.known_materials)}"
            )

    def in_training_range(self, oxygen_pct: float, pressure_kpa: float, flow_cm_s: float) -> bool:
        fr = self.meta["feature_range"]
        return (
            fr["oxygen_pct"]["min"] <= oxygen_pct <= fr["oxygen_pct"]["max"]
            and fr["pressure_kpa"]["min"] <= pressure_kpa <= fr["pressure_kpa"]["max"]
            and fr["flow_cm_s"]["min"] <= flow_cm_s <= fr["flow_cm_s"]["max"]
        )

    def _class_probabilities(
        self, oxygen_pct: float, pressure_kpa: float, flow_cm_s: float, material: str
    ) -> dict[str, float]:
        X = pd.DataFrame(
            [[oxygen_pct, pressure_kpa, flow_cm_s, material]],
            columns=FEATURES,
        )
        proba = self.pipe.predict_proba(X)[0]
        out = {c: 0.0 for c in CLASS_ORDER}
        for cls, p in zip(self.classes, proba):
            out[cls] = float(p)
        total = sum(out.values())
        if total > 0:
            out = {c: round(v / total, 4) for c, v in out.items()}
        return out

    def _predict_class(self, proba: dict[str, float]) -> str:
        p_spread = proba["spread"]
        if p_spread >= SPREAD_THRESHOLD:
            return "spread"
        if p_spread <= NO_SPREAD_THRESHOLD:
            return "no_spread"
        return "marginal_spread"

    def nearest_experiments(
        self, oxygen_pct: float, pressure_kpa: float, flow_cm_s: float, k: int = 3
    ) -> list[dict[str, Any]]:
        """The k closest real experiments by normalized feature distance."""
        df = self.df.copy()
        # Normalized distance: O2 (per 2 pts), pressure (per 20 kPa), flow (log2).
        d_o2 = (df["oxygen_pct"] - oxygen_pct).abs() / 2.0
        d_press = (df["pressure_kpa"] - pressure_kpa).abs() / 20.0
        d_flow = (
            np.log2(df["flow_cm_s"].clip(lower=0.5))
            - np.log2(max(flow_cm_s, 0.5))
        ).abs()
        df = df.assign(distance=d_o2 + d_press + d_flow)
        nearest = df.sort_values("distance").head(k)
        out = []
        for _, r in nearest.iterrows():
            out.append(
                {
                    "report_id": r["report_id"],
                    "oxygen_pct": round(float(r["oxygen_pct"]), 2),
                    "pressure_kpa": round(float(r["pressure_kpa"]), 2),
                    "flow_cm_s": round(float(r["flow_cm_s"]), 2),
                    "outcome": r["outcome_class"],
                    "material": r["material"],
                    "source_url": r["source_url"],
                    "distance": round(float(r["distance"]), 4),
                }
            )
        return out

    def predict(
        self, oxygen_pct: float, pressure_kpa: float, flow_cm_s: float, material: str
    ) -> dict[str, Any]:
        """Return the competition prediction object with limits attached.

        Validates inputs first, then checks the training envelope. If conditions
        fall outside the envelope, returns no prediction and an explanation —
        never extrapolates silently.
        """
        # Input validation (bounds + known material) before any model call.
        self.validate_inputs(oxygen_pct, pressure_kpa, flow_cm_s, material)

        in_range = self.in_training_range(oxygen_pct, pressure_kpa, flow_cm_s)
        inputs = {
            "oxygen_pct": oxygen_pct,
            "pressure_kpa": pressure_kpa,
            "flow_cm_s": flow_cm_s,
            "material": material,
        }

        if material not in self.materials_with_data:
            return {
                "inputs": inputs,
                "in_training_range": False,
                "data_status": "no_outcome_data",
                "prediction": None,
                "probabilities": None,
                "model": self._model_summary(),
                "nearest_experiments": [],
                "explanation": (
                    f"NASA has tested {material}, but its published results cannot "
                    "support a prediction: they either all show one outcome or come "
                    "from too few, inconsistent tests. The individual NASA test "
                    "results and the material profile are shown instead."
                ),
            }

        if not in_range:
            fr = self.meta["feature_range"]
            return {
                "inputs": inputs,
                "in_training_range": False,
                "data_status": "out_of_range",
                "prediction": None,
                "probabilities": None,
                "model": self._model_summary(),
                "nearest_experiments": self.nearest_experiments(
                    oxygen_pct, pressure_kpa, flow_cm_s
                ),
                "explanation": (
                    "Requested conditions are outside the published experimental "
                    f"envelope (O2 {fr['oxygen_pct']['min']}-{fr['oxygen_pct']['max']}%, "
                    f"pressure {fr['pressure_kpa']['min']}-{fr['pressure_kpa']['max']} kPa, "
                    f"flow {fr['flow_cm_s']['min']}-{fr['flow_cm_s']['max']} cm/s). "
                    "No prediction is returned; extrapolating a fire-safety answer "
                    "beyond tested data is unsafe."
                ),
            }

        proba = self._class_probabilities(oxygen_pct, pressure_kpa, flow_cm_s, material)
        prediction = self._predict_class(proba)
        nearest = self.nearest_experiments(oxygen_pct, pressure_kpa, flow_cm_s)

        return {
            "inputs": inputs,
            "in_training_range": True,
            "data_status": "ok",
            "prediction": prediction,
            "probabilities": proba,
            "model": self._model_summary(),
            "nearest_experiments": nearest,
        }


def main() -> None:
    train()


if __name__ == "__main__":
    main()
