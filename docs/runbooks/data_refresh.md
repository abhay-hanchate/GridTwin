# Data refresh

**When.** New CEEW files, a new district, or a fresh checkout (`data/processed/v2/` is not in git).

**Steps.**
1. `python scripts/download_data.py`: about 1 GB into `data/raw/` (never committed). An interrupted download stays
   a `*.part` file and is fetched again on the next run; archive timeouts are transient, so run it again.
2. `python scripts/build_data.py`: one line per district, then `legacy load_kw: 32 of 38 meters kept`.
3. Prove the Round 1 files did not move, because every Round 1 number depends on them: `git status data/processed`
   must show no change to `load_kw`, `upstream_vm_pu`, `pv_kw_per_kwp` or `weather_hourly`. If it does, stop: the
   cleaning changed.
4. `python -m pytest -m realdata tests/test_realdata.py`: 3 passed.
5. Re-run what depends on the data: `python -m ml.demand_v2` (and `python -m engine.upstream` once task P2.5 is
   merged), then update `docs/generated/data_v2.md` from the new numbers.

**Who decides.** The data owner (Person B). A changed gate result is written down, never tuned away.
