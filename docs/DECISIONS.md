# Method decisions (bake-offs)

Each entry is written **before** its candidates are run (plan section 0.8). The rule is not changed after the
results are seen. Results are appended under the entry and the machine-readable record goes to
`data/results/bakeoff_<component>.json` (written by `scripts/bakeoff.py`).

Seasons used in every per-season table (Indian meteorological seasons): winter Dec to Feb, summer Mar to May,
monsoon Jun to Sep, post-monsoon Oct and Nov.

---

## Solar median forecast (P4.1, owner: Person B)

Pre-registered 9 Oct 2026, before any candidate below was run in the build.

- **Truth:** ERA5-driven PV (pvlib PVWatts, Mathura), hourly. A reference proxy, not rooftop meters.
- **Split:** train 2024-01-01 to 2024-10-31; 2024-11 and 2024-12 only as the first conformal pool; test every
  daylight hour (clear-sky GHI > 0) of 2025.
- **Mask:** identical for all candidates: 2025 daylight hours where every candidate has a value.
- **Intervals for point forecasts:** candidates that only give a median get the same rolling 60-day split-conformal
  interval as solar v2 (P10 = P90 = median before widening), so WIS compares like with like.
- **Candidates, simplest first:**
  1. persistence (same hour yesterday)
  2. Round 1 model (its committed 2025 forecast with its own 2.5x interval)
  3. physics only, Open-Meteo best-match blend (one NWP)
  4. physics only, mean of the five NWP models that pass gate G2
  5. bias-corrected ensemble mean (linear regression of truth on the ensemble mean, fitted on the training months)
  6. LightGBM quantiles, direct target
  7. LightGBM quantiles, residual target over the ensemble mean (the solar v2 hypothesis)
  - Chronos-2 and TimesFM run in P4.3 on the same mask and are judged there by the stricter 5% rule.
- **Metric:** WIS (80% interval plus median) on the mask; MAE and coverage reported; per-season table.
- **Decision rule:** among candidates whose MAE is below Round 1's on the mask (gate G3), take the simplest one, S.
  The winner is the lowest-WIS candidate if its WIS is at least 3% below S's WIS; otherwise S wins.
  If no candidate beats Round 1, Round 1 stays.

## Solar intervals (P4.1, owner: Person B)

Pre-registered 9 Oct 2026, together with the median entry above.

- **Median:** the winner of the median bake-off.
- **Candidates:** raw quantiles; Round 1 scaling (half-widths around the median times 2.5); rolling split-conformal
  with windows 30, 60 and 120 days; rolling split-conformal per hour of day (60-day window).
- **Metric:** 80% interval coverage per season (target 78 to 82%), then WIS.
- **Decision rule:** among candidates inside 78 to 82% in every season, the lowest WIS wins. If none is inside the
  band in every season, the candidate with the smallest worst-season distance from 80% wins and the miss is reported
  on the Proof page.

## Demand forecast (P2.7, owner: Person B)

Pre-registered 9 Oct 2026, before the demand model was run on the real data.

- **Target:** mean kW per home across the meters present, 15 minutes.
- **Protocols:** (a) time: train Mathura up to 2020-12-31, test Mathura 2021; (b) held-out district: train all
  Mathura, test Bareilly. Calibration is the last 60 days of each training period.
- **Candidates:** baselines lag-1d, lag-7d and their mean; LightGBM quantiles on the log-ratio to the best baseline
  (demand v2); each with strict features (lagged temperature only) and an oracle variant (target-day ERA5
  temperature, labelled as an upper bound).
- **Metric:** MAE, WIS and P10 to P90 coverage, per protocol and per season.
- **Decision rule (gate G4):** demand v2 is adopted only if the strict variant on protocol (a) has skill of at least
  10% against the best baseline and coverage of 78 to 82%. Otherwise the true numbers are reported, Round 1's demand
  model stays in the API, and no AI improvement is claimed.
- **Known gap, recorded before the run:** demand v2 widens its interval with one fixed 60-day calibration window
  before the test period; section 4.2 of the plan asks for a rolling window. If coverage drifts out of the band
  across the test year, a rolling window is the first candidate to add.
