"""
Shared paths/config/validation for the numbered scripts in this directory.
Not numbered itself -- Python can't import a module starting with a digit,
so numbered scripts import only from here, never from each other. This is
also the only place `tests/` can reach pipeline logic without duplicating
it, since the numbered scripts themselves can't be imported either.

REGION_NAME picks an entry from REGIONS: single source of truth for a
region's climate bbox + FSA province filter, so switching it changes both
output filenames and actual filtering everywhere. Bbox is standard
lat/lon (-90/90, -180/180) -- the 0-360 longitude conversion NEX-GDDP-CMIP6
needs happens in 01_fetch_climate_data.py, not here.
"""

from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

REGIONS = {
    "alberta": {
        # Must match the FSA boundary shapefile's PRNAME field exactly --
        # see 03_extract_fsa_boundaries.py.
        "province_name": "Alberta",
        # Climate bbox in standard degrees north / degrees (-180 to 180,
        # negative = west) -- see 01_fetch_climate_data.py for the 0-360
        # conversion this feeds into.
        "lat_min": 49.0,
        "lat_max": 60.0,
        "lon_min": -120.05,
        "lon_max": -109.95,
    },
}

REGION_NAME = "alberta"
REGION = REGIONS[REGION_NAME]

PORTFOLIO_DATA_PATH = RAW_DIR / "provided_portfolio_data.csv"
CLAIMS_DATA_PATH = RAW_DIR / "provided_claims_data.csv"

# Single source of truth for the 6 Canadian FWI System components. Used by
# 05 (raw daily columns), 07 (event-window aggregation), and the EDA
# notebook -- previously each hardcoded its own copy of "the 6 components"
# and two of them silently fell out of sync (DMC missing from 07's
# aggregation, then DMC+ISI missing from the notebook's correlation
# matrix). Add/remove a component here and every consumer picks it up.
FWI_COMPONENTS = ["DC", "DMC", "FFMC", "ISI", "BUI", "FWI"]

# Aggregation applied to each component (except FWI itself, which gets a
# richer set of summary stats -- see 07_build_claims_feature_table.py) when
# building event-window claim features. Output column name is
# "{component.lower()}_{agg}".
FWI_COMPONENT_AGG = {"DC": "max", "DMC": "max", "FFMC": "max", "ISI": "max", "BUI": "mean"}
FWI_COMPONENT_AGG_COLUMNS = [f"{c.lower()}_{agg}" for c, agg in FWI_COMPONENT_AGG.items()]
FWI_SUMMARY_COLUMNS = ["fwi_mean", "fwi_max", "fwi_p95", "days_fwi_above_30"]
FWI_FEATURE_COLUMNS = FWI_SUMMARY_COLUMNS + FWI_COMPONENT_AGG_COLUMNS

# Future horizon for climate-scenario loss projection -- same model/scenario
# (EC-Earth3, SSP1-2.6) as the historical fetch, just a different year
# range. 2045-2050 (6 years) chosen as a mid-century horizon that's still
# fast enough to fetch given the deadline.
FUTURE_YEARS = range(2045, 2051)

# Columns the modelling notebook depends on -- checked by
# validate_claims_feature_table() at the end of 07_build_claims_feature_table.py.
REQUIRED_CLAIMS_FEATURE_COLUMNS = [
    "FSA", "Loss Dates", "Loss Frequency", "Total $ Loss",
    "Number of Exposure_at_claim", "Number of Exposure_current_portfolio",
    "climate_days_available", "window_coverage_fraction",
    "dominant_fuel_pct",
] + FWI_FEATURE_COLUMNS
CLAIMS_FEATURE_KEY_COLUMNS = ["FSA", "Loss Dates"]
CLAIMS_FEATURE_NON_NEGATIVE_COLUMNS = [
    "Total $ Loss", "Number of Exposure_at_claim", "Number of Exposure_current_portfolio",
]


# --- Small, pure utility functions -----------------------------------------
# Extracted from the numbered scripts below so the same logic is both
# reusable and unit-testable (numbered scripts can't be `import`ed --
# see the module docstring above -- so this is the only place tests can
# reach this logic without duplicating it).

def lon_360_to_180(lon: float) -> float:
    """Convert a longitude from the source data's native 0-360 convention
    to standard -180/180. Used by 05_aggregate_climate_to_fsa.py when
    building grid-cell polygons in EPSG:4326."""
    return ((lon + 180) % 360) - 180


