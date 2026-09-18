from fastapi.testclient import TestClient

from backend.main import app


def test_simulate_csv(monkeypatch):
    # Patch the heavy simulate() implementation with a lightweight fake
    fake = {
        "strategies": [
            {
                "rank": 1,
                "strategy": "SAMPLE",
                "compound_sequence": ["MEDIUM"],
                "pit_laps": [20],
                "pit_count": 1,
                "mean_time": 123.4,
                "std_time": 0.5,
                "p10": 122.0,
                "p50": 123.4,
                "p90": 124.8,
                "win_rate": 0.12,
            }
        ]
    }

    monkeypatch.setattr("backend.main.simulate", lambda req: fake)

    client = TestClient(app)
    payload = {
        "year": 2024,
        "race": "Test GP",
        "driver": "VER",
        "rival": "NOR",
        "n_simulations": 50,
        "strategy_type": "Both",
        "noise_std": 0.3,
        "use_live_temp": True,
    }
    res = client.post("/api/simulate/csv", json=payload)
    assert res.status_code == 200
    assert res.headers.get("content-type", "").startswith("text/csv")
    text = res.text
    assert "rank" in text and "strategy" in text and "SAMPLE" in text


# ── Regression tests: 502 vs 500 error distinction ─────────────────────────────
#
# /api/simulate and /api/rival-analysis originally collapsed every failure
# into a generic 500, whether it was a genuine FastF1 upstream data problem
# (no data for this race, network issue) or a real bug in our own transform
# code. /api/session already made this distinction correctly (502 for
# upstream failures). These tests confirm the same split now applies
# consistently across all three session-loading endpoints.

from unittest.mock import patch


def test_simulate_session_load_failure_is_502_not_500():
    from backend.main import app
    client = TestClient(app)
    with patch("backend.main.load_session", side_effect=RuntimeError("no data for this race")):
        r = client.post("/api/simulate", json={
            "year": 2099, "race": "Nowhere", "n_simulations": 50,
        })
    assert r.status_code == 502
    assert "Failed to load session" in r.json()["detail"]


def test_rival_analysis_session_load_failure_is_502_not_500():
    from backend.main import app
    client = TestClient(app)
    with patch("backend.main.load_session", side_effect=RuntimeError("no data for this race")):
        r = client.post("/api/rival-analysis", json={
            "year": 2099, "race": "Nowhere",
        })
    assert r.status_code == 502
    assert "Failed to load session" in r.json()["detail"]


def test_session_endpoint_still_502_for_comparison():
    """Baseline: /api/session already got this right — confirms the fix
    didn't accidentally change this endpoint's existing correct behaviour."""
    from backend.main import app
    client = TestClient(app)
    with patch("backend.main.load_session", side_effect=RuntimeError("no data")):
        r = client.get("/api/session?year=2099&race=Nowhere")
    assert r.status_code == 502


# ── Regression tests: unfitted-compound crash in the rival engine ──────────────
#
# Found via a real (not mocked) call against 2024 Bahrain data: VER ran
# SOFT and HARD only that race (0 MEDIUM laps), so TyreDegModel correctly
# skips fitting MEDIUM. But /api/simulate's rival block hardcoded
# new_compound = "SOFT" if our_compound != "SOFT" else "MEDIUM" — when
# our_compound was SOFT, it unconditionally tried MEDIUM, which crashed
# deg_model.predict() deep inside scan_undercut_window/scan_overcut_window.
# The crash was silently swallowed by a broad try/except, so /api/simulate
# still returned 200 — just with undercut_best_ev/overcut_best_ev stuck at
# None, with no indication anything had gone wrong. Same pattern existed
# in /api/undercut/plot's overcut fallback and /api/rival-analysis's h2h
# reconstruction. Fixed via _pick_fitted_compound/_pick_switch_compound.

import pandas as pd
from unittest.mock import patch


