"""Tests for the longitude-conversion utility in src/common.py, used by
05_aggregate_climate_to_fsa.py to build grid-cell polygons in EPSG:4326."""

from src.common import lon_360_to_180


def test_lon_360_to_180_converts_source_convention_to_standard():
    assert lon_360_to_180(0) == 0
    assert lon_360_to_180(180) == -180
    assert lon_360_to_180(200) == -160
    assert lon_360_to_180(359.75) == -0.25
