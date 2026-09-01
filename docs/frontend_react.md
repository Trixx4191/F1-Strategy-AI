# F1 Strategy AI — Primary Frontend (React Mission Control)

React Mission Control uses the FastAPI backend for simulation and analysis.

`dashboard_mc.py` provides a lightweight Streamlit interface.

## Stack
| Layer | Tech |
|-------|------|
| UI | React 19 + TypeScript + Vite |
| API | FastAPI (`backend/main.py`) |
| Engine | Existing `src/` pipeline (unchanged) |
| Charts | SVG (`Charts.tsx`) — curves, scatter, bars, heat, EV timelines |

## Frontend features

Cliff intervals are experimental and their statistical coverage has not been
validated. Undercut and overcut scans use different evaluation horizons, so
their EV values and recommendations need validation before direct comparison.

| Feature | Where |
|---------|--------|
| Degradation curves + experimental cliff interval | Tyre Model tab ← `tyre_curves` |
| Stint scatter | Tyre Model tab ← `stint_scatter` |
| Phase slopes table | Tyre Model tab ← `phase_slopes` |
| Model summary table (baseline, deg rates, in-sample MAE) | Tyre Model tab ← `model_summary` |
| Strategy comparison bar chart | Strategy tab ← ranked `strategies` |
| Lap trace (top 3) | Strategy tab ← `lap_traces` |
| 1-stop vs 2-stop comparison | Strategy tab ← `stop_comparison` |
| Undercut pit-lap heatmap | Undercut Window tab ← `undercut_heatmap` |
| Undercut/overcut EV timelines (full series, not just best) | Rival Analysis ← timelines |
| Undercut and overcut scan comparison | Rival Analysis |
| Interactive rival params + re-scan | Rival Analysis → `POST /api/rival-analysis` |
| Head-to-head win-rate chart | Rival Analysis ← `h2h` |
| Raw undercut/overcut scan tables | Rival Analysis |
| Backtest (actual vs AI + lap overlay) | Backtest tab ← `backtest` |
| Full results table + CSV export | Results tab |
| Timing tower, weather, pit loss, cliff metrics | Overview |
| Circuit outline from FastF1 (no hardcoded tracks) | Overview track map |
| Live temp + manual override | Sidebar |

## Run
```bash
# Terminal 1 — API
cd f1-strategy-ai
pip install -r requirements.txt
PYTHONPATH=$(pwd) uvicorn backend.main:app --reload --port 8000

# Terminal 2 — UI
cd f1-strategy-ai/frontend
npm install
npm run dev
# → http://localhost:5173
```

## Streamlit interfaces
- `src/visualisation/dashboard.py` — original Streamlit dashboard
- `src/visualisation/dashboard_mc.py` — lightweight Streamlit interface
