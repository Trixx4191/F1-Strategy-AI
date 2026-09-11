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
| Simulation-driven Track Map replay | Overview track map: play/pause, seek, restart, speed control, lap progress, and driver labels |
| Live temp + manual override | Sidebar |

## Simulation persistence and saved runs

The React client persists simulation state in the browser using `localStorage`.
This is intentionally client-local: it survives refreshes in the same browser
but is not a server sync or cross-device store.

- **Auto-save current run** stores the current result, selected session, model
	controls, and active tab. A refresh restores the result without requiring a
	new simulation request.
- **Reset current run** clears only the active result and its browser snapshot;
	saved simulations remain available.
- **Save to My Sims** copies the current result into a browser-local saved-run
	list. Saved runs can be loaded, individually deleted, selected for comparison,
	or cleared together from the Saved Sims tab.
- **Compare selected** ranks the selected runs by optimal mean time and shows
	the best strategy, time delta, win rate, pit laps, and a winner indicator.

The storage keys are versioned in `frontend/src/App.tsx`:
`f1-strategy-ai.current-run.v1`, `f1-strategy-ai.saved-runs.v1`, and
`f1-strategy-ai.ui-state.v1`. Storage failures are ignored gracefully so a
quota or privacy-mode error does not prevent the dashboard from running.

## Track Map replay

After a simulation, the Overview Track Map uses the returned optimal simulated
lap-time trace and the FastF1 circuit outline. Every displayed driver node is
interpolated along the real circuit and labelled with its driver code. The
compact replay bar supports Play/Pause, Restart, a seek slider, and `10x`,
`25x`, `50x`, and `100x` playback speeds. Without a simulation trace, the map
falls back to the circuit outline and session timing data.

The Under/Overcut plot pane remains mounted while tabs are switched and is only
hidden visually. This prevents expensive plot requests from being repeated just
because the user navigated to another tab; plot inputs still trigger a refresh
when the relevant session or simulation controls change.

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
