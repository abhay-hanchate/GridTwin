# Model card: joint scenario generator

**Status: in use** behind `/risk`, `/fixes`, `/headroom`, `/hosting` and `/whatif` (`engine.scenario_gen`, feature
B5). Owner: Person A.

**Purpose.** Tomorrow as many plausible days (100 by default, seed 42), each with every home's demand, rooftop solar
per kW and the grid-side voltage for all 96 quarter hours. The risk engine counts how many of them are unsafe at each
step; the fix tournament picks a robust set (median sun, P90 grid voltage, P90 sun) from them.

**Inputs.** Three day-ahead forecasts as P10/P50/P90 per quarter hour: solar (solar v2, `solar_v2.md`), demand
(climatology by month and day type for the demo dates; the live forecast for a real tomorrow) and grid voltage
(`upstream.md`, or the live forecast). Each home's demand shape comes from analog days of the CEEW meters.

**Method.** A Gaussian copula couples three day-level anomalies (solar clearness, demand level, grid-voltage
offset) using their rank correlation in the CEEW years (2019 to 2021): sunny days differ from cloudy ones in grid
voltage, and heavy-demand days pull the voltage down. Within a day the solar error is a shared day-level draw plus
an hour-to-hour AR(1) wobble; the split (70% of the variance shared across the day, persistence 0.9) is a setting in
the code, not fitted. Each draw maps to the forecast quantiles, so every scenario stays inside what the forecasts
say is plausible.

**Measured scores.** The generator has no score of its own; it is judged through the risk it produces. Gate G8
(`data/results/results.json`), on 100 held-out 2021 days of both districts (Mathura 40 days, January and February;
Bareilly 60 days, January to October), pre-registered in `docs/DECISIONS.md` ("Gate G8 on both districts"):

| Rule | Brier skill vs base rate, pooled (raw) | After isotonic recalibration | Bareilly | Mathura |
|---|---|---|---|---|
| ±10% (`pm10`) | +0.50 | **+0.51** | +0.41 | +0.009 |
| UP ±6% (`up_2005`) | +0.44 | **+0.45** | +0.36 | -3.90 |

G8 passes on both rules. Mathura alone under ±6% is below the base rate: 99.7% of its January and February steps were
unsafe, so "always unsafe" is nearly unbeatable there. The pooled reference is one rate for both districts, so part of
the pooled skill comes from telling the districts apart; Bareilly alone passes too. Since 10 Oct 2026 the dashboard
shows the recalibrated chances where the map was fitted (benchmark street, no fix) and the raw ones elsewhere
(`docs/DECISIONS.md`, "Which risk chances users see").

**Limitations and failure modes.**
- The copula models climatological anomalies of the meter years. Forecast archives do not overlap those years, so
  the correlation of forecast errors cannot be estimated; the Proof page says so.
- Mathura's held-out 2021 window covers January and February only (its file ends on 20 February 2021), and its
  voltage sits about 5 V above the training years. Bareilly's covers January to October.
- 100 scenarios give probabilities in steps of 1%; rare events below that are invisible.

**Monitoring.** Gate G8 is rerun with `python -m scripts.run_reliability --rule <rule>` and
`python -m scripts.calibrate_risk`; `results.json` records the outcome.
