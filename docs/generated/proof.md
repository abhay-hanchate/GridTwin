# Proof: gates and headline results

Generated 2026-10-09T19:57 UTC from `data/results/results.json` (git d465a7a). Do not edit by hand: run `python -m scripts.evaluate`.

| Gate | What | Status | Measured | Threshold |
| --- | --- | --- | --- | --- |
| G1 | Engine parity with pandapower | **pass** | {"max_voltage_diff_pct": 0.0005, "max_voltage_diff_v": 0.001, "max_trafo_loading_diff_pts": 0.0, "day_seconds_pgm": 0.026, "day_seconds_pandapower": 10.49, "speedup": 403.6} | max voltage difference <= 0.1% and at least 10x faster |
| G2 | Weather-model availability | **pass** | {"models_used": ["gfs_global", "icon_global", "gem_global", "meteofrance_arpege_world", "ecmwf_ifs025"], "dropped": ["jma_gsm", "ukmo_global_deterministic_10km"]} | >= 95% non-null hours from the first valid hour and in the test year, per model |
| G3 | Solar v2 beats Round 1 | **pass** | {"mae_p50": 0.0329, "round1_mae": 0.0396, "coverage_80": 0.794, "wis": 0.0214} | MAE below 0.0396 kW/kWp on the identical 2025 daylight mask |
| G4 | Demand v2 skill and coverage | **fail** | {"skill_vs_best_baseline": 0.084, "coverage_80": 0.833} | skill >= 10% against the best baseline and coverage 78-82% (strict variant, Mathura 2021) |
| G5 | Unbalanced engine converges; zero-sequence sensitivity | **pass** | {"peak_range_v": [268.4, 272.6], "balanced_peak_v": 263.1, "phase_modes_peak_v": {"random": 270.5, "round_robin": 268.9, "all_a": 294.1}} | >= 99% of steps converge for every phase mode and r0/x0 ratio 2-4 |
| G6 | Data and API licences permit the use | **conditional** | Open-Meteo free API: non-commercial use only | licences permit the intended use |
| G7 | Measured-plant yield calibration | **not_run** | outcome (b): IEEE DataPort needs a login | plant file readable with stated capacity |
| G8 | Risk probabilities are reliable | **fail** | {"pm10": {"brier": 0.1317, "brier_base_rate": 0.1331, "brier_skill": 0.01, "days": 40, "observed_unsafe_share": 0.8419, "unsafe_hours_predicted": 16.95, "unsafe_hours_observed": 20.21, "brier_skill_calibrated": 0.023, "calibrated_reliable": true}, "up_2005": {"brier": 0.0076, "brier_base_rate": 0.0026, "brier_skill": -1.928, "days": 40, "observed_unsafe_share": 0.9974, "unsafe_hours_predicted": 23.35, "unsafe_hours_observed": 23.94, "brier_skill_calibrated": -5.46, "calibrated_reliable": false}} | Brier skill > 0 against the base rate, on every rule |

## Notes

- **G4**: Failed and kept failed by the owner: no AI-improvement claim for demand.
- **G6**: Demo and research fit; a DISCOM deployment needs a paid plan or another licensed source.
- **G7**: PV keeps the 14% system-loss assumption: yield not calibrated against measured data.
- **G8**: Judged on the isotonic-recalibrated values the API serves (fitted on 2020-05..12, tested on held-out 2021). The 2021 window is January-February only and about 5 V above the training years; under +/-6% almost every step is unsafe, so nothing beats the base rate there.

## Bake-offs

| Component | Winner | Record |
| --- | --- | --- |
| solar | {'median': 'lgbm_residual', 'interval': 'conformal_30d'} | `data/results/bakeoff_solar.json` |
| solar_intervals | by_season_all_earlier | `data/results/bakeoff_solar_intervals.json` |
| upstream | lgbm_day_quantiles | `data/results/bakeoff_upstream.json` |
