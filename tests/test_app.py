from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parents[1]))
from streamlit.testing.v1 import AppTest


def test_demo_ui_and_filters(monkeypatch):
    monkeypatch.setenv("DASHBOARD_DEFAULT_MODE", "demo")
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=60).run()
    assert not app.exception
    assert any("SYNTHETIC DEMO" in x.value for x in app.warning)
    app.selectbox(key="focus_site").select("galle").run()
    assert not app.exception
    for box in app.selectbox:
        if box.label == "Explorer product":
            box.select("Forecast vintages")
            break
    app.run()
    assert not app.exception
    assert len(app.get("download_button")) >= 6


def test_invalid_live_shard_does_not_loop_reruns(monkeypatch):
    import app as module
    import data
    monkeypatch.delenv("DASHBOARD_DEFAULT_MODE", raising=False)
    monkeypatch.delenv("FISHERIES_LOCAL_SNAPSHOT", raising=False)
    monkeypatch.setattr(data, "repo_info", lambda _: {"sha": "a" * 40, "siblings": []})
    monkeypatch.setattr(data, "load_hf_bundle", lambda *args: (_ for _ in ()).throw(ValueError("fixture invalid shard")))
    module.cached_info.clear()
    module.cached_live.clear()
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert any("live connector failed" in x.value.lower() for x in app.error)


def test_map_click_updates_same_harbour_state(monkeypatch):
    import app as module
    state = {"harbour_map": {"selection": {"objects": {"land-points": [{"site_id": "galle"}]}}}}
    monkeypatch.setattr(module.st, "session_state", state)
    module.map_selected()
    assert state["focus_site"] == "galle"


def test_clearing_severity_selection_returns_no_rows():
    import app as module
    from demo import generate_demo
    from data import build_daily
    frame = build_daily(generate_demo("2026-10-09"), today="2026-10-09")
    dates = (frame.date_local.min().date(), frame.date_local.max().date())
    assert module.filtered(frame, ["galle"], dates, severity=[]).empty


def test_live_failure_is_explicit_and_demo_isolated(monkeypatch):
    import app as module
    import data
    monkeypatch.delenv("DASHBOARD_DEFAULT_MODE", raising=False)
    monkeypatch.delenv("FISHERIES_LOCAL_SNAPSHOT", raising=False)
    monkeypatch.setattr(data, "repo_info", lambda _: (_ for _ in ()).throw(ConnectionError("fixture offline")))
    module.cached_info.clear()
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=60).run()
    assert not app.exception
    assert any("live connector failed" in x.value.lower() for x in app.error)
    assert any("SYNTHETIC DEMO" in x.value for x in app.warning)


def test_combined_timeline_spans_history_to_forecast():
    import app as module
    from demo import generate_demo
    from data import build_daily, build_forecasts
    demo = generate_demo("2026-10-09")
    history = build_daily(demo, include_recent=True)
    forecasts = build_forecasts(demo)
    combined = module.build_combined_timeline(history, forecasts)
    assert not combined.empty
    assert combined.date_local.min() == history.date_local.min()
    assert combined.date_local.max() == forecasts.date_local.max()
    assert "galle" in combined.site_id.values


def test_theme_mode_dark_selection(monkeypatch):
    monkeypatch.setenv("DASHBOARD_DEFAULT_MODE", "demo")
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=60).run()
    assert not app.exception
    for radio in app.radio:
        if radio.label == "Theme":
            radio.set_value("Dark")
            break
    app.run()
    assert not app.exception


def test_coastal_location_dropdown_selection(monkeypatch):
    monkeypatch.setenv("DASHBOARD_DEFAULT_MODE", "demo")
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"), default_timeout=60).run()
    assert not app.exception
    coastal_box = app.selectbox(key="coastal_location_picker")
    coastal_box.select("myliddy").run()
    assert not app.exception
    assert app.session_state["focus_site"] == "myliddy"


