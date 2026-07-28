# External Sources

## Climate data
- **NEX-GDDP-CMIP6** (NASA Earth Exchange Global Daily Downscaled Projections, CMIP6)
  - Model: EC-Earth3, Scenario: SSP1-2.6, Variant: r1i1p1f1, Grid label: gr
  - Accessed via the public AWS S3 bucket `s3://nex-gddp-cmip6` (anonymous access)
  - Variables used: `tas`, `hurs`, `pr`, `sfcWind`, daily -- 2015-2025
    (historical) and 2045-2050 (SSP1-2.6 future scenario for the
    illustrative loss projection)
  - https://registry.opendata.aws/nex-gddp-cmip6/

## Fire Weather Index computation
- **xclim** (`xclim.indices.fire.cffwis_indices`) -- open-source Python library
  implementing the Canadian Forest Fire Weather Index (FWI) System
  - Season method: WF93 (Wotton & Flannigan, 1993) start/end-of-season estimation
  - https://xclim.readthedocs.io/

## Fuel data
- **FBP (Fire Behaviour Prediction) Canada fuel type raster**, 30m resolution,
  Lambert Conformal Conic (EPSG:3978) -- `data/raw/fuel_data/`. Not included
  in this repository (exceeds GitHub's 100 MB file limit; see `.gitignore`).
  - Source: National Forest Information System (Canadian Forest Service,
    Natural Resources Canada)
  - Download: https://ca.nfis.org/fss/fss?command=retrieveByName&fileName=FBP_Canada_30m_3978_22052024_forRelease.tif&fileNameSpace=fire_behaviour_prediction&format=png&promptToSave=true
  - Licensing: Government of Canada open data, typically distributed under
    the Open Government Licence -- Canada; verify current terms on NRCan's
    site before redistribution.

## Geographic boundaries
- **Canada FSA (Forward Sortation Area) boundary file**, 2021 vintage --
  `data/raw/boundary_data/canada_fsa.zip`. Not included in this repository
  (exceeds GitHub's 100 MB file limit; see `.gitignore`).
  - Source: Statistics Canada, 2021 Census digital boundary files --
    https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/index2021-eng.cfm?year=21
  - Direct download (FSA file, `lfsa000b21a_e.zip`): https://www12.statcan.gc.ca/census-recensement/alternative_alternatif.cfm?l=eng&dispext=zip&teng=lfsa000b21a_e.zip&k=%20%20%20158240&loc=//www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/files-fichiers/lfsa000b21a_e.zip
  - Licensing: Statistics Canada Open Licence; verify current terms on
    StatCan's site before redistribution.

## Provided data
- `data/raw/provided_portfolio_data.csv` -- current exposure by FSA (159 FSAs)
- `data/raw/provided_claims_data.csv` -- historical wildfire claims by FSA and
  event window
- Original combined file: `data/raw/Sample Wildfire data.xlsx`
