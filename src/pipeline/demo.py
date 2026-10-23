"""Load the bundled public race data without remote services."""
import json
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import fastf1
import pandas as pd


@lru_cache(maxsize=1)
def load_demo_session():
    path = Path(__file__).resolve().parents[2] / "data/demo/bahrain-2024.json"
    payload = json.loads(path.read_text())

    def decode_frame(data):
        frame = pd.DataFrame(data["records"])
        for col in data["timedeltas"]:
            frame[col] = pd.to_timedelta(frame[col], unit="s")
        for col in data["datetimes"]:
            frame[col] = pd.to_datetime(frame[col], errors="coerce")
        return frame

    return SimpleNamespace(
        laps=fastf1.core.Laps(decode_frame(payload["laps"])),
        results=decode_frame(payload["results"]),
        weather_data=decode_frame(payload["weather"]),
        demo_circuit=payload["circuit"],
    )
