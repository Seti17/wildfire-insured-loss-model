# Data Dictionary

Dataset-level documentation: grain, join keys, coverage, units, and
missing-value semantics for every raw and processed dataset in this
project. For a flat per-field lookup table, see
[`../data/data_dictionary.csv`](../data/data_dictionary.csv) -- that file
and this one describe the same data from two angles (field-by-field vs.
dataset-level) and should be kept in sync when either changes.

All processed datasets below are produced by the numbered scripts in
[`../src/`](../src/); the script name is given so the exact transformation
logic is one click away.

---

## Raw inputs

### `data/raw/provided_portfolio_data.csv`
- **Grain:** one row per FSA (current-state snapshot, not time-varying)
- **Key:** `FSA`
- **Rows:** 159
- **Columns:** `FSA`, `Number of Exposure` (count), `$ Average Exposure` (CAD)
- **Missing values:** none observed
- **Source:** provided case study materials, split from `Sample Wildfire data.xlsx` ("Current Exposure" sheet)

### `data/raw/provided_claims_data.csv`
- **Grain:** one row per (FSA, historical loss event)
- **Key:** `FSA` + `Loss Dates` (composite; `Loss Dates` is a free-text
  range like `"May 3 - May 18, 2016"`, not yet split into machine-usable
  start/end dates in this raw file -- see
  `data/processed/features/alberta_claims_features.csv` below)
- **Rows:** 305
- **Columns:** `FSA`, `Loss Dates`, `Number of Exposure`, `$ Average Exposure`, `Loss Frequency`, `Total $ Loss`
- **Missing values:** none observed
- **Source:** provided case study materials, split from `Sample Wildfire data.xlsx` ("Historical claims" sheet)

### `data/raw/climate_data/_cache/{var}_{year}.nc`
- **Grain:** one file per (climate variable, year); within each file, one
  value per (lat, lon, day)
- **Key:** filename encodes variable + year; internally indexed by (lat, lon, time)
- **Coverage:** `tas`, `hurs`, `pr`, `sfcWind` x 2015-2025 (44 files), Alberta bbox only (pre-sliced before download)
- **CRS:** implicit WGS84 degrees, but **longitude in the source's native 0-360 convention**, not -180/180
- **Missing values:** none expected within the fetched bbox/period
- **Source:** NASA NEX-GDDP-CMIP6, model EC-Earth3, scenario ssp126, variant r1i1p1f1, via public S3 (`s3://nex-gddp-cmip6`)
- **Produced by:** `src/01_fetch_climate_data.py`

### `data/raw/fuel_data/FBP_Canada_30m_3978_22052024_forRelease.tif`
- **Grain:** per 30m pixel, national coverage
- **Key:** (row, col) pixel index / (x, y) coordinate in EPSG:3978
- **Dimensions:** 178,399 x 119,099 pixels (~21.2 billion cells)
- **CRS:** EPSG:3978 (NAD83 / Canada Atlas Lambert)
- **Values:** integer FBP (Fire Behaviour Prediction) fuel type codes; nodata = -9999
- **Code legend source:** **none found.** No colormap, raster attribute
  table (RAT), or sidecar legend file ships with the provided `.tif` (only
  the single raster file is present in `data/raw/fuel_data/`, confirmed by
  directory listing; `rasterio` reports `NULL color table`). The observed
  codes within Alberta (1, 2, 3, 4, 5, 7, 11, 13, 31, 101, 102, 105, 415,
  625, 650, 675) do not match a simple guessed low-integer FBP numbering
  (C-1..C-7, D-1/D-2, M-1..M-4, S-1..S-3, O-1a/O-1b) cleanly -- some
  plausibly do, others (101, 102, 105, 415, 625, 650, 675) look like a
  different convention, likely non-fuel/water/other special classes.
  **Open item:** source the official NRCan/CWFIS numeric legend for this
  specific product before interpreting `dominant_fuel_code` as a labeled
  fuel class in the report -- until then, treat codes as opaque categorical
  IDs only.
