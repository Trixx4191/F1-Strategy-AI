"""Exercise the deployed demo end to end with stdlib HTTP requests."""
import json
import sys
import urllib.request

base = sys.argv[1].rstrip("/")


def request(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        content = response.read()
        print(path, response.status, len(content), flush=True)
        return content, response.headers.get("Content-Type", "")


assert b"root" in request("/")[0]
assert json.loads(request("/api/health")[0])["service"] == "f1-strategy-ai"
assert json.loads(request("/api/seasons/latest")[0])["year"] == 2024
assert json.loads(request("/api/seasons/2024/races")[0])["races"] == ["Bahrain"]
session = json.loads(request("/api/session?year=2024&race=Bahrain")[0])
assert len(session["timing"]) == 20 and session["circuit"]["points"]
initial = json.loads(request("/api/demo/run")[0])
assert len(initial["strategies"]) == 2772
body = dict(year=2024, race="Bahrain", driver="VER", rival="NOR", n_simulations=50, strategy_type="1-stop")
run = json.loads(request("/api/simulate", body)[0])
assert run["strategies"] and run["backtest"]
csv, kind = request("/api/simulate/csv", {**body, "precomputed_strategies": run["strategies"]})
assert "text/csv" in kind and len(csv.splitlines()) > 2
rival = json.loads(request("/api/rival-analysis", {**body, "our_compound": "SOFT", "rival_compound": "HARD"})[0])
assert rival["race_trace"] and rival["undercut_timeline"] and rival["overcut_timeline"]
for path, payload in [
    ("/api/undercut/plot", {"mc_results": run["strategies"], "race_laps": 57}),
    ("/api/overcut/plot", {"overcut_scan": rival["overcut_timeline"]}),
    ("/api/rival/compare-plot", rival),
    ("/api/backtest/plot", {"backtest": initial["backtest"]}),
]:
    data, kind = request(path, payload)
    assert kind.startswith("image/png") and data.startswith(b"\x89PNG")
print("All deployed demo checks passed.", flush=True)
