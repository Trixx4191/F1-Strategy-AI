# Model Notes — Tyre Degradation & Lap Time Prediction

## 1. Tyre Degradation Model (`tyre_deg.py`)

### What it models

For each tyre compound (SOFT / MEDIUM / HARD), we fit:

```
LapTime(tyre_age) = β₀ + β₁·age + β₂·age²  +  ε
```

where `LapTime` is **fuel-corrected** lap time in seconds.

The fuel-corrected target strips out the car getting lighter as fuel burns off (~0.05s/lap improvement as the tank empties), so the model captures *only* tyre degradation — not fuel load effects.

### Training data

- Source: FastF1 `session.laps` for the target race
- Features: `TyreAge` (1 scalar feature)
- Target: `FuelCorrectedLapTime` (or `LapTimeSec` as fallback)
- Filter: only green-flag laps, non-pit laps, `IsAccurate=True`, Z-score outlier removal

### Fit quality

Mean absolute error computed during fitting measures error on the training laps. This measures in-sample fit and does not establish held-out predictive accuracy.

---

## 2. Fuel Correction

```python
FuelCorrectedLapTime = LapTime - (total_laps - lap_number) * 0.05
```

This removes the ~0.05 seconds/lap improvement as the car burns ~1.7 kg of fuel per lap. The constant (0.05 s/lap) is a conservative estimate — real teams use car-specific aerodynamic sensitivity values. The coefficient is a configurable modelling assumption.

**Limitation**: We apply a fixed correction; in reality this varies with circuit speed (higher-speed circuits have greater fuel sensitivity).

---

## 3. Pit Stop Time Loss (`pit_loss.py`)

The simulator treats `pit_loss` as the relative cost of a stop and charges it once.
The data estimator averages available `PitDuration` values between 15 and 60 seconds.
A raw pit-lane duration is only a proxy for time lost versus staying on track.

When usable durations are absent, configuration defaults apply
(21.5 seconds for Red Bull, 22.5 seconds generic).

---

## 4. Lap Time Helpers (`lap_time.py`)

This module defines track-evolution and safety-car expected-value helpers.
Their presence does not imply integration into the primary strategy simulation.

---

## 5. Monte Carlo Noise

Each Monte Carlo iteration adds Gaussian noise per lap:

```
lap_time += N(0, σ)   where σ = LAP_TIME_NOISE_STD (default 0.3s)
```

This represents:
- Track condition variation
- Driver performance variation (traffic, lock-ups, small mistakes)
- Timing measurement noise

The 0.3-second default is a modelling assumption.

---

## Known Limitations

| Limitation | Impact | Possible fix |
|------------|--------|-------------|
| Fixed fuel correction coefficient | ±0.1s on short/long laps | Use circuit-specific value |
| No inter-compound crossover modelling | Doesn't detect "cliff" correctly | Piecewise regression |
| Deg model fitted on all drivers' laps | Driver noise adds variance | Filter to target driver only |
| No safety car strategic response | SC can make pit stops free | Add SC event layer to Monte Carlo |
| Single race fit | Bahrain deg rates ≠ Monaco | Would need multi-race training |

See `docs/improvements.md` for the roadmap addressing these.
