"""Tests for the value-range sanity checks applied to climate inputs before
FWI computation (02_compute_fwi.py) -- these catch a variable secretly
being in the wrong units even when its metadata label claims otherwise."""

import numpy as np

from src.common import validate_fwi_climate_inputs


def test_validate_fwi_climate_inputs_accepts_plausible_values():
    tas = np.array([260.0, 280.0, 300.0])  # Kelvin
    hurs = np.array([20.0, 55.0, 90.0])  # percent
    pr = np.array([0.0, 2.5, 10.0])
    sfcwind = np.array([0.5, 3.0, 8.0])

    assert validate_fwi_climate_inputs(tas, hurs, pr, sfcwind) == []


def test_validate_fwi_climate_inputs_flags_celsius_mistaken_for_kelvin():
    tas_celsius = np.array([-10.0, 5.0, 20.0])  # plausible Celsius, implausible Kelvin
    hurs = np.array([20.0, 55.0, 90.0])
    pr = np.array([0.0, 2.5, 10.0])
    sfcwind = np.array([0.5, 3.0, 8.0])

    problems = validate_fwi_climate_inputs(tas_celsius, hurs, pr, sfcwind)

    assert any("tas" in p for p in problems)
