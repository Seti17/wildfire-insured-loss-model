"""
Aggregate the national FBP fuel type raster to FSA level via zonal
statistics.

Run:
    python src/04_process_fuel_raster.py

Output:
    data/processed/fuel/{REGION_NAME}_fsa_fuel_summary.csv

Notes:
- No legend ships with the raster; dominant_fuel_code is kept as a raw
  numeric ID, not translated to a fuel class. See docs/data_dictionary.md.
"""

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd
import rasterio
from rasterstats import zonal_stats

from common import PROCESSED_DIR, RAW_DIR, REGION_NAME

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

FUEL_RASTER_PATH = RAW_DIR / "fuel_data" / "FBP_Canada_30m_3978_22052024_forRelease.tif"
FSA_BOUNDARIES_PATH = PROCESSED_DIR / "boundaries" / f"{REGION_NAME}_fsa_boundaries.gpkg"
PROCESSED_FUEL_DIR = PROCESSED_DIR / "fuel"
PROCESSED_FUEL_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH = PROCESSED_FUEL_DIR / f"{REGION_NAME}_fsa_fuel_summary.csv"

NODATA_VALUE = -9999


def process_fuel_raster(out_path: Path = OUT_PATH) -> Path:
    log.info("Loading FSA boundaries from %s", FSA_BOUNDARIES_PATH)
    fsa = gpd.read_file(FSA_BOUNDARIES_PATH)
    log.info("Loaded %d FSA polygons (CRS: %s)", len(fsa), fsa.crs)

    with rasterio.open(FUEL_RASTER_PATH) as src:
        raster_crs = src.crs
        log.info("Fuel raster CRS: %s, nodata: %s", raster_crs, src.nodata)

        if fsa.crs != raster_crs:
            log.info("Reprojecting FSA polygons from %s to %s", fsa.crs, raster_crs)
            fsa_for_raster = fsa.to_crs(raster_crs)
        else:
            fsa_for_raster = fsa
        assert fsa_for_raster.crs == raster_crs

        log.info("Running categorical zonal stats over %d polygons...", len(fsa_for_raster))
        stats = zonal_stats(
            fsa_for_raster,
            FUEL_RASTER_PATH,
            categorical=True,
            nodata=NODATA_VALUE,
            geojson_out=False,
        )

    rows = []
    for cfsauid, stat in zip(fsa_for_raster["CFSAUID"], stats):
        total_valid = sum(stat.values())
        if total_valid == 0:
            log.warning("FSA %s has zero valid fuel pixels", cfsauid)
            rows.append({
                "CFSAUID": cfsauid,
                "dominant_fuel_code": None,
                "dominant_fuel_pct": None,
                "n_valid_pixels": 0,
                "n_fuel_classes_present": 0,
            })
            continue

        dominant_code, dominant_count = max(stat.items(), key=lambda kv: kv[1])
        rows.append({
            "CFSAUID": cfsauid,
            "dominant_fuel_code": int(dominant_code),
            "dominant_fuel_pct": dominant_count / total_valid,
            "n_valid_pixels": total_valid,
            "n_fuel_classes_present": len(stat),
        })

    result = pd.DataFrame(rows)
    log.info(
        "Fuel summary: %d FSAs, %d with zero valid pixels",
        len(result), (result["n_valid_pixels"] == 0).sum(),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False)
    log.info("Wrote FSA fuel summary to %s", out_path)

    return out_path


if __name__ == "__main__":
    process_fuel_raster()