- **Source:** National Forest Information System (NRCan/Canadian Forest
  Service) -- see [`../references/external_sources.md`](../references/external_sources.md)
  for the download URL and licensing. Not included in this repository
  (exceeds GitHub's 100 MB file limit; see `.gitignore`).

### `data/raw/boundary_data/canada_fsa/lfsa000b21a_e.shp`
- **Grain:** one row per FSA polygon, national coverage
- **Key:** `CFSAUID`
- **Rows:** 1,643 (all of Canada)
- **Columns:** `CFSAUID`, `DGUID`, `PRUID`, `PRNAME`, `LANDAREA`, `geometry`
- **CRS:** EPSG:3347 (NAD83 / Statistics Canada Lambert) -- projected, conformal (not equal-area)
- **Vintage:** 2021 StatCan digital boundary file
- **Source:** Statistics Canada, 2021 Census digital boundary files -- see
  [`../references/external_sources.md`](../references/external_sources.md)
  for the download URL and licensing. Not included in this repository
  (exceeds GitHub's 100 MB file limit; see `.gitignore`).
- **Known coverage gap -- 5 portfolio FSAs have no polygon here, and they
  are NOT all the same kind of gap** (re-verified with case-insensitive/
  whitespace-normalized matching -- genuinely absent, not a lookup bug):
  - **`T0N`, `T0T`, `T0V`** -- correctly and expectedly absent. These are
    non-residential internal Canada Post routing codes for the Edmonton
    Mail Processing Plant/Distribution Centre: zero residential addresses,
    zero census respondents, no geography to map. Nothing to fix here.
  - **`T3T`, `T4K`** -- **genuinely populated, real areas** that should
    have boundary geometry but don't in this specific StatCan cartographic
    product. `T3T` is Tsuut'ina Nation territory bordering southwestern
    Calgary (populated, real tax-filer records on record); `T4K` covers
    rural residential/agricultural delivery zones around Red Deer. Most
    likely explanation: StatCan's digital boundary file is constructed
    from census geography and doesn't perfectly mirror Canada Post's full
    FSA list, especially for small or more recently established FSAs --
    not a lag/vintage issue in the sense of "doesn't exist yet," but a
    real gap in this cartographic product specifically. **This is an
    open item worth fixing** (source a supplementary boundary for these
    two, e.g. a newer StatCan release or a Canada Post FSA polygon
    product) before treating Alberta FSA coverage as complete, since one
    of these two (`T3T`) has real claims data attached to it (see below)
    that currently can't be spatially joined to climate/fuel features at all.

---

## Processed datasets

### `data/processed/climate/{region}_{model}_{scenario}_{variant}_{years}.nc`
- **Grain:** one value per (lat, lon, day) per variable
- **Key:** (lat, lon, time)
- **Variables:** `tas` (K), `hurs` (%), `pr` (kg m-2 s-1), `sfcWind` (m s-1)
- **Coverage:** Alberta bbox (49-60N, -120.05 to -109.95W). Two year ranges
  exist, produced by the same parametrized fetch function: **historical**
  (`{years}` = `2015_2025`, 2015-01-01 to 2025-12-31, 44 lat x 40 lon x
  4018 days) and **future** (`{years}` = `2045_2050`, the SSP1-2.6
  scenario horizon used for the illustrative future-loss projection in
  the modelling notebook, same scenario/variant, 6-year span).
- **CRS:** WGS84 degrees, 0-360 longitude (native to source)
- **Missing values:** none expected
- **Produced by:** `src/01_fetch_climate_data.py` (`fetch_climate_data(years=...)`, defaults to the historical range)

### `data/processed/climate/{region}_fwi_{years}.nc`
- **Grain:** one value per (lat, lon, day) per FWI component
- **Key:** (lat, lon, time)
- **Variables:** `DC`, `DMC`, `FFMC`, `ISI`, `BUI`, `FWI` (all unitless indices)
- **Coverage:** same two `{years}` variants as the climate file above --
  `2015_2025` (historical) and `2045_2050` (future SSP1-2.6 projection
  input), computed from the corresponding climate file.
- **Method:** `xclim.indices.fire.cffwis_indices`, `season_method="WF93"`, `overwintering=False`
- **Missing values:** NaN outside the WF93-estimated fire season (~61%
  of cells over a full calendar year at this latitude -- 100% NaN Dec-Mar,
  <1% NaN in August, verified month-by-month). This is expected behavior, not missing data.
  The future file's NaN fraction (~53%) was checked and found comparable
  to the historical file's (~55.5%), so the future/historical comparison
  in the modelling notebook isn't distorted by a coverage difference.
- **Produced by:** `src/02_compute_fwi.py`

### `data/processed/boundaries/{region}_fsa_boundaries.gpkg`
- **Grain:** one row per FSA polygon, Alberta only
- **Key:** `CFSAUID`
- **Rows:** 154 (of 159 in the portfolio data -- see coverage gap below)
- **CRS:** EPSG:3347 (unchanged from source)
- **Coverage gap:** 5 portfolio FSAs (`T0N`, `T0T`, `T0V`, `T3T`, `T4K`)
  have no matching polygon anywhere in the national boundary file --
  see the detailed breakdown under the raw shapefile entry above (3 are
  legitimately non-residential and correctly absent; 2 -- `T3T`, `T4K` --
  are real populated areas missing from this specific StatCan product,
  an open item worth fixing). **Any FSA-level table below built from this
  file inherits this 5-FSA gap** -- those FSAs are absent, not zero/null.
- **Produced by:** `src/03_extract_fsa_boundaries.py`

### `data/processed/fuel/{region}_fsa_fuel_summary.csv`
- **Grain:** one row per FSA
- **Key:** `CFSAUID`
- **Rows:** 154
- **Columns:**
  - `dominant_fuel_code` -- raw numeric FBP code with the most pixels in the FSA (mode). **Unlabeled** -- see the legend caveat above.
  - `dominant_fuel_pct` -- fraction of the FSA's valid pixels in `dominant_fuel_code` (mean 0.69, min 0.21 across Alberta -- most FSAs fairly homogeneous but not uniformly so)
  - `n_valid_pixels` -- count of non-nodata 30m pixels in the FSA (0 FSAs had zero valid pixels -- full coverage confirmed)
  - `n_fuel_classes_present` -- count of distinct codes present in the FSA
- **Method:** categorical zonal statistics (`rasterstats.zonal_stats`), FSA polygons reprojected to the raster's EPSG:3978 (not the raster reprojected -- far too large)
- **Missing values:** none (0/154 FSAs had zero valid pixels)
- **Produced by:** `src/04_process_fuel_raster.py`

### `data/processed/climate/{region}_fsa_fwi_daily.csv` (historical) and `{region}_fsa_fwi_daily_2045_2050.csv` (future)
- **Grain:** one row per (FSA, date)
- **Key:** `CFSAUID` + `date`
- **Rows:** historical file: 618,772 (154 FSAs x 4018 days, full grid -- no
  missing FSA/date combinations). Future file: 337,414 (154 FSAs x 2,191
  days, 2045-2050).
- **Columns:** `CFSAUID`, `date`, `DC`, `DMC`, `FFMC`, `ISI`, `BUI`, `FWI` (identical schema in both files)
- **Note:** the future file's name does not follow the `{years}` template
  used elsewhere in this section -- it is produced by calling
  `aggregate_climate_to_fsa(fwi_path=..., out_path=...)` from the same
  script with explicit paths pointed at the future FWI NetCDF, not by a
  separate script.
- **Method:** area-weighted average of intersecting climate grid cells per
  FSA per day. Each 0.25-degree grid cell is a polygon; intersected with
  each FSA polygon; weighted by fraction of the FSA's area covered.
  **CRS used for the area/weight calculation: Canada Albers Equal Area
  Conic** (`+proj=aea +lat_1=50 +lat_2=70 +lat_0=40 +lon_0=-96
  +datum=NAD83 +units=m +no_defs`) -- deliberately not EPSG:3347 (the FSA
  file's native CRS), since EPSG:3347 is conformal, not equal-area, and
  using it for area weighting introduces a small but real bias (verified:
  switching from EPSG:3347 to the Albers CRS changed weighted FWI values
  by up to ~2.5% relative, mean ~0.03-1% across the 6 variables).
- **Missing values:** historical file 55.5% NaN, future file ~53.1% NaN
  (checked to be comparable, not a coverage artifact), both inherited from
  the fire-season mask in the source grid. NaN handling is weight-mass-aware:
  an FSA/day is NaN only if **all** intersecting grid cells are NaN that
  day, not just some -- so season-transition days can show a partial
  (non-NaN) value blended from cells already in/out of season. This is
  intentional, not a simplification to work around later.
- **Coverage check:** all 154 FSAs have >=95% of their area covered by the
  climate grid (logged and verified at run time -- would warn per-FSA
  otherwise)
- **Produced by:** `src/05_aggregate_climate_to_fsa.py`

---

## Feature tables (this stage)

### `data/processed/features/{region}_fsa_static_features.csv`
- **Grain:** one row per FSA (time-invariant / current-snapshot features only)
- **Key:** `CFSAUID`
- **Columns:** fuel summary columns (`dominant_fuel_code`, `dominant_fuel_pct`, `n_valid_pixels`, `n_fuel_classes_present`) + portfolio columns (`Number of Exposure`, `$ Average Exposure`)
- **Coverage:** left-joined from the boundaries-derived fuel table (154
  FSAs) onto the 159-FSA portfolio list -- the 5 FSAs missing boundary
  geometry (see above) get NaN fuel columns, not dropped, so they remain
  visible as a known gap rather than silently vanishing from the exposure base.
- **Produced by:** `src/06_build_static_fsa_features.py`

### `data/processed/features/{region}_claims_features.csv`
- **Grain:** one row per historical claim/event (same grain as `provided_claims_data.csv`)
- **Key:** `FSA` + parsed `event_start` + `event_end`
- **Columns:** all `provided_claims_data.csv` columns, plus:
  - `event_start`, `event_end` -- parsed from the free-text `Loss Dates` field
  - `climate_days_available`, `window_coverage_fraction` -- how many days
    of the event window had non-NaN FSA-level FWI data, and what fraction
    of the window that represents. **Check this before trusting any
    max/mean feature below for a given row** -- a claim whose window falls
    mostly outside the fire season (e.g. a winter event) will have most
    FWI features derived from very few valid days.
  - `fwi_mean`, `fwi_max`, `fwi_p95`, `days_fwi_above_30`, `ffmc_max`, `isi_max`, `bui_mean`, `dc_max`, `dmc_max` -- computed only over the valid (non-NaN) days within the event window
  - static FSA features (fuel + portfolio exposure), joined from `{region}_fsa_static_features.csv`
- **Missing values:** event-window FWI features are NaN when
  `climate_days_available == 0` (event window entirely outside the fire
  season or outside the fetched climate period) -- **not** silently
  computed from zero days or dropped
- **Verified finding -- 73 of 305 claim rows (24%) have zero valid
  climate days, for two different reasons:**
  - **72 rows, all from the "May 3 - May 18, 2016" event:** genuinely
    zero FWI signal because the fire season hadn't started yet in that
    FSA's climate grid cell(s) by May 18. Spot-checked `T2A` (Calgary
    core, 19 km^2) vs. `T0A` (rural, 38,165 km^2) for the same window: T0A
    already had valid FWI from May 5 onward, T2A was NaN through the
    entire window (and through all of April too). This is a genuine
    latitude/timing effect, made worse for small urban FSAs since they
    depend on very few (sometimes effectively one) grid cells, so a late
    season start there is all-or-nothing rather than averaged out across
    many cells. **Modeling implication:** ~24% of the May 2016 event's
    claims have no FWI-based predictor available under the current
    WF93-based approach -- either those losses had a non-fire-weather
    cause, or WF93's season-start criterion is too conservative for this
    use case, or the claim date itself is imprecise. Resolution: these 73
    rows were excluded from the modelling set (not imputed) -- see
    `reports/wildfire_loss_report.md` §4/§6/§7 for the quantified impact
    (1.1% of total loss) and the resulting 232-row modelling set.
  - **1 row, from the "July 22 - August 17, 2024" event, FSA `T3T`:** a
    different cause entirely -- `T3T` (Tsuut'ina Nation territory) has no
    boundary polygon at all (see the real, unresolved boundary-file gap
    documented above), so it was never in the daily FSA FWI table to
    begin with. This is a coverage gap, not a seasonal-timing effect.
- **Produced by:** `src/07_build_claims_feature_table.py`
