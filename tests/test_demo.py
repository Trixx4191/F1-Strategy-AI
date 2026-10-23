"""The demo must work without FastF1 or circuit API access."""
import fastf1
import pytest

from src.pipeline.loader import (
    load_session, get_laps, get_circuit_outline,
    get_race_schedule, get_latest_available_year,
)


def test_bundled_race_needs_no_upstream(monkeypatch):
    monkeypatch.setenv("F1_DEMO_MODE", "true")
    monkeypatch.setattr(fastf1, "get_session", lambda *a, **k: pytest.fail("Remote session requested"))
    session = load_session(2024, "Bahrain")
    laps = get_laps(session, "VER")
    assert len(laps) == 57
    assert laps["LapTimeSec"].notna().any()
    assert len(session.results) == 20
    assert len(get_circuit_outline(session)["points"]) > 10
    assert get_latest_available_year() == 2024
    assert get_race_schedule(2024) == ["Bahrain"]
    assert get_race_schedule(2025) == []
    with pytest.raises(ValueError, match="2024 Bahrain"):
        load_session(2025, "Bahrain")


def test_rival_replay_gap_closes_when_we_are_faster():
    from types import SimpleNamespace
    from src.simulator.race_sim import simulate_race_with_rival
    from src.simulator.strategy import Strategy, Stint
    model = SimpleNamespace(models={"SOFT": 1, "HARD": 1}, predict=lambda compound, age: 90 if compound == "SOFT" else 91)
    trace = simulate_race_with_rival(
        Strategy([Stint("SOFT", 5)]), Strategy([Stint("HARD", 5)]),
        model, 22, initial_gap=2,
    )
    assert trace["final_gap"] == -3
    assert trace["we_won_position"] is True
