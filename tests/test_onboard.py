import numpy as np
import pandas as pd
import pytest

from engine.onboard import OnboardingError, load_feeder
from engine.solver import DaySolver
from engine.types import DayScenarioBatch

FEEDER = "node_id,parent_id,length_m,conductor\nn1,DT,40,rabbit\nn2,n1,60,rabbit\nn3,n2,50,weasel\nn4,n1,45,rabbit\n"
HOMES = "home_id,node_id,phase,kwp\nh1,n2,A,3\nh2,n3,B,3\nh3,n3,C,0\nh4,n4,A,5\n"
TRAFO = "kva,uk_percent\n100,4\n"


def _folder(tmp_path, feeder=FEEDER, homes=HOMES, trafo=TRAFO, meters=None):
    (tmp_path / "feeder.csv").write_text(feeder)
    (tmp_path / "homes.csv").write_text(homes)
    (tmp_path / "transformer.csv").write_text(trafo)
    if meters:
        (tmp_path / "meters.csv").write_text(meters)
    return tmp_path


def _problems(tmp_path, **kw):
    with pytest.raises(OnboardingError) as err:
        load_feeder(_folder(tmp_path, **kw))
    return "\n".join(err.value.problems)


def test_a_valid_feeder_builds_a_radial_network_that_solves(tmp_path):
    net = load_feeder(_folder(tmp_path))
    assert net.is_radial() and net.n_homes == 4 and net.house_kwp.sum() == 11 and net.trafo.sn_va == 100e3
    t = pd.date_range("2025-05-15", periods=4, freq="15min")
    scn = DayScenarioBatch(t, np.full((1, 4, 4), 0.5), np.full((1, 4), 0.6), np.full((1, 4), 1.02))
    res = DaySolver(net, asymmetric=True).solve(scn)
    assert res.converged.all() and 0.95 < float(np.nanmax(res.u_pu)) < 1.15


def test_missing_columns_unknown_conductor_and_bad_numbers_are_line_numbered(tmp_path):
    p = _problems(tmp_path, feeder=FEEDER.replace("n3,n2,50,weasel", "n3,n2,-5,copper"))
    assert "feeder.csv line 4: unknown conductor 'copper'" in p and "feeder.csv line 4: length_m must be positive" in p
    p = _problems(tmp_path, homes="home_id,node_id,kwp\nh1,n2,3\n")
    assert "homes.csv line 1: missing column(s): phase" in p


def test_bad_phase_negative_kwp_and_unknown_node(tmp_path):
    p = _problems(tmp_path, homes=HOMES.replace("h2,n3,B,3", "h2,n9,D,-1"))
    assert "homes.csv line 3: node 'n9' is not in feeder.csv" in p
    assert "homes.csv line 3: phase must be A, B or C, got 'D'" in p and "kwp must be at least 0" in p


def test_loops_and_islands_are_found(tmp_path):
    loop = FEEDER + "n5,n7,10,rabbit\nn6,n5,10,rabbit\nn7,n6,10,rabbit\n"          # n5 -> n7 -> n6 -> n5
    assert "loop" in _problems(tmp_path, feeder=loop)
    island = FEEDER + "n8,n9,10,rabbit\nn9,n8,10,rabbit\n"                          # two nodes pointing at each other
    assert "not connected to the transformer: n8, n9" in _problems(tmp_path, feeder=island)


def test_meter_file_is_checked_when_present(tmp_path):
    p = _problems(tmp_path, meters="timestamp,home_id,kwh,volts\n2025-05-15 00:00,h1,0.2,231\nyesterday,h1,-1,231\n")
    assert "meters.csv line 3: kwh must be at least 0" in p and "meters.csv line 3: timestamp is not a date" in p
