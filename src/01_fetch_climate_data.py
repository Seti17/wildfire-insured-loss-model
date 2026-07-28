"""
Fetch NEX-GDDP-CMIP6 climate data for a bounding box and merge into a
single daily dataset. Region/bbox comes from common.REGIONS[REGION_NAME].

Run:
    python src/01_fetch_climate_data.py

Output:
    data/processed/climate/{REGION_NAME}_{MODEL}_{SCENARIO}_{VARIANT}_{years}.nc
    Feeds into 02_compute_fwi.py.

Notes:
- Longitude is converted from common.py's standard -180/180 to this
  dataset's native 0-360 convention.
- Fetches run concurrently (thread pool, I/O-bound) with per-file local
  caching, so an interrupted run can resume without re-fetching.
"""

import concurrent.futures
import logging
from pathlib import Path

import h5py
import s3fs
import xarray as xr

from common import PROCESSED_DIR, RAW_DIR, REGION, REGION_NAME

# HDF5 logs a benign diagnostic when probing a not-yet-created output path
h5py._errors.silence_errors()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MODEL = "EC-Earth3"
SCENARIO = "ssp126"
VARIANT = "r1i1p1f1"
GRID_LABEL = "gr"  # confirmed against NASA's THREDDS catalog listing for this model/scenario

# Required FWI inputs (see 02_compute_fwi.py); tasmax/tasmin not needed
VARIABLES = ["tas", "hurs", "pr", "sfcWind"]
YEARS = range(2015, 2026)

LAT_MIN, LAT_MAX = REGION["lat_min"], REGION["lat_max"]
LON_MIN_360, LON_MAX_360 = REGION["lon_min"] % 360, REGION["lon_max"] % 360  # 0-360 convention

BUCKET = "nex-gddp-cmip6"
RAW_CLIMATE_DIR = RAW_DIR / "climate_data"
CACHE_DIR = RAW_CLIMATE_DIR / "_cache"
PROCESSED_CLIMATE_DIR = PROCESSED_DIR / "climate"
RAW_CLIMATE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_CLIMATE_DIR.mkdir(parents=True, exist_ok=True)

MAX_WORKERS = 8

YEAR_SPAN = f"{YEARS.start}_{YEARS.stop - 1}"
MERGED_CLIMATE_PATH = PROCESSED_CLIMATE_DIR / f"{REGION_NAME}_{MODEL}_{SCENARIO}_{VARIANT}_{YEAR_SPAN}.nc"


def s3_key(var: str, year: int) -> str:
    return (
        f"{BUCKET}/NEX-GDDP-CMIP6/{MODEL}/{SCENARIO}/{VARIANT}/{var}/"
        f"{var}_day_{MODEL}_{SCENARIO}_{VARIANT}_{GRID_LABEL}_{year}.nc"
    )


def cache_path(var: str, year: int) -> Path:
    return CACHE_DIR / f"{var}_{year}.nc"


def fetch_one(var: str, year: int) -> tuple[str, int, Path]:
    out_file = cache_path(var, year)
    if out_file.exists():
        log.info("Cache hit, skipping fetch: %s", out_file.name)
        return var, year, out_file

    fs = s3fs.S3FileSystem(  # own instance per thread
        anon=True,
        default_cache_type="readahead",
        default_block_size=16 * 1024 * 1024,
    )
    key = s3_key(var, year)
    if not fs.exists(key):
        raise FileNotFoundError(
            f"Not found on S3: {key} -- check variable/grid-label spelling "
            f"for this model/variant before assuming the whole run is broken."
        )

    log.info("Fetching %s ...", key)
    with fs.open(key, "rb") as f:
        ds = xr.open_dataset(f, engine="h5netcdf")

        lat_ascending = bool(ds.lat[0] < ds.lat[-1])
        lat_slice = slice(LAT_MIN, LAT_MAX) if lat_ascending else slice(LAT_MAX, LAT_MIN)
        sub = ds.sel(lat=lat_slice, lon=slice(LON_MIN_360, LON_MAX_360))

        if sub.sizes.get("lat", 0) == 0 or sub.sizes.get("lon", 0) == 0:
            raise ValueError(
                f"Empty spatial subset for {var} {year} -- check lat/lon slice "
                f"direction and the 0-360 longitude conversion."
            )

        sub = sub.load()

    sub.to_netcdf(out_file)
    log.info(
        "Cached %s -> lat=%d, lon=%d, time=%d",
        out_file.name, sub.sizes["lat"], sub.sizes["lon"], sub.sizes["time"],
    )
    return var, year, out_file


def fetch_climate_data(years=YEARS, out_path: Path = None) -> Path:
    """Fetch all variable-year combos (parallel, cached), merge, and write
    the combined climate subset. `years` defaults to the module-level
    historical range; pass a different range (e.g. a future decade for
    climate-scenario projection) to reuse this same fetch logic without
    duplicating it -- out_path defaults to a filename derived from `years`
    so a future fetch never collides with the historical output."""
    if out_path is None:
        year_span = f"{years.start}_{years.stop - 1}"
        out_path = PROCESSED_CLIMATE_DIR / f"{REGION_NAME}_{MODEL}_{SCENARIO}_{VARIANT}_{year_span}.nc"

    tasks = [(var, year) for var in VARIABLES for year in years]
    log.info(
        "Fetching %d variable-year combinations with %d parallel workers",
        len(tasks), MAX_WORKERS,
    )

    cached = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(fetch_one, var, year): (var, year) for var, year in tasks}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            var, year = futures[fut]
            _, _, path = fut.result()  # let exceptions propagate -- fail fast and loud
            cached[(var, year)] = path
            done += 1
            log.info("Progress: %d/%d combinations fetched", done, len(tasks))

    log.info("All variable-year combinations fetched. Merging...")

    data_vars = {}
    for var in VARIABLES:
        yearly = [xr.open_dataset(cached[(var, year)]) for year in years]
        merged = xr.concat(yearly, dim="time")
        data_vars[var] = merged[var]

    ds_all = xr.Dataset(data_vars)

    log.info("Writing merged %s subset to %s", REGION_NAME, out_path)
    ds_all.to_netcdf(out_path)

    log.info("Done. Shape summary:")
    log.info(ds_all)

    return out_path


if __name__ == "__main__":
    fetch_climate_data()
