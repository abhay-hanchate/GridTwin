# Solver failures

**Symptom.** Risk shows many unsafe quarter hours whose binding limit is `solver_failure`, or the convergence rate
drops *(API, Phase 8: `/api/v2/metrics`)*.

**Check.**
1. A non-converged step counts as unsafe on purpose: solver failure is never safe. The question is whether the
   network or the inputs are wrong, not how to hide the failure.
2. `python scripts/engine_sensitivity.py` *(Person A, task P3.4)* reports convergence per archetype and phase
   assignment; gate G5 needs at least 99% of steps.
3. After a data refresh, look for impossible upstream voltages or loads in `data/processed/v2/`.

**Fix.**
- Bad inputs: rebuild the data (`data_refresh.md`) and run again.
- An archetype fails gate G5: use the symmetric engine for that archetype and label its results
  "balanced approximation", as the plan prescribes.

**Who decides.** The engine owner (Person A).
