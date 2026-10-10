# Battery saturation: a nearly full battery before the solar peak

Street `benchmark_250`, rule `pm10`, 2025-05-15, quarter hours 36 to 59, horizon 16. Battery 30.0 kW / 60.0 kWh at node 65, starting at 85%.

- Observations: simulated_observation: scenario 87 of the day's fan (not one of the three retained forecast scenarios) with the declared perturbations; not meter data.
- Perturbations: none.
- Tap: 0, fixed for the run (off-load tap changer).

| | Unsafe quarter hours |
|---|---|
| No control | 21 of 24 |
| Reactive battery rule, same observations | 21 of 24 |
| Receding-horizon controller | 0 of 24 |

Statuses: verified_safe 24. Curtailed 145.672 kWh; battery throughput 34.835 kWh (reactive rule 3.158 kWh); SoC 34% to 85%; switching operations 0; fallbacks 0.

No infeasible period.

Timing: total 54.91 s; per step p50 2.087 s, p95 4.859 s.

Only steps marked verified_safe passed every declared check in the real three-phase solver at the observed step. Observations are simulated; this is not a field test.
