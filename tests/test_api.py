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


def test_cards_listed_with_sources_and_verification():
    j = client.get("/cards", headers=KEY).json()
    assert len(j["cards"]) >= 10
    assert j["verification"]["all_passed"] is True
    for c in j["cards"]:
        assert c["quotes"], c["card_id"]
        for sid in c["source_ids"]:
            assert j["sources"][sid]["url"].startswith("https://")
            assert "file" not in j["sources"][sid]


def test_cards_filter_and_lookup():
    sibal = client.get("/cards?material=sibal", headers=KEY).json()["cards"]
    assert sibal and all("sibal" in c["material_ids"] for c in sibal)
    assert client.get("/cards/CARD-BASS2-SIBAL", headers=SAME_ORIGIN).json()["card"]["card_id"] == "CARD-BASS2-SIBAL"
    assert client.get("/cards/NOPE", headers=KEY).status_code == 404
    assert client.get("/cards").status_code == 401


def test_every_map_report_with_a_card_resolves():
    # Each card link must point at a report id that exists in the experiment data.
    exp_ids = {e["report_id"] for e in client.get("/boundary?material=sibal&n=10", headers=KEY).json()["experiments"]}
    linked = {r for c in client.get("/cards", headers=KEY).json()["cards"] for r in c["linked_report_ids"]}
    assert "NTRS-20210011385" in linked & exp_ids
