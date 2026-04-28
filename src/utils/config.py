"""
config.py — Central configuration for F1 Strategy AI.
Change these values to target a different race or driver.
"""

from pathlib import Path

#  Project paths 
ROOT = Path(__file__).resolve().parents[2]
DATA_RAW       = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
CACHE_DIR      = ROOT / "data" / "cache"
OUTPUTS_DIR    = ROOT / "outputs"

# Create dirs if they don't exist
for _dir in [DATA_RAW, DATA_PROCESSED, CACHE_DIR, OUTPUTS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

#  Target race ─
YEAR  = 2024
RACE  = "Bahrain"       # Must match FastF1 event name exactly
SESSION = "R"           # R = Race, Q = Qualifying, FP1/FP2/FP3

#  Drivers to analyse 
PRIMARY_DRIVER   = "VER"
COMPARE_DRIVERS  = ["NOR", "SAI", "HAM"]   # For head-to-head strategy plots

#  Simulation parameters 
N_SIMULATIONS   = 1000      # Monte Carlo iterations
RANDOM_SEED     = 42
RACE_LAPS       = 57        # Override if needed; else auto-loaded from FastF1

#  Tyre compounds 
COMPOUNDS = ["SOFT", "MEDIUM", "HARD"]

# Pit stop time loss in seconds (team average — can be tuned per team)
PIT_LOSS = {
    "RBR": 21.5,
    "MCL": 22.1,
    "MER": 22.4,
    "FER": 22.0,
    "DEFAULT": 22.5,
}
TARGET_TEAM = "DEFAULT"

#  Tyre deg model parameters 
# Polynomial degree for degradation curve fit
DEG_POLY_DEGREE = 2

# Lap time noise (std dev in seconds) for Monte Carlo sampling
LAP_TIME_NOISE_STD = 0.3

#  Logging ─
LOG_LEVEL = "INFO"
