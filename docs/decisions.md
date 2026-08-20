# Engineering Decisions

This document describes modelling and data-pipeline design choices.
---

## 1. Why piecewise-linear replaced the degree-2 polynomial

**The original approach.** Tyre degradation was modelled as `LapTime(age) = β₀ + β₁·age + β₂·age²` per compound, fit with sklearn on fuel-corrected lap times.

**Why it was wrong.** Real tyre wear has three physically distinct phases:

- **Bedding** (laps 1–3) — new rubber is inconsistent; lap times can *improve* as the tyre comes in
- **Plateau** — roughly linear, predictable degradation
- **Cliff** — an abrupt phase transition as the compound breaks down; slope increases sharply

A parabola forces one smooth curve across all three phases. It cannot represent a step change in slope — mathematically, a polynomial's second derivative is either constant or smoothly varying, never a discontinuity. Trying to detect "the cliff" from a polynomial means taking a derivative trick on a curve shape that was never capable of representing a cliff in the first place.

**The fix.** Replaced with `pwlf.PiecewiseLinFit`, fitting 3 linear segments with jointly-optimised breakpoints. The cliff lap is now a directly estimated parameter (the final internal breakpoint) when the final segment passes the slope and boundary checks.

**Guards added:**
- A "cliff" is only declared if the final segment's slope exceeds a threshold (0.12 s/lap) **and** is the steepest of the three segments — this rejects U-shaped curves (e.g. rubber balling, where the tyre briefly gets faster) that would otherwise falsely trigger cliff detection.
- Below 12 clean laps, the model falls back to a simpler 2-segment fit (plateau + cliff, no bedding phase) rather than overfitting a 3-segment model on too little data.
- Below 6 laps, the compound is skipped entirely rather than reporting a model built on noise.

---

## 2. Why driver-weighted fitting instead of pure driver filtering

**The temptation.** Filter the training data to only the selected driver's laps, so the degradation curve reflects their specific driving style rather than an average across the field.

**Data constraint.** A single driver's laps can be sparse after cleaning. Retaining other drivers' laps increases the available sample, although fit stability and predictive benefit still require validation.


**Implementation.** Keep the full cleaned dataset and up-weight the selected driver's laps (default weight 4×). The weight is a modelling choice; its effect depends on the number and distribution of available laps.

---

## 3. Track temperature scaling — what it does and doesn't do

Degradation excess (the amount by which a lap is slower than the model's own baseline, not the baseline pace itself) is scaled by a factor derived from the session's mean track temperature relative to a neutral reference point (35°C), clamped to a 0.6×–1.6× range.

This deliberately does **not** touch the baseline pace prediction — a hotter track doesn't make the car faster on lap 1, it makes the tyre fall off faster as the stint progresses.

The clamp exists because the scaling factor is a simple linear approximation (1.3%/°C), and without a ceiling, an unusually hot or cold session could produce a scaling factor far outside anything physically plausible.
