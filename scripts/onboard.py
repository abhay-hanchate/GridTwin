"""Validate a utility feeder folder and run a first check on it, or purge uploaded files.

Usage:  python -m scripts.onboard data/onboarding/<feeder> [--rule up_2005]
        python -m scripts.onboard data/onboarding/<feeder> --purge
Files stay on local disk (data/onboarding is gitignored), are never logged, and --purge deletes them.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from engine.onboard import OnboardingError, load_feeder


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--purge", action="store_true", help="delete the folder and everything in it")
    a = ap.parse_args()
    if a.purge:
        shutil.rmtree(a.folder, ignore_errors=True)
        print(f"deleted {a.folder}")
        return 0
    try:
        net = load_feeder(a.folder)
    except OnboardingError as exc:
        print(exc)
        return 1
    print(f"ok: {net.n_homes} homes, {len(net.lv_nodes) - 1} nodes, {net.n_lines} segments, "
          f"{net.trafo.sn_va / 1000:g} kVA, {net.house_kwp.sum():g} kWp of solar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
