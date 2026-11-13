"""Smoke tests for the deployed API surface (dashboard, auth, gap handling)."""
import os

os.environ["FLAMEATLAS_API_KEY"] = "test-key"

from fastapi.testclient import TestClient  # noqa: E402

from src.api.app import app  # noqa: E402

client = TestClient(app)
KEY = {"X-API-Key": "test-key"}
SAME_ORIGIN = {"Sec-Fetch-Site": "same-origin"}


def body(o2=21.0, material="sibal", flow=10.0):
    return {"oxygen_pct": o2, "pressure_kpa": 101.3, "flow_cm_s": flow, "material": material}


def test_dashboard_served_without_key_in_page():
    r = client.get("/")
    assert r.status_code == 200
    assert "FlameAtlas" in r.text or "flameatlas" in r.text.lower()
    assert "X-API-Key" not in r.text and "test-key" not in r.text


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_predict_requires_key_for_direct_calls():
    assert client.post("/predict", json=body()).status_code == 401
    assert client.post("/predict", json=body(), headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.post("/predict", json=body(), headers={"Sec-Fetch-Site": "cross-site"}).status_code == 401


def test_predict_with_key_and_from_dashboard():
    for headers in (KEY, SAME_ORIGIN):
        r = client.post("/predict", json=body(), headers=headers)
        assert r.status_code == 200
        assert r.json()["data_status"] == "ok"
        assert r.json()["prediction"] in {"spread", "no_spread", "marginal_spread"}


def test_material_without_outcome_data_returns_gap():
    for m in ("pmma", "nomex"):
        j = client.post("/predict", json=body(material=m), headers=KEY).json()
        assert j["data_status"] == "no_outcome_data"
        assert j["prediction"] is None and j["probabilities"] is None
    assert client.get("/boundary?material=pmma", headers=KEY).status_code == 422


def test_out_of_range_returns_no_prediction():
    j = client.post("/predict", json=body(o2=34.0), headers=KEY).json()
    assert j["data_status"] == "out_of_range"
    assert j["prediction"] is None
    assert "feature_range" in j["model"]


def test_boundary_for_sibal():
    j = client.get("/boundary?material=sibal&n=20", headers=KEY).json()
    assert len(j["P_spread"]) == 20 and j["experiments"]
