"""Unit tests for prototype/core.py. Test IDs refer to docs/07-test-plan.md."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import core

DATA = Path(__file__).parents[1] / "data" / "sibal_bass_table71.csv"


def make_records(points):
    """points: list of (o2, flow, outcome[, exclude]) tuples."""
    rows = []
    for i, p in enumerate(points):
        o2, flow, outcome = p[:3]
        rows.append(dict(record_id=f"REC-{i:05d}", o2_pct=o2, flow_cm_s=flow, pressure_kpa=101.3, outcome=outcome,
                         exclude_from_fit=p[3] if len(p) > 3 else False))
    return pd.DataFrame(rows)


@pytest.fixture
def u_shaped():
    """Synthetic data from a known U-shaped rule: burns when O2 > 15 + 1.5 * (log2(flow) - log2(8))**2."""
    pts = []
    for flow in [0.5, 1, 2, 4, 8, 16, 32, 50]:
        for o2 in [14, 16, 18, 20, 22, 26, 30]:
            limit = 15 + 1.5 * (np.log2(flow) - 3) ** 2
            pts.append((o2, flow, "burned" if o2 > limit else "self_extinguished"))
    return make_records(pts)


def test_tc01_fit_recovers_known_boundary(u_shaped):
    m = core.fit_boundary(u_shaped)
    assert m is not None
    assert m.p_burn(30, 8) >= 0.9          # deep in the burn region
    assert m.p_burn(14, 0.5) <= 0.1        # low oxygen, quenching flow
    assert m.p_burn(16, 8) > m.p_burn(16, 0.5)  # U shape: easier to burn at moderate flow


def test_tc02_too_few_rows_returns_none():
    recs = make_records([(21, 10, "burned"), (20, 5, "burned"), (17, 2, "self_extinguished"),
                         (16, 3, "self_extinguished"), (21, 2, "burned")])
    assert core.fit_boundary(recs) is None


def test_tc03_too_few_non_burning_returns_none():
    pts = [(o2, f, "burned") for o2 in (19, 21) for f in (2, 5, 10, 20)] + [(16, 2, "self_extinguished"),
                                                                             (16, 5, "no_ignition")]
    assert core.fit_boundary(make_records(pts)) is None


def test_tc04_inverted_oxygen_effect_returns_none():
    pts = [(o2, f, "burned" if o2 < 18 else "self_extinguished") for o2 in (15, 16, 17, 19, 20, 21) for f in (2, 5, 10)]
    assert core.fit_boundary(make_records(pts)) is None


def test_tc05_envelope(u_shaped):
    m = core.fit_boundary(u_shaped)
    assert m.in_envelope(22, 8)              # a training point
    assert m.in_envelope(31.8, 8)            # 0.9 units above the top edge (O2 30 + 1.8)
    assert not m.in_envelope(33, 8)          # 1.5 units above


def test_tc06_no_model_is_no_boundary():
    assert core.classify_habitat(None, 21, 10) == (core.NO_BOUNDARY, None)


def test_tc07_envelope_checked_before_probability(u_shaped):
    m = core.fit_boundary(u_shaped)
    status, p = core.classify_habitat(m, 40, 8)   # far above all tests, P(burn) would be ~1
    assert status == core.UNTESTED and p is None


class FixedModel:
    def __init__(self, p):
        self.p = p

    def in_envelope(self, o2, flow):
        return True

    def p_burn(self, o2, flow):
        return self.p


@pytest.mark.parametrize("p,expected", [(0.5, core.DANGER), (0.49, core.MARGINAL), (0.2, core.MARGINAL),
                                        (0.19, core.SELF_EXTINGUISHES)])
def test_tc08_status_thresholds(p, expected):
    assert core.classify_habitat(FixedModel(p), 20, 5)[0] == expected


def test_tc09_nearest_tests_order_and_ties():
    recs = make_records([(21, 10, "burned"), (17, 10, "burned"), (21, 20, "burned"), (21, 10, "burned")])
    near = core.nearest_tests(recs, 21, 10, 101.3)
    assert list(near.record_id) == ["REC-00000", "REC-00003", "REC-00002"]
    assert near.distance.iloc[2] == pytest.approx(1.0)  # factor of 2 in flow = 1 unit


def test_tc11_zero_flow_treated_as_minimum():
    assert core.flow_feature(0) == pytest.approx(core.flow_feature(0.5))


def test_tc12_pressure_warning():
    recs = make_records([(21, 10, "burned")])
    assert core.pressure_mismatch(recs, 56.5) == pytest.approx(101.3)
    assert core.pressure_mismatch(recs, 95.0) is None


def test_excluded_rows_not_used_in_fit(u_shaped):
    extra = make_records([(40, 8, "self_extinguished", True)] * 5)
    m1 = core.fit_boundary(u_shaped)
    m2 = core.fit_boundary(pd.concat([u_shaped, extra], ignore_index=True))
    assert m1.p_burn(26, 8) == pytest.approx(m2.p_burn(26, 8))


def test_real_table71_data_is_consistent():
    df = pd.read_csv(DATA)
    assert len(df) == 48                                   # 31 table rows, 17 of them flow sweeps
    assert df.record_id.is_unique
    assert set(df.outcome) <= {"burned", "self_extinguished", "no_ignition"}
    assert df.o2_pct.between(16.4, 21).all()
    assert (df.status == "extracted").all()                # not verified yet: prototype must say so
    assert (df[df.exclude_from_fit].exclude_reason.notna()).all()
    quenched = df[df.extinction_mode == "quench"]
    assert set(quenched.test_label) == {"GMT45-T4", "GMT100-T13", "GMT175-T18", "GMT178-T14", "GMT190-T20",
                                        "GMT190-T22"}   # six quenching cases, as the report states


def test_real_table71_statuses():
    df = pd.read_csv(DATA)
    df["exclude_from_fit"] = df.exclude_from_fit.astype(str).str.lower() == "true"
    m = core.fit_boundary(df[df.sample_variant == "2.2 cm wide"])
    assert m is not None
    assert core.classify_habitat(m, 21, 10)[0] == core.DANGER       # ISS oxygen, normal ventilation
    assert core.classify_habitat(m, 34, 10)[0] == core.UNTESTED     # exploration atmosphere: no tests
