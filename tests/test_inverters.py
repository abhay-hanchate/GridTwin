"""IEEE 1547 curves. Their effect on a street is tested in the v2 engine (tests/test_solver.py)."""
import numpy as np
import pytest

from engine.inverters import VoltVarCurve, VoltWattCurve


def test_volt_var_curve_matches_ieee_cat_b_points():
    c = VoltVarCurve()
    assert c.q_fraction(1.00) == 0.0 and c.q_fraction(1.02) == 0.0
    assert c.q_fraction(0.92) == pytest.approx(0.44)
    assert c.q_fraction(1.08) == pytest.approx(-0.44)
    assert c.q_fraction(1.05) == pytest.approx(-0.22)
    assert c.q_fraction(1.20) == pytest.approx(-0.44)      # flat beyond the last point
    assert np.allclose(c.q_fraction(np.array([0.98, 1.08])), [0.0, -0.44])


def test_volt_watt_is_a_limit_on_rated_power():
    c = VoltWattCurve()
    assert c.p_fraction(1.05) == 1.0
    assert c.p_fraction(1.08) == pytest.approx(0.6)
    assert c.p_fraction(1.12) == pytest.approx(0.2)
