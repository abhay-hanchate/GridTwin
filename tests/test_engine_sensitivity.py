import pytest

from scripts.engine_sensitivity import run


@pytest.mark.slow
def test_sensitivity_report_has_every_case_and_passes_gate_g5():
    r = run("2019-05-15")
    assert len(r["zero_sequence"]) == 9 and set(r["phase_modes"]) == {"random", "round_robin", "all_a"}
    assert r["gate_g5_converged"] is True
    assert r["balanced"]["max_voltage_v"] < r["phase_modes"]["round_robin"]["max_voltage_v"] < r["phase_modes"]["all_a"]["max_voltage_v"]
    lo, hi = r["zero_sequence_peak_range_v"]
    assert 255 < lo <= hi < 300
