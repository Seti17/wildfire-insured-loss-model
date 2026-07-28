"""
Filter the national StatCan FSA boundary file down to one region
(province) and cross-check coverage against the portfolio's FSA list.

Run:
    python src/03_extract_fsa_boundaries.py

Output:
    data/processed/boundaries/{REGION_NAME}_fsa_boundaries.gpkg

Notes:
- Filters by province name (common.REGIONS[REGION_NAME]["province_name"]).
- Output is GeoPackage, not GeoJSON: source CRS (EPSG:3347) is projected, GeoJSON requires WGS84.
- Portfolio FSAs with no matching polygon are logged, not silently dropped.
"""

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from common import PORTFOLIO_DATA_PATH, PROCESSED_DIR, RAW_DIR, REGION, REGION_NAME

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

PROVINCE_NAME = REGION["province_name"]
NATIONAL_FSA_SHAPEFILE = RAW_DIR / "boundary_data" / "canada_fsa" / "lfsa000b21a_e.shp"
PROCESSED_BOUNDARIES_DIR = PROCESSED_DIR / "boundaries"
PROCESSED_BOUNDARIES_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = PROCESSED_BOUNDARIES_DIR / f"{REGION_NAME}_fsa_boundaries.gpkg"


def extract_region_fsa_boundaries(out_path: Path = OUT_PATH) -> Path:
    log.info("Loading national FSA boundary file from %s", NATIONAL_FSA_SHAPEFILE)

    gdf = gpd.read_file(NATIONAL_FSA_SHAPEFILE)
    log.info("Loaded %d FSA polygons nationally (CRS: %s)", len(gdf), gdf.crs)

    subset = gdf[gdf["PRNAME"] == PROVINCE_NAME].copy()

    if subset.empty:
        raise ValueError(f"No FSA polygons found for {PROVINCE_NAME}")

    subset.reset_index(drop=True, inplace=True)
    log.info("%s subset: %d FSA polygons", PROVINCE_NAME, len(subset))

    if PORTFOLIO_DATA_PATH.exists():
        portfolio_fsas = set(pd.read_csv(PORTFOLIO_DATA_PATH)["FSA"].astype(str).str.strip())
        shapefile_fsas = set(subset["CFSAUID"].astype(str).str.strip())
        missing = sorted(portfolio_fsas - shapefile_fsas)
        if missing:
            log.warning(
                "%d portfolio FSA(s) have no matching polygon in this boundary "
                "vintage -- excluded from the output, needs resolving before "
                "FSA-level spatial aggregation: %s",
                len(missing), missing,
            )
        else:
            log.info("All portfolio FSAs matched to a boundary polygon.")

    log.info("Writing %s FSA boundaries to %s", PROVINCE_NAME, out_path)
    subset.to_file(out_path, driver="GPKG", layer=f"{REGION_NAME}_fsa")

    return out_path


if __name__ == "__main__":
    extract_region_fsa_boundaries()
