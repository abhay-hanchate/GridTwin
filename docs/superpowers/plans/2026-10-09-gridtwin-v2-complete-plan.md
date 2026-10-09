# GridTwin v2 Complete Project Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Work on branch `v2/build`; commit after every task; **never push**.

**Goal:** Rebuild GridTwin from prototype to a production-grade decision-support service: for an Indian low-voltage street with single-phase rooftop solar on high-resistance overhead wire, give a DISCOM a calibrated day-ahead risk, a physics-verified ranked fix (including the phase to assign and per-house export limits), and a transformer-level connection decision, using the state's own voltage rule and an honest "no safe action" verdict.

**Architecture:** "AI predicts, physics decides." A data layer (all CEEW data, stochastic upstream voltage, measured-PV calibration) feeds calibrated forecasts. A scenario generator turns forecasts into correlated day samples. A phase-aware batch AC power-flow engine (power-grid-model, cross-checked against pandapower) replays every sample and every candidate fix. A risk engine and a fix tournament sit on top; planning tools (probabilistic hosting capacity, transformer headroom, connection check) reuse the same engine. A versioned FastAPI service and a four-area React dashboard deliver the results, packaged as one container with health checks, structured logs, metrics, runbooks and an offline demo mode.

**Tech Stack:** Python 3.11+ (CI matrix 3.11 and 3.13), pandapower, power-grid-model, pvlib, LightGBM, Chronos-2 (benchmark only), NetworkX, OR-Tools, NumPy/pandas/SciPy, FastAPI + Pydantic, Jinja2, React 19 + TypeScript + Vite + Recharts + Vitest, pytest, ruff, GitHub Actions, Docker.

**Evidence base:** `docs/GridTwin_V2_Master_Research_Document.md` (verified research; tags [V] verified, [S] snippet, [U] unverified) and the measured spikes in Part I.

## Global Constraints

Every task includes these. They are copied verbatim into each reviewer brief.

- The safe band is selected by **rule id** from the rule library; the old ids `"10"` and `"6"` stay as aliases (`"10"` = `pm10`, `"6"` = `up_2005`).
- One simulated day = **96 steps of 15 minutes**, naive IST timestamps.
- A step is **unsafe** if any LV node phase voltage is outside the rule band, any line or the transformer is above 100% loading, or the solver fails to converge. Solver failure is never safe.
- **Physics decides:** no ML output may approve a fix, a connection or a limit. Every recommended action is replayed through the full AC power flow for all 96 steps.
- Every number shown in the UI, API, report or docs carries a provenance tag: **observed**, **modeled**, or **benchmark**.
- No claim tagged [S] or [U] in the research document appears in the UI or the Final Document as a finding.
- **Leakage rules:** chronological splits; features use only information available before the target day starts; every demand or voltage model also reports a **held-out district** result (train Mathura, test Bareilly).
- **Never commit** raw data, API keys, `research/.env`, model weights above 25 MB, or generated caches. Raw data goes to `data/raw/` (gitignored).
- Licences are checked before any dataset or library enters a shipped path (Open-Meteo code is AGPL-3.0; its API terms are unchecked, gate G6).
- The existing 55 tests stay green unless a task explicitly changes the behaviour they pin; changed expectations are updated in the same task and the reason goes in the commit message.
- Time budgets: one balanced or unbalanced day replay < 0.3 s; a 100-sample risk run < 30 s; a cached API response < 300 ms (p95); see section 12.
- Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

---

# PART 0: HACKATHON EXECUTION GUIDE (TWO PEOPLE, SAME REPOSITORY)

This plan modifies and extends the existing repository on branch `v2/build` (cut from `v2/research`). Nothing is rebuilt from zero: the Round 1 engine, API and dashboard keep working until the v2 path replaces them. **Commit locally only; never push.**

## 0.1 What already exists and what changes

| Area | Existing (Round 1) | v2 change | Phase |
|---|---|---|---|
| `engine/config.py` | one site, Mathura | `Site`, `CeewFile`, both districts, six files | P2.1 |
| `engine/profiles.py` | loads cleaned Mathura | raw/clean/quality split, site-aware solar | P2.2 |
| `engine/powerflow.py` | pandapower day loop, balanced | `day_inputs(date, district)`, solver failure counted, cost fields; stays as the legacy path | P1.3, P2.3 |
| `engine/grid.py` | SimBench feeder | unchanged; wrapped by `engine/network.py` and `engine/archetypes.py` | P3 |
| `engine/actions.py`, `ranking.py`, `hosting_capacity.py`, `scenarios.py`, `simulate.py` | seven fixed fixes, one-day hosting | superseded by `engine/fixes/`, `hosting.py`, `scenario_gen.py`; deleted last | P6, P7, P10.12 |
| `engine/` new files | | `rules.py`, `voltage_rules.json`, `inverters.py`, `types.py`, `network.py`, `solver.py`, `violations.py`, `dayinputs.py`, `verdict.py`, `upstream.py`, `scenario_gen.py`, `risk.py`, `reliability.py`, `archetypes.py`, `reference.py`, `fixes/*` | P1 to P7 |
| `ml/forecast.py`, `live_forecast.py`, `early_warning.py` | Round 1 models | kept as fallback; `solar_v2.py`, `live_solar_v2.py`, `demand_v2.py`, `metrics.py`, `conformal.py`, `benchmark.py`, `pv_calibration.py`, `coldstart.py` added | P2, P4 |
| `backend/main.py` (18 routes) | legacy API | unchanged routes plus `/api/v2` router in `backend/v2/` | P8 |
| `backend/cache.py` | safe JSON cache | reused as is | P8 |
| `frontend/src/App.tsx` and `components/*` | five tabs | five areas; `GridMap`, `DayCharts` reused; `FixesView`, `CapacityView`, `StoryView`, `TwinSim` rewritten | P9 |
| `scripts/` | download, build, precompute | `download_data`/`build_data` extended; new `engine_sensitivity`, `download_solar_v2`, `calibrate_pv`, `run_reliability`, `nightly`, `evaluate`, `monitor`, `onboard`, `check` | P0 to P10 |
| `tests/` | 55 tests | stay green; about 150 added | all |
| CI, Docker, docs | one workflow | matrix, audit, nightly, Docker, runbooks, model cards | P0, P10 |

**A tested prototype of the new engine and model code is in `docs/superpowers/plans/prototype/`** (same folder layout as the repo, new and modified files only, 357 KB). Its tests passed on 9 Oct 2026 (engine, fixes, risk, scenario generator, solar v2, benchmark, calibration, Phase 2 data and demand code); the reliability backtest ran but did not beat the base rate, see P5.3. The fastest way to execute Phases 2 to 6 is to copy the files from there into the repo, run the tests, and commit task by task; the code blocks in this document are the same files. Files that were already in the repo (`engine/config.py`, `profiles.py`, `powerflow.py`, `scripts/build_data.py`) appear in the snapshot in their **modified** form: diff them against the repo before copying.

## 0.2 Who builds what

**Person A: Physics and Decisions** (engine, rules, risk, fixes, API, explanations)

| Order | Tasks | Notes |
|---|---|---|
| 1 | P1.1 rule library, P1.2 inverter curves, P1.3 violations and verdict, P1.4 settle legacy results | makes the existing demo truthful on day one |
| 2 | P2.5 upstream-voltage model | needed by the scenario generator |
| 3 | Phase 3 engine (P3.1 to P3.3 first, then P3.4, P3.5) | critical path for everything |
| 4 | Phase 5 scenarios and risk | P5.1 can start with simple spread scenarios before the copula exists |
| 5 | Phase 6 fix tournament | the headline feature |
| 6 | Phase 8 API v2 | B's dashboard consumes it |
| 7 | Phase 7 planning tools | headroom and connection check first |
| 8 | P10.1 explanations, P10.2 report, P10.3 onboarding, P10.4 evaluate | |

**Person B: Data, Models and Product** (data, forecasting, dashboard, operations)

| Order | Tasks | Notes |
|---|---|---|
| 1 | Phase 0 environment, CI, markers | one-time setup, shared by both |
| 2 | P2.1 to P2.3 all CEEW files and per-district profiles | start the 1 GB download immediately |
| 3 | Phase 9 dashboard against fixture JSON (shapes in P8.3) | does not wait for A: starts from hand-made fixtures, switches to the real API when it lands |
| 4 | P2.4 metrics and conformal, P2.6 demand v2, P2.7 real-data run | |
| 5 | Phase 4 solar v2, live inference, benchmark, calibration | |
| 6 | P10.5 to P10.12 nightly, monitor, security tests, licence register, model cards, Docker, runbooks, legacy removal | |
| 7 | Phase 11 release, demo script | joint |

## 0.3 Agree these in the first hour (so neither person blocks the other)

1. **Types** in section 8 (`Network`, `DayScenarioBatch`, `Controls`, `DayResult`, `Violations`) are final. Only A changes `engine/types.py`.
2. **API shapes** in P8.3 (`/risk`, `/fixes`) are final; A writes three fixture files by hand from those shapes in the first hour (`data/results/v2_fixtures/risk_sample.json`, `fixes_safe_sample.json`, `fixes_no_safe_sample.json`) and B builds the dashboard on them. When P8.3 lands, the fixtures are replaced by real output with no UI change.
3. **Forecast frames**: every forecaster returns a DataFrame indexed by 15-minute timestamps with `p10`, `p50`, `p90`.
4. **Ownership by directory.** A owns `engine/`, `backend/`, tests of those. B owns `ml/`, `frontend/`, `scripts/` (except `engine_sensitivity.py`, `run_reliability.py`, owned by A), `.github/`, `docs/`, `Dockerfile`. Shared files (`requirements*.txt`, `constraints.txt`, `pytest.ini`, `engine/config.py`): changes go through a one-line message to the other person before editing.
5. **Branches.** `v2/build` is the integration branch. A works on `v2/a-engine`, B on `v2/b-product`. Merge into `v2/build` at least at each merge point below and after any task other people depend on. Local merges only.

## 0.4 Priority tiers and the cut line

If time runs out, cut from the bottom. Each tier ends in something demonstrable.

**Tier 1: the demo (must have).** P0 (venv, markers only), P1.1 to P1.3, P3.1 to P3.3, P5.1 and P5.2 (spread scenarios acceptable), P6.1 to P6.6, P8.1 to P8.3, P9.1 to P9.3, P10.2 report, P11.2 demo script. Result: tomorrow's risk with P(unsafe), ranked fixes with phase swaps and per-house limits, the honest "No safe action" verdict under the UP ±6% rule, in the new dashboard.

**Tier 2: credibility (should have).** P2.1 to P2.7 (all data, demand v2, upstream), P3.4 and P3.5, P4.1 and P4.2 (solar v2, live), P5.3 (reliability), P7.2 and P7.3 (headroom, connection check), P8.4, P9.5 and P9.6, P10.1, P10.4, P10.7. Result: a Proof page with measured gates, planning tools, better forecasts.

**Tier 3: completeness (nice to have).** P4.3 and P4.4 (benchmark, calibration, cold start), P7.1, P7.4 to P7.7, P8.5, P9.4, P10.3, P10.5, P10.6, P10.8 to P10.12, Hindi strings, Docker.

## 0.5 Merge points

| When | What must be true |
|---|---|
| M1 | A's P1.3 merged: `run_day` counts solver failures and names the binding limit; B rebuilds data on it |
| M2 | A's P3.3 merged: `DaySolver` works; B can call it from `scripts/nightly.py` |
| M3 | A's P5.1 and P6.6 merged: `tournament.run` returns a verdict; B's dashboard switches from fixtures to `/api/v2` |
| M4 | B's P4.1 merged: solar v2 manifest committed; A feeds the v2 forecast into scenario generation |
| M5 | Everything merged on `v2/build`: `scripts/check.py`, full pytest, `npm run build`, `scripts/evaluate.py`; then Phase 11 together |

## 0.6 Effort (guesses by the plan author, not measured)

Person-hours assuming the prototype files are copied rather than retyped: Phase 0 about 2; Phase 1 about 4; Phase 2 about 8 (plus download time); Phase 3 about 4; Phase 4 about 5; Phase 5 about 5 (plus diagnosis of the reliability result); Phase 6 about 3; Phase 7 about 8; Phase 8 about 8; Phase 9 about 14; Phase 10 about 12; Phase 11 about 3. Total about 76, so roughly 38 each. Phases 7 to 11 are written but not run, so treat their estimates as less reliable than the others.

## 0.7 Rules that protect the demo

1. Never show a number that is not in `results.json` or an API response; never show a research claim tagged [S] or [U] as a finding.
2. If a gate fails, the UI shows the failure. A failed gate is a result, not a bug to hide.
3. Keep the legacy API until the dashboard has switched; the demo must never be broken by a half-finished migration.
4. Precompute the demo (P8.3 `scripts/nightly.py`) and keep `GRIDTWIN_OFFLINE=1` working so a dead network cannot stop the presentation.

## 0.8 Pick the best method DURING the build (bake-offs), not in the plan

The plan names a **current best hypothesis** for each component. It does not claim the winner. While executing, the person who owns a component runs the comparison below on the real data, applies the decision rule that is written **before** the run, and records the result. Numbers the plan quotes as "spike" or "measured on 9 Oct 2026" are one early look at the data, there to seed expectations; **the build re-runs them and the build's numbers decide.**

**Protocol for every bake-off (about 1 to 3 hours each):**
1. **Pre-register.** In `docs/DECISIONS.md` write the candidates, the metric, the split, and the decision rule before running anything. Do not change the rule after seeing results.
2. **Same data for everyone.** Identical train, calibration and test masks for all candidates. Never tune on the test period. Always include the simplest baseline and the Round 1 method.
3. **Run and record.** `scripts/bakeoff.py <component>` (written when the first bake-off is needed; it is a thin wrapper that calls each candidate and writes `data/results/bakeoff_<component>.json` with candidates, metric values, split, rule, winner, git hash, timestamp). The file feeds `results.json` (P10.4) and the Proof page.
4. **Ties go to the simpler method.** A complex candidate wins only by the margin in the rule. Losing candidates stay in the record.
5. **Keep the loser callable** behind a config switch until the release, so a surprise can be reverted without rewriting.
6. **Research if needed (time-box 45 minutes per component).** Before running, search for 2 or 3 candidates the table does not list: use web search, arXiv, GitHub and the paper reader (`research/omni_read.py`). Add a candidate only if it can be implemented in about 2 hours or less, and note its source and verification tag ([V] read, [S] snippet, [U] unverified) in `docs/DECISIONS.md`. If research changes a component's hypothesis, update the plan note in that task in the same commit.

| Component | Candidates to try (add more from research) | Metric and data | Decision rule (pre-registered) |
|---|---|---|---|
| Power-flow engine | power-grid-model, pandapower, any faster solver found | Voltage and loading parity on the 99-home street; time per day | Gate G1: parity within 0.1% and at least 10x faster |
| Solar median forecast | Round 1 model; physics on one blended NWP; physics mean of N models; LightGBM direct target; LightGBM residual target; bias-corrected mean; Chronos-2; TimesFM 2.5; newer solar models found by research | MAE and weighted interval score (WIS) on the identical 2025 daylight mask; per-season table | Lowest WIS wins if it is at least 3% better than the simplest candidate that already beats Round 1 (gate G3); a foundation model needs at least 5% and inputs that exist in production |
| Solar intervals | raw quantiles; Round 1 scale factor; split conformal with rolling windows 30 / 60 / 120 days; conformalised quantile regression; adaptive conformal; per-hour widths | Coverage per season (target 78-82%) and WIS | Within the coverage band in every season, then lowest WIS |
| Demand forecast | lag-1d, lag-7d, mean baselines; LightGBM on log-ratio; LightGBM direct; seasonal naive with holidays; Chronos-2 / TimesFM; with and without oracle weather | MAE, WIS, coverage; time split and held-out district; strict vs oracle variants | Gate G4 (at least 10% skill against the best baseline and coverage 78-82%), else report the true number and make no AI claim |
| Upstream voltage | AR(1) plus daily shape (current); LightGBM quantile; historical-day bootstrap; Gaussian process | Coverage of the 80% interval of the day maximum; CRPS; held-out district | Best coverage within 70-90% on both districts, then lowest CRPS |
| Scenario generator | independent draws; Gaussian copula; t-copula; joint-day bootstrap | Brier skill from the reliability backtest (G8); day-level energy score | Highest Brier skill; the copula must beat independent draws to be kept |
| Risk calibration | raw probabilities; isotonic; Platt scaling; conformal on the unsafe indicator | Brier score and reliability error per bin | Lowest Brier with every bin within 0.15 of ideal, else report the gap |
| Phase reallocation | CP-SAT; greedy swap; simulated annealing; MILP on voltage sensitivities | Unsafe steps removed at equal moves; runtime | Most unsafe steps removed with at most 15 moves; runtime at most 20 s |
| Export envelopes | per-step bisection; linearised sensitivity LP; proportional-fair rule | Curtailed kWh at zero unsafe steps | Least curtailed kWh |
| Battery control | sensitivity droop (current); LP schedule on sensitivities; rule-based peak shaving | Smallest battery size that clears the day; throughput | Smallest size that clears all scenarios, then least throughput |
| Feeder switching | greedy one-tie; exhaustive over candidate ties; none | Unsafe steps removed, operations | Fewest operations that clear the most steps |
| Hosting capacity sampling | plain Monte Carlo; Latin hypercube; fixed grid | Stability of P50 as draws grow | Fewest draws within 2 percentage points of the 500-draw answer |
| Cold-start PV | district forecast x kWp with shrinkage (current); physics-synthetic history plus fine-tuning; direct transfer | Error over the first 30 days on held-out rooftops (ERA5 PV at perturbed tilt and azimuth if no real roofs) | Lowest error; the simple method wins ties |

**Examples of what early looks suggested (hypotheses to confirm, not results to cite):** averaging several weather models helped the solar forecast far more than the choice of learner; Round 1's interval scale did not transfer across seasons; a foundation model was close but needed yesterday's observed PV; the risk percentages were not yet reliable on the old data. Each of these is a bake-off in the table above.

**Who runs which:** Person A runs the engine, scenario generator, risk calibration, phase, envelope, battery, switching and hosting-capacity bake-offs; Person B runs solar, intervals, demand, upstream voltage and cold-start. Each bake-off happens at the start of the task that implements the component (for example the solar bake-off is the first step of P4.1), before the code is copied from `prototype/`.

**Where the answers go:** `docs/DECISIONS.md` (human-readable, one entry per bake-off), `data/results/bakeoff_*.json` (machine-readable), the Proof page, and the model cards (P10.9).

---

# PART I: EVIDENCE, DECISIONS AND SCOPE

## 1. What Round 1 got wrong, and what replaces it

| Component | Round 1 (measured) | Why it is weak | v2 replacement |
|---|---|---|---|
| Smart-meter data | Mathura 2019 only, 38 homes, 26 usable profiles | 1 of 6 files; one season; one district | All 6 CEEW files (2 districts, May 2019 to Oct 2021) |
| Voltage rule | ±10% default; ±6% called "future strict" | CEEW cites UP Supply Code 2005 as ±6% today | Rule library with source and verification status |
| Smart inverter | Fixed power factor 0.9 all day | Not the standard curve | IEEE 1547 Cat B Volt/VAR and Volt/Watt with cost accounting |
| Network model | Balanced three-phase equivalent | Single-phase homes load one phase; balanced model under-predicts voltage (spike: 263 V balanced vs 268 V with perfectly spread phases, 273 V random, 294 V all on one phase) | Phase-aware asymmetric engine |
| Engine | pandapower, 1.7–3.2 s per day | Too slow for risk and hosting capacity | power-grid-model batch (12 ms balanced, 65 ms unbalanced per day) |
| Demand forecast | Skill 0.9%, coverage 75.3% | Trained on 5 summer months, tested on winter; lagged temperature only; outages as noise | All seasons, holiday flags, outage handling, split-conformal intervals, district hold-out |
| Solar forecast | Skill 13% vs persistence but 3.4% vs physics-only; interval scaled 2.5× | Overconfident raw quantiles; one NWP source; 10-month training | Multi-NWP ensemble, bias correction, conformal, Chronos-2 benchmark |
| Upstream voltage | Same calendar date of 2019 reused for a 2025 day | Not a forecast; no uncertainty | Stochastic conditional model |
| Risk | Three replays (P10/P50/P90) | No probability | Sampled scenarios, P(unsafe) per step, reliability backtest |
| Fixes | 7 fixed actions | No phase, switching, envelopes, battery sizing | Full tournament |
| Hosting capacity | One day, 10% steps, balanced | Single number | Probabilistic, seasonal, phase-aware, per transformer |
| Conductor model | R = 0.5524 Ω/km (DC at 20 °C), X = 0.35 assumed | Ignores conductor heating; X unsourced | Temperature-corrected R, sourced R values, X flagged as estimate |
| GNN shortcut, OpenDER | Promised, not built | Not worth building | Removed from all claims |

## 2. Measured spikes (9 Oct 2026, this machine)

These replace guesses in the plan. Scripts are not committed; the numbers are.

| Spike | Result | Consequence |
|---|---|---|
| **S1: power-grid-model vs pandapower**, 99-home street, balanced, 96 steps, same inputs | Max voltage difference **0.000005 pu (0.001 V)**; batch day **12 ms** vs pandapower **1.7 s (numba off) / 3.2 s (numba on, includes JIT)**; speedup **140–270×** | **Gate G1 passes** for this network. pandapower stays as the independent cross-check. |
| **S2: unbalanced power flow** (single-phase homes and PV on one phase each; zero-sequence assumed r0 = 3·r1, x0 = 3·x1) | Converges all 96 steps for 3 phase assignments; **63–69 ms per day**. Random phases (26/33/40 homes): max **273.3 V**, 32 steps above 1.10 pu, worst phase spread 33.5 V, max voltage unbalance 8.8%. Round-robin: **268.3 V**, spread 17.6 V, VUF 4.5%. All on phase A: **294.1 V**, VUF 30%. Balanced model, same inputs: **263.1 V**. | Unbalanced engine is the default. **Round 1 headline numbers are optimistic** and must be re-derived. The zero-sequence assumption is unsourced and drives the result: it becomes an explicit sensitivity (gate G5). |
| **S3: weather models** (Open-Meteo previous-runs, Mathura, 10–16 May 2025) | ECMWF IFS 0.25°, GFS, ICON, GEM, Météo-France ARPEGE returned 168 of 168 hours; JMA GSM returned none | Multi-NWP is viable. Full 2024–2025 coverage is still to be checked (gate G2). |
| **S4: Chronos-2** | `Chronos2Pipeline.from_pretrained`, `predict_df(df, future_df, id_column, timestamp_column, target, prediction_length, quantile_levels, ...)` exist (chronos-forecasting 2.3.2). Hugging Face returns 200 for `amazon/chronos-2` and `google/timesfm-2.5-200m-pytorch`. torch 2.6.0+cu124, CUDA available. | Foundation-model benchmark is feasible locally. TimesFM API still to be inspected in its task. |
| **S5: calendar** | `holidays.country_holidays('IN', subdiv='UP')` knows Diwali and Holi for 2019, 2020, 2021, 2025 | Holiday flags are usable. |
| **S6: CEEW files** | Six files, identical header `x_Timestamp,t_kWh,z_Avg Voltage (Volt),z_Avg Current (Amp),y_Freq (Hz),meter`; Dataverse ids and sizes listed in Plan task P2.1; about 1.05 GB total; 179 GB disk free | The existing positional loader works for all files. |
| **S7: conductor data** (IS 398 Part II reproduction, scanned; verify against BIS copy) | DC resistance at 20 °C, Ω/km: Squirrel 1.3940, Weasel 0.9289, **Rabbit 0.5524**, Racoon 0.3712, Dog 0.2792. Ampacity at 75 °C: 89, 114, 155, 196, 231 A | Archetypes can cite real resistances. Reactance X ≈ 0.29 Ω/km is **my estimate** (log formula, 0.4 m spacing); Round 1's 0.35 is also an assumption. |

## 3. Complete feature list

IDs are stable. **New** = not in Round 1. **Fix** = in Round 1 but wrong or weak.

### A. Data and calibration
| ID | Feature | Status |
|---|---|---|
| A1 | All-CEEW ingestion (6 files, 2 districts, 2.4 years) with per-district profiles | Fix |
| A2 | Data-quality layer: outage detection, surge flags, coverage and gap report | Fix |
| A3 | Stochastic upstream-voltage model (month, slot, day-type, day-level offset, AR(1)) | New |
| A4 | Indian feeder archetypes (urban short, rural long; DT 63–250 kVA; sourced conductors) | New |
| A5 | Phase-aware network: single-phase homes on phases A/B/C with neutral return (sequence model) | New |
| A6 | Utility onboarding: CSV schemas, validators, ingest CLI | New |
| A7 | Measured-PV yield calibration (Karnataka 72 kWp, if accessible) | New |
| A8 | Conductor temperature correction R(T) | New |

### B. Forecasting
| ID | Feature | Status |
|---|---|---|
| B1 | Demand v2 | Fix |
| B2 | Solar v2: multi-NWP, bias correction, conformal | Fix |
| B3 | Forecast benchmark: LightGBM vs Chronos-2 (and TimesFM if its API checks out) | New |
| B4 | Cold-start PV forecast for new rooftops | New |
| B5 | Joint scenario generator (copula on day-level anomalies, analog demand days) | New |

### C. Physics and rules
| ID | Feature | Status |
|---|---|---|
| C1 | Voltage-rule library with sources and verification status | New |
| C2 | Standard Volt/VAR and Volt/Watt (IEEE 1547 Cat B), damped iteration | Fix |
| C3 | Complete violation engine: voltage, line, transformer, neutral current, voltage-unbalance factor, reverse flow, solver failure, binding limit | Fix |
| C4 | Batch engine (power-grid-model) with pandapower cross-check in CI | New |
| C5 | Cost accounting: reactive loss, transformer loading, wire loss, curtailed energy, switching count | New |

### D. Risk and decisions
| ID | Feature | Status |
|---|---|---|
| D1 | Risk engine: P(unsafe) per step, expected unsafe hours, watch ≥20% / act ≥50%, reliability backtest | New |
| D2 | Fix tournament with lexicographic ranking | Fix |
| D3 | Phase reallocation fix (CP-SAT) | New |
| D4 | Day-ahead per-house export limits (operating envelopes) | New |
| D5 | Radial-safe feeder switching | New |
| D6 | Battery size sweep | Fix |
| D7 | Honest verdict: binding limit, closest option, what it would still need | Fix |
| D8 | Robust fix choice at the P90 case | Fix |

### E. Planning
| ID | Feature | Status |
|---|---|---|
| E1 | Probabilistic hosting capacity with random placement and phase draws | Fix |
| E2 | Transformer headroom engine per DT and per phase vs flat state caps | New |
| E3 | Connection check API | New |
| E4 | Meter-first ranking | New |
| E5 | Stress lab: panel size, upstream voltage, EV load, heatwave AC load, rule choice | New |
| E6 | R/X sensitivity map for Volt/VAR | New |

### F. Explain and deliver
| ID | Feature | Status |
|---|---|---|
| F1 | Grounded explanations; optional LLM rephrase with number-preservation check | Fix |
| F2 | Evening report (HTML, printable to PDF) | New |
| F3 | API v2 (versioned, typed, documented) | New |
| F4 | Plug-in registry and `/catalog` + `/whatif` | New |
| F5 | Dashboard redesign, Hindi and English, phone layout, accessibility | Fix |
| F6 | Container, deployment, offline demo mode | New |

### G. Quality and operations
| ID | Feature | Status |
|---|---|---|
| G1 | Evaluation harness (reliability, district hold-out, ablations, baselines) | New |
| G2 | `results.json` as the single source of truth; generated docs | New |
| G3 | Tests, CI matrix, lint, dependency audit, performance tests | Fix |
| G4 | Structured logging, metrics, health and readiness, drift monitoring | New |
| G5 | Security hardening, data governance, licence register | New |
| G6 | Runbooks, release process, rollback | New |

### H. Stretch (only after A–G pass their gates)
H1 sparse state estimation (power-grid-model estimator) · H2 phase identification by voltage correlation (validated on simulated labels) · H3 GIS-only topology repair (OptimalTPI baseline).

### Explicitly not built
GNN power-flow surrogate, OpenDER, reinforcement-learning control, LLM-driven control, SCADA streaming, transactive markets.

## 4. Best method, model and dataset per component, with gates

The method named in each subsection below is the **current best hypothesis**; section 0.8 says how the build confirms or replaces it. "Gate" = the measurement that must pass before the new method replaces the old one. A failed gate means: keep the old method, report the number honestly, and say nothing stronger in the UI or documents.

### 4.1 Engine (A5, C4) · Gate G1 (passed in spike S1), Gate G5

pandapower builds and cross-checks networks. power-grid-model runs scenarios (symmetric for parity tests, asymmetric by default). **G5** (convergence ≥99% of steps on all archetypes and phase assignments; sensitivity of peak voltage to r0/r1 ∈ {2, 3, 4} and x0/x1 ∈ {2, 3, 4} reported in the Proof page). If G5 fails on an archetype, fall back to the symmetric engine for that archetype and label results "balanced approximation".

### 4.2 Demand (B1) · Gate G4

Target: mean kW per home across present meters (Round 1 already used this), 15 min. Features: same-slot lags (1 and 7 days), 7-day same-slot mean, ratios, seasonal sine and cosine, weekday, UP holiday flag (today and yesterday), lagged temperature; plus an **oracle-weather** variant (target-day ERA5 temperature), labelled as an upper bound on what a good day-ahead temperature forecast could add. Model: LightGBM quantile on a log-ratio to the chosen lag baseline; split-conformal adjustment on a rolling 60-day calibration window. Evaluation: train Mathura up to 31 Dec 2020, test Mathura 2021; train Mathura, test Bareilly; per-season breakdown; baselines: 1-day, 7-day, mean of both. **G4:** strict-variant skill ≥10% against the better baseline and coverage 78–82%, else report the true number and make no AI-win claim.

### 4.3 Solar (B2, B3, B4, A7) · Gates G2, G3

Chain: multi-model NWP irradiance → learned bias correction (LightGBM on ensemble statistics) → pvlib transposition and cell temperature → calibrated yield factor → conformal intervals. **G2:** each NWP model must have ≥95% non-null hours over the training window; models below that are dropped. **G3:** MAE below Round 1's 0.0396 kW/kWp on the identical 2025 mask, else keep Round 1's model. Benchmark: Chronos-2 with covariates vs LightGBM, identical splits and metrics; adopt a foundation model only if weighted interval score improves ≥5% on 2025. Truth remains ERA5-driven PV (abstract-level evidence: ERA5 RMSE about 20.8 W/m², MBE −0.8%, r 0.94 against 27 IMD stations [S]); measured plant data only calibrates the yield factor.

### 4.4 Upstream voltage (A3)

Daily mean follows a seasonal mean plus AR(1) in the day-to-day deviation (the previous day's mean is known to the operator). Intra-day shape: mean by (month, daytype, slot) plus AR(1) residual. Validated on held-out days: coverage of the 80% interval for the day-maximum voltage, on Mathura 2021 and on Bareilly.

### 4.5 Scenario generator (B5)

Day-level anomalies of solar clearness (ERA5-driven PV energy over clear-sky), demand index (daily mean over seasonal mean) and upstream day-offset are available together for 2019–2021. A Gaussian copula on their rank-normal scores captures correlation. Given the solar forecast quantile level drawn for a scenario, the other two are sampled conditionally. Demand profiles come from analog days (same month, daytype) rescaled to the forecast daily mean. **Stated limitation:** the copula models climatological anomalies, not forecast errors, because forecast archives do not overlap the meter years.

### 4.6 Smart inverters (C2)

IEEE 1547-2018 Cat B Volt/VAR: (0.92 → +0.44, 0.98 → 0, 1.02 → 0, 1.08 → −0.44) of rated S. Volt/Watt: full output to 1.06 pu, falling to 0.2 at 1.10 pu (from the research notes; confirm against the BIS adoption annexure when readable). A second preset follows the Gujarat-authored paper (0.94, 0.99, 1.01, 1.06) and is labelled. Damped half-step iteration; the batch version iterates whole-day batches (about 8–10 passes). Always reported with reactive loss and transformer loading.

### 4.7 Risk (D1)

Sampled scenarios → batch replay → P(unsafe) per step → expected unsafe hours (mean and P10–P90) → watch ≥20%, act ≥50%. Violation duration windows (15 min to 24 h) reported because risk depends strongly on the window [S]. **Reliability backtest** (no forecast archive overlaps meter years): for every 2019–2021 day with observed demand and voltage and ERA5-driven PV, condition the generator only on coarse weather class (sunny, mixed, cloudy), month and previous-day voltage, predict P(unsafe) per step, and compare with the replay of the actual day. Report reliability curve and Brier score. Solar forecast calibration is reported separately on 2025.

### 4.8 Fix tournament (D2–D8)

Enumerate tap × inverter mode × battery × switching × export limit × phase assignment; every candidate verified by the engine. Phase assignment: OR-Tools CP-SAT on integer-scaled net injections at critical steps, then verified by power flow. Export limits: per-step bisection with voltage-sensitivity weights, vectorised. Switching: NetworkX spanning-tree radiality check, greedy with at most 2 operations. Battery: sequential droop controller with a sizing sweep. No ML pre-screen unless profiling shows the tournament exceeds budget (it will not, at 65 ms per day).

### 4.9 Planning (E1–E6)

Hosting capacity: Monte Carlo over (adoption level, kW tier, which homes, which phase, day scenario); per-draw capacity = highest adoption with zero unsafe steps; report P10/P50/P90. Headroom: additional kW per phase before the first violation at the P90 scenario. Comparison against flat state caps (Delhi 20%, Rajasthan 30%, Karnataka 80%, Tamil Nadu 90%, Odisha 75% [S]). Connection check returns approve, approve-with-conditions or refuse, with the binding limit and the phase to use.

### 4.10 Datasets

| Dataset | Use | Licence | Status |
|---|---|---|---|
| CEEW all six files | A1, B1, A3, B5 | CC0 [V] | Plan task P2.1 |
| Open-Meteo archive, ERA5 and previous-runs, several models | B2, weather for both districts | Code AGPL-3.0 [V]; API terms unchecked | Gate G6 |
| Karnataka 72 kWp plant (IEEE DataPort) | A7 yield factor | Not checked; may need login | Optional, branch in P4.4 |
| Prayas eMARC | Second Indian voltage source | Not stated | Optional, by email |
| RECON-SL | Cross-country check of demand features | CC BY 4.0 [V] | Optional, P2.7 |
| IS 398 Part II conductor table | Archetypes | Public standard | Verify against BIS copy |

## 5. Decision gates

| Gate | Measurement | Pass | If it fails |
|---|---|---|---|
| G1 | PGM vs pandapower on the 99-home street | ≤0.1% voltage and ≥10× faster | **Passed in spike S1** (0.001 V, 140–270×); re-run in CI every build |
| G2 | NWP model availability, Mathura 2024–2025 | ≥95% non-null per model | Drop that model |
| G3 | Solar v2 MAE vs 0.0396 on identical 2025 mask | Lower | Keep Round 1 model |
| G4 | Demand v2 strict-variant skill and coverage | ≥10% vs best baseline; 78–82% | Report true number, no AI-win claim |
| G5 | Unbalanced convergence and r0/x0 sensitivity | ≥99% steps converge on all archetypes | Symmetric fallback labelled "balanced approximation" |
| G6 | Open-Meteo API terms, dataset licences | Permit the intended use | Replace the source before release |
| G7 | Karnataka plant data accessible with capacity metadata | File readable, 72 kWp stated | Skip A7; keep the 14% loss assumption and say so |


---

# PART II: SYSTEM DESIGN

## 6. Architecture

```
              OFFLINE / NIGHTLY                                   ONLINE (FastAPI, one container)
 ┌──────────────────────────────────────────┐        ┌──────────────────────────────────────────────┐
 │ scripts/download_data.py  (CEEW, weather)│        │  /api/v2/*   typed, versioned, cached         │
 │ scripts/build_data.py     (profiles v2)  │        │   rules · catalog · whatif · risk · fixes     │
 │ ml/*.py train + calibrate (manifests)    │        │   headroom · connection-check · hosting       │
 │ scripts/nightly.py  (evening run)        │───────▶│   report · jobs · health · readiness · metrics│
 │ scripts/evaluate.py (gates → results.json)│        └───────────────┬──────────────────────────────┘
 └──────────────────────────────────────────┘                        │
                                                       ┌─────────────▼──────────────┐
  data/raw (gitignored) ─▶ data/processed/v2 ─▶ ml/models (manifest + sha256)        │  React dashboard   │
                                                       │ Home · Try a change · Fixes │
 FORECAST LAYER            SCENARIO LAYER              │ Planning · Proof            │
 solar_v2 ─┐               upstream.py ─┐              └────────────────────────────┘
 demand_v2 ─┼─▶ scenario_gen.py (copula + analog days) ─▶ DayScenarioBatch (S×T×H)
 conformal ─┘                                              │
                                                           ▼
 PHYSICS LAYER   Network (phase-aware) ─▶ DaySolver (power-grid-model; pandapower cross-check)
                 Controls (tap, VV/VW, export limits, battery) ─▶ DayResult arrays
                 violations.py (rule band, loading, VUF, reverse flow, solver failure, binding limit)
                                                           │
 DECISION LAYER  risk.py · fixes/tournament.py · hosting.py · headroom.py · connection.py
                                                           │
 DELIVERY        explain.py (numbers-only) · report.py · registry.py · results.json
```

Design rules:
1. **One canonical in-memory model** (`Network`, `DayScenarioBatch`, `Controls`, `DayResult`); every feature is a function of these.
2. **Vectorised over scenarios and steps.** Scenarios are a batch dimension; nothing loops in Python over 96 steps except the battery and the inverter fixed-point passes.
3. **Two engines, one contract.** `PgmBackend` is production; `engine/reference.py` (`pandapower_day`, balanced) is the independent reference used in the parity test and the nightly job.
4. **Legacy API stays until the dashboard is switched** (Phase 9); then `/api/*` is removed in Phase 10 with a deprecation note in the changelog.
5. **Everything cached is keyed by (input hash, code version).** Stale cache can never be served after a code change.

## 7. Target file structure

```
engine/
  config.py            # exists; extended: Site, CeewFile, paths, env settings
  rules.py             # C1
  voltage_rules.json   # C1 data with sources
  verdict.py           # binding limit + wording + verdict builder
  inverters.py         # C2 curves (pure functions) + pandapower controller (legacy)
  types.py             # Network, Controls, BatterySpec, DayScenarioBatch, DayResult
  network.py           # from_pandapower, assign_phases, with_* helpers
  archetypes.py        # A4
  solver.py            # DaySolver, PgmBackend, PandapowerBackend, parity helpers
  violations.py        # C3, C5 (array-based)
  dayinputs.py         # legacy DayInputs -> DayScenarioBatch
  upstream.py          # A3
  scenario_gen.py      # B5
  risk.py              # D1
  fixes/
    __init__.py
    base.py            # Candidate, cost vector, lexicographic ranking
    catalog.py         # enumerate tap/inverter/battery/curtail candidates
    phase_assign.py    # D3 CP-SAT
    envelopes.py       # D4
    switching.py       # D5
    battery.py         # D6
    tournament.py      # D2, D7, D8
  hosting.py           # E1
  headroom.py          # E2
  connection.py        # E3
  metering.py          # E4
  stress.py            # E5
  rxmap.py             # E6
  registry.py          # F4
  explain.py           # F1
  report.py            # F2
  grid.py, powerflow.py, actions.py, ranking.py, simulate.py, hosting_capacity.py, scenarios.py  # legacy (removed in P10.12)
ml/
  metrics.py           # pinball, wis, crps, coverage, skill
  conformal.py         # split-conformal helpers
  demand_v2.py         # B1
  solar_v2.py          # B2
  benchmark.py         # B3
  pv_calibration.py    # A7
  coldstart.py         # B4
  forecast.py, early_warning.py, live_forecast.py, explain.py   # legacy
backend/
  main.py              # legacy routes (until P10.12)
  v2/
    __init__.py
    app.py             # router assembly, middleware, error model
    schemas.py         # Pydantic models
    routes_*.py        # one module per area
    jobs.py            # background job store
    settings.py        # env settings
scripts/
  download_data.py  build_data.py  nightly.py  evaluate.py  monitor.py  onboard.py  check.py
frontend/src/
  app/ (shell, router)   pages/ (Home, TryChange, Fixes, Planning, Proof)
  components/ (RiskStrip, VoltageMap, HeadroomTable, ConnectionForm, ReliabilityChart, ...)
  i18n/ (en.json, hi.json)   api/ (typed client)
docs/
  GridTwin_V2_Master_Research_Document.md  runbooks/  model_cards/  generated/  DATA_SOURCES.md
tests/                 # one file per module; markers: slow, realdata
Dockerfile  docker-compose.yml  .dockerignore  pytest.ini  constraints.txt  CHANGELOG.md  NOTICE
```

## 8. Core data contracts (fixed; every phase honours these)

```python
# engine/types.py  (created in P3.1)
@dataclass(frozen=True)
class Network:
    name: str
    node_kv: np.ndarray            # (N,) rated line-to-line kV
    lv_nodes: np.ndarray           # indices of LV nodes (< 1 kV)
    line_from: np.ndarray; line_to: np.ndarray                  # (L,)
    line_r1_ohm: np.ndarray; line_x1_ohm: np.ndarray            # (L,) totals per line
    line_r0_ohm: np.ndarray; line_x0_ohm: np.ndarray            # (L,) zero sequence
    line_c1_f: np.ndarray; line_i_n_a: np.ndarray               # (L,)
    trafo: TrafoSpec                                            # one distribution transformer
    source_node: int
    house_node: np.ndarray         # (H,) node index per home
    house_phase: np.ndarray        # (H,) 0, 1, 2 = A, B, C
    house_kwp: np.ndarray          # (H,) installed PV per home (0 = none)
    provenance: dict               # {"topology": "benchmark: SimBench ...", "conductor": "IS 398 ..."}

@dataclass(frozen=True)
class DayScenarioBatch:
    t: pd.DatetimeIndex            # (T,) 15-minute steps, naive IST
    load_kw: np.ndarray            # (S, T, H) demand per home
    pv_per_kwp: np.ndarray         # (S, T) available kW per installed kWp (same for all homes)
    upstream_pu: np.ndarray        # (S, T) source voltage in pu of 230 V
    load_pf: float                 # 0.95
    labels: tuple                  # scenario names, length S

@dataclass(frozen=True)
class Controls:
    tap_pos: int = 0
    volt_var: VoltVarCurve | None = None
    volt_watt: VoltWattCurve | None = None
    pf_fixed: float | None = None              # Round 1 baseline only
    export_limit_kw: np.ndarray | None = None  # (T, H) or (H,) maximum net export per home
    curtail_keep: float | None = None          # uniform fraction kept (0..1)
    battery: BatterySpec | None = None
    inverter_s_factor: float = 1.0             # rated kVA = factor × installed kWp
    name: str = ""

@dataclass
class DayResult:
    t: pd.DatetimeIndex
    u_pu: np.ndarray               # (S, T, Nlv, 3) phase-to-neutral voltage in pu of 230 V
    line_loading_pct: np.ndarray   # (S, T, L)
    trafo_loading_pct: np.ndarray  # (S, T)
    trafo_p_kw: np.ndarray         # (S, T) active power into the HV side (negative = reverse flow)
    losses_kw: np.ndarray          # (S, T) line + transformer active loss
    q_loss_kvar: np.ndarray        # (S, T)
    pv_kw: np.ndarray              # (S, T) delivered
    pv_avail_kw: np.ndarray        # (S, T) available before any control
    inverter_kvar: np.ndarray      # (S, T) absorbed (positive = absorbing)
    battery_kw: np.ndarray         # (S, T) (positive = charging)
    neutral_a: np.ndarray          # (S, T) neutral current at the transformer LV side
    vuf_pct: np.ndarray            # (S, T) worst-node negative/positive sequence voltage ratio
    converged: np.ndarray          # (S, T) bool

@dataclass
class Violations:
    over: np.ndarray; under: np.ndarray; line: np.ndarray; trafo: np.ndarray; solver: np.ndarray  # (S, T) bool
    unsafe: np.ndarray             # (S, T) bool, OR of the five
    rule_id: str
```

Interface registry (signatures later tasks must match exactly):

```python
engine.rules.get_rule(rule_id: str) -> VoltageRule
engine.rules.load_rules() -> dict[str, VoltageRule]
engine.verdict.binding_limit(steps: list[dict]) -> dict | None            # legacy step dicts
engine.verdict.binding_limit_arrays(v: Violations, res: DayResult, rule: VoltageRule, s: int = 0) -> dict | None
engine.verdict.describe(limit: dict) -> str
engine.verdict.build_verdict(results: list[dict], safe: list[dict]) -> dict
engine.inverters.VoltVarCurve.q_fraction(v_pu)  # accepts float or ndarray
engine.inverters.VoltWattCurve.p_fraction(v_pu)
engine.network.from_pandapower(net, phases=None) -> Network
engine.network.assign_phases(n: int, mode: str, seed: int = 42) -> np.ndarray   # mode in {"random","round_robin","all_a"}
engine.solver.DaySolver(network, *, asymmetric=True, backend="pgm").solve(scn, controls=Controls()) -> DayResult
engine.violations.evaluate(res, rule, *, vuf_limit=None) -> Violations
engine.violations.summarise(res, viol, s=0) -> dict
engine.dayinputs.scenarios_from_legacy(inputs, network, seed=42) -> DayScenarioBatch
engine.upstream.UpstreamModel.fit(series) / .sample(date, n, prev_day_mean, rng) -> np.ndarray (n, 96)
engine.scenario_gen.ScenarioGenerator.sample(date, n, solar_fc, demand_fc, upstream, rng) -> DayScenarioBatch
engine.risk.assess_risk(solver, scn, controls, rule, *, watch=0.20, act=0.50) -> RiskResult
engine.fixes.tournament.run(network, scn, rule, *, solver_kwargs=None) -> TournamentResult
ml.metrics.pinball(y, q_pred: dict[float, array]) / wis(y, p10, p50, p90) / coverage(y, lo, hi) / skill(mae, base)
ml.conformal.conformal_q(pred, y, alpha) / apply_conformal(pred, q, floor=None)
```

Every forecaster returns a DataFrame indexed by 15-minute timestamps with columns `p10`, `p50`, `p90`.

## 9. API v2 (all under `/api/v2`, JSON, typed with Pydantic)

| Method and path | Purpose | Cache | Budget |
|---|---|---|---|
| GET `/rules` | Voltage rules with source and verification | static | 20 ms |
| GET `/networks` | Archetypes and the benchmark street, with provenance | static | 20 ms |
| GET `/risk?date&network&rule&fix` | Tomorrow's P(unsafe) per step, expected hours, level, per-limit shares | by (date, network, rule, fix, code version) | 300 ms cached, 30 s cold |
| GET `/fixes?date&network&rule` | Ranked tournament, verdict, binding limit, closest option | same | 300 ms cached, 60 s cold |
| GET `/simulate?date&network&rule&fix` | Side-by-side arrays for the replay | same | 300 ms cached |
| GET `/headroom?network&rule` | Per-phase headroom and comparison with flat caps | by (network, rule, version) | 300 ms cached |
| POST `/connection-check` | Approve, conditions or refuse for N homes at X kW | none (fast path) | 5 s |
| GET `/hosting?network&rule&season` | P10/P50/P90 hosting capacity with and without fix | cached | 300 ms cached, 120 s cold |
| GET `/catalog` | Every registered change, fix, check, output and its parameters | static | 20 ms |
| POST `/whatif` | Run a spec from the catalog; returns job id or result | by spec hash | 5 s warm |
| GET `/jobs/{id}` | Job status and result | none | 20 ms |
| GET `/report?date&network&rule&lang` | Evening report HTML | cached | 500 ms |
| GET `/health`, `/readiness`, `/metrics` | Liveness, data and model presence, Prometheus text | none | 20 ms |

Error model: `{"error": {"code": "...", "message": "...", "details": {...}}}` with 400 (bad input), 404 (unknown id), 409 (job not ready), 422 (validation), 503 (data or model missing). No stack traces in responses.

## 10. Security, privacy and data governance

- **No secrets in the repo.** Secrets come from the environment; `research/.env` is gitignored. CI runs `gitleaks`-style grep for `sk-` and `OMNIROUTE_API_KEY=`.
- **Inputs are validated** by Pydantic (dates within data range, numeric bounds, enum ids). Uploaded onboarding files are size-limited (10 MB), parsed with pandas only, never executed.
- **Dependency hygiene:** `pip-audit` and `npm audit --omit=dev` in CI (fail on high severity, warn otherwise); `constraints.txt` pins versions.
- **HTTP hardening:** CORS from env allow-list; security headers (`X-Content-Type-Options`, `Referrer-Policy`, a CSP for the static app); request-size limit; a simple in-process rate limit on `/whatif` and `/connection-check` (e.g. 30 per minute per client).
- **Privacy:** CEEW is anonymised (meter ids only). Utility data uploaded through onboarding stays on local disk, is never logged, and is deleted by `scripts/onboard.py --purge`. The report never prints meter ids.
- **Licence register** (`docs/DATA_SOURCES.md` and `NOTICE`): CEEW CC0; Open-Meteo (code AGPL-3.0; API terms pending, gate G6); ERA5 Copernicus licence; RECON-SL CC BY 4.0; ppOPF and the Hosting-Capacity repo are references only (not copied).
- **Honesty controls:** a test fails the build if any text in templates or UI strings contains a number not present in `results.json` or the API response it describes.

## 11. Observability and operations

- **Logging:** JSON lines with request id, route, status, duration, cache hit, code version; no payloads.
- **Metrics (`/api/v2/metrics`):** request count and latency histogram per route, cache hit ratio, solver convergence rate, job queue depth, model manifest age, last successful nightly run timestamp.
- **Drift monitoring (`scripts/monitor.py`, run nightly):** compares the last 14 days of forecast intervals with outcomes when outcomes exist (live demo: yesterday's realised weather); raises a `WARN` file in `data/monitor/` when coverage leaves 70–90% or MAE rises 25% over the model card baseline.
- **Fallbacks:** weather API failure → last good forecast with a visible "stale" flag (age in hours); model files missing → readiness 503 and the dashboard shows the cached evening report; solver non-convergence → step counted unsafe, never hidden.
- **Runbooks** (`docs/runbooks/`): gateway or weather API down; stale model; cache corruption; solver failures spike; data refresh; release and rollback.

## 12. Performance budgets (tested in `tests/test_performance.py`, marker `perf`)

| Operation | Budget | Basis |
|---|---|---|
| Balanced day (96 steps), PGM | < 0.1 s | spike: 12 ms |
| Unbalanced day, PGM | < 0.3 s | spike: 65 ms |
| Volt/VAR day (about 24 damped passes), unbalanced | < 3 s | 24 × 65 ms, measured |
| Risk run: 100 scenarios, one control set | < 30 s | 9,600 steps, estimated 6.5 s plus Python overhead |
| Fix tournament, about 40 candidates | < 150 s cold, served from precompute | measured 80 s (±10%, no battery) to 115 s (±6%, with battery) |
| Probabilistic hosting capacity: 11 levels × 200 draws | < 120 s | batch |
| Cached API responses | < 300 ms p95 | file or memory cache |
| Frontend first load (gzip) | < 300 KB initial, lazy-loaded pages | existing code-splitting |

## 13. Environments and configuration

Environment variables (all optional, defaults in `backend/v2/settings.py`): `GRIDTWIN_ENV` (dev, test, prod), `GRIDTWIN_DATA_DIR`, `GRIDTWIN_CACHE_DIR`, `GRIDTWIN_MODEL_DIR`, `GRIDTWIN_CORS_ORIGINS`, `GRIDTWIN_OFFLINE` (serve only bundled demo results), `GRIDTWIN_LOG_LEVEL`, `GRIDTWIN_RULE_DEFAULT` (default `up_2005` for UP deployments, `pm10` otherwise), `GRIDTWIN_LLM_REPHRASE` (off by default), `OMNIROUTE_BASE_URL` and `OMNIROUTE_API_KEY` (only used by `research/` tools and the optional rephrase).

Python environments: `requirements.txt` (loose) and `constraints.txt` (pinned, generated from a clean virtual environment). CI installs with `-c constraints.txt`. Local developers create a venv; the global interpreter is not used for the suite.


---

# PART III: IMPLEMENTATION

How to read a task: **Files** lists what is created, modified and tested. **Interfaces** states what the task consumes and produces. Steps are small (2–5 minutes each), test first. "Expected" lines state the output to see; if you see something else, stop and investigate before continuing.

Phase order and dependencies: 0 → 1 → 2 → 3 → (4, 5 need 2 and 3) → 6 → 7 → 8 → 9 → 10 → 11 → 12. Phases 2 and 3 can interleave; the dashboard (9) needs the API (8).

---

# PHASE 0: REPOSITORY, ENVIRONMENT AND CI FOUNDATIONS

**Deliverable:** a clean `v2/build` branch with a reproducible environment, a test marker scheme, a CI matrix, and a local `scripts/check.py` that runs the same gates as CI. Nothing in behaviour changes.

### Task P0.1: Branch, virtual environment, pinned constraints

**Files:**
- Modify: `requirements.txt`
- Create: `requirements-dev.txt`, `requirements-ml.txt`, `constraints.txt`

- [ ] **Step 1: Create the build branch and a clean virtual environment**

```bash
git checkout v2/research
git checkout -b v2/build
python -m venv .venv
source .venv/Scripts/activate        # Git Bash on Windows
python -m pip install --upgrade pip
```
Expected: prompt shows `(.venv)`; `git branch --show-current` prints `v2/build`.

- [ ] **Step 2: Update `requirements.txt` (runtime only)**

```text
pandapower==3.5.5
simbench==1.6.3
pvlib==0.16.1
lightgbm==4.7.0
pandas==2.3.3
pyarrow
numba
requests
fastapi
uvicorn[standard]
scikit-learn
power-grid-model
ortools
holidays
jinja2
pydantic-settings
prometheus-client
networkx
```

- [ ] **Step 3: Create `requirements-dev.txt`**

```text
-r requirements.txt
pytest
httpx
ruff
pip-audit
```

- [ ] **Step 4: Create `requirements-ml.txt` (optional, heavy; only for the foundation-model benchmark)**

```text
-r requirements.txt
chronos-forecasting
accelerate
einops
# torch is installed separately to match the local CUDA build:
#   pip install torch --index-url https://download.pytorch.org/whl/cu124
```

- [ ] **Step 5: Install and run the existing suite in the clean environment**

Run: `pip install -r requirements-dev.txt && python -m pytest -q tests`
Expected: `55 passed` (about 80 s). If a test fails here but passed in the global interpreter, the global environment had a different package version: fix the pin, not the test.

- [ ] **Step 6: Freeze constraints**

```bash
pip freeze --exclude-editable > constraints.txt
head -5 constraints.txt
```
Expected: pinned lines such as `pandapower==3.5.5`. The file must not contain `torch` or `chronos`.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt requirements-dev.txt requirements-ml.txt constraints.txt
git commit -m "build: split requirements, add pinned constraints for reproducible CI

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P0.2: Test markers and lint configuration

**Files:**
- Create: `pytest.ini`, `ruff.toml`
- Modify: `tests/test_api.py` (mark slow), none else

- [ ] **Step 1: Create `pytest.ini`**

```ini
[pytest]
testpaths = tests
addopts = -ra -m "not realdata and not perf"
markers =
    realdata: needs the raw datasets in data/raw (run with -m realdata after scripts/download_data.py)
    perf: performance budget tests (run with -m perf)
    slow: takes more than 20 seconds
```

- [ ] **Step 2: Create `ruff.toml` (syntax and undefined-name errors only, so no mass reformat)**

```toml
line-length = 120
target-version = "py311"

[lint]
select = ["E9", "F63", "F7", "F82"]
```

- [ ] **Step 3: Run both**

Run: `ruff check . && python -m pytest -q tests`
Expected: `All checks passed!` then `55 passed`.

- [ ] **Step 4: Commit**

```bash
git add pytest.ini ruff.toml
git commit -m "build: add pytest markers (realdata, perf, slow) and a minimal ruff config

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P0.3: CI matrix, dependency audit, parity job, frontend tests

**Files:**
- Modify: `.github/workflows/ci.yml`
- Create: `.github/workflows/nightly.yml`

- [ ] **Step 1: Replace `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  python:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
      - run: pip install -r requirements-dev.txt -c constraints.txt
      - run: ruff check .
      - run: pytest -q
      - name: Dependency audit
        run: pip-audit -r requirements.txt --progress-spinner off || echo "::warning::pip-audit reported findings"
      - name: Secret scan
        run: "! grep -rIE 'sk-[A-Za-z0-9]{20,}' --exclude-dir=.git --exclude-dir=node_modules --exclude=.env ."

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 24
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run build
      - run: npm test --if-present
      - run: npm audit --omit=dev --audit-level=high || echo "::warning::npm audit reported findings"
```

- [ ] **Step 2: Create `.github/workflows/nightly.yml` (engine parity and performance budgets)**

```yaml
name: Nightly

on:
  schedule:
    - cron: "30 20 * * *"
  workflow_dispatch:

jobs:
  parity-and-perf:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
      - run: pip install -r requirements-dev.txt -c constraints.txt
      - run: pytest -q -m "perf" tests/test_performance.py tests/test_solver_parity.py
```
(The files named here are created in Phase 3; until then the job is skipped by `workflow_dispatch` only.)

- [ ] **Step 3: Validate the YAML locally**

Run: `python -c "import yaml,sys; [yaml.safe_load(open(f)) for f in ['.github/workflows/ci.yml','.github/workflows/nightly.yml']]; print('yaml ok')"`
Expected: `yaml ok`. (If `yaml` is missing: `pip install pyyaml` in the venv; it is only a checker.)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows
git commit -m "ci: 3.11 and 3.13 matrix, ruff, pip-audit, secret scan, frontend lint and tests, nightly parity job

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P0.4: Local gate script and baseline tag

**Files:**
- Create: `scripts/check.py`

- [ ] **Step 1: Write `scripts/check.py`**

```python
"""Run the same gates as CI: lint, tests, frontend build. Usage: python scripts/check.py [--fast]"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(name: str, cmd: list[str], cwd: Path = ROOT) -> bool:
    print(f"\n=== {name}: {' '.join(cmd)}", flush=True)
    ok = subprocess.run(cmd, cwd=cwd, shell=sys.platform == "win32").returncode == 0
    print(f"--- {name}: {'ok' if ok else 'FAILED'}")
    return ok


def main() -> int:
    fast = "--fast" in sys.argv
    steps = [("lint", ["ruff", "check", "."]),
             ("tests", [sys.executable, "-m", "pytest", "-q", "-x"] + (["-m", "not slow"] if fast else []))]
    if not fast:
        steps.append(("frontend build", ["npm", "run", "build"], ROOT / "frontend"))
    results = [run(*s) for s in steps]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it**

Run: `python scripts/check.py`
Expected: three `ok` lines and exit code 0.

- [ ] **Step 3: Tag the Round 1 baseline and commit**

```bash
git add scripts/check.py
git commit -m "build: scripts/check.py runs the CI gates locally

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
git tag v1-baseline 3977cbb
```
Expected: `git tag` lists `v1-baseline`. This is the rollback point for Round 1 behaviour.

---

# PHASE 1: RULES, STANDARD INVERTERS AND A COMPLETE VIOLATION ENGINE

**Deliverable:** the legacy engine and API become truthful immediately: state voltage rules with sources, the IEEE 1547 inverter curves, solver failures counted as unsafe, reverse flow, cost accounting and a named binding limit. Shared pieces (`rules`, `inverters` curves, `verdict`) are reused by the v2 engine.

### Task P1.1: Voltage-rule library (C1)

**Files:**
- Create: `engine/rules.py`, `engine/voltage_rules.json`, `tests/test_rules.py`
- Modify: `engine/powerflow.py`, `engine/config.py`, `engine/scenarios.py`, `backend/main.py`, `tests/test_api.py`

**Interfaces:**
- Produces: `get_rule(rule_id) -> VoltageRule`, `load_rules()`, aliases `"10"` and `"6"`.
- Consumes: nothing.

- [ ] **Step 1: Write the failing tests** — `tests/test_rules.py`

```python
import pytest

from engine.rules import get_rule, load_rules


def test_aliases_keep_old_band_ids_working():
    assert get_rule("10").id == "pm10"
    assert get_rule("6").id == "up_2005"


def test_up_supply_code_is_plus_minus_six_percent_with_source():
    rule = get_rule("up_2005")
    assert (rule.vmin_pu, rule.vmax_pu) == (0.94, 1.06)
    assert (rule.vmin_v, rule.vmax_v) == (216.2, 243.8)
    assert rule.region == "Uttar Pradesh"
    assert "UPERC" in rule.source and "CEEW" in rule.source
    assert rule.verification == "secondary"


def test_default_band_is_marked_unverified():
    assert get_rule("pm10").verification == "unverified"


def test_asymmetric_rules_are_supported():
    rule = get_rule("mh_plus10_minus15")
    assert (rule.vmin_pu, rule.vmax_pu) == (0.85, 1.10)
    assert rule.vmin_v == 195.5 and rule.vmax_v == 253.0


def test_unknown_rule_lists_valid_ids():
    with pytest.raises(KeyError) as err:
        get_rule("nope")
    assert "pm10" in str(err.value) and "up_2005" in str(err.value)


def test_every_rule_is_well_formed():
    for rule in load_rules().values():
        assert 0.5 < rule.vmin_pu < 1.0 < rule.vmax_pu < 1.5
        assert rule.source.strip()
        assert rule.verification in {"primary", "secondary", "unverified"}
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -m pytest tests/test_rules.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.rules'`.

- [ ] **Step 3: Create `engine/voltage_rules.json`**

```json
{
  "rules": [
    {
      "id": "pm10",
      "label": "±10% of 230 V (default)",
      "vmin_pu": 0.90, "vmax_pu": 1.10, "nominal_v": 230.0,
      "region": "Generic",
      "source": "Round 1 default; the CEEW (2020) report also evaluates this band as its second reference range",
      "verification": "unverified",
      "note": "The 2021 CEA panel's preference is quoted in the Final Project Document and has not been re-checked."
    },
    {
      "id": "up_2005",
      "label": "Uttar Pradesh Supply Code 2005: ±6% of 230 V",
      "vmin_pu": 0.94, "vmax_pu": 1.06, "nominal_v": 230.0,
      "region": "Uttar Pradesh",
      "source": "UPERC, UP Electricity Supply Code 2005, as cited in CEEW (2020) 'What Smart Meters Can Tell Us' (prescribed 230 V ± 6%, 216-244 V)",
      "verification": "secondary",
      "note": "Cited second-hand; confirm against the Supply Code text."
    },
    {
      "id": "mh_plus10_minus15",
      "label": "Maharashtra: +10% / -15% of 230 V",
      "vmin_pu": 0.85, "vmax_pu": 1.10, "nominal_v": 230.0,
      "region": "Maharashtra",
      "source": "GridTwin Final Project Document section 3 (state regulator variant)",
      "verification": "unverified",
      "note": "Not re-checked in the v2 research."
    },
    {
      "id": "plus6_minus10",
      "label": "+6% / -10% of 230 V",
      "vmin_pu": 0.90, "vmax_pu": 1.06, "nominal_v": 230.0,
      "region": "Generic (reported for several state codes)",
      "source": "GridTwin Round 2 playbook (4 Oct 2026)",
      "verification": "unverified",
      "note": "Not re-checked in the v2 research."
    }
  ]
}
```

- [ ] **Step 4: Create `engine/rules.py`**

```python
"""Voltage-rule library: every band the engine can check, with its source and verification status."""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

RULES_FILE = Path(__file__).with_name("voltage_rules.json")
ALIASES = {"10": "pm10", "6": "up_2005"}
VERIFICATION = {"primary", "secondary", "unverified"}


@dataclass(frozen=True)
class VoltageRule:
    id: str
    label: str
    vmin_pu: float
    vmax_pu: float
    nominal_v: float
    region: str
    source: str
    verification: str
    note: str = ""

    @property
    def vmin_v(self) -> float:
        return round(self.vmin_pu * self.nominal_v, 1)

    @property
    def vmax_v(self) -> float:
        return round(self.vmax_pu * self.nominal_v, 1)

    def as_dict(self) -> dict:
        return {**self.__dict__, "vmin_v": self.vmin_v, "vmax_v": self.vmax_v}


@lru_cache(maxsize=1)
def load_rules() -> dict[str, VoltageRule]:
    raw = json.loads(RULES_FILE.read_text(encoding="utf-8"))
    rules: dict[str, VoltageRule] = {}
    for item in raw["rules"]:
        rule = VoltageRule(**item)
        if not 0.5 < rule.vmin_pu < 1.0 < rule.vmax_pu < 1.5:
            raise ValueError(f"rule {rule.id}: band must straddle 1.0 pu")
        if rule.verification not in VERIFICATION:
            raise ValueError(f"rule {rule.id}: verification must be one of {sorted(VERIFICATION)}")
        if not rule.source.strip():
            raise ValueError(f"rule {rule.id}: a source is required")
        rules[rule.id] = rule
    return rules


def get_rule(rule_id: str) -> VoltageRule:
    rules = load_rules()
    key = ALIASES.get(rule_id, rule_id)
    if key not in rules:
        raise KeyError(f"unknown voltage rule {rule_id!r}; valid ids: {sorted(rules)} and aliases {sorted(ALIASES)}")
    return rules[key]
```

- [ ] **Step 5: Run the rule tests**

Run: `python -m pytest tests/test_rules.py -v`
Expected: `6 passed`.

- [ ] **Step 6: Wire the rule into the legacy engine** — in `engine/powerflow.py` add `from engine.rules import get_rule` to the imports and replace `vmin, vmax = config.BANDS[band]` with:

```python
    rule = get_rule(band)
    vmin, vmax = rule.vmin_pu, rule.vmax_pu
```
and change the returned `"limits"` entry to `{"vm_min_pu": vmin, "vm_max_pu": vmax, "loading_max_pct": 100, "rule": rule.id}`.
Then delete the `BANDS = {...}` block from `engine/config.py` (confirm first: `grep -rn "BANDS" --include=*.py . | grep -v research` shows only those two places).

- [ ] **Step 7: Rename scenario S5** — in `engine/scenarios.py`:

```python
    "S5": {"name": "Every home with solar, UP Supply Code band (±6%)", "pv_share": 1.0, "band": "up_2005"},
```
(The alias `"6"` still works, but the scenario now names the rule explicitly. Cache file names use the scenario id, not the band, so existing cache keys are unchanged.)

- [ ] **Step 8: Validate band ids and add the rules endpoint** — in `backend/main.py` add `from engine.rules import get_rule, load_rules` to the imports, replace the `hosting_capacity` route with:

```python
@app.get("/api/hosting-capacity")
def hosting_capacity(date: str = DEFAULT_DATE, band: str = "10"):
    """Estimate solar adoption the feeder can host, with and without the recommended fix."""
    try:
        get_rule(band)
    except KeyError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        return _cached(f"hosting_capacity_{date}_{band}", lambda: estimate_hosting_capacity(date, band))
    except (KeyError, ValueError) as e:
        raise HTTPException(422, f"No complete meter data for {date}: {e}")


@app.get("/api/rules")
def rules():
    """Every voltage rule the engine can check, with its source and how well it is verified."""
    return [r.as_dict() for r in load_rules().values()]
```
and remove the now-unused `Query` import only if nothing else uses it (`grep -n "Query" backend/main.py`).

- [ ] **Step 9: Add API tests** — append to `tests/test_api.py`:

```python
def test_rules_endpoint_lists_sources_and_verification():
    rules = client.get("/api/rules").json()
    ids = [r["id"] for r in rules]
    assert {"pm10", "up_2005"} <= set(ids)
    up = next(r for r in rules if r["id"] == "up_2005")
    assert up["vmin_v"] == 216.2 and up["vmax_v"] == 243.8
    assert up["verification"] == "secondary"


def test_scenario_s5_names_the_rule():
    scenarios = {s["id"]: s for s in client.get("/api/scenarios").json()}
    assert "UP Supply Code" in scenarios["S5"]["name"]
```

- [ ] **Step 10: Run the full suite**

Run: `python -m pytest -q`
Expected: all pass except possibly tests that read cached S5 results (the cache for `run_S5_*` and `actions_S5_*` is keyed by scenario id and still valid because the band is numerically identical). If `test_strict_band_has_no_safe_action` fails, do not edit it yet: P1.2 changes the inverter model and may legitimately change that verdict; P1.5 settles it.

- [ ] **Step 11: Commit**

```bash
git add engine tests backend
git commit -m "feat(rules): voltage-rule library with sources; UP Supply Code 2005 band; /api/rules

The strict +/-6% case is the UP rule today per the CEEW report, not a future tightening.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P1.2: IEEE 1547 inverter curves and an interim legacy controller (C2)

**Files:**
- Create: `engine/inverters.py`, `tests/test_inverters.py`
- Modify: `engine/powerflow.py`, `engine/actions.py`, `frontend/src/plain.ts`, `frontend/src/components/FixesView.tsx`

**Interfaces:**
- Produces: `VoltVarCurve`, `VoltWattCurve`, `GUJARAT_VOLT_VAR`, `InverterControl` (pandapower fixed-point controller used by the legacy engine until Phase 10).
- Consumes: `run_day` accepts a hook that has a `.solve(net, step)` attribute and then uses it instead of `pp.runpp`.

- [ ] **Step 1: Write the failing tests** — `tests/test_inverters.py`

```python
import warnings

import pytest

from engine.grid import build_grid
from engine.inverters import VoltVarCurve, VoltWattCurve
from engine.powerflow import day_inputs, run_day
from engine.simulate import ACTIONS_BY_ID, worst_bus

warnings.filterwarnings("ignore")


def test_volt_var_curve_matches_ieee_cat_b_points():
    c = VoltVarCurve()
    assert c.q_fraction(1.00) == 0.0 and c.q_fraction(1.02) == 0.0
    assert c.q_fraction(0.92) == pytest.approx(0.44)
    assert c.q_fraction(1.08) == pytest.approx(-0.44)
    assert c.q_fraction(1.05) == pytest.approx(-0.22)
    assert c.q_fraction(1.20) == pytest.approx(-0.44)      # flat beyond the last point


def test_volt_watt_curve_reduces_output_between_1_06_and_1_10():
    c = VoltWattCurve()
    assert c.p_fraction(1.05) == 1.0
    assert c.p_fraction(1.08) == pytest.approx(0.6)
    assert c.p_fraction(1.12) == pytest.approx(0.2)


def _run(action_id: str, share: float = 1.0, band: str = "10") -> dict:
    inputs = day_inputs("2019-05-15")
    base = run_day(build_grid(share), inputs, band=band, detail=True)
    net = build_grid(share)
    hook = ACTIONS_BY_ID[action_id].make_hook(net, worst_bus(base), base["limits"]["vm_max_pu"])
    return run_day(net, inputs, band=band, hook=hook, detail=False)


@pytest.fixture(scope="module")
def baseline():
    return run_day(build_grid(1.0), day_inputs("2019-05-15"), detail=False)


def test_standard_volt_var_clears_the_every_home_day(baseline):
    # Measured 8 Oct 2026 in the v2 research: 0 unsafe steps, 220.5-250.1 V, transformer about 66%.
    r = _run("volt_var")["summary"]
    assert r["violation_steps"] == 0 and r["solver_failed_steps"] == 0
    assert r["max_vm_pu"] * 230 == pytest.approx(250.1, abs=0.5)
    assert r["min_vm_pu"] * 230 == pytest.approx(220.5, abs=0.5)
    assert r["max_vm_pu"] < baseline["summary"]["max_vm_pu"]


def test_volt_watt_curtails_energy_and_lowers_the_peak(baseline):
    r = _run("volt_watt")["summary"]
    assert r["curtailed_kwh"] > 0
    assert r["max_vm_pu"] < baseline["summary"]["max_vm_pu"]
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -m pytest tests/test_inverters.py -v`
Expected: FAIL on import (`engine.inverters` does not exist).

- [ ] **Step 3: Create `engine/inverters.py`**

```python
"""IEEE 1547-2018 smart-inverter characteristics (pure functions) and a pandapower controller.

Sign convention: Q fractions are positive when the inverter injects reactive power and negative when it
absorbs, as a fraction of rated apparent power. pandapower sgen q_mvar uses the same sign.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandapower as pp


@dataclass(frozen=True)
class VoltVarCurve:
    v_pu: tuple = (0.92, 0.98, 1.02, 1.08)
    q_frac: tuple = (0.44, 0.0, 0.0, -0.44)
    name: str = "IEEE 1547-2018 Category B"

    def q_fraction(self, v_pu):
        return np.interp(v_pu, self.v_pu, self.q_frac)


@dataclass(frozen=True)
class VoltWattCurve:
    v_pu: tuple = (1.06, 1.10)
    p_frac: tuple = (1.0, 0.2)
    name: str = "IEEE 1547-2018 Volt-Watt (confirm against the BIS annexure)"

    def p_fraction(self, v_pu):
        return np.interp(v_pu, self.v_pu, self.p_frac)


# Reactive limits of +-100% of the *available* capacity sqrt(S^2 - P^2); the controller clips to it.
GUJARAT_VOLT_VAR = VoltVarCurve(v_pu=(0.94, 0.99, 1.01, 1.06), q_frac=(1.0, 0.0, 0.0, -1.0),
                                name="Preset from the Gujarat-authored 2026 paper")


class InverterControl:
    """Damped fixed-point solve so every inverter responds to the voltage at its own bus."""

    def __init__(self, volt_var: VoltVarCurve | None = None, volt_watt: VoltWattCurve | None = None,
                 damping: float = 0.5, tol_mw: float = 1e-6, max_iter: int = 40, s_factor: float = 1.0):
        self.volt_var, self.volt_watt = volt_var, volt_watt
        self.damping, self.tol_mw, self.max_iter, self.s_factor = damping, tol_mw, max_iter, s_factor
        self.iterations: list[int] = []

    def solve(self, net: pp.pandapowerNet, step: int) -> None:
        sn = net.sgen.sn_mva.to_numpy() * self.s_factor
        p_avail = net.sgen.p_mw.to_numpy().copy()
        buses = net.sgen.bus.to_numpy()
        p, q = p_avail.copy(), np.zeros_like(p_avail)
        for k in range(self.max_iter):
            net.sgen["p_mw"] = p
            net.sgen["q_mvar"] = q
            pp.runpp(net, numba=True, init="results" if (step or k) else "auto")
            v = net.res_bus.loc[buses, "vm_pu"].to_numpy()
            p_t = p_avail * (self.volt_watt.p_fraction(v) if self.volt_watt else 1.0)
            cap = np.sqrt(np.maximum(sn ** 2 - p_t ** 2, 0.0))
            q_t = np.clip(sn * self.volt_var.q_fraction(v), -cap, cap) if self.volt_var else np.zeros_like(p)
            dp, dq = p_t - p, q_t - q
            if max(np.abs(dp).max(initial=0.0), np.abs(dq).max(initial=0.0)) < self.tol_mw:
                self.iterations.append(k + 1)
                return
            p, q = p + self.damping * dp, q + self.damping * dq
        raise pp.LoadflowNotConverged("inverter control did not settle")
```

- [ ] **Step 4: Let `run_day` use a hook's own solver** — in `engine/powerflow.py` replace the block from `curtailed_kwh += ...` through the `except pp.LoadflowNotConverged:` handler with:

```python
        if hook:
            hook(net, i)

        try:
            solve = getattr(hook, "solve", None)
            if solve:
                solve(net, i)
            else:
                pp.runpp(net, numba=True, init="results" if i else "auto")
        except pp.LoadflowNotConverged:
            steps.append({"t": t.strftime("%Y-%m-%dT%H:%M"), "solver_failed": True, "violations": []})
            continue
        curtailed_kwh += float((available - net.sgen.p_mw).sum()) * 1000 / 4
```
(Curtailment is now measured after the solve, so Volt/Watt's reduction is counted. For hooks without `.solve`, `net.sgen.p_mw` is unchanged by `runpp`, so existing numbers do not change. The earlier `if hook: hook(net, i)` and `curtailed_kwh += ...` lines above the `try` are removed.)

- [ ] **Step 5: Replace the actions** — in `engine/actions.py` add `from engine.inverters import InverterControl, VoltVarCurve, VoltWattCurve` and this factory after `_volt_var`:

```python
def _inverter(tap: int = 0, volt_var: bool = True, volt_watt: bool = False):
    def make(net, worst_bus, vmax):
        control = InverterControl(VoltVarCurve() if volt_var else None, VoltWattCurve() if volt_watt else None)

        def hook(net, i):
            net.trafo["tap_pos"] = tap
        hook.solve = control.solve
        hook.control = control
        return hook
    return make
```
Then replace the `ACTIONS` entries for `volt_var` and `tap1_volt_var` and add the new ones (keep every other entry):

```python
VV_PARAMS = {"curve": VoltVarCurve.name, "points_pu": VoltVarCurve.v_pu, "q_fraction": VoltVarCurve.q_frac}
VW_PARAMS = {"curve": VoltWattCurve.name, "points_pu": VoltWattCurve.v_pu, "p_fraction": VoltWattCurve.p_frac}
```
```python
    Action("volt_var", "Smart inverters: IEEE 1547 Volt/VAR", "volt_var", VV_PARAMS, _inverter()),
    Action("volt_watt", "Smart inverters: IEEE 1547 Volt/Watt", "volt_watt", VW_PARAMS, _inverter(volt_var=False, volt_watt=True)),
    Action("volt_var_watt", "Smart inverters: Volt/VAR with Volt/Watt", "volt_var", {**VV_PARAMS, **VW_PARAMS}, _inverter(volt_watt=True)),
    Action("tap1_volt_var", "Tap +1 with IEEE 1547 Volt/VAR", "combined", {"tap_pos": 1, **VV_PARAMS}, _inverter(tap=1)),
    Action("pf09_fixed", "Fixed power factor 0.9 (Round 1 setting, not a standard curve)", "volt_var",
           {"pf": VOLT_VAR_PF}, _volt_var(0)),
```
`VoltVarCurve.v_pu` on the class returns the dataclass default tuple, which is what we want for documentation.

- [ ] **Step 6: Frontend wording** — in `frontend/src/plain.ts` replace the `volt_var` entry and add:

```ts
  volt_var: {
    name: 'Switch solar inverters to the standard smart mode',
    how: 'Each home\'s inverter follows the international standard curve: it absorbs a little "reactive power" only when its own voltage is high. No solar is wasted.',
  },
  volt_watt: {
    name: 'Let inverters trim output when voltage is high',
    how: 'Above 1.06 times normal voltage each inverter reduces its output a little, only at the worst moments.',
  },
  volt_var_watt: {
    name: 'Standard smart mode plus output trimming',
    how: 'Inverters absorb reactive power first and trim output only if voltage is still too high.',
  },
  pf09_fixed: {
    name: 'Fixed power factor 0.9 (earlier setting)',
    how: 'Every inverter always absorbs the same share of reactive power. Kept only for comparison; it is not a standard curve.',
  },
```
and in `FixesView.tsx` add this case to `doingText` before `default:`:

```ts
    case 'volt_watt':
      return sun
        ? `Inverters trim their output when local voltage is high: ${kw(s.pv_kw)} of the ${kw(s.pv_available_kw)} available is being sent out.`
        : 'No sun right now, so the inverters are idle.'
```
Also change the S5 wording in `plain.ts`:

```ts
  S5: { short: 'Every home, UP rule (±6%)', long: 'Every home has solar, judged by the Uttar Pradesh supply-code rule (±6% of 230 V)' },
```
and the glossary entry `['Safe limit', 'Default ±10% of 230 V (207–253 V). The Uttar Pradesh supply code uses ±6% (216–244 V). Above the limit, appliances and solar inverters can fail.']`.

- [ ] **Step 7: Run the new tests and the frontend build**

Run: `python -m pytest tests/test_inverters.py -v && (cd frontend && npm run build)`
Expected: `4 passed` (about 2–3 minutes: the integration tests replay full days); the build prints `built in` with no TypeScript errors.

- [ ] **Step 8: Commit**

```bash
git add engine tests frontend
git commit -m "feat(inverters): IEEE 1547 Volt/VAR and Volt/Watt with damped solve; Round 1 fixed pf kept as a labelled baseline

Standard Volt/VAR alone clears the every-home day (0 unsafe steps, 220.5-250.1 V).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P1.3: Complete violation engine and honest verdicts (C3, C5, D7)

**Files:**
- Create: `engine/verdict.py`, `tests/test_verdict.py`
- Modify: `engine/powerflow.py`, `engine/ranking.py`, `tests/test_engine.py`

**Interfaces:**
- Produces: `binding_limit(steps)`, `describe(limit)`, `build_verdict(results, safe)`; `run_day` summary keys `reverse_flow_steps`, `max_trafo_loading_pct`, `reactive_loss_kvarh`, `inverter_kvarh`, `binding_limit`; solver failures appear as violations of type `solver_failure`.

- [ ] **Step 1: Write the failing tests** — `tests/test_verdict.py`

```python
from engine.verdict import binding_limit, build_verdict, describe


def _step(*items):
    return {"violations": [{"type": t, "element": "bus", "id": 1, "value": v, "limit": l} for t, v, l in items]}


def test_binding_limit_picks_the_most_frequent_type():
    steps = [_step(("overvoltage", 1.15, 1.10)), _step(("overvoltage", 1.12, 1.10)), _step(("trafo_overload", 120.0, 100))]
    b = binding_limit(steps)
    assert b["type"] == "overvoltage" and b["steps"] == 2 and b["worst"]["value"] == 1.15


def test_a_tie_prefers_the_transformer():
    steps = [_step(("overvoltage", 1.12, 1.10)), _step(("trafo_overload", 120.0, 100))]
    assert binding_limit(steps)["type"] == "trafo_overload"


def test_safe_day_has_no_binding_limit():
    assert binding_limit([{"violations": []}]) is None


def test_describe_uses_volts_and_percent():
    assert describe({"type": "overvoltage", "steps": 3, "worst": {"value": 1.1435, "limit": 1.10}}) == \
        "voltage reached 263 V against a 253 V limit in 3 steps"
    assert describe({"type": "trafo_overload", "steps": 1, "worst": {"value": 172.0, "limit": 100}}) == \
        "transformer loading reached 172% against a 100% limit in 1 step"
    assert describe({"type": "solver_failure", "steps": 2, "worst": {"value": 0.0, "limit": 0.0}}) == \
        "the power flow did not converge in 2 steps"


def _result(action_id, label, steps, curtailed, limit=None):
    return {"action_id": action_id, "label": label, "remaining_violation_steps": steps,
            "cost": {"curtailed_kwh": curtailed}, "binding_limit": limit}


def test_verdict_with_a_safe_action():
    safe = [_result("a", "Fix A", 0, 0.0)]
    v = build_verdict(safe, safe)
    assert v["safe_action_found"] and v["recommended"] == "a" and v["binding_limit"] is None


def test_no_safe_action_names_the_binding_limit_and_the_closest_option():
    limit = {"type": "trafo_overload", "steps": 12, "worst": {"value": 172.0, "limit": 100}}
    results = [_result("a", "Fix A", 20, 0.0), _result("b", "Fix B", 12, 5.0, limit)]
    v = build_verdict(results, [])
    assert not v["safe_action_found"] and v["closest"] == "b" and v["recommended"] is None
    assert "transformer loading reached 172%" in v["message"] and "Fix B" in v["message"]
    assert v["binding_limit"] == limit
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -m pytest tests/test_verdict.py -v`
Expected: FAIL (`engine.verdict` missing).

- [ ] **Step 3: Create `engine/verdict.py`**

```python
"""Name the limit that stops a fix from working, and build the honest verdict."""
from __future__ import annotations

NOMINAL_V = 230.0
ORDER = ("trafo_overload", "line_overload", "overvoltage", "undervoltage", "solver_failure")


def binding_limit(steps: list[dict]) -> dict | None:
    counts: dict[str, int] = {}
    worst: dict[str, dict] = {}
    for s in steps:
        for t in {v["type"] for v in s["violations"]}:
            counts[t] = counts.get(t, 0) + 1
        for v in s["violations"]:
            cur = worst.get(v["type"])
            if cur is None or abs(v["value"] - v["limit"]) > abs(cur["value"] - cur["limit"]):
                worst[v["type"]] = v
    if not counts:
        return None
    rank = lambda t: ORDER.index(t) if t in ORDER else len(ORDER)  # noqa: E731
    top = min(counts, key=lambda t: (-counts[t], rank(t)))
    return {"type": top, "steps": counts[top], "worst": worst[top]}


def describe(limit: dict) -> str:
    t, n, w = limit["type"], limit["steps"], limit["worst"]
    when = f"in {n} step{'s' if n != 1 else ''}"
    if t == "overvoltage":
        return f"voltage reached {w['value'] * NOMINAL_V:.0f} V against a {w['limit'] * NOMINAL_V:.0f} V limit {when}"
    if t == "undervoltage":
        return f"voltage fell to {w['value'] * NOMINAL_V:.0f} V against a {w['limit'] * NOMINAL_V:.0f} V limit {when}"
    if t == "trafo_overload":
        return f"transformer loading reached {w['value']:.0f}% against a {w['limit']:.0f}% limit {when}"
    if t == "line_overload":
        return f"wire loading reached {w['value']:.0f}% against a {w['limit']:.0f}% limit {when}"
    return f"the power flow did not converge {when}"


def build_verdict(results: list[dict], safe: list[dict]) -> dict:
    if safe:
        return {"safe_action_found": True, "recommended": safe[0]["action_id"],
                "message": f"Recommended: {safe[0]['label']}", "binding_limit": None, "closest": None}
    closest = min(results, key=lambda r: (r["remaining_violation_steps"], r["cost"]["curtailed_kwh"]))
    limit = closest.get("binding_limit")
    why = f" The limit that stops it: {describe(limit)}." if limit else ""
    return {"safe_action_found": False, "recommended": None, "closest": closest["action_id"], "binding_limit": limit,
            "message": (f"No safe action: every option leaves violations. Closest is '{closest['label']}' with "
                        f"{closest['remaining_violation_steps']} unsafe steps.{why}")}
```

- [ ] **Step 4: Run the verdict tests**

Run: `python -m pytest tests/test_verdict.py -v`
Expected: `6 passed`.

- [ ] **Step 5: Write failing engine tests** — append to `tests/test_engine.py`

```python
import pandapower as pp

from engine import powerflow
from engine.powerflow import day_inputs, run_day
from engine.scenarios import run_scenario


@pytest.fixture(scope="module")
def s1():
    return run_scenario("S1", detail=False)


def test_solver_failure_counts_as_unsafe(monkeypatch):
    real = pp.runpp
    calls = {"n": 0}

    def flaky(net, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 4:
            raise pp.LoadflowNotConverged("forced")
        return real(net, *args, **kwargs)

    monkeypatch.setattr(powerflow.pp, "runpp", flaky)
    r = run_day(build_grid(0.0), day_inputs("2019-05-15"), detail=False)
    assert r["summary"]["solver_failed_steps"] == 1
    failed = [s for s in r["steps"] if s.get("solver_failed")]
    assert failed[0]["violations"][0]["type"] == "solver_failure"
    assert r["summary"]["violation_steps"] >= 1


def test_reverse_flow_appears_only_with_solar(s4, s1):
    assert s4["summary"]["reverse_flow_steps"] > 0
    assert s1["summary"]["reverse_flow_steps"] == 0


def test_cost_accounting_fields_are_present_and_sane(s4):
    sm = s4["summary"]
    assert 40 < sm["max_trafo_loading_pct"] < 50           # 44.5% measured on 15 May 2019
    assert sm["reactive_loss_kvarh"] > 0
    assert sm["inverter_kvarh"] == 0                        # no inverter control in a plain scenario run


def test_binding_limit_is_named_for_the_every_home_day(s4):
    assert s4["summary"]["binding_limit"]["type"] == "overvoltage"
```

- [ ] **Step 6: Run to confirm they fail**

Run: `python -m pytest tests/test_engine.py -v`
Expected: the four new tests FAIL with `KeyError` (missing summary keys) or `IndexError` (failed step has no violations); the original four still pass.

- [ ] **Step 7: Replace `run_day` in `engine/powerflow.py`** with this final version (keeps the signature):

```python
def run_day(net: pp.pandapowerNet, inputs: DayInputs, band: str = "10",
            hook: Optional[Hook] = None, detail: bool = True) -> dict:
    """Simulate 96 steps. `hook(net, step)` lets a corrective action adjust the grid each step.

    A hook may carry a `.solve(net, step)` attribute that replaces the plain power flow (used by
    smart-inverter control, which needs its own fixed-point iteration).
    """
    rule = get_rule(band)
    vmin, vmax = rule.vmin_pu, rule.vmax_pu
    lv = lv_buses(net)
    meters = assign_meters(net, inputs.load_kw.columns)
    load_matrix = inputs.load_kw[meters].to_numpy() / 1000          # MW, 96 x houses

    steps = []
    losses_kwh = pv_kwh = curtailed_kwh = battery_kwh = reactive_loss_kvarh = inverter_kvarh = 0.0
    max_trafo = 0.0
    reverse_steps = 0
    for i, t in enumerate(inputs.load_kw.index):
        stamp = t.strftime("%Y-%m-%dT%H:%M")
        net.load["p_mw"] = load_matrix[i]
        net.load["q_mvar"] = load_matrix[i] * TAN_PHI
        available = float(inputs.pv_kw_per_kwp.iloc[i]) * net.sgen.sn_mva
        net.sgen["p_mw"] = available
        net.sgen["q_mvar"] = 0.0
        net.ext_grid["vm_pu"] = float(inputs.upstream_vm_pu.iloc[i])
        if hook:
            hook(net, i)

        try:
            solve = getattr(hook, "solve", None)
            if solve:
                solve(net, i)
            else:
                pp.runpp(net, numba=True, init="results" if i else "auto")
        except pp.LoadflowNotConverged:
            steps.append({"t": stamp, "solver_failed": True,
                          "violations": [{"type": "solver_failure", "element": "network", "id": 0,
                                          "value": 0.0, "limit": 0.0}]})
            continue
        curtailed_kwh += float((available - net.sgen.p_mw).sum()) * 1000 / 4

        vm = net.res_bus.loc[lv, "vm_pu"]
        line_load = net.res_line.loading_percent
        trafo_load = float(net.res_trafo.loading_percent.iloc[0])
        violations = [{"type": "overvoltage", "element": "bus", "id": int(b), "value": round(float(v), 4), "limit": vmax}
                      for b, v in vm[vm > vmax].items()]
        violations += [{"type": "undervoltage", "element": "bus", "id": int(b), "value": round(float(v), 4), "limit": vmin}
                       for b, v in vm[vm < vmin].items()]
        violations += [{"type": "line_overload", "element": "line", "id": int(l), "value": round(float(v), 1), "limit": 100}
                       for l, v in line_load[line_load > 100].items()]
        if trafo_load > 100:
            violations.append({"type": "trafo_overload", "element": "trafo", "id": 0, "value": round(trafo_load, 1), "limit": 100})

        reverse_kw = max(0.0, -float(net.res_trafo.p_hv_mw.iloc[0]) * 1000)
        reverse_steps += reverse_kw > 0.1
        max_trafo = max(max_trafo, trafo_load)
        losses_kwh += float(net.res_line.pl_mw.sum() + net.res_trafo.pl_mw.sum()) * 1000 / 4
        reactive_loss_kvarh += float(net.res_line.ql_mvar.sum() + net.res_trafo.ql_mvar.sum()) * 1000 / 4
        pv_kwh += float(net.res_sgen.p_mw.sum()) * 1000 / 4 if len(net.sgen) else 0.0
        inverter_kvarh += float(-net.sgen.q_mvar.clip(upper=0).sum()) * 1000 / 4 if len(net.sgen) else 0.0
        battery_kwh += float(net.res_storage.p_mw.abs().sum()) * 1000 / 4 if len(net.storage) else 0.0
        step = {
            "t": stamp,
            "max_vm_pu": round(float(vm.max()), 4),
            "min_vm_pu": round(float(vm.min()), 4),
            "trafo_loading_pct": round(trafo_load, 1),
            "reverse_flow_kw": round(reverse_kw, 2),
            "pv_kw": round(float(net.sgen.p_mw.sum()) * 1000, 2),
            "load_kw": round(float(net.load.p_mw.sum()) * 1000, 2),
            "upstream_vm_pu": round(float(inputs.upstream_vm_pu.iloc[i]), 4),
            # What any corrective action is doing at this step (all zero when no action is applied)
            "pv_available_kw": round(float(available.sum()) * 1000, 2),
            "inverter_kvar": round(float(-net.sgen.q_mvar.sum()) * 1000, 2) if len(net.sgen) else 0.0,
            "battery_kw": round(float(net.storage.p_mw.sum()) * 1000, 2) if len(net.storage) else 0.0,
            "tap_pos": int(net.trafo.tap_pos.iloc[0]),
            "violations": violations,
        }
        if detail:
            step["bus_vm_pu"] = {str(b): round(float(v), 4) for b, v in vm.items()}
            step["line_loading_pct"] = {str(l): round(float(v), 1) for l, v in line_load.items()}
        steps.append(step)

    ok = [s for s in steps if not s.get("solver_failed")]
    return {
        "date": inputs.date,
        "limits": {"vm_min_pu": vmin, "vm_max_pu": vmax, "loading_max_pct": 100, "rule": rule.id},
        "steps": steps,
        "summary": {
            "max_vm_pu": max(s["max_vm_pu"] for s in ok),
            "min_vm_pu": min(s["min_vm_pu"] for s in ok),
            "violation_steps": sum(1 for s in steps if s["violations"]),
            "solver_failed_steps": len(steps) - len(ok),
            "reverse_flow_steps": int(reverse_steps),
            "max_trafo_loading_pct": round(max_trafo, 1),
            "reactive_loss_kvarh": round(reactive_loss_kvarh, 2),
            "inverter_kvarh": round(inverter_kvarh, 1),
            "pv_kwh": round(pv_kwh, 1),
            "curtailed_kwh": round(curtailed_kwh, 1),
            "losses_kwh": round(losses_kwh, 2),
            "battery_throughput_kwh": round(battery_kwh, 1),
            "homes_profiled": int(inputs.load_kw.shape[1]),
            "binding_limit": binding_limit(steps),
        },
        "provenance": {
            "load": "observed: CEEW smart meters, Mathura",
            "voltage": "observed: median CEEW customer voltage, used as upstream voltage",
            "pv": "modeled: pvlib PVWatts on observed Open-Meteo weather",
            "grid": "benchmark: SimBench 1-LV-rural2 with Indian overhead line impedance",
        },
    }
```
Add the imports `from engine.rules import get_rule` and `from engine.verdict import binding_limit` at the top of the file. (`inverter_kvarh` counts absorbed energy: sgen `q_mvar` below zero is absorption.)

- [ ] **Step 8: Use the verdict builder and per-action binding limit in `engine/ranking.py`** — add `from engine.verdict import build_verdict`; inside the results loop add `"binding_limit": s["binding_limit"],` to the appended dict; replace the `best_partial = ...` and `verdict = {...}` block with:

```python
    verdict = build_verdict(results, safe)
```
(`ordered`, the return statement and everything else stay.)

- [ ] **Step 9: Run the engine and verdict tests**

Run: `python -m pytest tests/test_engine.py tests/test_verdict.py -v`
Expected: all pass. If `test_cost_accounting_fields_are_present_and_sane` fails on the 40–50 range, print `s4["summary"]["max_trafo_loading_pct"]`: the 15 May 2019 reference is 44.5%; a different value means the profile selection changed, so stop and investigate.

- [ ] **Step 10: Commit**

```bash
git add engine tests
git commit -m "feat(violations): solver failure counts as unsafe, reverse flow, cost accounting, named binding limit

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P1.4: Settle legacy results and pinned expectations (interim truth)

**Files:**
- Modify: `tests/test_api.py` (only expectations that the evidence changes), `README.md`
- Regenerate: `data/results/*.json`

- [ ] **Step 1: Regenerate every precomputed result with the new engine**

Run: `python scripts/precompute.py`
Expected: lines `saved grid_S1 … done in NNNs`. Allow 15–40 minutes: the Volt/VAR fixed-point solve repeats each power flow up to 10 times. If it exceeds 60 minutes, stop and profile one `volt_var` day before changing anything.

- [ ] **Step 2: Read the new verdicts, do not assume them**

```bash
python - <<'PY'
import json
for s in ["S4", "S5"]:
    d = json.load(open(f"data/results/actions_{s}_2019-05-15.json"))
    print(s, d["verdict"]["message"])
    for a in d["actions"]:
        print("  ", a["action_id"], a["remaining_violation_steps"] * 15, "min unsafe,", a["cost"]["curtailed_kwh"], "kWh curtailed, rank", a["rank"])
PY
```
Record both blocks in the commit message. Three outcomes are possible for S5 (UP ±6% band): (a) still "No safe action" with a named binding limit; (b) a safe action using Volt/Watt with curtailment; (c) a safe action without curtailment. Each is a valid, honest result.

- [ ] **Step 3: Update only the expectations the evidence changed**

`test_strict_band_has_no_safe_action` in `tests/test_api.py` pins outcome (a). Replace it with the measured outcome, for example for (b):

```python
def test_up_band_needs_a_curtailing_fix():
    r = client.get("/api/actions", params={"scenario": "S5"}).json()
    assert r["verdict"]["safe_action_found"] is True
    best = r["actions"][0]
    assert best["cost"]["curtailed_kwh"] > 0 and "volt_watt" in best["action_id"]
```
or for (a) keep the assertion and add `assert r["verdict"]["binding_limit"] is not None`. Any other test that fails: read the failure, compare with the measured number, and update the pinned value only if the new value is explained by the inverter change (state the reason in the commit message).

- [ ] **Step 4: Update the README tables** with the regenerated numbers (the "Seven fixes" table becomes the new ranked list; add a sentence that the ±6% case is the UP Supply Code band and that the earlier fixed-power-factor setting is kept only as a labelled baseline).

- [ ] **Step 5: Run the whole suite, the frontend build and the check script**

Run: `python scripts/check.py`
Expected: three `ok` lines.

- [ ] **Step 6: Commit**

```bash
git add data/results README.md tests
git commit -m "chore(results): regenerate with IEEE 1547 inverters and UP rule; update pinned verdicts

<paste the two verdict blocks from step 2>

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```


---

# PHASE 2: DATA V2, UPSTREAM VOLTAGE AND DEMAND FORECAST

**Deliverable:** all six CEEW files processed per district with a quality report; reusable forecasting metrics and conformal helpers; a stochastic upstream-voltage model; demand v2 evaluated on time and on a held-out district with gate G4 decided from real numbers. Legacy outputs are reproduced byte-for-byte in value so the existing demo is unaffected.

### Task P2.1: Configuration and download for both districts (A1)

**Files:**
- Modify: `engine/config.py`, `scripts/download_data.py`
- Create: `tests/test_config_v2.py`

**Interfaces:**
- Produces: `config.Site`, `config.SITES`, `config.DISTRICTS`, `config.CeewFile`, `config.CEEW_FILES` (list), per-district weather files `weather_<district>.json`.
- Consumes: nothing.

- [ ] **Step 1: Write the failing test** — `tests/test_config_v2.py`

```python
from engine import config


def _file(district, year):
    return next(f for f in config.CEEW_FILES if (f.district, f.year) == (district, year))


def test_ceew_files_cover_both_districts_and_three_years():
    keys = {(f.district, f.year) for f in config.CEEW_FILES}
    assert keys == {(d, y) for d in ("mathura", "bareilly") for y in (2019, 2020, 2021)}


def test_urls_use_original_format_only_for_ingested_tab_files():
    assert _file("mathura", 2019).url.endswith("/5425311") and "?" not in _file("mathura", 2019).url
    assert _file("mathura", 2021).url.endswith("/5425312?format=original")
    assert _file("bareilly", 2019).url.endswith("/5425325?format=original")
    assert _file("bareilly", 2020).filename == "ceew_bareilly_2020.csv"


def test_sites_and_legacy_constants():
    assert config.SITES["bareilly"].latitude == 28.37
    assert (config.LATITUDE, config.LONGITUDE, config.ALTITUDE_M) == (27.49, 77.67, 180)
    assert config.DISTRICTS == ("mathura", "bareilly")
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -m pytest tests/test_config_v2.py -v`
Expected: FAIL (`CEEW_FILES` is a dict; `SITES` missing).

- [ ] **Step 3: Update `engine/config.py`** — add `from typing import NamedTuple` at the top and replace the `LATITUDE … ALTITUDE_M` lines and the `CEEW_FILES` dict with:

```python
class Site(NamedTuple):
    latitude: float
    longitude: float
    altitude_m: float


SITES = {
    "mathura": Site(27.49, 77.67, 180),
    "bareilly": Site(28.37, 79.43, 270),     # city centre; altitude approximate, used only for sun position
}
DISTRICTS = tuple(SITES)

# Mathura is the original site; these names stay for code written before the second district.
LATITUDE, LONGITUDE, ALTITUDE_M = SITES["mathura"]
TIMEZONE = "Asia/Kolkata"


class CeewFile(NamedTuple):
    district: str
    year: int
    file_id: int
    original: bool = False      # some files are stored as ingested tab files; ?format=original returns the csv

    @property
    def filename(self) -> str:
        return f"ceew_{self.district}_{self.year}.csv"

    @property
    def url(self) -> str:
        base = f"https://dataverse.harvard.edu/api/access/datafile/{self.file_id}"
        return base + ("?format=original" if self.original else "")


# CEEW "High frequency smart meter data from two districts in India" (Harvard Dataverse, CC0)
# https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/GOCHJH
CEEW_FILES = [
    CeewFile("mathura", 2019, 5425311),
    CeewFile("mathura", 2020, 5425313),
    CeewFile("mathura", 2021, 5425312, original=True),
    CeewFile("bareilly", 2019, 5425325, original=True),
    CeewFile("bareilly", 2020, 5425310),
    CeewFile("bareilly", 2021, 5425314),
]
```
(Keep the existing `TIMEZONE` line only once.)

- [ ] **Step 4: Update `scripts/download_data.py`** — replace `weather_url` and `main` with:

```python
LEGACY_NAMES = {("mathura", 2019): "mathura2019.csv", ("mathura", 2021): "mathura2021.csv"}


def weather_url(base: str, start: str, end: str, site: config.Site = config.SITES["mathura"]) -> str:
    return (
        f"{base}?latitude={site.latitude}&longitude={site.longitude}"
        f"&start_date={start}&end_date={end}"
        f"&hourly={','.join(config.WEATHER_VARS)}&timezone={config.TIMEZONE}"
    )


def main() -> None:
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    for f in config.CEEW_FILES:
        legacy = config.RAW_DIR / LEGACY_NAMES.get((f.district, f.year), "")
        target = config.RAW_DIR / f.filename
        if legacy.is_file() and not target.exists():
            legacy.rename(target)                      # Round 1 file names are migrated, not downloaded again
        download(f.url, target)
    for district, site in config.SITES.items():
        download(weather_url(ARCHIVE, config.WEATHER_START, config.WEATHER_END, site),
                 config.RAW_DIR / f"weather_{district}.json")
    # ML training data for Mathura: genuine day-ahead forecasts (issued the day before) and ERA5 reanalysis.
    day_ahead_vars = ",".join(f"{v}_previous_day1" for v in config.WEATHER_VARS)
    download(weather_url(PREVIOUS_RUNS, "2024-01-01", "2025-12-31").replace(
        f"hourly={','.join(config.WEATHER_VARS)}", f"hourly={day_ahead_vars}"),
        config.RAW_DIR / "dayahead_mathura_2024_2025.json")
    download(weather_url(ARCHIVE, "2024-01-01", "2025-12-31") + "&models=era5",
             config.RAW_DIR / "era5_mathura_2024_2025.json")
```
(the file name `weather_mathura.json` is unchanged, so an existing download is reused.)

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_config_v2.py -v`
Expected: `3 passed`.

- [ ] **Step 6: Commit**

```bash
git add engine/config.py scripts/download_data.py tests/test_config_v2.py
git commit -m "feat(data): config and downloader for all six CEEW files and both districts

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P2.2: Raw/clean/quality loaders and site-aware solar (A1, A2)

**Files:**
- Modify: `engine/profiles.py`
- Create: `tests/test_profiles_v2.py`

**Interfaces:**
- Produces: `read_ceew_raw(path)`, `clean_ceew(df)`, `read_ceew(path)` (unchanged behaviour), `quality_report(raw) -> dict`, `pv_hourly(w, site=None)`, `pv_from_weather(w, site=None)`, `clearsky_ghi(index, site=None)`.
- Consumes: `config.SITES`.

- [ ] **Step 1: Write the failing tests** — `tests/test_profiles_v2.py`

```python
import numpy as np
import pandas as pd
import pytest

from engine import config, profiles

HEADER = "x_Timestamp,t_kWh,z_Avg Voltage (Volt),z_Avg Current (Amp),y_Freq (Hz),meter\n"


def _csv(tmp_path, rows):
    path = tmp_path / "x.csv"
    path.write_text(HEADER + "\n".join(rows) + "\n")
    return path


@pytest.fixture
def messy(tmp_path):
    return _csv(tmp_path, ["2019-05-01 00:00:00,0.02,240,1,50,A",
                           "2019-05-01 00:03:00,0.0,0,0,0,A",          # outage: zeros
                           "2019-05-01 00:06:00,0.9,654,1,50,A"])      # surge


def test_clean_marks_outage_and_surge_as_missing(messy):
    clean = profiles.read_ceew(messy)
    assert clean["v"].isna().tolist() == [False, True, True]
    assert clean["kwh"].isna().tolist() == [False, True, True]


def test_raw_keeps_every_reading(messy):
    raw = profiles.read_ceew_raw(messy)
    assert raw["v"].tolist() == [240.0, 0.0, 654.0]


def test_quality_report_counts_outages_and_surges(messy):
    rep = profiles.quality_report(profiles.read_ceew_raw(messy))
    assert rep["readings"] == 3 and rep["meters"] == 1
    assert rep["outage_share"] == pytest.approx(1 / 3, abs=1e-3) and rep["surge_share"] == pytest.approx(1 / 3, abs=1e-3)
    assert rep["max_voltage_v"] == 654.0
    assert rep["per_meter"]["A"]["valid"] == pytest.approx(1 / 3, abs=1e-3)


def _weather():
    idx = pd.date_range("2019-06-01 00:00", periods=24, freq="h")
    return pd.DataFrame({"direct_normal_irradiance": 600.0, "shortwave_radiation": 700.0,
                         "diffuse_radiation": 100.0, "temperature_2m": 30.0, "wind_speed_10m": 7.2}, index=idx)


def test_solar_output_depends_on_the_site():
    a = profiles.pv_hourly(_weather(), config.SITES["mathura"])
    b = profiles.pv_hourly(_weather(), config.SITES["bareilly"])
    assert a.max() > 0 and not np.allclose(a.to_numpy(), b.to_numpy())


def test_default_site_is_mathura():
    pd.testing.assert_series_equal(profiles.pv_hourly(_weather()), profiles.pv_hourly(_weather(), config.SITES["mathura"]))
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -m pytest tests/test_profiles_v2.py -v`
Expected: FAIL (`read_ceew_raw` missing).

- [ ] **Step 3: Edit `engine/profiles.py`** — replace `read_ceew` with the three functions and the report, and make the solar helpers site-aware:

```python
def read_ceew_raw(path: Path) -> pd.DataFrame:
    """All readings exactly as recorded (the files share one column order across districts and years)."""
    df = pd.read_csv(path, parse_dates=[0])
    df.columns = CEEW_COLUMNS
    return df[["ts", "kwh", "v", "meter"]]


def clean_ceew(df: pd.DataFrame) -> pd.DataFrame:
    """A zero or impossible voltage means the meter was off (outage) or surged, not zero demand."""
    lo, hi = config.VALID_VOLTAGE_RANGE_V
    df = df.copy()
    df.loc[~df["v"].between(lo, hi), ["kwh", "v"]] = np.nan
    return df


def read_ceew(path: Path) -> pd.DataFrame:
    return clean_ceew(read_ceew_raw(path))


def quality_report(raw: pd.DataFrame) -> dict:
    """Outage, surge and coverage statistics before any cleaning."""
    lo, hi = config.VALID_VOLTAGE_RANGE_V
    v = raw["v"]
    flags = pd.DataFrame({"meter": raw["meter"], "outage": v < lo, "surge": v > hi, "valid": v.between(lo, hi)})
    per_meter = flags.groupby("meter")[["outage", "surge", "valid"]].mean().round(4)
    return {
        "readings": int(len(raw)),
        "meters": int(raw["meter"].nunique()),
        "first": raw["ts"].min().strftime("%Y-%m-%d %H:%M"),
        "last": raw["ts"].max().strftime("%Y-%m-%d %H:%M"),
        "outage_share": round(float((v < lo).mean()), 4),
        "surge_share": round(float((v > hi).mean()), 4),
        "max_voltage_v": round(float(v.max()), 1),
        "per_meter": per_meter.to_dict(orient="index"),
    }
```
and change the three solar helpers:

```python
def _location(site: config.Site | None) -> pvlib.location.Location:
    site = site or config.SITES["mathura"]
    return pvlib.location.Location(site.latitude, site.longitude, config.TIMEZONE, site.altitude_m)


def pv_from_weather(w: pd.DataFrame, site: config.Site | None = None) -> pd.Series:
    """Solar output in kW per installed kW, 15-minute, from hourly weather."""
    return pv_hourly(w, site).resample("15min").interpolate("time").clip(lower=0).astype("float32")


def pv_hourly(w: pd.DataFrame, site: config.Site | None = None) -> pd.Series:
    """Solar output in kW per installed kW (PVWatts model), hourly.

    Open-Meteo radiation is the mean of the preceding hour, so the sun position is
    evaluated at the middle of that hour.
    """
    mid = (w.index - pd.Timedelta(minutes=30)).tz_localize(config.TIMEZONE)
    sun = _location(site).get_solarposition(mid)
    # (the remainder of the function body is unchanged: get_total_irradiance, sapm_cell, pvwatts_dc ...)
```
```python
def clearsky_ghi(index: pd.DatetimeIndex, site: config.Site | None = None) -> pd.Series:
    """Clear-sky global horizontal irradiance (Ineichen) at mid-hour, W/m2."""
    mid = (index - pd.Timedelta(minutes=30)).tz_localize(config.TIMEZONE)
    return pd.Series(_location(site).get_clearsky(mid)["ghi"].to_numpy(), index=index, name="clearsky_ghi")
```
(`pv_hourly` keeps its existing body from `poa = pvlib.irradiance.get_total_irradiance(...)` down; only the `site = pvlib.location.Location(...)` / `sun = site.get_solarposition(mid)` lines are replaced as shown.)

- [ ] **Step 4: Run the tests plus the existing forecast integrity tests (they call these helpers)**

Run: `python -m pytest tests/test_profiles_v2.py tests/test_ml_integrity.py tests/test_live_forecast.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add engine/profiles.py tests/test_profiles_v2.py
git commit -m "feat(data): raw/clean/quality loaders and site-aware solar helpers

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P2.3: Per-district build with quality report and legacy parity (A1, A2)

**Files:**
- Modify: `scripts/build_data.py`, `engine/powerflow.py` (add `district` option to `day_inputs`), `.gitignore`
- Create: `tests/test_build_data.py`

**Interfaces:**
- Produces: `build_district(frames, weather, site, out, district) -> dict`; files in `data/processed/v2/`: `load_kw_<d>.parquet`, `upstream_vm_pu_<d>.parquet`, `weather_hourly_<d>.parquet`, `pv_kw_per_kwp_<d>.parquet`, `quality_<d>.json`; `day_inputs(date, district=None, processed_dir=None)`.
- Consumes: P2.2 loaders.

- [ ] **Step 1: Write the failing tests** — `tests/test_build_data.py`

```python
import json

import numpy as np
import pandas as pd
import pytest

from engine import config
from engine.powerflow import day_inputs
from scripts import build_data


def _frames():
    idx = pd.date_range("2019-05-01", periods=480, freq="3min")          # one day of 3-minute readings
    return [pd.DataFrame({"ts": idx, "kwh": 0.02, "v": 240.0, "a": 1.0, "hz": 50.0, "meter": m})[["ts", "kwh", "v", "meter"]]
            for m in ("A", "B")]


def _weather():
    idx = pd.date_range("2019-05-01", periods=24, freq="h")
    return pd.DataFrame({"direct_normal_irradiance": 500.0, "shortwave_radiation": 600.0, "diffuse_radiation": 100.0,
                         "temperature_2m": 30.0, "wind_speed_10m": 7.2, "cloud_cover": 10.0}, index=idx)


def test_build_district_writes_every_output(tmp_path):
    report = build_data.build_district(_frames(), _weather(), config.SITES["mathura"], tmp_path, "mathura")
    for name in ("load_kw_mathura.parquet", "upstream_vm_pu_mathura.parquet", "weather_hourly_mathura.parquet",
                 "pv_kw_per_kwp_mathura.parquet", "quality_mathura.json"):
        assert (tmp_path / name).exists(), name
    assert report["meters"] == 2 and "coverage_by_year" in report
    loads = pd.read_parquet(tmp_path / "load_kw_mathura.parquet")
    assert list(loads.columns) == ["A", "B"]
    assert loads.iloc[0, 0] == pytest.approx(0.4)                         # 0.02 kWh per 3 min x 20 = 0.4 kW
    assert json.loads((tmp_path / "quality_mathura.json").read_text())["outage_share"] == 0.0


def test_day_inputs_reads_a_district_from_a_chosen_directory(tmp_path):
    build_data.build_district(_frames(), _weather(), config.SITES["mathura"], tmp_path, "mathura")
    di = day_inputs("2019-05-01", district="mathura", processed_dir=tmp_path)
    assert di.load_kw.shape == (96, 2)
    assert len(di.pv_kw_per_kwp) == 96 and len(di.upstream_vm_pu) == 96
    assert di.upstream_vm_pu.iloc[0] == pytest.approx(240.0 / 230.0, rel=1e-4)
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -m pytest tests/test_build_data.py -v`
Expected: FAIL (`build_district` missing).

- [ ] **Step 3: Rewrite `scripts/build_data.py`**

```python
"""Build the processed profiles from data/raw.

Usage:  python scripts/download_data.py && python scripts/build_data.py

Outputs
  data/processed/v2/*_<district>.parquet|json   one set per district, every meter kept
  data/processed/*.parquet                      the Round 1 (legacy) Mathura files, rebuilt unchanged
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import config, profiles  # noqa: E402


def build_district(frames: list[pd.DataFrame], weather: pd.DataFrame, site: config.Site, out: Path, district: str) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    raw = pd.concat(frames)
    report = profiles.quality_report(raw)
    ceew = profiles.clean_ceew(raw)

    loads = profiles.load_profiles(ceew)
    loads.to_parquet(out / f"load_kw_{district}.parquet")
    profiles.voltage_profile(ceew).to_frame().to_parquet(out / f"upstream_vm_pu_{district}.parquet")
    weather.to_parquet(out / f"weather_hourly_{district}.parquet")
    profiles.pv_from_weather(weather, site).to_frame().to_parquet(out / f"pv_kw_per_kwp_{district}.parquet")

    coverage = loads.notna().groupby(loads.index.year).mean().T                  # meters x years
    report["coverage_by_year"] = coverage.round(3).rename(columns=str).to_dict(orient="index")
    report["voltage_by_year"] = {str(y): profiles.voltage_stats(g) for y, g in ceew.groupby(ceew["ts"].dt.year)}
    (out / f"quality_{district}.json").write_text(json.dumps(report, indent=2))
    return report


def build_legacy(raw_by_key: dict, out: Path) -> None:
    """Round 1 files: Mathura 2019 and 2021, meters kept by their 2019 coverage."""
    keys = [("mathura", 2019), ("mathura", 2021)]
    if not all(k in raw_by_key for k in keys):
        print("legacy files skipped (Mathura 2019 and 2021 not both downloaded)")
        return
    ceew = profiles.clean_ceew(pd.concat([raw_by_key[k] for k in keys]))
    loads = profiles.load_profiles(ceew)
    coverage = loads.loc[:"2019-12-31"].notna().mean()
    keep = coverage[coverage >= config.MIN_METER_COVERAGE].index
    loads[keep].to_parquet(out / "load_kw.parquet")
    print(f"legacy load_kw: {len(keep)} of {len(coverage)} meters kept, {len(loads)} steps")
    profiles.voltage_profile(ceew).to_frame().to_parquet(out / "upstream_vm_pu.parquet")
    stats = profiles.voltage_stats(ceew[ceew.ts < "2020-01-01"])
    (out / "voltage_stats.json").write_text(json.dumps(stats, indent=2))
    weather = profiles.read_weather(config.RAW_DIR / "weather_mathura.json")
    weather.to_parquet(out / "weather_hourly.parquet")
    profiles.pv_from_weather(weather).to_frame().to_parquet(out / "pv_kw_per_kwp.parquet")


def main() -> None:
    out = config.PROCESSED_DIR
    out.mkdir(parents=True, exist_ok=True)
    raw_by_key = {}
    for f in config.CEEW_FILES:
        path = config.RAW_DIR / f.filename
        if path.exists():
            raw_by_key[(f.district, f.year)] = profiles.read_ceew_raw(path)
        else:
            print(f"skip {f.filename} (run scripts/download_data.py)")
    for district in config.DISTRICTS:
        frames = [df for (d, _), df in raw_by_key.items() if d == district]
        if not frames:
            continue
        weather = profiles.read_weather(config.RAW_DIR / f"weather_{district}.json")
        rep = build_district(frames, weather, config.SITES[district], out / "v2", district)
        print(district, {k: rep[k] for k in ("meters", "readings", "outage_share", "surge_share", "max_voltage_v")})
    build_legacy(raw_by_key, out)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add the `district` option to `day_inputs`** — in `engine/powerflow.py` replace `day_inputs` with:

```python
def day_inputs(date: str, district: str | None = None, processed_dir: Path | None = None) -> DayInputs:
    """Real profiles for one day; only meters with a complete day are used.

    `district=None` reads the Round 1 (legacy) Mathura files so existing results do not move;
    a district name reads the v2 per-district files.
    """
    if district is None:
        base, suffix = config.PROCESSED_DIR, ""
    else:
        base, suffix = (processed_dir or config.PROCESSED_DIR / "v2"), f"_{district}"
    loads = pd.read_parquet(base / f"load_kw{suffix}.parquet").loc[date]
    loads = loads.loc[:, loads.notna().all()]
    pv = pd.read_parquet(base / f"pv_kw_per_kwp{suffix}.parquet")["pv_kw_per_kwp"].reindex(loads.index).fillna(0)
    vm = pd.read_parquet(base / f"upstream_vm_pu{suffix}.parquet")["upstream_vm_pu"]
    vm = vm.reindex(loads.index).interpolate(limit_direction="both")
    if len(loads) != 96 or loads.shape[1] == 0:
        raise ValueError(f"{date}: no complete day of meter data")
    return DayInputs(date, loads, pv, vm)
```
and add `from pathlib import Path` to the imports.

- [ ] **Step 5: Ignore derived v2 data** — append to `.gitignore`:

```text
# derived per-district profiles (about 30 MB; rebuilt by scripts/build_data.py)
data/processed/v2/
```

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_build_data.py tests/test_engine.py -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add scripts engine tests .gitignore
git commit -m "feat(data): per-district build with quality report; day_inputs can read a district

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P2.4: Forecast metrics and split-conformal helpers (shared)

**Files:**
- Create: `ml/metrics.py`, `ml/conformal.py`, `tests/test_metrics_conformal.py`

**Interfaces:**
- Produces: `pinball(y, preds)`, `wis(y, p10, p50, p90)`, `coverage(y, lo, hi)`, `skill(mae, base_mae)`, `conformal_q(pred, y, alpha=0.2)`, `apply_conformal(pred, q, floor=None)`.

- [ ] **Step 1: Write the failing tests** — `tests/test_metrics_conformal.py`

```python
import numpy as np
import pandas as pd
import pytest

from ml.conformal import apply_conformal, conformal_q
from ml.metrics import coverage, pinball, skill, wis


def test_wis_for_a_point_inside_the_interval():
    # IS = 2 (width), |y - median| = 0  ->  (0.5*0 + 0.1*2) / 1.5
    assert wis(np.array([5.0]), np.array([4.0]), np.array([5.0]), np.array([6.0])) == pytest.approx(0.2 / 1.5)


def test_wis_penalises_a_miss():
    # y=8, interval 4..6, median 5: IS = 2 + 10*(8-6) = 22; (0.5*3 + 0.1*22) / 1.5
    assert wis(np.array([8.0]), np.array([4.0]), np.array([5.0]), np.array([6.0])) == pytest.approx(3.7 / 1.5)


def test_pinball_is_zero_for_a_perfect_forecast():
    y = np.array([1.0, 2.0, 3.0])
    assert pinball(y, {0.1: y, 0.5: y, 0.9: y}) == 0.0


def test_coverage_and_skill():
    assert coverage(np.array([1, 2, 3, 4]), np.array([0, 0, 0, 0]), np.array([2, 2, 2, 2])) == 0.5
    assert skill(0.9, 1.0) == pytest.approx(0.1)


def test_conformal_widening_reaches_the_target_coverage():
    rng = np.random.default_rng(1)
    y = pd.Series(rng.normal(0, 1, 12000))                                           # large enough that noise is about 0.8%
    pred = pd.DataFrame({"p10": -0.2, "p50": 0.0, "p90": 0.2}, index=y.index)        # far too narrow
    q = conformal_q(pred.iloc[:6000], y.iloc[:6000], alpha=0.2)
    adj = apply_conformal(pred.iloc[6000:], q)
    cov = ((y.iloc[6000:] >= adj["p10"]) & (y.iloc[6000:] <= adj["p90"])).mean()
    assert 0.77 <= cov <= 0.83


def test_apply_conformal_keeps_quantiles_ordered_and_respects_the_floor():
    pred = pd.DataFrame({"p10": [0.1], "p50": [0.2], "p90": [0.3]})
    adj = apply_conformal(pred, 0.5, floor=0.0)
    assert adj["p10"].iloc[0] == 0.0 and adj["p10"].iloc[0] <= adj["p50"].iloc[0] <= adj["p90"].iloc[0]
    shrunk = apply_conformal(pred, -0.5)
    assert shrunk["p10"].iloc[0] <= shrunk["p50"].iloc[0] <= shrunk["p90"].iloc[0]
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -m pytest tests/test_metrics_conformal.py -v`
Expected: FAIL (modules missing).

- [ ] **Step 3: Create `ml/metrics.py`**

```python
"""Forecast scores shared by every model: pinball loss, weighted interval score, coverage, skill."""
from __future__ import annotations

import numpy as np


def pinball(y, preds: dict) -> float:
    """Mean pinball loss over the given quantile levels (keys) and samples."""
    y = np.asarray(y, dtype=float)
    losses = []
    for level, q in preds.items():
        diff = y - np.asarray(q, dtype=float)
        losses.append(np.maximum(level * diff, (level - 1) * diff))
    return float(np.mean(losses))


def wis(y, p10, p50, p90, alpha: float = 0.2) -> float:
    """Weighted interval score for one central 80% interval plus the median (lower is better)."""
    y, lo, med, hi = (np.asarray(a, dtype=float) for a in (y, p10, p50, p90))
    interval = (hi - lo) + (2 / alpha) * np.maximum(lo - y, 0) + (2 / alpha) * np.maximum(y - hi, 0)
    return float(np.mean((0.5 * np.abs(y - med) + (alpha / 2) * interval) / 1.5))


def coverage(y, lo, hi) -> float:
    y, lo, hi = (np.asarray(a, dtype=float) for a in (y, lo, hi))
    return float(np.mean((y >= lo) & (y <= hi)))


def skill(mae: float, base_mae: float) -> float:
    """1 - MAE / baseline MAE: positive means better than the baseline."""
    return 1.0 - mae / base_mae
```

- [ ] **Step 4: Create `ml/conformal.py`**

```python
"""Split-conformal adjustment of a P10-P90 interval on a held-out calibration window."""
from __future__ import annotations

import numpy as np
import pandas as pd


def conformal_q(pred: pd.DataFrame, y: pd.Series, alpha: float = 0.2) -> float:
    """Amount by which both ends must move so the interval covers about 1 - alpha of calibration points."""
    scores = np.maximum(pred["p10"].to_numpy() - y.to_numpy(), y.to_numpy() - pred["p90"].to_numpy())
    n = len(scores)
    k = min(n, int(np.ceil((n + 1) * (1 - alpha))))
    return float(np.sort(scores)[k - 1])


def apply_conformal(pred: pd.DataFrame, q: float, floor: float | None = None) -> pd.DataFrame:
    out = pred.copy()
    out["p10"] = pred["p10"] - q
    out["p90"] = pred["p90"] + q
    if floor is not None:
        out[["p10", "p50", "p90"]] = out[["p10", "p50", "p90"]].clip(lower=floor)
    out["p10"] = np.minimum(out["p10"], out["p50"])
    out["p90"] = np.maximum(out["p90"], out["p50"])
    return out
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_metrics_conformal.py -v`
Expected: `6 passed`.

- [ ] **Step 6: Commit**

```bash
git add ml/metrics.py ml/conformal.py tests/test_metrics_conformal.py
git commit -m "feat(ml): shared forecast metrics (pinball, WIS, coverage, skill) and split-conformal helpers

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P2.5: Stochastic upstream-voltage model (A3)

**Files:**
- Create: `engine/upstream.py`, `tests/test_upstream.py`

**Interfaces:**
- Produces: `UpstreamModel.fit(series) -> UpstreamModel`, `.sample(date, n, prev_day_mean, rng) -> np.ndarray (n, 96)` in pu of 230 V, `evaluate(model, series, n=200, seed=0) -> dict`.
- Consumes: a 15-minute Series of the median customer voltage in pu (`upstream_vm_pu_<district>.parquet`).

- [ ] **Step 1: Write the failing tests** — `tests/test_upstream.py`

```python
import numpy as np
import pandas as pd
import pytest

from engine.upstream import UpstreamModel, evaluate


def _series(days=240, phi=0.6, sigma=0.01, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=days * 96, freq="15min")
    dev, means = 0.0, []
    for _ in range(days):
        dev = phi * dev + rng.normal(0, sigma)
        means.append(1.04 + dev)
    shape = 0.01 * np.sin(2 * np.pi * np.arange(96) / 96)
    v = np.concatenate([m + shape + rng.normal(0, 0.002, 96) for m in means])
    return pd.Series(v, index=idx)


def test_fit_recovers_the_day_to_day_persistence():
    model = UpstreamModel.fit(_series())
    assert 0.4 < model.phi < 0.8
    assert 0.007 < model.sigma_day < 0.014


def test_samples_have_the_right_shape_and_are_reproducible():
    model = UpstreamModel.fit(_series())
    a = model.sample(pd.Timestamp("2020-09-01"), 50, 1.04, np.random.default_rng(3))
    b = model.sample(pd.Timestamp("2020-09-01"), 50, 1.04, np.random.default_rng(3))
    assert a.shape == (50, 96) and np.array_equal(a, b)
    assert (a >= 0.8).all() and (a <= 1.2).all()


def test_a_high_previous_day_raises_the_forecast():
    model = UpstreamModel.fit(_series())
    low = model.sample(pd.Timestamp("2020-09-01"), 200, 1.02, np.random.default_rng(0)).mean()
    high = model.sample(pd.Timestamp("2020-09-01"), 200, 1.08, np.random.default_rng(0)).mean()
    assert high > low


def test_interval_for_the_daily_maximum_is_roughly_calibrated():
    train, test = _series(seed=0), _series(seed=1)
    rep = evaluate(UpstreamModel.fit(train), test, n=200)
    assert 0.65 <= rep["day_max_coverage_80"] <= 0.95 and rep["days"] > 100


def test_a_supplied_day_draw_moves_the_whole_day_and_is_reproducible():
    m = UpstreamModel.fit(_series())
    up = m.sample(pd.Timestamp("2021-06-15"), 3, 1.0, np.random.default_rng(0), day_z=np.array([-2.0, 0.0, 2.0]))
    means = up.mean(axis=1)
    assert means[0] < means[1] < means[2]
    again = m.sample(pd.Timestamp("2021-06-15"), 3, 1.0, np.random.default_rng(0), day_z=np.array([-2.0, 0.0, 2.0]))
    assert np.allclose(up, again)
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -m pytest tests/test_upstream.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Create `engine/upstream.py`**

```python
"""Day-ahead stochastic model of the voltage arriving at the transformer.

Daily mean = monthly mean + AR(1) deviation (yesterday's mean is known to the operator).
Intra-day = shape by (month, weekend) + AR(1) residual across 15-minute slots.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

SLOTS = 96
MIN_VALID_SLOTS = 80
LOW, HIGH = 0.80, 1.20


def _ar1(x: np.ndarray) -> tuple[float, float]:
    """Least-squares AR(1) coefficient and innovation standard deviation."""
    a, b = x[:-1], x[1:]
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    phi = float((a * b).sum() / (a * a).sum()) if len(a) > 2 and (a * a).sum() > 0 else 0.0
    phi = float(np.clip(phi, -0.99, 0.99))
    resid = b - phi * a
    return phi, float(resid.std()) if len(resid) > 2 else 0.0


@dataclass
class UpstreamModel:
    month_mean: dict
    phi: float
    sigma_day: float
    shape: dict
    resid_phi: float
    resid_sigma: float
    global_shape: np.ndarray = field(default_factory=lambda: np.zeros(SLOTS))

    @classmethod
    def fit(cls, series: pd.Series) -> "UpstreamModel":
        s = series.asfreq("15min")
        days = {d: g.to_numpy() for d, g in s.groupby(s.index.normalize()) if len(g) == SLOTS}
        valid = {d: v for d, v in days.items() if np.isfinite(v).sum() >= MIN_VALID_SLOTS}
        if len(valid) < 30:
            raise ValueError("need at least 30 usable days to fit the upstream-voltage model")
        day_mean = pd.Series({d: np.nanmean(v) for d, v in valid.items()}).sort_index()
        by_month = day_mean.groupby(day_mean.index.month).mean()
        month_mean = {int(m): float(v) for m, v in by_month.items()}
        dev = pd.Series({d: day_mean[d] - month_mean[d.month] for d in day_mean.index})
        dev = dev.reindex(pd.date_range(dev.index.min(), dev.index.max(), freq="D"))   # gaps stay NaN: pairs are consecutive days
        phi, sigma_day = _ar1(dev.to_numpy())

        shapes: dict = {}
        resid_all = []
        for d, v in valid.items():
            shapes.setdefault((d.month, int(d.dayofweek >= 5)), []).append(v - np.nanmean(v))
        shape = {k: np.nanmean(np.vstack(vs), axis=0) for k, vs in shapes.items()}
        global_shape = np.nanmean(np.vstack([v for vs in shapes.values() for v in vs]), axis=0)
        for d, v in valid.items():
            sh = shape[(d.month, int(d.dayofweek >= 5))]
            resid_all.append(v - np.nanmean(v) - sh)
        resid = np.concatenate([np.r_[r, np.nan] for r in resid_all])
        r_phi, r_sigma = _ar1(resid)
        return cls(month_mean, phi, sigma_day, shape, r_phi, r_sigma, global_shape)

    def sample(self, date, n: int, prev_day_mean: float, rng: np.random.Generator, day_z: np.ndarray | None = None) -> np.ndarray:
        """`n` day curves (n, 96). `day_z` (n,) supplies the standard-normal day-level draw when it must be coupled
        to other quantities (the scenario generator's copula); otherwise it is drawn here."""
        date = pd.Timestamp(date)
        prev = date - pd.Timedelta(days=1)
        mu = self.month_mean.get(date.month, float(np.mean(list(self.month_mean.values()))))
        mu_prev = self.month_mean.get(prev.month, mu)
        shock = rng.normal(0, 1, n) if day_z is None else np.asarray(day_z, float)
        day_mean = mu + self.phi * (prev_day_mean - mu_prev) + self.sigma_day * shock
        shape = self.shape.get((date.month, int(date.dayofweek >= 5)), self.global_shape)
        resid = np.zeros((n, SLOTS))
        var0 = self.resid_sigma ** 2 / max(1e-9, 1 - self.resid_phi ** 2)
        resid[:, 0] = rng.normal(0, np.sqrt(var0), n)
        for t in range(1, SLOTS):
            resid[:, t] = self.resid_phi * resid[:, t - 1] + rng.normal(0, self.resid_sigma, n)
        return np.clip(day_mean[:, None] + shape[None, :] + resid, LOW, HIGH)


def evaluate(model: UpstreamModel, series: pd.Series, n: int = 200, seed: int = 0) -> dict:
    """Coverage of the 10-90% interval of the daily maximum, given only yesterday's observed mean."""
    s = series.asfreq("15min")
    rng = np.random.default_rng(seed)
    hits, days = 0, 0
    prev_mean = None
    for d, g in s.groupby(s.index.normalize()):
        v = g.to_numpy()
        if len(v) != SLOTS or np.isfinite(v).sum() < MIN_VALID_SLOTS:
            prev_mean = None
            continue
        today_mean = float(np.nanmean(v))
        if prev_mean is not None:
            peak = model.sample(d, n, prev_mean, rng).max(axis=1)
            lo, hi = np.quantile(peak, [0.1, 0.9])
            hits += int(lo <= np.nanmax(v) <= hi)
            days += 1
        prev_mean = today_mean
    return {"days": days, "day_max_coverage_80": round(hits / days, 3) if days else float("nan")}


def main() -> None:
    from engine import config
    out = {}
    base = config.PROCESSED_DIR / "v2"
    train = pd.read_parquet(base / "upstream_vm_pu_mathura.parquet")["upstream_vm_pu"]
    model = UpstreamModel.fit(train[train.index < "2021-01-01"])
    out["mathura_2021"] = evaluate(model, train[train.index >= "2021-01-01"])
    bar = pd.read_parquet(base / "upstream_vm_pu_bareilly.parquet")["upstream_vm_pu"]
    out["bareilly_all_years_with_mathura_model"] = evaluate(model, bar)
    path = Path(__file__).resolve().parents[1] / "ml" / "reports" / "upstream_v2.json"
    path.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_upstream.py -v`
Expected: `5 passed`. If `test_fit_recovers…` fails on the φ range, print `model.phi`; the synthetic series has φ = 0.6, so a value outside 0.4–0.8 indicates a bug in `_ar1` or the day-mean alignment, not a tolerance problem.

- [ ] **Step 5: Commit**

```bash
git add engine/upstream.py tests/test_upstream.py
git commit -m "feat(upstream): stochastic day-ahead upstream-voltage model with held-out interval check

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P2.6: Demand forecast v2 (B1)

**Files:**
- Create: `ml/demand_v2.py`, `tests/test_demand_v2.py`

**Interfaces:**
- Produces: `street_mean`, `baselines`, `holiday_set`, `build_features`, `fit_model`, `predict`, `score`, `score_by_season`, `main`; report `ml/reports/demand_v2.json`.
- Consumes: `ml.forecast.PARAMS`, `ml.metrics`, `ml.conformal`, v2 profiles.

- [ ] **Step 1: Write the failing tests** — `tests/test_demand_v2.py`

```python
import numpy as np
import pandas as pd
import pytest

from ml.demand_v2 import baselines, build_features, fit_model, holiday_set, predict, score, street_mean

SMALL = {"n_estimators": 40, "learning_rate": 0.1, "num_leaves": 15, "min_child_samples": 20, "verbose": -1,
         "random_state": 42, "deterministic": True, "force_col_wise": True}


def _y(days=80):
    idx = pd.date_range("2020-01-01", periods=days * 96, freq="15min")
    rng = np.random.default_rng(0)
    daily = 0.4 + 0.15 * np.sin(2 * np.pi * (np.arange(len(idx)) % 96) / 96 - 1.2)
    weekly = 1 + 0.1 * (idx.dayofweek.to_numpy() >= 5)
    return pd.Series(daily * weekly + rng.normal(0, 0.01, len(idx)), index=idx)


def _temp(y):
    return pd.Series(25 + 5 * np.sin(np.arange(len(y)) / 960), index=y.index)


def test_baselines_are_exact_day_and_week_lags():
    y = _y(); b = baselines(y); t = y.index[-1]
    assert b["lag1d"][t] == y[t - pd.Timedelta(days=1)]
    assert b["lag7d"][t] == y[t - pd.Timedelta(days=7)]
    assert b["mean_1d_7d"][t] == pytest.approx((b["lag1d"][t] + b["lag7d"][t]) / 2)


def test_features_ignore_target_day_demand_and_temperature():
    y = _y(); temp = _temp(y); t = y.index[-1]
    before = build_features(y, temp, set())
    y2, t2 = y.copy(), temp.copy()
    y2[t], t2[t] = 99.0, 99.0
    after = build_features(y2, t2, set())
    pd.testing.assert_series_equal(before.loc[t], after.loc[t])


def test_oracle_temperature_is_added_only_on_request():
    y = _y(); temp = _temp(y)
    assert "temp_target" not in build_features(y, temp, set()).columns
    assert "temp_target" in build_features(y, temp, set(), oracle_temp=temp).columns


def test_holiday_flags_mark_the_target_date_and_the_day_after():
    y = _y(); temp = _temp(y)
    X = build_features(y, temp, {pd.Timestamp("2020-02-10").date()})
    assert X.loc["2020-02-10 12:00", "is_holiday"] == 1
    assert X.loc["2020-02-11 12:00", "is_holiday"] == 0 and X.loc["2020-02-11 12:00", "is_holiday_prev"] == 1


def test_holiday_set_knows_diwali_in_uttar_pradesh():
    assert pd.Timestamp("2019-10-27").date() in holiday_set([2019], "UP")


def test_street_mean_needs_enough_meters():
    idx = pd.date_range("2020-01-01", periods=3, freq="15min")
    loads = pd.DataFrame({f"m{i}": [1.0, 1.0, np.nan] for i in range(6)}, index=idx)
    loads.iloc[2, :2] = [1.0, 1.0]
    out = street_mean(loads)
    assert out.iloc[0] == 1.0 and np.isnan(out.iloc[2])


def test_end_to_end_forecast_is_ordered_and_beats_nothing_silly():
    y = _y(); temp = _temp(y)
    train_end = pd.Timestamp("2020-03-01")
    model = fit_model(y, temp, set(), "lag7d", train_end, calib_days=14, params=SMALL)
    frame = predict(model, y, temp, set())
    test = frame[frame.index >= train_end]
    assert (test["p10"] <= test["p50"]).all() and (test["p50"] <= test["p90"]).all()
    s = score(test)
    assert s["n"] > 500 and np.isfinite(s["skill_vs_best_baseline"]) and 0.5 <= s["coverage"] <= 1.0
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -m pytest tests/test_demand_v2.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Create `ml/demand_v2.py`**

```python
"""Demand forecast v2: all seasons, holiday flags, conformal intervals, time and district hold-out.

Target: mean kW per home across the meters present, 15-minute (Round 1 used the same quantity).
Two variants are always reported: STRICT (only lagged temperature) and ORACLE (target-day ERA5
temperature, an upper bound on what a good day-ahead temperature forecast could add).

Usage:  python -m ml.demand_v2        (needs data/processed/v2 from scripts/build_data.py)
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import holidays
import lightgbm as lgb
import numpy as np
import pandas as pd

from engine import config
from ml.conformal import apply_conformal, conformal_q
from ml.forecast import PARAMS
from ml.metrics import coverage, skill, wis

SLOTS_PER_DAY = 96
EPS = 0.05
QUANTILES = {"p10": 0.1, "p50": 0.5, "p90": 0.9}
BASES = ("lag1d", "lag7d", "mean_1d_7d")
REPORT = Path(__file__).resolve().parent / "reports" / "demand_v2.json"
SEASON = {12: "DJF", 1: "DJF", 2: "DJF", 3: "MAM", 4: "MAM", 5: "MAM", 6: "JJA", 7: "JJA", 8: "JJA",
          9: "SON", 10: "SON", 11: "SON"}


def street_mean(loads: pd.DataFrame, min_meters: int = 5) -> pd.Series:
    """Mean kW per home over the meters present; NaN when fewer than `min_meters` report."""
    mean = loads.mean(axis=1).where(loads.notna().sum(axis=1) >= min_meters)
    return mean.asfreq("15min").rename("kw_per_home")


def baselines(y: pd.Series) -> dict[str, pd.Series]:
    d1, d7 = y.shift(SLOTS_PER_DAY), y.shift(7 * SLOTS_PER_DAY)
    return {"lag1d": d1, "lag7d": d7, "mean_1d_7d": (d1 + d7) / 2}


def holiday_set(years, subdiv: str = "UP") -> set[date]:
    return set(holidays.country_holidays("IN", subdiv=subdiv, years=list(years)).keys())


def build_features(y: pd.Series, temp: pd.Series, hol: set, oracle_temp: pd.Series | None = None) -> pd.DataFrame:
    """Every column is known before the target interval begins, except `temp_target` (oracle only)."""
    b = baselines(y)
    same_slot = pd.concat([y.shift(k * SLOTS_PER_DAY) for k in range(1, 8)], axis=1)
    roll7 = same_slot.mean(axis=1).where(same_slot.notna().sum(axis=1) >= 4)
    idx = y.index
    day = pd.Series(idx.date, index=idx)
    prev_day = pd.Series((idx - pd.Timedelta(days=1)).date, index=idx)
    temp = temp.reindex(idx)
    doy = idx.dayofyear.to_numpy()
    X = pd.DataFrame({
        "ratio_1d_7d": np.log((b["lag1d"] + EPS) / (b["lag7d"] + EPS)),
        "ratio_roll7_1d": np.log((roll7 + EPS) / (b["lag1d"] + EPS)),
        "slot": idx.hour * 4 + idx.minute // 15,
        "dow": idx.dayofweek,
        "sin_doy": np.sin(2 * np.pi * doy / 365.25),
        "cos_doy": np.cos(2 * np.pi * doy / 365.25),
        "is_holiday": day.isin(hol).astype(int),
        "is_holiday_prev": prev_day.isin(hol).astype(int),
        "temp_lag_1d": temp.shift(SLOTS_PER_DAY),
        "temp_change_lagged": temp.shift(SLOTS_PER_DAY) - temp.shift(2 * SLOTS_PER_DAY),
    }, index=idx)
    if oracle_temp is not None:
        X["temp_target"] = oracle_temp.reindex(idx)
    return X


def choose_base(y: pd.Series, upto: pd.Timestamp) -> str:
    b = baselines(y)
    mask = y.index < upto
    return min(BASES, key=lambda n: float((b[n][mask] - y[mask]).abs().mean()))


def fit_model(y: pd.Series, temp: pd.Series, hol: set, base_name: str, train_end: pd.Timestamp,
              calib_days: int = 60, params: dict | None = None, oracle: bool = False) -> dict:
    X = build_features(y, temp, hol, oracle_temp=temp if oracle else None)
    base = baselines(y)[base_name]
    target = np.log((y + EPS) / (base + EPS))
    ok = X.notna().all(axis=1) & target.notna() & base.notna()
    X, target, base, yy = X[ok], target[ok], base[ok], y[ok]
    calib_start = train_end - pd.Timedelta(days=calib_days)
    train = X.index < calib_start
    calib = (X.index >= calib_start) & (X.index < train_end)
    p = dict(PARAMS if params is None else params)
    models = {q: lgb.LGBMRegressor(objective="quantile", alpha=a, **p).fit(X[train], target[train])
              for q, a in QUANTILES.items()}
    model = {"models": models, "base_name": base_name, "oracle": oracle, "columns": list(X.columns),
             "train_end": train_end, "q": 0.0}
    cal = _predict_level(model, X[calib], base[calib])
    model["q"] = conformal_q(cal, yy[calib])
    model["n_train"] = int(train.sum())
    return model


def _predict_level(model: dict, X: pd.DataFrame, base: pd.Series) -> pd.DataFrame:
    raw = pd.DataFrame({q: m.predict(X[model["columns"]]) for q, m in model["models"].items()}, index=X.index)
    level = np.exp(raw).mul(base + EPS, axis=0) - EPS
    level[:] = np.sort(level.clip(lower=0).to_numpy(), axis=1)
    return level


def predict(model: dict, y: pd.Series, temp: pd.Series, hol: set) -> pd.DataFrame:
    X = build_features(y, temp, hol, oracle_temp=temp if model["oracle"] else None)
    b = baselines(y)
    ok = X.notna().all(axis=1) & y.notna() & b["lag1d"].notna() & b["lag7d"].notna()
    X, yy = X[ok], y[ok]
    level = _predict_level(model, X, b[model["base_name"]][ok])
    out = apply_conformal(level, model["q"], floor=0.0)
    out["actual"] = yy
    for n in BASES:
        out[n] = b[n][ok]
    return out


def score(frame: pd.DataFrame) -> dict:
    mae = float((frame["p50"] - frame["actual"]).abs().mean())
    res = {"n": int(len(frame)), "mae_p50": round(mae, 4),
           "coverage": round(coverage(frame["actual"], frame["p10"], frame["p90"]), 3),
           "wis": round(wis(frame["actual"], frame["p10"], frame["p50"], frame["p90"]), 4)}
    base_mae = {n: float((frame[n] - frame["actual"]).abs().mean()) for n in BASES}
    for n, m in base_mae.items():
        res[f"mae_{n}"] = round(m, 4)
        res[f"skill_vs_{n}"] = round(skill(mae, m), 3)
    res["best_baseline"] = min(base_mae, key=base_mae.get)
    res["skill_vs_best_baseline"] = round(skill(mae, min(base_mae.values())), 3)
    return res


def score_by_season(frame: pd.DataFrame) -> dict:
    return {s: score(g) for s, g in frame.groupby(frame.index.month.map(SEASON)) if len(g) > 200}


def _load(district: str) -> tuple[pd.Series, pd.Series]:
    base = config.PROCESSED_DIR / "v2"
    y = street_mean(pd.read_parquet(base / f"load_kw_{district}.parquet"))
    temp = pd.read_parquet(base / f"weather_hourly_{district}.parquet")["temperature_2m"]
    return y, temp.resample("15min").interpolate("time").reindex(y.index)


def main() -> None:
    hol = holiday_set(range(2019, 2022))
    y_m, t_m = _load("mathura")
    y_b, t_b = _load("bareilly")
    train_end = pd.Timestamp("2021-01-01")
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "target": "mean kW per home, 15 min",
              "protocols": {}, "gate_g4": {}}
    for variant, oracle in (("strict", False), ("oracle_weather", True)):
        base_name = choose_base(y_m, train_end)
        # Protocol 1: train Mathura before 2021, test Mathura 2021
        m1 = fit_model(y_m, t_m, hol, base_name, train_end, oracle=oracle)
        f1 = predict(m1, y_m, t_m, hol)
        test1 = f1[f1.index >= train_end]
        # Protocol 2: train all Mathura, test Bareilly (held-out district)
        m2 = fit_model(y_m, t_m, hol, base_name, y_m.dropna().index.max().floor("D"), oracle=oracle)
        test2 = predict(m2, y_b, t_b, hol)
        report["protocols"][variant] = {
            "base": base_name,
            "time_mathura_2021": {**score(test1), "by_season": score_by_season(test1)},
            "district_bareilly": {**score(test2), "by_season": score_by_season(test2)},
        }
    s = report["protocols"]["strict"]["time_mathura_2021"]
    report["gate_g4"] = {"skill_vs_best_baseline": s["skill_vs_best_baseline"], "coverage": s["coverage"],
                         "passed": bool(s["skill_vs_best_baseline"] >= 0.10 and 0.78 <= s["coverage"] <= 0.82)}
    REPORT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report["gate_g4"], indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_demand_v2.py -v`
Expected: `7 passed`. If `test_holiday_set_knows_diwali…` fails, run `python -c "import holidays; print(holidays.country_holidays('IN', subdiv='UP', years=[2019]).get('2019-10-27'))"`; it printed `Diwali (Deepavali)` on 9 Oct 2026 (research spike S5), so a failure means a different `holidays` version: pin the version that passes in `constraints.txt`.

- [ ] **Step 5: Commit**

```bash
git add ml/demand_v2.py tests/test_demand_v2.py
git commit -m "feat(demand): v2 forecaster with holiday flags, conformal intervals, time and district hold-out

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P2.7: Run on the real data and decide gate G4

**Files:**
- Create: `tests/test_realdata.py`, `docs/generated/data_v2.md`
- Generate (committed): `ml/reports/demand_v2.json`, `ml/reports/upstream_v2.json`

- [ ] **Step 1: Download and build** (about 1.05 GB; 10–30 minutes)

```bash
python scripts/download_data.py
python scripts/build_data.py
```
Expected: six `done ceew_*.csv` lines plus two weather files; `build_data` prints one dict per district and `legacy load_kw: 32 of 38 meters kept`.

- [ ] **Step 2: Prove the legacy files were reproduced**

```bash
python - <<'PY'
import io, subprocess
import pandas as pd
for name in ["load_kw", "upstream_vm_pu", "pv_kw_per_kwp"]:
    old = pd.read_parquet(io.BytesIO(subprocess.check_output(["git", "show", f"HEAD:data/processed/{name}.parquet"])))
    new = pd.read_parquet(f"data/processed/{name}.parquet")
    pd.testing.assert_frame_equal(old, new, check_exact=False, rtol=1e-5)
    print(name, "identical in value")
PY
```
Expected: three `identical in value` lines. A difference means the cleaning changed: stop and fix before anything else, because every Round 1 number depends on these files.

- [ ] **Step 3: Write the real-data checks** — `tests/test_realdata.py`

```python
import json

import pandas as pd
import pytest

from engine import config

pytestmark = pytest.mark.realdata
V2 = config.PROCESSED_DIR / "v2"


@pytest.mark.parametrize("district", config.DISTRICTS)
def test_district_files_and_quality(district):
    q = json.loads((V2 / f"quality_{district}.json").read_text())
    assert q["meters"] >= 25 and q["readings"] > 3_000_000
    assert 0 <= q["outage_share"] < 0.35 and q["max_voltage_v"] > 250
    loads = pd.read_parquet(V2 / f"load_kw_{district}.parquet")
    assert loads.index.freq is not None or len(loads) > 50_000
    assert loads.index.min().year == 2019 and loads.index.max().year >= 2021


def test_both_districts_have_voltage_above_the_nominal():
    for d in config.DISTRICTS:
        v = pd.read_parquet(V2 / f"upstream_vm_pu_{d}.parquet")["upstream_vm_pu"]
        assert v.median() > 1.0
```

- [ ] **Step 4: Run them**

Run: `python -m pytest -m realdata tests/test_realdata.py -v`
Expected: `3 passed`. Thresholds are deliberately loose; a failure means the data is not what the plan assumes (read `quality_<district>.json` and write down what it actually says before relaxing anything).

- [ ] **Step 5: Run the demand and upstream evaluations**

```bash
python -m ml.demand_v2
python -m engine.upstream
```
Expected: `ml/reports/demand_v2.json` and `ml/reports/upstream_v2.json` written; the first prints `{"skill_vs_best_baseline": ..., "coverage": ..., "passed": ...}`.

- [ ] **Step 6: Decide G4 from the numbers, in writing** — create `docs/generated/data_v2.md` containing: meters, readings, outage share, surge share, median voltage and share above 253 V per district and year (from `quality_<district>.json` `voltage_by_year`); the strict and oracle skill and coverage on both protocols; the gate result. Then follow exactly one branch:
  - **G4 passed:** promote `ml/demand_v2.py` as the demand model of record (model card in Phase 10).
  - **G4 failed:** keep Round 1's demand model in the API, state the true numbers (including that oracle-weather and the district protocol show), and do not describe the demand forecast as an AI improvement anywhere. This is an acceptable result; the day-ahead risk engine does not depend on demand skill because demand enters through analog days.
  Whichever branch applies, the upstream result is recorded the same way: if `day_max_coverage_80` is outside 0.65–0.95 on either protocol, note it in the Proof page backlog (Phase 9) rather than tuning until it looks good.

- [ ] **Step 7: Commit**

```bash
git add ml/reports docs/generated tests/test_realdata.py
git commit -m "data(v2): real-data build, demand v2 and upstream evaluations; gate G4 decision recorded

<paste the gate_g4 JSON and one line per protocol>

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

**Optional task P2.8 (cross-country check):** if RECON-SL can be downloaded without login (Zenodo or Kaggle), fit `ml/demand_v2` features on its 15-minute smart-meter series and report the same metrics; the aim is only to show whether the feature set transfers to another South Asian utility. Skip silently if the data is not freely downloadable; do not use a login-gated copy.


---

# PHASE 3: THE V2 ENGINE (PHASE-AWARE, BATCHED, CROSS-CHECKED)

**Deliverable:** one canonical in-memory model (`Network`, `DayScenarioBatch`, `Controls`, `DayResult`, `Violations`); a power-grid-model day solver that replays whole batches of scenarios with unbalanced single-phase homes, standard Volt/VAR and Volt/Watt, export limits, tap changes and temperature-corrected resistance; array-based violation checks; an independent pandapower reference; and a convergence and zero-sequence sensitivity report (gate G5).

**Evidence behind the design (spikes S1, S2 in section 2, re-measured with this code):** balanced engine 263.1 V peak on the 99-home street, round-robin single-phase homes 268.9 V, random phases 270.5 V, all on phase A 294.1 V; zero-sequence ratios 2 to 4 move the random-phase peak only between 268.4 V and 272.6 V; batch day under 0.1 s (balanced) and 0.3 s (unbalanced); transformer loading matches pandapower to 0.2 points when computed from current.

Run every command in this phase from the repository root with the virtual environment active. Tests that need the Round 1 data (`data/processed/*.parquet`) pass locally because that data is tracked in git.

### Task P3.1: Canonical types and the phase-aware network (A5, A8)

**Files:**
- Create: `engine/types.py`, `engine/network.py`
- Test: `tests/test_network.py`

**Interfaces:**
- Consumes: `engine.inverters.VoltVarCurve`, `VoltWattCurve` (P1.2); `engine.grid.build_grid` (Round 1).
- Produces: `TrafoSpec`, `Network` (with `with_phases`, `with_pv`, `with_topology`, `is_radial`, `replace`), `BatterySpec`, `DayScenarioBatch` (with optional `ambient_c`), `Controls`, `DayResult`, `Violations`; `assign_phases(n, mode, seed)`, `from_pandapower(net, phases, r0_ratio, x0_ratio, seed, name)`.

**Design notes (so the code is not a surprise):**
- Positive and zero-sequence impedance are both stored per line. Zero-sequence defaults to three times positive sequence; this ratio is **unsourced**, so it is a parameter, it is written into `Network.provenance`, and task P3.4 reports the sensitivity.
- `Network` and `DayScenarioBatch` use `eq=False` because they hold arrays; compare them with `np.array_equal` on fields, never `==`.
- Conductor heating: IS 398 resistances are DC at 20 °C. `conductor_alpha = 0.00403 per °C` (aluminium) is general engineering knowledge and `conductor_delta_t_c = 10 K` above ambient is an **assumption**; both are fields so the Stress lab can vary them.

- [ ] **Step 1: Write the failing tests** — `tests/test_network.py`

```python
import warnings

import numpy as np
import pytest

from engine.grid import build_grid
from engine.network import assign_phases, from_pandapower

warnings.filterwarnings("ignore")


@pytest.fixture(scope="module")
def pp_net():
    return build_grid(1.0)


@pytest.fixture(scope="module")
def network(pp_net):
    return from_pandapower(pp_net, phases="round_robin")


def test_assign_phases_modes():
    assert assign_phases(7, "round_robin").tolist() == [0, 1, 2, 0, 1, 2, 0]
    assert assign_phases(5, "all_a").tolist() == [0] * 5
    a, b = assign_phases(60, "random", seed=1), assign_phases(60, "random", seed=1)
    assert a.tolist() == b.tolist() and set(a.tolist()) == {0, 1, 2}
    with pytest.raises(ValueError, match="unknown phase mode"):
        assign_phases(3, "diagonal")


def test_conversion_keeps_the_pandapower_structure(pp_net, network):
    assert network.n_homes == len(pp_net.load) == 99
    assert network.n_lines == len(pp_net.line)
    assert network.n_nodes == len(pp_net.bus)
    assert network.house_kwp.sum() == pytest.approx(pp_net.sgen.sn_mva.sum() * 1000)
    assert (network.house_kwp > 0).all()                        # 100% adoption, one system per home
    assert network.trafo.sn_va == pytest.approx(250e3)


def test_zero_sequence_is_an_explicit_multiple_of_positive_sequence(pp_net):
    n = from_pandapower(pp_net, r0_ratio=4.0, x0_ratio=2.0)
    assert np.allclose(n.line_r0_ohm, 4 * n.line_r1_ohm) and np.allclose(n.line_x0_ohm, 2 * n.line_x1_ohm)
    assert "unsourced" in n.provenance["zero_sequence"]


def test_the_converted_feeder_is_radial_and_a_loop_is_detected(network):
    assert network.is_radial()
    lv = network.lv_nodes
    tie = {"from": int(lv[0]), "to": int(lv[-1]), "r1": 0.1, "x1": 0.03, "r0": 0.3, "x0": 0.09, "c1": 0.0, "i_n": 200.0, "length_m": 50.0}
    assert not network.with_topology(add=[tie]).is_radial()
    assert network.with_topology(add=[tie], remove=[0]).n_lines == network.n_lines


def test_copies_do_not_change_the_original(network):
    moved = network.with_phases(np.zeros(network.n_homes, dtype=int)).with_pv(np.zeros(network.n_homes))
    assert moved.house_phase.sum() == 0 and moved.house_kwp.sum() == 0
    assert network.house_phase.sum() > 0 and network.house_kwp.sum() > 0
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/test_network.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'engine.network'`.

- [ ] **Step 3: Create `engine/types.py`**

```python
"""Canonical in-memory model shared by every v2 feature: network, scenarios, controls, results."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from engine.inverters import VoltVarCurve, VoltWattCurve

PHASES = ("A", "B", "C")


@dataclass(frozen=True)
class TrafoSpec:
    from_node: int
    to_node: int
    u1_v: float
    u2_v: float
    sn_va: float
    uk: float                 # relative short-circuit voltage (0.06 = 6%)
    pk_w: float
    i0: float                 # relative no-load current
    p0_w: float
    clock: int
    tap_min: int
    tap_max: int
    tap_nom: int
    tap_size_v: float         # volts per tap step on the HV side
    winding_from: str = "delta"
    winding_to: str = "wye_n"


@dataclass(frozen=True, eq=False)
class Network:
    name: str
    node_kv: np.ndarray                 # (N,) rated line-to-line kV
    lv_nodes: np.ndarray                # indices of LV nodes (< 1 kV)
    line_from: np.ndarray
    line_to: np.ndarray                 # (L,)
    line_r1_ohm: np.ndarray
    line_x1_ohm: np.ndarray
    line_r0_ohm: np.ndarray
    line_x0_ohm: np.ndarray
    line_c1_f: np.ndarray
    line_i_n_a: np.ndarray
    line_length_m: np.ndarray
    trafo: TrafoSpec
    source_node: int
    house_node: np.ndarray              # (H,) node index per home
    house_phase: np.ndarray             # (H,) 0, 1, 2 = A, B, C
    house_kwp: np.ndarray               # (H,) installed PV per home, 0 = none
    provenance: dict = field(default_factory=dict)
    node_xy: np.ndarray | None = None   # (N, 2) metres, for candidate tie switches
    conductor_alpha: float = 0.00403    # resistance temperature coefficient of aluminium per degree C (general knowledge, not sourced)
    conductor_delta_t_c: float = 10.0   # conductor temperature above ambient under load (assumption)

    @property
    def n_nodes(self) -> int:
        return len(self.node_kv)

    @property
    def n_homes(self) -> int:
        return len(self.house_node)

    @property
    def n_lines(self) -> int:
        return len(self.line_from)

    def replace(self, **changes) -> "Network":
        return replace(self, **changes)

    def with_phases(self, phases: np.ndarray) -> "Network":
        return replace(self, house_phase=np.asarray(phases, dtype=int))

    def with_pv(self, kwp: np.ndarray) -> "Network":
        return replace(self, house_kwp=np.asarray(kwp, dtype=float))

    def with_topology(self, add: list[dict] | None = None, remove: list[int] | None = None) -> "Network":
        """Copy with lines removed (by index) and lines added (dicts with from, to, r1, x1, r0, x0, c1, i_n)."""
        keep = np.ones(self.n_lines, dtype=bool)
        keep[list(remove or [])] = False
        cols = {"line_from": "from", "line_to": "to", "line_r1_ohm": "r1", "line_x1_ohm": "x1", "line_r0_ohm": "r0",
                "line_x0_ohm": "x0", "line_c1_f": "c1", "line_i_n_a": "i_n", "line_length_m": "length_m"}
        new = {name: np.r_[getattr(self, name)[keep], [a[key] for a in (add or [])]] for name, key in cols.items()}
        new["line_from"], new["line_to"] = new["line_from"].astype(int), new["line_to"].astype(int)
        return replace(self, **new)

    def is_radial(self) -> bool:
        """One connected tree over the LV nodes and the transformer's LV node (no loops, nothing islanded)."""
        import networkx as nx
        lv = set(self.lv_nodes.tolist())
        g = nx.Graph()
        g.add_nodes_from(lv)
        g.add_edges_from((int(a), int(b)) for a, b in zip(self.line_from, self.line_to) if a in lv and b in lv)
        return nx.is_connected(g) and g.number_of_edges() == g.number_of_nodes() - 1


@dataclass(frozen=True)
class BatterySpec:
    kw: float
    kwh: float
    node: int
    efficiency: float = 0.95
    soc_min: float = 0.10
    soc_max: float = 0.90
    soc_start: float = 0.50


@dataclass(frozen=True, eq=False)
class DayScenarioBatch:
    t: pd.DatetimeIndex                 # (T,)
    load_kw: np.ndarray                 # (S, T, H)
    pv_per_kwp: np.ndarray              # (S, T)
    upstream_pu: np.ndarray             # (S, T)
    load_pf: float = 0.95
    labels: tuple = ()
    ambient_c: np.ndarray | None = None  # (S, T) air temperature; when given, line resistance is temperature-corrected

    @property
    def shape(self) -> tuple[int, int]:
        return self.pv_per_kwp.shape


@dataclass(frozen=True, eq=False)
class Controls:
    tap_pos: int = 0
    volt_var: VoltVarCurve | None = None
    volt_watt: VoltWattCurve | None = None
    pf_fixed: float | None = None
    export_limit_kw: np.ndarray | None = None      # (T, H) or (H,) maximum net export per home
    curtail_keep: float | None = None
    battery: BatterySpec | None = None
    inverter_s_factor: float = 1.0
    name: str = ""


@dataclass
class DayResult:
    t: pd.DatetimeIndex
    u_pu: np.ndarray                    # (S, T, Nlv, 3) phase-to-neutral, pu of 230 V
    line_loading_pct: np.ndarray        # (S, T, L)
    trafo_loading_pct: np.ndarray       # (S, T)
    trafo_p_kw: np.ndarray              # (S, T) into the HV side; negative = reverse flow
    losses_kw: np.ndarray               # (S, T)
    q_loss_kvar: np.ndarray             # (S, T)
    pv_kw: np.ndarray                   # (S, T) delivered
    pv_avail_kw: np.ndarray             # (S, T) available before any control
    inverter_kvar: np.ndarray           # (S, T) absorbed, positive = absorbing
    battery_kw: np.ndarray              # (S, T) positive = charging
    neutral_a: np.ndarray               # (S, T)
    vuf_pct: np.ndarray                 # (S, T)
    converged: np.ndarray               # (S, T) bool
    passes: int = 1                     # inverter-control passes used


@dataclass
class Violations:
    over: np.ndarray
    under: np.ndarray
    line: np.ndarray
    trafo: np.ndarray
    solver: np.ndarray                  # all (S, T) bool
    unbalance: np.ndarray               # (S, T) bool, only set when a voltage-unbalance limit is given
    unsafe: np.ndarray
    rule_id: str
```

- [ ] **Step 4: Create `engine/network.py`**

```python
"""Build the canonical Network from a pandapower net, and assign single-phase homes to phases."""
from __future__ import annotations

import json

import numpy as np
import pandapower as pp

from engine.types import Network, TrafoSpec

PHASE_MODES = ("random", "round_robin", "all_a")


def assign_phases(n: int, mode: str = "random", seed: int = 42) -> np.ndarray:
    if mode == "round_robin":
        return np.arange(n) % 3
    if mode == "all_a":
        return np.zeros(n, dtype=int)
    if mode == "random":
        return np.random.default_rng(seed).integers(0, 3, n)
    raise ValueError(f"unknown phase mode {mode!r}; choose from {PHASE_MODES}")


def _house_pv(net: pp.pandapowerNet) -> np.ndarray:
    """Installed kWp per home: the n-th PV system on a bus goes to the n-th home on that bus."""
    homes_at: dict[int, list[int]] = {}
    for h, bus in enumerate(net.load.bus.to_numpy()):
        homes_at.setdefault(int(bus), []).append(h)
    kwp = np.zeros(len(net.load))
    for bus, sn in zip(net.sgen.bus.to_numpy(), net.sgen.sn_mva.to_numpy()):
        queue = homes_at.get(int(bus), [])
        if not queue:
            raise ValueError(f"PV system on bus {bus} has no home to belong to")
        kwp[queue.pop(0)] = sn * 1000.0
    return kwp


def _xy_metres(net: pp.pandapowerNet) -> np.ndarray | None:
    """SimBench stores lon/lat; convert to local metres for distance-based tie candidates."""
    try:
        lonlat = np.array([json.loads(g)["coordinates"] for g in net.bus.geo], dtype=float)
    except (KeyError, TypeError, ValueError):
        return None
    lon0, lat0 = lonlat[:, 0].mean(), lonlat[:, 1].mean()
    return np.c_[(lonlat[:, 0] - lon0) * 111_320 * np.cos(np.radians(lat0)), (lonlat[:, 1] - lat0) * 110_540]


def from_pandapower(net: pp.pandapowerNet, phases: str | np.ndarray = "random", r0_ratio: float = 3.0,
                    x0_ratio: float = 3.0, seed: int = 42, name: str = "simbench_rural2_india") -> Network:
    """Convert a pandapower net. Zero-sequence impedance is r0_ratio * r1 and x0_ratio * x1.

    The zero-sequence ratios are an unsourced assumption for a 4-wire Indian LV line; they are exposed
    so the sensitivity can be reported (gate G5).
    """
    bus_ids = net.bus.index.to_numpy()
    pos = {int(b): i for i, b in enumerate(bus_ids)}
    length = net.line.length_km.to_numpy()
    r1 = net.line.r_ohm_per_km.to_numpy() * length
    x1 = net.line.x_ohm_per_km.to_numpy() * length
    t = net.trafo.iloc[0]
    sn_va = float(t.sn_mva) * 1e6
    trafo = TrafoSpec(
        from_node=pos[int(t.hv_bus)], to_node=pos[int(t.lv_bus)],
        u1_v=float(t.vn_hv_kv) * 1000, u2_v=float(t.vn_lv_kv) * 1000, sn_va=sn_va,
        uk=float(t.vk_percent) / 100, pk_w=float(t.vkr_percent) / 100 * sn_va,
        i0=float(t.i0_percent) / 100, p0_w=float(t.pfe_kw) * 1000,
        clock=int(round(float(t.shift_degree) / 30)) % 12,
        tap_min=int(t.tap_min), tap_max=int(t.tap_max), tap_nom=int(t.tap_neutral),
        tap_size_v=float(t.tap_step_percent) / 100 * float(t.vn_hv_kv) * 1000,
    )
    n_homes = len(net.load)
    phase = assign_phases(n_homes, phases, seed) if isinstance(phases, str) else np.asarray(phases, dtype=int)
    return Network(
        name=name,
        node_kv=net.bus.vn_kv.to_numpy(float),
        lv_nodes=np.flatnonzero(net.bus.vn_kv.to_numpy() < 1),
        line_from=np.array([pos[int(b)] for b in net.line.from_bus]),
        line_to=np.array([pos[int(b)] for b in net.line.to_bus]),
        line_r1_ohm=r1, line_x1_ohm=x1, line_r0_ohm=r1 * r0_ratio, line_x0_ohm=x1 * x0_ratio,
        line_c1_f=net.line.c_nf_per_km.to_numpy() * 1e-9 * length,
        line_i_n_a=net.line.max_i_ka.to_numpy() * 1000,
        line_length_m=length * 1000,
        trafo=trafo,
        source_node=pos[int(net.ext_grid.bus.iloc[0])],
        house_node=np.array([pos[int(b)] for b in net.load.bus]),
        house_phase=phase,
        house_kwp=_house_pv(net),
        node_xy=_xy_metres(net),
        provenance={"topology": "benchmark: SimBench 1-LV-rural2, Indian overhead-line impedance",
                    "zero_sequence": f"assumed r0 = {r0_ratio} r1, x0 = {x0_ratio} x1 (unsourced)"},
    )
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_network.py -v`
Expected: `5 passed`.

- [ ] **Step 6: Commit**

```bash
git add engine/types.py engine/network.py tests/test_network.py
git commit -m "feat(engine): canonical Network/Scenario/Controls/Result types and phase-aware conversion (A5, A8)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P3.2: Array-based violation checks and the scenario bridge (C3, C5)

**Files:**
- Create: `engine/violations.py`, `engine/dayinputs.py`
- Test: `tests/test_violations.py`

**Interfaces:**
- Consumes: `DayResult`, `Violations`, `DayScenarioBatch`, `Network` (P3.1); `engine.rules.VoltageRule` (P1.1); `engine.powerflow.DayInputs` (Round 1).
- Produces: `evaluate(res, rule, *, vuf_limit=None) -> Violations`; `summarise(res, viol, s=0) -> dict` with the same keys as the Round 1 `run_day` summary plus `max_vuf_pct`, `max_neutral_a`, `battery_throughput_kwh`; `scenarios_from_legacy(inputs, network, seed=42)`.

**Rules the code encodes (from Global Constraints):** a step is unsafe if any LV phase voltage is outside the rule band, any line or the transformer exceeds 100% of its current rating, or the solver did not converge. A non-converged step has `NaN` voltages, so over- and under-voltage comparisons are `False` there, but `solver` is `True`, so the step is still unsafe. Voltage unbalance is a violation only when a limit is passed in (there is no verified Indian limit to hard-code; the Proof page reports VUF as information).

- [ ] **Step 1: Write the failing tests** — `tests/test_violations.py`

```python
import numpy as np
import pandas as pd
import pytest

from engine.rules import get_rule
from engine.types import DayResult
from engine.violations import evaluate, summarise


def _result(s=1, t=4, n=3):
    z = lambda *shape: np.zeros(shape)  # noqa: E731
    return DayResult(
        t=pd.date_range("2025-05-15", periods=t, freq="15min"), u_pu=np.full((s, t, n, 3), 1.0),
        line_loading_pct=z(s, t, 2), trafo_loading_pct=z(s, t), trafo_p_kw=np.full((s, t), 5.0), losses_kw=np.full((s, t), 0.4),
        q_loss_kvar=np.full((s, t), 0.1), pv_kw=np.full((s, t), 8.0), pv_avail_kw=np.full((s, t), 10.0), inverter_kvar=z(s, t),
        battery_kw=z(s, t), neutral_a=z(s, t), vuf_pct=z(s, t), converged=np.ones((s, t), dtype=bool))


def test_a_clean_day_has_no_violations():
    v = evaluate(_result(), get_rule("pm10"))
    assert not v.unsafe.any() and v.rule_id == "pm10"


def test_each_limit_is_detected_on_its_own_step():
    r = _result()
    r.u_pu[0, 0, 1, 2] = 1.11             # over, on phase C of one node
    r.u_pu[0, 1, 0, 0] = 0.89             # under
    r.line_loading_pct[0, 2, 1] = 101     # line overload
    r.trafo_loading_pct[0, 3] = 100.5     # transformer overload
    v = evaluate(r, get_rule("pm10"))
    assert v.over[0].tolist() == [True, False, False, False] and v.under[0].tolist() == [False, True, False, False]
    assert v.line[0].tolist() == [False, False, True, False] and v.trafo[0].tolist() == [False, False, False, True]
    assert v.unsafe.all()


def test_the_rule_decides_the_band():
    r = _result()
    r.u_pu[0, 0, 0, 0] = 1.07
    assert not evaluate(r, get_rule("pm10")).unsafe.any()
    assert evaluate(r, get_rule("up_2005")).over[0, 0]          # +-6% band


def test_solver_failure_is_unsafe_even_with_nan_voltages():
    r = _result()
    r.converged[0, 2] = False
    r.u_pu[0, 2] = np.nan
    v = evaluate(r, get_rule("pm10"))
    assert v.solver[0, 2] and v.unsafe[0, 2] and not v.over[0, 2] and not v.under[0, 2]


def test_voltage_unbalance_is_only_a_violation_when_a_limit_is_given():
    r = _result()
    r.vuf_pct[0, 1] = 3.5
    assert not evaluate(r, get_rule("pm10")).unsafe.any()
    assert evaluate(r, get_rule("pm10"), vuf_limit=2.0).unbalance[0].tolist() == [False, True, False, False]


def test_summary_keys_and_cost_accounting():
    r = _result()
    r.u_pu[0, 1, 0, 0] = 1.12
    r.trafo_p_kw[0, 3] = -2.0             # reverse flow
    r.inverter_kvar[0, :] = [1, 1, -1, 0]
    s = summarise(r, evaluate(r, get_rule("pm10")))
    assert s["violation_steps"] == 1 and s["solver_failed_steps"] == 0 and s["reverse_flow_steps"] == 1
    assert s["max_vm_pu"] == 1.12
    assert s["curtailed_kwh"] == pytest.approx(2.0 * 4 * 0.25)     # 2 kW lost for 4 steps of 0.25 h
    assert s["pv_kwh"] == pytest.approx(8.0)
    assert s["inverter_kvarh"] == pytest.approx(0.5)               # only absorption counts
    assert s["losses_kwh"] == pytest.approx(0.4)
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/test_violations.py -v`
Expected: `ModuleNotFoundError: No module named 'engine.violations'`.

- [ ] **Step 3: Create `engine/violations.py`**

```python
"""Array-based violation checks and day summaries (the vectorised counterpart of the legacy run_day)."""
from __future__ import annotations

import numpy as np

from engine.rules import VoltageRule
from engine.types import DayResult, Violations

STEP_H = 0.25
REVERSE_KW = 0.1


def evaluate(res: DayResult, rule: VoltageRule, *, vuf_limit: float | None = None) -> Violations:
    with np.errstate(invalid="ignore"):
        over = (res.u_pu > rule.vmax_pu).any(axis=(2, 3))
        under = (res.u_pu < rule.vmin_pu).any(axis=(2, 3))
        line = (res.line_loading_pct > 100).any(axis=2)
        trafo = res.trafo_loading_pct > 100
        unbalance = (res.vuf_pct > vuf_limit) if vuf_limit is not None else np.zeros_like(over)
    solver = ~res.converged
    unsafe = over | under | line | trafo | solver | unbalance
    return Violations(over=over, under=under, line=line, trafo=trafo, solver=solver, unbalance=unbalance,
                      unsafe=unsafe, rule_id=rule.id)


def summarise(res: DayResult, viol: Violations, s: int = 0) -> dict:
    """Headline numbers for scenario `s`, with the same keys as the legacy run_day summary where they exist."""
    ok = res.converged[s]
    u = res.u_pu[s][ok]
    pv_avail_kwh = float(res.pv_avail_kw[s].sum() * STEP_H)
    pv_kwh = float(res.pv_kw[s].sum() * STEP_H)
    return {
        "max_vm_pu": round(float(np.nanmax(u)), 4) if ok.any() else float("nan"),
        "min_vm_pu": round(float(np.nanmin(u)), 4) if ok.any() else float("nan"),
        "violation_steps": int(viol.unsafe[s].sum()),
        "solver_failed_steps": int((~ok).sum()),
        "reverse_flow_steps": int((res.trafo_p_kw[s][ok] < -REVERSE_KW).sum()),
        "max_trafo_loading_pct": round(float(np.nanmax(res.trafo_loading_pct[s][ok])), 1) if ok.any() else float("nan"),
        "max_line_loading_pct": round(float(np.nanmax(res.line_loading_pct[s][ok])), 1) if ok.any() else float("nan"),
        "reactive_loss_kvarh": round(float(np.nansum(res.q_loss_kvar[s]) * STEP_H), 2),
        "inverter_kvarh": round(float(np.clip(res.inverter_kvar[s], 0, None).sum() * STEP_H), 1),
        "pv_kwh": round(pv_kwh, 1),
        "curtailed_kwh": round(pv_avail_kwh - pv_kwh, 1),
        "losses_kwh": round(float(np.nansum(res.losses_kw[s]) * STEP_H), 2),
        "battery_throughput_kwh": round(float(np.abs(res.battery_kw[s]).sum() * STEP_H), 1),
        "max_vuf_pct": round(float(np.nanmax(res.vuf_pct[s][ok])), 2) if ok.any() else float("nan"),
        "max_neutral_a": round(float(np.nanmax(res.neutral_a[s][ok])), 1) if ok.any() else float("nan"),
    }
```

- [ ] **Step 4: Create `engine/dayinputs.py`**

```python
"""Bridge from the Round 1 DayInputs (one real day) to the batch scenario format."""
from __future__ import annotations

import numpy as np

from engine.powerflow import DayInputs
from engine.types import DayScenarioBatch, Network

LOAD_POWER_FACTOR = 0.95


def scenarios_from_legacy(inputs: DayInputs, network: Network, seed: int = 42) -> DayScenarioBatch:
    """One scenario: the same meter-to-home assignment as the legacy engine (seeded rng.choice)."""
    meters = np.random.default_rng(seed).choice(np.asarray(inputs.load_kw.columns), network.n_homes)
    return DayScenarioBatch(
        t=inputs.load_kw.index,
        load_kw=inputs.load_kw[meters].to_numpy(dtype=float)[None, :, :],
        pv_per_kwp=inputs.pv_kw_per_kwp.to_numpy(dtype=float)[None, :],
        upstream_pu=inputs.upstream_vm_pu.to_numpy(dtype=float)[None, :],
        load_pf=LOAD_POWER_FACTOR,
        labels=(inputs.date,),
    )
```

- [ ] **Step 5: Run the tests**

Run: `python -m pytest tests/test_violations.py -v`
Expected: `6 passed`.

- [ ] **Step 6: Commit**

```bash
git add engine/violations.py engine/dayinputs.py tests/test_violations.py
git commit -m "feat(engine): array-based violation checks, summaries and legacy scenario bridge (C3, C5)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P3.3: The batch day solver, the pandapower reference and parity (C4, C2, A8)

**Files:**
- Create: `engine/solver.py`, `engine/reference.py`
- Test: `tests/test_solver.py`, `tests/test_solver_parity.py`, `tests/test_performance.py`
- Modify: `.github/workflows/nightly.yml` (last line only)

**Interfaces:**
- Consumes: P3.1, P3.2; `engine.inverters` curves (P1.2); `engine.rules.get_rule` (P1.1).
- Produces: `DaySolver(network, *, asymmetric=True, backend="pgm").solve(scn, controls=Controls()) -> DayResult`; `PgmBackend` (adapter); `engine.reference.pandapower_day(inputs, tap=0, pv_share=1.0) -> (voltages (96, buses), loading (96,))`.

**Design notes:**
1. **Batching.** Scenarios and steps are one batch dimension `B = S × T`. Updates carry per-home active and reactive power (as load and as generator), the source voltage and the tap position. Each home is a single-phase load and generator on its own phase (asymmetric) or a balanced three-phase injection (symmetric).
2. **Failures are masked, never hidden.** If power-grid-model raises `PowerGridBatchError`, the engine reruns with `continue_on_batch_error=True`, marks the failed rows `converged=False` and sets their outputs to `NaN`; `violations.evaluate` turns that into an unsafe step.
3. **Transformer loading is computed from current**, not from power-grid-model's apparent-power `loading`, because the thermal rating is a current rating and the S-based figure reads up to 4 points higher above nominal voltage. The worst phase is used when unbalanced.
4. **Neutral current and unbalance.** power-grid-model's asymmetric result has no phase angle on branch currents, so the neutral current is the magnitude of the sum of the three phase currents rebuilt from `S = V·I*` at the transformer's low-voltage terminals. Voltage unbalance is the negative-to-positive sequence ratio, worst LV node.
5. **Standard inverter control** is a damped fixed point over whole batches: compute each home's voltage, evaluate the Volt/VAR and Volt/Watt curves, move the setpoints a fraction (`damping = 0.3`) toward the targets, re-solve, and stop when no setpoint moves more than 1 W. Damping 0.5 oscillated with both curves active; 0.3 settles in about 24 passes with no unconverged rows. Reactive power is limited to `sqrt(S² − P²)`, with `S = installed kWp × inverter_s_factor`.
6. **Temperature-corrected resistance.** A line's resistance cannot be changed inside a power-grid-model batch update, so resistances are binned (step 0.02 of the 20 °C value) and one cached model is built per bin; rows are solved per bin and merged. With no `ambient_c` the base model is used.
7. **Battery control** is sequential (the state of charge couples the steps) and is added in P6.5 as `engine.fixes.battery`; `DaySolver.solve` rejects `controls.battery` with a clear error rather than ignoring it.

- [ ] **Step 1: Write the failing tests** — `tests/test_solver.py`

```python
import warnings

import numpy as np
import pytest

from engine.dayinputs import scenarios_from_legacy
from engine.grid import build_grid
from engine.inverters import VoltVarCurve, VoltWattCurve
from engine.network import assign_phases, from_pandapower
from engine.powerflow import day_inputs
from engine.rules import get_rule
from engine.solver import DaySolver
from engine.types import Controls, DayScenarioBatch
from engine.violations import evaluate, summarise

warnings.filterwarnings("ignore")
DATE = "2019-05-15"


@pytest.fixture(scope="module")
def inputs():
    return day_inputs(DATE)


@pytest.fixture(scope="module")
def network():
    return from_pandapower(build_grid(1.0), phases="round_robin")


@pytest.fixture(scope="module")
def scn(inputs, network):
    return scenarios_from_legacy(inputs, network)


@pytest.fixture(scope="module")
def sym(network):
    return DaySolver(network, asymmetric=False)


def test_unsafe_step_count_matches_the_legacy_engine(sym, scn):
    res = sym.solve(scn)
    viol = evaluate(res, get_rule("pm10"))
    s = summarise(res, viol)
    assert s["violation_steps"] == 26 and s["solver_failed_steps"] == 0       # legacy S4: 26 steps = 6 h 30 min
    assert s["max_vm_pu"] * 230 == pytest.approx(263.1, abs=0.3)
    assert s["max_trafo_loading_pct"] == pytest.approx(44.5, abs=0.3)
    assert s["reverse_flow_steps"] > 0


def test_asymmetric_engine_equals_symmetric_when_every_home_is_split_over_three_phases(network, scn, sym):
    # Each home becomes three co-located homes with a third of the load and PV, one per phase.
    h = network.n_homes
    net3 = network.replace(house_node=np.repeat(network.house_node, 3), house_phase=np.tile([0, 1, 2], h),
                           house_kwp=np.repeat(network.house_kwp / 3, 3))
    scn3 = DayScenarioBatch(scn.t, np.repeat(scn.load_kw / 3, 3, axis=2), scn.pv_per_kwp, scn.upstream_pu, scn.load_pf, scn.labels)
    res3 = DaySolver(net3, asymmetric=True).solve(scn3)
    res = sym.solve(scn)
    for phase in range(3):
        assert np.abs(res3.u_pu[0, :, :, phase] - res.u_pu[0, :, :, 0]).max() < 5e-4
    assert res3.vuf_pct.max() < 0.05 and res3.neutral_a.max() < 1.0


def test_single_phase_homes_give_higher_voltage_and_unbalance_than_the_balanced_model(network, scn, sym):
    balanced = sym.solve(scn).u_pu.max()
    peaks = {}
    for mode in ("round_robin", "random", "all_a"):
        res = DaySolver(network.with_phases(assign_phases(network.n_homes, mode)), asymmetric=True).solve(scn)
        assert res.converged.all()
        peaks[mode] = (res.u_pu.max(), res.vuf_pct.max())
    assert peaks["round_robin"][0] > balanced
    assert peaks["round_robin"][0] < peaks["random"][0] < peaks["all_a"][0]
    assert peaks["round_robin"][1] < peaks["random"][1] < peaks["all_a"][1]


def test_standard_volt_var_clears_the_day_in_the_symmetric_engine(sym, scn):
    res = sym.solve(scn, Controls(volt_var=VoltVarCurve()))
    s = summarise(res, evaluate(res, get_rule("pm10")))
    assert s["violation_steps"] == 0
    assert s["max_vm_pu"] * 230 == pytest.approx(250.1, abs=0.5) and s["min_vm_pu"] * 230 == pytest.approx(220.5, abs=0.5)
    assert s["max_trafo_loading_pct"] == pytest.approx(66.4, abs=1.0)
    assert 3 <= res.passes <= 40


def test_volt_watt_curtails_and_curtail_keep_matches_legacy(sym, scn):
    vw = summarise(*(lambda r: (r, evaluate(r, get_rule("pm10"))))(sym.solve(scn, Controls(volt_watt=VoltWattCurve()))))
    assert vw["curtailed_kwh"] > 0
    keep = sym.solve(scn, Controls(curtail_keep=0.6))
    s = summarise(keep, evaluate(keep, get_rule("pm10")))
    assert s["curtailed_kwh"] == pytest.approx(489.3, abs=1.0)           # legacy export_cap_60
    assert s["violation_steps"] == 15                                     # legacy: 3 h 45 min


def test_export_limit_caps_net_export_per_home(sym, scn, network):
    limit = np.full(network.n_homes, 0.5)                                 # 0.5 kW export per home
    res = sym.solve(scn, Controls(export_limit_kw=limit))
    exported = res.pv_kw[0] - scn.load_kw[0].sum(axis=1)
    assert (exported <= 0.5 * network.n_homes + 1e-6).all()
    assert res.pv_kw.sum() < res.pv_avail_kw.sum()


def test_stacked_scenarios_equal_individual_runs(sym, scn):
    both = DayScenarioBatch(scn.t, np.concatenate([scn.load_kw, scn.load_kw * 0.5]), np.concatenate([scn.pv_per_kwp] * 2),
                            np.concatenate([scn.upstream_pu] * 2), scn.load_pf, ("a", "b"))
    r2 = sym.solve(both)
    r_a, r_b = sym.solve(scn), sym.solve(DayScenarioBatch(scn.t, scn.load_kw * 0.5, scn.pv_per_kwp, scn.upstream_pu, scn.load_pf, ("b",)))
    assert np.allclose(r2.u_pu[0], r_a.u_pu[0], atol=1e-9) and np.allclose(r2.u_pu[1], r_b.u_pu[0], atol=1e-9)


def test_an_impossible_scenario_is_masked_not_hidden(sym, scn):
    bad = DayScenarioBatch(scn.t, np.concatenate([scn.load_kw, scn.load_kw * 5000]), np.concatenate([scn.pv_per_kwp] * 2),
                           np.concatenate([scn.upstream_pu] * 2), scn.load_pf, ("ok", "impossible"))
    res = sym.solve(bad)
    assert res.converged[0].all() and not res.converged[1].any()
    viol = evaluate(res, get_rule("pm10"))
    assert viol.solver[1].all() and viol.unsafe[1].all() and not np.isnan(res.u_pu[0]).any()


def test_hot_conductors_raise_the_voltage(network, scn):
    solver = DaySolver(network, asymmetric=False)
    cool = solver.solve(scn).u_pu.max()
    hot_scn = DayScenarioBatch(scn.t, scn.load_kw, scn.pv_per_kwp, scn.upstream_pu, scn.load_pf, scn.labels,
                               ambient_c=np.full(scn.shape, 40.0))
    hot = solver.solve(hot_scn).u_pu.max()
    assert hot > cool
    ref_scn = DayScenarioBatch(scn.t, scn.load_kw, scn.pv_per_kwp, scn.upstream_pu, scn.load_pf, scn.labels,
                               ambient_c=np.full(scn.shape, 10.0))     # 10 + 10 = 20 degrees C: scale exactly 1
    assert abs(solver.solve(ref_scn).u_pu.max() - cool) < 1e-9
```

Parity and speed live in their own files so the nightly job can run them alone:

`tests/test_solver_parity.py`

```python
import numpy as np
import pytest

from engine.dayinputs import scenarios_from_legacy
from engine.grid import build_grid
from engine.network import from_pandapower
from engine.powerflow import day_inputs
from engine.reference import pandapower_day
from engine.solver import DaySolver
from engine.types import Controls

DATE = "2019-05-15"


@pytest.fixture(scope="module")
def inputs():
    return day_inputs(DATE)


@pytest.fixture(scope="module")
def network():
    return from_pandapower(build_grid(1.0), phases="round_robin")


@pytest.fixture(scope="module")
def scn(inputs, network):
    return scenarios_from_legacy(inputs, network)


@pytest.mark.parametrize("tap", [0, 1])
def test_symmetric_engine_matches_pandapower(network, scn, inputs, tap):
    """Gate G1: the production engine agrees with the independent reference on the 99-home street."""
    res = DaySolver(network, asymmetric=False).solve(scn, Controls(tap_pos=tap))
    u_ref, trafo_ref = pandapower_day(inputs, tap)
    assert np.abs(res.u_pu[0, :, :, 0] - u_ref).max() < 2e-4            # 0.05 V
    assert np.abs(res.trafo_loading_pct[0] - trafo_ref).max() < 0.2
    assert res.converged.all()
```

`tests/test_performance.py`

```python
import time

import pytest

from engine.dayinputs import scenarios_from_legacy
from engine.grid import build_grid
from engine.network import from_pandapower
from engine.powerflow import day_inputs
from engine.solver import DaySolver


@pytest.fixture(scope="module")
def network():
    return from_pandapower(build_grid(1.0), phases="round_robin")


@pytest.fixture(scope="module")
def scn(network):
    return scenarios_from_legacy(day_inputs("2019-05-15"), network)


@pytest.mark.perf
def test_day_replay_speed_budgets(network, scn):
    sym_solver, asym_solver = DaySolver(network, asymmetric=False), DaySolver(network, asymmetric=True)
    sym_solver.solve(scn); asym_solver.solve(scn)                         # warm up
    t0 = time.perf_counter(); sym_solver.solve(scn); t_sym = time.perf_counter() - t0
    t0 = time.perf_counter(); asym_solver.solve(scn); t_asym = time.perf_counter() - t0
    assert t_sym < 0.1 and t_asym < 0.3, (t_sym, t_asym)
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/test_solver.py tests/test_solver_parity.py -v`
Expected: collection error `ModuleNotFoundError: No module named 'engine.solver'`.

- [ ] **Step 3: Create `engine/reference.py` (independent pandapower replay)**

```python
"""Independent pandapower replay of one real day: the reference the batch engine is checked against."""
from __future__ import annotations

import numpy as np
import pandapower as pp

from engine.grid import build_grid, lv_buses
from engine.powerflow import TAN_PHI, DayInputs, assign_meters


def pandapower_day(inputs: DayInputs, tap: int = 0, pv_share: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """LV bus voltages (96, buses) in pu and transformer loading (96,) in percent, balanced three-phase."""
    net = build_grid(pv_share)
    net.trafo["tap_pos"] = tap
    meters = assign_meters(net, inputs.load_kw.columns)
    load = inputs.load_kw[meters].to_numpy() / 1000
    lv = lv_buses(net)
    voltages, loading = [], []
    for i in range(len(inputs.load_kw)):
        net.load["p_mw"], net.load["q_mvar"] = load[i], load[i] * TAN_PHI
        net.sgen["p_mw"], net.sgen["q_mvar"] = inputs.pv_kw_per_kwp.iloc[i] * net.sgen.sn_mva, 0.0
        net.ext_grid["vm_pu"] = inputs.upstream_vm_pu.iloc[i]
        pp.runpp(net, numba=True, init="results" if i else "auto")
        voltages.append(net.res_bus.loc[lv, "vm_pu"].to_numpy())
        loading.append(float(net.res_trafo.loading_percent.iloc[0]))
    return np.array(voltages), np.array(loading)
```

- [ ] **Step 4: Create `engine/solver.py`**

```python
"""Day solver: Network + scenarios + controls -> DayResult, on the power-grid-model batch engine.

All scenarios and all 96 steps are one batch dimension (B = S x T). Smart-inverter control is a damped
fixed point over whole batches (about 8-10 passes), not a Python loop over steps.
"""
from __future__ import annotations

import numpy as np
from power_grid_model import CalculationMethod, LoadGenType, PowerGridModel, WindingType, initialize_array
from power_grid_model.enum import BranchSide
from power_grid_model.errors import PowerGridBatchError

from engine.types import Controls, DayResult, DayScenarioBatch, Network

NOMINAL_V = 230.0
SOURCE_ID, TRAFO_ID, LINE0, LOAD0, GEN0 = 5000, 2000, 10_000, 100_000, 200_000
_WINDING = {"delta": WindingType.delta, "wye": WindingType.wye, "wye_n": WindingType.wye_n}
A_OP = np.exp(2j * np.pi / 3)


class PgmBackend:
    """Thin adapter over PowerGridModel for one Network; one generator slot per home (zero where no PV)."""

    def __init__(self, net: Network, asymmetric: bool = True):
        self.net, self.asym = net, asymmetric
        n, n_l, n_h = net.n_nodes, net.n_lines, net.n_homes
        node = initialize_array("input", "node", n)
        node["id"] = np.arange(n)
        node["u_rated"] = net.node_kv * 1000

        line = initialize_array("input", "line", n_l)
        line["id"] = LINE0 + np.arange(n_l)
        line["from_node"], line["to_node"] = net.line_from, net.line_to
        line["from_status"] = line["to_status"] = 1
        line["r1"], line["x1"], line["c1"], line["tan1"] = net.line_r1_ohm, net.line_x1_ohm, net.line_c1_f, 0.0
        line["r0"], line["x0"], line["c0"], line["tan0"] = net.line_r0_ohm, net.line_x0_ohm, net.line_c1_f, 0.0
        line["i_n"] = net.line_i_n_a

        tr_spec = net.trafo
        tr = initialize_array("input", "transformer", 1)
        tr["id"], tr["from_node"], tr["to_node"] = TRAFO_ID, tr_spec.from_node, tr_spec.to_node
        tr["from_status"] = tr["to_status"] = 1
        tr["u1"], tr["u2"], tr["sn"] = tr_spec.u1_v, tr_spec.u2_v, tr_spec.sn_va
        tr["uk"], tr["pk"], tr["i0"], tr["p0"] = tr_spec.uk, tr_spec.pk_w, tr_spec.i0, tr_spec.p0_w
        tr["winding_from"], tr["winding_to"] = _WINDING[tr_spec.winding_from], _WINDING[tr_spec.winding_to]
        tr["clock"] = tr_spec.clock
        tr["tap_side"] = BranchSide.from_side
        tr["tap_pos"], tr["tap_min"], tr["tap_max"] = 0, tr_spec.tap_min, tr_spec.tap_max
        tr["tap_nom"], tr["tap_size"] = tr_spec.tap_nom, tr_spec.tap_size_v

        src = initialize_array("input", "source", 1)
        src["id"], src["node"], src["status"], src["u_ref"] = SOURCE_ID, net.source_node, 1, 1.0

        kind = "asym" if asymmetric else "sym"
        self.kind = kind
        load = initialize_array("input", f"{kind}_load", n_h)
        load["id"], load["node"], load["status"], load["type"] = LOAD0 + np.arange(n_h), net.house_node, 1, LoadGenType.const_power
        gen = initialize_array("input", f"{kind}_gen", n_h)
        gen["id"], gen["node"], gen["status"], gen["type"] = GEN0 + np.arange(n_h), net.house_node, 1, LoadGenType.const_power
        self.load_id, self.gen_id = load["id"].copy(), gen["id"].copy()

        data = {"node": node, "line": line, "transformer": tr, "source": src,
                f"{kind}_load": load, f"{kind}_gen": gen}
        self._data = data
        self.model = PowerGridModel(data, system_frequency=50.0)
        self._models: dict[float, PowerGridModel] = {}
        self.onehot = np.eye(3)[net.house_phase]                       # (H, 3)
        self.lv = net.lv_nodes

    def _spread(self, a: np.ndarray) -> np.ndarray:
        """(B, H) per-home watts -> (B, H, 3) with each home on its own phase (asymmetric) or unchanged."""
        return a[:, :, None] * self.onehot[None, :, :] if self.asym else a

    def _model_for(self, scale: float) -> PowerGridModel:
        """Line resistance cannot change inside a batch update, so each resistance bin gets its own cached model."""
        if scale not in self._models:
            lines = self._data["line"].copy()
            lines["r1"], lines["r0"] = lines["r1"] * scale, lines["r0"] * scale
            self._models[scale] = PowerGridModel({**self._data, "line": lines}, system_frequency=50.0)
        return self._models[scale]

    def calculate(self, p_load_w, q_load_w, p_gen_w, q_gen_w, upstream_pu, tap_pos: int, r_scale=None, step: float = 0.02) -> dict:
        if r_scale is None:
            return self._calculate_with(self.model, p_load_w, q_load_w, p_gen_w, q_gen_w, upstream_pu, tap_pos)
        bins = np.round(np.asarray(r_scale) / step) * step
        out = None
        for value in np.unique(bins):
            idx = np.flatnonzero(bins == value)
            part = self._calculate_with(self._model_for(float(round(value, 6))), p_load_w[idx], q_load_w[idx], p_gen_w[idx],
                                        q_gen_w[idx], upstream_pu[idx], tap_pos)
            if out is None:
                out = {k: np.empty((len(upstream_pu),) + v.shape[1:], dtype=v.dtype) for k, v in part.items()}
            for k, v in part.items():
                out[k][idx] = v
        return out

    def _calculate_with(self, model, p_load_w, q_load_w, p_gen_w, q_gen_w, upstream_pu, tap_pos: int) -> dict:
        b, n_h = p_load_w.shape
        ul = initialize_array("update", f"{self.kind}_load", (b, n_h))
        ul["id"], ul["p_specified"], ul["q_specified"] = self.load_id, self._spread(p_load_w), self._spread(q_load_w)
        ug = initialize_array("update", f"{self.kind}_gen", (b, n_h))
        ug["id"], ug["p_specified"], ug["q_specified"] = self.gen_id, self._spread(p_gen_w), self._spread(q_gen_w)
        us = initialize_array("update", "source", (b, 1))
        us["id"], us["u_ref"] = SOURCE_ID, upstream_pu[:, None]
        ut = initialize_array("update", "transformer", (b, 1))
        ut["id"], ut["tap_pos"] = TRAFO_ID, tap_pos
        update = {f"{self.kind}_load": ul, f"{self.kind}_gen": ug, "source": us, "transformer": ut}

        def run(continue_on_error: bool):
            return model.calculate_power_flow(
                symmetric=not self.asym, error_tolerance=1e-8, max_iterations=40,
                calculation_method=CalculationMethod.newton_raphson, update_data=update,
                continue_on_batch_error=continue_on_error)

        failed = np.array([], dtype=int)
        try:
            res = run(False)
        except PowerGridBatchError as err:           # rare: recover the good rows, mask the bad ones
            failed = np.asarray(err.failed_scenarios, dtype=int)
            res = run(True)
        return self._extract(res, b, failed)

    def _trafo_loading(self, i_from, i_to) -> np.ndarray:
        """Current-based loading in percent (the thermal measure, as in pandapower), worst phase if unbalanced.

        power-grid-model's own `loading` is apparent power over rating, which reads higher whenever the
        voltage is above nominal, so it is not used.
        """
        spec = self.net.trafo
        rated_from = spec.sn_va / (np.sqrt(3) * spec.u1_v)
        rated_to = spec.sn_va / (np.sqrt(3) * spec.u2_v)
        i_from, i_to = np.asarray(i_from, dtype=float), np.asarray(i_to, dtype=float)
        worst_from = i_from if i_from.ndim == 1 else i_from.max(axis=-1)
        worst_to = i_to if i_to.ndim == 1 else i_to.max(axis=-1)
        return np.maximum(worst_from / rated_from, worst_to / rated_to) * 100

    def _extract(self, res: dict, b: int, failed: np.ndarray) -> dict:
        lv = self.lv
        node, line, trf = res["node"], res["line"], res["transformer"]
        if self.asym:
            u = node["u_pu"][:, lv, :].astype(float)
            ang = node["u_angle"][:, lv, :]
            v = u * np.exp(1j * ang)
            v1 = (v[..., 0] + A_OP * v[..., 1] + A_OP ** 2 * v[..., 2]) / 3
            v2 = (v[..., 0] + A_OP ** 2 * v[..., 1] + A_OP * v[..., 2]) / 3
            vuf = (np.abs(v2) / np.maximum(np.abs(v1), 1e-9)).max(axis=1) * 100
            # Phase currents at the transformer's LV side from S = V I*; the neutral carries their sum.
            nt = self.net.trafo.to_node
            v_to = node["u"][:, nt, :] * np.exp(1j * node["u_angle"][:, nt, :])
            s_to = trf["p_to"][:, 0, :] + 1j * trf["q_to"][:, 0, :]
            neutral = np.abs(np.conj(s_to / v_to).sum(axis=1))
            trafo_loading = self._trafo_loading(trf["i_from"][:, 0, :], trf["i_to"][:, 0, :])
            p_line = (line["p_from"] + line["p_to"]).sum(axis=-1).sum(axis=-1)
            q_line = (line["q_from"] + line["q_to"]).sum(axis=-1).sum(axis=-1)
            p_trf_in = trf["p_from"][:, 0, :].sum(axis=-1)
            p_trf_loss = (trf["p_from"] + trf["p_to"])[:, 0, :].sum(axis=-1)
            q_trf_loss = (trf["q_from"] + trf["q_to"])[:, 0, :].sum(axis=-1)
        else:
            u = np.repeat(node["u_pu"][:, lv, None], 3, axis=2).astype(float)
            vuf, neutral = np.zeros(b), np.zeros(b)
            p_line = (line["p_from"] + line["p_to"]).sum(axis=-1)
            q_line = (line["q_from"] + line["q_to"]).sum(axis=-1)
            trafo_loading = self._trafo_loading(trf["i_from"][:, 0], trf["i_to"][:, 0])
            p_trf_in = trf["p_from"][:, 0]
            p_trf_loss = (trf["p_from"] + trf["p_to"])[:, 0]
            q_trf_loss = (trf["q_from"] + trf["q_to"])[:, 0]
        out = {
            "u_pu": u,
            "line_loading_pct": np.asarray(line["loading"], dtype=float) * 100,
            "trafo_loading_pct": trafo_loading,
            "trafo_p_kw": p_trf_in / 1000,
            "losses_kw": (p_line + p_trf_loss) / 1000,
            "q_loss_kvar": (q_line + q_trf_loss) / 1000,
            "neutral_a": neutral, "vuf_pct": vuf,
            "converged": np.ones(b, dtype=bool),
        }
        if len(failed):
            out["converged"][failed] = False
            for key in ("u_pu", "line_loading_pct", "trafo_loading_pct", "trafo_p_kw", "losses_kw",
                        "q_loss_kvar", "neutral_a", "vuf_pct"):
                out[key] = out[key].astype(float)
                out[key][failed] = np.nan
        return out


class DaySolver:
    def __init__(self, network: Network, *, asymmetric: bool = True, backend: str = "pgm"):
        if backend != "pgm":
            raise ValueError("only the power-grid-model backend is available; the pandapower reference lives in engine.reference")
        self.network, self.asymmetric = network, asymmetric
        self.backend = PgmBackend(network, asymmetric)
        self._h_idx = np.array([int(np.flatnonzero(network.lv_nodes == n)[0]) for n in network.house_node])
        self.max_passes, self.damping, self.tol_kw = 80, 0.3, 1e-3

    def solve(self, scn: DayScenarioBatch, controls: Controls = Controls()) -> DayResult:
        if controls.battery is not None:
            raise NotImplementedError("battery control is a sequential solve added in the fix-tournament phase")
        net, (s, t) = self.network, scn.shape
        b, n_h = s * t, net.n_homes
        load_kw = scn.load_kw.reshape(b, n_h)
        p_load = load_kw * 1000.0
        q_load = p_load * np.tan(np.arccos(scn.load_pf))
        up = scn.upstream_pu.reshape(b)
        pv_avail = scn.pv_per_kwp.reshape(b, 1) * net.house_kwp[None, :]                    # kW
        p_cap = pv_avail.copy()
        if controls.curtail_keep is not None:
            p_cap *= controls.curtail_keep
        if controls.export_limit_kw is not None:
            lim = np.broadcast_to(np.asarray(controls.export_limit_kw, float), (t, n_h))
            p_cap = np.minimum(p_cap, load_kw + np.tile(lim, (s, 1)))
        sn_kw = net.house_kwp * controls.inverter_s_factor
        p, q = p_cap.copy(), np.zeros_like(p_cap)
        if controls.pf_fixed is not None:
            q = -p * np.tan(np.arccos(controls.pf_fixed))

        r_scale = None
        if scn.ambient_c is not None:
            t_cond = scn.ambient_c.reshape(b) + net.conductor_delta_t_c
            r_scale = 1 + net.conductor_alpha * (t_cond - 20.0)           # IS 398 resistances are DC at 20 degrees C

        def run(p_kw, q_kw):
            return self.backend.calculate(p_load, q_load, p_kw * 1000, q_kw * 1000, up, controls.tap_pos, r_scale)

        res, passes, unsettled = run(p, q), 1, np.zeros(b, dtype=bool)
        if controls.volt_var is not None or controls.volt_watt is not None:
            for _ in range(self.max_passes):
                v = res["u_pu"][:, self._h_idx, net.house_phase]                             # (B, H)
                v = np.where(np.isfinite(v), v, 1.0)
                p_t = p_cap * (controls.volt_watt.p_fraction(v) if controls.volt_watt else 1.0)
                cap = np.sqrt(np.maximum(sn_kw ** 2 - p_t ** 2, 0.0))
                q_t = np.clip(sn_kw * controls.volt_var.q_fraction(v), -cap, cap) if controls.volt_var else np.zeros_like(p)
                dp, dq = p_t - p, q_t - q
                delta = np.maximum(np.abs(dp), np.abs(dq)).max(axis=1)
                unsettled = delta >= self.tol_kw
                if not unsettled.any():
                    break
                p, q = p + self.damping * dp, q + self.damping * dq
                res = run(p, q)
                passes += 1
        converged = res["converged"] & ~unsettled

        def shape(a):
            return a.reshape((s, t) + a.shape[1:])

        return DayResult(
            t=scn.t, u_pu=shape(res["u_pu"]), line_loading_pct=shape(res["line_loading_pct"]),
            trafo_loading_pct=shape(res["trafo_loading_pct"]), trafo_p_kw=shape(res["trafo_p_kw"]),
            losses_kw=shape(res["losses_kw"]), q_loss_kvar=shape(res["q_loss_kvar"]),
            pv_kw=shape(p.sum(axis=1)), pv_avail_kw=shape(pv_avail.sum(axis=1)),
            inverter_kvar=shape(-q.sum(axis=1)), battery_kw=np.zeros((s, t)),
            neutral_a=shape(res["neutral_a"]), vuf_pct=shape(res["vuf_pct"]),
            converged=shape(converged), passes=passes,
        )
```

- [ ] **Step 5: Run the behaviour and parity tests**

Run: `python -m pytest tests/test_solver.py tests/test_solver_parity.py -v`
Expected: `11 passed` (9 behaviour tests plus 2 parity cases), about 40 s. The pandapower reference accounts for most of the time.

Pinned numbers in these tests are measured, not guessed: 26 unsafe steps and 263.1 V peak match the Round 1 balanced result for scenario S4; Volt/VAR peak 250.1 V and trough 220.5 V; export cap at 60% curtails 489.3 kWh with 15 unsafe steps. If a pinned number moves, read why before changing it.

- [ ] **Step 6: Run the performance budget**

Run: `python -m pytest tests/test_performance.py -m perf -v`
Expected: `1 passed` (balanced day under 0.1 s, unbalanced day under 0.3 s; measured 12 ms and 65 ms).

- [ ] **Step 7: Make the nightly job run the parity and performance files regardless of the marker filter**

In `.github/workflows/nightly.yml` change the last step to:

```yaml
      - run: pytest -q -o addopts="" tests/test_performance.py tests/test_solver_parity.py
```

(`-o addopts=""` removes the default `-m "not realdata and not perf"` so the perf test is selected.)

- [ ] **Step 8: Commit**

```bash
git add engine/solver.py engine/reference.py tests/test_solver.py tests/test_solver_parity.py tests/test_performance.py .github/workflows/nightly.yml
git commit -m "feat(engine): power-grid-model batch day solver with unbalanced homes, IEEE 1547 inverters, export limits, R(T); pandapower reference and parity (C4, C2, A8)

Parity on the 99-home street: <0.05 V voltage, <0.2 points transformer loading. Day replay 12 ms balanced, 65 ms unbalanced.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P3.4: Convergence and zero-sequence sensitivity report (gate G5)

**Files:**
- Create: `scripts/engine_sensitivity.py`
- Test: `tests/test_engine_sensitivity.py`
- Output: `data/results/engine_sensitivity.json` (tracked; it feeds the Proof page)

**Interfaces:**
- Consumes: P3.1 to P3.3.
- Produces: `scripts.engine_sensitivity.run(date) -> dict` with keys `balanced`, `phase_modes`, `zero_sequence` (9 cases of `r0_ratio` × `x0_ratio` ∈ {2, 3, 4}), `zero_sequence_peak_range_v`, `gate_g5_converged`.

This is what turns "we assumed r0 = 3·r1" from a hidden risk into a reported range. Measured on 15 May 2019: balanced 263.1 V; random phases 270.5 V; round-robin 268.9 V; all on phase A 294.1 V; zero-sequence peak range 268.4 to 272.6 V; every case converged on all 96 steps.

- [ ] **Step 1: Write the failing test** — `tests/test_engine_sensitivity.py`

```python
import pytest

from scripts.engine_sensitivity import run


@pytest.mark.slow
def test_sensitivity_report_has_every_case_and_passes_gate_g5():
    r = run("2019-05-15")
    assert len(r["zero_sequence"]) == 9 and set(r["phase_modes"]) == {"random", "round_robin", "all_a"}
    assert r["gate_g5_converged"] is True
    assert r["balanced"]["max_voltage_v"] < r["phase_modes"]["round_robin"]["max_voltage_v"] < r["phase_modes"]["all_a"]["max_voltage_v"]
    lo, hi = r["zero_sequence_peak_range_v"]
    assert 255 < lo <= hi < 300
```

- [ ] **Step 2: Run it and see it fail**

Run: `python -m pytest tests/test_engine_sensitivity.py -v`
Expected: `ModuleNotFoundError: No module named 'scripts.engine_sensitivity'`.

- [ ] **Step 3: Create `scripts/engine_sensitivity.py`**

```python
"""Gate G5 evidence: convergence and the zero-sequence sensitivity of the unbalanced engine.

Usage: python -m scripts.engine_sensitivity [--date 2019-05-15] [--out data/results/engine_sensitivity.json]
"""
from __future__ import annotations

import argparse
import itertools
import json
import warnings
from pathlib import Path

from engine.dayinputs import scenarios_from_legacy
from engine.grid import build_grid
from engine.network import PHASE_MODES, assign_phases, from_pandapower
from engine.powerflow import day_inputs
from engine.rules import get_rule
from engine.solver import DaySolver
from engine.violations import evaluate, summarise

RATIOS = (2.0, 3.0, 4.0)
RULE = "pm10"


def run(date: str) -> dict:
    warnings.filterwarnings("ignore")
    pp_net, rule = build_grid(1.0), get_rule(RULE)
    base = from_pandapower(pp_net, phases="round_robin")
    scn = scenarios_from_legacy(day_inputs(date), base)

    def row(res) -> dict:
        s = summarise(res, evaluate(res, rule))
        return {"max_voltage_v": round(s["max_vm_pu"] * 230, 1), "unsafe_steps": s["violation_steps"],
                "max_vuf_pct": s["max_vuf_pct"], "converged_share": float(res.converged.mean())}

    out = {"date": date, "rule": RULE, "balanced": row(DaySolver(base, asymmetric=False).solve(scn)), "phase_modes": {}, "zero_sequence": []}
    for mode in PHASE_MODES:
        out["phase_modes"][mode] = row(DaySolver(base.with_phases(assign_phases(base.n_homes, mode)), asymmetric=True).solve(scn))
    for r0, x0 in itertools.product(RATIOS, RATIOS):
        net = from_pandapower(pp_net, phases="random", r0_ratio=r0, x0_ratio=x0)
        out["zero_sequence"].append({"r0_ratio": r0, "x0_ratio": x0, **row(DaySolver(net, asymmetric=True).solve(scn))})
    peaks = [z["max_voltage_v"] for z in out["zero_sequence"]]
    out["zero_sequence_peak_range_v"] = [min(peaks), max(peaks)]
    out["gate_g5_converged"] = all(z["converged_share"] >= 0.99 for z in out["zero_sequence"]) and \
        all(m["converged_share"] >= 0.99 for m in out["phase_modes"].values())
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="2019-05-15")
    ap.add_argument("--out", default="data/results/engine_sensitivity.json")
    args = ap.parse_args()
    result = run(args.date)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ("balanced", "zero_sequence_peak_range_v", "gate_g5_converged")}, indent=2))
```

- [ ] **Step 4: Run the test, then the report**

Run: `python -m pytest tests/test_engine_sensitivity.py -v && python -m scripts.engine_sensitivity`
Expected: `1 passed`, then a JSON summary with `"gate_g5_converged": true` and `zero_sequence_peak_range_v` close to `[268.4, 272.6]`. A different range means a different network or data: record the new range in the commit message.

- [ ] **Step 5: Commit**

```bash
git add scripts/engine_sensitivity.py tests/test_engine_sensitivity.py data/results/engine_sensitivity.json
git commit -m "feat(engine): convergence and zero-sequence sensitivity report (gate G5)

Round 1 balanced peak 263.1 V; single-phase peaks 268.4-272.6 V across r0/x0 ratios 2-4. All 96 steps converge in every case.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P3.5: Indian feeder archetypes (A4)

**Files:**
- Create: `engine/archetypes.py`
- Test: `tests/test_archetypes.py`

**Interfaces:**
- Consumes: `engine.grid.build_grid`, `engine.network.from_pandapower`, `assign_phases`, `Network` (P3.1).
- Produces: `ARCHETYPES: dict[str, Archetype]`, `CONDUCTORS`, `list_archetypes() -> list[dict]`, `build(archetype_id, phases="random", seed=42) -> Network`. Ids: `benchmark_250`, `urban_short_160`, `suburban_100`, `rural_long_100`, `rural_weak_63`.

**What is real and what is not (stated in `Network.provenance` and on the Proof page):** the resistance and ampacity per conductor come from the IS 398 Part II table (spike S7; a scanned reproduction, to be checked against the BIS copy). The topology is the German SimBench benchmark scaled in length, and reactance 0.29 Ω/km is an **estimate** (the benchmark archetype keeps Round 1's 0.35). No archetype is a surveyed Indian feeder. Measured on 15 May 2019 with round-robin phases: benchmark 99 homes peak 268.9 V; urban short 80 homes 257.1 V; suburban 70 homes 257.9 V; rural long 60 homes 260.6 V; rural weak (63 kVA) 40 homes 259.8 V with the highest transformer loading per home.

- [ ] **Step 1: Write the failing tests** — `tests/test_archetypes.py`

```python
import warnings

import numpy as np
import pytest

from engine.archetypes import ARCHETYPES, CONDUCTORS, build, list_archetypes
from engine.dayinputs import scenarios_from_legacy
from engine.grid import build_grid
from engine.network import from_pandapower
from engine.powerflow import day_inputs
from engine.rules import get_rule
from engine.solver import DaySolver
from engine.violations import evaluate, summarise

warnings.filterwarnings("ignore")


@pytest.fixture(scope="module")
def inputs():
    return day_inputs("2019-05-15")


def _peak(net, inputs):
    res = DaySolver(net, asymmetric=True).solve(scenarios_from_legacy(inputs, net))
    assert res.converged.all()
    return res, summarise(res, evaluate(res, get_rule("pm10")))


def test_catalogue_lists_every_archetype_with_its_parameters():
    rows = {r["id"]: r for r in list_archetypes()}
    assert set(rows) == set(ARCHETYPES) and rows["rural_weak_63"]["trafo_kva"] == 63.0
    assert CONDUCTORS["rabbit"]["r_ohm_per_km"] == 0.5524            # the Round 1 value, from IS 398


def test_unknown_archetype_is_rejected_with_the_valid_names():
    with pytest.raises(KeyError, match="urban_short_160"):
        build("nowhere")


@pytest.mark.parametrize("aid", list(ARCHETYPES))
def test_every_archetype_is_radial_sized_and_sourced(aid):
    net = build(aid)
    a = ARCHETYPES[aid]
    assert net.is_radial() and net.n_homes == a.n_homes
    assert net.trafo.sn_va == pytest.approx(a.trafo_kva * 1000)
    assert "IS 398" in net.provenance["conductor"] and "benchmark" in net.provenance["topology"]
    assert (net.house_kwp > 0).all() and set(np.unique(net.house_phase)) <= {0, 1, 2}


def test_benchmark_archetype_is_exactly_round_one():
    ref = from_pandapower(build_grid(1.0), phases="random")
    got = build("benchmark_250")
    assert np.allclose(got.line_r1_ohm, ref.line_r1_ohm) and np.array_equal(got.house_node, ref.house_node)
    assert np.array_equal(got.house_phase, ref.house_phase)


def test_longer_and_thinner_feeders_have_more_wire_resistance_and_more_voltage_rise(inputs):
    nets = {aid: build(aid, phases="round_robin") for aid in ("urban_short_160", "suburban_100", "rural_long_100", "rural_weak_63")}
    resistance = {aid: float(n.line_r1_ohm.sum()) for aid, n in nets.items()}
    assert resistance["urban_short_160"] < resistance["suburban_100"] < resistance["rural_long_100"] < resistance["rural_weak_63"]
    peaks = {aid: _peak(n, inputs)[1]["max_vm_pu"] for aid, n in nets.items() if aid != "rural_weak_63"}
    # The weak 63 kVA feeder carries only 40 homes, so its peak is not compared: fewer homes means less rise.
    assert peaks["urban_short_160"] < peaks["suburban_100"] < peaks["rural_long_100"]


def test_a_small_transformer_loads_up_faster_per_home(inputs):
    big, small = build("benchmark_250", phases="round_robin"), build("rural_weak_63", phases="round_robin")
    t_big = _peak(big, inputs)[0].trafo_loading_pct.max() / big.n_homes
    t_small = _peak(small, inputs)[0].trafo_loading_pct.max() / small.n_homes
    assert t_small > t_big
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/test_archetypes.py -v`
Expected: `ModuleNotFoundError: No module named 'engine.archetypes'`.

- [ ] **Step 3: Create `engine/archetypes.py`**

```python
"""A4: Indian low-voltage feeder archetypes built on the 99-home benchmark topology.

The topology is a German benchmark (SimBench 1-LV-rural2); what is Indian is the conductor (IS 398 Part II
ACSR resistance and ampacity), the feeder length, the distribution-transformer rating and the number of homes.
Reactance is not in the standard table used here: 0.29 ohm/km is an ESTIMATE (log formula, 0.4 m spacing)
and is labelled as such in `Network.provenance`.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import networkx as nx
import numpy as np

from engine.grid import build_grid
from engine.network import assign_phases, from_pandapower
from engine.types import Network

X_ESTIMATE_OHM_PER_KM = 0.29
BENCHMARK_X_OHM_PER_KM = 0.35               # Round 1 value, kept for the benchmark archetype only
ZERO_SEQUENCE_RATIO = 3.0                   # unsourced; see gate G5

# IS 398 Part II (scanned reproduction; verify against the BIS copy): DC resistance at 20 degrees C in ohm/km,
# current rating at 75 degrees C conductor temperature in A.
CONDUCTORS = {
    "squirrel": {"r_ohm_per_km": 1.3940, "i_a": 89},
    "weasel": {"r_ohm_per_km": 0.9289, "i_a": 114},
    "rabbit": {"r_ohm_per_km": 0.5524, "i_a": 155},
    "racoon": {"r_ohm_per_km": 0.3712, "i_a": 196},
    "dog": {"r_ohm_per_km": 0.2792, "i_a": 231},
}


@dataclass(frozen=True)
class Archetype:
    id: str
    label: str
    conductor: str
    length_scale: float        # multiplies the benchmark's cable lengths
    trafo_kva: float
    n_homes: int
    x_ohm_per_km: float = X_ESTIMATE_OHM_PER_KM
    note: str = ""


ARCHETYPES = {a.id: a for a in (
    Archetype("benchmark_250", "Benchmark street (Round 1): 99 homes, 250 kVA, Rabbit", "rabbit", 1.0, 250.0, 99,
              BENCHMARK_X_OHM_PER_KM, "Unchanged from Round 1 so earlier results stay comparable."),
    Archetype("urban_short_160", "Urban short feeder: 80 homes, 160 kVA, Dog", "dog", 0.6, 160.0, 80),
    Archetype("suburban_100", "Suburban feeder: 70 homes, 100 kVA, Racoon", "racoon", 1.0, 100.0, 70),
    Archetype("rural_long_100", "Rural long feeder: 60 homes, 100 kVA, Rabbit", "rabbit", 1.5, 100.0, 60),
    Archetype("rural_weak_63", "Rural weak feeder: 40 homes, 63 kVA, Weasel", "weasel", 1.5, 63.0, 40,
              note="Smallest transformer in the plan range and a thin conductor."),
)}


def list_archetypes() -> list[dict]:
    return [{"id": a.id, "label": a.label, "conductor": a.conductor, "trafo_kva": a.trafo_kva, "n_homes": a.n_homes,
             "length_scale": a.length_scale, "x_ohm_per_km": a.x_ohm_per_km} for a in ARCHETYPES.values()]


def _nearest_homes(net: Network, n: int) -> np.ndarray:
    """Indices of the n homes electrically closest to the transformer (cumulative line length)."""
    g = nx.Graph()
    for a, b, length in zip(net.line_from, net.line_to, net.line_length_m):
        g.add_edge(int(a), int(b), weight=float(length))
    dist = nx.single_source_dijkstra_path_length(g, net.trafo.to_node, weight="weight")
    order = np.argsort([dist[int(node)] for node in net.house_node], kind="stable")
    return np.sort(order[:n])


def build(archetype_id: str, phases: str | np.ndarray = "random", seed: int = 42) -> Network:
    if archetype_id not in ARCHETYPES:
        raise KeyError(f"unknown archetype {archetype_id!r}; choose from {sorted(ARCHETYPES)}")
    a = ARCHETYPES[archetype_id]
    net = from_pandapower(build_grid(1.0), phases="round_robin", name=a.id)
    cond = CONDUCTORS[a.conductor]
    if archetype_id == "benchmark_250":
        keep = np.arange(net.n_homes)
    else:
        length_m = net.line_length_m * a.length_scale
        km = length_m / 1000
        lv_line = np.isin(net.line_from, net.lv_nodes) & np.isin(net.line_to, net.lv_nodes)
        r1 = np.where(lv_line, cond["r_ohm_per_km"] * km, net.line_r1_ohm * a.length_scale)
        x1 = np.where(lv_line, a.x_ohm_per_km * km, net.line_x1_ohm * a.length_scale)
        ratio = a.trafo_kva * 1000 / net.trafo.sn_va
        trafo = replace(net.trafo, sn_va=net.trafo.sn_va * ratio, pk_w=net.trafo.pk_w * ratio, p0_w=net.trafo.p0_w * ratio)
        net = net.replace(
            line_length_m=length_m, line_r1_ohm=r1, line_x1_ohm=x1, line_r0_ohm=r1 * ZERO_SEQUENCE_RATIO,
            line_x0_ohm=x1 * ZERO_SEQUENCE_RATIO, line_c1_f=net.line_c1_f * a.length_scale,
            line_i_n_a=np.where(lv_line, float(cond["i_a"]), net.line_i_n_a), trafo=trafo)
        keep = _nearest_homes(net, a.n_homes)
    phase = assign_phases(len(keep), phases, seed) if isinstance(phases, str) else np.asarray(phases, dtype=int)[keep]
    net = net.replace(house_node=net.house_node[keep], house_kwp=net.house_kwp[keep], house_phase=phase)
    return net.replace(provenance={
        **net.provenance,
        "archetype": a.id,
        "conductor": f"IS 398 Part II ACSR {a.conductor}: R {cond['r_ohm_per_km']} ohm/km at 20 C, {cond['i_a']} A at 75 C (verify against BIS copy)",
        "reactance": f"{a.x_ohm_per_km} ohm/km: " + ("Round 1 assumption" if archetype_id == "benchmark_250" else "estimate, not from the standard"),
        "topology": "benchmark: SimBench 1-LV-rural2 topology scaled in length; not a surveyed Indian feeder",
    })
```

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_archetypes.py -v`
Expected: `10 passed` (about 60 s).

- [ ] **Step 5: Commit**

```bash
git add engine/archetypes.py tests/test_archetypes.py
git commit -m "feat(engine): five Indian feeder archetypes with IS 398 conductors, DT 63-250 kVA (A4)

Reactance 0.29 ohm/km is an estimate and is labelled so in provenance.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

**Phase 3 exit check:** `python scripts/check.py` is green; `python -m pytest -q tests` passes (Round 1's 55 plus this phase's new tests); `git log --oneline` shows five commits in this phase.


---

# PHASE 4: SOLAR V2, FOUNDATION-MODEL BENCHMARK AND CALIBRATION

**Deliverable:** a multi-model solar forecast that beats Round 1 on the identical 2025 mask (gate G3) with honest intervals; its live inference path; a Chronos-2 benchmark with a written adoption rule; a measured-plant yield calibration; a cold-start forecast for new rooftops.

**Spike results, a starting point and not a decision (9 Oct 2026, Mathura, truth = ERA5-driven PV, 4,414 daylight hours of 2025; train 2024-01 to 10, first conformal pool 2024-11 and 12).** The Round 1 pipeline was rebuilt first from freshly downloaded data and reproduced Round 1's published numbers exactly (MAE 0.0396, physics-only 0.0411, persistence 0.0456), so the comparison below is like for like.

| Variant | MAE kW/kWp | 80% interval coverage | WIS |
|---|---|---|---|
| Persistence (same hour yesterday) | 0.0456 | | |
| Round 1 replica (one blended NWP, LightGBM, interval scale 2.5) | 0.0396 | 82.3% | 0.0290 |
| Physics only, one blended NWP | 0.0411 | | |
| Physics only, mean of 5 NWP models | 0.0335 | | |
| 5-model LightGBM, direct target, Round 1 interval scaling | 0.0334 | 82.7% | 0.0230 |
| 4 models (without ECMWF) / 3 models / ICON alone | 0.0356 / 0.0347 / 0.0366 | | |
| 5-model residual LightGBM, raw quantiles | 0.0327 | 52–58% | 0.0223 |
| **Solar v2: residual LightGBM + rolling 60-day conformal** | **0.0329** | **80.3%** | **0.0214** |
| Chronos-2 zero-shot with covariates (sees 14 days of observed PV) | 0.0318 | 78.6% | 0.0207 |

What this says, without spin:
1. **Most of the gain is averaging five weather models** (MAE 0.0411 to 0.0335, no ML at all). LightGBM then adds a small median gain and mainly better intervals.
2. **Round 1's interval scale 2.5 was tuned on two winter months** and does not transfer to other seasons; the raw quantiles cover only 52–58% in 2025. A **rolling 60-day conformal width** restores 79–80% in every season (winter 77%, summer 82–86%, monsoon 77–78%, post-monsoon 82–83% across window variants).
3. **Solar v2 is 16.9% better than Round 1 on MAE and 26% better on WIS.** By season (direct-target variant): winter 0.0349 vs 0.0418, monsoon 0.0462 vs 0.0503, post-monsoon 0.0276 vs 0.0513, **summer 0.0181 vs 0.0173 (slightly worse)**. The summer result stays on the Proof page.
4. **ECMWF IFS matters in the ensemble** (dropping it costs 6.5% MAE) although it is the worst single model by itself (0.0476).
5. **In the spike Chronos-2 was 3.3% better on WIS than solar v2, below the 5% adoption bar**, and it needs yesterday's observed PV, which the LightGBM pipeline does not. Spike verdict: not adopted. The build re-runs this bake-off (section 0.8) and decides.
6. **Gate G2 (measured):** GFS, ICON, GEM, Météo-France ARPEGE and ECMWF IFS return 100% of hours from their first valid hour (ECMWF starts 6 March 2024, the others 19 January 2024). JMA GSM returns nothing and UKMO 10 km returns 73% (from January 2025): both are dropped. The gate text is refined to **≥95% non-null from the model's first valid hour and in the test year**, because a full-window rule would have wrongly discarded ECMWF, which is complete after its start date.

### Task P4.1: Multi-model downloader and solar forecast v2 (B2), gates G2 and G3

**Files:**
- Create: `scripts/download_solar_v2.py`, `ml/solar_v2.py`
- Test: `tests/test_download_solar_v2.py`, `tests/test_solar_v2.py`
- Output (tracked): `ml/models/solar_v2_p10.txt`, `solar_v2_p50.txt`, `solar_v2_p90.txt`, `solar_v2_manifest.json`, `ml/reports/solar_v2.json`, `data/processed/solar_forecast_v2_2025.parquet`

**Interfaces:**
- Consumes: `engine.profiles.pv_hourly`, `clearsky_ghi`, `read_weather` (P2.2); `ml.conformal.conformal_q` and `ml.metrics` (P2.4).
- Produces: `availability(frames)`, `ensemble_features(frames, site)`, `fit(X, y, mask)`, `predict(models, X)`, `rolling_conformal(pred, y, daylight, days, window=60, calibration_start=None)`, `evaluate(pred, y, mask, baselines)`, `load_dataset(district)`, `run(district, window)`; constants `MODELS`, `FEATURES`, `QUANTILES`, `ROUND1_MAE = 0.0396`, `MODEL_DIR`, `REPORT`. Every forecaster returns a frame with `p10`, `p50`, `p90`.

**Design notes:**
- **Residual target.** The models predict `truth − ensemble mean`, so the physics carries the signal and the trees only learn the correction and the spread (the direct target spends trees re-learning the diurnal curve).
- **Rolling conformal, no peeking.** Day *d*'s width uses the realised errors of days *d−60 … d−1* only, from the out-of-sample pool (2024-11 onward). A test proves that changing later observations does not change earlier intervals.
- **Truth is a proxy.** ERA5 through PVWatts is not measured rooftop output; this is written into the manifest and shown on the Proof page.
- **NaN-safe.** Hours where no model has data produce `NaN`, never a silent zero; downstream code must treat that as "no forecast".

- [ ] **Step 1: Write the failing tests** — `tests/test_download_solar_v2.py` and `tests/test_solar_v2.py`

```python
from engine import config
from ml import solar_v2
from scripts import download_solar_v2 as dl


def test_request_asks_for_the_day_before_forecast_of_every_variable():
    p = dl.request_params(config.SITES["mathura"], "icon_global")
    assert p["models"] == "icon_global" and p["start_date"] == "2024-01-01" and p["end_date"] == "2025-12-31"
    assert p["hourly"].split(",") == [f"{v}_previous_day1" for v in config.WEATHER_VARS]
    assert "models" not in dl.request_params(config.SITES["mathura"], None)       # None = default best-match blend


def test_file_names_match_what_the_trainer_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_DIR", tmp_path)
    assert solar_v2.raw_path(None).name == "dayahead_mathura_2024_2025.json"             # Round 1 name is kept
    assert solar_v2.raw_path("ecmwf_ifs025").name == "dayahead_ecmwf_ifs025_mathura_2024_2025.json"


def test_an_existing_file_is_not_downloaded_again(tmp_path, monkeypatch):
    dest = tmp_path / "x.json"
    dest.write_text("x" * 2000)
    monkeypatch.setattr(dl.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network used")))
    assert dl.fetch(config.SITES["mathura"], "icon_global", dest) is True
```

```python
import numpy as np
import pandas as pd
import pytest

from engine import profiles
from ml import solar_v2

IDX = pd.date_range("2024-03-01", "2024-09-30 23:00", freq="h")


def _weather(ghi: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({"shortwave_radiation": ghi, "direct_normal_irradiance": ghi * 0.7, "diffuse_radiation": ghi * 0.2,
                         "temperature_2m": 30.0, "cloud_cover": 50.0, "wind_speed_10m": 2.0}, index=IDX)


@pytest.fixture(scope="module")
def world():
    """Truth irradiance with day-level cloudiness, and five models that each see it with their own error."""
    rng = np.random.default_rng(0)
    clear = profiles.clearsky_ghi(IDX).to_numpy()
    daily = rng.uniform(0.3, 1.0, len(IDX) // 24 + 1)
    truth = clear * np.repeat(daily, 24)[: len(IDX)]
    frames = {}
    for i, m in enumerate(solar_v2.MODELS):
        err = rng.normal(0, 0.25, len(IDX) // 24 + 1)                   # each model misjudges the day's cloudiness
        frames[m] = _weather(np.clip(truth * (1 + np.repeat(err, 24)[: len(IDX)]), 0, None))
    y = profiles.pv_hourly(_weather(truth))
    return frames, y


def test_availability_reports_the_gate_per_model():
    ghi = np.ones(len(IDX))
    good, late, sparse = _weather(ghi), _weather(ghi), _weather(ghi)
    late.iloc[:100] = np.nan                                            # starts a little late but is complete afterwards
    sparse.iloc[::3] = np.nan                                           # a third of the hours missing
    a = solar_v2.availability({"good": good, "late": late, "sparse": sparse}, test_year=2024)
    assert a.loc["good", "passes"] and a.loc["late", "passes"] and not a.loc["sparse", "passes"]
    assert a.loc["late", "first_valid"] == IDX[100] and a.loc["sparse", "nonnull_since_first"] < 0.7


def test_ensemble_features_ignore_a_missing_model_at_that_hour(world):
    frames, _ = world
    broken = {k: v.copy() for k, v in frames.items()}
    broken["gfs_global"].iloc[5000:5010] = np.nan
    X = solar_v2.ensemble_features(broken)
    assert X.loc[IDX[5003], "n_models"] == 4 and X.loc[IDX[100], "n_models"] == 5
    day = X.index[(X.clearsky_ghi > 0)][:200]
    assert (X.loc[day, "pv_min"] <= X.loc[day, "pv_mean"] + 1e-9).all() and (X.loc[day, "pv_mean"] <= X.loc[day, "pv_max"] + 1e-9).all()


def test_the_ensemble_mean_beats_every_single_model(world):
    frames, y = world
    X = solar_v2.ensemble_features(frames)
    day = X.clearsky_ghi > 0
    single = {m: float((profiles.pv_hourly(f)[day] - y[day]).abs().mean()) for m, f in frames.items()}
    ensemble = float((X.pv_mean[day] - y[day]).abs().mean())
    assert ensemble < min(single.values())


def test_predictions_are_sorted_non_negative_and_zero_at_night(world):
    frames, y = world
    X = solar_v2.ensemble_features(frames)
    day = X.clearsky_ghi > 0
    models = solar_v2.fit(X, y, day & (X.index < "2024-07-01"))
    pred = solar_v2.predict(models, X)
    assert (pred.p10 <= pred.p50).all() and (pred.p50 <= pred.p90).all() and (pred.to_numpy() >= 0).all()
    assert (pred[~day].to_numpy() == 0).all()
    X2 = X.copy()
    X2.loc[IDX[3000], "pv_mean"] = np.nan
    assert solar_v2.predict(models, X2).loc[IDX[3000]].isna().all()


def test_rolling_conformal_restores_coverage_and_never_peeks_ahead(world):
    frames, y = world
    X = solar_v2.ensemble_features(frames)
    day = X.clearsky_ghi > 0
    raw = solar_v2.predict(solar_v2.fit(X, y, day & (X.index < "2024-06-01")), X)
    days = pd.date_range("2024-07-15", "2024-09-30")
    out = solar_v2.rolling_conformal(raw, y, day, days, window=30, calibration_start="2024-06-01")
    t = day & (X.index >= "2024-07-15")
    cover = ((y[t] >= out.p10[t]) & (y[t] <= out.p90[t])).mean()
    assert 0.70 <= cover <= 0.90
    # Interval of one day is unchanged when later observations change.
    y_changed = y.copy()
    y_changed[y_changed.index >= "2024-08-20"] += 5.0
    again = solar_v2.rolling_conformal(raw, y_changed, day, days, window=30, calibration_start="2024-06-01")
    same = (again.index < "2024-08-20")
    assert np.allclose(again[same].fillna(-1).to_numpy(), out[same].fillna(-1).to_numpy())


def test_evaluate_reports_gate_g3_against_round_one(world):
    frames, y = world
    X = solar_v2.ensemble_features(frames)
    day = X.clearsky_ghi > 0
    pred = solar_v2.predict(solar_v2.fit(X, y, day & (X.index < "2024-07-01")), X)
    s = solar_v2.evaluate(pred, y, day & (X.index >= "2024-08-01"), {"persistence": y.shift(24)})
    assert {"mae_p50", "p10_p90_coverage", "wis", "skill_vs_persistence", "gate_g3_passes"} <= set(s)
    assert s["gate_g3_passes"] == (s["mae_p50"] < solar_v2.ROUND1_MAE)


@pytest.mark.realdata
def test_real_run_passes_gates_g2_and_g3():
    """Needs data/raw/dayahead_*_mathura_2024_2025.json and era5_mathura_2024_2025.json (scripts/download_solar_v2.py)."""
    report = solar_v2.run()
    s = report["scores_2025"]
    assert set(report["nwp_models_used"]) == set(solar_v2.MODELS)
    assert s["gate_g3_passes"] and s["mae_p50"] < 0.0396
    assert 0.77 <= s["p10_p90_coverage"] <= 0.83 and s["wis"] < 0.029
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/test_download_solar_v2.py tests/test_solar_v2.py -v -m "not realdata"`
Expected: collection errors, `ImportError: cannot import name 'solar_v2' from 'ml'`.

- [ ] **Step 3: Create `ml/solar_v2.py` (complete file)**

```python
"""Solar forecast v2 (B2): multi-model NWP ensemble, residual quantile model, rolling split-conformal.

Pipeline for each hour:
  1. every available NWP model's day-ahead irradiance (Open-Meteo previous-runs, `previous_day1`) goes through the same
     pvlib PVWatts chain as the truth, giving one physical PV forecast per model;
  2. the mean, spread (min, max, std) of those forecasts plus mean cloud, mean irradiance and the clear-sky irradiance
     are the features;
  3. LightGBM quantile models predict the *residual* of truth over the ensemble mean (P10, P50, P90);
  4. the interval is widened by split-conformal scores from the most recent 60 days of out-of-sample errors.

The truth is ERA5-driven PV (a reference proxy, not measured rooftop output); see the model manifest.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from engine import config, profiles
from ml.conformal import conformal_q

MODELS = ("gfs_global", "icon_global", "gem_global", "meteofrance_arpege_world", "ecmwf_ifs025")
CANDIDATE_MODELS = MODELS + ("jma_gsm", "ukmo_global_deterministic_10km")
QUANTILES = {"p10": 0.1, "p50": 0.5, "p90": 0.9}
FEATURES = ["pv_mean", "pv_min", "pv_max", "pv_std", "ghi_mean", "cloud_mean", "clearsky_ghi", "hour", "doy", "n_models"]
PARAMS = {"n_estimators": 400, "learning_rate": 0.05, "num_leaves": 31, "min_child_samples": 20, "verbose": -1,
          "random_state": 42, "deterministic": True, "force_col_wise": True}
ROUND1_MAE = 0.0396                  # Round 1 solar model on the 2025 daylight mask (gate G3 reference)
AVAILABILITY_MIN = 0.95              # gate G2
FILL = {"wind_speed_10m": 5.0, "temperature_2m": 30.0, "diffuse_radiation": 0.0,
        "direct_normal_irradiance": 0.0, "shortwave_radiation": 0.0}


def raw_path(model: str | None, district: str = "mathura") -> Path:
    """`None` is Open-Meteo's default (best-match) blend that Round 1 used."""
    stem = "dayahead" if model is None else f"dayahead_{model}"
    return config.RAW_DIR / f"{stem}_{district}_2024_2025.json"


def read_previous_runs(path: Path) -> pd.DataFrame:
    """Hourly frame with the `_previous_day1` suffix removed; unavailable hours are NaN."""
    df = profiles.read_weather(path)
    df.columns = [c.replace("_previous_day1", "") for c in df.columns]
    return df.apply(pd.to_numeric, errors="coerce")


def availability(frames: dict[str, pd.DataFrame], test_year: int = 2025) -> pd.DataFrame:
    """Gate G2: share of non-null irradiance hours since the model's first valid hour, and in the test year."""
    rows = []
    for name, df in frames.items():
        ghi = df["shortwave_radiation"]
        first = ghi.first_valid_index()
        since = float(ghi[first:].notna().mean()) if first is not None else 0.0
        in_year = float(ghi[ghi.index.year == test_year].notna().mean())
        rows.append({"model": name, "first_valid": first, "nonnull_since_first": round(since, 4),
                     f"nonnull_{test_year}": round(in_year, 4), "passes": since >= AVAILABILITY_MIN and in_year >= AVAILABILITY_MIN})
    return pd.DataFrame(rows).set_index("model")


def _pv(frame: pd.DataFrame) -> pd.Series:
    """Physical PV forecast for one model; NaN wherever the model had no irradiance."""
    ok = frame["shortwave_radiation"].notna()
    return profiles.pv_hourly(frame.ffill().fillna(FILL)).where(ok)


def ensemble_features(frames: dict[str, pd.DataFrame], site: config.Site | None = None) -> pd.DataFrame:
    """Features on the union hourly index of the frames. Models missing at an hour are ignored at that hour."""
    index = next(iter(frames.values())).index
    pv = pd.DataFrame({m: _pv(f.reindex(index)) for m, f in frames.items()}, index=index)
    ghi = pd.DataFrame({m: f.reindex(index)["shortwave_radiation"] for m, f in frames.items()})
    cloud = pd.DataFrame({m: f.reindex(index)["cloud_cover"] for m, f in frames.items()})
    return pd.DataFrame({
        "pv_mean": pv.mean(axis=1), "pv_min": pv.min(axis=1), "pv_max": pv.max(axis=1), "pv_std": pv.std(axis=1),
        "ghi_mean": ghi.mean(axis=1), "cloud_mean": cloud.mean(axis=1),
        "clearsky_ghi": profiles.clearsky_ghi(index, site).to_numpy(),
        "hour": index.hour, "doy": index.dayofyear, "n_models": pv.notna().sum(axis=1),
    }, index=index)


def fit(X: pd.DataFrame, y: pd.Series, mask: pd.Series) -> dict[str, lgb.LGBMRegressor]:
    """Quantile models on the residual y - pv_mean over the rows where the ensemble exists."""
    rows = mask & X["pv_mean"].notna()
    resid = (y - X["pv_mean"])[rows]
    return {q: lgb.LGBMRegressor(objective="quantile", alpha=a, **PARAMS).fit(X.loc[rows, FEATURES], resid) for q, a in QUANTILES.items()}


def predict(models: dict[str, lgb.LGBMRegressor], X: pd.DataFrame) -> pd.DataFrame:
    """P10/P50/P90 in kW per installed kW; sorted, never negative, zero at night. NaN where there is no ensemble."""
    raw = pd.DataFrame({q: m.predict(X[FEATURES]) for q, m in models.items()}, index=X.index)
    raw[:] = np.sort(raw.to_numpy(), axis=1)
    out = raw.add(X["pv_mean"], axis=0).clip(lower=0)
    out[X["clearsky_ghi"] <= 0] = 0.0
    out[X["pv_mean"].isna()] = np.nan
    return out


def rolling_conformal(pred: pd.DataFrame, y: pd.Series, daylight: pd.Series, days: pd.DatetimeIndex, *,
                      window: int = 60, min_points: int = 50, alpha: float = 0.2, calibration_start: str | None = None) -> pd.DataFrame:
    """Widen each day's interval by the conformal score of the previous `window` days of out-of-sample errors.

    Only days strictly before the target day are used, so the interval is available the evening before.
    `calibration_start` excludes in-sample rows (the model's own training period) from the pool.
    """
    out = pred.copy()
    dates = pd.Series(pred.index.normalize(), index=pred.index)
    pool = daylight & y.notna() & pred["p50"].notna()
    if calibration_start is not None:
        pool &= pred.index >= calibration_start
    for d in days:
        today = (dates == d) & daylight & pred["p50"].notna()
        sel = pool & (dates < d) & (dates >= d - pd.Timedelta(days=window))
        if not today.any() or sel.sum() < min_points:
            continue
        q = conformal_q(pred[sel], y[sel], alpha)
        out.loc[today, "p10"] = (pred.loc[today, "p10"] - q).clip(lower=0)
        out.loc[today, "p90"] = pred.loc[today, "p90"] + q
    return out


def evaluate(pred: pd.DataFrame, y: pd.Series, mask: pd.Series, baselines: dict[str, pd.Series]) -> dict:
    from ml import metrics
    t = mask & pred["p50"].notna()
    yt = y[t]
    mae = float((pred["p50"][t] - yt).abs().mean())
    scores = {"n": int(t.sum()), "mae_p50": round(mae, 4),
              "p10_p90_coverage": round(metrics.coverage(yt, pred["p10"][t], pred["p90"][t]), 3),
              "wis": round(metrics.wis(yt, pred["p10"][t], pred["p50"][t], pred["p90"][t]), 4)}
    for name, series in baselines.items():
        b = float((series[t] - yt).abs().mean())
        scores[f"mae_{name}"] = round(b, 4)
        scores[f"skill_vs_{name}"] = round(metrics.skill(mae, b), 3)
    scores["gate_g3_passes"] = bool(mae < ROUND1_MAE)
    return scores


def write_manifest(path: Path, *, models_used: list[str], scores: dict, window: int, files: dict, sha256: dict, conformal_q: float) -> None:
    path.write_text(json.dumps({
        "model_type": "LightGBM residual quantiles over a multi-NWP physical ensemble, rolling split-conformal",
        "model_version": "2.0.0", "quantiles": list(QUANTILES), "model_files": files, "model_sha256": sha256,
        "nwp_models": models_used, "conformal_window_days": window, "conformal_q": round(conformal_q, 6),
        "feature_names": FEATURES,
        "truth": "ERA5 reanalysis through pvlib PVWatts (reference proxy, not measured rooftop PV)",
        "scores_2025": scores,
        "limitations": ["Coverage is tuned to the ERA5-driven proxy, not to rooftop meters.",
                        "Open-Meteo previous-runs history for some models starts in 2024 only.",
                        "conformal_q is the value at the end of the training year; the nightly monitor refreshes it."],
    }, indent=2), encoding="utf-8")


MODEL_DIR = Path(__file__).resolve().parent / "models"
REPORT = Path(__file__).resolve().parent / "reports" / "solar_v2.json"


def load_dataset(district: str = "mathura") -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, list[str]]:
    """Ensemble features X, ERA5-driven truth y, the availability table (gate G2) and the NWP models that passed it."""
    site = config.SITES[district]
    candidates = {m: read_previous_runs(raw_path(m, district)) for m in CANDIDATE_MODELS if raw_path(m, district).exists()}
    avail = availability(candidates)
    used = [m for m in MODELS if m in avail.index and bool(avail.loc[m, "passes"])]
    if len(used) < 3:
        raise RuntimeError(f"gate G2 leaves only {len(used)} NWP models; need at least 3: {list(avail.index[avail.passes])}")
    truth = profiles.read_weather(config.RAW_DIR / f"era5_{district}_2024_2025.json")
    y = profiles.pv_hourly(truth, site)
    X = ensemble_features({m: candidates[m].reindex(y.index) for m in used}, site)
    return X, y, avail, used


def run(district: str = "mathura", window: int = 60) -> dict:
    """Train on 2024-01..10, use 2024-11..12 only as the first conformal pool, score on daylight hours of 2025."""
    X, y, avail, used = load_dataset(district)
    day = X["clearsky_ghi"] > 0
    train = day & (X.index < "2024-11-01")
    test = day & (X.index.year == 2025)
    models = fit(X, y, train)
    raw = predict(models, X)
    pred = rolling_conformal(raw, y, day, pd.date_range("2025-01-01", "2025-12-31"), window=window, calibration_start="2024-11-01")
    best = read_previous_runs(raw_path(None, district)).reindex(y.index)
    baselines = {"persistence": y.shift(24), "physics_only_best_match": _pv(best), "physics_only_ensemble": X["pv_mean"]}
    scores = evaluate(pred, y, test, baselines)
    scores["interval_without_conformal"] = evaluate(raw, y, test, {})["p10_p90_coverage"]
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    files, digests = {}, {}
    for q, m in models.items():
        f = MODEL_DIR / f"solar_v2_{q}.txt"
        m.booster_.save_model(str(f))
        files[q], digests[q] = f.name, hashlib.sha256(f.read_bytes()).hexdigest()
    last = pd.Timestamp("2025-12-31")
    pool = day & raw["p50"].notna() & (X.index >= last - pd.Timedelta(days=window - 1)) & (X.index <= last + pd.Timedelta(days=1))
    q_now = conformal_q(raw[pool], y[pool], 0.2)
    write_manifest(MODEL_DIR / "solar_v2_manifest.json", models_used=used, scores=scores, window=window,
                   files=files, sha256=digests, conformal_q=q_now)
    report = {"availability": json.loads(avail.reset_index().to_json(orient="records", date_format="iso")),
              "nwp_models_used": used, "scores_2025": scores, "model_sha256": digests, "conformal_q_end_of_2025": round(q_now, 6)}
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    pred.assign(actual=y).loc[test[test].index].to_parquet(config.PROCESSED_DIR / "solar_forecast_v2_2025.parquet")
    return report


if __name__ == "__main__":
    print(json.dumps(run()["scores_2025"], indent=2))
```

- [ ] **Step 4: Create `scripts/download_solar_v2.py`**

```python
"""Download the multi-model day-ahead weather used by solar v2 into data/raw (never committed).

Usage:  python -m scripts.download_solar_v2 [--district mathura]

One file per NWP model (Open-Meteo previous-runs API, `previous_day1` = issued the day before). A model that the
API does not carry for the period comes back with empty values; `ml.solar_v2.availability` (gate G2) drops it.
Open-Meteo API terms are unchecked (gate G6): read them before any use beyond the competition build.
"""
from __future__ import annotations

import argparse
import time

import requests

from engine import config
from ml import solar_v2

PREVIOUS_RUNS = "https://previous-runs-api.open-meteo.com/v1/forecast"
START, END = "2024-01-01", "2025-12-31"


def request_params(site: config.Site, model: str | None) -> dict:
    params = {"latitude": site.latitude, "longitude": site.longitude, "timezone": config.TIMEZONE,
              "start_date": START, "end_date": END,
              "hourly": ",".join(f"{v}_previous_day1" for v in config.WEATHER_VARS)}
    if model is not None:
        params["models"] = model
    return params


def fetch(site: config.Site, model: str | None, dest, attempts: int = 4) -> bool:
    if dest.exists() and dest.stat().st_size > 1000:
        print(f"skip  {dest.name}")
        return True
    for attempt in range(attempts):
        r = requests.get(PREVIOUS_RUNS, params=request_params(site, model), timeout=180)
        if r.status_code == 200:
            dest.write_text(r.text)
            print(f"done  {dest.name} ({len(r.text) / 1e6:.1f} MB)")
            return True
        print(f"retry {dest.name}: HTTP {r.status_code} {r.text[:120]}")
        time.sleep(5 * (attempt + 1))
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--district", default="mathura", choices=config.DISTRICTS)
    args = ap.parse_args()
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    site = config.SITES[args.district]
    failed = [m for m in (None, *solar_v2.CANDIDATE_MODELS)
              if not fetch(site, m, solar_v2.raw_path(m, args.district))]
    if failed:
        raise SystemExit(f"could not download: {failed}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the fast tests, then download the weather (eight files of about 0.8 MB, about 90 seconds)**

Run: `python -m pytest tests/test_download_solar_v2.py tests/test_solar_v2.py -v -m "not realdata" && python -m scripts.download_solar_v2`
Expected: `9 passed`; then `done dayahead_*.json` lines for the default blend plus seven candidate models. `data/raw` is gitignored. The ERA5 truth file `era5_mathura_2024_2025.json` comes from `scripts/download_data.py` (P2.1).

- [ ] **Step 6: Train and score on the real data (gates G2 and G3)**

Run: `python -m ml.solar_v2`
Expected (about 20 seconds): JSON ending in `"gate_g3_passes": true`, with `mae_p50` near 0.0329, `p10_p90_coverage` near 0.803, `wis` near 0.0214, `interval_without_conformal` near 0.52. `ml/reports/solar_v2.json` lists all seven candidate models with `passes` true for exactly the five in `MODELS`.

**If `gate_g3_passes` is false:** stop. Do not commit the models. Keep Round 1's solar model for every downstream task, record the true MAE in the commit message and in `docs/generated/proof.md`, and make no improvement claim.

- [ ] **Step 7: Run the real-data test**

Run: `python -m pytest tests/test_solar_v2.py -v -m realdata`
Expected: `1 passed`.

- [ ] **Step 8: Commit**

```bash
git add scripts/download_solar_v2.py ml/solar_v2.py tests/test_download_solar_v2.py tests/test_solar_v2.py ml/models/solar_v2_* ml/reports/solar_v2.json data/processed/solar_forecast_v2_2025.parquet
git commit -m "feat(ml): solar v2 - five-NWP ensemble, residual quantiles, rolling conformal (B2); gates G2 and G3

2025 daylight, identical mask: MAE 0.0396 -> 0.0329, WIS 0.0290 -> 0.0214, coverage 80.3%.
Summer is slightly worse than Round 1 (0.0181 vs 0.0173); the ensemble average, not the trees, carries most of the gain.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P4.2: Live multi-model solar inference

**Files:**
- Create: `ml/live_solar_v2.py`
- Test: `tests/test_live_solar_v2.py`

**Interfaces:**
- Consumes: `ml.solar_v2` (P4.1), `ml.live_forecast.LiveForecastError`, `tomorrow_local` (Round 1).
- Produces: `request_params`, `fetch_payload`, `frames_from_payload`, `predict_live(frames, target, model_dir, state_path) -> (96-row P10/P50/P90 frame, interval_source)`, `live_solar_forecast_v2(target) -> dict` with `points`, `nwp_models`, `interval_source`, `provenance`.

**Behaviour that matters:** a model with any missing irradiance hour is left out and at least three must remain; each booster file is checked against the manifest's SHA-256 before use; the interval width is read from `data/monitor/conformal_state.json` (written by the nightly monitor, P10.6) and falls back to the manifest value with the source stated in the response. The live API gives the same variable names with a `_<model>` suffix; this was checked against the real endpoint on 9 Oct 2026 (48 complete hours, five models).

- [ ] **Step 1: Write the failing tests** — `tests/test_live_solar_v2.py`

```python
import json
import shutil
from datetime import date

import numpy as np
import pandas as pd
import pytest

from engine import config
from ml import live_solar_v2 as live
from ml import solar_v2
from ml.live_forecast import LiveForecastError

TARGET = date(2026, 10, 12)


def _payload(models=solar_v2.MODELS, scale=1.0, drop=None):
    times = pd.date_range(TARGET.isoformat(), periods=48, freq="h")
    hour = times.hour.to_numpy()
    sun = np.clip(np.sin((hour - 6) / 12 * np.pi), 0, None)
    hourly = {"time": [t.isoformat() for t in times]}
    for i, m in enumerate(models):
        hourly[f"shortwave_radiation_{m}"] = list(sun * 800 * scale * (1 + 0.03 * i))
        hourly[f"direct_normal_irradiance_{m}"] = list(sun * 600)
        hourly[f"diffuse_radiation_{m}"] = list(sun * 120)
        hourly[f"temperature_2m_{m}"] = [30.0] * 48
        hourly[f"cloud_cover_{m}"] = [20.0] * 48
        hourly[f"wind_speed_10m_{m}"] = [6.0] * 48
    if drop:
        hourly[f"shortwave_radiation_{drop}"][5] = None
    return {"hourly": hourly}


@pytest.fixture()
def artifacts(tmp_path):
    """Frozen boosters trained on the real data if present; otherwise skip (they are committed with the repo)."""
    src = solar_v2.MODEL_DIR
    if not (src / "solar_v2_manifest.json").exists():
        pytest.skip("run python -m ml.solar_v2 first")
    for f in src.glob("solar_v2_*"):
        shutil.copy(f, tmp_path / f.name)
    return tmp_path


def test_request_asks_for_all_models_in_one_call():
    p = live.request_params(TARGET)
    assert p["models"] == ",".join(solar_v2.MODELS) and p["start_date"] == "2026-10-12" and p["end_date"] == "2026-10-13"


def test_models_with_gaps_are_left_out_and_too_few_models_is_an_error():
    assert len(live.frames_from_payload(_payload(drop="gfs_global"), TARGET)) == 4
    with pytest.raises(LiveForecastError, match="need 3"):
        live.frames_from_payload(_payload(models=solar_v2.MODELS[:2]), TARGET)
    with pytest.raises(LiveForecastError, match="no valid hourly table"):
        live.frames_from_payload({}, TARGET)


def test_frozen_models_give_96_ordered_intervals_and_a_stated_width_source(artifacts, tmp_path):
    frames = live.frames_from_payload(_payload(), TARGET)
    fc, source = live.predict_live(frames, TARGET, artifacts, tmp_path / "missing.json")
    assert len(fc) == 96 and list(fc.columns) == ["p10", "p50", "p90"]
    assert (fc.p10 <= fc.p50).all() and (fc.p50 <= fc.p90).all() and fc.min().min() >= 0 and fc.max().max() <= 1
    assert fc.loc[fc.index.hour == 12, "p50"].max() > 0.3 and fc.loc[fc.index.hour == 2, "p50"].max() == 0
    assert source.startswith("manifest value")


def test_monitor_state_overrides_the_manifest_width(artifacts, tmp_path):
    state = tmp_path / "state.json"
    frames = live.frames_from_payload(_payload(), TARGET)
    narrow, _ = live.predict_live(frames, TARGET, artifacts, tmp_path / "none.json")
    state.write_text(json.dumps({"q": 0.2, "as_of": "2026-10-11"}))
    wide, source = live.predict_live(frames, TARGET, artifacts, state)
    assert source == "monitor state from 2026-10-11" and (wide.p90 - wide.p10).sum() > (narrow.p90 - narrow.p10).sum()
    assert np.allclose(wide.p50, narrow.p50)


def test_a_tampered_model_file_is_rejected(artifacts, tmp_path):
    (artifacts / "solar_v2_p50.txt").write_text("tampered")
    with pytest.raises(LiveForecastError, match="checksum mismatch"):
        live.predict_live(live.frames_from_payload(_payload(), TARGET), TARGET, artifacts, tmp_path / "none.json")


def test_missing_manifest_is_a_clean_error(tmp_path):
    with pytest.raises(LiveForecastError, match="manifest"):
        live.predict_live(live.frames_from_payload(_payload(), TARGET), TARGET, tmp_path, tmp_path / "none.json")


def test_end_to_end_wiring_with_the_network_and_inference_stubbed(monkeypatch):
    stub = pd.DataFrame({"p10": 0.1, "p50": 0.2, "p90": 0.3}, index=pd.date_range("2026-10-12", periods=96, freq="15min"))
    monkeypatch.setattr(live, "fetch_payload", lambda target, site=None: _payload())
    monkeypatch.setattr(live, "predict_live", lambda frames, target, **kw: (stub, "stub"))
    r = live.live_solar_forecast_v2(TARGET)
    assert len(r["points"]) == 96 and r["interval_source"] == "stub" and r["nwp_models"] == sorted(solar_v2.MODELS)
    assert r["provenance"].startswith("modeled") and r["points"][0] == {"t": "00:00", "p10": 0.1, "p50": 0.2, "p90": 0.3}
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/test_live_solar_v2.py -v`
Expected: `ModuleNotFoundError: No module named 'ml.live_solar_v2'`.

- [ ] **Step 3: Create `ml/live_solar_v2.py`**

```python
"""Live next-day solar inference for v2: several NWP models from Open-Meteo, frozen v2 boosters, current conformal width.

The conformal width comes from `data/monitor/conformal_state.json` when the nightly monitor has written one
(the last 60 days of realised errors); otherwise the value stored in the model manifest is used and the result
says so (`interval_source`).

Usage: python -m ml.live_solar_v2 [--date YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import requests

from engine import config
from ml import solar_v2
from ml.live_forecast import LiveForecastError, tomorrow_local

FORECAST_API = "https://api.open-meteo.com/v1/forecast"
MODEL_DIR = solar_v2.MODEL_DIR
STATE_PATH = config.ROOT / "data" / "monitor" / "conformal_state.json"
MIN_MODELS = 3


def request_params(target: date, models: tuple[str, ...] = solar_v2.MODELS, site: config.Site | None = None) -> dict:
    site = site or config.SITES["mathura"]
    return {"latitude": site.latitude, "longitude": site.longitude, "timezone": config.TIMEZONE,
            "start_date": target.isoformat(), "end_date": (target + timedelta(days=1)).isoformat(),
            "hourly": ",".join(config.WEATHER_VARS), "models": ",".join(models)}


def fetch_payload(target: date, site: config.Site | None = None) -> dict:
    try:
        r = requests.get(FORECAST_API, params=request_params(target, site=site), timeout=30)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as exc:
        raise LiveForecastError(f"Open-Meteo multi-model request failed: {exc}") from exc


def frames_from_payload(payload: dict, target: date, models: tuple[str, ...] = solar_v2.MODELS) -> dict[str, pd.DataFrame]:
    """One two-day hourly frame per model that returned complete irradiance; others are left out."""
    try:
        table = pd.DataFrame(payload["hourly"])
        table["time"] = pd.to_datetime(table["time"], errors="raise")
        table = table.set_index("time")
    except (KeyError, TypeError, ValueError) as exc:
        raise LiveForecastError("Open-Meteo response has no valid hourly table") from exc
    start = pd.Timestamp(target)
    table = table[(table.index >= start) & (table.index < start + pd.Timedelta(days=2))]
    frames = {}
    for m in models:
        cols = {f"{v}_{m}": v for v in config.WEATHER_VARS}
        if not set(cols) <= set(table.columns):
            continue
        frame = table[list(cols)].rename(columns=cols).apply(pd.to_numeric, errors="coerce")
        if len(frame) == 48 and frame["shortwave_radiation"].notna().all():
            frames[m] = frame
    if len(frames) < MIN_MODELS:
        raise LiveForecastError(f"only {len(frames)} NWP models returned complete data; need {MIN_MODELS}")
    return frames


def _conformal_q(manifest: dict, state_path: Path) -> tuple[float, str]:
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        return float(state["q"]), f"monitor state from {state['as_of']}"
    except (OSError, ValueError, KeyError):
        return float(manifest["conformal_q"]), "manifest value from the end of the training year"


def predict_live(frames: dict[str, pd.DataFrame], target: date, model_dir: Path = MODEL_DIR,
                 state_path: Path = STATE_PATH) -> tuple[pd.DataFrame, str]:
    """96 quarter-hour P10/P50/P90 values (kW per installed kW) for `target` and the source of the interval width."""
    manifest_path = model_dir / "solar_v2_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LiveForecastError("solar v2 manifest is unavailable or invalid") from exc
    X = solar_v2.ensemble_features(frames)
    if list(manifest["feature_names"]) != solar_v2.FEATURES:
        raise LiveForecastError("live feature schema does not match the trained model")
    day = X["clearsky_ghi"] > 0
    out = pd.DataFrame(0.0, index=X.index, columns=list(solar_v2.QUANTILES))
    for q in solar_v2.QUANTILES:
        path = model_dir / manifest["model_files"][q]
        try:
            blob = path.read_bytes()
        except OSError as exc:
            raise LiveForecastError(f"solar v2 model artifact could not be read: {exc}") from exc
        if hashlib.sha256(blob).hexdigest() != manifest["model_sha256"][q]:
            raise LiveForecastError(f"checksum mismatch for {path.name}")
        out.loc[day, q] = lgb.Booster(model_file=str(path)).predict(X.loc[day, solar_v2.FEATURES])
    out[:] = np.sort(out.to_numpy(), axis=1)
    out = out.add(X["pv_mean"], axis=0).clip(lower=0)
    out[~day] = 0.0
    q_width, source = _conformal_q(manifest, state_path)
    out.loc[day, "p10"] = (out.loc[day, "p10"] - q_width).clip(lower=0)
    out.loc[day, "p90"] = out.loc[day, "p90"] + q_width
    out = out.clip(upper=1.0)
    quarter = out.resample("15min").interpolate("time").loc[target.isoformat()]
    if len(quarter) != 96 or quarter.isna().any().any():
        raise LiveForecastError("live inference did not produce 96 complete intervals")
    return quarter.astype("float32"), source


def live_solar_forecast_v2(target: date | None = None) -> dict:
    target = target or tomorrow_local()
    frames = frames_from_payload(fetch_payload(target), target)
    forecast, source = predict_live(frames, target)
    return {"target": "solar", "unit": "kW per installed kW", "date": target.isoformat(), "model": "GridTwin solar v2",
            "nwp_models": sorted(frames), "interval_source": source,
            "provenance": "modeled: multi-model NWP through pvlib PVWatts plus LightGBM residual quantiles",
            "points": [{"t": ts.strftime("%H:%M"), **{q: round(float(row[q]), 4) for q in solar_v2.QUANTILES}}
                       for ts, row in forecast.iterrows()]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=date.fromisoformat, default=None)
    result = live_solar_forecast_v2(ap.parse_args().date)
    print(json.dumps({"date": result["date"], "nwp_models": result["nwp_models"], "interval_source": result["interval_source"],
                      "peak_p50": max(p["p50"] for p in result["points"])}, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests, then one real call**

Run: `python -m pytest tests/test_live_solar_v2.py -v && python -m ml.live_solar_v2`
Expected: `7 passed`; the call prints five model names, `"interval_source": "manifest value from the end of the training year"` and a `peak_p50` between 0.4 and 0.8 for an October day. If the network is unavailable the command fails with `Open-Meteo multi-model request failed`, which is the intended error.

- [ ] **Step 5: Commit**

```bash
git add ml/live_solar_v2.py tests/test_live_solar_v2.py
git commit -m "feat(ml): live multi-model solar inference with checksummed boosters and monitor-refreshed interval width

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P4.3: Foundation-model benchmark (B3)

**Files:**
- Create: `ml/benchmark.py`
- Test: `tests/test_benchmark.py`
- Output (tracked): `ml/reports/solar_benchmark.json`

**Interfaces:**
- Consumes: `ml.solar_v2` (P4.1), `ml.metrics` (P2.4).
- Produces: `build_frames`, `chronos_forecast(past, future, pipeline=None, batch_days=60)`, `compare(y, mask, candidates, reference)` with an `adopt` flag, `run(district)`.

**Adoption rule (written before the result was known):** a candidate replaces the reference only if its WIS is at least 5% lower on 2025 **and** the deployment can supply yesterday's observed PV. Measured: Chronos-2 with `pv_mean`, `ghi_mean`, `cloud_mean` covariates and a 14-day context scores MAE 0.0318, coverage 78.6%, WIS 0.0207 against solar v2's 0.0214, a 3.3% gain, so the spike verdict is **not adopted**; the build re-runs the comparison with the final features and decides by this rule. TimesFM 2.5 was not run in the spike: its Hugging Face repository answers (spike S4) but its Python API was not inspected, and adding a second foundation model before the first one clears the bar would not change a decision. Document it as "not evaluated".

- [ ] **Step 1: Install the optional packages**

Run: `pip install -r requirements-ml.txt && pip install torch --index-url https://download.pytorch.org/whl/cu124`
Expected: `python -c "import chronos, torch; print(chronos.__version__, torch.cuda.is_available())"` prints `2.3.2 True` (or `False` on a CPU-only machine; the benchmark then takes about 10 minutes instead of about 1).

- [ ] **Step 2: Write the failing tests** — `tests/test_benchmark.py`

```python
import numpy as np
import pandas as pd
import pytest

from ml import benchmark

IDX = pd.date_range("2025-01-01", "2025-02-28 23:00", freq="h")


@pytest.fixture(scope="module")
def data():
    rng = np.random.default_rng(3)
    hour = IDX.hour.to_numpy()
    base = np.clip(np.sin((hour - 6) / 12 * np.pi), 0, None)
    y = pd.Series(base * rng.uniform(0.4, 1.0, len(IDX) // 24)[np.arange(len(IDX)) // 24], index=IDX)
    X = pd.DataFrame({"pv_mean": base * 0.7, "ghi_mean": base * 600, "cloud_mean": 40.0}, index=IDX)
    return X, y


def test_frames_have_a_full_context_and_a_24_hour_future_per_day(data):
    X, y = data
    days = pd.date_range("2025-01-20", "2025-01-25")
    past, future = benchmark.build_frames(X, y, days)
    assert past.id.nunique() == future.id.nunique() == 6
    assert (past.groupby("id").size() == benchmark.CONTEXT_HOURS).all() and (future.groupby("id").size() == 24).all()
    # nothing from the target day leaks into its own context
    first = past[past.id == "2025-01-20"]
    assert first.timestamp.max() == pd.Timestamp("2025-01-19 23:00")
    assert "target" not in future.columns


def test_days_without_enough_context_are_skipped(data):
    X, y = data
    past, future = benchmark.build_frames(X, y, pd.date_range("2025-01-03", "2025-01-05"))      # fewer than 14 days of history
    assert past.empty and future.empty


def test_chronos_wrapper_renames_quantiles_and_clips_at_zero(data):
    X, y = data

    class Fake:
        def predict_df(self, df, future_df, **kw):
            assert kw["prediction_length"] == 24 and kw["quantile_levels"] == [0.1, 0.5, 0.9]
            t = future_df[["id", "timestamp"]].copy()
            t["target_name"], t["predictions"] = "target", 0.0
            t["0.1"], t["0.5"], t["0.9"] = -0.1, 0.2, 0.4
            return t

    past, future = benchmark.build_frames(X, y, pd.date_range("2025-01-20", "2025-01-22"))
    out = benchmark.chronos_forecast(past, future, pipeline=Fake(), batch_days=2)
    assert list(out.columns) == ["p10", "p50", "p90"] and len(out) == 72 and (out.p10 == 0).all() and (out.p90 == 0.4).all()


def test_adoption_needs_a_five_percent_better_wis(data):
    _, y = data
    mask = pd.Series(True, index=IDX)
    good = pd.DataFrame({"p10": y - 0.1, "p50": y, "p90": y + 0.1})
    wide = pd.DataFrame({"p10": y - 0.4, "p50": y, "p90": y + 0.4})
    scores = benchmark.compare(y, mask, {"v2": wide, "foundation": good}, reference="v2")
    assert scores["foundation"]["adopt"] is True and scores["v2"]["adopt"] is False
    almost = benchmark.compare(y, mask, {"v2": good, "foundation": good}, reference="v2")
    assert almost["foundation"]["wis_gain_vs_reference"] == 0 and almost["foundation"]["adopt"] is False


@pytest.mark.realdata
def test_real_benchmark_reports_both_pipelines_on_the_same_hours():
    """Needs the raw files plus torch and chronos-forecasting; the adoption flag is a result, not an expectation."""
    pytest.importorskip("chronos")
    report = benchmark.run()
    a, b = report["scores_2025"]["solar_v2_lightgbm"], report["scores_2025"]["chronos2_with_covariates"]
    assert a["n"] == b["n"] and report["scores_2025"]["solar_v2_lightgbm"]["adopt"] is False
```

- [ ] **Step 3: Run them and see them fail**

Run: `python -m pytest tests/test_benchmark.py -v`
Expected: `ModuleNotFoundError: No module named 'ml.benchmark'`.

- [ ] **Step 4: Create `ml/benchmark.py`**

```python
"""B3: foundation-model benchmark. Chronos-2 with covariates against the solar v2 LightGBM pipeline, same splits.

The foundation model is used as a benchmark only. It is adopted only if its weighted interval score is at least 5%
better on 2025 AND the deployment can supply yesterday's observed PV (it uses a 14-day context of observations, which
the LightGBM pipeline does not need). Requires `pip install -r requirements-ml.txt`.
"""
from __future__ import annotations

import pandas as pd

from ml import metrics

ADOPTION_WIS_GAIN = 0.05
CONTEXT_HOURS = 24 * 14
COVARIATES = ("pv_mean", "ghi_mean", "cloud_mean")


def build_frames(X: pd.DataFrame, y: pd.Series, days: pd.DatetimeIndex, covariates=COVARIATES,
                 context_hours: int = CONTEXT_HOURS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One series per target day: observations and covariates up to 23:00 the day before, covariates for the 24 hours of the day."""
    cov = X[list(covariates)].ffill().fillna(0.0)
    past, future = [], []
    for d in days:
        ctx = X.index[(X.index >= d - pd.Timedelta(hours=context_hours)) & (X.index < d)]
        fut = X.index[(X.index >= d) & (X.index < d + pd.Timedelta(days=1))]
        if len(ctx) < context_hours or len(fut) < 24:
            continue
        past.append(pd.DataFrame({"id": str(d.date()), "timestamp": ctx, "target": y.loc[ctx].to_numpy()}).join(cov.loc[ctx].reset_index(drop=True)))
        future.append(pd.DataFrame({"id": str(d.date()), "timestamp": fut}).join(cov.loc[fut].reset_index(drop=True)))
    if not past:
        return pd.DataFrame(columns=["id", "timestamp", "target", *covariates]), pd.DataFrame(columns=["id", "timestamp", *covariates])
    return pd.concat(past, ignore_index=True), pd.concat(future, ignore_index=True)


def chronos_forecast(past: pd.DataFrame, future: pd.DataFrame, pipeline=None, batch_days: int = 60) -> pd.DataFrame:
    """P10/P50/P90 per hour from Chronos-2. `pipeline` can be injected (tests); otherwise amazon/chronos-2 is loaded."""
    if pipeline is None:
        import torch
        from chronos import Chronos2Pipeline
        pipeline = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map="cuda" if torch.cuda.is_available() else "cpu")
    ids = past["id"].unique()
    parts = []
    for i in range(0, len(ids), batch_days):
        chunk = ids[i:i + batch_days]
        parts.append(pipeline.predict_df(past[past.id.isin(chunk)], future_df=future[future.id.isin(chunk)], id_column="id",
                                         timestamp_column="timestamp", target="target", prediction_length=24,
                                         quantile_levels=[0.1, 0.5, 0.9]))
    out = pd.concat(parts).rename(columns={"0.1": "p10", "0.5": "p50", "0.9": "p90"}).set_index("timestamp")[["p10", "p50", "p90"]]
    return out.clip(lower=0)


def compare(y: pd.Series, mask: pd.Series, candidates: dict[str, pd.DataFrame], reference: str) -> dict:
    """Scores for every candidate on the identical mask, plus the adoption decision against the reference."""
    scores = {}
    for name, pred in candidates.items():
        t = mask & pred["p50"].notna()
        scores[name] = {"n": int(t.sum()), "mae_p50": round(float((pred["p50"][t] - y[t]).abs().mean()), 4),
                        "coverage": round(metrics.coverage(y[t], pred["p10"][t], pred["p90"][t]), 3),
                        "wis": round(metrics.wis(y[t], pred["p10"][t], pred["p50"][t], pred["p90"][t]), 4)}
    ref = scores[reference]["wis"]
    for name, s in scores.items():
        s["wis_gain_vs_reference"] = round(1 - s["wis"] / ref, 3)
        s["adopt"] = bool(name != reference and s["wis_gain_vs_reference"] >= ADOPTION_WIS_GAIN)
    return scores


def run(district: str = "mathura") -> dict:
    """Chronos-2 against the solar v2 pipeline on daylight hours of 2025. Needs the raw files and requirements-ml.txt."""
    import json
    from ml import solar_v2
    X, y, _, used = solar_v2.load_dataset(district)
    day = X["clearsky_ghi"] > 0
    test = day & (X.index.year == 2025)
    raw = solar_v2.predict(solar_v2.fit(X, y, day & (X.index < "2024-11-01")), X)
    v2 = solar_v2.rolling_conformal(raw, y, day, pd.date_range("2025-01-01", "2025-12-31"), calibration_start="2024-11-01")
    past, future = build_frames(X, y, pd.date_range("2025-01-01", "2025-12-31"))
    chronos = chronos_forecast(past, future).reindex(X.index)
    scores = compare(y, test, {"solar_v2_lightgbm": v2, "chronos2_with_covariates": chronos}, reference="solar_v2_lightgbm")
    report = {"scores_2025": scores, "nwp_models_used": used,
              "caveat": "Chronos-2 sees the previous 14 days of observed PV; the LightGBM pipeline needs none. "
                        "Adoption therefore also requires a live source of yesterday's PV."}
    out = solar_v2.REPORT.with_name("solar_benchmark.json")
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    import json
    print(json.dumps(run()["scores_2025"], indent=2))
```

- [ ] **Step 5: Run the tests and the real benchmark**

Run: `python -m pytest tests/test_benchmark.py -v && python -m ml.benchmark`
Expected: `4 passed, 1 skipped` (the real-data test runs only with `-m realdata` and `chronos` installed); the benchmark prints both pipelines on `n: 4414` with `"adopt": false` for Chronos-2 and a `wis_gain_vs_reference` near 0.033. If the gain is ≥0.05 on your run, the rule says adopt only if yesterday's PV is available in production; write that decision into `docs/model_cards/solar_v2.md` (P10.9) and do not change any code in this phase.

- [ ] **Step 6: Commit**

```bash
git add ml/benchmark.py tests/test_benchmark.py ml/reports/solar_benchmark.json
git commit -m "feat(ml): Chronos-2 vs solar v2 benchmark with a pre-registered adoption rule (B3)

Chronos-2 WIS 0.0207 vs 0.0214 (3.3%, below the 5% bar) and it needs yesterday's observed PV: not adopted.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task P4.4: Measured-plant yield calibration and cold-start forecast (A7, B4)

**Files:**
- Create: `ml/pv_calibration.py`, `ml/coldstart.py`, `scripts/calibrate_pv.py`
- Test: `tests/test_pv_calibration_coldstart.py`
- Optional output: `data/processed/pv_yield_factor.json`

**Interfaces:**
- Consumes: nothing from earlier tasks except `pandas`/`numpy`.
- Produces: `pv_calibration.read_plant_csv(path, timestamp_col, power_col, unit)`, `yield_factor(measured_kw, kwp, modelled_kw_per_kwp) -> {"factor", "p10", "p90", "n_days", "usable"}`; `coldstart.shrunk_factor(observed_ratio, n_days, prior, prior_weight_days)`, `uncertainty_spread(n_days)`, `forecast_new_system(per_kwp, kwp, factor, n_days)`.

**Gate G7 branch (do this first, 15 minutes).** Try to obtain the Karnataka 72 kWp plant data (IEEE DataPort). Outcomes: (a) the file downloads with capacity metadata: run the calibration script; (b) a login is required or the capacity is not stated: skip the script, keep the 14% system-loss assumption, and write "yield not calibrated against measured data" under the PV assumption on the Proof page. Both outcomes are valid; the code and tests below stand either way.

**Stated assumptions:** the widening of the cold-start interval (15% at zero history, shrinking with a 30-day prior weight) is an **assumption**, not a measured quantity; the Proof page says so.

- [ ] **Step 1: Write the failing tests** — `tests/test_pv_calibration_coldstart.py`

```python
import numpy as np
import pandas as pd
import pytest

from ml import coldstart, pv_calibration

IDX = pd.date_range("2025-03-01", periods=24 * 40, freq="h")


def _modelled():
    hour = IDX.hour.to_numpy()
    return pd.Series(np.clip(np.sin((hour - 6) / 12 * np.pi), 0, None) * 0.8, index=IDX)


def test_yield_factor_recovers_the_true_loss_and_ignores_outage_days():
    modelled = _modelled()
    measured = modelled * 72 * 0.9                             # a 72 kWp plant that yields 10% less than modelled
    measured[(IDX >= "2025-03-10") & (IDX < "2025-03-12")] = 0.0   # two outage days
    r = pv_calibration.yield_factor(measured, 72, modelled)
    assert r["factor"] == pytest.approx(0.9, abs=1e-3) and r["usable"] and r["n_days"] == 40


def test_too_few_days_are_not_usable_and_no_data_returns_the_neutral_factor():
    modelled = _modelled()
    short = pv_calibration.yield_factor((modelled * 10)[: 24 * 5], 10, modelled)
    assert short["factor"] == pytest.approx(1.0, abs=1e-3) and short["usable"] is False
    empty = pv_calibration.yield_factor(pd.Series(dtype=float), 10, modelled)
    assert empty == {"factor": 1.0, "p10": 1.0, "p90": 1.0, "n_days": 0, "usable": False}


def test_plant_csv_is_read_in_watts_or_kilowatts(tmp_path):
    f = tmp_path / "plant.csv"
    pd.DataFrame({"ts": pd.date_range("2025-03-01 10:00", periods=4, freq="30min"), "power": [2000, 4000, 6000, 8000]}).to_csv(f, index=False)
    s = pv_calibration.read_plant_csv(f, "ts", "power", unit="W")
    assert s.iloc[0] == pytest.approx(3.0) and s.iloc[1] == pytest.approx(7.0)


def test_factor_starts_at_the_prior_and_moves_toward_the_roof_own_readings():
    assert coldstart.shrunk_factor(None, 0) == 1.0
    assert coldstart.shrunk_factor(0.8, 0, prior=0.95) == 0.95
    f10, f60, f600 = (coldstart.shrunk_factor(0.8, n) for n in (10, 60, 600))
    assert 1.0 > f10 > f60 > f600 > 0.8 and f600 == pytest.approx(0.8, abs=0.015)


def test_new_roof_forecast_scales_with_size_and_widens_while_history_is_short():
    per = pd.DataFrame({"p10": [0.2], "p50": [0.4], "p90": [0.6]}, index=pd.DatetimeIndex(["2025-05-01 12:00"]))
    new, old = coldstart.forecast_new_system(per, 3.0, n_days=0), coldstart.forecast_new_system(per, 3.0, n_days=300)
    assert new.p50.iloc[0] == pytest.approx(1.2) and (new.p90 - new.p10).iloc[0] > (old.p90 - old.p10).iloc[0]
    assert new.p10.iloc[0] < old.p10.iloc[0] < old.p50.iloc[0] < old.p90.iloc[0] < new.p90.iloc[0]
    assert coldstart.forecast_new_system(per, 3.0, factor=0.9, n_days=300).p50.iloc[0] == pytest.approx(1.08)


def test_calibrate_script_recovers_the_loss_from_files(tmp_path):
    import json

    from engine import config, profiles
    from scripts.calibrate_pv import calibrate
    idx = pd.date_range("2025-03-01", periods=24 * 30, freq="h")
    clear = profiles.clearsky_ghi(idx).to_numpy()
    hourly = {"time": [t.isoformat() for t in idx], "shortwave_radiation": list(clear), "direct_normal_irradiance": list(clear * 0.7),
              "diffuse_radiation": list(clear * 0.2), "temperature_2m": [30.0] * len(idx), "cloud_cover": [10.0] * len(idx),
              "wind_speed_10m": [2.0] * len(idx)}
    weather = tmp_path / "w.json"
    weather.write_text(json.dumps({"hourly": hourly}))
    site = config.Site(12.97, 77.59, 900)
    modelled = profiles.pv_hourly(profiles.read_weather(weather), site)
    csv = tmp_path / "plant.csv"
    pd.DataFrame({"ts": idx, "kw": (modelled * 72 * 0.85).to_numpy()}).to_csv(csv, index=False)
    r = calibrate(csv, "ts", "kw", "kW", 72.0, weather, site)
    assert r["factor"] == pytest.approx(0.85, abs=0.01) and r["usable"] and r["n_days"] >= 25
```

- [ ] **Step 2: Run them and see them fail**

Run: `python -m pytest tests/test_pv_calibration_coldstart.py -v`
Expected: `ImportError: cannot import name 'coldstart' from 'ml'`.

- [ ] **Step 3: Create `ml/pv_calibration.py`**

```python
"""A7: calibrate the modelled PV yield against a measured plant (kW per installed kWp).

The modelled yield comes from pvlib PVWatts with a flat 14% system loss. A measured plant tells us whether that
loss assumption is too kind or too harsh. The factor is a median of daily ratios over productive hours, so one cloudy
afternoon or an outage does not move it.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

MIN_MODELLED_KW_PER_KWP = 0.25       # only hours when the sun is clearly producing
MIN_HOURS_PER_DAY = 4
MIN_DAYS = 20


def read_plant_csv(path: Path, timestamp_col: str, power_col: str, *, unit: str = "kW") -> pd.Series:
    """Hourly mean power in kW from a plant file. `unit` is kW or W. Timestamps are taken as local time (IST)."""
    df = pd.read_csv(path, parse_dates=[timestamp_col])
    scale = {"kW": 1.0, "W": 1e-3}[unit]
    s = pd.to_numeric(df.set_index(timestamp_col)[power_col], errors="coerce") * scale
    return s.resample("h").mean().rename("measured_kw")


def yield_factor(measured_kw: pd.Series, kwp: float, modelled_kw_per_kwp: pd.Series) -> dict:
    """Ratio of measured to modelled energy per day over productive hours, and its spread.

    Returns {"factor", "p10", "p90", "n_days", "usable"}; `usable` is False when there are too few days to trust.
    """
    both = pd.concat([measured_kw / kwp, modelled_kw_per_kwp], axis=1, keys=["m", "p"]).dropna()
    both = both[both["p"] >= MIN_MODELLED_KW_PER_KWP]
    if both.empty:
        return {"factor": 1.0, "p10": 1.0, "p90": 1.0, "n_days": 0, "usable": False}
    daily = both.groupby(both.index.normalize()).agg(m=("m", "sum"), p=("p", "sum"), n=("m", "size"))
    daily = daily[daily["n"] >= MIN_HOURS_PER_DAY]
    ratio = (daily["m"] / daily["p"]).replace([np.inf, -np.inf], np.nan).dropna()
    if ratio.empty:
        return {"factor": 1.0, "p10": 1.0, "p90": 1.0, "n_days": 0, "usable": False}
    return {"factor": round(float(ratio.median()), 4), "p10": round(float(ratio.quantile(0.1)), 4),
            "p90": round(float(ratio.quantile(0.9)), 4), "n_days": int(len(ratio)), "usable": bool(len(ratio) >= MIN_DAYS)}
```

- [ ] **Step 4: Create `ml/coldstart.py`**

```python
"""B4: forecast a rooftop that has no history yet, and improve as its own readings arrive.

A new system starts from the district's per-kWp forecast times its installed kWp. Its yield factor starts at the
prior (1.0, or a plant-calibrated value from `ml.pv_calibration`) and moves toward what its own meter shows,
weighted by the number of observed days. The interval is widened while the factor is still uncertain.
The widening constant (15% of output at zero history) is an ASSUMPTION, not a measured quantity.
"""
from __future__ import annotations

import pandas as pd

PRIOR_WEIGHT_DAYS = 30.0
INITIAL_SPREAD = 0.15


def shrunk_factor(observed_ratio: float | None, n_days: int, prior: float = 1.0, prior_weight_days: float = PRIOR_WEIGHT_DAYS) -> float:
    """Posterior-style blend: (n x observed + w x prior) / (n + w)."""
    if observed_ratio is None or n_days <= 0:
        return float(prior)
    return float((n_days * observed_ratio + prior_weight_days * prior) / (n_days + prior_weight_days))


def uncertainty_spread(n_days: int, prior_weight_days: float = PRIOR_WEIGHT_DAYS) -> float:
    """Extra relative width of the interval; falls from INITIAL_SPREAD toward zero as days accumulate."""
    return INITIAL_SPREAD * prior_weight_days / (max(n_days, 0) + prior_weight_days)


def forecast_new_system(per_kwp: pd.DataFrame, kwp: float, *, factor: float = 1.0, n_days: int = 0) -> pd.DataFrame:
    """P10/P50/P90 in kW for one system of `kwp` installed kilowatts, from the district forecast per kWp."""
    spread = uncertainty_spread(n_days)
    out = pd.DataFrame(index=per_kwp.index)
    out["p10"] = per_kwp["p10"] * kwp * factor * (1 - spread)
    out["p50"] = per_kwp["p50"] * kwp * factor
    out["p90"] = per_kwp["p90"] * kwp * factor * (1 + spread)
    return out
```

- [ ] **Step 5: Create `scripts/calibrate_pv.py` (used only if gate G7 passes, and for any later utility plant data)**

```python
"""A7: compute the yield factor of a measured plant against the modelled PV for the same site and period.

Usage:
  python -m scripts.calibrate_pv --csv data/raw/plant.csv --timestamp-col ts --power-col kw --unit kW --kwp 72 \
      --weather data/raw/weather_plant.json --lat 12.97 --lon 77.59 --alt 900
Writes data/processed/pv_yield_factor.json. The weather file is an Open-Meteo archive download for the plant's own
coordinates (same variables as config.WEATHER_VARS).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from engine import config, profiles
from ml.pv_calibration import read_plant_csv, yield_factor


def calibrate(csv: Path, timestamp_col: str, power_col: str, unit: str, kwp: float, weather: Path, site: config.Site) -> dict:
    measured = read_plant_csv(csv, timestamp_col, power_col, unit=unit)
    modelled = profiles.pv_hourly(profiles.read_weather(weather), site)
    return yield_factor(measured, kwp, modelled)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--timestamp-col", required=True)
    ap.add_argument("--power-col", required=True)
    ap.add_argument("--unit", choices=("kW", "W"), default="kW")
    ap.add_argument("--kwp", type=float, required=True)
    ap.add_argument("--weather", type=Path, required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--alt", type=float, default=0.0)
    ap.add_argument("--out", type=Path, default=config.PROCESSED_DIR / "pv_yield_factor.json")
    a = ap.parse_args()
    result = calibrate(a.csv, a.timestamp_col, a.power_col, a.unit, a.kwp, a.weather, config.Site(a.lat, a.lon, a.alt))
    a.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
```

Run it with the plant file's real column names, its kWp and its coordinates, and a weather file downloaded for those coordinates; for example `python -m scripts.calibrate_pv --csv data/raw/plant.csv --timestamp-col ts --power-col kw --unit kW --kwp 72 --weather data/raw/weather_plant.json --lat 12.97 --lon 77.59 --alt 900`. Expected: `usable: true` with at least 20 days. A factor outside 0.6 to 1.1 means a unit or time-zone error in the file, not a finding. The script's unit test passes without any real plant data.

- [ ] **Step 6: Run the tests**

Run: `python -m pytest tests/test_pv_calibration_coldstart.py -v`
Expected: `6 passed`.

- [ ] **Step 7: Commit**

```bash
git add ml/pv_calibration.py ml/coldstart.py scripts/calibrate_pv.py tests/test_pv_calibration_coldstart.py
git commit -m "feat(ml): measured-plant yield calibration and cold-start forecast for new rooftops (A7, B4)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

**Phase 4 exit check:** `python -m pytest -q tests` green; `ml/reports/solar_v2.json` shows five models passing gate G2 and `gate_g3_passes: true` (or the Round 1 model is kept and the reason is recorded); `git log --oneline` shows four commits in this phase.


---

# PHASE 5: SCENARIOS, RISK AND THE HONEST VERDICT

**Deliverable:** tomorrow becomes a set of correlated scenarios (sun, demand, grid voltage); the engine replays all of them; the output is P(unsafe) per 15 minutes, expected unsafe hours with a range, a watch/act level, and a verdict that names the binding limit.

**Repo changes:** adds `engine/risk.py`, `engine/scenario_gen.py`, `engine/reliability.py`; **replaces** `engine/verdict.py` with the complete file below (a superset of the P1.3 version: the old `binding_limit`, `describe`, `build_verdict` are unchanged); adds a three-line `day_z` option to `UpstreamModel.sample` (already in the P2.5 text).

**Measured (Mathura 2019–2021 legacy data, 293 usable days):** day-level rank correlation of the three anomalies: demand index vs upstream voltage offset **−0.34** (heavy-demand days have lower grid voltage), solar clearness vs upstream offset **−0.20**, clearness vs demand **+0.06**. These are small-to-moderate; the copula matters but is not dominant.

### Task P5.1: Risk engine and array verdicts (D1, D7)

**Files:** Create `engine/risk.py`; replace `engine/verdict.py`; Test `tests/test_risk_verdict.py`.
**Interfaces:** `assess_risk(solver, scn, controls, rule, *, watch=0.20, act=0.50) -> RiskResult`; `binding_limit_arrays(viol, res, rule, s=0)`; `shortfall(limit, rule, network) -> str`.
**Rules:** level is `act` if any step has P(unsafe) ≥ 50%, `watch` if ≥ 20%, else `ok`; window risk is the probability of an unsafe spell of at least 15 min / 1 h / 3 h / 24 h (risk depends strongly on the window); solver failure counts as unsafe.

`engine/risk.py`

```python
"""D1: turn sampled scenarios into a probability of unsafe voltage or overload."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from engine.rules import VoltageRule
from engine.solver import DaySolver
from engine.types import Controls, DayScenarioBatch
from engine.violations import STEP_H, evaluate

WINDOWS_STEPS = {"15 min": 1, "1 h": 4, "3 h": 12, "24 h": 96}


def longest_run(flags: np.ndarray) -> np.ndarray:
    """Longest run of consecutive True per row of an (S, T) boolean array."""
    best = np.zeros(flags.shape[0], dtype=int)
    cur = np.zeros(flags.shape[0], dtype=int)
    for t in range(flags.shape[1]):
        cur = np.where(flags[:, t], cur + 1, 0)
        best = np.maximum(best, cur)
    return best


@dataclass
class RiskResult:
    t: pd.DatetimeIndex
    p_unsafe: np.ndarray                 # (T,) share of scenarios unsafe at each step
    expected_unsafe_hours: float
    unsafe_hours_p10: float
    unsafe_hours_p90: float
    peak_voltage_v: dict                 # P10 / P50 / P90 of the per-scenario peak phase voltage
    level: str                           # "ok", "watch" or "act"
    first_watch: str | None
    first_act: str | None
    shares: dict                         # probability that a scenario has any violation of each kind
    window_risk: dict                    # probability of an unsafe spell at least this long
    n_scenarios: int
    rule_id: str
    extra: dict = field(default_factory=dict)


def assess_risk(solver: DaySolver, scn: DayScenarioBatch, controls: Controls, rule: VoltageRule, *,
                watch: float = 0.20, act: float = 0.50) -> RiskResult:
    res = solver.solve(scn, controls)
    viol = evaluate(res, rule)
    n = scn.shape[0]
    p = viol.unsafe.mean(axis=0)
    hours = viol.unsafe.sum(axis=1) * STEP_H
    peak_v = np.nanmax(np.where(res.converged[:, :, None, None], res.u_pu, np.nan), axis=(1, 2, 3)) * 230.0
    runs = longest_run(viol.unsafe)
    stamp = lambda i: scn.t[int(i)].strftime("%H:%M")  # noqa: E731
    watch_idx, act_idx = np.flatnonzero(p >= watch), np.flatnonzero(p >= act)
    return RiskResult(
        t=scn.t, p_unsafe=p, expected_unsafe_hours=float(hours.mean()),
        unsafe_hours_p10=float(np.quantile(hours, 0.1)), unsafe_hours_p90=float(np.quantile(hours, 0.9)),
        peak_voltage_v={f"p{q}": float(np.nanquantile(peak_v, q / 100)) for q in (10, 50, 90)},
        level="act" if len(act_idx) else "watch" if len(watch_idx) else "ok",
        first_watch=stamp(watch_idx[0]) if len(watch_idx) else None,
        first_act=stamp(act_idx[0]) if len(act_idx) else None,
        shares={k: float(getattr(viol, k).any(axis=1).mean()) for k in ("over", "under", "line", "trafo", "solver")},
        window_risk={name: float((runs >= steps).mean()) for name, steps in WINDOWS_STEPS.items()},
        n_scenarios=n, rule_id=rule.id,
        extra={"passes": res.passes},
    )
```

`engine/verdict.py` (complete file; replaces the P1.3 version)

```python
"""Name the limit that stops a fix from working, and build the honest verdict."""
from __future__ import annotations

import math

import numpy as np

NOMINAL_V = 230.0
ORDER = ("trafo_overload", "line_overload", "overvoltage", "undervoltage", "solver_failure")


def binding_limit(steps: list[dict]) -> dict | None:
    counts: dict[str, int] = {}
    worst: dict[str, dict] = {}
    for s in steps:
        for t in {v["type"] for v in s["violations"]}:
            counts[t] = counts.get(t, 0) + 1
        for v in s["violations"]:
            cur = worst.get(v["type"])
            if cur is None or abs(v["value"] - v["limit"]) > abs(cur["value"] - cur["limit"]):
                worst[v["type"]] = v
    if not counts:
        return None
    rank = lambda t: ORDER.index(t) if t in ORDER else len(ORDER)  # noqa: E731
    top = min(counts, key=lambda t: (-counts[t], rank(t)))
    return {"type": top, "steps": counts[top], "worst": worst[top]}


def describe(limit: dict) -> str:
    t, n, w = limit["type"], limit["steps"], limit["worst"]
    when = f"in {n} step{'s' if n != 1 else ''}"
    if t == "overvoltage":
        return f"voltage reached {w['value'] * NOMINAL_V:.0f} V against a {w['limit'] * NOMINAL_V:.0f} V limit {when}"
    if t == "undervoltage":
        return f"voltage fell to {w['value'] * NOMINAL_V:.0f} V against a {w['limit'] * NOMINAL_V:.0f} V limit {when}"
    if t == "trafo_overload":
        return f"transformer loading reached {w['value']:.0f}% against a {w['limit']:.0f}% limit {when}"
    if t == "line_overload":
        return f"wire loading reached {w['value']:.0f}% against a {w['limit']:.0f}% limit {when}"
    return f"the power flow did not converge {when}"


def build_verdict(results: list[dict], safe: list[dict]) -> dict:
    if safe:
        return {"safe_action_found": True, "recommended": safe[0]["action_id"],
                "message": f"Recommended: {safe[0]['label']}", "binding_limit": None, "closest": None}
    closest = min(results, key=lambda r: (r["remaining_violation_steps"], r["cost"]["curtailed_kwh"]))
    limit = closest.get("binding_limit")
    why = f" The limit that stops it: {describe(limit)}." if limit else ""
    return {"safe_action_found": False, "recommended": None, "closest": closest["action_id"], "binding_limit": limit,
            "message": (f"No safe action: every option leaves violations. Closest is '{closest['label']}' with "
                        f"{closest['remaining_violation_steps']} unsafe steps.{why}")}


# ---- array-based versions used by the v2 engine -------------------------------------------------------------

def binding_limit_arrays(v, res, rule, s: int = 0) -> dict | None:
    """Same shape as `binding_limit`, computed from the violation arrays of scenario `s`."""
    counts = {"trafo_overload": int(v.trafo[s].sum()), "line_overload": int(v.line[s].sum()),
              "overvoltage": int(v.over[s].sum()), "undervoltage": int(v.under[s].sum()),
              "solver_failure": int(v.solver[s].sum())}
    counts = {k: n for k, n in counts.items() if n}
    if not counts:
        return None
    top = min(counts, key=lambda t: (-counts[t], ORDER.index(t)))
    ok = res.converged[s]
    if top == "overvoltage":
        value, limit = float(np.nanmax(res.u_pu[s][ok])), rule.vmax_pu
    elif top == "undervoltage":
        value, limit = float(np.nanmin(res.u_pu[s][ok])), rule.vmin_pu
    elif top == "trafo_overload":
        value, limit = float(np.nanmax(res.trafo_loading_pct[s][ok])), 100.0
    elif top == "line_overload":
        value, limit = float(np.nanmax(res.line_loading_pct[s][ok])), 100.0
    else:
        value, limit = 0.0, 0.0
    return {"type": top, "steps": counts[top], "worst": {"value": round(value, 4), "limit": limit}}


def shortfall(limit: dict, rule, network) -> str:
    """What the closest option would still need, in plain words."""
    t, w = limit["type"], limit["worst"]
    if t == "overvoltage":
        excess = w["value"] - w["limit"]
        steps = max(1, math.ceil(excess / 0.025))
        return (f"about {excess * NOMINAL_V:.0f} V less voltage at the worst moments: roughly {steps} more transformer tap "
                f"step{'s' if steps != 1 else ''}, or tighter limits on solar export at those moments")
    if t == "undervoltage":
        return (f"about {(w['limit'] - w['value']) * NOMINAL_V:.0f} V more voltage at the far end: a heavier conductor "
                f"or a closer transformer")
    if t == "trafo_overload":
        kva = math.ceil(w["value"] / 100 * network.trafo.sn_va / 1000 / 25) * 25
        return f"a transformer of at least {kva:.0f} kVA (now {network.trafo.sn_va / 1000:.0f} kVA)"
    if t == "line_overload":
        return f"a heavier conductor on the most loaded section (loaded to {w['value']:.0f}%)"
    return "a closer look at the network model, because the power flow does not converge"
```

`tests/test_risk_verdict.py`

```python
import warnings

import numpy as np
import pytest

from engine.dayinputs import scenarios_from_legacy
from engine.grid import build_grid
from engine.network import from_pandapower
from engine.powerflow import day_inputs
from engine.risk import assess_risk, longest_run
from engine.rules import get_rule
from engine.solver import DaySolver
from engine.types import Controls, DayScenarioBatch
from engine.verdict import binding_limit_arrays, shortfall
from engine.violations import evaluate

warnings.filterwarnings("ignore")


@pytest.fixture(scope="module")
def network():
    return from_pandapower(build_grid(1.0), phases="round_robin")


@pytest.fixture(scope="module")
def scn(network):
    return scenarios_from_legacy(day_inputs("2019-05-15"), network)


def _spread(scn, solar_scales, upstream_shifts):
    n = len(solar_scales)
    return DayScenarioBatch(scn.t, np.repeat(scn.load_kw, n, axis=0), scn.pv_per_kwp * np.array(solar_scales)[:, None],
                            scn.upstream_pu + np.array(upstream_shifts)[:, None], scn.load_pf, tuple(map(str, range(n))))


def test_longest_run():
    flags = np.array([[0, 1, 1, 0, 1, 1, 1, 0], [0, 0, 0, 0, 0, 0, 0, 0]], dtype=bool)
    assert longest_run(flags).tolist() == [3, 0]


def test_risk_rises_with_solar_and_names_the_hours(network, scn):
    rule = get_rule("pm10")
    solver = DaySolver(network, asymmetric=True)
    sunny = assess_risk(solver, _spread(scn, [1.0] * 30, [0.0] * 30), Controls(), rule)
    dull = assess_risk(solver, _spread(scn, [0.3] * 30, [0.0] * 30), Controls(), rule)
    assert 0.0 <= dull.p_unsafe.min() and sunny.p_unsafe.max() <= 1.0
    assert sunny.expected_unsafe_hours > dull.expected_unsafe_hours
    assert sunny.level == "act" and sunny.first_act is not None
    assert set(sunny.window_risk) == {"15 min", "1 h", "3 h", "24 h"}
    assert sunny.window_risk["15 min"] >= sunny.window_risk["3 h"]


def test_risk_has_spread_when_the_scenarios_differ(network, scn):
    rule = get_rule("pm10")
    solver = DaySolver(network, asymmetric=True)
    mixed = assess_risk(solver, _spread(scn, np.linspace(0.3, 1.1, 40), np.linspace(-0.03, 0.03, 40)), Controls(), rule)
    assert 0 < mixed.p_unsafe.max() < 1 and mixed.unsafe_hours_p10 < mixed.unsafe_hours_p90
    assert mixed.peak_voltage_v["p10"] < mixed.peak_voltage_v["p90"]


def test_binding_limit_from_arrays_matches_the_legacy_wording(network, scn):
    res = DaySolver(network, asymmetric=False).solve(scn)
    rule = get_rule("pm10")
    limit = binding_limit_arrays(evaluate(res, rule), res, rule)
    assert limit["type"] == "overvoltage" and limit["steps"] == 26
    assert limit["worst"]["value"] * 230 == pytest.approx(263.1, abs=0.3) and limit["worst"]["limit"] == 1.10


def test_shortfall_words(network):
    over = {"type": "overvoltage", "steps": 3, "worst": {"value": 1.0777, "limit": 1.06}}
    assert "tap step" in shortfall(over, get_rule("up_2005"), network)
    trafo = {"type": "trafo_overload", "steps": 2, "worst": {"value": 172.0, "limit": 100.0}}
    assert "450 kVA" in shortfall(trafo, get_rule("pm10"), network)          # 1.72 x 250 kVA = 430, rounded up to 25
```

Run: `python -m pytest tests/test_risk_verdict.py -v` (5 tests). Commit: `feat(risk): scenario-based P(unsafe), windows, watch/act, array verdicts with shortfall (D1, D7)`.

### Task P5.2: Joint scenario generator (B5)

**Files:** Create `engine/scenario_gen.py`; Test `tests/test_scenario_gen.py`.
**Interfaces:** `day_table(load_kw, pv, upstream) -> DataFrame`, `fit_copula(table) -> (3,3)`, `quantile_path(fc, z)`, `AnalogPool.build(load_kw)`, `ScenarioGenerator(corr, upstream_model, analogs).sample(date, n, solar_fc, demand_fc, prev_day_upstream_mean, n_homes, rng, temperature_c=None) -> DayScenarioBatch`.
**Method:** Gaussian copula on day-level rank-normal scores of (solar clearness, demand level, upstream offset). Solar within the day = shared day-level draw (70% of variance) plus AR(1) wobble (φ 0.9). Demand = forecast curve at the drawn level times each home's ratio to the street mean taken from random analog days (same month and weekday type; nearest month if none). Upstream = `UpstreamModel.sample(..., day_z=z_upstream)`.
**Stated limitation (printed on the Proof page):** the copula models climatological anomalies of the observed years because no forecast archive overlaps the meter years.

`engine/scenario_gen.py`

```python
"""B5: joint scenarios for tomorrow from three marginal forecasts and a day-level correlation.

Solar (clearness), demand (level) and the upstream voltage (day offset) are not independent: sunny days differ from
cloudy ones in grid voltage, and heavy-demand days pull the voltage down. A Gaussian copula on the day-level rank-normal
scores of those three anomalies (estimated from the CEEW years) couples the draws. Within a day the solar error is a
mix of the shared day-level draw and an AR(1) wobble, because cloud errors persist but not perfectly.

Stated limitation: the copula models CLIMATOLOGICAL anomalies of the observed years. Forecast archives do not overlap
the meter years, so forecast-error correlation cannot be estimated. The Proof page says so.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from engine.types import DayScenarioBatch
from engine.upstream import UpstreamModel

SLOTS = 96
Z10 = float(stats.norm.ppf(0.9))                 # 1.2816: the P90 level in standard-normal units
ANOMALIES = ("clearness", "demand_index", "upstream_offset")
MIN_METERS = 5
MIN_SLOTS = 80
RATIO_FLOOR_KW = 0.05
RATIO_CAP = 8.0


def day_table(load_kw: pd.DataFrame, pv_kw_per_kwp: pd.Series, upstream_pu: pd.Series) -> pd.DataFrame:
    """One row per day with the three anomalies.

    clearness      daily PV energy over the 90th percentile of the surrounding 31 days (a robust clear-day reference)
    demand_index   daily mean demand over the 31-day rolling median
    upstream_offset daily mean upstream voltage minus its calendar-month mean
    """
    street = load_kw.mean(axis=1).where(load_kw.notna().sum(axis=1) >= MIN_METERS)
    pv_daily = pv_kw_per_kwp.resample("D").sum()
    table = pd.DataFrame({"demand": street.resample("D").mean(), "up": upstream_pu.resample("D").mean(),
                          "slots": street.resample("D").count()})
    table = table[table["slots"] >= MIN_SLOTS].dropna()
    ref = pv_daily.rolling(31, center=True, min_periods=10).quantile(0.9)
    table["clearness"] = (pv_daily / ref).reindex(table.index)
    table["demand_index"] = table["demand"] / table["demand"].rolling(31, center=True, min_periods=10).median()
    table["upstream_offset"] = table["up"] - table["up"].groupby(table.index.month).transform("mean")
    return table[list(ANOMALIES)].dropna()


def fit_copula(table: pd.DataFrame) -> np.ndarray:
    """3x3 correlation of the rank-normal scores, in the order of ANOMALIES."""
    if len(table) < 60:
        raise ValueError("need at least 60 days to estimate the day-level correlation")
    z = table[list(ANOMALIES)].rank().sub(0.5).div(len(table)).apply(stats.norm.ppf)
    return z.corr().to_numpy()


def quantile_path(fc: pd.DataFrame, z: np.ndarray) -> np.ndarray:
    """Forecast value at standard-normal level `z` (per scenario and step) from the P10/P50/P90 columns.

    Piecewise linear through (-1.28, p10), (0, p50), (+1.28, p90) and extended linearly beyond, never below zero.
    `fc` has T rows; `z` is (S,) or (S, T). Returns (S, T).
    """
    p10, p50, p90 = (fc[c].to_numpy(float)[None, :] for c in ("p10", "p50", "p90"))
    z = np.asarray(z, float)
    z = z[:, None] if z.ndim == 1 else z
    lower = p50 + (z / Z10) * (p50 - p10)
    upper = p50 + (z / Z10) * (p90 - p50)
    return np.clip(np.where(z < 0, lower, upper), 0.0, None)


@dataclass
class AnalogPool:
    """Observed full days of per-meter demand, grouped by (month, weekend)."""
    days: dict            # (month, weekend) -> list of (96, meters) arrays, meters with complete data that day
    mean_by_day: dict     # same keys -> list of (96,) street means

    @classmethod
    def build(cls, load_kw: pd.DataFrame) -> "AnalogPool":
        days, means = {}, {}
        for d, g in load_kw.groupby(load_kw.index.normalize()):
            if len(g) != SLOTS:
                continue
            full = g.loc[:, g.notna().all()]
            if full.shape[1] < MIN_METERS:
                continue
            key = (d.month, int(d.dayofweek >= 5))
            days.setdefault(key, []).append(full.to_numpy(float))
            means.setdefault(key, []).append(full.to_numpy(float).mean(axis=1))
        if not days:
            raise ValueError("no complete day with enough meters")
        return cls(days, means)

    def _key(self, date: pd.Timestamp) -> tuple:
        key = (date.month, int(date.dayofweek >= 5))
        if key in self.days:
            return key
        same_type = [k for k in self.days if k[1] == key[1]] or list(self.days)
        return min(same_type, key=lambda k: min((k[0] - key[0]) % 12, (key[0] - k[0]) % 12))

    def home_ratios(self, date, n_scn: int, n_homes: int, rng: np.random.Generator) -> np.ndarray:
        """(S, T, H) demand of each home relative to its day's street mean, from random analog days and meters."""
        key = self._key(pd.Timestamp(date))
        pool, means = self.days[key], self.mean_by_day[key]
        out = np.empty((n_scn, SLOTS, n_homes))
        for s in range(n_scn):
            i = int(rng.integers(len(pool)))
            cols = rng.integers(pool[i].shape[1], size=n_homes)
            out[s] = np.clip(pool[i][:, cols] / np.maximum(means[i], RATIO_FLOOR_KW)[:, None], 0, RATIO_CAP)
        return out


@dataclass
class ScenarioGenerator:
    corr: np.ndarray                # (3, 3) copula correlation in the order of ANOMALIES
    upstream: UpstreamModel
    analogs: AnalogPool
    day_share: float = 0.7          # share of the solar error variance that is shared across the whole day
    intraday_phi: float = 0.9       # AR(1) persistence of the remaining, hour-to-hour part

    def sample(self, date, n: int, solar_fc: pd.DataFrame, demand_fc: pd.DataFrame, prev_day_upstream_mean: float,
               n_homes: int, rng: np.random.Generator, temperature_c: np.ndarray | None = None, load_pf: float = 0.95) -> DayScenarioBatch:
        """`n` correlated scenarios for `date`. Both forecasts are 96-row frames with p10, p50, p90."""
        if len(solar_fc) != SLOTS or len(demand_fc) != SLOTS:
            raise ValueError("forecasts must have 96 quarter-hour rows")
        date = pd.Timestamp(date)
        z = rng.multivariate_normal(np.zeros(3), self.corr, size=n)                   # (n, 3): clearness, demand, upstream
        # Sun: shared day-level error plus an AR(1) wobble; the marginal at each step stays standard normal.
        eps = rng.normal(size=(n, SLOTS))
        wobble = np.empty_like(eps)
        wobble[:, 0] = eps[:, 0]
        for t in range(1, SLOTS):
            wobble[:, t] = self.intraday_phi * wobble[:, t - 1] + np.sqrt(1 - self.intraday_phi ** 2) * eps[:, t]
        z_solar = np.sqrt(self.day_share) * z[:, [0]] + np.sqrt(1 - self.day_share) * wobble
        pv = quantile_path(solar_fc, z_solar)
        demand_mean = quantile_path(demand_fc, z[:, 1])                                # (n, T)
        ratios = self.analogs.home_ratios(date, n, n_homes, rng)                       # (n, T, H)
        load = demand_mean[:, :, None] * ratios
        upstream = self.upstream.sample(date, n, prev_day_upstream_mean, rng, day_z=z[:, 2])
        ambient = None if temperature_c is None else np.tile(np.asarray(temperature_c, float), (n, 1))
        return DayScenarioBatch(t=pd.date_range(date, periods=SLOTS, freq="15min"), load_kw=load, pv_per_kwp=pv,
                                upstream_pu=upstream, load_pf=load_pf, labels=tuple(f"{date.date()}#{i}" for i in range(n)),
                                ambient_c=ambient)
```

`tests/test_scenario_gen.py`

```python
import warnings

import numpy as np
import pandas as pd
import pytest

from engine import config
from engine.scenario_gen import ANOMALIES, Z10, AnalogPool, ScenarioGenerator, day_table, fit_copula, quantile_path
from engine.upstream import UpstreamModel

warnings.filterwarnings("ignore")
SLOTS = 96


def _forecast(scale=1.0):
    x = np.clip(np.sin((np.arange(SLOTS) - 24) / 48 * np.pi), 0, None)
    return pd.DataFrame({"p10": 0.6 * x * scale, "p50": 0.8 * x * scale, "p90": 1.0 * x * scale}, index=pd.date_range("2025-05-15", periods=SLOTS, freq="15min"))


def _loads(days=70, meters=8, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-05-01", periods=days * SLOTS, freq="15min")
    base = 0.5 + 0.4 * np.sin(2 * np.pi * (idx.hour + idx.minute / 60) / 24) ** 2
    return pd.DataFrame(base.to_numpy()[:, None] * rng.uniform(0.6, 1.4, meters)[None, :] * rng.uniform(0.9, 1.1, (len(idx), meters)), index=idx)


@pytest.fixture(scope="module")
def generator():
    loads = _loads()
    up = pd.Series(1.04 + 0.01 * np.sin(np.arange(len(loads)) / 400) + np.random.default_rng(1).normal(0, 0.003, len(loads)), index=loads.index)
    corr = np.array([[1, 0.0, -0.5], [0.0, 1, -0.4], [-0.5, -0.4, 1]])
    return ScenarioGenerator(corr, UpstreamModel.fit(up), AnalogPool.build(loads))


def test_quantile_path_hits_the_forecast_quantiles_and_never_goes_negative():
    fc = _forecast()
    mid = fc.p50.to_numpy()
    out = quantile_path(fc, np.array([0.0, Z10, -Z10, 3.0, -9.0]))
    assert np.allclose(out[0], fc.p50) and np.allclose(out[1], fc.p90) and np.allclose(out[2], fc.p10)
    assert (out[3] >= out[1]).all() and (out[4] >= 0).all() and out[4].max() < mid.max()
    assert quantile_path(fc, np.zeros((2, SLOTS))).shape == (2, SLOTS)


def test_fitted_copula_recovers_the_correlation_of_day_level_anomalies():
    rng = np.random.default_rng(0)
    true = np.array([[1, 0.1, -0.5], [0.1, 1, -0.3], [-0.5, -0.3, 1]])
    z = rng.multivariate_normal(np.zeros(3), true, 1500)
    table = pd.DataFrame(np.exp(z * 0.1), columns=list(ANOMALIES), index=pd.date_range("2020-01-01", periods=1500))
    assert np.abs(fit_copula(table) - true).max() < 0.08
    with pytest.raises(ValueError, match="at least 60 days"):
        fit_copula(table.iloc[:30])


def test_day_table_has_one_row_per_usable_day_and_three_anomalies():
    loads = _loads(days=70)
    pv = pd.Series(np.clip(np.sin((loads.index.hour - 6) / 12 * np.pi), 0, None), index=loads.index)
    pv = pv * np.repeat(np.random.default_rng(2).uniform(0.5, 1.0, 70), SLOTS)
    up = pd.Series(1.03 + np.random.default_rng(3).normal(0, 0.01, len(loads)), index=loads.index)
    table = day_table(loads, pv, up)
    assert list(table.columns) == list(ANOMALIES) and 55 <= len(table) <= 70
    assert abs(table.demand_index.mean() - 1) < 0.05 and abs(table.upstream_offset.mean()) < 0.01


def test_analog_pool_falls_back_to_the_nearest_month_and_is_reproducible():
    pool = AnalogPool.build(_loads())
    a = pool.home_ratios("2019-05-15", 4, 10, np.random.default_rng(5))
    b = pool.home_ratios("2019-05-15", 4, 10, np.random.default_rng(5))
    assert a.shape == (4, SLOTS, 10) and np.array_equal(a, b) and a.min() >= 0 and a.max() <= 8
    assert pool.home_ratios("2025-09-15", 1, 3, np.random.default_rng(0)).shape == (1, SLOTS, 3)   # only May-June data exist


def test_scenarios_have_the_right_shapes_and_respect_the_forecast(generator):
    scn = generator.sample("2019-05-15", 400, _forecast(), _forecast(0.5), 1.04, 12, np.random.default_rng(7))
    assert scn.load_kw.shape == (400, SLOTS, 12) and scn.pv_per_kwp.shape == (400, SLOTS) and scn.upstream_pu.shape == (400, SLOTS)
    pv_noon = scn.pv_per_kwp[:, 48]
    fc = _forecast().iloc[48]
    assert abs(np.median(pv_noon) - fc.p50) < 0.08 * fc.p50 + 0.02
    lo, hi = np.quantile(pv_noon, [0.1, 0.9])
    assert lo < fc.p50 < hi and (scn.pv_per_kwp >= 0).all() and scn.pv_per_kwp[:, 0].max() == 0     # no sun at midnight
    assert scn.upstream_pu.min() >= 0.8 and scn.upstream_pu.max() <= 1.2 and len(scn.labels) == 400


def test_day_level_correlations_follow_the_copula(generator):
    scn = generator.sample("2019-05-15", 1500, _forecast(), _forecast(0.5), 1.04, 4, np.random.default_rng(11))
    sun, up = scn.pv_per_kwp.mean(axis=1), scn.upstream_pu.mean(axis=1)
    demand = scn.load_kw.mean(axis=(1, 2))
    assert np.corrcoef(sun, up)[0, 1] < -0.15           # copula says -0.5 (diluted by the intraday part)
    assert np.corrcoef(demand, up)[0, 1] < -0.15


def test_same_seed_same_scenarios_and_bad_input_is_rejected(generator):
    args = ("2019-05-15", 5, _forecast(), _forecast(0.5), 1.04, 6)
    a, b = generator.sample(*args, np.random.default_rng(3)), generator.sample(*args, np.random.default_rng(3))
    assert np.array_equal(a.pv_per_kwp, b.pv_per_kwp) and np.array_equal(a.load_kw, b.load_kw)
    with pytest.raises(ValueError, match="96 quarter-hour"):
        generator.sample("2019-05-15", 2, _forecast().iloc[:48], _forecast(), 1.04, 3, np.random.default_rng(0))
    with_temp = generator.sample(*args, np.random.default_rng(3), temperature_c=np.full(SLOTS, 38.0))
    assert with_temp.ambient_c.shape == (5, SLOTS) and with_temp.ambient_c[0, 0] == 38.0


def test_real_data_gives_the_physically_expected_signs():
    base = config.PROCESSED_DIR
    load = pd.read_parquet(base / "load_kw.parquet")
    pv = pd.read_parquet(base / "pv_kw_per_kwp.parquet")["pv_kw_per_kwp"]
    up = pd.read_parquet(base / "upstream_vm_pu.parquet")["upstream_vm_pu"]
    corr = fit_copula(day_table(load, pv, up))
    assert corr.shape == (3, 3) and np.allclose(np.diag(corr), 1)
    assert corr[1, 2] < -0.1          # heavy-demand days have lower grid voltage (measured about -0.34 on Mathura 2019-2021)
```

Run: `python -m pytest tests/test_scenario_gen.py -v` (8 tests). Commit: `feat(scenarios): copula scenario generator with analog demand days (B5)`.

### Task P5.3: Reliability backtest and gate G8 (D1)

**Files:** Create `engine/reliability.py`, `scripts/run_reliability.py`; Output `data/results/reliability_<district>.json`.
**What it answers:** when the system says 60%, were 60% of such steps unsafe? For each held-out day it gives the generator only coarse knowledge (weather class, month, day type, yesterday's voltage), predicts P(unsafe) per step and compares with the replay of what the day actually did. It reports a reliability table in five bins, the Brier score against the base-rate climatology, and predicted vs observed unsafe hours.

`engine/reliability.py`

```python
"""D1: does "P(unsafe) = 60% at 12:30" mean that 60% of such moments really were unsafe? A reliability backtest.

No forecast archive overlaps the CEEW meter years, so the backtest cannot use real forecasts. Instead, for every held-out
day it gives the generator only COARSE knowledge that a forecast would carry: the weather class of the day (cloudy,
mixed, sunny), the month, the day type and yesterday's mean grid voltage. It then predicts P(unsafe) per step and
compares it with the replay of what that day actually did (observed demand, observed voltage, ERA5-driven PV).
The result is an upper bound on risk-model skill with coarse knowledge, not a claim about live forecast skill;
solar forecast calibration is reported separately (ml.solar_v2, 2025).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from engine.risk import assess_risk
from engine.rules import VoltageRule
from engine.scenario_gen import SLOTS, AnalogPool, ScenarioGenerator, day_table, fit_copula
from engine.solver import DaySolver
from engine.types import Controls, DayScenarioBatch, Network
from engine.upstream import UpstreamModel
from engine.violations import evaluate

CLASSES = ("cloudy", "mixed", "sunny")
BINS = np.linspace(0, 1, 6)                      # five reliability bins: 0-0.2 ... 0.8-1.0


@dataclass
class Climatology:
    """P10/P50/P90 curves per (weather class, month) for solar and per (weekend, month) for demand, from training days."""
    thresholds: tuple[float, float]
    solar: dict
    demand: dict

    @staticmethod
    def weather_class(clearness: float, thresholds: tuple[float, float]) -> str:
        return CLASSES[int(clearness >= thresholds[0]) + int(clearness >= thresholds[1])]

    @classmethod
    def build(cls, table: pd.DataFrame, pv: pd.Series, load_kw: pd.DataFrame) -> "Climatology":
        thresholds = tuple(float(x) for x in table["clearness"].quantile([1 / 3, 2 / 3]))
        street = load_kw.mean(axis=1)
        solar_days, demand_days = {}, {}
        for d in table.index:
            pv_day, dem_day = pv.loc[d:d + pd.Timedelta(hours=23, minutes=45)], street.loc[d:d + pd.Timedelta(hours=23, minutes=45)]
            if len(pv_day) != SLOTS or len(dem_day) != SLOTS or dem_day.isna().any():
                continue
            solar_days.setdefault((cls.weather_class(table.loc[d, "clearness"], thresholds), d.month), []).append(pv_day.to_numpy(float))
            demand_days.setdefault((int(d.dayofweek >= 5), d.month), []).append(dem_day.to_numpy(float))

        def quantiles(days):
            a = np.vstack(days)
            return pd.DataFrame(np.quantile(a, [0.1, 0.5, 0.9], axis=0).T, columns=["p10", "p50", "p90"])
        return cls(thresholds, {k: quantiles(v) for k, v in solar_days.items() if len(v) >= 3},
                   {k: quantiles(v) for k, v in demand_days.items() if len(v) >= 3})

    def _nearest(self, table: dict, key: tuple) -> pd.DataFrame:
        if key in table:
            return table[key]
        same = [k for k in table if k[0] == key[0]] or list(table)
        return table[min(same, key=lambda k: min((k[1] - key[1]) % 12, (key[1] - k[1]) % 12))]

    def solar_forecast(self, weather_class: str, month: int) -> pd.DataFrame:
        return self._nearest(self.solar, (weather_class, month))

    def demand_forecast(self, weekend: int, month: int) -> pd.DataFrame:
        return self._nearest(self.demand, (weekend, month))


def actual_scenario(date: pd.Timestamp, load_kw: pd.DataFrame, pv: pd.Series, upstream: pd.Series, n_homes: int,
                    seed: int = 42) -> DayScenarioBatch:
    """What the day really did, on the same street: meters assigned to homes with a seeded draw."""
    day = slice(date, date + pd.Timedelta(hours=23, minutes=45))
    loads = load_kw.loc[day]
    loads = loads.loc[:, loads.notna().all()]
    cols = np.random.default_rng(seed).choice(np.asarray(loads.columns), n_homes)
    return DayScenarioBatch(t=loads.index, load_kw=loads[cols].to_numpy(float)[None], pv_per_kwp=pv.loc[day].to_numpy(float)[None],
                            upstream_pu=upstream.loc[day].to_numpy(float)[None], load_pf=0.95, labels=(str(date.date()),))


def reliability_table(pred: np.ndarray, observed: np.ndarray) -> list[dict]:
    """Mean predicted probability against observed frequency in five bins."""
    p, o = pred.ravel(), observed.ravel().astype(float)
    rows = []
    for lo, hi in zip(BINS[:-1], BINS[1:]):
        m = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        rows.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(m.sum()),
                     "mean_predicted": round(float(p[m].mean()), 3) if m.any() else None,
                     "observed_frequency": round(float(o[m].mean()), 3) if m.any() else None})
    return rows


def brier(pred: np.ndarray, observed: np.ndarray) -> float:
    return float(np.mean((pred - observed.astype(float)) ** 2))


def backtest(network: Network, rule: VoltageRule, load_kw: pd.DataFrame, pv: pd.Series, upstream: pd.Series, *,
             split: str, n_days: int = 40, n_scenarios: int = 30, seed: int = 42, controls: Controls = Controls()) -> dict:
    """Fit everything on days before `split`, then predict and replay `n_days` evenly spaced later days."""
    train_loads, train_up = load_kw[load_kw.index < split], upstream[upstream.index < split]
    table = day_table(train_loads, pv[pv.index < split], train_up)
    full = day_table(load_kw, pv, upstream)
    clim = Climatology.build(table, pv, load_kw)
    gen = ScenarioGenerator(fit_copula(table), UpstreamModel.fit(train_up), AnalogPool.build(train_loads))
    solver = DaySolver(network, asymmetric=True)
    rng = np.random.default_rng(seed)

    def usable(d: pd.Timestamp) -> bool:
        day, prev = slice(d, d + pd.Timedelta(hours=23, minutes=45)), slice(d - pd.Timedelta(days=1), d - pd.Timedelta(minutes=15))
        loads = load_kw.loc[day]
        return (len(loads) == SLOTS and int(loads.notna().all().sum()) >= 5 and len(pv.loc[day]) == SLOTS
                and upstream.loc[day].notna().sum() == SLOTS and upstream.loc[prev].notna().sum() == SLOTS)

    test_days = [d for d in full.index if d >= pd.Timestamp(split) and usable(d)]
    chosen = [test_days[i] for i in np.linspace(0, len(test_days) - 1, min(n_days, len(test_days))).astype(int)]
    predicted, observed, hours_pred, hours_obs = [], [], [], []
    for d in chosen:
        cls = Climatology.weather_class(float(full.loc[d, "clearness"]), clim.thresholds)
        prev_mean = float(upstream.loc[d - pd.Timedelta(days=1):d - pd.Timedelta(minutes=15)].mean())
        scn = gen.sample(d, n_scenarios, clim.solar_forecast(cls, d.month), clim.demand_forecast(int(d.dayofweek >= 5), d.month),
                         prev_mean, network.n_homes, rng)
        risk = assess_risk(solver, scn, controls, rule)
        actual = evaluate(solver.solve(actual_scenario(d, load_kw, pv, upstream, network.n_homes), controls), rule)
        predicted.append(risk.p_unsafe)
        observed.append(actual.unsafe[0])
        hours_pred.append(risk.expected_unsafe_hours)
        hours_obs.append(float(actual.unsafe[0].sum() * 0.25))
    pred, obs = np.array(predicted), np.array(observed)
    base_rate = float(obs.mean())
    b, b_ref = brier(pred, obs), brier(np.full_like(pred, base_rate), obs)
    return {
        "days": len(chosen), "scenarios_per_day": n_scenarios, "split": split, "rule": rule.id,
        "observed_unsafe_share_of_steps": round(base_rate, 4),
        "brier": round(b, 4), "brier_climatology": round(b_ref, 4),
        "brier_skill": round(1 - b / b_ref, 3) if b_ref > 0 else None,
        "reliability": reliability_table(pred, obs),
        "unsafe_hours": {"predicted_mean": round(float(np.mean(hours_pred)), 2), "observed_mean": round(float(np.mean(hours_obs)), 2),
                         "correlation": round(float(np.corrcoef(hours_pred, hours_obs)[0, 1]), 3) if np.std(hours_obs) > 0 and np.std(hours_pred) > 0 else None},
        "limitation": "Generator conditioned on coarse weather class, month, day type and yesterday's voltage; not live forecasts.",
    }
```

**Measured first result, and why it is a known weakness (not hidden):** on the legacy Mathura data (train May–Sep 2019, test Oct 2019–Feb 2021, 24 days, 25 scenarios each, 99-home street, round-robin phases) the backtest **does not yet beat the base rate**: Brier 0.373 vs 0.216 for ±10%, and 0.121 vs 0.025 for ±6% (where 97% of observed steps are unsafe). Predicted unsafe hours per day averaged 11.2 against 16.4 observed (correlation 0.70 for ±10%, 0.48 for ±6%). The low-probability bins are the problem: steps predicted at about 6% were unsafe 67% of the time. That pattern means something systematic is missing from the scenarios, not just noise. The legacy data has no winter in the training window, which is a likely contributor.

**Gate G8:** Brier skill > 0 against the base rate on the full v2 data (both districts, three years, train on earlier years, test on the later year). **If it fails after the diagnosis below, ship the risk numbers with the isotonic recalibration and label them "recalibrated on 2019–2021 history", and show the reliability table on the Proof page. Do not claim calibrated probabilities without the table.**

**Diagnosis checklist (do these in order, stop at the first that explains the gap):**
1. Break the observed unsafe steps by hour and by type (`over`, `under`, `line`, `trafo`) for the test days. If most are outside sun hours, the cause is the upstream-voltage model or the load, not solar.
2. Compare the distribution of the generated upstream voltage with the observed one for the same month. If the observed mean is higher than the model's, the AR(1) day mean is not capturing the level; use the previous-day mean with a larger weight or add a month-and-year level term.
3. Compare generated demand with observed demand per slot for the test days. If the analog pool lacks that season, enlarge the pool (all three years) before judging.
4. Re-run with `n_scenarios=100` to rule out sampling noise.

**Recalibration (only if G8 still fails):** fit `sklearn.isotonic.IsotonicRegression(out_of_bounds="clip")` on (predicted p, observed unsafe) pairs from the training years' backtest, save the mapping to `data/results/risk_calibration.json`, and apply it in `assess_risk` output as `p_unsafe_calibrated` next to the raw value. The UI shows the calibrated number and the raw one in the details.

`scripts/run_reliability.py` (written, not yet run)

```python
"""Run the reliability backtest on the v2 data for one district and rule.

Usage: python -m scripts.run_reliability --district mathura --rule up_2005 --split 2021-01-01
"""
import argparse
import json
import warnings
from pathlib import Path

import pandas as pd

from engine import config
from engine.archetypes import build
from engine.reliability import backtest
from engine.rules import get_rule

warnings.filterwarnings("ignore")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--district", default="mathura", choices=config.DISTRICTS)
    ap.add_argument("--rule", default="up_2005")
    ap.add_argument("--archetype", default="benchmark_250")
    ap.add_argument("--split", default="2021-01-01")
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--scenarios", type=int, default=40)
    a = ap.parse_args()
    base = config.PROCESSED_DIR / "v2"
    load = pd.read_parquet(base / f"load_kw_{a.district}.parquet")
    pv = pd.read_parquet(base / f"pv_kw_per_kwp_{a.district}.parquet")["pv_kw_per_kwp"]
    up = pd.read_parquet(base / f"upstream_vm_pu_{a.district}.parquet")["upstream_vm_pu"]
    result = backtest(build(a.archetype, phases="round_robin"), get_rule(a.rule), load, pv, up,
                      split=a.split, n_days=a.days, n_scenarios=a.scenarios)
    out = Path("data/results") / f"reliability_{a.district}_{a.rule}.json"
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps({k: result[k] for k in ("days", "brier", "brier_climatology", "brier_skill")}, indent=2))


if __name__ == "__main__":
    main()
```

Run: `python -m scripts.run_reliability --district mathura --rule pm10` then `--rule up_2005`; expect 3–6 minutes each. Record the numbers in the commit message whether or not G8 passes.

**Phase 5 exit check:** tests green; `data/results/reliability_*.json` exist; G8 outcome written down.


---

# PHASE 6: THE FIX TOURNAMENT

**Deliverable:** for a street, a rule and a set of scenarios, enumerate every sensible fix, replay each over all scenarios, rank the safe ones lexicographically, and when none is safe say so, name the binding limit and what the closest option would still need.

**Repo changes:** replaces the role of `engine/actions.py` and `engine/ranking.py` (kept until P10.12 so the old API keeps working). New package `engine/fixes/`.

**Measured on the 99-home benchmark (15 May 2019, unbalanced model):** the tournament takes about 80 s (±10%, no battery) to 115 s (±6%, with battery) because the Volt/VAR cases need about 24 damped passes. Under the **±6% UP rule there is genuinely no safe action**: the closest option still leaves about 25–28 unsafe steps. That is the honest headline for UP and it stays that way unless a tournament candidate truly clears it.

**Ranking (lexicographic, in this order):** unsafe steps must be zero in every scenario and every solve must converge; then least curtailed energy (kWh, 0.1 resolution), fewest operations (tap steps, switch operations, phase moves), least battery throughput, **largest voltage margin** (robust choice), and only then least wire loss. The voltage margin sits before losses because equal-cost fixes were otherwise separated by tiny loss differences and the tournament picked a fix with no safety margin.

**Candidates:** transformer tap (0, +1, +2), Volt/VAR (IEEE 1547 Cat B and the Gujarat preset), Volt/Watt, tap plus Volt/VAR, uniform curtailment (60%, 80%), per-house export envelopes, CP-SAT phase reallocation (with a move limit), radial-safe tie switching (at most two operations), community battery sweep (25–150 kW, 2 or 4 hours).

### Task P6.1: Candidate, cost vector and evaluation

**Files:** Create `engine/fixes/__init__.py` (empty), `engine/fixes/base.py`.
**Interfaces:** `Candidate(id, label, kind, network, controls, operations, battery, params)`, `Outcome`, `margin_v`, `cost_vector`, `evaluate_candidate(c, scn, rule, asymmetric=True, design=-1)`.
**Rule:** a candidate is acceptable only if the worst scenario has zero unsafe steps and all solves converged; `summary` is the highest-solar scenario, the robust choice at the P90 case (D8).

`engine/fixes/base.py`

```python
"""A fix candidate, its verified outcome, and the lexicographic ranking."""
from __future__ import annotations

from dataclasses import dataclass, field

from engine.fixes.battery import solve_with_battery
from engine.rules import VoltageRule
from engine.solver import DaySolver
from engine.types import BatterySpec, Controls, DayScenarioBatch, Network
from engine.verdict import binding_limit_arrays
from engine.violations import evaluate, summarise


@dataclass
class Candidate:
    id: str
    label: str
    kind: str                          # tap, inverter, combined, curtailment, envelope, phase, battery, switching
    network: Network
    controls: Controls = field(default_factory=Controls)
    operations: int = 0                # switch operations plus phase moves
    battery: BatterySpec | None = None
    params: dict = field(default_factory=dict)


@dataclass
class Outcome:
    candidate: Candidate
    summary: dict                      # headline numbers for the design (highest-solar) scenario
    unsafe_steps: int                  # worst case over the robust scenario set
    acceptable: bool
    binding_limit: dict | None
    cost: tuple
    rank: int | None = None


def margin_v(summary: dict, rule: VoltageRule) -> float:
    """Smallest distance (volts) between the day's voltage extremes and the rule band; bigger is safer."""
    return min(rule.vmax_pu - summary["max_vm_pu"], summary["min_vm_pu"] - rule.vmin_pu) * rule.nominal_v


def cost_vector(summary: dict, operations: int, rule: VoltageRule) -> tuple:
    """Lexicographic: least solar wasted, fewest operations, least battery use, then the LARGEST voltage margin
    (a robust choice), and only then the least wire loss."""
    return (round(summary["curtailed_kwh"], 1), operations, round(summary["battery_throughput_kwh"], 1),
            -round(margin_v(summary, rule), 1), round(summary["losses_kwh"], 2))


def evaluate_candidate(c: Candidate, scn: DayScenarioBatch, rule: VoltageRule, *, asymmetric: bool = True,
                       design: int = -1) -> Outcome:
    """Replay every robust scenario; safe only if every scenario is safe at all steps and every solve converged."""
    if c.battery is not None:
        res = solve_with_battery(c.network, scn, c.battery, rule, c.controls, asymmetric=asymmetric)
    else:
        res = DaySolver(c.network, asymmetric=asymmetric).solve(scn, c.controls)
    viol = evaluate(res, rule)
    per_scn = viol.unsafe.sum(axis=1)
    worst = int(per_scn.argmax())
    s_design = design % scn.shape[0]
    summary = summarise(res, viol, s_design)
    return Outcome(candidate=c, summary=summary, unsafe_steps=int(per_scn.max()),
                   acceptable=bool(per_scn.max() == 0 and res.converged.all()),
                   binding_limit=binding_limit_arrays(viol, res, rule, worst),
                   cost=cost_vector(summary, c.operations, rule))
```

### Task P6.2: Phase reallocation (D3)

**Files:** Create `engine/fixes/phase_assign.py`.
**Method:** pick the `k` most critical steps (largest net injections), then solve with OR-Tools CP-SAT: minimise the worst phase imbalance in integer-scaled watts subject to a limit on moved homes; `num_workers=1`, seed 42 so the plan is reproducible. The plan is then verified by the power flow like any other candidate.

```python
"""D3: choose the phase of each (movable) home so net injections are balanced at the critical steps.

CP-SAT minimises the largest difference between phase net-injections over the critical steps; the result is
only a proposal, and the tournament verifies it with the full power flow.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from ortools.sat.python import cp_model

SCALE = 100          # kW to integer units of 0.01 kW


@dataclass
class PhasePlan:
    phases: np.ndarray            # (H,) proposed phase per home
    moved: int                    # homes whose phase changed
    imbalance_before_kw: float    # largest phase difference over critical steps
    imbalance_after_kw: float
    status: str


def critical_steps(net_kw: np.ndarray, k: int = 6) -> np.ndarray:
    """Steps with the largest total export and the largest total import (net_kw is (T, H), export positive)."""
    total = net_kw.sum(axis=1)
    return np.unique(np.r_[np.argsort(total)[-k:], np.argsort(total)[:k]])


def _imbalance(phases: np.ndarray, net_kw: np.ndarray, steps: np.ndarray) -> float:
    per_phase = np.stack([net_kw[steps][:, phases == p].sum(axis=1) for p in range(3)], axis=1)
    return float((per_phase.max(axis=1) - per_phase.min(axis=1)).max())


def plan_phases(net_kw: np.ndarray, current: np.ndarray, movable: np.ndarray | None = None,
                max_moves: int | None = None, time_limit_s: float = 20.0, workers: int = 1) -> PhasePlan:
    """net_kw: (T, H) net injection per home (PV minus load). movable: (H,) bool; max_moves: cap on changes."""
    n_h = net_kw.shape[1]
    movable = np.ones(n_h, dtype=bool) if movable is None else np.asarray(movable, dtype=bool)
    steps = critical_steps(net_kw)
    ints = np.rint(net_kw[steps] * SCALE).astype(int)                         # (K, H)

    m = cp_model.CpModel()
    x = [[m.NewBoolVar(f"x{h}_{p}") for p in range(3)] for h in range(n_h)]
    for h in range(n_h):
        m.AddExactlyOne(x[h])
        if not movable[h]:
            m.Add(x[h][int(current[h])] == 1)
    bound = int(np.abs(ints).sum(axis=1).max()) + 1
    z = m.NewIntVar(0, 2 * bound, "z")
    for k in range(len(steps)):
        load = [sum(int(ints[k, h]) * x[h][p] for h in range(n_h)) for p in range(3)]
        for a in range(3):
            for b in range(a + 1, 3):
                m.Add(load[a] - load[b] <= z)
                m.Add(load[b] - load[a] <= z)
    if max_moves is not None:
        stay = [x[h][int(current[h])] for h in range(n_h) if movable[h]]
        m.Add(sum(stay) >= len(stay) - max_moves)
    m.Minimize(z)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = workers          # 1 = reproducible; more is faster but not deterministic
    solver.parameters.random_seed = 42
    status = solver.Solve(m)
    name = solver.StatusName(status)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return PhasePlan(current.copy(), 0, _imbalance(current, net_kw, steps), _imbalance(current, net_kw, steps), name)
    phases = np.array([[solver.Value(x[h][p]) for p in range(3)].index(1) for h in range(n_h)])
    return PhasePlan(phases, int((phases != current).sum()), _imbalance(current, net_kw, steps),
                     _imbalance(phases, net_kw, steps), name)
```

### Task P6.3: Per-house export envelopes (D4)

**Files:** Create `engine/fixes/envelopes.py`.
**Method:** per step, bisect the export limit (kW per home) that removes the violation, weighting homes by voltage sensitivity so the far end gives up more; vectorised over steps. Output is a day-ahead table of limits per home and step. Curtails less than a uniform cap (tested).

```python
"""D4: day-ahead per-house export limits (operating envelopes) by per-step bisection.

For every step independently, find the largest per-home export cap (kW) at which that step is safe.
Steps are independent without a battery, so all 96 bisections run together as one batch.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.rules import VoltageRule
from engine.solver import DaySolver
from engine.types import Controls, DayScenarioBatch
from engine.violations import evaluate


@dataclass
class Envelope:
    limit_kw: np.ndarray        # (T, H) maximum net export per home per step
    infeasible: np.ndarray      # (T,) steps unsafe even at zero export
    curtailed_kwh: float
    iterations: int


def compute_envelope(solver: DaySolver, scn: DayScenarioBatch, rule: VoltageRule, base: Controls = Controls(),
                     weights: np.ndarray | None = None, iterations: int = 14) -> Envelope:
    """`weights` (H,) in (0, 1] scale each home's share of the cap (equal shares by default)."""
    if scn.shape[0] != 1:
        raise ValueError("envelopes are computed for one scenario at a time")
    t = scn.shape[1]
    n_h = solver.network.n_homes
    w = np.ones(n_h) if weights is None else np.asarray(weights, dtype=float)
    cap_max = float(solver.network.house_kwp.max() or 1.0)
    lo, hi = np.zeros(t), np.full(t, cap_max)

    def unsafe_at(c: np.ndarray) -> np.ndarray:
        limit = c[:, None] * w[None, :]
        res = solver.solve(scn, _with_limit(base, limit))
        return evaluate(res, rule).unsafe[0]

    zero_unsafe = unsafe_at(np.zeros(t))
    if not unsafe_at(hi).any():                               # nothing to limit anywhere
        lo = hi.copy()
    else:
        for _ in range(iterations):
            mid = (lo + hi) / 2
            bad = unsafe_at(mid)
            hi = np.where(bad, mid, hi)
            lo = np.where(bad, lo, mid)
    cap = np.where(zero_unsafe, 0.0, lo)
    limit = cap[:, None] * w[None, :]
    res = solver.solve(scn, _with_limit(base, limit))
    curtailed = float((res.pv_avail_kw - res.pv_kw).sum() * 0.25)
    return Envelope(limit_kw=limit, infeasible=zero_unsafe, curtailed_kwh=curtailed, iterations=iterations)


def _with_limit(base: Controls, limit: np.ndarray) -> Controls:
    from dataclasses import replace
    return replace(base, export_limit_kw=limit)
```

### Task P6.4: Radial-safe feeder switching (D5)

**Files:** Create `engine/fixes/switching.py`.
**Method:** candidate tie lines between nodes of different feeders within 150 m (coordinates from the benchmark), at most six ties; each reconfiguration closes one tie and opens one line so the result stays a spanning tree (checked with NetworkX); greedy, at most two operations. Needs `Network.node_xy` (set by `from_pandapower`).

```python
"""D5: radial-safe feeder reconfiguration.

A tie joins the ends of two different feeders; closing it makes one loop, so one line on that loop must be opened
to stay radial. Candidates are (tie, line to open) pairs; every candidate is verified by the power flow.
"""
from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import numpy as np

from engine.types import Network


@dataclass(frozen=True)
class Reconfiguration:
    tie: tuple[int, int]            # nodes joined by the new line
    opened_line: int                # index of the line removed from the original network
    tie_length_m: float
    operations: int = 2             # one closing and one opening


def _graph(network: Network) -> nx.Graph:
    g = nx.Graph()
    for k, (a, b) in enumerate(zip(network.line_from, network.line_to)):
        g.add_edge(int(a), int(b), line=k)
    return g


def feeder_of(network: Network) -> dict[int, int]:
    """Which feeder (child subtree of the transformer's LV node) each node belongs to."""
    g, root = _graph(network), int(network.trafo.to_node)
    out = {root: -1}
    for k, child in enumerate(sorted(g.neighbors(root))):
        for n in nx.node_connected_component(g.subgraph(set(g.nodes) - {root}), child):
            out[n] = k
    return out


def candidate_ties(network: Network, max_distance_m: float = 150.0, max_ties: int = 6) -> list[tuple[int, int, float]]:
    """Pairs of feeder-end nodes on different feeders within `max_distance_m`, nearest first."""
    if network.node_xy is None:
        return []
    g, feeder = _graph(network), feeder_of(network)
    ends = [n for n in g.nodes if g.degree[n] == 1 and n in feeder]
    pairs = []
    for i, u in enumerate(ends):
        for v in ends[i + 1:]:
            if feeder[u] != feeder[v]:
                d = float(np.linalg.norm(network.node_xy[u] - network.node_xy[v]))
                if d <= max_distance_m:
                    pairs.append((u, v, d))
    return sorted(pairs, key=lambda p: p[2])[:max_ties]


def apply(network: Network, rec: Reconfiguration) -> Network:
    """Network after closing the tie and opening the chosen line; the tie uses the street's median per-metre impedance."""
    length = np.maximum(network.line_length_m, 1.0)
    per_m = lambda total: float(np.median(total / length))  # noqa: E731
    new = {"from": rec.tie[0], "to": rec.tie[1], "length_m": rec.tie_length_m,
           "r1": per_m(network.line_r1_ohm) * rec.tie_length_m, "x1": per_m(network.line_x1_ohm) * rec.tie_length_m,
           "r0": per_m(network.line_r0_ohm) * rec.tie_length_m, "x0": per_m(network.line_x0_ohm) * rec.tie_length_m,
           "c1": per_m(network.line_c1_f) * rec.tie_length_m, "i_n": float(np.median(network.line_i_n_a))}
    return network.with_topology(add=[new], remove=[rec.opened_line])


def candidates(network: Network, max_distance_m: float = 150.0, max_ties: int = 6) -> list[Reconfiguration]:
    g = _graph(network)
    out = []
    for u, v, d in candidate_ties(network, max_distance_m, max_ties):
        path = nx.shortest_path(g, u, v)                       # the loop that the tie closes
        for a, b in zip(path[:-1], path[1:]):
            out.append(Reconfiguration((u, v), int(g.edges[a, b]["line"]), d))
    return out
```

### Task P6.5: Community battery sweep (D6)

**Files:** Create `engine/fixes/battery.py`.
**Method:** the battery is three pseudo-homes at its node (one per phase) whose load is the charging power, so the same batch solver is reused, sequentially per step because the state of charge couples the steps. Gains come from probe solves: the measured sensitivity of the highest and lowest voltage to one kW at the peak and at the lowest step (a fixed droop constant failed on this weak feeder). Charge only to bring the highest voltage back to the target, never so hard that the lowest voltage crosses its limit plus a margin; discharge in the evening only while there is headroom. `DaySolver.solve` refuses `controls.battery`; this module is the entry point.

```python
"""D6: community battery with volt-droop control, solved step by step (the battery state couples the steps).

The battery is three pseudo-homes at its node (one per phase) whose 'load' is the charging power, so the same
batch solver is reused. Positive power = charging.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from engine.rules import VoltageRule
from engine.solver import DaySolver
from engine.types import BatterySpec, Controls, DayResult, DayScenarioBatch, Network

STEP_H = 0.25
DISCHARGE_HOURS = range(18, 23)
DISCHARGE_MARGIN_PU = 0.03          # stay this far below the upper limit when discharging
LOW_MARGIN_PU = 0.03                # stay this far above the lower limit when charging
PROBE_KW = 10.0


def with_battery(network: Network, spec: BatterySpec) -> Network:
    return network.replace(house_node=np.r_[network.house_node, [spec.node] * 3],
                           house_phase=np.r_[network.house_phase, [0, 1, 2]],
                           house_kwp=np.r_[network.house_kwp, np.zeros(3)])


def node_sensitivity(solver: DaySolver, scn: DayScenarioBatch, n_homes: int) -> dict:
    """Voltage change (pu per kW) caused by the battery, measured with probe solves at the two steps that matter.

    On a weak overhead feeder one kW at the far end moves the voltage far more than a fixed droop constant assumes,
    and charging moves the lowest voltage (another node and phase) more than the highest. The probe runs at the step
    of the day's highest voltage and at the step of its lowest, using the first scenario:
      charge_max     fall of the highest voltage per kW charged (at the peak step)
      discharge_max  rise of the highest voltage per kW discharged (at the peak step)
      charge_min     fall of the lowest voltage per kW charged (at the lowest step)
    """
    zeros = np.zeros((1, scn.shape[1], 3))                                  # the battery's three pseudo-homes, idle
    first = DayScenarioBatch(scn.t, np.concatenate([scn.load_kw[:1, :, :n_homes], zeros], axis=2), scn.pv_per_kwp[:1],
                             scn.upstream_pu[:1], scn.load_pf, scn.labels[:1])
    u0 = solver.solve(first).u_pu[0]                                       # (T, N, 3), battery at zero output
    peak_step, low_step = int(np.nanmax(u0, axis=(1, 2)).argmax()), int(np.nanmin(u0, axis=(1, 2)).argmin())

    def extremes(step: int, p_kw: float) -> tuple[float, float]:
        sl = slice(step, step + 1)
        load = np.concatenate([first.load_kw[:, sl, :n_homes], np.full((1, 1, 3), p_kw / 3)], axis=2)
        one = DayScenarioBatch(first.t[sl], load, first.pv_per_kwp[:, sl], first.upstream_pu[:, sl], first.load_pf, first.labels)
        u = solver.solve(one).u_pu
        return float(np.nanmax(u)), float(np.nanmin(u))

    (hi0, _), (hi_c, _), (hi_d, _) = extremes(peak_step, 0.0), extremes(peak_step, PROBE_KW), extremes(peak_step, -PROBE_KW)
    (_, lo0), (_, lo_c) = extremes(low_step, 0.0), extremes(low_step, PROBE_KW)
    floor = 1e-5
    return {"charge_max": max((hi0 - hi_c) / PROBE_KW, floor), "discharge_max": max((hi_d - hi0) / PROBE_KW, floor),
            "charge_min": max((lo0 - lo_c) / PROBE_KW, floor), "peak_step": peak_step, "low_step": low_step}


def solve_with_battery(network: Network, scn: DayScenarioBatch, spec: BatterySpec, rule: VoltageRule,
                       controls: Controls = Controls(), *, asymmetric: bool = True) -> DayResult:
    s, t = scn.shape
    n_h = network.n_homes
    solver = DaySolver(with_battery(network, spec), asymmetric=asymmetric)
    base = replace(controls, battery=None)
    soc = np.full(s, spec.soc_start)
    prev_vm, prev_min = np.ones(s), np.ones(s)
    parts, power = [], np.zeros((s, t))
    target = rule.vmax_pu - 0.02
    capacity = spec.kwh
    sens = node_sensitivity(solver, scn, n_h)                    # pu per kW at the battery node
    for i in range(t):
        room = (spec.soc_max - soc) * capacity / (STEP_H * spec.efficiency)
        avail = (soc - spec.soc_min) * capacity * spec.efficiency / STEP_H
        high = prev_vm > target
        # Charge only to bring the highest voltage back to the target, and never so hard that the voltage would fall
        # below the lower limit plus a margin (the feeder end is very sensitive, so the gain is the measured sensitivity).
        floor_kw = np.maximum(prev_min - (rule.vmin_pu + LOW_MARGIN_PU), 0) / sens["charge_min"]
        charge = np.minimum.reduce([np.full(s, spec.kw), room, (prev_vm - target) / sens["charge_max"], floor_kw])
        # Discharge in the evening only while there is headroom below the upper limit.
        headroom = np.maximum(rule.vmax_pu - DISCHARGE_MARGIN_PU - prev_vm, 0) / sens["discharge_max"]
        discharge = np.minimum.reduce([np.full(s, spec.kw / 2), avail, headroom])
        evening = ~high & (scn.t[i].hour in DISCHARGE_HOURS)
        p = np.where(high, charge, np.where(evening, -discharge, 0.0))
        soc = soc + np.where(p > 0, p * spec.efficiency, p / spec.efficiency) * STEP_H / capacity
        power[:, i] = p
        load = np.concatenate([scn.load_kw[:, i:i + 1, :], np.repeat((p / 3)[:, None, None], 3, axis=2)], axis=2)
        step = DayScenarioBatch(scn.t[i:i + 1], load, scn.pv_per_kwp[:, i:i + 1], scn.upstream_pu[:, i:i + 1], scn.load_pf, scn.labels)
        r = solver.solve(step, base)
        parts.append(r)
        prev_vm = np.nan_to_num(np.nanmax(r.u_pu[:, 0], axis=(1, 2)), nan=1.0)
        prev_min = np.nan_to_num(np.nanmin(r.u_pu[:, 0], axis=(1, 2)), nan=1.0)
    cat = lambda name: np.concatenate([getattr(r, name) for r in parts], axis=1)  # noqa: E731
    return DayResult(
        t=scn.t, u_pu=cat("u_pu"), line_loading_pct=cat("line_loading_pct"), trafo_loading_pct=cat("trafo_loading_pct"),
        trafo_p_kw=cat("trafo_p_kw"), losses_kw=cat("losses_kw"), q_loss_kvar=cat("q_loss_kvar"), pv_kw=cat("pv_kw"),
        pv_avail_kw=cat("pv_avail_kw"), inverter_kvar=cat("inverter_kvar"), battery_kw=power, neutral_a=cat("neutral_a"),
        vuf_pct=cat("vuf_pct"), converged=cat("converged"), passes=max(r.passes for r in parts))
```

### Task P6.6: Catalogue and tournament (D2, D7, D8)

**Files:** Create `engine/fixes/catalog.py`, `engine/fixes/tournament.py`; Test `tests/test_fixes.py`.
**Interfaces:** `catalog.build(network, scn, rule, asymmetric=True, include_battery=True, include_switching=True) -> list[Candidate]`; `tournament.run(network, scn, rule, ...) -> TournamentResult(rule_id, before, outcomes, verdict, n_scenarios)`.
**Verdict:** `verdict["safe_action_found"]`, `recommended`, `closest`, `binding_limit`, `still_needs` (plain words from `shortfall`), `baseline_unsafe_steps`.

`engine/fixes/catalog.py`

```python
"""Enumerate the candidate fixes for one street and one robust scenario set."""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from engine.fixes import switching
from engine.fixes.base import Candidate, evaluate_candidate
from engine.fixes.envelopes import compute_envelope
from engine.fixes.phase_assign import plan_phases
from engine.inverters import VoltVarCurve, VoltWattCurve
from engine.rules import VoltageRule
from engine.solver import DaySolver
from engine.types import BatterySpec, Controls, DayScenarioBatch, Network

BATTERY_SIZES_KW = (25, 50, 100, 150)
BATTERY_HOURS = (2, 4)
MAX_PHASE_MOVES_LIMITED = 15


def _design(scn: DayScenarioBatch) -> DayScenarioBatch:
    """The highest-solar scenario alone (the last one), used to design plans that are then verified on all."""
    return DayScenarioBatch(scn.t, scn.load_kw[-1:], scn.pv_per_kwp[-1:], scn.upstream_pu[-1:], scn.load_pf, scn.labels[-1:])


def worst_node(network: Network, scn: DayScenarioBatch, asymmetric: bool = True) -> int:
    res = DaySolver(network, asymmetric=asymmetric).solve(_design(scn))
    per_node = np.nanmax(res.u_pu[0], axis=(0, 2))
    return int(network.lv_nodes[int(per_node.argmax())])


def build(network: Network, scn: DayScenarioBatch, rule: VoltageRule, *, asymmetric: bool = True,
          include_battery: bool = True, include_switching: bool = True) -> list[Candidate]:
    vv, vw = VoltVarCurve(), VoltWattCurve()
    out: list[Candidate] = []
    add = lambda cid, label, kind, **kw: out.append(Candidate(cid, label, kind, kw.pop("network", network), **kw))  # noqa: E731

    add("tap_plus1", "Transformer tap +1 (off-load, seasonal)", "tap", controls=Controls(tap_pos=1), params={"tap_pos": 1})
    add("tap_plus2", "Transformer tap +2 (off-load, seasonal)", "tap", controls=Controls(tap_pos=2), params={"tap_pos": 2})
    add("volt_var", "Smart inverters: IEEE 1547 Volt/VAR", "inverter", controls=Controls(volt_var=vv))
    add("volt_watt", "Smart inverters: IEEE 1547 Volt/Watt", "inverter", controls=Controls(volt_watt=vw))
    add("volt_var_watt", "Smart inverters: Volt/VAR with Volt/Watt", "inverter", controls=Controls(volt_var=vv, volt_watt=vw))
    add("tap1_volt_var", "Tap +1 with IEEE 1547 Volt/VAR", "combined", controls=Controls(tap_pos=1, volt_var=vv))
    add("tap1_volt_var_watt", "Tap +1 with Volt/VAR and Volt/Watt", "combined", controls=Controls(tap_pos=1, volt_var=vv, volt_watt=vw))
    add("tap2_volt_var", "Tap +2 with IEEE 1547 Volt/VAR", "combined", controls=Controls(tap_pos=2, volt_var=vv), params={"tap_pos": 2})
    add("export_cap_80", "Solar export limited to 80% of output", "curtailment", controls=Controls(curtail_keep=0.8), params={"keep": 0.8})
    add("export_cap_60", "Solar export limited to 60% of output", "curtailment", controls=Controls(curtail_keep=0.6), params={"keep": 0.6})

    design = _design(scn)
    # Per-house export limits (operating envelope), alone and after the cheap settings.
    for cid, label, base in (("envelope", "Per-house export limits for tomorrow", Controls()),
                             ("tap1_volt_var_envelope", "Tap +1, Volt/VAR and per-house export limits", Controls(tap_pos=1, volt_var=vv))):
        env = compute_envelope(DaySolver(network, asymmetric=asymmetric), design, rule, base)
        add(cid, label, "envelope", controls=replace(base, export_limit_kw=env.limit_kw),
            params={"infeasible_steps": int(env.infeasible.sum())})

    # Phase reallocation of the homes, proposed by CP-SAT and verified like everything else.
    if asymmetric:
        net_kw = design.pv_per_kwp[0][:, None] * network.house_kwp[None, :] - design.load_kw[0]
        plan = plan_phases(net_kw, network.house_phase)
        few = plan_phases(net_kw, network.house_phase, max_moves=MAX_PHASE_MOVES_LIMITED)
        if few.moved > 0:
            add("phase_rebalance_limited", f"Re-balance phases, at most {MAX_PHASE_MOVES_LIMITED} homes move", "phase",
                network=network.with_phases(few.phases), operations=few.moved,
                params={"moved": few.moved, "imbalance_kw": [few.imbalance_before_kw, few.imbalance_after_kw]})
        if plan.moved > 0:
            net_p = network.with_phases(plan.phases)
            add("phase_rebalance", f"Re-balance phases ({plan.moved} homes move)", "phase", network=net_p, operations=plan.moved,
                params={"moved": plan.moved, "imbalance_kw": [plan.imbalance_before_kw, plan.imbalance_after_kw]})
            add("phase_tap1_volt_var", "Re-balance phases, tap +1 and Volt/VAR", "phase", network=net_p, operations=plan.moved,
                controls=Controls(tap_pos=1, volt_var=vv), params={"moved": plan.moved})

    if include_battery:
        node = worst_node(network, scn, asymmetric)
        for kw in BATTERY_SIZES_KW:
            for hours in BATTERY_HOURS:
                add(f"battery_{kw}kw_{hours}h", f"Community battery {kw} kW / {kw * hours} kWh at the worst node", "battery",
                    battery=BatterySpec(kw=float(kw), kwh=float(kw * hours), node=node), params={"kw": kw, "kwh": kw * hours})

    if include_switching:
        best = None
        for rec in switching.candidates(network):
            net_s = switching.apply(network, rec)
            if not net_s.is_radial():
                continue
            outcome = evaluate_candidate(Candidate("probe", "probe", "switching", net_s), scn, rule, asymmetric=asymmetric)
            key = (outcome.unsafe_steps, outcome.summary["max_vm_pu"])
            if best is None or key < best[0]:
                best = (key, rec, net_s)
        if best is not None:
            _, rec, net_s = best
            params = {"tie": list(rec.tie), "opened_line": rec.opened_line, "tie_length_m": round(rec.tie_length_m, 1)}
            add("switching", "Re-route a feeder through a tie switch", "switching", network=net_s, operations=rec.operations, params=params)
            add("switching_tap1_volt_var", "Tie switch, tap +1 and Volt/VAR", "switching", network=net_s, operations=rec.operations,
                controls=Controls(tap_pos=1, volt_var=vv), params=params)
    return out
```

`engine/fixes/tournament.py`

```python
"""D2, D7, D8: replay every candidate over the robust scenario set, rank the safe ones, give an honest verdict."""
from __future__ import annotations

from dataclasses import dataclass

from engine.fixes import catalog
from engine.fixes.base import Candidate, Outcome, evaluate_candidate
from engine.rules import VoltageRule
from engine.types import DayScenarioBatch, Network
from engine.verdict import build_verdict, shortfall


@dataclass
class TournamentResult:
    rule_id: str
    before: Outcome
    outcomes: list[Outcome]            # safe first (ranked), then the rest by remaining unsafe steps
    verdict: dict
    n_scenarios: int


def _as_result(o: Outcome) -> dict:
    return {"action_id": o.candidate.id, "label": o.candidate.label, "remaining_violation_steps": o.unsafe_steps,
            "cost": {"curtailed_kwh": o.summary["curtailed_kwh"]}, "binding_limit": o.binding_limit}


def run(network: Network, scn: DayScenarioBatch, rule: VoltageRule, *, asymmetric: bool = True,
        include_battery: bool = True, include_switching: bool = True, extra: list[Candidate] | None = None) -> TournamentResult:
    before = evaluate_candidate(Candidate("none", "Do nothing", "none", network), scn, rule, asymmetric=asymmetric)
    cands = catalog.build(network, scn, rule, asymmetric=asymmetric, include_battery=include_battery,
                          include_switching=include_switching) + list(extra or [])
    outcomes = [evaluate_candidate(c, scn, rule, asymmetric=asymmetric) for c in cands]
    safe = sorted((o for o in outcomes if o.acceptable), key=lambda o: o.cost)
    for rank, o in enumerate(safe, 1):
        o.rank = rank
    rest = sorted((o for o in outcomes if not o.acceptable), key=lambda o: (o.unsafe_steps, o.cost))
    results = [_as_result(o) for o in safe + rest]
    verdict = build_verdict(results, [r for r in results[:len(safe)]])
    if not verdict["safe_action_found"] and verdict["binding_limit"]:
        verdict["still_needs"] = shortfall(verdict["binding_limit"], rule, network)
    verdict["baseline_unsafe_steps"] = before.unsafe_steps
    return TournamentResult(rule.id, before, safe + rest, verdict, scn.shape[0])
```

`tests/test_fixes.py`

```python
import warnings

import numpy as np
import pytest

from engine.dayinputs import scenarios_from_legacy
from engine.fixes import catalog, switching
from engine.fixes.battery import solve_with_battery, with_battery
from engine.fixes.envelopes import compute_envelope
from engine.fixes.phase_assign import plan_phases
from engine.grid import build_grid
from engine.network import from_pandapower
from engine.powerflow import day_inputs
from engine.rules import get_rule
from engine.solver import DaySolver
from engine.types import BatterySpec, Controls
from engine.violations import evaluate

warnings.filterwarnings("ignore")
RULE = get_rule("pm10")


@pytest.fixture(scope="module")
def network():
    return from_pandapower(build_grid(1.0), phases="random")


@pytest.fixture(scope="module")
def scn(network):
    return scenarios_from_legacy(day_inputs("2019-05-15"), network)


def test_phase_plan_balances_a_lopsided_street_and_respects_limits():
    net_kw = np.random.default_rng(0).uniform(-0.5, 1.5, size=(8, 12))        # 8 steps, 12 homes
    current = np.zeros(12, dtype=int)                                          # everyone on phase A
    plan = plan_phases(net_kw, current, time_limit_s=5)
    assert plan.status in {"OPTIMAL", "FEASIBLE"} and plan.imbalance_after_kw < 0.3 * plan.imbalance_before_kw
    assert len(set(plan.phases.tolist())) == 3

    movable = np.arange(12) < 6
    pinned = plan_phases(net_kw, current, movable=movable, time_limit_s=5)
    assert (pinned.phases[~movable] == 0).all()

    capped = plan_phases(net_kw, current, max_moves=3, time_limit_s=5)
    assert capped.moved <= 3


def test_phase_plan_is_reproducible():
    net_kw = np.random.default_rng(1).uniform(-0.5, 1.5, size=(8, 12))
    a = plan_phases(net_kw, np.zeros(12, dtype=int), time_limit_s=5)
    b = plan_phases(net_kw, np.zeros(12, dtype=int), time_limit_s=5)
    assert (a.phases == b.phases).all()


def test_envelope_reduces_unsafe_steps_and_curtails_less_than_uniform(network, scn):
    solver = DaySolver(network)
    before = evaluate(solver.solve(scn), RULE).unsafe.sum()
    env = compute_envelope(solver, scn, RULE)
    assert env.limit_kw.shape == (96, network.n_homes) and (env.limit_kw >= 0).all()
    after = evaluate(solver.solve(scn, Controls(export_limit_kw=env.limit_kw)), RULE).unsafe.sum()
    assert after < before
    assert env.curtailed_kwh < 500                       # uniform curtailment needs about 880 kWh for the same day


def test_battery_lowers_the_peak_and_respects_its_state_of_charge(network, scn):
    base = DaySolver(network).solve(scn)
    spec = BatterySpec(kw=100.0, kwh=400.0, node=catalog.worst_node(network, scn))
    res = solve_with_battery(network, scn, spec, RULE)
    assert np.nanmax(res.u_pu) < np.nanmax(base.u_pu)
    assert 0 < res.battery_kw.max() <= spec.kw + 1e-6
    power = res.battery_kw[0]
    soc = spec.soc_start + np.cumsum(np.where(power > 0, power * spec.efficiency, power / spec.efficiency) * 0.25 / spec.kwh)
    assert soc.min() >= spec.soc_min - 1e-6 and soc.max() <= spec.soc_max + 1e-6
    assert with_battery(network, spec).n_homes == network.n_homes + 3


def test_every_switching_candidate_stays_radial(network):
    assert network.is_radial()
    cands = switching.candidates(network)
    assert cands, "the benchmark street has feeder ends close enough to tie"
    for rec in cands[:12]:
        net_s = switching.apply(network, rec)
        assert net_s.n_lines == network.n_lines and net_s.is_radial()


def test_a_loop_is_detected():
    n = from_pandapower(build_grid(0.0))
    loop = n.with_topology(add=[{"from": int(n.line_from[0]), "to": int(n.line_to[-1]), "r1": 0.1, "x1": 0.03, "r0": 0.3,
                                 "x0": 0.09, "c1": 0.0, "i_n": 200.0, "length_m": 50.0}])
    assert not loop.is_radial()


def test_equal_cost_fixes_are_separated_by_voltage_margin_before_loss():
    from engine.fixes.base import cost_vector
    narrow = {"curtailed_kwh": 0.0, "battery_throughput_kwh": 0.0, "losses_kwh": 1.0, "max_vm_pu": 1.050, "min_vm_pu": 0.905}
    wide = {"curtailed_kwh": 0.0, "battery_throughput_kwh": 0.0, "losses_kwh": 2.0, "max_vm_pu": 1.080, "min_vm_pu": 0.950}
    assert cost_vector(wide, 0, RULE) < cost_vector(narrow, 0, RULE)          # wide margin wins despite higher loss
    assert cost_vector(wide, 0, RULE) < cost_vector({**wide, "curtailed_kwh": 5.0}, 0, RULE)   # solar wasted still dominates
```

Run: `python -m pytest tests/test_fixes.py -v` (7 tests). Then the three headline runs and record them in the commit message:

```bash
python - <<'PY'
import warnings; warnings.filterwarnings("ignore")
from engine.dayinputs import scenarios_from_legacy
from engine.fixes import tournament
from engine.grid import build_grid
from engine.network import from_pandapower
from engine.powerflow import day_inputs
from engine.rules import get_rule
net = from_pandapower(build_grid(1.0), phases="round_robin")
scn = scenarios_from_legacy(day_inputs("2019-05-15"), net)
for rule in ("pm10", "up_2005"):
    r = tournament.run(net, scn, get_rule(rule), include_battery=(rule == "up_2005"))
    print(rule, r.verdict["message"], "|", r.verdict.get("still_needs"))
PY
```

Commit: `feat(fixes): tournament with phase reallocation, export envelopes, switching, battery sweep; honest no-safe-action verdict (D2-D8)`.

**Note for later phases:** the tournament takes 80–115 s for one scenario. The API runs it as a background job (Phase 8) and the dashboard shows the precomputed result; for live "what if" use a smaller candidate set (`include_battery=False, include_switching=False`, about 20 s).

**Phase 6 exit check:** tests green; the two verdict lines printed and saved to `data/results/tournament_headline.json`.


---

# PHASE 7: PLANNING TOOLS (E1–E6)

**Status of the code in Phases 7 to 11:** written as specifications (files, signatures, method, tests to write). Unlike Phases 0 to 6, **this code has not been run**. Each task lists its tests; write them first.

**Deliverable:** answers to the questions a DISCOM planner asks before a connection is approved: how much solar can this transformer take, what happens if the rule changes, can I approve this 5 kW request and on which phase.

**Repo changes:** replaces `engine/hosting_capacity.py` (Round 1: one day, 10% steps, balanced) and `engine/scenarios.py` (five fixed scenarios) in role; both stay until P10.12.

### Task P7.1: Probabilistic hosting capacity (E1)

**Files:** Create `engine/hosting.py`; Test `tests/test_hosting.py`.
**Interface:** `hosting_capacity(network, scn, rule, *, levels=np.linspace(0, 1, 11), kw_tiers=(1, 3, 5), draws=100, seed=42, controls=Controls()) -> dict` with `p10`, `p50`, `p90` (adoption share), `kw_p50` (total installed kW), `by_level` (share of draws unsafe at each level), `binding` (most common binding limit).
**Method:** for each draw: pick which homes have solar (a random subset of the requested share), their size from the tier mix, and their phase (random). For each level run the day over the scenario set; a draw's capacity is the highest level with zero unsafe steps. Because the engine takes a batch, one call evaluates all draws of one level together: homes' `house_kwp` and `house_phase` differ per draw, so build one `Network` per draw and solve in a loop of draws (65 ms each for one scenario; 100 draws × 11 levels × 3 scenarios ≈ 3.6 minutes cold, cached after). Budget: under 120 s with 50 draws and one design scenario.
**Tests:** capacity falls when the rule is tightened (`pm10` ≥ `up_2005`); capacity with Volt/VAR ≥ capacity without; seed makes it reproducible; with 0 draws a clear error.

### Task P7.2: Transformer and phase headroom (E2)

**Files:** Create `engine/headroom.py`; Test `tests/test_headroom.py`.
**Interface:** `headroom(network, scn, rule, *, step_kw=0.5, max_kw=60) -> dict` with `per_phase_kw` (extra export that can be added on each phase at the street's far end and at the transformer before the first violation, P90 scenario), `trafo_kw`, `binding_per_phase`, `flat_caps` (Delhi 20%, Rajasthan 30%, Karnataka 80%, Tamil Nadu 90%, Odisha 75%; research tag [S], shown as "reported, not verified") and `vs_flat_cap` (the physics number as a share of the transformer rating next to each flat cap).
**Method:** add a probe home at a chosen node on one phase, bisect its export until the first unsafe step in the P90 scenario; do it per phase and for two probe locations (nearest and farthest node). Provenance: modeled.
**Tests:** far-end headroom < near-end headroom; adding load on the most loaded phase lowers that phase's headroom first; a weaker conductor gives less headroom.

### Task P7.3: Connection check (E3)

**Files:** Create `engine/connection.py`; Test `tests/test_connection.py`.
**Interface:** `check_connection(network, scn, rule, *, node: int, kw: float, count: int = 1, phase: int | None = None) -> dict` returning `decision` (`approve`, `approve_with_conditions`, `refuse`), `phase` used (best phase if none given), `binding_limit`, `conditions` (for example "export limit 2.5 kW on phase B at midday" from the envelope of P6.3, or "Volt/VAR required"), `margin_v`, `evidence` (before/after unsafe steps).
**Method:** try the request on each phase (or the requested one) without any control; if unsafe, try the cheapest control from the tournament (Volt/VAR, then envelope); if still unsafe, `refuse` with the binding limit and the smaller size that would pass (bisect on kW). Physics decides; no ML in this path.
**10 kW exemption (reported in the research as [S]; verify the exact rule before relying on it):** rooftop systems up to 10 kW are reported to be exempt from a technical feasibility study, so nobody checks their cumulative effect on the transformer. Add `exempt_below_kw: float = 10.0` and `existing: list[dict] | None` (already-connected systems as `{node, phase, kwp}`) to `check_connection`. For a request at or below the threshold the response adds `regulatory_status: "exempt from feasibility study (reported, unverified)"` and still returns the physics decision as `advisory`. A second function `cumulative_check(network, scn, rule, existing, new)` adds all existing plus new systems and reports the combined binding limit and the remaining headroom per phase, because the harm comes from many small exempt systems on one transformer. The response always says whether the request alone is safe and whether the request plus the exempt systems already connected is safe.
**Tests:** a 5 kW request alone is safe but fails `cumulative_check` when enough exempt systems already sit on the same phase; the response carries the `regulatory_status` text; the threshold is a parameter, not a constant buried in code.
**Other tests:** a small request at the transformer is approved; a large request at the far end on the loaded phase is refused with a named limit; a phase suggestion is never worse than the worst phase; response time under 5 s on the benchmark.

### Task P7.4: Meter-first ranking (E4)

**Files:** Create `engine/metering.py`; Test `tests/test_metering.py`.
**Interface:** `rank_nodes(network, scn, rule, controls) -> list[dict]` ordering the nodes by value of putting a smart meter there.
**Method:** score = worst-case voltage-rise sensitivity (probe solve with 1 kW at the node) × number of homes downstream; the top node is where one meter reveals the most. **Tests:** the far end of the longest feeder ranks above a node next to the transformer.

### Task P7.5: Stress lab (E5)

**Files:** Create `engine/stress.py`; Test `tests/test_stress.py`.
**Interface:** `stress(network, scn, rule, *, kwp_per_home=None, upstream_shift_pu=0.0, ev_homes_share=0.0, ev_kw=7.4, ev_hours=(19, 23), heat_load_factor=1.0, rule_id=None) -> dict` (unsafe steps, peak voltage, trafo loading, binding limit vs the unstressed baseline).
**Method:** build a modified `DayScenarioBatch` (extra EV load in the evening hours on a random share of homes, load scaled in a heatwave, upstream shifted) and a modified `Network` (kWp per home) and reuse the solver. **Tests:** raising upstream voltage by 0.02 pu increases unsafe steps; EV charging at night raises the transformer loading and not the midday voltage.

### Task P7.6: R/X sensitivity map for Volt/VAR (E6)

**Files:** Create `engine/rxmap.py`; Test `tests/test_rxmap.py`.
**Interface:** `rx_map(network, scn, rule, *, r_scales=(0.5, 1, 1.5, 2), x_scales=(0.5, 1, 1.5, 2)) -> dict` giving, per (R scale, X scale), the peak voltage with and without standard Volt/VAR and the unsafe steps.
**Why:** reactive-power control works when X is large relative to R; Indian overhead LV has high R, so Volt/VAR may help less than the literature suggests. The map shows where Volt/VAR works on this street and is a Proof-page figure. Reactance is an estimate (provenance), so the map doubles as the sensitivity to that estimate.
**Tests:** at a high R/X ratio Volt/VAR reduces the peak by less than at a low ratio.

### Task P7.7: Which transformers to meter first (E4, across transformers)

**Files:** Create `engine/portfolio.py`; Test `tests/test_portfolio.py`.
**Interface:** `rank_transformers(portfolio: list[dict], rule) -> list[dict]` where each portfolio item is `{id, network, scenarios, connected_kw, metered: bool}`; returns the transformers ordered by risk of unseen overload or over-voltage, each with `score`, `headroom_kw`, `connected_kw`, `share_of_headroom_used`, `binding_limit`, `metered`.
**Method:** run `headroom` (P7.2) per transformer; score = `connected_kw / headroom_kw` (how much of the safe room is already used), boosted when the transformer is unmetered, since there the utility cannot see the problem; ties by lowest headroom. The five archetypes act as a five-transformer demo portfolio; a utility's own list comes in through the onboarding schema (P10.3, add a `transformers.csv`). The flat state caps appear beside the result so a planner sees where a flat cap and the physics disagree.
**Tests:** a small, long, heavily connected transformer ranks above a large, short, lightly connected one; an unmetered transformer outranks an otherwise identical metered one; an empty portfolio is a clear error.

**Phase 7 exit check:** tests green; one `data/results/planning_<archetype>.json` per archetype with headroom and hosting capacity for `pm10` and `up_2005`.

---

# PHASE 8: API V2 (F3, F4, G4)

**Repo changes:** `backend/main.py` keeps its 18 legacy routes and mounts the new router; new package `backend/v2/`; `backend/cache.py` (atomic JSON cache with key validation, already in the repo) is reused for all v2 caching; `backend/schemas.py` stays for legacy, v2 models go in `backend/v2/schemas.py`.

**Principle for the hackathon:** the heavy results are precomputed (Task P8.3) and served from cache in under 300 ms; any cache miss starts a background job and the response says `status: "running"` with a job id. The dashboard never waits on a 100-second computation.

### Task P8.1: Settings, error model, app assembly

**Files:** Create `backend/v2/__init__.py`, `settings.py`, `errors.py`, `app.py`; Modify `backend/main.py` (add `app.include_router(v2_router, prefix="/api/v2")` and the security middleware); Test `tests/test_api_v2_base.py`.
**Content:** `Settings` (pydantic-settings) with the environment variables of section 13; error model `{"error": {"code", "message", "details"}}` with 400/404/409/422/503 and no stack traces; middleware adding `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, a request id header, JSON-line access log (route, status, duration, cache hit); CORS from `GRIDTWIN_CORS_ORIGINS`; request-size limit; in-process rate limit (30 per minute per client) on `/whatif` and `/connection-check`.
**Tests:** unknown id gives 404 with the error model; oversize body gives 413; an exception inside a route returns 500 without a traceback; the rate limit returns 429.

### Task P8.2: Schemas and read-only routes

**Files:** Create `backend/v2/schemas.py`, `routes_core.py`; Test `tests/test_api_v2_core.py`.
**Routes:** `GET /rules` (rule library with source and verification), `GET /networks` (archetypes with provenance), `GET /health`, `GET /readiness` (data, models, cache present), `GET /metrics` (Prometheus text via `prometheus_client`).
**Schema example for `/rules` item:** `{"id": "up_2005", "label": "Uttar Pradesh Supply Code 2005, ±6%", "vmin_v": 216.2, "vmax_v": 243.8, "region": "UP", "source": "...", "verification": "secondary"}`.
**Tests:** every rule appears with a source and a verification status; `/readiness` is 503 when `data/processed/v2` is missing.

### Task P8.3: Risk, fixes and simulate with precompute and jobs

**Files:** Create `backend/v2/jobs.py`, `routes_decision.py`, `scripts/nightly.py`; Test `tests/test_api_v2_decision.py`.
**Routes:** `GET /risk?date&network&rule&fix`, `GET /fixes?date&network&rule`, `GET /simulate?date&network&rule&fix`.
**Cache key:** `sha256(date|network|rule|fix|code_version)`; `code_version` is the git short hash or a constant in `engine/__init__.py` so stale results cannot survive a code change.
**Job store:** an in-memory dict plus a JSON file per finished job, a `ThreadPoolExecutor(max_workers=2)`, states `queued`, `running`, `done`, `failed`; `GET /jobs/{id}` returns status and result.
**Response shape for `/risk`:** `{"date", "network", "rule", "level": "act", "p_unsafe": [96 floats], "expected_unsafe_hours": {"mean", "p10", "p90"}, "first_watch", "first_act", "peak_voltage_v": {"p10","p50","p90"}, "window_risk": {...}, "shares": {...}, "provenance": {"solar": "modeled", "demand": "observed analog days", "voltage": "modeled"}, "calibration": {"raw": [...], "calibrated": [...]}}`.
**Response shape for `/fixes`:** `{"verdict": {...}, "baseline_unsafe_steps", "outcomes": [{"id", "label", "kind", "safe": bool, "unsafe_steps", "cost": {...}, "binding_limit", "rank"}]}`.
**`scripts/nightly.py`:** for every archetype × rule in {pm10, up_2005} × three demo dates (a sunny, a mixed, a cloudy day) run risk and the tournament once and write the cache files; it also writes `data/results/v2/index.json`. This is what the demo serves, and it is the offline mode (`GRIDTWIN_OFFLINE=1` serves only these files).
**Tests:** a precomputed key returns in under 300 ms; a missing key returns `running` with a job id and later `done`; two identical requests share one job.

### Task P8.4: Planning routes

**Files:** Create `backend/v2/routes_planning.py`; Test `tests/test_api_v2_planning.py`.
**Routes:** `GET /headroom?network&rule`, `POST /connection-check` (body `{network, rule, node, kw, count, phase}`; validated: kw in (0, 50], count in 1..50, node must be an LV node), `GET /hosting?network&rule&season`.
**Tests:** invalid node gives 422; a valid request returns a decision and a binding limit or conditions; response time under 5 s.

### Task P8.5: Catalogue and what-if (F4)

**Files:** Create `engine/registry.py`, `backend/v2/routes_whatif.py`; Test `tests/test_registry.py`.
**Idea:** every change, fix, check and output is registered once with an id, a parameter schema and a function, so the API and the UI list them from `GET /catalog` and run them through `POST /whatif` without new endpoints. Registry entries: `change.panel_size`, `change.upstream_shift`, `change.ev_share`, `fix.tap`, `fix.volt_var`, `fix.volt_watt`, `fix.curtail`, `fix.envelope`, `fix.phase_swap`, `fix.battery`, `check.connection`, `output.report`. `@register(id, kind, params)` decorator; params declared as a Pydantic model so validation and the form come from one place.
**Tests:** unknown id 404; invalid parameter 422; same spec twice gives one computation (spec hash).

**Phase 8 exit check:** `pytest tests/test_api*` green including the 55 legacy tests; `GRIDTWIN_OFFLINE=1` serves risk and fixes for every demo date.

---

# PHASE 9: DASHBOARD (F5)

**Repo changes (existing files):** `frontend/src/App.tsx` (five tabs become five areas), `api.ts` (typed v2 client next to the legacy calls), `types.ts`, `plain.ts` (plain-language strings move to `i18n/`), `index.css` (tokens, phone layout). Existing components are reused rather than rewritten: `GridMap.tsx` and `DayCharts.tsx` stay as the voltage map and day chart; `FixesView.tsx` is rewritten around the tournament result; `CapacityView.tsx` becomes the Planning page; `StoryView.tsx` becomes Home; `TwinSim.tsx` becomes Try a change; `ForecastView.tsx` content moves to Proof.

**Tooling added:** `vitest`, `@testing-library/react`, `jsdom` (dev dependencies). No new runtime dependency except none; Hindi strings are a JSON file.

### Task P9.1: Typed v2 client, i18n, layout shell

**Files:** Create `frontend/src/api/v2.ts`, `frontend/src/i18n/{en,hi}.json`, `frontend/src/i18n/index.ts`, `frontend/src/app/Shell.tsx`; Modify `App.tsx`, `main.tsx`, `index.css`, `package.json`, `vite.config.ts`; Test `frontend/src/app/Shell.test.tsx`.
**Content:** `useV2<T>(path)` hook with loading, error and `running` (polls `/jobs/{id}` every 2 s) states; language switch (English, हिन्दी) stored in `localStorage` inside try/catch; phone layout at 360 px with 16 px gutters; skip link and tab keyboard pattern kept from the current code.
**Tests:** switching language changes the tab labels; a `running` response shows the progress state and then the result; no horizontal scroll at 360 px (checked with a CSS assertion).

### Task P9.2: Home: tomorrow's risk

**Files:** Create `frontend/src/pages/Home.tsx`, `components/RiskStrip.tsx`, `components/Verdict.tsx`; Test `Home.test.tsx`.
**Content:** one line answer (example wording only: "Tomorrow: ACT, over-voltage likely between 11:45 and 14:30"), the 96-step probability strip coloured ok/watch/act with the watch (20%) and act (50%) lines, expected unsafe hours with the P10–P90 range, the peak-voltage range against the rule band, the provenance tags (observed/modeled/benchmark), and a rule selector (`pm10`, `up_2005`, other state rules) showing the rule's source and verification status. When the reliability result is not yet calibrated, a visible note says so.
**Tests:** level `act` renders the act wording and the first act time; the rule selector changes the request; provenance tags are present for every number block.

### Task P9.3: Fixes: the ranked tournament and the honest verdict

**Files:** Rewrite `frontend/src/components/FixesView.tsx` as `pages/Fixes.tsx`; Create `components/FixCard.tsx`, `components/Envelope.tsx`, `components/PhasePlan.tsx`; Test `Fixes.test.tsx`.
**Content:** if a safe fix exists, a recommended card with cost lines (curtailed kWh, operations, battery use, margin); if none, the "No safe action" panel with the binding limit in words, the closest option and "what it still needs". Details for the winning fix: per-house export limit table (for envelopes), phase swap list (home, from, to) and a before/after voltage chart. Compare table of all candidates.
**Tests:** `safe_action_found: false` shows the no-safe-action panel and never a "recommended" badge; the phase list shows from and to; the before/after chart receives both series.

### Task P9.4: Try a change (what-if)

**Files:** Rewrite `components/TwinSim.tsx` as `pages/TryChange.tsx`; Create `components/ParamForm.tsx`; Test `TryChange.test.tsx`.
**Content:** the form is generated from `GET /catalog` parameter schemas; submit calls `POST /whatif`; result shows violations before/after, peak voltage and the voltage map (`GridMap.tsx`).
**Tests:** the form renders every parameter of a catalog entry with its bounds; invalid input is blocked before the request.

### Task P9.5: Planning: headroom, hosting capacity, connection check

**Files:** Rewrite `components/CapacityView.tsx` as `pages/Planning.tsx`; Create `components/HeadroomTable.tsx`, `components/ConnectionForm.tsx`; Test `Planning.test.tsx`.
**Content:** headroom per phase and location beside the flat state caps (each cap labelled "reported, not verified"); probabilistic hosting capacity as P10/P50/P90 bars with and without the fix; the connection form (node on the map, kW, count, optional phase) and the decision with its reason.
**Tests:** the three decisions render distinct wording; refusal shows the binding limit and the largest size that passes.

### Task P9.6: Proof: how much to trust it

**Files:** Create `pages/Proof.tsx`, `components/ReliabilityChart.tsx`, `components/GateTable.tsx`; Test `Proof.test.tsx`.
**Content:** reads `results.json` (P10.4): every gate with measured value and pass/fail, the reliability table, solar and demand scores against baselines (including the summer solar result where v2 is slightly worse), the zero-sequence sensitivity range, the list of assumptions with their tags, and the "not built" list.
**Tests:** a failed gate renders as failed, never hidden; every number on the page exists in `results.json` (the honesty test of P10.8).

**Phase 9 exit check:** `npm run build`, `npm run lint`, `npm run test` pass; Lighthouse accessibility ≥ 90 on Home; initial JS ≤ 300 KB gzip with lazy pages.

---

# PHASE 10: EXPLAIN, DELIVER, OPERATE (F1, F2, F6, G1–G6, A6)

### Task P10.1: Grounded explanations (F1)

**Files:** Create `engine/explain.py`; Test `tests/test_explain.py`.
**Interface:** `explain_risk(risk: dict) -> str`, `explain_fix(outcome: dict) -> str`, `explain_verdict(verdict: dict) -> str`; plain English and Hindi templates in `engine/explain_templates/{en,hi}.json`; every number inserted comes from the input dict. Optional `rephrase(text)` through the OmniRoute gateway when `GRIDTWIN_LLM_REPHRASE=1`: after rephrasing, extract all numbers with a regex from before and after and **reject the rephrasing if the sets differ**.
**Tests:** numbers preserved; a rephrase that changes a number is rejected and the original text is used; Hindi output contains the same numbers.

### Task P10.2: Evening report (F2)

**Files:** Create `engine/report.py`, `engine/report_templates/evening.html.j2`; Test `tests/test_report.py`.
**Interface:** `render_report(risk, fixes, headroom, lang) -> str` HTML, print-ready (A4 CSS, no external requests). Sections: tomorrow in one line, hours at risk, the recommended fix with per-house limits or phase swaps, what to do if no fix is safe, assumptions and provenance. `GET /api/v2/report?date&network&rule&lang` serves it. **Privacy:** never prints meter ids. **Tests:** contains the same numbers as the input; no meter id appears; works offline.

### Task P10.3: Onboarding (A6)

**Files:** Create `engine/onboard.py`, `scripts/onboard.py`, `docs/ONBOARDING.md`; Test `tests/test_onboard.py`.
**Schemas:** feeder CSV `node_id, parent_id, length_m, conductor, phase_count`; homes CSV `home_id, node_id, phase, kwp`; transformer row `kva, uk_percent`; meter CSV `timestamp, home_id, kwh, volts`. Validators with line-numbered errors (missing columns, unknown conductor, loops, islanded nodes, phase not in {A,B,C}, negative kWp). `scripts/onboard.py --purge` deletes uploaded files. Uploads limited to 10 MB, parsed with pandas only, never executed, never logged. **Tests:** a valid sample builds a `Network` that passes `is_radial`; each invalid case yields a specific message.

### Task P10.4: Evaluation harness and `results.json` (G1, G2)

**Files:** Create `scripts/evaluate.py`, `docs/generated/` (generated); Test `tests/test_evaluate.py`.
**What it does:** runs the gates G1–G8 and the headline numbers and writes `data/results/results.json` with `{gate, measured, threshold, passed, provenance, command, git_hash, timestamp}`; generates `docs/generated/proof.md` from it. It also ingests every `data/results/bakeoff_*.json` (section 0.8) so the Proof page can show which method won and by how much. All UI and docs numbers come from this file. **Tests:** a failed gate is written as failed; the file validates against a schema.

### Task P10.5: Nightly run

**Files:** Modify `scripts/nightly.py` (P8.3); Create `.github/workflows/nightly.yml` additions. Steps: refresh live solar forecast, regenerate tomorrow's risk and fixes for the demo networks, update `data/monitor/conformal_state.json`, write the evening report, write a `WARN` file on failure.

### Task P10.6: Drift monitor

**Files:** Create `scripts/monitor.py`; Test `tests/test_monitor.py`.
**Content:** compares yesterday's forecast with realised ERA5 PV, updates the rolling 60-day conformal width in `data/monitor/conformal_state.json` (`{"q": ..., "as_of": date}`, read by `ml.live_solar_v2`), and writes `data/monitor/WARN` if coverage over 14 days leaves 70–90% or MAE rises 25% above the model card baseline. **Tests:** synthetic drift triggers the warning.

### Task P10.7: Logging, metrics, security (G4, G5)

**Files:** Modify `backend/v2/app.py`; Create `tests/test_honesty.py`, `tests/test_security.py`.
**Content:** the middleware from P8.1 plus counters (requests, latency histogram, cache hit ratio, solver convergence rate, job queue depth, last nightly timestamp). **Honesty test:** every number in `frontend/src/i18n/*.json` templates and `engine/explain_templates/*` placeholders resolves to a field of `results.json` or an API response; no `[S]` or `[U]` tagged research claim appears in UI strings. **Security tests:** path traversal in cache keys rejected, oversize upload rejected, no stack trace in error bodies, CORS only for allowed origins, secrets pattern absent from the repo.

### Task P10.8: Licence and data register (G5)

**Files:** Create `docs/DATA_SOURCES.md`, `NOTICE`. List CEEW (CC0), Open-Meteo (API terms unchecked: gate G6), ERA5 (Copernicus licence), SimBench (check licence text before release), IS 398 table (public standard, verify), RECON-SL (CC BY 4.0, optional), ppOPF and other repositories as references only. **Gate G6:** read Open-Meteo's terms; if non-commercial use only, say so in the register and in the README, and note that a commercial deployment must use a licensed source.

### Task P10.9: Model cards (documentation)

**Files:** Create `docs/model_cards/{solar_v2,demand_v2,upstream,scenario_generator,engine}.md`. Each: purpose, data, method, measured scores (copied from `results.json`), limitations, failure modes, how it is monitored. The solar card records the Chronos-2 decision and the summer weakness.

### Task P10.10: Container and offline mode (F6)

**Files:** Create `Dockerfile` (multi-stage: node builds the frontend; python:3.12-slim installs `requirements.txt -c constraints.txt`; non-root user; `HEALTHCHECK` on `/api/v2/health`), `docker-compose.yml`, `.dockerignore`. `GRIDTWIN_OFFLINE=1` serves the committed `data/results/v2` files only. **Test:** `docker build` succeeds and `/api/v2/readiness` returns 200 with the bundled results.

### Task P10.11: Runbooks (G6)

**Files:** Create `docs/runbooks/{weather_api_down,stale_model,cache_corruption,solver_failures,data_refresh,release_rollback}.md`. Each: symptom, check, fix, who decides. Rollback is `git checkout v1-baseline` for the code and deleting `data/results/v2` for the cache.

### Task P10.12: Remove the legacy path

**Files:** Delete `engine/actions.py`, `engine/ranking.py`, `engine/hosting_capacity.py`, `engine/scenarios.py`, `engine/simulate.py` and the legacy routes in `backend/main.py` **only after** the dashboard uses v2 everywhere and `grep -rn "api/run\|api/actions\|api/grid" frontend/src backend scripts tests` returns nothing. Update `tests/test_api.py` to the v2 equivalents, update `README.md` and `CHANGELOG.md`. If time is short, skip this task: legacy code left in place is harmless.

---

# PHASE 11: RELEASE

### Task P11.1: Full verification and performance

Run `python scripts/check.py`, `pytest -q`, `pytest -m perf`, `python scripts/evaluate.py`, `npm run build && npm run lint && npm run test`, `docker build .`. Confirm the budgets of section 12 (note the corrections: Volt/VAR day 1.5 to 3 s, tournament 80 to 150 s, both served from precompute).

### Task P11.2: Documentation and demo

**Files:** Update `README.md` (what it is, how to run, results with provenance, limits), `docs/GridTwin_Final_Project_Document.md` (only claims present in `results.json`), `CHANGELOG.md`; Create `docs/DEMO_SCRIPT.md`.
**Five-minute demo:** (1) Home: tomorrow's risk strip for the ±6% UP rule: "ACT with the expected unsafe hours and their range from the latest run"; (2) change the rule to ±10% to show the rule matters; (3) Fixes: for ±6% the honest "No safe action", binding limit and what it still needs; for ±10% the ranked fix with the phase swap and per-house limits; (4) Planning: connection check for a 5 kW request, refused at the far end on the loaded phase, approved on another phase; (5) Proof: reliability table, gates, assumptions, the weak spots we found ourselves.

### Task P11.3: Tag

`git tag v2.0.0` locally. Do not push.
