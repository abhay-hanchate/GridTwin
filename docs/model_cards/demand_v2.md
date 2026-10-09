# Model card: demand forecast v2

**Status: not the model of record.** Gate G4 failed (below), so Round 1's demand model stays in the API and demand
v2 is not presented as an AI improvement anywhere.

**Purpose.** Tomorrow's mean household demand (kW per home) for every 15 minutes, as P10, P50 and P90.

**Data.** CEEW smart meters (CC0): Mathura, 38 meters, May 2019 to 20 February 2021; Bareilly, 46 meters, May 2019
to October 2021. Outages (voltage below 150 V) and surges (above 300 V) are treated as missing, not as zero demand.
Details: `docs/generated/data_v2.md`.

**Method.** LightGBM quantile models on the log-ratio of demand to a baseline (the mean of the same quarter hour one
day and seven days before, the best baseline on the training data). Features use only what is known before the
target day: same-slot lags, a seven-day same-slot mean, season, weekday, UP holiday flags (today and yesterday) and
lagged temperature. An oracle variant adds the target day's ERA5 temperature as an upper bound on what a perfect
temperature forecast could add. The interval is widened by split-conformal scores from the last 60 days of the
training period.

**Measured scores** (`ml/reports/demand_v2.json`, strict variant)

| Protocol | Steps | MAE (kW/home) | Skill vs baseline | P10 to P90 coverage |
|---|---|---|---|---|
| Time: train Mathura to 2020, test Mathura 2021 (51 winter days) | 4,896 | 0.0372 | +8.4% | 83.3% |
| Held-out district: train Mathura, test Bareilly | 78,116 | 0.0570 | +11.6% | 76.6% |

Gate G4 needs at least 10% skill and 78 to 82% coverage on the time protocol: **failed** (8.4%, 83.3%).
The oracle-weather variant changes skill by under 1.5 points, so better temperature forecasts would not change this.

**Limitations and failure modes.**
- The Mathura 2021 file ends on 20 February 2021, so the time hold-out covers 51 winter days only.
- The interval uses one fixed calibration window; on Bareilly it under-covers (76.6%, monsoon 73.0%).
- 26 to 46 meters per district: a small street sample, not a feeder.

**Monitoring.** None while it is not the model of record. If it is promoted later, it gets the same drift checks
as the solar model.
