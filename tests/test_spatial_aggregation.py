"""Tests for weighted_mean_matrix, the NaN-aware area-weighted-average
logic 05_aggregate_climate_to_fsa.py uses to aggregate the climate grid
onto FSA polygons -- an FSA/day should be NaN only if every grid cell it
draws from is NaN, not just some (see docs/data_dictionary.md's note on
this)."""

import numpy as np

from src.common import weighted_mean_matrix


def test_weighted_mean_matrix_excludes_missing_cells_from_numerator_and_weight_total():
    # 3 grid cells x 1 day. FSA A draws on all three cells, one of which
    # (weight 5.0) is NaN for this day -- it must be dropped from *both*
    # the weighted sum and the weight total, not just skipped in the sum
    # (which would silently understate the result instead of renormalizing).
    values = np.array([[10.0], [np.nan], [30.0]])
    weights = np.array([[1.0, 5.0, 3.0]])

    result = weighted_mean_matrix(weights, values)

    # (1*10 + 3*30) / (1+3) = 100/4 = 25.0 -- NOT (1*10+3*30)/(1+5+3) = 100/9
    assert np.isclose(result[0, 0], 25.0)


def test_weighted_mean_matrix_returns_nan_only_when_every_source_is_missing():
    # FSA B only draws weight from the one non-missing cell -- it should
    # get that cell's exact value, not NaN, even though a *different* FSA
    # sharing the same values array is affected by the missing cell.
    values = np.array([[10.0], [np.nan], [30.0]])
    weights = np.array([[0.0, 0.0, 1.0]])

    result = weighted_mean_matrix(weights, values)

    assert np.isclose(result[0, 0], 30.0)

    # But if literally every cell an FSA draws from is missing, the result
    # must be NaN, not zero or a divide-by-zero artifact.
    all_missing = np.array([[np.nan], [np.nan]])
    weights_two_cells = np.array([[1.0, 1.0]])
    result_all_missing = weighted_mean_matrix(weights_two_cells, all_missing)
    assert np.isnan(result_all_missing[0, 0])
