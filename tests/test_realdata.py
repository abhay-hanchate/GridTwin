import json

import pandas as pd
import pytest

from engine import config

pytestmark = pytest.mark.realdata
V2 = config.PROCESSED_DIR / "v2"


@pytest.mark.parametrize("district", config.DISTRICTS)
def test_district_files_and_quality(district):
    q = json.loads((V2 / f"quality_{district}.json").read_text())
    assert q["meters"] >= 25 and q["readings"] > 3_000_000
    assert 0 <= q["outage_share"] < 0.35 and q["max_voltage_v"] > 250
    loads = pd.read_parquet(V2 / f"load_kw_{district}.parquet")
    assert loads.index.freq is not None or len(loads) > 50_000
    assert loads.index.min().year == 2019 and loads.index.max().year >= 2021


def test_both_districts_have_voltage_above_the_nominal():
    for d in config.DISTRICTS:
        v = pd.read_parquet(V2 / f"upstream_vm_pu_{d}.parquet")["upstream_vm_pu"]
        assert v.median() > 1.0
