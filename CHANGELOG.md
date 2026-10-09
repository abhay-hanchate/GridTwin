# Changelog

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
| Engine time for one day | 7.79 s (pandapower) | 0.012 s, 0.001 V apart (gate G1) |
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