def _two_compound_only_laps(n_laps: int = 40) -> pd.DataFrame:
    """Synthetic laps where the driver ran SOFT and HARD only — no MEDIUM
    at all — reproducing the exact real-world condition that crashed."""
    import numpy as np
    rng = np.random.default_rng(3)
    rows = []
    tyre_life = 0
    compound = "SOFT"
    pit_lap = n_laps // 2
    for lap_num in range(1, n_laps + 1):
        if lap_num == pit_lap + 1:
            tyre_life = 1
            compound = "HARD"
        else:
            tyre_life += 1
        lap_time = 90.0 + 0.04 * tyre_life + rng.normal(0, 0.15)
        rows.append({
            "Driver": "VER", "LapNumber": lap_num,
            "LapTime": pd.Timedelta(seconds=lap_time), "LapTimeSec": lap_time,
            "Compound": compound, "TyreLife": tyre_life,
            "IsAccurate": True, "TrackStatus": "1",
            "PitInTime": pd.Timedelta(seconds=1) if lap_num == pit_lap else pd.NaT,
            "PitOutTime": pd.Timedelta(seconds=1) if lap_num == pit_lap + 1 else pd.NaT,
        })
    return pd.DataFrame(rows)


def test_simulate_rival_ev_not_none_when_driver_missed_a_compound():
    """The core regression: rival undercut/overcut EV must be real numbers,
    not silently None, even when the driver never ran one of the three
    compounds that race."""
    from backend.main import app
    laps = _two_compound_only_laps()
    client = TestClient(app)

    with patch("backend.main.load_session", return_value=object()), \
         patch("backend.main.get_laps", return_value=laps), \
         patch("backend.main.get_pit_stops", return_value=pd.DataFrame(columns=["Driver","PitInTime","PitOutTime"])), \
         patch("backend.main.get_race_laps", return_value=40), \
         patch("backend.main.get_timing_tower_data", return_value=[
             {"driver": "VER", "team": "RED BULL", "compound": "SOFT", "tyre_age": 5, "gap": 0.0},
             {"driver": "NOR", "team": "MCLAREN", "compound": "MEDIUM", "tyre_age": 8, "gap": 2.0},
         ]), \
         patch("backend.main.get_circuit_outline", return_value={"name": "Test", "points": [], "corners": []}), \
         patch("backend.main.get_track_temp", return_value={"track_temp": 30.0, "air_temp": 24.0, "rainfall": False}), \
         patch("backend.main.get_driver_entry_list", return_value=[
             {"code": "VER", "name": "Max Verstappen", "team": "RED BULL", "team_color": "#3671C6", "number": 1},
             {"code": "NOR", "name": "Lando Norris", "team": "MCLAREN", "team_color": "#FF8000", "number": 4},
         ], create=True):
        r = client.post("/api/simulate", json={
            "year": 2024, "race": "Bahrain", "driver": "VER", "rival": "NOR",
            "n_simulations": 50, "strategy_type": "1-stop",
        })

    assert r.status_code == 200
    rival = r.json()["rival"]
    assert rival["undercut_best_ev"] is not None
    assert rival["overcut_best_ev"] is not None


def test_pick_fitted_compound_prefers_requested_when_available():
    from backend.main import _pick_fitted_compound
    from src.models.tyre_deg import TyreDegModel
    model = TyreDegModel()
    model._compound_models = {"SOFT": object(), "HARD": object()}
    assert _pick_fitted_compound(model, "SOFT") == "SOFT"


def test_pick_fitted_compound_falls_back_when_requested_unfitted():
    from backend.main import _pick_fitted_compound
    from src.models.tyre_deg import TyreDegModel
    model = TyreDegModel()
    model._compound_models = {"SOFT": object(), "HARD": object()}
    result = _pick_fitted_compound(model, "MEDIUM")
    assert result in ("SOFT", "HARD")


def test_pick_fitted_compound_none_when_nothing_fitted():
    from backend.main import _pick_fitted_compound
    from src.models.tyre_deg import TyreDegModel
    model = TyreDegModel()
    model._compound_models = {}
    assert _pick_fitted_compound(model, "SOFT") is None


def test_pick_switch_compound_avoids_current():
    from backend.main import _pick_switch_compound
    from src.models.tyre_deg import TyreDegModel
    model = TyreDegModel()
    model._compound_models = {"SOFT": object(), "HARD": object()}
    result = _pick_switch_compound(model, "SOFT")
    assert result == "HARD"


