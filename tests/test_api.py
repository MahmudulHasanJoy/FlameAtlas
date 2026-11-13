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


def test_materials_profiles_have_sourced_facts():
    j = client.get("/materials", headers=KEY).json()
    ids = {m["material_id"] for m in j["materials"]}
    assert {"sibal", "pmma", "nomex", "silicone"} <= ids
    for m in j["materials"]:
        assert m["facts"]
        for f in m["facts"]:
            assert f["quotes"] and all(q["source_id"] in j["sources"] for q in f["quotes"])


def test_evidence_points_for_gap_materials():
    for m, at_least in (("pmma", 40), ("nomex", 4), ("silicone", 4)):
        pts = client.get(f"/evidence?material={m}", headers=KEY).json()["points"]
        assert len(pts) >= at_least
        assert all(p["material_id"] == m and p["quotes"] for p in pts)
    j = client.post("/predict", json=body(material="silicone"), headers=KEY).json()
    assert j["data_status"] == "no_outcome_data"


def test_boundary_grid_matches_predict():
    # Guards the grid orientation: P_spread is indexed [flow][o2].
    b = client.get("/boundary?material=sibal&n=60", headers=KEY).json()
    for i in (25, 40, 55):  # flows above the 0.5 cm/s input minimum
        for j in (5, 30, 55):
            pr = client.post("/predict", json={"oxygen_pct": b["o2s"][j], "pressure_kpa": 101.3,
                                               "flow_cm_s": b["flows"][i], "material": "sibal"}, headers=KEY).json()
            assert abs(pr["probabilities"]["spread"] - b["P_spread"][i][j]) < 0.01


def test_sibal_map_and_nearest_use_only_recorded_sibal_tests():
    exps = client.get("/boundary?material=sibal&n=10", headers=KEY).json()["experiments"]
    shown = [e for e in exps if e["same_material"] and e["outcome_recorded"]]
    assert len(shown) >= 38
    assert all(e["outcome"] in ("spread", "no_spread") for e in shown)
    names = {e["material"] for e in exps if e["same_material"]}
    assert {"sibal", "SIBAL Fabric", "Cotton-Fiberglass (SIBAL)"} <= names
    assert not any(e["same_material"] for e in exps if "Heptane" in e["material"] or e["material"] == "PMMA & Nomex")
    # Near Saffire-II conditions the nearest list must still be SIBAL only.
    near = client.post("/predict", json=body(o2=22.0, flow=20.0), headers=KEY).json()["nearest_experiments"]
    assert near and all("sibal" in n["material"].lower() for n in near)
    assert all(n["outcome"] != "marginal_spread" for n in near)
