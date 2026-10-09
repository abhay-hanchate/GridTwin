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

### Result (run 9 Oct 2026, `python -m scripts.bakeoff solar`)

Mask: 4,414 daylight hours of 2025. Five NWP models passed gate G2 (GFS, ICON, GEM, ARPEGE, ECMWF IFS).
Round 1's committed forecast reproduces its published MAE (0.0396) on this mask exactly.

| Candidate | MAE | WIS | Coverage | Winter MAE | Summer MAE | Monsoon MAE | Post-monsoon MAE |
|---|---|---|---|---|---|---|---|
| persistence | 0.0456 | 0.0353 | 78.9% | 0.0427 | 0.0241 | 0.0609 | 0.0508 |
| Round 1 | 0.0396 | 0.0290 | 82.3% | 0.0411 | 0.0176 | 0.0510 | 0.0489 |
| physics, best-match blend | 0.0411 | 0.0292 | 76.3% | 0.0440 | 0.0219 | 0.0526 | 0.0427 |
| physics, mean of 5 NWP | 0.0335 | 0.0235 | 78.7% | 0.0386 | 0.0208 | 0.0421 | 0.0279 |
| bias-corrected mean | 0.0326 | 0.0233 | 78.1% | 0.0365 | 0.0185 | 0.0428 | 0.0276 |
| LightGBM direct | 0.0333 | 0.0215 | 79.9% | 0.0347 | 0.0180 | 0.0464 | 0.0273 |
| **LightGBM residual (solar v2)** | **0.0329** | **0.0214** | 80.3% | 0.0321 | 0.0173 | 0.0470 | 0.0277 |

**Winner: LightGBM residual.** S (simplest below Round 1) is the 5-model physics mean; the residual model's WIS
is 8.9% lower, which clears the 3% margin. What the table says: averaging five weather models carries most of the
median gain (0.0411 to 0.0335, no ML); the trees mainly improve the interval. In the monsoon the plain ensemble
mean has the lower MAE (0.0421 against 0.0470).

## Solar intervals (P4.1, owner: Person B)

Pre-registered 9 Oct 2026, together with the median entry above.

- **Median:** the winner of the median bake-off.
- **Candidates:** raw quantiles; Round 1 scaling (half-widths around the median times 2.5); rolling split-conformal
  with windows 30, 60 and 120 days; rolling split-conformal per hour of day (60-day window).
- **Metric:** 80% interval coverage per season (target 78 to 82%), then WIS.
- **Decision rule:** among candidates inside 78 to 82% in every season, the lowest WIS wins. If none is inside the
  band in every season, the candidate with the smallest worst-season distance from 80% wins and the miss is reported
  on the Proof page.

### Result (run 9 Oct 2026, same run)

Median model: LightGBM residual. Coverage of the 80% interval:

| Candidate | WIS | Overall | Winter | Summer | Monsoon | Post-monsoon |
|---|---|---|---|---|---|---|
| raw quantiles | 0.0224 | 51.8% | 46.9% | 59.6% | 54.1% | 40.0% |
| Round 1 scale 2.5 | 0.0226 | 83.6% | 77.6% | 86.8% | 89.4% | 72.6% |
| **conformal, 30 days** | **0.0213** | 79.9% | 74.9% | 84.0% | 79.5% | 80.7% |
| conformal, 60 days | 0.0214 | 80.3% | 76.4% | 86.0% | 77.6% | 82.4% |
| conformal, 120 days | 0.0215 | 80.1% | 76.4% | 89.1% | 74.1% | 83.9% |
| conformal per hour, 60 days | 0.0214 | 78.0% | 72.6% | 80.4% | 77.3% | 83.6% |

**No candidate stays within 78 to 82% in every season.** Winter is under-covered and summer over-covered by
every window. By the fallback rule the 30-day window wins (worst season: winter, 5.1 points below 80%). It is also
the lowest WIS. The plan's spike reported that a 60-day window "restores 79-80% in every season"; the build does
not confirm that, and the Proof page shows the seasonal miss. Solar v2 ships with
`ml.solar_v2.CONFORMAL_WINDOW_DAYS = 30`; 60 and 120 days stay callable through `run(window=...)`.

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

---

## Gate G7: measured-plant yield calibration (P4.4, owner: Person B)

Recorded 9 Oct 2026. The Karnataka 72 kWp plant data is on IEEE DataPort, whose downloads need a signed-in
account; the build has none, so the outcome is **(b)**: the calibration script is not run, the PV model keeps the
14% system-loss assumption, and the Proof page says "yield not calibrated against measured data".
`scripts/calibrate_pv.py` and its tests are in place, so a teammate with an IEEE account can download the file and
run it (see the plan, P4.4 step 5). The cold-start interval widening (15% at zero history, 30-day prior weight)
is an assumption, not a measurement.
