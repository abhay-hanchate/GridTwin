# Forecast error: a cloud the forecast did not see

Street `benchmark_250`, rule `pm10`, 2025-05-15, quarter hours 36 to 71, horizon 16. Battery 30.0 kW / 60.0 kWh at node 65, starting at 50%.

- Observations: simulated_observation: scenario 87 of the day's fan (not one of the three retained forecast scenarios) with the declared perturbations; not meter data.
- Perturbations: unforecast cloud: half the sun from 11:30 to 13:30.
- Tap: 0, fixed for the run (off-load tap changer).

| | Unsafe quarter hours |
|---|---|
| No control | 13 of 36 |
| Reactive battery rule, same observations | 10 of 36 |
| Receding-horizon controller | 0 of 36 |

Statuses: verified_safe 36. Curtailed 61.536 kWh; battery throughput 51.972 kWh (reactive rule 25.263 kWh); SoC 10% to 56%; switching operations 0; fallbacks 0.

No infeasible period.

Timing: total 61.6 s; per step p50 1.421 s, p95 4.155 s.

Only steps marked verified_safe passed every declared check in the real three-phase solver at the observed step. Observations are simulated; this is not a field test.