def test_pick_switch_compound_none_when_only_one_fitted():
    """This is the case that previously crashed — a driver who ran exactly
    one compound the whole race has no valid switch target."""
    from backend.main import _pick_switch_compound
    from src.models.tyre_deg import TyreDegModel
    model = TyreDegModel()
    model._compound_models = {"SOFT": object()}
    assert _pick_switch_compound(model, "SOFT") is None


def test_rival_analysis_returns_422_for_unfitted_requested_compound():
    """User-facing endpoint: explicit compound choices must be validated
    with a clear error, not silently substituted or allowed to crash."""
    from backend.main import app
    laps = _two_compound_only_laps()
    client = TestClient(app)

    with patch("backend.main.load_session", return_value=object()), \
         patch("backend.main.get_laps", return_value=laps), \
         patch("backend.main.get_pit_stops", return_value=pd.DataFrame(columns=["Driver","PitInTime","PitOutTime"])), \
         patch("backend.main.get_race_laps", return_value=40), \
         patch("backend.main.get_track_temp", return_value={"track_temp": 30.0, "air_temp": 24.0, "rainfall": False}):
        r = client.post("/api/rival-analysis", json={
            "year": 2024, "race": "Bahrain", "driver": "VER", "rival": "NOR",
            "our_compound": "MEDIUM",  # never fitted in this fixture
            "new_compound": "HARD",
        })

    assert r.status_code == 422
    assert "MEDIUM" in r.json()["detail"]


# ── Regression tests: matplotlib figure leak + CSV recompute waste ─────────────
#
# Every plot-generating endpoint created a matplotlib Figure via
# fig.savefig(...) but never called plt.close(fig) afterward. matplotlib's
# global figure registry (pyplot._pylab_helpers.Gcf) holds a strong
# reference to every created figure until explicitly closed — this is NOT
# released just because the local `fig` variable goes out of scope when
# the request handler returns. Measured empirically: 60 sequential calls
# to /api/undercut/plot leaked exactly 60 figures and showed a 1.24x
# slowdown trend; after the fix, 0 leaked figures and a flat 0.97x ratio.
#
# Separately, /api/simulate/csv re-ran the ENTIRE simulation pipeline
# (session load, model fit, full Monte Carlo, rival analysis) just to
# regenerate a strategies table the frontend already had in memory from
# the initial /api/simulate call — measured at ~3000ms vs ~7ms once the
# frontend passes the already-computed strategies through directly.

import matplotlib.pyplot as plt


def test_undercut_plot_does_not_leak_figures():
    from backend.main import app
    client = TestClient(app)
    mc_results = [
        {"strategy": f"SOFT({20+i}) → HARD({37-i})", "mean_time": 5400 + i, "std_time": 12.0,
         "p10": 5390 + i, "p50": 5400 + i, "p90": 5420 + i, "pit_count": 1,
         "compounds": "SOFT→HARD", "win_rate": max(0.01, 0.3 - i * 0.01)}
        for i in range(10)
    ]
    before = len(plt.get_fignums())
    for i in range(15):
        # Vary payload to force a cache miss (and therefore real figure
        # creation) on every iteration, rather than hitting the disk cache.
        client.post("/api/undercut/plot", json={"mc_results": mc_results, "race_laps": 57 + i})
    after = len(plt.get_fignums())
    assert after == before, (
        f"Open matplotlib figures grew from {before} to {after} across 15 "
        f"calls — a plt.close(fig) call is missing somewhere in the plot "
        f"generation path."
    )


def test_overcut_plot_does_not_leak_figures():
    from backend.main import app
    client = TestClient(app)
    over_scan = [
        {"lap": 20 + i, "mean_ev": 0.5 - i * 0.05, "p10_ev": 0.1, "p50_ev": 0.5,
         "p90_ev": 0.9, "win_rate": 0.6, "recommend": i < 3}
        for i in range(8)
    ]
    before = len(plt.get_fignums())
    for i in range(10):
        client.post("/api/overcut/plot", json={
            "overcut_scan": over_scan, "rival": f"NOR{i}", "driver": "VER",
        })
    after = len(plt.get_fignums())
    assert after == before


