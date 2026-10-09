# Live day-ahead demand and voltage, anchored to live UP state demand

Status: approved in conversation on 9 Oct 2026 (option "Yes, build it"). Owner: Person B. The voltage part overlaps
Person A's task P2.5 (upstream-voltage model); A is told, and this model stays in `ml/` so `engine/upstream.py` is
untouched.

## Problem

Demand and voltage forecasts must be for **tomorrow, from today's date**, not replays of 2019 or 2025. The CEEW
household meters end in 2021 and no public live household meter feed exists (searched: CEEW, Prayas ESMI to 2019,
IIT Bombay 2016-18, Grid-India daily reports whose host no longer resolves). A live signal does exist: the Uttar
Pradesh load dispatch centre (UPSLDC) publishes the state's demand every 3 minutes for **yesterday and today**
(`https://www.upsldc.org/assets/dataset/scada-load-graph.json`).

## Evidence (measured 9 Oct 2026, 2019-2021, daily values, 31-day centred mean removed for "swings")

| | Mathura | Bareilly |
|---|---|---|
| UP daily demand vs household daily demand, level | +0.89 | +0.90 |
| UP yesterday's swing vs household swing today | +0.53 | +0.60 |
| UP yesterday's swing vs grid-voltage swing today | -0.38 | -0.54 |

History of UP daily energy for training: Zenodo record 14983362 (Grid-India reports, CC BY 4.0), 2013 to April 2024.

## Design

1. **Live UP feed** (`ml/up_demand.py`): fetch the load graph, turn each day into daily energy (MU) and a
   15-minute profile; `scripts/record_up_demand.py` stores every fetch in `data/live/up_demand.parquet`
   (gitignored). One fetch a day is enough because each fetch holds all of yesterday.
2. **Anchor feature, scale-free:** `up_ratio = E(d-1) / mean(E(d-8 .. d-2))`, the UP energy of the last full day
   against the week before it. A ratio cancels any scale difference between Zenodo history and the live feed.
   Until eight days are recorded live, the forecast runs without the anchor and says so.
3. **Models** (`ml/live_dayahead.py`), one for household demand (mean kW per home) and one for grid voltage (V),
   per 15 minutes, P10/P50/P90. Features known the evening before: slot, weekday, day of year (sine, cosine),
   UP holiday flags (day and next day), tomorrow's temperature (training uses ERA5 actual temperature as a stand-in
   for the forecast; live uses the Open-Meteo forecast), and `up_ratio`. **No household lags**, because there are no
   live meters. LightGBM quantile regression; districts pooled with a district flag.
4. **Intervals:** split-conformal per season (Mondrian), so winter and summer each get their own width.
5. **Live output:** `live_forecast(district, date)` returns 96 steps for tomorrow with provenance
   "modeled: household pattern from CEEW meters 2019-2021, level from live UPSLDC state demand".

## Evaluation (pre-registered in docs/DECISIONS.md before running)

- Walk-forward by month over every month with data after the first 6 months: train on everything before the
  month (both districts), test the month. Plus a held-out district run (train Mathura, test Bareilly).
- Baselines, all without household lags: climatology (mean by district, month, weekday type, slot) and the same
  model without `up_ratio` (pattern only).
- Adopt the live-anchored model if MAE is at least 10% below climatology and below pattern-only, with P10-P90
  coverage 78-82% overall and 70-90% in every season. Otherwise report the true numbers.

## Out of scope here

Solar seasonal intervals, the lag-based demand gate G4, Chronos-2, Karnataka calibration: separate fixes, done after
this one, each with its own pre-registered test.
