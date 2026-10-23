"""Export a real historical race into a small, network-independent demo bundle.

Run with PYTHONPATH=. python scripts/prepare_demo.py after caching Bahrain 2024.
Only public race data is exported; no HTTP caches or credentials are included.
"""
import json
import argparse
import os
from pathlib import Path

import pandas as pd

from src.pipeline.loader import load_session, get_circuit_outline


def encode_frame(frame):
    frame = pd.DataFrame(frame).copy()
    timedeltas = [c for c in frame if pd.api.types.is_timedelta64_dtype(frame[c])]
    datetimes = [c for c in frame if pd.api.types.is_datetime64_any_dtype(frame[c])]
    for col in timedeltas:
        frame[col] = frame[col].dt.total_seconds()
    for col in datetimes:
        frame[col] = frame[col].astype(str)
    return {
        "records": json.loads(frame.to_json(orient="records")),
        "timedeltas": timedeltas,
        "datetimes": datetimes,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-run", action="store_true", help="Also regenerate the initial simulation")
    args = parser.parse_args()
    session = load_session(2024, "Bahrain")
    payload = {
        "year": 2024, "race": "Bahrain",
        "source": "FastF1: 2024 Bahrain Grand Prix, Race (historical data)",
        "laps": encode_frame(session.laps),
        "results": encode_frame(session.results),
        "weather": encode_frame(session.weather_data),
        "circuit": get_circuit_outline(session),
    }
    target = Path("data/demo/bahrain-2024.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, allow_nan=False))
    print(f"Exported {len(session.laps)} laps to {target}")
    if args.with_run:
        os.environ["F1_DEMO_MODE"] = "true"
        from backend.main import SimulateRequest, simulate
        from fastapi.encoders import jsonable_encoder
        result = simulate(SimulateRequest(year=2024, race="Bahrain"))
        # Plot-cache files belong to the preparation host. The browser can
        # generate this plot from the bundled backtest payload on demand.
        if result.get("backtest"):
            result["backtest"].pop("plot_url", None)
        target.with_name("default-run.json").write_text(
            json.dumps(jsonable_encoder(result), allow_nan=False)
        )
        print(f"Exported {len(result['strategies'])} strategies")
