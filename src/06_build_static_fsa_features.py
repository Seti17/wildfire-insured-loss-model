"""
Build the static (time-invariant) FSA feature table: portfolio exposure +
fuel summary, one row per FSA.

Run:
    python src/06_build_static_fsa_features.py

Output:
    data/processed/features/{REGION_NAME}_fsa_static_features.csv

Base table is the portfolio's FSA list; fuel is left-joined so FSAs
missing boundary geometry stay in the table with NaN fuel columns.
"""

import logging
from pathlib import Path

import pandas as pd

from common import PORTFOLIO_DATA_PATH, PROCESSED_DIR, REGION_NAME

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

FUEL_SUMMARY_PATH = PROCESSED_DIR / "fuel" / f"{REGION_NAME}_fsa_fuel_summary.csv"
PROCESSED_FEATURES_DIR = PROCESSED_DIR / "features"
PROCESSED_FEATURES_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = PROCESSED_FEATURES_DIR / f"{REGION_NAME}_fsa_static_features.csv"


def build_static_fsa_features(out_path: Path = OUT_PATH) -> Path:
    log.info("Loading portfolio data from %s", PORTFOLIO_DATA_PATH)
    portfolio = pd.read_csv(PORTFOLIO_DATA_PATH)
    log.info("Loading fuel summary from %s", FUEL_SUMMARY_PATH)
    fuel = pd.read_csv(FUEL_SUMMARY_PATH).rename(columns={"CFSAUID": "FSA"})

    merged = portfolio.merge(fuel, on="FSA", how="left")

    missing_fuel = merged.loc[merged["dominant_fuel_code"].isna(), "FSA"].tolist()
    if missing_fuel:
        log.warning("%d portfolio FSA(s) have no fuel data: %s", len(missing_fuel), sorted(missing_fuel))
    else:
        log.info("All portfolio FSAs matched to fuel data.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_path, index=False)
    log.info("Wrote %d rows to %s", len(merged), out_path)

    return out_path


if __name__ == "__main__":
    build_static_fsa_features()
