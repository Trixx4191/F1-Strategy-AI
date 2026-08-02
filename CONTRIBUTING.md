# Contributing to F1 Strategy AI

Thanks for your interest. Contributions are welcome — especially from anyone with motorsport data or engineering experience.

## Getting Started

```bash
git clone https://github.com/Trixx4191/F1-Strategy-AI.git
cd f1-strategy-ai
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` already includes `pytest` and `jupyterlab` — no separate dev-extras install needed.

Or with Docker:

```bash
docker compose up --build
```

## Areas Where Help Is Most Valuable

The tyre model, undercut/overcut engine, and driver-weighted fitting are
implemented and remain open to validation and improvement. See
[`docs/architecture.md`](docs/architecture.md) and
[`docs/decisions.md`](docs/decisions.md) for implementation context.

**Tyre model**
- Circuit-cluster multi-race training (pool laps across similar-deg circuits — the
  proposed way to increase training data; see `docs/improvements.md`)
- Mixed-effects driver modelling once cluster training provides enough per-driver data

**Simulation engine**
- Safety Car Monte Carlo layer — sample SC events from historical `TrackStatus`
  frequency and re-evaluate pit timing when one fires mid-simulation
- Weather branching (wet / intermediate strategy paths)

**Rival modelling**
- Multi-car battle scanning (currently one rival at a time)
- DRS train modelling

**Data pipeline / UI**
- Strategy history tab — pit lap heatmap by year for the selected circuit
- Telemetry analysis module — track map, speed/brake/throttle traces, sector deltas
  (in progress, see project roadmap)

## Code Standards

- Type hints on all public functions
- Docstrings (NumPy format) on all classes and public methods
- No bare `except` clauses
- `pytest` for all new logic — aim for ≥ 80% coverage on new modules

## Pull Request Process

1. Fork → feature branch (`git checkout -b feat/tyre-cliff`)
2. Write tests first where possible
3. Run `pytest tests/ -v` — all must pass
4. Open a PR with a clear description of what the change does and why

## Issues

Use GitHub Issues for bugs and feature requests. For bugs, include:
- Race/year that reproduces the issue
- Full traceback
- Python / FastF1 version (`fastf1.__version__`)
