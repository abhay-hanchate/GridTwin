# Changelog

## Unreleased

- **New dashboard.** A light design with new type (Bricolage Grotesque, Figtree, JetBrains Mono) and colours that
  each mean one thing: phases A, B, C and the neutral; fine, close to the limit, too high, too low; solar and the
  grid's own voltage. An overview and five numbered steps (Tomorrow, Fixes, Planning, Try a change, Proof), each
  ending with its labels explained and the next step.
- **The street, animated.** `GET /street` returns the street as a schematic with each home on its phase and the
  design day quarter hour by quarter hour. The dashboard plays it: power flows along A, B, C and the neutral (the
  wire flows are estimated from each home's net power; the voltages are the solver's), homes change colour with
  their voltage, and any fix can be watched with and without.
- **What causes the risk.** `/risk` also runs the day with every panel switched off. What stays unsafe is the grid's
  own voltage; the rest is rooftop solar. This is why a November night can be unsafe with no sun at all.
- **Real days instead of demo days.** The dashboard opens on the real tomorrow (live forecast) and a calendar gives
  any day of 2025 (`GET /calendar`). The evening run also computes tomorrow, so it opens instantly.
- **Fixes explained.** Every fix type says what it is, how it helps, who does it and what it costs.
- **Planning on the map.** Room per phase, a connection check by clicking the street, and meter sites, on the street
  schematic.
- **What-if compares with today's street.** The result used to compare the changed street with the changed street
  (identical when no fix was chosen); it now returns `today` as the baseline and shows the changes alone when fixes
  are added.
- **A quarter hour the power flow cannot solve is `null`, not an error.** Overloads that make the power flow fail
  (for example many evening EV chargers) used to break the response; the API now writes `null`, the dashboard shows
  those homes grey, and the engine keeps counting them as unsafe.
- **Planning:** three tools that were built but not shown are now in the API and on the Planning page: where to
  put a smart meter first (`/meter-sites`), how much standard Volt/VAR lowers the peak if the wires' resistance or
  reactance differ (`/rx-map`), and the five street types ranked by how much of their safe room connected solar
  already uses (`/transformers`). The evening precompute now covers headroom and hosting capacity for every street
  type and writes `data/results/planning_<street>.json`.
- **Demand v2, second run:** extra lag features, both districts' training rows, and a rolling 14-day conformal
  window, chosen on 2020 validation before 2021 was scored. Gate G4 is still not met: skill 9.0% (needs 10%),
  coverage 78.8% (now inside 78 to 82%). On the held-out district: 15.3% and 79.8%.
- The benchmark street's label and the G3 gate name no longer refer to the first release.
- **Grid-voltage history fixed (F-0).** The app read an older Mathura file that missed all of 2020, so March and
  April had no "yesterday's voltage" at all (a missing value reached the model) and March came out 8.1 V off the
  record. The app now reads the full record (three small files are committed), and the proxy is never missing. Every
  precomputed number changed with it.
- **Switching fix drawn on the right wires (F1).** A switching fix re-numbers the street's wires; the animation drew
  the switched flows on the original wire numbers. Each run now carries its own wire ends, the opened wire is drawn
  grey and still and the closed tie dashed.
- **The pages show the recalibrated risk chances (F2).** Gate G8 passes on the recalibrated chances, but the pages
  drew the raw ones. Where the map was fitted (benchmark street, no fix) the chart, the level, the first watch and
  act times and the expected hours now all use the recalibrated chances; elsewhere the raw ones, with a note saying
  so. Decision in `docs/DECISIONS.md`.
- **Days with no forecast are refused at once (F6).** A date outside the 2025 archive and outside today to seven days
  ahead is a 404 with the valid ranges, instead of a job that fails later; a live-forecast outage is a 503.
- **One error shape everywhere (F7).** The removed `/api/...` routes answer in the v2 error shape.
- **Hindi has its own font (F9).** Noto Sans Devanagari is bundled; English pages never download it.
- **Solar gates re-run (F3).** G2 and G3 were re-run from the downloaded weather files with identical scores, and the
  first model's 0.0396 is now recomputed from its committed table instead of typed.
- **UP demand recorded every evening (F5).** The evening workflow runs the recorder and keeps its record between
  runs; the Tomorrow page says how many days are recorded while the forecast runs pattern only.
- **Wire-flow estimate explained (F8).** The player and the Proof page list what the estimated flows leave out.
- Housekeeping (F10): the `charts` chunk is now `vendor`; 43 unused translation keys are gone; `nightly --prune`
  removes cached results the index no longer names. Two stale test fixtures left by the merge are fixed.

## Since v2.0.0: Round 1 removed (plan task P10.12)

- The dashboard is v2 only; no build switch (`VITE_DASHBOARD` is gone). The Round 1 screens and the chart library
  they used (recharts) are removed, so the first page load is smaller.
- The Round 1 API routes (`/api/run`, `/api/actions`, `/api/grid`, ...) are removed; `backend/main.py` serves API v2
  under `/api/v2` and the dashboard. An unknown `/api/...` path is a JSON 404, never the dashboard page.
