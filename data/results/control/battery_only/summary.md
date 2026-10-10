# Battery only, against the reactive rule (same observations as forecast_error)

Street `benchmark_250`, rule `pm10`, 2025-05-15, quarter hours 36 to 71, horizon 16. Battery 30.0 kW / 60.0 kWh at node 65, starting at 50%.

- Observations: simulated_observation: scenario 87 of the day's fan (not one of the three retained forecast scenarios) with the declared perturbations; not meter data.
- Perturbations: unforecast cloud: half the sun from 11:30 to 13:30.
- Tap: 0, fixed for the run (off-load tap changer).

| | Unsafe quarter hours |
|---|---|
| No control | 13 of 36 |
| Reactive battery rule, same observations | 10 of 36 |
| Receding-horizon controller | 9 of 36 |

Statuses: verified_safe 27, unsafe_fallback 9. Curtailed 0.0 kWh; battery throughput 88.888 kWh (reactive rule 25.263 kWh); SoC 29% to 90%; switching operations 0; fallbacks 12.

Infeasible periods (no permitted action verified safe):
- 09:45 to 11:15 (7 steps, unsafe_fallback): planned action unsafe at the observed step: over-voltage 256.3 V > 253.0 V; search exhausted: none of 5 permitted actions was safe; least violation 1.55 V-equivalent
- 13:45 to 14:00 (2 steps, unsafe_fallback): planned action unsafe at the observed step: over-voltage 257.3 V > 253.0 V; search exhausted: none of 5 permitted actions was safe; least violation 2.30 V-equivalent

Timing: total 56.67 s; per step p50 1.609 s, p95 2.134 s.

Only steps marked verified_safe passed every declared check in the real three-phase solver at the observed step. Observations are simulated; this is not a field test.