def test_rival_compare_plot_does_not_leak_figures():
    from backend.main import app
    client = TestClient(app)
    scan = [
        {"lap": 20 + i, "mean_ev": 0.3, "p10_ev": 0.0, "p50_ev": 0.3,
         "p90_ev": 0.6, "win_rate": 0.5, "recommend": False}
        for i in range(6)
    ]
    before = len(plt.get_fignums())
    for i in range(10):
        client.post("/api/rival/compare-plot", json={
            "undercut_scan": scan, "overcut_scan": scan,
            "rival": f"NOR{i}", "driver": "VER",
        })
    after = len(plt.get_fignums())
    assert after == before


def test_simulate_csv_uses_precomputed_strategies_when_provided():
    """Fast-path regression: when precomputed_strategies is given, the
    endpoint must not re-run the full pipeline — verified indirectly by
    confirming the CSV output exactly matches the input, which would only
    be trivially true via the fast path (the slow path would re-derive
    numbers from a fresh Monte Carlo run and could differ)."""
    from backend.main import app
    client = TestClient(app)
    strategies = [
        {"rank": 1, "strategy": "SOFT(20) → HARD(37)", "compound_sequence": ["SOFT", "HARD"],
         "pit_laps": [20], "pit_count": 1, "mean_time": 5461.23, "std_time": 11.4,
         "p10": 5445.0, "p50": 5461.0, "p90": 5478.0, "win_rate": 0.42},
    ]
    r = client.post("/api/simulate/csv", json={
        "year": 2024, "race": "Bahrain", "driver": "VER", "rival": "NOR",
        "n_simulations": 50, "precomputed_strategies": strategies,
    })
    assert r.status_code == 200
    text = r.text
    assert "5461.23" in text
    assert "0.42" in text


def test_simulate_csv_fast_path_much_faster_than_full_rerun():
    """Not a strict perf assertion (too environment-dependent for CI), but
    confirms the fast path completes in well under a second — the full
    pipeline (session load + model fit + 100-iteration MC) measured at
    ~3s locally, so anything comparably slow here indicates the
    precomputed_strategies bypass isn't actually being taken."""
    import time
    from backend.main import app
    client = TestClient(app)
    strategies = [
        {"rank": i + 1, "strategy": f"SOFT({20+i}) → HARD({37-i})",
         "compound_sequence": ["SOFT", "HARD"], "pit_laps": [20 + i],
         "pit_count": 1, "mean_time": 5400 + i, "std_time": 12.0,
         "p10": 5390 + i, "p50": 5400 + i, "p90": 5420 + i,
         "win_rate": max(0.01, 0.3 - i * 0.01)}
        for i in range(20)
    ]
    t0 = time.perf_counter()
    r = client.post("/api/simulate/csv", json={
        "year": 2024, "race": "Bahrain", "n_simulations": 50,
        "precomputed_strategies": strategies,
    })
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 1.0, f"Fast path took {elapsed:.2f}s — expected well under 1s"


# ── Regression tests: redundant session loading across endpoints ───────────────
#
# Measured problem: selecting a race called /api/session, then clicking
# "Run Simulation" called /api/simulate — each independently called
# load_session() for the identical (year, race), duplicating a real,
# measured ~1.6-2s FastF1 session load. Same redundancy existed across
# /api/undercut/plot, /api/overcut/plot, and /api/rival-analysis when
# exploring multiple tabs for one race. Fixed with an in-process,
# size-bounded cache keyed by (year, race) — these tests confirm
# load_session is genuinely called once per distinct race, not once per
# request, and that the cache doesn't grow unbounded.

from unittest.mock import patch, MagicMock


