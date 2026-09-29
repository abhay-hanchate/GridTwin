# Solar forecasting model selection and finale plan

This note separates the model that GridTwin runs today from external models that may be
benchmarked in the finale. An external checkpoint is not part of GridTwin until its predictions
are reproduced on GridTwin's held-out test period and it passes the warning-level evaluation.

## Decision

- **Current round:** keep the implemented LightGBM quantile ensemble. It is small, explainable,
  trained locally, and already evaluated against persistence and the physics-only baseline.
- **Pretrained finale baseline:** benchmark [`amazon/chronos-2`](https://huggingface.co/amazon/chronos-2).
  It is an Apache-2.0, 120M-parameter time-series foundation model that accepts known-future
  covariates and directly returns quantiles. This matches GridTwin's need to condition a 24-hour
  PV forecast on tomorrow's weather and emit P10/P50/P90.
- **Own finale model:** train a compact weather-conditioned quantile forecaster after assembling
  measured PV generation. Start with a Temporal Fusion Transformer or a smaller
  decomposition/Transformer design, but retain LightGBM and Chronos-2 as required baselines.

Chronos-2 is a candidate, not an integrated dependency and not a Mathura-calibrated solar model.
It still needs historical target values. A weather API alone cannot supply those targets.

## What exists now

| Stage | Current implementation | Status |
| --- | --- | --- |
| Weather input | Open-Meteo Previous Runs, `previous_day1` | Historical day-ahead forecasts; no API key |
| PV conversion feature | pvlib/PVWatts from forecast weather | Physics-derived feature, not the final prediction |
| Solar forecast | Three LightGBM quantile regressors | Implemented: P10, P50 and P90 |
| Solar reference | ERA5 reanalysis converted with pvlib | Independent synthetic proxy, not measured PV |
| Demand and incoming voltage | Same-calendar-day 2019 CEEW Mathura readings | Historical proxies in the 2025 warning |
| Grid risk | pandapower simulation | Deterministic voltage calculation |

The current demonstration is an offline historical backtest. It reads the committed 2025
forecast artifact; it does not call a live weather endpoint whenever the dashboard is opened.
The production path will fetch tomorrow's weather, build the same feature schema, load a frozen
model version, predict P10/P50/P90, and then run all three cases through pandapower.

## F13 input provenance

F13 uses several datasets for different roles; they must not be described as one dataset.

| Quantity | Source used in F13 | Why it is used |
| --- | --- | --- |
| Predicted solar | LightGBM output from genuine prior-day Open-Meteo weather forecasts | Day-ahead uncertainty entering the grid |
| Reference solar | ERA5 weather converted to PV output using pvlib | Backtest reference proxy |
| Household load | CEEW Mathura, same month/day in 2019 | Historical demand proxy |
| Upstream voltage | CEEW Mathura, same month/day in 2019 | Historical supply-voltage proxy |
| Feeder topology | Adapted SimBench feeder | Benchmark network because a surveyed Mathura feeder is unavailable |

Therefore, the answer to “CEEW or weather?” is **both, for different variables**. Weather drives
the solar forecast. CEEW supplies load and upstream voltage to the power-flow simulation. CEEW
does not provide rooftop-PV generation labels for this project.

## External model screening

| Candidate | Evidence | Decision |
| --- | --- | --- |
| [Chronos-2](https://huggingface.co/amazon/chronos-2) | Future covariates, multivariate input and quantile output; Apache-2.0; maintained inference package | **Benchmark in finale** |
| [Granite TTM R3](https://huggingface.co/ibm-granite/granite-timeseries-ttm-r3) | Very small CPU-friendly model, exogenous variables and multi-quantile head | Secondary low-compute baseline; recipes were still marked forthcoming when screened |
| [Suncast](https://huggingface.co/ryukkt62/Suncast) | Runnable random-forest checkpoint trained on GFS/CERES | Reject for Mathura: its model card limits use to mainland China and a coarse grid |
| [Open Climate Fix PVNet](https://github.com/openclimatefix/pvnet) | Serious multimodal PV forecasting code using NWP, satellite imagery and recent generation | Architecture reference, not a drop-in Indian checkpoint; substantially heavier data pipeline |
| [OpenSTEF](https://github.com/OpenSTEF/openstef) | Maintained LF Energy forecasting and evaluation framework | Useful tooling/reference, not a pretrained Mathura PV model |
| [SEEDTrans](https://github.com/AI4SClab/SEEDTrans) | Day-ahead PV architecture with weather variables and decomposition | Research reference only; the screened root contained no released checkpoint or license file |

## Dataset decision

### Best immediately useful development data

1. [`EDS-lab/pv-generation`](https://huggingface.co/datasets/EDS-lab/pv-generation) — a harmonized
   PV dataset containing generation, system metadata and weather. The Hub card reports 871 MB and
   a BSD-3-Clause license, but access is gated and must be approved before use.
2. [`openclimatefix/uk_pv`](https://huggingface.co/datasets/openclimatefix/uk_pv) — measured AC-side
   generation from more than 30,000 PV systems, 2010–2025, with system capacity/orientation
   metadata under CC BY 4.0. Join it to issue-time NWP weather for training.
3. GridTwin's Open-Meteo Previous Runs and ERA5/pvlib data — useful for pipeline development,
   pretraining and controlled ablations, but synthetic PV must remain labelled as a proxy.

### Data required for a defensible Mathura model

Collect inverter or revenue-meter PV output at 5–15 minute resolution from Mathura/UP systems,
including capacity, tilt, azimuth, curtailment/outage flags and timestamps. Join each target with
the weather forecast that was actually available before the forecast issue time. Three months can
support a pilot fine-tune; six to twelve months is preferred to cover monsoon and winter regimes.

Minimum training schema:

```text
site_id, timestamp, pv_kw, capacity_kwp, tilt_deg, azimuth_deg,
forecast_issue_time, forecast_ghi, forecast_dni, forecast_diffuse,
forecast_cloud_cover, forecast_temperature, forecast_wind,
actual_or_reanalysis_weather, curtailment_flag, outage_flag, quality_flag
```

CEEW demand and voltage remain valuable for the digital twin, but they cannot replace `pv_kw` as
the target for a measured-PV forecasting model.

## Finale implementation gates

1. Create leakage-safe, issue-time-aligned train/calibration/test splits by date and site.
2. Normalize generation as kW/kWp and retain site metadata as static covariates.
3. Evaluate persistence, pvlib, current LightGBM, zero-shot Chronos-2 and the new model on exactly
   the same held-out dates.
4. Report MAE/nMAE, pinball loss, P10–P90 coverage/width, ramp-event error, cloudy-day error and
   the downstream voltage-warning metrics.
5. Promote a model only if it improves forecast skill and warning quality. A larger neural model
   is not an improvement by itself.
6. Freeze the checkpoint, feature schema, data hashes and model card; then integrate live
   Open-Meteo input with cached fallback and issue-time logging.

## Permitted claim

> GridTwin currently runs a locally trained LightGBM probabilistic solar model. For the finale we
> will benchmark the open Chronos-2 checkpoint, then train or fine-tune a weather-conditioned model
> on measured PV generation. CEEW Mathura data supplies demand and voltage, not solar labels.

Do not say that Chronos-2 is already integrated, trained on Mathura, or validated for Indian PV.