- Removed the Round 1 fix, ranking, scenario, simulation and hosting-capacity modules (`engine/actions.py`,
  `ranking.py`, `scenarios.py`, `simulate.py`, `hosting_capacity.py`), the Round 1 inverter loop, the Round 1
  early warning and its evaluation (`ml/early_warning.py`, `ml/evaluate_warning.py`), the feature-importance report
  (`ml/explain.py`), `scripts/precompute.py` and the results only those routes served. v2 keeps the Round 1 power
  flow (`engine/grid.py`, `engine/powerflow.py`), the Round 1 forecasting base (`ml/forecast.py`,
  `ml/live_forecast.py`) and the Round 1 solar model, which v2 builds on.
- Round 1 documents moved to `docs/round1/`. The release tag `v2.0.0` still contains everything removed here.

## v2.0.0

Round 1 answered "is this street unsafe on a past day, and which fix works?". Version 2 answers it **for tomorrow,
with uncertainty**, adds planning, and states how far each answer can be trusted. The plan is
[docs/superpowers/plans/2026-10-09-gridtwin-v2-complete-plan.md](docs/superpowers/plans/2026-10-09-gridtwin-v2-complete-plan.md);
every method choice and its result is in [docs/DECISIONS.md](docs/DECISIONS.md); every gate is in
[data/results/results.json](data/results/results.json).

### New

- **Tomorrow's risk**: chance of an unsafe step every 15 minutes from 100 correlated scenarios, expected unsafe hours
  with a P10 to P90 range, and an OK / WATCH / ACT level.
- **Live day-ahead demand and grid voltage** for the real next day, anchored to live UP state demand when it is
  recorded.
- **Phase-aware engine**: single-phase homes on phases A, B and C with the neutral, on power-grid-model's batch solver,
  cross-checked against pandapower.
- **Fix tournament** with phase moves, per-home day-ahead export limits, radial-safe switching and a battery size
  sweep, and an honest verdict naming the binding limit, the closest option and what it would still need.
- **Planning**: headroom per phase and place beside the flat state caps, probabilistic hosting capacity, and a
  connection check.
- **Try a change**: any mix of registered changes and fixes, from a catalogue the API describes.
- **Upstream (grid-side) voltage model** and a **joint scenario generator**.
- **API v2** (`/api/v2`), an offline mode that serves precomputed results, and a printable evening report.
- **Dashboard v2**: five areas, English and Hindi, phone layout, Lighthouse accessibility 100.
- **Operations**: Docker image, evening precompute and drift monitor, honesty and security tests, licence register,
  model cards, runbooks, utility onboarding from CSV.

### Improved (measured)

| | Round 1 | v2 |
| --- | --- | --- |
| Meter data | 1 file, Mathura | 6 files, Mathura and Bareilly |
| Solar forecast error (MAE, kW per kW) | 0.0396 | 0.0329 (gate G3) |
| Solar range in winter, share of real values inside | — (74.9% in the first v2 version, one width for all seasons) | 79.5% (per-season widths) |
| Tomorrow's demand and voltage | a usual-value guess | 46% (demand) and 37% (voltage) better than that guess |
| Engine time for one day | 10.49 s (pandapower, latest run) | 0.026 s, 0.001 V apart (gate G1) |
| Smart inverters | fixed power factor 0.9 | IEEE 1547 Volt/VAR and Volt/Watt |
| Peak voltage on the reference day | 263.1 V (balanced model, understated) | 268.9 V (homes on single phases) |

### Did not work (kept as results)

- **Demand v2** reached 8.4% skill against the best simple method; gate G4 needed 10%. Round 1's demand model stays.
- **Risk reliability (gate G8)** fails: under ±10% the recalibrated chances are only slightly better than the
  historical average; under the UP ±6% rule almost every step is unsafe, so nothing beats "always unsafe".
- **Chronos-2** was 2.8% better than LightGBM (5% needed), and worse with only the data that exists live. Not adopted.
- **Upstream voltage** covers the day's peak 82% of the time in Mathura but 69.3% in Bareilly: slightly too narrow.
- **Gate G7** (solar yield against a measured plant) was not run: the data needs an IEEE DataPort login.
- **Gate G6** is conditional: Open-Meteo's free API is for non-commercial use.

### Performance (plan section 12, measured 10 Oct 2026 on the development laptop)

| Operation | Measured | Budget |
| --- | --- | --- |
| Balanced and unbalanced day, power flow | within budget (`pytest -m perf`) | 0.1 s, 0.3 s |
| Volt/VAR day, unbalanced | 2.9 s | 3 s |
| Risk run, 100 scenarios | 13.3 s | 30 s |
| Fix tournament, ±10%, not cached | 148.5 s | 150 s |
| Fix tournament, UP ±6%, not cached | **177 s, over** | 150 s |
| Hosting capacity as served (two runs of 30 draws), not cached | **181 s, over** | 120 s |
| API answer from precomputed results, p95 | 12 ms | 300 ms |

The two over-budget computations are precomputed for the demo days, so the dashboard serves them in milliseconds;
a new day or rule waits for them.

### Changed

- CI runs on Python 3.12 and 3.13 (the pinned power-grid-model and networkx need 3.12 or later).
- The v2 dashboard is built with `VITE_DASHBOARD=v2`; the Round 1 dashboard and API stay until the legacy path is
  removed after this tag.
