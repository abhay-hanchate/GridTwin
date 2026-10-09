"""Run the reliability backtest on the v2 data for one district and rule.

Usage: python -m scripts.run_reliability --district mathura --rule up_2005 --split 2021-01-01
"""
import argparse
import json
import warnings
from pathlib import Path

import pandas as pd

from engine import config
from engine.archetypes import build
from engine.reliability import backtest
from engine.rules import get_rule

warnings.filterwarnings("ignore")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--district", default="mathura", choices=config.DISTRICTS)
    ap.add_argument("--rule", default="up_2005")
    ap.add_argument("--archetype", default="benchmark_250")
    ap.add_argument("--split", default="2021-01-01")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--scenarios", type=int, default=40)
    a = ap.parse_args()
    base = config.PROCESSED_DIR / "v2"
    load = pd.read_parquet(base / f"load_kw_{a.district}.parquet")
    pv = pd.read_parquet(base / f"pv_kw_per_kwp_{a.district}.parquet")["pv_kw_per_kwp"]
    up = pd.read_parquet(base / f"upstream_vm_pu_{a.district}.parquet")["upstream_vm_pu"]
    result = backtest(build(a.archetype, phases="round_robin"), get_rule(a.rule), load, pv, up,
                      split=a.split, n_days=a.days, n_scenarios=a.scenarios)
    out = Path("data/results") / f"reliability_{a.district}_{a.rule}.json"
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ("days", "brier", "brier_climatology", "brier_skill")}, indent=2))


if __name__ == "__main__":
    main()
