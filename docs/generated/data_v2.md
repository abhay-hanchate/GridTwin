# Data v2 and gate G4 (P2.7)

Run on 9 Oct 2026 with `python scripts/download_data.py && python scripts/build_data.py && python -m ml.demand_v2`.
Every number below is copied from `data/processed/v2/quality_<district>.json` (not committed; rebuilt by
`scripts/build_data.py`) and `ml/reports/demand_v2.json`.

## What the six CEEW files contain

| | Mathura | Bareilly |
|---|---|---|
| Meters | 38 | 46 |
| Readings (3-minute) | 7,898,794 | 13,495,635 |
| First and last reading | 2019-05-01 to 2021-02-20 | 2019-05-09 to 2021-10-31 |
| Outage share (voltage below 150 V) | 9.71% | 7.48% |
| Surge share (voltage above 300 V) | 0.04% | 0.09% |
| Highest recorded voltage | 654.7 V | 654.7 V |

**The Mathura 2021 file stops on 20 February 2021.** The plan assumed a full year, so the time hold-out below is
51 winter days, not a year.

Voltage at the meters, per year (outages and surges removed). The 253 V line is +10% of 230 V; 243.8 V is +6%.

| District, year | Meters | Median | Above +6% | Above +10% | Below -10% | Mean meter coverage |
|---|---|---|---|---|---|---|
| Mathura 2019 | 38 | 245.5 V | 54.9% | 27.2% | 6.1% | 79.1% |
| Mathura 2020 | 38 | 245.6 V | 54.8% | 28.3% | 5.8% | 53.7% |
| Mathura 2021 (Jan to 20 Feb) | 35 | 255.6 V | 83.5% | 60.2% | 0.2% | 55.8% |
| Bareilly 2019 | 46 | 247.4 V | 60.2% | 33.1% | 1.2% | 55.0% |
| Bareilly 2020 | 46 | 245.3 V | 53.9% | 28.5% | 1.8% | 81.0% |
| Bareilly 2021 | 38 | 241.9 V | 45.1% | 23.2% | 3.7% | 57.6% |

Both districts sit above 230 V most of the time and above the UP ±6% limit about half the time before any rooftop
solar is added.

**Legacy parity:** the Round 1 files in `data/processed/` (`load_kw`, `upstream_vm_pu`, `pv_kw_per_kwp`,
`weather_hourly`) were rebuilt from the new loaders and are identical in value to the committed ones
(32 of 38 Mathura meters kept, 63,552 steps), so no Round 1 number moves.

## Demand v2 and gate G4

Target: mean kW per home, 15 minutes. Baseline chosen on the training data: mean of lag-1-day and lag-7-day.

| Variant | Protocol | Steps | MAE | Skill vs best baseline | P10 to P90 coverage | WIS |
|---|---|---|---|---|---|---|
| strict | time: Mathura 2021 (51 winter days) | 4,896 | 0.0372 | +8.4% | 83.3% | 0.0241 |
| strict | held-out district: Bareilly | 78,116 | 0.0570 | +11.6% | 76.6% | 0.0366 |
| oracle weather | time: Mathura 2021 | 4,896 | 0.0373 | +8.2% | 83.0% | 0.0241 |
| oracle weather | held-out district: Bareilly | 78,116 | 0.0562 | +12.9% | 76.8% | 0.0360 |

Bareilly by season (strict): winter skill 8.5%, coverage 78.0%; summer 12.2%, 77.1%; monsoon 10.5%, 73.0%;
post-monsoon 14.9%, 78.7%.

**Gate G4: failed.** The pre-registered rule (`docs/DECISIONS.md`) needs at least 10% skill and 78 to 82% coverage
for the strict variant on the time protocol; it scored 8.4% and 83.3%. Consequences, as pre-registered:
- Round 1's demand model stays in the API; demand v2 is not described as an AI improvement anywhere.
- On the held-out district demand v2 is 11.6% better than the baseline on MAE, but its interval under-covers
  (76.6%, monsoon 73.0%); the fixed 60-day calibration window is the first thing to revisit.
- Target-day temperature (oracle) adds almost nothing, so a better temperature forecast would not rescue the gate.
- The risk engine does not depend on this result: scenarios draw demand from observed analog days.

## Upstream voltage

Not run here: the upstream-voltage model (`engine/upstream.py`, task P2.5) belongs to Person A. Its evaluation
(`python -m engine.upstream`, writing `ml/reports/upstream_v2.json`) runs on these same files once P2.5 is merged.