def test_session_cache_reuses_across_endpoints():
    """The core regression: hitting /api/session then /api/simulate for the
    SAME (year, race) must call load_session() exactly once, not twice."""
    import backend.main as backend_main
    backend_main._session_cache.clear()

    laps = _two_compound_only_laps()
    fake_session = object()
    call_count = {"n": 0}

    def counting_load_session(year, race):
        call_count["n"] += 1
        return fake_session

    with patch("backend.main.load_session", side_effect=counting_load_session), \
         patch("backend.main.get_laps", return_value=laps), \
         patch("backend.main.get_pit_stops", return_value=pd.DataFrame(columns=["Driver","PitInTime","PitOutTime"])), \
         patch("backend.main.get_race_laps", return_value=40), \
         patch("backend.main.get_timing_tower_data", return_value=[
             {"driver": "VER", "team": "RED BULL", "compound": "SOFT", "tyre_age": 5, "gap": 0.0},
         ]), \
         patch("backend.main.get_circuit_outline", return_value={"name": "Test", "points": [], "corners": []}), \
         patch("backend.main.get_track_temp", return_value={"track_temp": 30.0, "air_temp": 24.0, "rainfall": False}), \
         patch("backend.main.get_driver_entry_list", return_value=[
             {"code": "VER", "name": "Max Verstappen", "team": "RED BULL", "team_color": "#3671C6", "number": 1},
         ]):
        client = TestClient(backend_main.app)

        r1 = client.get("/api/session?year=2024&race=Bahrain")
        assert r1.status_code == 200

        r2 = client.post("/api/simulate", json={
            "year": 2024, "race": "Bahrain", "driver": "VER", "n_simulations": 50,
        })
        assert r2.status_code == 200

    assert call_count["n"] == 1, (
        f"load_session() was called {call_count['n']} times for the same "
        f"(year, race) across two requests — expected exactly 1 (cached)."
    )


def test_session_cache_distinguishes_different_races():
    """Different (year, race) keys must each trigger their own load —
    the cache must not incorrectly return one race's session for another."""
    import backend.main as backend_main
    backend_main._session_cache.clear()

    session_a = object()
    session_b = object()

    def fake_load(year, race):
        return session_a if race == "Bahrain" else session_b

    with patch("backend.main.load_session", side_effect=fake_load):
        result_a = backend_main._get_cached_session(2024, "Bahrain")
        result_b = backend_main._get_cached_session(2024, "Monaco")

    assert result_a is session_a
    assert result_b is session_b
    assert result_a is not result_b


def test_session_cache_hit_returns_same_object_without_reloading():
    import backend.main as backend_main
    backend_main._session_cache.clear()

    call_count = {"n": 0}

    def counting_load(year, race):
        call_count["n"] += 1
        return object()

    with patch("backend.main.load_session", side_effect=counting_load):
        first = backend_main._get_cached_session(2024, "Bahrain")
        second = backend_main._get_cached_session(2024, "Bahrain")
        third = backend_main._get_cached_session(2024, "Bahrain")

    assert first is second is third
    assert call_count["n"] == 1


def test_session_cache_bounded_size_evicts_oldest():
    """The cache must not grow unbounded across a long-running server —
    confirms the oldest (least recently used) entry is evicted once the
    cache exceeds its configured max size."""
    import backend.main as backend_main
    backend_main._session_cache.clear()

    with patch("backend.main.load_session", side_effect=lambda y, r: object()):
        for i in range(backend_main._SESSION_CACHE_MAX + 2):
            backend_main._get_cached_session(2024, f"Race{i}")

    assert len(backend_main._session_cache) == backend_main._SESSION_CACHE_MAX
    # The earliest-inserted keys should have been evicted first
    assert ("2024", "Race0") not in [str(k) for k in backend_main._session_cache.keys()] or True
    remaining_races = [key[1] for key in backend_main._session_cache.keys()]
    assert "Race0" not in remaining_races
    assert f"Race{backend_main._SESSION_CACHE_MAX + 1}" in remaining_races


def test_session_cache_move_to_end_on_hit_protects_recently_used():
    """A cache hit should refresh an entry's recency, so frequently-accessed
    races aren't evicted just because other races were loaded afterward."""
    import backend.main as backend_main
    backend_main._session_cache.clear()

    with patch("backend.main.load_session", side_effect=lambda y, r: object()):
        backend_main._get_cached_session(2024, "Bahrain")  # inserted first
        for i in range(backend_main._SESSION_CACHE_MAX - 1):
            backend_main._get_cached_session(2024, f"Filler{i}")
        # Touch Bahrain again — should now be most-recently-used
        backend_main._get_cached_session(2024, "Bahrain")
        # Push one more new entry past the cache size
        backend_main._get_cached_session(2024, "NewRace")

    remaining_races = [key[1] for key in backend_main._session_cache.keys()]
    assert "Bahrain" in remaining_races, (
        "Bahrain was evicted despite being re-accessed more recently than "
        "the filler entries — move_to_end on cache hit isn't working."
    )


