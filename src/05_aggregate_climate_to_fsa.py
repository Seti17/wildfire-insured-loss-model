"""
Area-weighted spatial join of the daily FWI grid onto FSA polygons.

Run:
    python src/05_aggregate_climate_to_fsa.py

Output:
    data/processed/climate/{REGION_NAME}_fsa_fwi_daily.csv
    One row per (FSA, date), columns DC/DMC/FFMC/ISI/BUI/FWI.

Notes:
- Daily granularity (not pre-aggregated) so claims can later be matched
  to arbitrary event-date windows.
- True area-weighted overlay (grid cell polygons x FSA polygons), not
  nearest-cell -- needed since FSA sizes vary hugely relative to the
  0.25deg grid.
- Area/weights computed in AREA_CRS (Canada Albers Equal Area), not the
  FSA file's native EPSG:3347 (biases area).
- NaN-aware weighted mean: an FSA/day is NaN only if all intersecting
  cells are NaN, not just some.
"""

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from shapely.geometry import box

from common import FWI_COMPONENTS, PROCESSED_DIR, REGION_NAME, lon_360_to_180, weighted_mean_matrix

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

PROCESSED_CLIMATE_DIR = PROCESSED_DIR / "climate"
FWI_PATH = PROCESSED_CLIMATE_DIR / f"{REGION_NAME}_fwi_2015_2025.nc"
FSA_BOUNDARIES_PATH = PROCESSED_DIR / "boundaries" / f"{REGION_NAME}_fsa_boundaries.gpkg"
OUT_PATH = PROCESSED_CLIMATE_DIR / f"{REGION_NAME}_fsa_fwi_daily.csv"

FWI_VARIABLES = FWI_COMPONENTS

MIN_COVERAGE_WARNING_THRESHOLD = 0.95  # below this, flag partial climate-grid coverage

# Canada Albers Equal Area Conic -- for area/weight calculations only
AREA_CRS = (
    "+proj=aea +lat_1=50 +lat_2=70 "
    "+lat_0=40 +lon_0=-96 "
    "+datum=NAD83 +units=m +no_defs"
)


def build_grid_cell_polygons(ds: xr.Dataset) -> gpd.GeoDataFrame:
    """One polygon per FWI grid cell, centered on each (lat, lon) point with
    half-cell-width edges, in EPSG:4326 with standard -180/180 longitude."""
    lat_res = abs(float(ds.lat[1] - ds.lat[0]))
    lon_res = abs(float(ds.lon[1] - ds.lon[0]))

    cells = []
    for lat_idx, lat in enumerate(ds.lat.values):
        for lon_idx, lon in enumerate(ds.lon.values):
            lon_std = lon_360_to_180(float(lon))
            cell = box(
                lon_std - lon_res / 2, lat - lat_res / 2,
                lon_std + lon_res / 2, lat + lat_res / 2,
            )
            cells.append({"lat_idx": lat_idx, "lon_idx": lon_idx, "geometry": cell})

    return gpd.GeoDataFrame(cells, crs="EPSG:4326")


def build_fsa_weights(fsa: gpd.GeoDataFrame, grid_cells: gpd.GeoDataFrame) -> pd.DataFrame:
    """Area-weighted overlap of each FSA with each grid cell (long table:
    CFSAUID, lat_idx, lon_idx, weight). Area computed in AREA_CRS, not
    EPSG:4326 or the FSA file's native EPSG:3347 (both biased for area)."""
    grid_cells_proj = grid_cells.to_crs(AREA_CRS)

    # dissolve first so a multi-row FSA doesn't need += below to be correct
    fsa_area = fsa[["CFSAUID", "geometry"]].dissolve(by="CFSAUID").reset_index().to_crs(AREA_CRS)
    fsa_area["fsa_total_area"] = fsa_area.geometry.area

    overlay = gpd.overlay(fsa_area, grid_cells_proj, how="intersection")
    overlay["intersection_area"] = overlay.geometry.area
    overlay["weight"] = overlay["intersection_area"] / overlay["fsa_total_area"]

    coverage = overlay.groupby("CFSAUID")["weight"].sum()
    poor_coverage = coverage[coverage < MIN_COVERAGE_WARNING_THRESHOLD]
    if len(poor_coverage):
        log.warning("%d FSA(s) not fully covered by the climate grid: %s",
                     len(poor_coverage), {k: round(v, 3) for k, v in poor_coverage.items()})
    else:
        log.info("All FSAs have >=%.0f%% climate grid coverage.", MIN_COVERAGE_WARNING_THRESHOLD * 100)

    return overlay[["CFSAUID", "lat_idx", "lon_idx", "weight"]]


def aggregate_climate_to_fsa(fwi_path: Path = FWI_PATH, out_path: Path = OUT_PATH) -> Path:
    """`fwi_path` defaults to the historical FWI file; pass a different one
    (e.g. a future-horizon FWI file) to reuse this same spatial-join logic
    without duplicating it."""
    log.info("Loading FWI data from %s", fwi_path)
    ds = xr.open_dataset(fwi_path)

    log.info("Loading FSA boundaries from %s", FSA_BOUNDARIES_PATH)
    fsa = gpd.read_file(FSA_BOUNDARIES_PATH)
    log.info("FSA CRS: %s", fsa.crs)

    log.info("Building %d x %d grid cell polygons (EPSG:4326)...", ds.sizes["lat"], ds.sizes["lon"])
    grid_cells = build_grid_cell_polygons(ds)

    log.info("Computing area-weighted FSA <-> grid cell overlap...")
    weights = build_fsa_weights(fsa, grid_cells)

    fsa_ids = sorted(fsa["CFSAUID"].unique())
    fsa_idx = {f: i for i, f in enumerate(fsa_ids)}
    n_lat, n_lon = ds.sizes["lat"], ds.sizes["lon"]

    W = np.zeros((len(fsa_ids), n_lat * n_lon))
    for row in weights.itertuples():
        cell_flat_idx = row.lat_idx * n_lon + row.lon_idx
        W[fsa_idx[row.CFSAUID], cell_flat_idx] += row.weight

    log.info("Applying weights to %d days x %d variables...", ds.sizes["time"], len(FWI_VARIABLES))
    results = {"CFSAUID": np.repeat(fsa_ids, ds.sizes["time"]), "date": np.tile(ds.time.values, len(fsa_ids))}
    for var in FWI_VARIABLES:
        values = ds[var].transpose("lat", "lon", "time").values.reshape(n_lat * n_lon, ds.sizes["time"])
        fsa_values = weighted_mean_matrix(W, values)  # NaN-aware weighted mean, (n_fsa, time)
        results[var] = fsa_values.reshape(-1)

    result = pd.DataFrame(results)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out_path, index=False)
    log.info("Wrote %d rows (%d FSAs x %d days) to %s", len(result), len(fsa_ids), ds.sizes["time"], out_path)

    return out_path


if __name__ == "__main__":
    aggregate_climate_to_fsa()
