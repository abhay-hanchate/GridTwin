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

### Demand result (run 9 Oct 2026, `python -m ml.demand_v2`)

**Gate G4 failed:** strict variant, Mathura 2021: skill +8.4% against the mean of lag-1d and lag-7d (needs 10%),
coverage 83.3% (needs 78 to 82%). Round 1's demand model stays; no AI improvement is claimed. The Mathura 2021
file ends on 20 Feb 2021, so this protocol covers 51 winter days only. On the held-out district (Bareilly) the
skill is +11.6% but coverage is 76.6% (monsoon 73.0%). The oracle-weather variant changes skill by under 1.5
points. Details: `docs/generated/data_v2.md`.

### Demand v2, second run (pre-registered 10 Oct 2026, before the 2021 test was scored)

Gate G4 and its threshold are unchanged. The first run above stays on record.

- **Selection window, not the test:** train before 2020-11-01, validate on Mathura 2020-11-01 to 2020-12-31. 2021 was
  not loaded while choosing.
- **Candidates and validation results (skill vs best baseline, P10 to P90 coverage):** as shipped, fixed 60-day
  window 13.0%, 88.4%; rolling 30-day window 13.0%, 82.2%; rolling 60-day 13.0%, 84.2%; extra features + rolling 30
  15.4%, 83.1%; pooled districts + rolling 30 13.9%, 81.7%; extra features + pooled + rolling 30 15.9%, 82.7%;
  the same with a slower learner 15.6%, 82.1%; extra features + pooled + rolling 21 15.9%, 82.2%;
  **extra features + pooled + rolling 14: 15.9%, 82.0%**.
- **Rule:** the highest validation skill among candidates whose validation coverage is inside 78 to 82%. Winner:
  extra features + pooled + rolling 14-day conformal window.
  - *Extra features* (all known at the end of the day before): same-slot lag 2 and 14 days, yesterday's and the last
    week's mean level, a trailing smooth of yesterday around the slot, yesterday's mean temperature.
  - *Pooled:* Bareilly's training-period rows are added to Mathura's, with a district flag (protocol (a) only;
    protocol (b) keeps Bareilly fully held out).
  - *Rolling window:* each test day is widened with the conformal amount from the 14 days before it, which a
    day-ahead forecast has already observed.
- **Then:** the winner is run once on 2021 with `python -m ml.demand_v2`, and the result is recorded below whether
  or not it passes.

**Result (run 10 Oct 2026, once):** strict variant, Mathura 2021: skill **+9.0%** (needs 10%), coverage **78.8%**
(inside 78 to 82%). **Gate G4 still fails**, now on skill only. The 2021 test was not used for any choice and no
further variant is tried against it. On the held-out district (Bareilly, January to October 2021) the same method
scores +15.3% and 79.8% coverage, with every season inside the band (winter 12.5%, 79.4%; summer 15.4%, 79.9%;
monsoon 15.5%, 80.0%; post-monsoon 16.9%, 80.0%). The second-run model replaces the first in `ml/demand_v2.py`
because it is better on both protocols; demand is still not described as an AI improvement, as the rule requires.

---

## Foundation-model benchmark: Chronos-2 (P4.3, owner: Person B)

Pre-registered 9 Oct 2026, before Chronos-2 was run in the build. The rule is the plan's, unchanged.

- **Reference:** solar v2 as shipped (LightGBM residual, 30-day conformal window), on the same 2025 daylight mask.
- **Candidate:** Chronos-2 with covariates (`pv_mean`, `ghi_mean`, `cloud_mean`) and a 14-day context of past PV.
  TimesFM 2.5: not evaluated (its Python API was not inspected; a second foundation model cannot change the decision
  until the first clears the bar).
- **Rule:** adopt only if WIS is at least 5% lower than the reference **and** the deployment can supply yesterday's
  observed PV.
- **Known before the run:** in this project "observed PV" is ERA5-driven, and ERA5 is published several days late,
  so yesterday's value is not available when tomorrow's forecast is made. Unless rooftop meters supply it, the
  second condition fails whatever the score; the WIS result is still recorded.

### Result (run 9 Oct 2026, `python -m ml.benchmark`, RTX 4050, 35 s)

| | MAE | Coverage | WIS | WIS gain vs solar v2 |
|---|---|---|---|---|
| Solar v2 (as shipped, 30-day window) | 0.0329 | 79.9% | 0.0213 | |
| Chronos-2 with covariates | 0.0318 | 78.6% | 0.0207 | 2.8% |

