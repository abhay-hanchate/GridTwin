# Assumptions and limitations

GridTwin labels every input as **observed**, **modeled** or **benchmark**. This page lists every assumption behind the numbers, so they can be checked.

## Grid

| Item | Value | Status |
| --- | --- | --- |
| Topology | SimBench `1-LV-rural2--0-sw`: 96 low-voltage buses, 99 houses, 95 lines, one 250 kVA transformer | Benchmark (German public dataset) |
| Line impedance | Low-voltage lines set to ACSR Rabbit: R = 0.5524 Ω/km (IS 398) | Adapted to Indian overhead lines |
| Line reactance | X = 0.35 Ω/km | Assumed typical overhead value |
| Transformer taps | ±2 steps of 2.5%, off-load: one setting holds for the whole day | Benchmark; Indian distribution transformers above 100 kVA have off-load taps (CEA minutes) |
| Household power factor | 0.95 | Assumed |

The benchmark's original cables are strong and short; with Indian household demand they show **no** voltage problems even with solar on every home. The overhead-line adaptation is what makes the grid representative of an Indian rural feeder. It is a benchmark adapted to Indian conditions, **not** a real Mathura feeder.

## Demand and voltage (observed)

- CEEW smart meters, Mathura, May–Dec 2019 (3-minute readings, CC0). kW = kWh per 3 minutes × 20, averaged to 15 minutes.
- Readings with voltage outside 150–300 V are treated as outages (missing), not zero demand.
- Meters with at least 70% coverage are kept (32 of 38). A simulated day uses only meters with a complete day (26 on 15 May 2019).
- 26 real profiles serve 99 houses, so each profile is reused about 4 times (random assignment, seed 42).
- **Upstream voltage** = median customer voltage across meters at each 15-minute step, applied at the supply side of the transformer. Customers sit downstream of the transformer, so their voltage is usually a little lower than the transformer's; the twin therefore, if anything, **understates** over-voltage. This is an approximation.

## Solar (modeled)

- pvlib PVWatts: panels tilted 25° facing south, SAPM cell temperature (close mount), −0.4%/°C, 14% system losses.
- Weather: Open-Meteo archive (ERA5/IFS). Radiation is the mean of the preceding hour, so the sun position is evaluated at mid-hour.
- 3 kW per participating home, matching the top PM Surya Ghar subsidy tier.

## Voltage limits

- Default band ±10% of 230 V (207–253 V), the tolerance a 2021 CEA panel favoured. The strict ±6% band (216–244 V) is the planned future tolerance.
- Maharashtra's regulator (MERC) allows +10% / −15%; limits are configurable in `engine/config.py`.

## Forecasting

- Solar inputs are **genuine day-ahead forecasts** (Open-Meteo Previous Runs API, `previous_day1`). Open-Meteo's historical-forecast and archive APIs return identical values for 2021 onward, so they are not used as forecast vs truth.
- Solar truth is modeled from ERA5 reanalysis, an independent proxy for measured output. Train 2024, test 2025.
- Demand model: trained May–Oct 2019, tested Nov–Dec 2019 on the average CEEW household.
- Demand features use lagged demand, calendar variables and temperature delayed by at least one day. Target-day archive weather is excluded to prevent hindsight leakage.
- P10–P90 bands are calibrated on held-out data (Nov–Dec 2024 for solar, Oct 2019 for demand) to about 80% coverage.
- Early warning for 2025 dates uses 2019 demand and voltage from the same calendar day as a labelled proxy, as no newer smart-meter data is public.
- The dashboard's 2025 comparison is an ERA5/PVWatts reference simulation, not measured panel production or measured 2025 feeder voltage.

## Not modeled in Round 1

- Thermal overloads: with Indian household demand, lines stay below 28% and the transformer below 45% loading, so overload scenarios are omitted.
- Three-phase unbalance (the model is balanced), feeder reconfiguration, and protection settings.
