# Proof: gates and headline results

Generated 2026-10-10T10:52 UTC from `data/results/results.json` (git 1da1730). Do not edit by hand: run `python -m scripts.evaluate`.

| Gate | What | Status | Measured | Threshold |
| --- | --- | --- | --- | --- |
| G1 | Engine parity with pandapower | **pass** | {"max_voltage_diff_pct": 0.0005, "max_voltage_diff_v": 0.001, "max_trafo_loading_diff_pts": 0.0, "day_seconds_pgm": 0.012, "day_seconds_pandapower": 5.54, "speedup": 455.7} | max voltage difference <= 0.1% and at least 10x faster |
| G2 | Weather-model availability | **pass** | {"models_used": ["gfs_global", "icon_global", "gem_global", "meteofrance_arpege_world", "ecmwf_ifs025"], "dropped": ["jma_gsm", "ukmo_global_deterministic_10km"]} | >= 95% non-null hours from the first valid hour and in the test year, per model |
| G3 | Solar v2 beats the first solar model | **pass** | {"mae_p50": 0.0329, "round1_mae": 0.0396, "coverage_80": 0.794, "wis": 0.0214} | MAE below 0.0396 kW/kWp on the identical 2025 daylight mask (recomputed from the first model's committed table: ml.solar_v2.first_model_mae) |
| G4 | Demand v2 skill and coverage | **fail** | {"skill_vs_best_baseline": 0.09, "coverage_80": 0.788, "held_out_district_skill": 0.153, "held_out_district_coverage_80": 0.798} | skill >= 10% against the best baseline and coverage 78-82% (strict variant, Mathura 2021) |
| G5 | Unbalanced engine converges; zero-sequence sensitivity | **pass** | {"peak_range_v": [268.4, 272.6], "balanced_peak_v": 263.1, "phase_modes_peak_v": {"random": 270.5, "round_robin": 268.9, "all_a": 294.1}} | >= 99% of steps converge for every phase mode and r0/x0 ratio 2-4 |
| G6 | Data and API licences permit the use | **conditional** | Open-Meteo free API: non-commercial use only | licences permit the intended use |
| G7 | Measured-plant yield calibration | **not_run** | outcome (b): IEEE DataPort needs a login | plant file readable with stated capacity |
| G8 | Risk probabilities are reliable | **pass** | {"pm10": {"days": 100, "observed_unsafe_share": 0.4989, "brier_calibrated": 0.1224, "brier_base_rate": 0.25, "brier_skill_raw": 0.498, "brier_skill_calibrated": 0.51, "by_district": {"mathura": {"days": 40, "observed_unsafe_share": 0.8419, "skill_calibrated": 0.009}, "bareilly": {"days": 60, "observed_unsafe_share": 0.2701, "skill_calibrated": 0.412}}}, "up_2005": {"days": 100, "observed_unsafe_share": 0.7871, "brier_calibrated": 0.0927, "brier_base_rate": 0.1676, "brier_skill_raw": 0.442, "brier_skill_calibrated": 0.447, "by_district": {"mathura": {"days": 40, "observed_unsafe_share": 0.9974, "skill_calibrated": -3.901}, "bareilly": {"days": 60, "observed_unsafe_share": 0.6469, "skill_calibrated": 0.361}}}} | calibrated Brier skill > 0 against the base rate of the pooled held-out steps, on every rule |

## Notes

- **G4**: Not met on the gate's protocol: no AI-improvement claim for demand. The held-out district (Bareilly 2021, every season) is reported beside it and does not replace it.
- **G6**: Demo and research fit; a DISCOM deployment needs a paid plan or another licensed source.
- **G7**: PV keeps the 14% system-loss assumption: yield not calibrated against measured data.
- **G8**: Isotonic map fitted on 2020-05..12 of both districts. Below the base rate on its own: mathura under up_2005 (almost every step unsafe, so a constant is hard to beat). The pooled reference is one rate for both districts, so part of the pooled skill is telling them apart; the per-district skills are shown for that reason.

## Bake-offs

| Component | Winner | Record |
| --- | --- | --- |
| solar | {'median': 'lgbm_residual', 'interval': 'conformal_30d'} | `data/results/bakeoff_solar.json` |
| solar_intervals | by_season_all_earlier | `data/results/bakeoff_solar_intervals.json` |
| upstream | lgbm_day_quantiles | `data/results/bakeoff_upstream.json` |
