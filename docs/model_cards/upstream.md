# Model card: upstream (grid-side) voltage

**Status: in use** for the demo dates (`engine.upstream.UpstreamModel`, winner `lgbm_day_quantiles`). For a real
"tomorrow" the API uses the live day-ahead voltage forecast instead (`ml.live_dayahead`, see `demand_v2.md` and
`docs/DECISIONS.md`, "Live day-ahead demand and voltage"). Owner: Person A.

**Purpose.** Whole-day paths of the voltage arriving at the transformer, in per unit of 230 V, 96 quarter hours per
path. The scenario generator replays these paths, so per-slot quantiles alone would not be enough.

**Data.** CEEW smart meters (CC0), May 2019 to 2021: fitted on Mathura, with Bareilly as the held-out district. The
median customer voltage across
meters per 15 minutes, taken as the supply-side voltage. Customers sit downstream of the transformer, so this
approximation, if anything, understates over-voltage. A day is usable with at least 80 of 96 valid slots and a
usable previous day.

**Method.** LightGBM quantile regression (9 levels) of the day mean on yesterday's mean, maximum and spread and the
calendar; a day mean is drawn by inverting the interpolated quantiles, and the intra-day shape is a same-month
training day's deviation from its own mean. Only the target date and yesterday's observed mean are used; nothing
from the target day. Chosen by a bake-off written down before the run (`docs/DECISIONS.md`, "Upstream voltage").

**Measured scores** (`ml/reports/upstream_v2.json`, `data/results/bakeoff_upstream.json`; 200 paths per day, seed 0)

| Protocol | Days | Day-maximum 10-90% coverage | CRPS of the day maximum (pu) | Per-slot 80% coverage |
|---|---|---|---|---|
| Time: fit Mathura before 2021, test Mathura 2021 | 50 | 82.0% | 0.00536 | 59.8% |
| Held-out district: fit Mathura, test Bareilly | 875 | 69.3% | 0.00970 | 69.6% |

The rule asked for 70 to 90% day-maximum coverage on both protocols. No candidate met it; this one won through the
fallback branch (closest to 80% in its worse protocol, and the lowest CRPS on both). **Recorded as a miss:** on the
held-out district the interval is slightly too narrow. The plan's own hypothesis (AR(1) plus a daily shape) lost on
both coverage and CRPS.

**Limitations and failure modes.**
- The Mathura 2021 test has 50 usable days (January and February), so its coverage is uncertain by several points.
- Per-slot coverage (59.8% and 69.6%) is well below 80%: the paths are right about the day's peak more often than
  about each quarter hour.
- For the demo dates (2025), "yesterday" is a proxy: the day before the same calendar date of 2019, else of 2020 or
  2021, whichever the Mathura record has (`backend/v2/compute.py::yesterday_upstream_mean`, `PROXY_YEARS`); failing
  that, the mean of that month, then of the whole record. It is never missing. The API labels it "modeled (proxy)".
- Until 10 Oct 2026 the app read an older Mathura file that missed all of 2020, so March and April had no proxy at
  all (a missing value reached the model) and March came out 8.1 V off the record. The app now reads the full record
  (`data/processed/v2/*_mathura.parquet`); the generated grid voltage is within 3.6 V of the real monthly mean in
  every month, with daily-shape correlation 0.99 to 1.00 (audit of 10 Oct 2026; this checks the pipeline against the
  data it learned from, not forecast skill).
- The customer median stands in for the transformer's secondary voltage; it has not been checked against a
  transformer measurement.

**Monitoring.** No live grid-voltage measurements exist, so the model cannot be checked against reality day by day.
The end-to-end check is gate G8 (risk reliability), which replays held-out days through the whole chain.
