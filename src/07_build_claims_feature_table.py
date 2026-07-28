"""
Build the claims-level feature table: parse each claim's free-text "Loss
Dates" event window, aggregate the daily FSA FWI table over that window,
and attach static FSA features.

Run:
    python src/07_build_claims_feature_table.py

Output:
    data/processed/features/{REGION_NAME}_claims_features.csv

climate_days_available / window_coverage_fraction are kept on every row:
check these before trusting fwi_mean/fwi_max/etc, since a window mostly
outside the fire season yields a feature from very few valid days.
"""

import logging
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from common import CLAIMS_DATA_PATH, FWI_COMPONENT_AGG, PROCESSED_DIR, REGION_NAME, validate_claims_feature_table

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DAILY_FWI_PATH = PROCESSED_DIR / "climate" / f"{REGION_NAME}_fsa_fwi_daily.csv"
STATIC_FEATURES_PATH = PROCESSED_DIR / "features" / f"{REGION_NAME}_fsa_static_features.csv"
PROCESSED_FEATURES_DIR = PROCESSED_DIR / "features"
OUT_PATH = PROCESSED_FEATURES_DIR / f"{REGION_NAME}_claims_features.csv"

# e.g. "May 3 - May 18, 2016"
LOSS_DATES_PATTERN = re.compile(
    r"^\s*(?P<start_month>[A-Za-z]+)\s+(?P<start_day>\d{1,2})"
    r"\s*-\s*"
    r"(?P<end_month>[A-Za-z]+)\s+(?P<end_day>\d{1,2})"
    r",\s*(?P<year>\d{4})\s*$"
)


def parse_loss_dates(text: str) -> tuple[date, date]:
    m = LOSS_DATES_PATTERN.match(text)
    if not m:
        raise ValueError(f"Could not parse Loss Dates value: {text!r}")

    year = int(m.group("year"))
    start = pd.to_datetime(f"{m.group('start_month')} {m.group('start_day')} {year}").date()
    end = pd.to_datetime(f"{m.group('end_month')} {m.group('end_day')} {year}").date()

    if end < start:  # window crosses a year boundary
        start = pd.to_datetime(f"{m.group('start_month')} {m.group('start_day')} {year - 1}").date()

    return start, end


def compute_window_fwi_features(daily_fwi: pd.DataFrame, fsa: str, start: date, end: date) -> dict:
    """Both the zero-days and success cases below build their component
    columns from the same FWI_COMPONENT_AGG dict (src/common.py), so they
    can't drift out of sync the way two hand-maintained dicts did before
    (DMC was missing from this function entirely until caught in review)."""
    window = daily_fwi[
        (daily_fwi["CFSAUID"] == fsa)
        & (daily_fwi["date"] >= pd.Timestamp(start))
        & (daily_fwi["date"] <= pd.Timestamp(end) + pd.Timedelta(hours=23, minutes=59))
    ]
    total_days = (end - start).days + 1
    valid = window.dropna(subset=["FWI"])
    n_valid = len(valid)

    if n_valid == 0:
        result = {
            "climate_days_available": 0,
            "window_coverage_fraction": 0.0,
            "fwi_mean": np.nan, "fwi_max": np.nan, "fwi_p95": np.nan,
            "days_fwi_above_30": 0,
        }
        for component, agg in FWI_COMPONENT_AGG.items():
            result[f"{component.lower()}_{agg}"] = np.nan
        return result

    result = {
        "climate_days_available": n_valid,
        "window_coverage_fraction": n_valid / total_days,
        "fwi_mean": valid["FWI"].mean(),
        "fwi_max": valid["FWI"].max(),
        "fwi_p95": valid["FWI"].quantile(0.95),
        "days_fwi_above_30": int((valid["FWI"] > 30).sum()),
    }
    for component, agg in FWI_COMPONENT_AGG.items():
        result[f"{component.lower()}_{agg}"] = getattr(valid[component], agg)()
    return result


def build_claims_feature_table(out_path: Path = OUT_PATH) -> Path:
    log.info("Loading claims data from %s", CLAIMS_DATA_PATH)
    claims = pd.read_csv(CLAIMS_DATA_PATH)

    log.info("Parsing %d unique Loss Dates value(s)...", claims["Loss Dates"].nunique())
    parsed = claims["Loss Dates"].apply(parse_loss_dates)
    claims["event_start"] = parsed.apply(lambda t: t[0])
    claims["event_end"] = parsed.apply(lambda t: t[1])
    for window in claims[["Loss Dates", "event_start", "event_end"]].drop_duplicates().itertuples():
        log.info("  %r -> %s to %s", window[1], window[2], window[3])

    log.info("Loading daily FSA FWI table from %s", DAILY_FWI_PATH)
    daily_fwi = pd.read_csv(DAILY_FWI_PATH, parse_dates=["date"])

    log.info("Computing event-window FWI features for %d claim rows...", len(claims))
    feature_rows = [
        compute_window_fwi_features(daily_fwi, row.FSA, row.event_start, row.event_end)
        for row in claims.itertuples()
    ]
    claims = pd.concat([claims, pd.DataFrame(feature_rows, index=claims.index)], axis=1)

    zero_coverage = (claims["climate_days_available"] == 0).sum()
    if zero_coverage:
        log.warning("%d claim row(s) have zero valid climate days", zero_coverage)
    low_coverage = claims[(claims["window_coverage_fraction"] > 0) & (claims["window_coverage_fraction"] < 0.5)]
    if len(low_coverage):
        log.warning("%d claim row(s) have <50%% window coverage", len(low_coverage))

    log.info("Loading static FSA features from %s", STATIC_FEATURES_PATH)
    static_features = pd.read_csv(STATIC_FEATURES_PATH)
    # claims' exposure cols are event-time snapshot; static_features' are current portfolio
    claims = claims.merge(static_features, on="FSA", how="left", suffixes=("_at_claim", "_current_portfolio"))

    for problem in validate_claims_feature_table(claims):
        log.warning("Feature table validation: %s", problem)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    claims.to_csv(out_path, index=False)
    log.info("Wrote %d rows to %s", len(claims), out_path)

    return out_path


if __name__ == "__main__":
    build_claims_feature_table()
