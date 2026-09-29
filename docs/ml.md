# GridTwin ML model card and evaluation protocol

This document defines what the ML layer does, which data existed at prediction time, how it is evaluated, and which claims are safe to use in the hackathon pitch.

## Operational boundary

GridTwin's ML layer predicts uncertain solar and household demand. It does not declare a grid action safe. Every voltage warning and corrective action is evaluated by the deterministic pandapower engine.

The current 2025 early-warning demonstration is driven by the solar forecast. Demand and upstream voltage are same-calendar-day CEEW measurements from 2019 and are labelled `historical_proxy`. The separate demand model is an evaluated prototype, but it does not drive the 2025 warning.

This is not merely a weather-to-power formula: `ml/forecast.py` trains three LightGBM quantile
models. The audited dashboard comparison remains an offline historical backtest, while
`/api/live-forecast` and `/api/live-early-warning` now fetch keyless Open-Meteo weather and run
the frozen, versioned boosters for a future date. A live warning has no `actual`/reference case
until its target day has occurred. See
[`docs/finale_model_plan.md`](finale_model_plan.md) for the screened pretrained baseline and the
measured-PV dataset plan.

## Solar model

| Item | Definition |
| --- | --- |
| Target | kW per installed kW, derived from ERA5 reanalysis with pvlib/PVWatts |
| Input issue time | Open-Meteo Previous Runs `previous_day1`, issued the prior day |
| Features | forecast PV estimate, GHI, cloud cover, temperature, clear-sky GHI, hour and day of year |
| Train | January–October 2024 daylight hours |
| Calibration | November–December 2024 daylight hours |
| Test | 2025 daylight hours |
| Outputs | P10, P50 and P90 |

ERA5/PVWatts is an independent reference proxy. It is not measured output from rooftop panels. Feature importance is predictive rather than causal and is reported using both LightGBM gain and permutation importance on the untouched 2025 test period.

## Demand model

| Item | Definition |
| --- | --- |
| Target | mean household kW from CEEW Mathura meters |
| Features | yesterday/week ratio, 15-minute slot, weekday, yesterday's temperature and lagged temperature change |
| Train | May–September 2019 |
| Calibration | October 2019 |
| Test | November–December 2019 |
| Outputs | P10, P50 and P90 |

All temperature inputs are delayed by at least one day. The earlier target-day archive-temperature feature was removed because it would not be available when issuing a genuine day-ahead prediction.

## Leakage controls

1. Temporal splits are chronological and disjoint.
2. Solar inputs come from forecasts issued the previous day.
3. Solar truth comes from a different data product: ERA5 reanalysis processed through pvlib.
4. Demand features use only lagged measurements and calendar data.
5. Calibration data controls interval width; the test period never does.
6. Training is seeded and configured for deterministic LightGBM execution.

## Uncertainty

Three independent LightGBM quantile models estimate P10, P50 and P90. Quantiles are sorted after prediction to prevent crossing. A held-out calibration period scales the interval around P50 until it reaches approximately 80% marginal coverage.

This is an empirically calibrated interval, not a formal conditional-coverage guarantee. Coverage can deteriorate on unusual cloudy or high-ramp days, which is why `ml/evaluate_warning.py` reports a separate challenge segment.

## Warning evaluation

Run:

```bash
python -m ml.evaluate_warning
```

The evaluator:

1. keeps only 2025 dates with 96 complete forecast intervals and a complete same-calendar-day 2019 proxy;
2. scores cloudy/variable days using only P10–P90 width and P50 ramping available in the forecast;
3. selects the challenge day before inspecting its reference outcome;
4. runs P10, P50, P90 and ERA5/PVWatts reference solar through the same feeder;
5. reports unsafe-duration error, peak-voltage error, warning-start error, unsafe-day precision/recall and duration-envelope coverage.

For quick engineering checks, `--stride` or `--max-days` may be used, but any report generated with a cap must disclose its evaluated day count. Final claims should use the uncapped evaluation.

## Reproduction

```bash
python scripts/download_data.py
python scripts/build_data.py
python -m ml.forecast
python -m ml.explain
python -m ml.evaluate_warning
python scripts/precompute.py
pytest -q tests
```

Model files under `ml/models/` are generated and ignored. Small metrics, explainability and warning-evaluation reports are committed for auditability.

The three solar boosters and `solar_manifest.json` are exceptions: they are versioned so a
deployment can perform live inference without retraining at request time. Demand boosters remain
generated locally because live warnings still use a labelled historical demand proxy.

## Known limitations

- The feeder is an adapted SimBench benchmark, not a surveyed Mathura feeder.
- Solar reference output is modelled from ERA5 rather than measured at panels.
- The 2025 warning uses 2019 demand and upstream-voltage proxies.
- The grid model is balanced three-phase and omits protection behaviour.
- Prediction intervals provide marginal rather than per-condition coverage.
- A model trained at Mathura should not be presented as calibrated for another climate or feeder.

## Permitted pitch wording

Use:

> The AI estimates tomorrow's solar uncertainty from weather forecasts that existed the previous day. The grid simulator converts that uncertainty into voltage risk. The comparison uses an independent ERA5/PVWatts reference simulation, while demand and incoming voltage use a labelled 2019 historical proxy. Physics—not ML—decides whether an action is safe.

Do not say that the project measured rooftop production or observed seven unsafe hours on a real feeder in 2025. Do not say the demand model drives the warning until a live or genuinely forecast demand input is integrated.

Do not say that an external foundation model is already integrated. The screened Chronos-2
checkpoint is a proposed finale baseline; the implemented model is the local LightGBM ensemble.
