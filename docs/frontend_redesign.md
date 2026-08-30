# Frontend Redesign — F1 Mission Control

**Goal**: Transform the Streamlit dashboard into a dense, multi-panel race-engineer workstation that feels like a real F1 pit wall / mission-control room (inspired by the Azure F1 control-room aesthetic).

**Future flexibility**: Component boundaries and data contracts are designed so the UI can later be extracted into a React/Next.js (or similar) frontend talking to a FastAPI backend while keeping the Python simulation engine unchanged.

---

## Design Principles

1. **Data density first** — real F1 software is information-dense, not sparse “pretty cards”.
2. **Single coherent view** — primary experience is one wide multi-panel layout, not classic tab switching.
3. **Live / progressive feel** — simulation progress, lap counter, tyre phase, and driver nodes should feel alive.
4. **Dark industrial aesthetic** — pure black / near-black panels, thin borders, F1 red accent, monospace numbers, subtle scanlines/glass.
5. **Separation of concerns** — pure presentation components receive pre-computed data structures; no simulation logic inside UI components.

---

## Target Layout (Mission Control Shell)

```
┌─ TOP BAR ──────────────────────────────────────────────────────────────────┐
│ LOGO · SEASON · GP · SESSION · STATUS (LIVE/SIM) · WEATHER · CLOCK · TEAM  │
├─────────────┬────────────────────────────────────────┬─────────────────────┤
│             │                                        │                     │
│  TIMING     │           TRACK MAP + NODES            │  DRIVER STATUS      │
│  TOWER      │  Circuit outline · car dots · sectors  │  CARDS / NODES      │
│  (pos, gap, │  Selected driver highlight · pit lane  │  Tyre · age · cliff │
│   sectors,  │                                        │  Predicted pace     │
│   compound) │                                        │  Gap to rival       │
│             │                                        │                     │
├─────────────┼────────────────────────────────────────┼─────────────────────┤
│             │                                        │                     │
│  STRATEGY   │      SIM PROGRESS / LAP TRACE          │  RIVAL ENGINE       │
│  RESULTS    │  Current lap · stint phase · deltas    │  Undercut / Overcut │
│  Top strats │  MC progress bar · recommended window  │  EV timeline        │
│  P10/P50/P90│                                        │  Win probability    │
│             │                                        │                     │
└─────────────┴────────────────────────────────────────┴─────────────────────┘
│  BOTTOM STRIP: Tyre degradation curves + cliff CI + compound comparison    │
└────────────────────────────────────────────────────────────────────────────┘
```

Sidebar remains the **control surface** (session selection, driver, MC parameters, Run button).

---

## Component Architecture (Streamlit phase)

```
src/visualisation/
├── dashboard.py                 # Thin orchestrator + session state + layout
├── components/
│   ├── top_bar.py               # Sticky nav / status strip
│   ├── timing_tower.py          # Positions, gaps, compounds, sectors
│   ├── track_map.py             # Circuit + driver nodes (Plotly or SVG)
│   ├── driver_cards.py          # Status cards / nodes for selected + rivals
│   ├── strategy_panel.py        # Top strategies + recommended pit windows
│   ├── sim_progress.py          # Lap counter, phase, MC progress, lap trace
│   ├── rival_panel.py           # Undercut/overcut EV + gap
│   ├── tyre_strip.py            # Bottom degradation curves + cliff badges
│   └── theme.py                 # Shared CSS variables + panel primitives
├── tyre_plots.py                # Existing plot helpers (kept, wrapped)
├── strategy_plots.py
├── rival_plots.py
└── assets/                      # Circuit SVGs, icons, etc. (future)
```

Each component:
- Accepts a clean data dict / DataFrame
- Returns HTML/CSS or a Streamlit element
- Has no knowledge of FastF1 or Monte Carlo internals

---

## Data Contracts (stable for future React migration)

```python
# Example shapes the UI will consume

SessionMeta = {
    "year": int,
    "race": str,
    "session": str,
    "track_temp": float | None,
    "weather": dict,
    "status": "idle" | "loading" | "simulating" | "ready",
}

TimingRow = {
    "pos": int,
    "driver": str,
    "team_color": str,
    "gap": float | None,          # to leader
    "interval": float | None,     # to car ahead
    "compound": str,
    "tyre_age": int,
    "last_lap": float | None,
    "sectors": list[float | None],
}

DriverNode = {
    "code": str,
    "x": float, "y": float,       # normalised track position 0-1
    "compound": str,
    "selected": bool,
    "status": "racing" | "pitting" | "out",
}

StrategyResult = {
    "rank": int,
    "compound_sequence": list[str],
    "pit_laps": list[int],
    "mean_time": float,
    "p10": float, "p50": float, "p90": float,
    "win_rate": float | None,
}

SimProgress = {
    "current_lap": int,
    "total_laps": int,
    "stint_phase": "bedding" | "plateau" | "cliff",
    "mc_done": int,
    "mc_total": int,
    "recommended_window": tuple[int, int] | None,
}
```

These contracts will become the JSON API surface later.

---

## Implementation Phases (Frontend)

### Phase B1 — Shell (this sprint)
- [ ] New multi-panel grid layout in `dashboard.py`
- [ ] `theme.py` — shared CSS variables + panel primitives
- [ ] `top_bar.py`
- [ ] Placeholder panels for Timing Tower, Track Map, Driver Cards, Strategy, Sim Progress, Rival, Tyre Strip
- [ ] Sidebar remains functional (session selection + Run)
- [ ] Existing simulation pipeline still runs; results feed into the new shell

### Phase B2 — Core panels
- [ ] Real Timing Tower from classification + lap data
- [ ] Track Map (static circuit outline first, then position dots)
- [ ] Driver status cards with live tyre/cliff info
- [ ] Strategy panel + Sim progress visualisation

### Phase B3 — Rival + polish + “live” feel
- [ ] Rival EV panel integrated
- [ ] Lap-by-lap or progressive reveal of results
- [ ] Micro-animations, better density, responsive breakpoints
- [ ] Export / screenshot mode

### Later — Flexible frontend
- Extract data contracts into a FastAPI layer
- Rebuild the same panels in React (or equivalent) consuming the API
- Keep Python engine + models untouched

---

## Tech choices (Streamlit phase)

| Concern              | Choice                          | Reason |
|----------------------|----------------------------------|--------|
| Layout               | `st.columns` + custom CSS grid   | Fastest path to dense panels |
| Interactive charts   | Plotly (new) + existing Matplotlib | Track map + live-updating traces |
| Track geometry       | FastF1 position data or static SVG | Start simple, upgrade later |
| State                | `st.session_state`               | Standard |
| “Live” updates       | `st.fragment` / progressive fill | Avoid full page reloads |
| Future migration     | Pure data in / pure HTML out     | Easy to port |

---

## Visual language (from control-room reference)

- Background: pure black `#000` / `#080808`
- Panels: `#0f0f0f` – `#161616` with 1px `#1e1e1e` borders
- Accent: F1 red `#e8002d`
- Typography: Antonio (display) + Titillium Web / monospace for numbers
- No rounded corners on primary panels (sharp industrial look)
- Subtle scanline / noise texture (already present)
- High-contrast numbers, colour-coded compounds and status

---

## Success criteria for the shell

1. One coherent wide view that feels like a control room, not a blog post with tabs.
2. All existing simulation outputs still reachable and correctly displayed.
3. Clear component boundaries so any panel can be rewritten in another framework later.
4. 2026 races (including Dutch GP) appear automatically as soon as FastF1 has the data.
"""