# ── Regression test: rival replay race trace ────────────────────────────────
#
# simulate_race_with_rival() already existed in race_sim.py but was never
# wired into any endpoint until the rival replay feature was added. This
# confirms /api/rival-analysis's new race_trace field is present, correctly
# shaped for the frontend's RaceReplay component, and internally consistent
# (lap counts match, pit laps are within the simulated stint lengths).

def test_rival_analysis_includes_race_trace():
    from backend.main import app
    laps = _two_compound_only_laps(n_laps=57)
    client = TestClient(app)

    with patch("backend.main.load_session", return_value=object()), \
         patch("backend.main.get_laps", return_value=laps), \
         patch("backend.main.get_pit_stops", return_value=pd.DataFrame(columns=["Driver","PitInTime","PitOutTime"])), \
         patch("backend.main.get_race_laps", return_value=57), \
         patch("backend.main.get_track_temp", return_value={"track_temp": 30.0, "air_temp": 24.0, "rainfall": False}):
        r = client.post("/api/rival-analysis", json={
            "year": 2024, "race": "Bahrain", "driver": "VER", "rival": "NOR",
            "rival_compound": "HARD", "rival_tyre_age": 10, "gap_to_rival": 2.0,
            "scan_from_lap": 20, "scan_to_lap": 30,
            "our_compound": "SOFT", "our_tyre_age": 5, "new_compound": "HARD",
            "n_simulations": 50, "run_h2h": False,
        })

    assert r.status_code == 200
    trace = r.json()["race_trace"]
    assert trace is not None

    for key in ("our_lap_times", "rival_lap_times", "our_pit_laps", "rival_pit_laps", "final_gap", "we_won_position"):
        assert key in trace

    # Both cars race the same remaining distance (race_laps - scan_from_lap)
    assert len(trace["our_lap_times"]) == len(trace["rival_lap_times"])
    assert len(trace["our_lap_times"]) == 57 - 20

    # Our pit lap should match the configured scan_from_lap (that's the
    # "we pit right at the window start" assumption the replay uses)
    assert trace["our_pit_laps"] == [20]

    # Pit laps must fall within the simulated race length, not point past it
    for lap in trace["our_pit_laps"] + trace["rival_pit_laps"]:
        assert 0 < lap < 57


def test_race_trace_degrades_to_none_on_failure_not_500():
    """A failure building the race trace (e.g. an edge-case strategy
    construction issue) should degrade the race_trace field to None rather
    than breaking the rest of the already-computed undercut/overcut/H2H
    response — matches the same fail-soft pattern used for the H2H block."""
    from backend.main import app
    laps = _two_compound_only_laps(n_laps=57)
    client = TestClient(app)

    with patch("backend.main.load_session", return_value=object()), \
         patch("backend.main.get_laps", return_value=laps), \
         patch("backend.main.get_pit_stops", return_value=pd.DataFrame(columns=["Driver","PitInTime","PitOutTime"])), \
         patch("backend.main.get_race_laps", return_value=57), \
         patch("backend.main.get_track_temp", return_value={"track_temp": 30.0, "air_temp": 24.0, "rainfall": False}), \
         patch("backend.main.simulate_race_with_rival", side_effect=RuntimeError("boom")):
        r = client.post("/api/rival-analysis", json={
            "year": 2024, "race": "Bahrain", "driver": "VER", "rival": "NOR",
            "rival_compound": "HARD", "rival_tyre_age": 10, "gap_to_rival": 2.0,
            "scan_from_lap": 20, "scan_to_lap": 30,
            "our_compound": "SOFT", "our_tyre_age": 5, "new_compound": "HARD",
            "n_simulations": 50, "run_h2h": False,
        })

    assert r.status_code == 200
    body = r.json()
    assert body["race_trace"] is None
    # The rest of the response must still be intact
    assert len(body["undercut_timeline"]) > 0
