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
