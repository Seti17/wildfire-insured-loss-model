"""
Compute daily Fire Weather Index (FWI) components from the merged climate
subset produced by 01_fetch_climate_data.py.

Run:
    python src/02_compute_fwi.py

Output:
    data/processed/climate/{REGION_NAME}_fwi_{years}.nc -- daily DC, DMC,
    FFMC, ISI, BUI, FWI. NaN outside the WF93-estimated fire season.
"""

import logging
from pathlib import Path

import xarray as xr
from xclim.core.units import convert_units_to
from xclim.indices.fire import cffwis_indices  # xclim >=0.4x renamed this from fire_weather_indexes

from common import PROCESSED_DIR, REGION_NAME, validate_fwi_climate_inputs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Must match 01_fetch_climate_data.py's config for this run
MODEL = "EC-Earth3"
SCENARIO = "ssp126"
VARIANT = "r1i1p1f1"
YEAR_SPAN = "2015_2025"

PROCESSED_CLIMATE_DIR = PROCESSED_DIR / "climate"
IN_PATH = PROCESSED_CLIMATE_DIR / f"{REGION_NAME}_{MODEL}_{SCENARIO}_{VARIANT}_{YEAR_SPAN}.nc"
OUT_PATH = PROCESSED_CLIMATE_DIR / f"{REGION_NAME}_fwi_{YEAR_SPAN}.nc"


def compute_fwi(in_path: Path = IN_PATH, out_path: Path = OUT_PATH) -> Path:
    """Compute daily FWI components from a merged climate subset (as
    produced by 01_fetch_climate_data.py) and write them to out_path."""
    log.info("Loading merged climate subset from %s", in_path)
    ds = xr.open_dataset(in_path)

    # sanity-check units before handing off to xclim
    for var, expected in [
        ("tas", "K"),
        ("pr", "kg m-2 s-1"),
        ("sfcWind", "m s-1"),
        ("hurs", "%"),
    ]:
        units = ds[var].attrs.get("units", "")
        log.info("%s units: %s (expected roughly: %s)", var, units, expected)

    # the check above only confirms the *label* says the right units -- this
    # checks the actual *values* are in a plausible range, which would catch
    # e.g. Celsius silently mislabeled as Kelvin
    for problem in validate_fwi_climate_inputs(ds["tas"].values, ds["hurs"].values, ds["pr"].values, ds["sfcWind"].values):
        log.warning("Climate input sanity check failed: %s", problem)

    # xclim requires an explicit units attr on lat
    if "units" not in ds["lat"].attrs:
        ds["lat"].attrs["units"] = "degrees_north"

    # cffwis_indices needs pr in mm/day with the hydro pint context
    pr_mm_day = convert_units_to(ds["pr"], "mm/day", context="hydro")

    log.info("Running cffwis_indices...")
    out = cffwis_indices(
        tas=ds["tas"],
        pr=pr_mm_day,
        sfcWind=ds["sfcWind"],
        hurs=ds["hurs"],
        lat=ds["lat"],
        season_method="WF93",
        overwintering=False,
    )

    dc, dmc, ffmc, isi, bui, fwi = out  # xclim's fixed return order

    ds_out = xr.Dataset(
        {
            "DC": dc,
            "DMC": dmc,
            "FFMC": ffmc,
            "ISI": isi,
            "BUI": bui,
            "FWI": fwi,
        }
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    log.info("Writing FWI outputs to %s", out_path)
    ds_out.to_netcdf(out_path)

    log.info("Done. Quick summary of FWI field:")
    log.info(ds_out["FWI"])

    return out_path


if __name__ == "__main__":
    compute_fwi()
