# Model card: demand forecast v2

**Status: not the model of record.** Gate G4 is not met (below), so demand v2 is not presented as an AI improvement
anywhere. The risk engine draws demand from observed analog days, and tomorrow's live demand comes from
`ml/live_dayahead.py`.

**Purpose.** Tomorrow's mean household demand (kW per home) for every 15 minutes, as P10, P50 and P90.

**Data.** CEEW smart meters (CC0): Mathura, 38 meters, May 2019 to 20 February 2021; Bareilly, 46 meters, May 2019
to October 2021. Outages (voltage below 150 V) and surges (above 300 V) are treated as missing, not as zero demand.
Details: `docs/generated/data_v2.md`.

**Method.** LightGBM quantile models on the log-ratio of demand to a baseline (the mean of the same quarter hour one
day and seven days before, the best baseline on the training data). Features use only what is known before the
target day: same-slot lags (1, 2, 7 and 14 days), a seven-day same-slot mean, yesterday's and the last week's mean
level, a trailing smooth of yesterday around the slot, season, weekday, UP holiday flags (today and yesterday), and
lagged and yesterday's mean temperature. For the time protocol, Bareilly's training-period rows are pooled in with a
district flag. An oracle variant adds the target day's ERA5 temperature as an upper bound on what a perfect
temperature forecast could add. The interval is widened each day by split-conformal scores from the 14 days before it (a
rolling window; the last 60 training days start it). The design was chosen on 2020 validation days before 2021 was
scored (`docs/DECISIONS.md`).

**Measured scores** (`ml/reports/demand_v2.json`, strict variant)

| Protocol | Steps | MAE (kW/home) | Skill vs baseline | P10 to P90 coverage |
|---|---|---|---|---|
| Time: train to 2020, test Mathura 2021 (51 winter days) | 4,896 | 0.0369 | +9.0% | 78.8% |
| Held-out district: train Mathura, test Bareilly | 78,116 | 0.0545 | +15.3% | 79.8% |

Gate G4 needs at least 10% skill and 78 to 82% coverage on the time protocol: **not met** (9.0%, 78.8%: coverage
inside the band, skill one point short). On the held-out district both conditions hold in every season.
The oracle-weather variant changes skill by under 1.5 points, so better temperature forecasts would not change this.

**Limitations and failure modes.**
- The Mathura 2021 file ends on 20 February 2021, so the time hold-out covers 51 winter days only.
- The rolling window needs 14 days of recent observed demand; until then the fixed training-period width is used.
- 26 to 46 meters per district: a small street sample, not a feeder.

**Monitoring.** None while it is not the model of record. If it is promoted later, it gets the same drift checks
as the solar model.
