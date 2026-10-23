"""Core rules for the FlameAtlas prototype.

Pure functions with no Streamlit imports, implementing docs/06-ai-rag-spec.md:
  Section 5  flammability boundary model (logistic regression, data-sufficiency rule, envelope)
  Section 6  habitat status and nearest tests
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.spatial import ConvexHull, QhullError
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

MIN_FLOW = 0.5  # cm/s; zero flow is drawn and modelled at this value (log axis)
ENVELOPE_MARGIN = 1.0  # normalized units: a factor of 2 in flow or 2 points of O2

DANGER = "DANGER"
MARGINAL = "MARGINAL"
SELF_EXTINGUISHES = "SELF-EXTINGUISHES"
UNTESTED = "UNTESTED"
NO_BOUNDARY = "NO BOUNDARY"


def flow_feature(flow_cm_s):
    """log2 of flow, with zero and tiny flows clamped to MIN_FLOW."""
    return np.log2(np.maximum(np.asarray(flow_cm_s, dtype=float), MIN_FLOW))


def normalized(o2_pct, flow_cm_s):
    """Map conditions to the space where 1 unit = 2 points of O2 or a factor of 2 in flow."""
    return np.column_stack([flow_feature(flow_cm_s), np.asarray(o2_pct, dtype=float) / 2.0])


def burn_label(outcome: pd.Series) -> np.ndarray:
    return (outcome == "burned").astype(int).to_numpy()


def fit_rows(records: pd.DataFrame) -> pd.DataFrame:
    """Rows allowed in the boundary fit."""
    return records[~records["exclude_from_fit"]]


def sufficiency_problem(rows: pd.DataFrame) -> str | None:
    """Return why a boundary cannot be drawn, or None if the data is sufficient (spec 5.2, rules 1 to 3)."""
    y = burn_label(rows["outcome"])
    if len(rows) < 8:
        return f"only {len(rows)} usable tests (8 needed)"
    if y.sum() < 3 or (len(y) - y.sum()) < 3:
        return f"{int(y.sum())} burned and {int(len(y) - y.sum())} not burned (3 of each needed)"
    if rows["flow_cm_s"].nunique() < 3 or rows["o2_pct"].nunique() < 2:
        return "too few distinct airflow or oxygen values"
    return None


@dataclass
class BoundaryModel:
    pipeline: object
    points: np.ndarray  # normalized coordinates of the training rows
    hull: ConvexHull | None
    n_rows: int

    def p_burn(self, o2_pct, flow_cm_s):
        o2 = np.atleast_1d(np.asarray(o2_pct, dtype=float))
        L = flow_feature(np.atleast_1d(flow_cm_s))
        X = np.column_stack([o2, L, L**2])
        p = self.pipeline.predict_proba(X)[:, 1]
        return float(p[0]) if np.ndim(o2_pct) == 0 and np.ndim(flow_cm_s) == 0 else p

    def in_envelope(self, o2_pct, flow_cm_s):
        q = normalized(np.atleast_1d(o2_pct), np.atleast_1d(flow_cm_s))
        inside = _envelope_mask(q, self.points, self.hull)
        return bool(inside[0]) if np.ndim(o2_pct) == 0 and np.ndim(flow_cm_s) == 0 else inside


def _envelope_mask(q: np.ndarray, points: np.ndarray, hull: ConvexHull | None) -> np.ndarray:
    """True where q is inside the convex hull of points or within ENVELOPE_MARGIN of it."""
    if hull is not None:
        # Hull facets satisfy normal . x + offset <= 0 inside; signed distance is the max over facets.
        eq = hull.equations
        signed = q @ eq[:, :-1].T + eq[:, -1]
        outside_dist = signed.max(axis=1)
        mask = outside_dist <= 0
        # For points outside, the max facet distance can underestimate; use vertex distance as a bound check.
        near = np.zeros(len(q), dtype=bool)
        cand = ~mask
        if cand.any():
            near[cand] = _distance_to_hull(q[cand], points[hull.vertices]) <= ENVELOPE_MARGIN
        return mask | near
    d = np.sqrt(((q[:, None, :] - points[None, :, :]) ** 2).sum(axis=2)).min(axis=1)
    return d <= ENVELOPE_MARGIN


def _distance_to_hull(q: np.ndarray, vertices: np.ndarray) -> np.ndarray:
    """Exact distance from each point in q to the boundary polygon given by ordered hull vertices (2-D)."""
    a = vertices
    b = np.roll(vertices, -1, axis=0)
    ab = b - a
    out = np.empty(len(q))
    for i, p in enumerate(q):
        t = np.clip(((p - a) * ab).sum(axis=1) / np.maximum((ab**2).sum(axis=1), 1e-12), 0, 1)
        proj = a + t[:, None] * ab
        out[i] = np.sqrt(((proj - p) ** 2).sum(axis=1)).min()
    return out


def fit_boundary(records: pd.DataFrame) -> BoundaryModel | None:
    """Fit P(burn | O2, flow) for one fit group, or return None if the spec's rules are not met."""
    rows = fit_rows(records)
    if sufficiency_problem(rows) is not None:
        return None
    L = flow_feature(rows["flow_cm_s"])
    X = np.column_stack([rows["o2_pct"].to_numpy(float), L, L**2])
    y = burn_label(rows["outcome"])
    pipe = make_pipeline(StandardScaler(), LogisticRegression(C=1.0, class_weight="balanced"))
    pipe.fit(X, y)
    if pipe[-1].coef_[0][0] <= 0:  # rule 4: more oxygen must not make burning less likely
        return None
    pts = normalized(rows["o2_pct"], rows["flow_cm_s"])
    try:
        hull = ConvexHull(np.unique(pts, axis=0))
        hull_pts = np.unique(pts, axis=0)
    except (QhullError, ValueError):
        hull, hull_pts = None, pts
    return BoundaryModel(pipeline=pipe, points=hull_pts, hull=hull, n_rows=len(rows))


