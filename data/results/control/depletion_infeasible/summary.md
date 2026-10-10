# Battery depletion and an infeasible evening on the weak street, with permitted switching

Street `rural_weak_63`, rule `pm10`, 2025-05-15, quarter hours 64 to 87, horizon 16. Battery 30.0 kW / 60.0 kWh at node 65, starting at 40%.

- Observations: simulated_observation: scenario 87 of the day's fan (not one of the three retained forecast scenarios) with the declared perturbations; not meter data.
- Perturbations: grid voltage sag of 0.10 pu from 18:00 to 21:30, evening demand 50% above the forecast from 18:00.
- Tap: 0, fixed for the run (off-load tap changer).

| | Unsafe quarter hours |
|---|---|
| No control | 8 of 24 |
| Reactive battery rule, same observations | 8 of 24 |
| Receding-horizon controller | 6 of 24 |

Statuses: verified_safe 18, unsafe_fallback 6. Curtailed 4.116 kWh; battery throughput 33.488 kWh (reactive rule 17.1 kWh); SoC 10% to 49%; switching operations 2; fallbacks 8.

Infeasible periods (no permitted action verified safe):
- 19:45 to 19:45 (1 steps, unsafe_fallback): planned action unsafe at the observed step: under-voltage 204.4 V < 207.0 V; search exhausted: none of 25 permitted actions was safe; least violation 1.82 V-equivalent
- 20:15 to 21:15 (5 steps, unsafe_fallback): planned action unsafe at the observed step: under-voltage 203.3 V < 207.0 V; search exhausted: none of 25 permitted actions was safe; least violation 0.32 V-equivalent

Timing: total 48.73 s; per step p50 1.715 s, p95 5.807 s.

Only steps marked verified_safe passed every declared check in the real three-phase solver at the observed step. Observations are simulated; this is not a field test.
