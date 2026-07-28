"""Tests for the final sanity checks on the claims feature table
(07_build_claims_feature_table.py) before it's used for modelling."""

import pandas as pd

from src.common import validate_claims_feature_table

REQUIRED = ["FSA", "Loss Dates", "Total $ Loss"]


def test_validate_claims_feature_table_passes_on_clean_data():
    df = pd.DataFrame({
        "FSA": ["T1A", "T1B"],
        "Loss Dates": ["May 2016", "Jul 2024"],
        "Total $ Loss": [100.0, 200.0],
    })

    problems = validate_claims_feature_table(
        df, required_columns=REQUIRED, key_columns=["FSA", "Loss Dates"],
        non_negative_columns=["Total $ Loss"],
    )

    assert problems == []


def test_validate_claims_feature_table_flags_missing_column_duplicate_key_and_negative_value():
    df = pd.DataFrame({
        "FSA": ["T1A", "T1A"],  # duplicate (FSA, Loss Dates) pair below
        "Loss Dates": ["May 2016", "May 2016"],
        "Total $ Loss": [100.0, -50.0],  # negative value
        # "Loss Frequency" intentionally absent from the wider required list below
    })

    problems = validate_claims_feature_table(
        df,
        required_columns=REQUIRED + ["Loss Frequency"],
        key_columns=["FSA", "Loss Dates"],
        non_negative_columns=["Total $ Loss"],
    )

    assert any("missing required column" in p for p in problems)
    assert any("duplicate-key" in p for p in problems)
    assert any("negative value" in p for p in problems)