**Not adopted.** The WIS gain is 2.8%, below the 5% bar, and the second condition fails anyway (no live source of
yesterday's PV). Chronos-2 stays a benchmark; `ml/reports/solar_benchmark.json` holds the record.

---

## Upstream voltage (P2.5, owner: Person A)

Pre-registered 9 Oct 2026, before any candidate below was run on the real data. Person A builds the model and
runs this bake-off (it is the first step of P2.5); Person B reuses `engine.upstream.evaluate` in P2.7.

- **Series:** median customer voltage per 15 minutes in pu of 230 V (`upstream_vm_pu_<district>.parquet`), used as
  the voltage arriving at the transformer.
- **What a candidate must produce:** whole-day sample paths (n x 96). The scenario generator replays paths, so
  per-slot quantiles alone are not enough.
- **Information at issue time:** the target date (month, weekday or weekend) and the previous day's observed mean
  voltage. Nothing from the target day.
- **Usable day:** at least 80 of 96 valid slots, and the previous day also usable.
- **Protocols:** (a) time: fit on Mathura days before 2021-01-01, test Mathura 2021; (b) held-out district: fit on
  all Mathura days, test all Bareilly days (conditioned on Bareilly's own previous day).
- **Candidates, simplest first:**
  1. `climatology`: whole training days drawn at random from the same calendar month (nearest month if none).
  2. `analog_days`: whole training days drawn from the 30 days within +/-1 month whose previous-day mean is closest
     to the target's previous-day mean (historical-day bootstrap conditioned on yesterday).
  3. `ar1_shape`: monthly mean plus an AR(1) day-to-day deviation conditioned on yesterday, a (month, weekend) mean
     intra-day shape and an AR(1) residual across slots (the plan's hypothesis).
  4. `lgbm_day_quantiles`: LightGBM quantile regression (9 levels) of the day mean on yesterday's mean, maximum and
     spread and the calendar; a day mean is drawn by inverting the interpolated quantiles, and the intra-day shape
     is a same-month training day's deviation from its own mean (quantile regression, made into paths).
  - Not run: Gaussian process (for one daily series with a seasonal mean it is close to AR(1) smoothing, and fitting
    and tuning it exceeds the two-hour budget for no expected gain).
- **Metrics (200 paths per test day, seed 0):** coverage of the 10-90% interval of the day maximum (primary);
  sample CRPS of the day maximum; also reported: CRPS of the day mean and mean per-slot 80% coverage.
- **Decision rule:** keep candidates whose day-maximum coverage is within 70-90% on BOTH protocols; the winner is
  the lowest CRPS of the day maximum averaged over the two protocols. Candidates within 2% of that CRPS count as
  tied and the simplest of them wins. If none is in the band on both protocols, the candidate with the smallest
  worst-protocol distance from 80% wins, and the miss is reported, not tuned away.

### Result (run 9 Oct 2026, `python -m engine.upstream --bakeoff`)

| Candidate | Mathura 2021 (50 days): day-max coverage / CRPS | Bareilly (875 days): day-max coverage / CRPS |
| --- | --- | --- |
| climatology | 18.0% / 0.01288 | 44.2% / 0.01390 |
| analog_days | 70.0% / 0.00796 | 51.8% / 0.01085 |
| ar1_shape | 70.0% / 0.00985 | 65.3% / 0.01060 |
| **lgbm_day_quantiles** | **82.0% / 0.00536** | **69.3% / 0.00970** |

**Winner: `lgbm_day_quantiles`, through the fallback branch of the rule.** No candidate is inside 70-90% on both
protocols; it has the smallest worst-protocol distance from 80% (Bareilly 69.3%), and it also has the lowest CRPS on
both. **Recorded as a miss:** on the held-out district its interval is slightly too narrow. The Mathura 2021 test has
only 50 usable days, so its coverage is uncertain by several points. The plan's hypothesis (AR(1) plus shape) loses on
both coverage and CRPS. `engine.upstream.UpstreamModel` now points to the winner.

## Live day-ahead demand and voltage (owner: Person B)

Pre-registered 9 Oct 2026, before any model below was trained. Design: `docs/superpowers/specs/2026-10-09-live-demand-voltage-design.md`.

- **Targets:** household demand (mean kW per home) and grid voltage (V), every 15 minutes, for tomorrow.
- **Split:** walk-forward by month (train on all earlier months of both districts, test the month), for every month
  after the first six; plus train Mathura, test Bareilly.
- **Candidates:** climatology (district, month, weekday type, slot); pattern-only LightGBM (no `up_ratio`);
  live-anchored LightGBM (with `up_ratio`). None uses household lags.
- **Rule:** the live-anchored model is adopted if its MAE is at least 10% below climatology and below pattern-only,
  and its P10-P90 coverage is 78-82% overall and 70-90% in every season. Otherwise the best model that does meet the
  coverage rule is used and the true numbers are reported.

### Round 1 result (run 9 Oct 2026, `python -m ml.live_dayahead`, 22 walk-forward months, 2019-11 to 2021-10)

| Target | Candidate | MAE | Skill vs climatology | Coverage | Post-monsoon coverage |
|---|---|---|---|---|---|
| Demand (kW/home) | climatology | 0.1415 | | 78.6% | 29.5% |
| | pattern only | 0.0713 | +49.6% | 77.1% | 43.6% |
| | live anchored | 0.0727 | +48.6% | 76.5% | 40.6% |
| Voltage (V) | climatology | 6.23 | | 73.7% | 45.2% |
| | pattern only | 3.77 | +39.5% | 76.8% | 54.2% |
| | live anchored | 3.75 | +39.8% | 76.9% | 49.2% |

No candidate met the coverage rule. The UP anchor did not beat pattern-only (tomorrow's temperature already carries
most of what state demand says). Diagnosis of the post-monsoon miss: (1) the first tested month (2019-11) had no
earlier out-of-sample errors, so its interval was never widened (coverage 32-42%); (2) Bareilly in October 2021 used
0.16 kW per home more than any earlier pattern (a level shift no model without live household data can see);
(3) the anchor needed all eight days, and 65 missing days in the UP history (mostly August to December 2020) blanked
248 of 976 anchor days.

### Round 2, pre-registered before running

Same candidates, same rule, same months. Two method fixes, applied to every candidate alike:
- **A. Warm-up interval:** when a month has no earlier out-of-sample errors, its interval width comes from a
  cross-fitted pool inside the training data (fit without the last training month, predict that month).
- **B. Anchor robustness:** `up_ratio` needs yesterday plus at least 5 of the 7 days before it (was: all 7).
Not added: a year-on-year UP level term. It would target the October 2021 shift, but it cannot run live (no UP
daily data for 2025 is reachable), so it fails the deployability condition.

### Round 2 result (run 9 Oct 2026, 24 walk-forward months, 2019-11 to 2021-10)

| Target | Candidate | MAE | Skill vs climatology | Coverage | Seasons (winter, summer, monsoon, post-monsoon) |
|---|---|---|---|---|---|
| Demand (kW/home), 124,761 rows | climatology | 0.1308 | | 83.1% | 90.7, 78.9, 80.3, 78.4 |
| | pattern only | 0.0700 | +46.5% | 83.5% | 85.8, 80.0, 79.3, 91.0 |
| | live anchored | 0.0705 | +46.1% | 83.6% | 85.8, 80.3, 79.8, 90.7 |
| Voltage (V), 129,348 rows | climatology | 5.91 | | 78.4% | 75.6, 70.9, 82.9, 89.3 |
| | pattern only | 3.79 | +36.0% | 82.2% | 80.9, 79.5, 81.5, 90.6 |
| | live anchored | 3.72 | +37.1% | 83.0% | 82.6, 79.8, 81.5, 91.4 |

Held-out district (train Mathura, test Bareilly), MAE: demand 0.0926 live / 0.0934 pattern / 0.1081 climatology;
voltage 4.74 / 4.83 / 5.03 V.

**Rule outcome, applied literally:** demand: no candidate meets the coverage rule, so pattern-only (lowest MAE) is
reported. Voltage: only climatology meets the coverage rule, so the rule picks climatology, although its MAE is 59%
higher than the live-anchored model's. The live UP anchor adds at most 1.7% (voltage) and nothing for demand.
**Open question for the owner:** the rule ranks interval coverage above accuracy, so it picks a far less accurate
model whose interval happens to land in the band. The rule is not changed here; changing it is the owner's decision
and will be recorded as a rule change, not as a result.

### Rule change by the owner (9 Oct 2026, after seeing round 2)

The owner changed the rule to **accuracy first**: the lowest-MAE candidate whose P10-P90 coverage is 75-85% overall
and 70-92% in every season. Reason given: coverage can be corrected by widening or narrowing the interval, accuracy
cannot, so a rule that picks a model with 59% more error for its interval width is the wrong rule. This is a rule
change made after the results were seen, and it is reported as one.

Outcome on the round 2 numbers: **demand: pattern only** (MAE 0.0700 kW/home, +46.5% vs climatology, coverage
83.5%); **voltage: live anchored** (MAE 3.72 V, +37.1%, coverage 83.0%; pattern-only is used live until the UP
recorder has six days). Under the original rule the picks were pattern only and climatology.

---

## Solar intervals, round 2: different ranges for different kinds of day (owner: Person B)

Pre-registered 9 Oct 2026, before any candidate below was run. Round 1 (above) found no method inside 78-82% in
every season; winter under-covered (74.9%) with the shipped 30-day window.

- **Median:** solar v2 (LightGBM residual), unchanged. Same split and the same 4,414-hour 2025 mask.
- **Candidates** (all rolling, each day's width from earlier days only):
  1. shipped: one width from the last 30 days (reference);
  2. by sky: separate widths for forecast-clear, partly cloudy and cloudy hours, where the forecast clearness is
     the ensemble mean irradiance over clear-sky irradiance (clear above 0.8, cloudy below 0.5), 30 and 60 days;
  3. by season: separate widths per season from all earlier days of that season;
  4. scaled: errors divided by the model's own P10-P90 spread, so wide-spread hours get wider intervals, 30 days.
  A group with fewer than 50 earlier points uses the all-hours pool.
- **Rule (unchanged from round 1):** lowest WIS among candidates inside 78-82% in every season; if none, the
  smallest worst-season distance from 80%. A new candidate replaces the shipped one only if it wins by this rule.

### Result (run 9 Oct 2026, `python -m scripts.bakeoff solar_intervals`)

| Candidate | WIS | Overall | Winter | Summer | Monsoon | Post-monsoon |
|---|---|---|---|---|---|---|
| shipped, one width, 30 days | 0.0213 | 79.9% | 74.9% | 84.0% | 79.5% | 80.7% |
| by sky, 30 days | 0.0214 | 79.6% | 74.0% | 84.5% | 79.2% | 80.1% |
| by sky, 60 days | 0.0214 | 79.1% | 75.4% | 84.9% | 76.4% | 81.0% |
| **by season, all earlier days** | 0.0214 | 79.4% | 79.5% | 82.4% | 78.5% | 75.8% |
| scaled by spread, 30 days | 0.0218 | 79.6% | 82.0% | 81.2% | 79.1% | 74.8% |

Still no candidate inside 78-82% in every season. By the fallback, **by season** wins (worst season 4.2 points from
80% against 5.1 for the shipped width): winter is fixed (74.9% to 79.5%) and post-monsoon drops to 75.8%, because
post-monsoon 2025 has only November 2024 to learn from. WIS is unchanged. Sky classes did not help winter, so the
winter miss is seasonal (haze and fog), not about clouds. Solar v2 switches to per-season widths.

---

## Chronos-2, round 2: a context that exists live (owner: Person B)

Pre-registered 9 Oct 2026, before running. Round 1 fed Chronos-2 the last 14 days of ERA5-driven PV, which arrives
days late, so it could not run live.

- **Candidate:** Chronos-2 whose 14-day context is PV computed from the weather service's **same-day (day-0)
  estimate** of irradiance, the historical counterpart of what the live forecast API returns for yesterday
  (`past_days=1`). Covariates unchanged (`pv_mean`, `ghi_mean`, `cloud_mean`).
- **Reference:** solar v2 as shipped (per-season interval widths), same 4,414-hour 2025 mask.
- **Also reported, not a candidate:** round 1's ERA5-context Chronos-2, as the upper bound of what better context
  would give.
- **Rule (unchanged):** adopt only if WIS is at least 5% lower than the reference; deployability is now satisfied by
  construction.

### Result (run 9 Oct 2026, `python -m ml.benchmark`)

| | MAE | Coverage | WIS | WIS gain vs solar v2 |
|---|---|---|---|---|
| Solar v2 as shipped (per-season widths) | 0.0329 | 79.4% | 0.0214 | |
| **Chronos-2, day-0 nowcast context (live-capable)** | 0.0511 | 45.2% | 0.0360 | **-68%** |
| Chronos-2, ERA5 context (upper bound, not live) | 0.0318 | 78.6% | 0.0207 | +3.3% |

**Not adopted, and closed.** Chronos-2's edge came entirely from seeing the true PV of the past days. The only
yesterday estimate that exists live (the same-day NWP irradiance) is itself far from the truth (MAE 0.0507 against
0.0335 for our five-model day-ahead mean; checked for a time shift: none), and Chronos-2 inherits that error. Even
with the true history it would gain 3.3%, below the 5% bar. Solar v2 stays.

---

## Owner decisions, 9 Oct 2026

- **Gate G4 is not retired.** It stays recorded as failed (`docs/generated/data_v2.md`).
- **The UP recorder is not scheduled.** `scripts/record_up_demand.py` runs only when started by hand, so the live
  forecast normally runs without the UP anchor: voltage uses its pattern-only model (36.0% better than climatology
  in round 2, against 37.1% with the anchor) and every forecast says which model it used.

---

## Gate G8 on both districts (pre-registered 10 Oct 2026, before the run)

The first G8 run replayed only Mathura's 2021 days, and that file ends on 20 February 2021. Task P5.3 of the plan
defines G8 on **both districts**: train on the earlier years, test on the later year. This run follows that protocol.
Nothing else changes: the threshold, the models, and the reference.

- **Calibration fit:** each district's risk model is fitted before 2020-05-01 and predicts 40 days spread over
  2020-05-01 to 2020-12-31. One isotonic map per rule is fitted on the pooled (predicted, observed) steps of both
  districts.
- **Held-out test:** each district's model is fitted before 2021-01-01 and predicts its 2021 days: Mathura 40 days
  (January to February), Bareilly 60 days (January to October). The fixed map is applied.
- **Reference:** the base rate of the pooled test steps themselves. This is a strict reference because it knows the
  test outcome; it is kept on purpose.
- **Gate:** the calibrated Brier skill against that reference is above 0 on the pooled test, for each rule. The
  per-district skills are reported next to it, whether or not they pass.
- **Then:** the API serves the new map, and the result is recorded below whether or not it passes.

**Result (run 10 Oct 2026):** calibrated Brier skill on the pooled held-out test: **±10%: +0.51** (raw +0.50),
**UP ±6%: +0.45** (raw +0.44). **Gate G8 passes on both rules.** Per district: Bareilly (60 days, January to
October) +0.41 and +0.36; Mathura (40 days, January to February) +0.009 and **-3.90**. Mathura's 2021 window under
±6% is 99.7% unsafe, so a constant forecast is nearly unbeatable there, and that sub-result stays reported as below
the base rate. The pooled reference is a single rate for both districts, so part of the pooled skill comes from
telling the districts apart; Bareilly alone, a single district with every season, also passes.

## Which risk chances users see (decided 10 Oct 2026, fix brief F2)

- **Problem:** gate G8 passes on the recalibrated (isotonic) chances, but every page drew the raw ones, and the level,
  the first watch and act times and the expected hours came from the raw series.
- **Decision (option 1 of the brief):** `/risk` returns in `p_unsafe` the series users see: the calibrated chances
  when the stored map is `reliable` **and** the request is where the map was fitted (benchmark street, no fix);
  the raw chances otherwise. `series` says which; `calibration.applied` says whether the map was used, and
  `calibration.raw` and `calibration.calibrated` keep both.
- **One place:** `backend/v2/compute.py::shown_series` derives the level, `first_watch`, `first_act` and the expected
  hours from the shown series, with the same watch (20%) and act (50%) thresholds. The dashboard and the printable
  report only read these fields.
- **Expected hours when calibrated:** the sum of the calibrated chances times a quarter hour. The P10 to P90 range
  comes from the raw scenario draws and does not describe the calibrated chances, so it is `null` and not shown.
- **Grid and solar split:** the no-solar series is scaled step by step by calibrated over raw, so each bar keeps its
  grid and solar shares; where the raw chance is 0 the whole calibrated bar counts as grid.
- **Why not apply it everywhere:** the map was fitted with no fix on the benchmark street; applying it to a replay with
  a fix or to another street type would be an extrapolation that was never tested.

## The grid-voltage history the app reads (recorded 10 Oct 2026, fix brief F-0)

- **Problem:** `backend/v2/compute.py` read the older committed Mathura files (`data/processed/load_kw.parquet`,
  `pv_kw_per_kwp.parquet`, `upstream_vm_pu.parquet`), built from 2019 and early 2021 only. All of 2020 was missing
  (the voltage file 55.7% empty), so March and April had no "yesterday's voltage" and a missing value reached the
  voltage model silently; March was 8.1 V off the real record and April's daily shape correlated at 0.48.
- **Decision:** the app prefers the full record in `data/processed/v2` (`*_mathura.parquet`, about 4 MB, committed)
  and falls back to the old files. "Yesterday" for a 2025 date is the same calendar day of 2019, else 2020, else
  2021, then the month's mean, then the record's mean: never missing. Readiness requires the three files.
- **Open:** the generator still trains on Mathura only, because the benchmark street and the solar forecast are
  Mathura's. Adding Bareilly is a separate decision.

## Addition 1: control across multiple time steps (pre-registered 10 Oct 2026, before any run)

Starting point: `GridTwin_Final_Round_Feature_Research.md` (research blueprint, W1 to W4 and W8). Checked against the
code before building; where the check disagreed with the blueprint, the check wins.

- **Checked facts.** The battery is three pseudo-homes that inherit the homes' 0.95 power factor; at 20 kW of charge
  that shifts voltages by 2.2 V on the benchmark street and 4.3 to 5.0 V on the weak street, so the controller gives
  the battery explicit unity power factor (a per-home power-factor array; no engine change). A single linearisation of
  the voltages in battery power is accurate to 0.2 to 0.3 V at +/-15 kW on the benchmark street but off by 8 to 12 V
  at +/-30 kW on the weak street (15 May 2025, noon and 20:00, central differences, real solver as truth).
- **Planner (changed from the blueprint):** sequential linear programming, not one linearisation. Each round
  linearises every monitored phase voltage, line and transformer loading around the current planned trajectory by
  finite differences with the real three-phase solver, solves a MILP with a trust region on the actuators, and
  replays the horizon in the real solver; at most four rounds, the trust region halves when the prediction misses.
  Decision variables per step: charge and discharge power with a charge/discharge binary (no simultaneous charging and
  discharging) and three curtailment fractions, one per phase group. Horizon 16 quarter hours (at least 8 required),
  the same plan across three retained forecast scenarios. Objective, in order: hard limits, then least curtailed
  energy, then least battery throughput, then a soft end-of-horizon reserve.
- **Optimiser:** SciPy's HiGHS MILP (matrix form fits the sensitivity matrices) unless OR-Tools is faster on the same
  problems; both are already dependencies; the comparison is recorded below.
- **Re-planning:** every quarter hour, receding horizon, the first action executed; the battery's energy carries over.
  Forecasts are corrected causally with an exponentially weighted residual (solar, demand, grid voltage) whose
  coefficients are set on a development day, not on the fixture days; solar is never corrected at night. Extra
  trigger reasons (forecast residual, margin) are logged. Observations are **simulated** (a scenario not among the
  retained forecast ones, plus declared perturbations) and labelled so; they are not meter data.
- **Switching:** only an explicit allowlist of tie switches, all marked **hypothetical** (inferred from feeder-end
  geometry, not installed equipment); each device operation counts against a daily budget with a minimum dwell; at
  most one reconfiguration schedule per horizon is enumerated outside the MILP. The transformer tap stays fixed for
  the day (off-load tap changer).
- **Verification and statuses:** every executed action is solved in the real solver at the observed step and checked
  against every declared limit (voltage band, line and transformer loading, solver convergence, voltage unbalance
  only when declared). Statuses: verified_safe, optimiser_infeasible, search_exhausted, solver_failed,
  unsafe_fallback, invalid_action. Fallback order: the planned action if verified safe; else the first safe action in
  a finite permitted set checked with the solver; else the least-violation action, labelled unsafe_fallback; never
  called safe without the solver.
- **Comparison:** the existing reactive battery controller on the identical observations, starting energy and battery.
- **Code location:** a new top-level `control/` package that uses `engine/` as a library, so the results cache key
  (and the precomputed demo) is unchanged.

**Result: forecast correction settings (development day 10 June 2025, not a fixture day; 10 held-out truth scenarios,
every 16-step horizon of the day).** Mean absolute error of the horizon's later steps without correction: solar
0.0113 kW/kWp, demand 24.1% of the mean, grid voltage 4.63 V. Best of rho {0.3, 0.5, 0.7, 0.9} x decay {0.8, 0.9,
0.95} by the mean of the three relative errors: **rho 0.3, decay 0.95**: solar 0.0085, demand 10.5%, grid 3.65 V
(0.66 of the uncorrected error). These are the defaults; the fixture days were not used to choose them.

**Result: Addition 1 demonstrations (run 10 Oct 2026, `python -m scripts.control_replay --near-limit`).**

| Demonstration (`data/results/control/`) | Receding-horizon controller | Reactive battery rule, same observations | No control |
| --- | --- | --- | --- |
| Forecast error: an unforecast cloud (benchmark street, 09:00 to 18:00) | **0** of 36 unsafe | 10 | 13 |
| Battery only, like for like with the reactive rule (same day) | **9** of 36 | 10 | 13 |
| Battery saturation: 85% charge before the solar peak (09:00 to 15:00) | **0** of 24 | 21 | 21 |
| Depletion and an infeasible evening: weak street, grid sag and 50% more demand, permitted switching (16:00 to 22:00) | **6** of 24, all labelled unsafe | 8 | 8 |

Per quarter hour the loop took 1.4 to 2.1 s typical and up to 5.6 s (p95) on the development laptop, about 1 minute per
demonstration; the reactive rule takes under 0.1 s for the same window. The near-limit sweep (09:15 of
forecast_error, the executed action held) stays inside 253 V up to 5% more sun (252.6 V) and crosses it at 10% more
(253.2 V). Battery only, the look-ahead controller beats the reactive rule by one quarter hour (9 against 10); the
larger gains come from coordinating curtailment with the battery, so the two effects are reported separately. On the
weak street the battery empties (10%) holding the evening voltage up, one permitted reconfiguration is used at 18:00
when the sag starts (budget 2 operations, then refused for the rest of the day), and 6 quarter hours remain below
207 V with no permitted action safe: they are labelled unsafe_fallback with the reason, not hidden. The existing
battery fix in the tournament inherits the homes' 0.95 power factor; that is left unchanged here (it is in the cached
results) and noted as a known modelling issue.
## Addition 2: power-flow surrogate (pre-registered 10 Oct 2026, before any state was generated or model trained)

- **Purpose:** a screen that predicts what the solver would say about one street at one quarter hour, so candidate
  actions can be sorted before the solver verifies them. A screen is a prediction, never a verdict: only the
  power-grid-model solver may call anything safe (requirement 2.4).
- **Pilot (10 Oct 2026, simulated scenarios, before this section):** one state takes 2.4 ms in the solver and
  1.1-1.3 ms in a batch; Volt/VAR needed 26 passes on a 9,600-state batch (about 33 ms a state); the whole fix
  tournament on three scenarios took about 160 s, mostly envelopes, battery runs and switching probes. The surrogate
  must earn its place on the complete pipeline (screening plus solver verification), not on isolated inference.
- **Teacher and inputs:** labels come from `engine.solver.DaySolver` on `backend.v2.compute.network(id)` (round-robin
  phases). Inputs come from the app's own scenario generator (`compute.scenarios`, demo dates in 2025), so every
  state is **simulated**, never measured. The battery is three pseudo-homes at the street's worst node at unity power
  factor (as `control/execution.py`); homes keep power factor 0.95; curtailment keeps a share of each home's solar
  through the per-step export limit; no ambient temperature correction.
- **Streets:** `benchmark_250` and `rural_weak_63`, one model per street. The others are unsupported (sent to the
  solver) until trained.
- **Features (same for every candidate):** each home's demand kW, delivered solar kW (before the Volt/Watt cut) and
  installed kWp; grid voltage pu; tap; battery kW (+ charging); inverter mode one-hot (fixed unity power factor,
  Volt/VAR, Volt/Watt, both). Nothing the solver computes is an input.
- **Targets:** every LV node-phase voltage (96 x 3), every line loading (95), transformer loading, convergence.
- **Families and splits (per street).** A family is (date, solar adoption, tap, inverter mode); each family is 6
  scenarios x 96 steps, with battery power (half the states, uniform within +-100 kW, fixed power factor only) and
  per-phase-group curtailment (30% of states, keep uniform 0.2-1) drawn per state.
  - Development months: Jan, Feb, Apr, May, Jul, Aug, Oct, Nov (days 5, 15, 25). Day 5 and 15 are **train**; day 25
    is **tune** in Jan, Apr, Jul, Oct and **calibrate** in Feb, May, Aug, Nov. Adoption 25%, 50%, 100%.
  - Test months: Mar, Jun, Sep, Dec (days 10, 20). Adoption 75% and 100%.
  - Tap {0, 1, 2} x four modes; **tap 2 with Volt/VAR and Volt/Watt** and **tap 1 with Volt/Watt** never appear in
    development data and are tested as unseen combinations inside the declared range.
  - Each date gets four random (adoption, tap, mode) families with a fixed seed.
  - **Boundary sets (2.7):** about 30% extra states per split, from that split's families only. Bisection on the grid
    voltage (for voltage limits) or a demand scale 0.3-2 (for loading) puts the solved extreme within 2 V of a limit
    of the +-6% or +-10% rule, or at 95-105% line or transformer loading. States on both sides are kept.
  - **Out-of-range set (2.5):** kWp doubled, demand x4, grid voltage outside the trained range, taps -1 and -2,
    battery 150 kW, battery at another node, a changed phase map, a switched layout, an ambient temperature. Every one
    must come back `unsupported` and go to the solver; the raw model error there is reported too.
  - Solver failures are kept: regression targets are masked, convergence is a label.
- **Supported range (2.5):** the street's layout, phase map and solver version as trained; each feature within its
  min-max over the train split; tap and mode each seen in training. Anything else: `unsupported`, risky, solver.
- **Candidates (2.2), same features, splits and labels:**
  1. Ridge (alpha chosen on tune from 0.01, 0.1, 1, 10), one per inverter mode, predicting every output; extremes
     taken afterwards.
  2. LightGBM predicting the four extremes directly (63 leaves, rate 0.05, up to 2,000 trees, early stopping on tune).
  3. MLP 256/128 ReLU (scikit-learn, Adam, rate 0.001, batch 256, L2 0.0001), standardised inputs and outputs, all
     outputs, up to 200 epochs with early stopping (patience 15) on the tune split; exported to NumPy.
  - Convergence: a LightGBM classifier when train has at least 20 failures, otherwise no failure model (stated).
  - Not built: a graph network (all five streets share one layout, so its only advantage, new layouts, cannot be
    tested honestly) and physics-informed refinement (it adds latency to approach what the solver gives in ~2 ms).
    No PyTorch: the MLP trains on the CPU and the GPU is not used.
- **Guard band:** on the calibrate split, one-sided split-conformal residuals of each extreme (V for voltage, points
  for loading) in the dangerous direction and, separately, in the optimistic direction, each at level 1 - 0.005/4.
  Never negative. A screen is **risky** when a guarded extreme crosses the rule's band or 100% loading, or the
  failure probability exceeds 1%. **Clearly unsafe** means even the optimistic bound crosses a limit.
- **Metrics (2.8), per split and rule (+-6% and +-10%):** sample counts; per-element and extreme MAE, 99th percentile
  and maximum (V, loading points); unsafe = any violation or solver failure; unsafe-as-safe count, miss rate and
  rate among predicted safe with denominators; false rejections; precision and recall; guarded and point screens
  separately; latency for batches 1, 16, 128, 1,024 including feature building and range checks.
  Engineering targets (shown as pass or fail): voltage MAE <= 0.5 V and 99th percentile <= 2 V; loading MAE <= 2 points
  and 99th percentile <= 5 points.
- **Selection rule (development data only, before the test split is scored):** fewest guarded unsafe-as-safe on tune
  (both rules), then the lowest false-rejection rate, then the lowest batch latency. If the MLP does not beat ridge on
  the first two, ridge ships. The test, boundary-test and out-of-range splits are scored once, for every candidate.
- **End-to-end (2.3, 2.8):** (a) controller-style: 36 candidate actions (battery 9 levels x keep 1, 0.8, 0.6, 0.4)
  held over a 16-step window, 10 scenarios, on test dates; the cheapest verified-safe action by screen-then-verify
  against solve-everything and against the solver in cost order with early stop: time, solver states, same choice,
  disagreements, false rejections. (b) the whole-day fix tournament on test dates with and without skipping
  candidates the screen calls clearly unsafe; skipped candidates are verified offline to count false rejections.
  Battery-droop, switching and phase-move candidates are unsupported and always solved.
- **What counts as failure:** a missed target or a slower pipeline is reported as failed, not tuned away on test data.

### Addition 2, round 2: guard bands by predicted value (pre-registered 10 Oct 2026, after round 1 on development data, before any test state was scored)

- **What round 1 showed (benchmark street, development data only):** with one margin per extreme, no candidate let an
  unsafe tune state through, but the margins were set by a tail far from any limit. The MLP's lowest-voltage margin was
  14.2 V because deep under-voltage states (mostly battery charging, predicted below 0.93 pu) have errors up to 70 V,
  while near the limits (predicted 0.93-1.10 pu) the 99th-percentile error was 1-2 V. The screen called 37% (+-10%)
  and 87% (+-6%) of safe tune states risky; ridge and LightGBM called nearly all of them risky.
- **Change:** Mondrian split-conformal margins. For each extreme, the calibrate split is cut into 8 bins at the
  quantiles of the *predicted* value (edges saved in the manifest; the outer bins are open-ended); each bin gets its
  own one-sided margin at the same level 1 - 0.005/4, danger and optimistic sides as before; a bin too small for the
  level gets an infinite margin (always risky). The fitted models are not changed or refitted.
- **Selection:** the same rule on tune, over the three candidates with round 2 margins. Round 2 ships only if its
  guarded unsafe-as-safe count on tune is not higher than round 1's for the same model; otherwise round 1 ships.
- **Reporting:** round 1 and round 2 are both scored once on the test, boundary and out-of-range splits and both are
  reported. Validity holds within each bin under exchangeability; it is still not a certificate.

### Addition 2, round 3: solar layouts as part of the support (pre-registered 10 Oct 2026, before the fresh test set was generated)

- **What the test split showed (rural_weak_63, rounds 1-2, scored once):** the screen failed. Node-voltage MAE was
  1.9 V (target 0.5) and the guarded screen called 585 of 7,152 unsafe test states safe under +-6%. The error sat almost
  entirely in the unseen 75% adoption layout (3.7 V MAE) while the trained 100% layout in the same unseen months stayed at
  0.15 V (tune: 0.145 V). Every home's kWp was inside its trained range, so the per-feature box let a new combination
  through. These results stay in the report as the pre-registered outcome.
- **Change (support only; the models and the round 2 margins are unchanged):** the solar layout, which homes have panels
  and their sizes, must equal one of the layouts in the train split, as the phase map and the line layout already must.
  Any other layout is `unsupported` and goes to the solver.
- **Fresh test set:** the original test split has been looked at, so round 3 is scored on new families generated
  after this entry: the same test months (Mar, Jun, Sep, Dec) on days 3 and 27 (never used), with the same adoption
  levels (75%, which must now be refused, and 100%), held-out tap/mode combinations, boundary share and seeds derived
  from the new dates. The end-to-end runs use the 27th of each test month.
- **Reporting:** rounds 1-2 on the original test split with the per-feature box (as pre-registered); round 3 on the
  fresh split with the shipped support. A missed target or a slower pipeline is reported as such.

### Addition 2, result (run 10 Oct 2026, `python -m scripts.surrogate_evaluate`)

- **Selected (tune, both streets):** the MLP in rounds 1 and 2. Round 2 shipped by its rule on both streets; on the weak
  feeder it did not lower tune false rejections (21% vs 20%).
- **First test set (rounds 1-2, per-feature box):** the shipped round 2 MLP called unsafe states safe on the weak
  feeder (585 of 7,152 under +-6%, 437 of 3,109 under +-10%) and 38 of 9,462 on the benchmark (+-6%). It failed, almost
  entirely on the unseen 75% solar layout.
- **Fresh test set (round 3, shipped support):** 0 unsafe states called safe on either street under either rule,
  including near-limit states and the benchmark's unseen tap/mode combinations (none of the weak feeder's were
  accepted). The screen accepted about half the test states. On those, all four accuracy targets were met (MAE
  0.31/0.17 V, 99th percentile 1.89/1.00 V); over all states, 1 of 4. Out-of-range sets were refused in full except
  demand x4 (169 and 164 of 250).
- **Speed:** about 10x the solver per state at fixed power factor and about 180-240x under Volt/VAR (batch 1,024).
  - Controller-style search: 0.9x the solver in cost order, because no action was safe in 30 of 32 runs. There was one
    false rejection of the cheapest safe action, and zero unsafe actions passed.
  - Fix tournament: 1.02-1.04x, with no false rejections and the same best fix in all 16 runs.
- **Added during the run (a safety correction, not a tuning):** when nothing solved is safe, the candidates the screen
  skipped are solved too, so a "no safe action" verdict never rests on the screen.

### Addition 2, round 4: fixing the stated limitations (pre-registered 10 Oct 2026, before any round 4 state was generated)

Asked by the owner after the round 3 report. Every change below is decided now; the round 4 result is scored once on a
**new test set** (test months, days 7 and 17, never used), because the earlier test sets have been looked at.

1. **All five streets.** One model per street. Battery nodes per street: every node that was the street's
   highest-voltage node (catalog.worst_node) on any of 24 sampled days of 2025 (the 5th and 20th of each month):
   benchmark_250 {21, 26, 54, 65}, urban_short_160 {13, 21, 26, 58, 62, 65}, suburban_100 {25, 26, 31, 58, 65, 69},
   rural_long_100 {26, 58, 62, 65, 91}, rural_weak_63 {26, 31, 41, 58, 65, 69}. Battery power is an input per node.
2. **Solar layouts.** Every family draws a random layout: adoption uniform in 0.2-1.0, homes chosen at random, each
   panel 1.5-5 kWp. A quarter of families use the planning layouts (25/50/75/100%, spread as planning_street does).
   The exact-layout rule is replaced by a **novelty check**: the Mahalanobis distance of the standardised features in
   the principal components that hold 99% of the train variance; states farther than the 99.9th percentile of the
   calibrate split's distances are unsupported. The per-feature box stays.
3. **Fewer safe states sent to the solver.** Boundary share 0.4 (was 0.3). MLP 512/256/256, up to 400 epochs,
   patience 20 (round 1 hit the cap of 200).
4. **Margins centred on the limits.** Mondrian margins with bin edges at every decision limit +-1.5% (voltage: 0.90,
   0.94, 1.06, 1.10 pu) and +-10 points (100% loading), adjacent bins merged until each holds at least 1,000
   calibrate states.
5. **End-to-end.** No new mechanism: tighter margins should let more clearly unsafe candidates be skipped. The
   profile (10 Oct 2026) shows the tournament's largest costs are the phase optimiser (about 40 s, not a power flow)
   and Volt/VAR candidates (about 9 s each), so a large speed-up is not expected. A "no safe action" verdict still
   needs the solver.
6. **Cheapest options always verified.** In the controller-style search, the three cheapest actions are solved first
   whatever the screen says, then the screened-safe ones by cost, then the rest.
7. **Miss bound.** Every unsafe-as-safe count also gets a one-sided 95% Clopper-Pearson upper bound on the miss rate.
   States are correlated within a day, so the bound is optimistic; it is still not a guarantee, and every state is
   simulated.
8. **More outputs and layouts.** New outputs: voltage unbalance (VUF %), neutral current (A) and transformer power
   (reverse flow when negative), each with margins. The screen can apply a VUF limit when given one. Switched layouts:
   the first three switching candidates of each street (the ones the controller permits) are trained, as a layout
   input. Moved phase maps stay unsupported.

Candidates, selection rule (tune only), metrics and targets are otherwise as pre-registered for round 1. Rounds 1-3
stay in the record.

### Addition 2, round 4 result (run 10-11 Oct 2026, scored once on the round 4 test set, days 7 and 17)

- **Selected on tune:** MLP on benchmark_250, rural_long_100 and rural_weak_63; ridge on urban_short_160 and
  suburban_100. On those two the MLP and LightGBM let unsafe tune states through (4 and 34), and ridge calls about 99%
  of safe states risky, so the screen is safe but of little use there.
- **Unsafe called safe (as deployed, unseen months, +-6% / +-10%):**
  - benchmark: 0 / 0 (miss-rate bound below 2.3 and 6.8 per 10,000);
  - rural_weak: 0 / 1;
  - rural_long: 0 / 0 on the base states, plus 2 near-limit states under +-6%;
  - urban: 0 / 2;
  - suburban: 13 / 0.

  Round 3 had 0 on its two streets with a narrower support, so this **failed** the zero-miss record. The solver
  still verifies every choice, so no miss can become a recommendation.
- **States accepted:**

  | | Benchmark | Urban | Suburban | Rural long | Rural weak |
  |---|---|---|---|---|---|
  | All test states | 34% | 64% | 49% | 72% | 60% |
  | New random solar layouts | 10% | 55% | 33% | 60% | 47% |

  The novelty check is stricter than expected on the benchmark.
- **Safe states still sent to the solver (+-6%):** benchmark 90%, rural_long 54%, rural_weak 69%, urban and
  suburban about 99%. Worse than round 3 on the same streets: **failed** item 3.
- **Accuracy on accepted states:**

  | Street | Targets met | Node-voltage MAE |
  |---|---|---|
  | Benchmark | 2 of 4 | 0.48 V |
  | Rural long | 1 of 4 | 0.64 V |
  | Rural weak | 1 of 4 | 0.78 V |
  | Urban | 0 of 4 | about 3 V (ridge) |
  | Suburban | 0 of 4 | about 3 V (ridge) |

  Unbalance error is 0.08-0.25 points. Round 3 met 4 of 4 on its two streets.
- **Margins at the limits:**
  - +-6% upper limit: 3.0-8.6 V;
  - +-10% lower limit: up to 64 V on the weak feeder;
  - 100% transformer loading: 15-103 points.

  Item 4 **failed**: the bins are centred on the limits, but the errors there remained large.
- **End to end:**
  - Controller-style search: 0.85-0.90x the solver in cost order. Only 2 of 16 runs per street had any safe action.
    The same action as solving everything was chosen in all 80 runs (item 6 met: the cheapest actions are always
    solved). In 16 runs the controller's default battery node was not one of the declared nodes.
  - Fix tournament: 0.99-1.05x, the same best fix in all 40 runs, no false rejections.
- **Out of range:** every set was refused in full except demand x4 (160-200 of 250).
- **Speed per state:** screen about 0.2 ms; solver about 1.3 ms at fixed power factor and about 25 ms under Volt/VAR.
- **Reading:** widening the support (items 1, 2, 8) cost precision (items 3, 4) and the zero-miss record. Items 1, 6,
  7 and 8 are met; item 2 partly; items 3, 4 and 5 are not.
