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
Second run (10 Oct 2026): extra lag features, Bareilly's training rows pooled in for the time protocol, and a rolling
14-day conformal window, chosen on 2020 validation before 2021 was scored (`docs/DECISIONS.md`).

| Variant | Protocol | Steps | MAE | Skill vs best baseline | P10 to P90 coverage |
|---|---|---|---|---|---|
| strict | time: Mathura 2021 (51 winter days) | 4,896 | 0.0369 | +9.0% | 78.8% |
| strict | held-out district: Bareilly | 78,116 | 0.0545 | +15.3% | 79.8% |
| oracle weather | time: Mathura 2021 | 4,896 | 0.0372 | +8.4% | 79.5% |
| oracle weather | held-out district: Bareilly | 78,116 | 0.0538 | +16.5% | 79.9% |

Bareilly by season (strict): winter skill 12.5%, coverage 79.4%; summer 15.4%, 79.9%; monsoon 15.5%, 80.0%;
post-monsoon 16.9%, 80.0%.

**Gate G4: failed, on skill only.** The pre-registered rule needs at least 10% skill and 78 to 82% coverage for the
strict variant on the time protocol; it scored 9.0% and 78.8%. Consequences, as pre-registered:
- The demand model is not described as an AI improvement anywhere.
- On the held-out district, which covers every season, both conditions are met; the time protocol has only 51
  winter days because the Mathura 2021 file ends on 20 February 2021.
- Target-day temperature (oracle) adds almost nothing, so a better temperature forecast would not rescue the gate.
- The risk engine does not depend on this result: scenarios draw demand from observed analog days.

## Upstream voltage

Not run here: the upstream-voltage model (`engine/upstream.py`, task P2.5) belongs to Person A. Its evaluation
(`python -m engine.upstream`, writing `ml/reports/upstream_v2.json`) runs on these same files once P2.5 is merged.