def weighted_mean_matrix(weights, values):
    """NaN-aware weighted mean via matrix multiplication: `weights`
    (n_targets, n_sources) applied to `values` (n_sources, n_series) gives
    (n_targets, n_series) weighted means, treating NaN entries in `values`
    as missing -- excluded from both the numerator and the weight total for
    that target/series, rather than propagating NaN. A target/series
    combination is NaN only if every source it draws from is NaN for that
    series, not if only some are. This is the exact computation
    05_aggregate_climate_to_fsa.py uses to average climate grid cells onto
    FSA polygons -- see docs/data_dictionary.md's note on FSA/day NaN
    handling."""
    valid = ~np.isnan(values)
    values_filled = np.where(valid, values, 0.0)
    weighted_sum = weights @ values_filled
    weight_sum = weights @ valid.astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(weight_sum > 0, weighted_sum / weight_sum, np.nan)


def validate_fwi_climate_inputs(tas, hurs, pr, sfcwind):
    """Value-range sanity checks on the four climate variables feeding
    xclim's FWI computation (02_compute_fwi.py) -- catches unit mistakes
    (e.g. Celsius mistaken for the expected Kelvin) that a metadata-only
    check (an attrs string that merely *says* the right unit) would miss.
    Returns a list of human-readable problem descriptions; an empty list
    means no problems were found."""
    problems = []

    tas = np.asarray(tas, dtype=float)
    valid_tas = tas[~np.isnan(tas)]
    if valid_tas.size and ((valid_tas < 150) | (valid_tas > 340)).any():
        problems.append("tas has values outside the plausible Kelvin range (150-340K) -- check units")

    # Tolerances below are not arbitrary: run against the real Alberta
    # NEX-GDDP-CMIP6 subsets, hurs reaches 100.23% in 2015-2025 (42 of
    # ~7.07M values) and 121.1% in 2045-2050 (60 of ~3.86M), and sfcWind
    # reaches -0.66 m/s in 2015-2025 (16 of ~7.07M) -- small, low-count
    # excursions consistent with known BCSD downscaling/interpolation
    # artifacts near a physical bound, not a units mistake. The tolerance
    # is wide enough to pass both real files but still catches a genuinely
    # wrong variable (e.g. a signed wind component, or humidity in the
    # wrong units/scale entirely).
    hurs = np.asarray(hurs, dtype=float)
    valid_hurs = hurs[~np.isnan(hurs)]
    if valid_hurs.size and ((valid_hurs < -5) | (valid_hurs > 135)).any():
        problems.append("hurs has values far outside the plausible 0-100% range (allowing a small downscaling-artifact margin)")

    pr = np.asarray(pr, dtype=float)
    valid_pr = pr[~np.isnan(pr)]
    if valid_pr.size and (valid_pr < -0.01).any():
        problems.append("pr has meaningfully negative value(s) -- precipitation cannot be negative")

    sfcwind = np.asarray(sfcwind, dtype=float)
    valid_wind = sfcwind[~np.isnan(sfcwind)]
    if valid_wind.size and (valid_wind < -1.0).any():
        problems.append("sfcWind has meaningfully negative value(s) -- wind speed cannot be negative")

    return problems


def validate_claims_feature_table(
    df,
    required_columns=REQUIRED_CLAIMS_FEATURE_COLUMNS,
    key_columns=CLAIMS_FEATURE_KEY_COLUMNS,
    non_negative_columns=CLAIMS_FEATURE_NON_NEGATIVE_COLUMNS,
):
    """Cheap sanity checks on the final claims feature table
    (07_build_claims_feature_table.py) before it's used for modelling:
    required columns present, no duplicate (FSA, event) rows, and no
    negative exposure/loss values. Returns a list of human-readable
    problem descriptions; an empty list means no problems were found --
    callers decide whether to warn or hard-fail."""
    problems = []

    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        problems.append(f"missing required column(s): {missing}")

    present_keys = [c for c in key_columns if c in df.columns]
    if present_keys:
        dup_mask = df.duplicated(subset=present_keys, keep=False)
        if dup_mask.any():
            problems.append(f"{int(dup_mask.sum())} duplicate-key row(s) on {present_keys}")

    for col in non_negative_columns:
        if col in df.columns and (df[col].dropna() < 0).any():
            problems.append(f"negative value(s) found in column {col!r}")

    return problems
