# Model Notes — Tyre Degradation & Lap Time Prediction

## 1. Tyre Degradation Model (`tyre_deg.py`)

### What it models

For each tyre compound (SOFT / MEDIUM / HARD), a 3-phase piecewise-linear model
is fit via `pwlf.PiecewiseLinFit`:

```
Bedding  (laps 1–B₁):   often flat or slightly negative slope
Plateau  (laps B₁–B₂):  roughly linear degradation
Cliff    (laps B₂+):    steep slope increase — the phase transition
```

`LapTime` is **fuel-corrected** lap time in seconds (see §2). The breakpoints
`B₁` and `B₂` are optimised jointly with the segment slopes, so the model finds
the phase boundaries from the data rather than assuming a fixed lap count.

**Why not a polynomial?** A degree-2 (or higher) polynomial forces a single
smooth curve across all three phases and cannot represent a genuine step
change in slope, which is what the cliff physically is. Full reasoning and
the specific failure modes considered are in [`docs/decisions.md`](decisions.md).

### Cliff detection

The cliff lap is the final internal breakpoint, exposed via
`TyreDegModel.cliff_lap(compound)`. The interval returned by `cliff_ci()`
is experimental; its breakpoint coverage has not been validated.

A cliff is only reported when:
- the final segment's slope exceeds `DEG_CLIFF_THRESHOLD` (0.12 s/lap), **and**
- it's the steepest of the three segments

This guards against false positives on flat compounds and U-shaped curves
(e.g. rubber balling, where the tyre can briefly get *faster* mid-stint —
without the guard this would otherwise look like a cliff to a naive slope check).

### Driver-weighted fitting

`TyreDegModel.fit(laps, driver="VER", driver_weight=4.0)` up-weights the named
driver's laps via `sample_weight` while still fitting on the full fleet
dataset. This retains available fitting data while giving the selected driver greater weight. See `docs/decisions.md` for the rationale.

### Fit density thresholds

- **≥ 12 clean laps** (`DEG_MIN_LAPS_FULL`): full 3-segment fit
- **6–11 laps** (`DEG_MIN_LAPS_FALLBACK`): falls back to a 2-segment fit (plateau + cliff, no bedding phase)
- **< 6 laps**: compound is skipped entirely rather than fitting on noise

### Track temperature scaling

`TyreDegModel.set_track_temp(track_temp_celsius)` scales the **degradation
excess** (predicted lap time minus that compound's baseline) by a factor
derived from mean session track temperature relative to a 35°C reference,
clamped to 0.6×–1.6×. Baseline pace is deliberately untouched — a hotter
track doesn't make lap 1 faster, it makes the tyre fall off faster later.

### Training data

- Source: FastF1 `session.laps` for the target race
- Feature: `TyreAge`
- Target: `FuelCorrectedLapTime` (falls back to `LapTimeSec` if unavailable)
- Filter: `IsAccurate=True`, non-pit laps, green-flag laps (`TrackStatus == "1"`), per-compound outlier removal via vectorised Z-score

### Fit quality

Mean absolute error computed during fitting measures error on the training laps. This measures in-sample fit and does not establish held-out predictive accuracy.

---

## 2. Fuel Correction

```python
FuelCorrectedLapTime = LapTime - (total_laps - lap_number) * 0.05
```

Removes the ~0.05 s/lap improvement as the car burns fuel over the race. This
constant is a conservative estimate — real teams use car-specific aerodynamic
sensitivity values that vary by circuit speed. Applying a fixed correction
across all circuits is a known simplification (see Limitations below).

---

## 3. Pit Stop Time Loss (`pit_loss.py`)

The simulator treats `pit_loss` as the relative cost of a stop and charges it once.
The data estimator averages available `PitDuration` values between 15 and 60 seconds.
A raw pit-lane duration is only a proxy for time lost versus staying on track.

When usable durations are absent, configuration defaults apply
(21.5 seconds for Red Bull, 22.5 seconds generic).

---

## 4. Lap Time Context Helpers (`lap_time.py`)

This module defines track-evolution and safety-car expected-value helpers.
The primary deterministic and Monte Carlo strategy engines use tyre-model
predictions directly and do not call these helpers. Safety-car events and
track evolution are currently omitted from strategy evaluation.

---

## 5. Monte Carlo Noise

Each iteration adds Gaussian noise per lap:

```
lap_time += N(0, σ)   where σ = LAP_TIME_NOISE_STD (default 0.3s, adjustable 0–1s via dashboard)
```

The Gaussian distribution and its standard deviation are configurable
modelling assumptions, rather than independently calibrated uncertainty.

---

## 6. Rival Engine (`rival.py`)

The engine scans candidate laps for undercut and overcut scenarios, reporting
gap-change scores, percentiles, and simulated success rates. A positive gap
means the rival is ahead; a negative gap means we are ahead.

These are simplified short-horizon projections. The undercut projection
does not deduct the rival's eventual stop cost, and the overcut projection
ends before our later stop. Their scores do not establish which strategy
wins a complete exchange.

---

## Known Limitations

| Limitation | Impact | Status |
|------------|--------|--------|
| Fixed fuel correction coefficient | Effect varies by circuit | Open — needs circuit-specific value |
| Safety-car events omitted from primary simulation | Can't discover "pit under this SC" as a strategy | Open — planned: SC Monte Carlo layer |
| Single-race model fit | Bahrain deg rates ≠ Monaco; ~15–18 laps/compound is a data-poverty floor | Open — planned: circuit-cluster multi-race training |
| One rival at a time | Can't model a 3-way battle | Open |

See [`docs/improvements.md`](improvements.md) for the prioritised roadmap addressing the open items.
