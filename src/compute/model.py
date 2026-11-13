"""FlameAtlas compute layer: deterministic science, no LLM.

Fits a U-shaped flammability boundary for SIBAL fabric: logistic regression on
oxygen, log(airflow) and log(airflow)^2, the shape NASA reports for low-gravity
flammability (quenching at low flow, blowoff at high flow; NTRS 20210011385).
Training data are measured microgravity outcomes only: BASS-II Table 7.1
(prototype/data/sibal_bass_table71.csv, rows flagged exclude_from_fit dropped)
and Saffire I-IV (data/processed/sibal_added_tests.json).

predict() returns the competition prediction object with an explicit
training-range guard. All numbers come from the model or the data; nothing is
guessed.
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
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DATA = REPO / "cache" / "experiments.parquet"
MODEL_ARTIFACT = REPO / "cache" / "model.joblib"
MODEL_CHECKSUM = REPO / "cache" / "model.sha256"
MODEL_META = REPO / "cache" / "model_meta.json"
TABLE71 = REPO / "prototype" / "data" / "sibal_bass_table71.csv"
ADDED_TESTS = REPO / "data" / "processed" / "sibal_added_tests.json"

MODEL_FEATURES = ["oxygen_pct", "inv_flow"]
TARGET = "outcome_class"
TRAINED_MATERIALS = ["sibal"]
# All SIBAL tests ran near 1 atm. Pressures within this margin of the tested
# range are accepted (the PRD's pressure-mismatch threshold); beyond it the
# guard returns no prediction.
PRESSURE_TOLERANCE_KPA = 15.0
OUTCOME_FROM_TABLE = {"burned": "spread", "self_extinguished": "no_spread", "no_ignition": "no_spread"}

# Classes the competition prediction object reports, in order.
CLASS_ORDER = ["no_spread", "marginal_spread", "spread"]

# Materials known to the trained model. Anything outside this list is rejected
# outright instead of being silently passed through the unknown-category path.
KNOWN_MATERIALS = {"sibal", "pmma", "nomex", "silicone"}

# A material needs at least this many training rows with a recorded outcome
# before the model will predict for it. Below that, predict() returns a
# research-gap response instead of a number the data cannot support.
MIN_ROWS_FOR_PREDICTION = 10

# Thresholds that turn P(spread) into SPREAD / MARGINAL / NO SPREAD. Chosen
# from 0.4-0.6, 0.3-0.7 and 0.2-0.8 by held-out testing (ADR-0023): 0.3-0.7
# flags most extinctions as MARGINAL without ever calling a burning test
# NO SPREAD.
SPREAD_THRESHOLD = 0.70
NO_SPREAD_THRESHOLD = 0.30

# Physical input bounds (defense in depth beyond the envelope guard).
O2_MIN, O2_MAX = 10.0, 40.0
PRESSURE_MIN, PRESSURE_MAX = 30.0, 110.0
FLOW_MIN, FLOW_MAX = 0.5, 60.0


# scripts/build_experiments_parquet.py stores rows whose source gives no
# outcome as "marginal_spread" (see docs/05-data-spec.md, 4.8). Every
# marginal_spread row in the current data is such a default, so it is treated
# as "no outcome recorded" wherever results are shown to people.
UNRECORDED_OUTCOME = "marginal_spread"


def matches_material(name: Any, material_id: str) -> bool:
    """True if a dataset material name refers to the given material id.

    The PSI tables name the same fabric "sibal", "SIBAL Fabric" and
    "Cotton-Fiberglass (SIBAL)", so this matches on the id as a word.
    """
    n = str(name).lower()
    return n == material_id or material_id in n.replace("(", " ").replace(")", " ").split()


def display_material(name: Any) -> str:
    n = str(name)
    return "unnamed sample" if n.lower() in ("nan", "none", "", "unknown") else n


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


def u_features(oxygen_pct, flow_cm_s) -> np.ndarray:
    """Model inputs: O2 and 1/flow (flow floored at 0.5 cm/s).

    1/flow grows sharply as airflow approaches zero, which lets the boundary
    bend steeply on the quenching side, as NASA's SIBAL data and the authors'
    quenching line do (NTRS 20150008962, Fig. 7). It beat log(flow),
    log(flow)^2 and sample-width variants in held-out testing (ADR-0023,
    ADR-0024; scripts/model_experiments.py)."""
    o2 = np.asarray(oxygen_pct, dtype=float).ravel()
    u = np.clip(np.asarray(flow_cm_s, dtype=float).ravel(), 0.5, None)
    return np.c_[o2, 1.0 / u]


def load_training() -> pd.DataFrame:
    """Measured SIBAL microgravity outcomes used to fit the boundary."""
    t = pd.read_csv(TABLE71)
    t = t[t["exclude_from_fit"].astype(str).str.lower() != "true"]
    t = t.dropna(subset=["o2_pct", "flow_cm_s", "outcome"])
    rows = pd.DataFrame({
        "oxygen_pct": t["o2_pct"].astype(float),
        "pressure_kpa": t["pressure_kpa"].astype(float),
        "flow_cm_s": t["flow_cm_s"].astype(float),
        "material": "sibal",
        TARGET: t["outcome"].map(OUTCOME_FROM_TABLE),
        "report_id": t["source_id"],
        "source_url": "https://ntrs.nasa.gov/citations/" + t["source_id"].str.replace("NTRS-", "", regex=False),
        "note": t["experiment"] + " " + t["test_label"] + " (" + t["outcome"].str.replace("_", " ") + ")",
    })
    added = json.loads(ADDED_TESTS.read_text(encoding="utf-8"))["records"]
    extra = pd.DataFrame([{
        "oxygen_pct": r["oxygen_pct"], "pressure_kpa": r["pressure_kpa"], "flow_cm_s": r["flow_cm_s"],
        "material": r["material"], TARGET: r["outcome_class"], "report_id": r["report_id"],
        "source_url": r["source_url"], "note": f"{r['test_label']}: {r['note']}",
    } for r in added])
    df = pd.concat([rows, extra], ignore_index=True)
    df["in_training"] = True
    return df


def load_context() -> pd.DataFrame:
    """Tests shown for context but not used to fit the boundary: Table 7.1 rows
    flagged exclude_from_fit, and other materials or unrecorded rows from the
    PSI tables (minus the PSI SIBAL rows that duplicate Saffire tests)."""
    t = pd.read_csv(TABLE71)
    t = t[t["exclude_from_fit"].astype(str).str.lower() == "true"].dropna(subset=["o2_pct", "flow_cm_s"])
    excluded = pd.DataFrame({
        "oxygen_pct": t["o2_pct"].astype(float), "pressure_kpa": t["pressure_kpa"].astype(float),
        "flow_cm_s": t["flow_cm_s"].astype(float), "material": "sibal",
        TARGET: t["outcome"].map(OUTCOME_FROM_TABLE), "report_id": t["source_id"],
        "source_url": "https://ntrs.nasa.gov/citations/" + t["source_id"].str.replace("NTRS-", "", regex=False),
        "note": "excluded from the model: " + t["exclude_reason"],
    })
    psi = pd.read_parquet(DATA).dropna(subset=["oxygen_pct", "flow_cm_s", TARGET]) if DATA.exists() else pd.DataFrame()
    if len(psi):
        # SIBAL rows here are copies of Table 7.1 (above) or of the Saffire tests.
        replaces = json.loads(ADDED_TESTS.read_text(encoding="utf-8"))["replaces"]
        drop = psi["material"].map(lambda n: matches_material(n, "sibal"))
        for r in replaces:
            m = (psi["report_id"] == r["report_id"]) & (psi["material"].astype(str) == r["material"])
            if "oxygen_pct" in r:
                m &= (psi["oxygen_pct"] - r["oxygen_pct"]).abs() < 0.05
            drop |= m
        psi = psi[~drop]
        psi = psi.assign(note="")[["oxygen_pct", "pressure_kpa", "flow_cm_s", "material", TARGET, "report_id", "source_url", "note"]]
    df = pd.concat([excluded, psi], ignore_index=True)
    df["in_training"] = False
    return df


def load_data() -> pd.DataFrame:
    return pd.concat([load_training(), load_context()], ignore_index=True)


def _u_pipeline() -> Pipeline:
    return Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(C=1.0, max_iter=1000))])


def _three_way(p: np.ndarray) -> np.ndarray:
    return np.where(p >= SPREAD_THRESHOLD, 2, np.where(p <= NO_SPREAD_THRESHOLD, 0, 1))


def train() -> dict[str, Any]:
    """Fit the quenching boundary and report honest held-out metrics.

    Every metric comes from 5-fold stratified cross-validation repeated 20
    times, scoring only tests the model did not see. Besides accuracy (and
    the always-burns baseline) it reports AUC, and the fire-safety view of the
    app's three-way output: how many burning tests were called NO SPREAD (the
    dangerous error) and how many extinctions were flagged MARGINAL or NO
    SPREAD. Gradient boosting is scored on the same folds for comparison."""
    df = load_training()
    X = u_features(df["oxygen_pct"], df["flow_cm_s"])
    y = (df[TARGET] == "spread").astype(int).to_numpy()
    rcv = RepeatedStratifiedKFold(n_splits=5, n_repeats=20, random_state=0)

    def held_out(make_model, feats) -> dict[str, float]:
        acc, auc = [], []
        burned_as_no_spread = burned_n = out_flagged = out_n = 0
        for tr, te in rcv.split(feats, y):
            p = make_model().fit(feats[tr], y[tr]).predict_proba(feats[te])[:, 1]
            yt, cls = y[te], _three_way(p)
            acc.append(((p >= 0.5).astype(int) == yt).mean())
            auc.append(roc_auc_score(yt, p))
            burned_as_no_spread += int(((cls == 0) & (yt == 1)).sum()); burned_n += int((yt == 1).sum())
            out_flagged += int(((cls <= 1) & (yt == 0)).sum()); out_n += int((yt == 0).sum())
        return {
            "accuracy": round(float(np.mean(acc)), 4),
            "auc": round(float(np.mean(auc)), 4),
            "burned_called_no_spread": burned_as_no_spread, "burned_cases": burned_n,
            "extinctions_flagged": out_flagged, "extinction_cases": out_n,
        }

    main = held_out(_u_pipeline, X)
    gb = held_out(lambda: GradientBoostingClassifier(random_state=42), np.c_[df["oxygen_pct"], df["flow_cm_s"]])
    baseline = float(max(y.mean(), 1 - y.mean()))

    pipe = _u_pipeline().fit(X, y)
    coef = pipe.named_steps["clf"].coef_[0]
    feature_range = {
        f: {"min": float(df[f].min()), "max": float(df[f].max())}
        for f in ["oxygen_pct", "pressure_kpa", "flow_cm_s"]
    }
    meta = {
        "type": "logistic_quench_boundary",
        "description": "Logistic regression on O2 and 1/flow for SIBAL fabric (microgravity, concurrent flow); "
                       "describes the low-flow quenching side of NASA's flammability boundary",
        "n_train": int(len(df)),
        "n_spread": int(y.sum()),
        "n_no_spread": int(len(y) - y.sum()),
        "cv_method": "5-fold stratified, repeated 20 times; held-out tests only",
        "cv_accuracy": main["accuracy"],
        "baseline_accuracy": round(baseline, 4),
        "auc": main["auc"],
        "safety": {k: main[k] for k in ("burned_called_no_spread", "burned_cases", "extinctions_flagged", "extinction_cases")},
        "comparison": {"gradient_boosting": gb},
        "features": MODEL_FEATURES,
        "coefficients_standardized": dict(zip(MODEL_FEATURES, [round(float(c), 4) for c in coef])),
        "classes": ["no_spread", "spread"],
        "class_order": CLASS_ORDER,
        "feature_range": feature_range,
        "pressure_tolerance_kpa": PRESSURE_TOLERANCE_KPA,
        "spread_threshold": SPREAD_THRESHOLD,
        "no_spread_threshold": NO_SPREAD_THRESHOLD,
        "known_materials": sorted(KNOWN_MATERIALS),
        "trained_materials": TRAINED_MATERIALS,
    }

    tmp_artifact = MODEL_ARTIFACT.with_suffix(".joblib.tmp")
    with open(tmp_artifact, "wb") as fh:
        joblib.dump(pipe, fh)
    os.replace(tmp_artifact, MODEL_ARTIFACT)
    _write_checksum(MODEL_ARTIFACT)

    tmp_meta = MODEL_META.with_suffix(".json.tmp")
    tmp_meta.write_text(json.dumps(meta, indent=2))
    os.replace(tmp_meta, MODEL_META)
    MODEL_META.chmod(0o444)

    sf = meta["safety"]
    print(f"Trained quenching boundary on {len(df)} SIBAL tests ({int(y.sum())} burned, {len(y) - int(y.sum())} went out)")
    print(f"  held-out accuracy {main['accuracy']:.3f} (always-burns {baseline:.3f}) | AUC {main['auc']:.3f}")
    print(f"  burning tests called NO SPREAD: {sf['burned_called_no_spread']}/{sf['burned_cases']} | "
          f"extinctions flagged: {sf['extinctions_flagged']}/{sf['extinction_cases']}")
    print(f"  gradient boosting, same folds: {gb}")
    print(f"  standardized coefficients {meta['coefficients_standardized']}")
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
        self.known_materials = set(self.meta.get("known_materials", [])) | KNOWN_MATERIALS
        # Materials the boundary was fitted for, and only if they have enough
        # measured tests (a new material needs data, not a code change).
        counts = self.df[self.df["in_training"]]["material"].value_counts()
        self.materials_with_data = {
            m for m in self.meta.get("trained_materials", []) if counts.get(m, 0) >= MIN_ROWS_FOR_PREDICTION
        }

    def prob_spread(self, oxygen_pct, flow_cm_s) -> np.ndarray:
        """P(spread) from the fitted boundary. Used by /predict and /boundary
        alike, so the plot and the prediction cannot disagree."""
        return self.pipe.predict_proba(u_features(oxygen_pct, flow_cm_s))[:, 1]

    def _model_summary(self) -> dict[str, Any]:
        return {
            "type": self.meta["type"],
            "n_train": self.meta["n_train"],
            "cv_accuracy": self.meta["cv_accuracy"],
            "baseline_accuracy": self.meta.get("baseline_accuracy"),
            "auc": self.meta.get("auc"),
            "safety": self.meta.get("safety"),
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
        tol = self.meta.get("pressure_tolerance_kpa", 0.0)
        return (
            fr["oxygen_pct"]["min"] <= oxygen_pct <= fr["oxygen_pct"]["max"]
            and fr["pressure_kpa"]["min"] - tol <= pressure_kpa <= fr["pressure_kpa"]["max"] + tol
            and fr["flow_cm_s"]["min"] <= flow_cm_s <= fr["flow_cm_s"]["max"]
        )

    def _class_probabilities(
        self, oxygen_pct: float, pressure_kpa: float, flow_cm_s: float, material: str
    ) -> dict[str, float]:
        # Binary model: marginal_spread is reported as a band of P(spread)
        # (see _predict_class), not as a separate probability.
        p = float(self.prob_spread(oxygen_pct, flow_cm_s)[0])
        return {"no_spread": round(1 - p, 4), "marginal_spread": 0.0, "spread": round(p, 4)}

    def _predict_class(self, proba: dict[str, float]) -> str:
        p_spread = proba["spread"]
        if p_spread >= SPREAD_THRESHOLD:
            return "spread"
        if p_spread <= NO_SPREAD_THRESHOLD:
            return "no_spread"
        return "marginal_spread"

    def nearest_experiments(
        self,
        oxygen_pct: float,
        pressure_kpa: float,
        flow_cm_s: float,
        k: int = 3,
        material: str | None = None,
    ) -> list[dict[str, Any]]:
        """The k closest real experiments by normalized feature distance.

        With a material, only that material's tests with a recorded outcome
        are considered, so a different material is never shown as "nearest".
        """
        df = self.df.copy()
        if material is not None:
            same = df["material"].map(lambda n: matches_material(n, material))
            df = df[same & df["in_training"]]
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
                    "note": r["note"],
                    "oxygen_pct": round(float(r["oxygen_pct"]), 2),
                    "pressure_kpa": round(float(r["pressure_kpa"]), 2),
                    "flow_cm_s": round(float(r["flow_cm_s"]), 2),
                    "outcome": r["outcome_class"],
                    "material": display_material(r["material"]),
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
                    oxygen_pct, pressure_kpa, flow_cm_s, material=material
                ),
                "explanation": (
                    "Requested conditions are outside the published experimental "
                    f"envelope (O2 {fr['oxygen_pct']['min']}-{fr['oxygen_pct']['max']}%, "
                    f"pressure {fr['pressure_kpa']['min']}-{fr['pressure_kpa']['max']} kPa "
                    f"(accepted within {self.meta.get('pressure_tolerance_kpa', 0)} kPa), "
                    f"flow {fr['flow_cm_s']['min']}-{fr['flow_cm_s']['max']} cm/s). "
                    "No prediction is returned; extrapolating a fire-safety answer "
                    "beyond tested data is unsafe."
                ),
            }

        proba = self._class_probabilities(oxygen_pct, pressure_kpa, flow_cm_s, material)
        prediction = self._predict_class(proba)
        nearest = self.nearest_experiments(oxygen_pct, pressure_kpa, flow_cm_s, material=material)

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
