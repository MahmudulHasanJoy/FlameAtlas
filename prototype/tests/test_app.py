"""Headless app tests with Streamlit's AppTest (no browser needed)."""

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).parents[1] / "app.py")


def run_app():
    at = AppTest.from_file(APP, default_timeout=30)
    at.run()
    assert not at.exception
    return at


def test_app_starts_on_iss_preset_with_danger():
    at = run_app()
    assert at.title[0].value == "FlameAtlas"
    assert any("DANGER" in e.value for e in at.error)


def test_exploration_preset_is_untested_with_pressure_warning():
    at = run_app()
    at.selectbox[2].select("Exploration 8.2 psia (56.5 kPa, 34% O2)").run()
    assert not at.exception
    assert any("UNTESTED" in i.value for i in at.info)
    assert any("kPa" in w.value for w in at.warning)


def test_low_oxygen_low_flow_is_not_danger():
    at = run_app()
    at.slider[0].set_value(17.0).run()
    at.slider[1].set_value(3.0).run()
    assert not at.exception
    assert not any("DANGER" in e.value for e in at.error)


def test_material_without_data_shows_gap():
    at = run_app()
    at.selectbox[0].select("nomex").run()
    assert not at.exception
    assert any("research gap" in i.value for i in at.info)


def test_opposed_flow_has_no_tests_in_this_data():
    at = run_app()
    at.radio[0].set_value("opposed").run()
    assert not at.exception
    assert any("only in concurrent flow" in i.value for i in at.info)
