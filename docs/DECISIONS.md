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
