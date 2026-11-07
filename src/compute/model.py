"""FlameAtlas compute layer: deterministic science, no LLM.

Trains a gradient-boosting classifier on the curated microgravity combustion
table (cache/experiments.parquet) and exposes a single predict() function that
returns the competition prediction object with an explicit training-range guard.

All numbers come from the trained model or the data table; nothing is guessed.
"""
from __future__ import annotations

import json
import os
import pickle
from dataclasses import asdict
from pathlib import Path
from typing import Any

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
MODEL_META = REPO / "cache" / "model_meta.json"

NUMERIC_FEATURES = ["oxygen_pct", "pressure_kpa", "flow_cm_s"]
CATEGORICAL_FEATURES = ["material"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET = "outcome_class"

# Classes the competition prediction object reports, in order.
CLASS_ORDER = ["no_spread", "marginal_spread", "spread"]

# Thresholds that turn P(spread) into the 3-class prediction, mirroring the
# prototype's MARGINAL band (core.py classify_habitat).
SPREAD_THRESHOLD = 0.60
NO_SPREAD_THRESHOLD = 0.40


class ModelNotTrainedError(RuntimeError):
    pass


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
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )


def train(df: pd.DataFrame | None = None) -> dict[str, Any]:
    """Train the gradient-boosting classifier, report honest CV accuracy,
    save the model artifact and metadata to cache/."""
    if df is None:
        df = load_data()

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
    }

    with open(MODEL_ARTIFACT, "wb") as fh:
        pickle.dump(pipe, fh)
    MODEL_META.write_text(json.dumps(meta, indent=2))

    print(f"Trained gradient-boosting classifier on {len(df)} rows")
    print(f"  classes: {present}")
    print(f"  CV accuracy: {cv_accuracy:.4f} (scores: {[round(float(s),3) for s in cv_scores]})")
    print(f"  confusion matrix labels={labels} matrix={cm.tolist()}")
    print(f"  feature range: {feature_range}")
    print(f"  artifact -> {MODEL_ARTIFACT}")
    print(f"  metadata -> {MODEL_META}")
    return meta


class FlameAtlasModel:
    """Loaded model with training-range guard and nearest-experiment lookup."""

    def __init__(self) -> None:
        if not MODEL_ARTIFACT.exists() or not MODEL_META.exists():
            raise ModelNotTrainedError(
                "Model artifact or metadata missing. Run train() first."
            )
        with open(MODEL_ARTIFACT, "rb") as fh:
            self.pipe = pickle.load(fh)
        self.meta = json.loads(MODEL_META.read_text())
        self.df = load_data()
        self.classes = list(self.meta["classes"])

    def in_training_range(self, oxygen_pct: float, pressure_kpa: float, flow_cm_s: float) -> bool:
        fr = self.meta["feature_range"]
        return (
            fr["oxygen_pct"]["min"] <= oxygen_pct <= fr["oxygen_pct"]["max"]
            and fr["pressure_kpa"]["min"] <= pressure_kpa <= fr["pressure_kpa"]["max"]
            and fr["flow_cm_s"]["min"] <= flow_cm_s <= fr["flow_cm_s"]["max"]
        )

    def _class_probabilities(self, oxygen_pct, pressure_kpa, flow_cm_s, material) -> dict[str, float]:
        X = pd.DataFrame(
            [[oxygen_pct, pressure_kpa, flow_cm_s, material]],
            columns=FEATURES,
        )
        proba = self.pipe.predict_proba(X)[0]
        # Map model classes (subset of CLASS_ORDER present in training) to the
        # full 3-class output. Classes not in training get 0.0.
        out = {c: 0.0 for c in CLASS_ORDER}
        for cls, p in zip(self.classes, proba):
            out[cls] = float(p)
        # Normalize so the three classes sum to 1.
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
        d_flow = (np.log2(df["flow_cm_s"].clip(lower=0.5)) - np.log2(max(flow_cm_s, 0.5))).abs()
        df = df.assign(distance=d_o2 + d_press + d_flow)
        nearest = df.sort_values("distance").head(k)
        out = []
        for _, r in nearest.iterrows():
            out.append({
                "report_id": r["report_id"],
                "oxygen_pct": round(float(r["oxygen_pct"]), 2),
                "pressure_kpa": round(float(r["pressure_kpa"]), 2),
                "flow_cm_s": round(float(r["flow_cm_s"]), 2),
                "outcome": r["outcome_class"],
                "material": r["material"],
                "source_url": r["source_url"],
                "distance": round(float(r["distance"]), 4),
            })
        return out

    def predict(
        self, oxygen_pct: float, pressure_kpa: float, flow_cm_s: float, material: str
    ) -> dict[str, Any]:
        """Return the competition prediction object with limits attached.

        If conditions fall outside the training range, returns no prediction
        and an explanation (never extrapolates silently).
        """
        in_range = self.in_training_range(oxygen_pct, pressure_kpa, flow_cm_s)
        inputs = {
            "oxygen_pct": oxygen_pct,
            "pressure_kpa": pressure_kpa,
            "flow_cm_s": flow_cm_s,
            "material": material,
        }

        if not in_range:
            fr = self.meta["feature_range"]
            return {
                "inputs": inputs,
                "in_training_range": False,
                "prediction": None,
                "probabilities": None,
                "model": {
                    "type": self.meta["type"],
                    "n_train": self.meta["n_train"],
                    "cv_accuracy": self.meta["cv_accuracy"],
                    "features": self.meta["features"],
                },
                "nearest_experiments": self.nearest_experiments(oxygen_pct, pressure_kpa, flow_cm_s),
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
            "prediction": prediction,
            "probabilities": proba,
            "model": {
                "type": self.meta["type"],
                "n_train": self.meta["n_train"],
                "cv_accuracy": self.meta["cv_accuracy"],
                "features": self.meta["features"],
            },
            "nearest_experiments": nearest,
        }


def main() -> None:
    train()


if __name__ == "__main__":
    main()
