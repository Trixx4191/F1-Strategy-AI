# Contributing to F1 Strategy AI

Thanks for your interest. Contributions are welcome — especially from anyone with motorsport data or engineering experience.

## Getting Started

```bash
git clone https://github.com/Trixx4191/F1-Strategy-AI.git
cd f1-strategy-ai
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install pytest jupyterlab  # dev extras
```

## Areas Where Help Is Most Valuable

**Tyre model improvements**
- Non-linear cliff detection (changepoint / piecewise regression)
- Compound-specific outlier strategies

**Simulation engine**
- Weather branching (wet / intermediate strategy paths)
- Safety Car probability injection into MC iterations

**Rival modelling**
- Multi-car battle scanning (not just one rival)
- DRS train modelling

**Data pipeline**
- Telemetry sector analysis (sector-level pace delta)
- Qualifying → race pace normalisation

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