def classify_habitat(model: BoundaryModel | None, o2_pct: float, flow_cm_s: float) -> tuple[str, float | None]:
    """Habitat status per spec 6.2. Returns (status, P(burn) or None)."""
    if model is None:
        return NO_BOUNDARY, None
    if not model.in_envelope(o2_pct, flow_cm_s):
        return UNTESTED, None
    p = model.p_burn(o2_pct, flow_cm_s)
    if p >= 0.5:
        return DANGER, p
    if p >= 0.2:
        return MARGINAL, p
    return SELF_EXTINGUISHES, p


def distance(o2_a, flow_a, p_a, o2_b, flow_b, p_b):
    """Normalized distance between conditions (spec 6.1)."""
    return np.sqrt(
        ((np.asarray(o2_a) - o2_b) / 2.0) ** 2
        + (flow_feature(flow_a) - flow_feature(flow_b)) ** 2
        + ((np.asarray(p_a) - p_b) / 20.0) ** 2
    )


def nearest_tests(records: pd.DataFrame, o2_pct: float, flow_cm_s: float, pressure_kpa: float, k: int = 3):
    """The k closest records by normalized distance, ties broken by record_id."""
    if records.empty:
        return records.assign(distance=[])
    d = distance(records["o2_pct"], records["flow_cm_s"], records["pressure_kpa"], o2_pct, flow_cm_s, pressure_kpa)
    return records.assign(distance=d).sort_values(["distance", "record_id"]).head(k)


def pressure_mismatch(records: pd.DataFrame, pressure_kpa: float, limit_kpa: float = 15.0) -> float | None:
    """Median tested pressure if the habitat differs from it by more than limit_kpa, else None."""
    if records.empty:
        return None
    median = float(records["pressure_kpa"].median())
    return median if abs(pressure_kpa - median) > limit_kpa else None


def boundary_grid(model: BoundaryModel, n: int = 200):
    """P(burn) on a log-flow x linear-O2 grid, NaN outside the envelope (spec 5.4)."""
    flows = np.logspace(np.log10(MIN_FLOW), np.log10(60), n)
    o2s = np.linspace(10, 40, n)
    F, O = np.meshgrid(flows, o2s)
    P = model.p_burn(O.ravel(), F.ravel()).reshape(F.shape)
    inside = model.in_envelope(O.ravel(), F.ravel()).reshape(F.shape)
    return flows, o2s, np.where(inside, P, np.nan), inside
