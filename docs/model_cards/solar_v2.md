# Model card: solar forecast v2

**Purpose.** Tomorrow's rooftop solar output in kW per installed kW, for every 15 minutes, as P10, P50 and P90.
It feeds the scenario generator; it never approves a fix on its own (physics decides).

**Data.**
- Inputs: day-ahead irradiance, cloud, temperature and wind from five NWP models through Open-Meteo's
  previous-runs API (`previous_day1`, so only what was known the day before): GFS, ICON, GEM, ARPEGE, ECMWF IFS.
- Truth: ERA5 reanalysis weather through the same pvlib PVWatts chain (a reference proxy, not measured rooftop
  output; the yield is not calibrated against a real plant, gate G7).
- Site: Mathura. Split: train January to October 2024; November and December 2024 only seed the interval;
  test every daylight hour of 2025 (4,414 hours).

**Method.** Each NWP model's weather goes through PVWatts; the ensemble mean, spread, mean cloud, mean irradiance
and clear-sky irradiance are features; LightGBM quantile models predict the residual of truth over the ensemble
mean; the 80% interval is widened by split-conformal scores from earlier out-of-sample errors of the same season
(one width per season; chosen in interval bake-off round 2).
Model files are checksummed (SHA-256 of the committed LF bytes) and checked before every live use.

**Measured scores** (`ml/reports/solar_v2.json`, `data/results/bakeoff_solar.json`, 2025 daylight hours)

| | MAE (kW/kWp) | 80% interval coverage | WIS |
|---|---|---|---|
| Solar v2 | 0.0329 | 79.4% | 0.0214 |
| Round 1 model | 0.0396 | 82.3% | 0.0290 |
| Physics only, mean of the five NWP models | 0.0335 | | |
| Physics only, one blended NWP | 0.0411 | | |
| Persistence | 0.0456 | | |

Gate G2 (NWP availability): five models pass; JMA GSM and UKMO 10 km are dropped. Gate G3 (beat Round 1's MAE on
the identical mask): passed.

**What the numbers say, without spin.**
- Most of the median gain comes from averaging five weather models, with no ML at all (0.0411 to 0.0335).
  LightGBM adds a small median gain and mainly a better interval.
- In the monsoon the plain ensemble mean has the lower MAE (0.0421 against 0.0470).
- **Coverage by season** (per-season widths): winter 79.5%, summer 82.4%, monsoon 78.5%, post-monsoon 75.8%.
  Per-season widths fixed the winter under-coverage of the earlier single 30-day width (74.9%); post-monsoon is now
  the weakest season because only November 2024 came before it. No method tried kept 78-82% in every season.
- Chronos-2 is benchmarked separately (task P4.3); its result and adoption decision are recorded in
  `docs/DECISIONS.md` when run.

**Limitations and failure modes.**
- Truth is a reanalysis proxy; coverage is measured against it, not against rooftop meters.
- Open-Meteo's previous-runs history starts in 2024, so the model has one training season of each kind.
- With fewer than three complete NWP models, live inference refuses to forecast rather than guess.
- Trained for Mathura; Bareilly uses the same model with its own sun position, which is not separately validated.

**Monitoring.** `scripts/monitor.py`, nightly: re-estimates the per-season widths (and a 30-day fallback) from
realised errors (`data/monitor/conformal_state.json`) and writes `data/monitor/WARN` when 14-day coverage leaves 70 to 90%
or MAE rises more than 25% above 0.0329. Runbook: `docs/runbooks/stale_model.md`.
