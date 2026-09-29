# GridTwin — Day-Ahead Voltage and Overload Guard for Solar Streets

**HackMatrix 5.0 · Track: Energy · ENR-02 — Renewable Distribution Grid Digital Twin**

> This is the complete project document for GridTwin. It is the single source for the Round 1 PPT and the video. It describes the full system we are building. The numbers in §9 are measured on our working Round 1 prototype; every other section describes how the complete system works.

---

## Contents

1. [One-page summary](#1-one-page-summary)
2. [The problem](#2-the-problem)
3. [Evidence from real Indian data](#3-evidence-from-real-indian-data)
4. [What exists today and the gap](#4-what-exists-today-and-the-gap)
5. [The GridTwin idea](#5-the-gridtwin-idea)
6. [Architecture](#6-architecture)
7. [Every module: methods and techniques](#7-every-module-methods-and-techniques)
8. [The optimisation problem, formally](#8-the-optimisation-problem-formally)
9. [Results](#9-results)
10. [What makes GridTwin different](#10-what-makes-gridtwin-different)
11. [Problem-statement traceability](#11-problem-statement-traceability)
12. [Data sources](#12-data-sources)
13. [Technology stack](#13-technology-stack)
14. [How GridTwin is evaluated](#14-how-gridtwin-is-evaluated)
15. [Impact, users and SDGs](#15-impact-users-and-sdgs)
16. [Feasibility, scale and adoption](#16-feasibility-scale-and-adoption)
17. [The dashboard](#17-the-dashboard)
18. [Team](#18-team)
19. [Judge questions and answers](#19-judge-questions-and-answers)
20. [Slide-by-slide content for the PPT](#20-slide-by-slide-content-for-the-ppt)
21. [Three-minute video script](#21-three-minute-video-script)
22. [Sources](#22-sources)

---

## 1. One-page summary

| | |
|---|---|
| **Problem** | India is putting rooftop solar on 1 crore homes (PM Surya Ghar). At midday the surplus flows back up the street's wire and **raises** voltage above the 253 V safe limit. Appliances get damaged, inverters trip off, and utilities respond by capping or curtailing solar. |
| **Evidence** | Smart meters in 38 Mathura homes read a typical **245.5 V** against a 230 V nominal, and **27.2%** of readings were already above 253 V — **before any rooftop solar**. |
| **Gap** | Utilities cannot answer: *"If more homes on this street add solar, when will it go unsafe — on voltage or on overload — and what is the cheapest action that keeps it safe all day?"* Commercial planning suites are expensive and not calibrated to Indian low-voltage streets; open-source engines only calculate, they do not forecast or recommend. |
| **GridTwin** | A computer model of a street's low-voltage network, calibrated with real Indian smart-meter data and Indian overhead-wire values, that (1) **forecasts tomorrow** with an AI that knows its own uncertainty, (2) **turns that forecast into a probability of unsafe voltage or overload**, (3) **tests every corrective action** — transformer tap, smart-inverter curves, battery, feeder switching, limited curtailment — over the whole day with physics, (4) **reports how much solar the street can safely host**, and (5) **says "no safe action" honestly** when nothing works. |
| **Headline result (prototype, real day)** | Solar on every home: unsafe time rises from **1 h 15 min to 6 h 30 min**, peak **263 V**. Best fix — transformer one notch lower + smart inverters — brings it to **0 min unsafe with 0 kWh solar wasted**. The common approach (throw away 40% of solar) still leaves **3 h 45 min unsafe** and wastes **489 kWh**. Safe solar capacity rises from **30 kW to 297 kW** with two setting changes. |
| **One line** | *GridTwin tells a utility the evening before which streets will go unsafe tomorrow, how likely it is, and the cheapest verified action that keeps them safe without wasting solar.* |
| **Principle** | **AI predicts, physics decides.** No recommendation is ever made by the ML model alone; every action is replayed through a full AC power flow for all 96 fifteen-minute steps of the day. |

---

## 2. The problem

### 2.1 How a street's electricity works
A distribution transformer on a pole feeds 50–150 homes through overhead wires. Voltage is highest at the transformer and drops along the wire because every wire has resistance. Utilities set the transformer so the last home still gets enough voltage at the evening peak.

### 2.2 What rooftop solar changes
At noon a home with 3 kW of panels may produce 1.5–2 kW while using 0.3 kW. The surplus flows **backwards** up the wire. Pushing current against the wire's resistance **raises** voltage instead of lowering it, and the rise is largest at the far end — exactly where the transformer setting assumed voltage would be lowest. The same reverse current also loads the transformer and the wires, so a street can fail on **voltage** and on **overload** at the same time.

### 2.3 Why it is dangerous
| Who | Harm |
|---|---|
| Households | Sustained over-voltage shortens appliance life and damages electronics; inverters must switch off when grid voltage is too high, so homes lose the solar they paid for on the sunniest days |
| Utilities (DISCOMs) | Complaints, equipment damage, overloaded transformers, and no visibility of low-voltage streets |
| The energy transition | Utilities without visibility respond bluntly — capping or refusing new solar connections, or curtailing output |

### 2.4 Why it is urgent in India
- **PM Surya Ghar** targets rooftop solar on **1 crore homes**, with subsidies of Rs 30,000–78,000 per home for 1–3 kW systems.
- Many of these homes sit on **rural and semi-urban low-voltage feeders** with little or no real-time monitoring.
- Indian low-voltage lines are **long, thin overhead ACSR conductors** with high resistance, which makes them far more voltage-sensitive than the underground cables used in European benchmark grids (§9.4).
- Our data shows many Indian streets **already run near the upper voltage limit before any solar arrives** (§3).

### 2.5 The question GridTwin answers
> *"If more homes on this street add solar, when and where will it go unsafe — on voltage or on overload — how likely is that tomorrow, and what is the cheapest safe fix?"*

---

## 3. Evidence from real Indian data

**Source:** CEEW high-frequency smart-meter data, Mathura (Uttar Pradesh), May–December 2019, one reading every 3 minutes per home, **3.31 million valid voltage readings** (CC0, Harvard Dataverse).

| Measured at 38 real homes, 2019 | Value |
|---|---|
| Median voltage (nominal 230 V) | **245.5 V** |
| Readings above 243.8 V (230 V + 6%) | **54.9%** |
| Readings above 253 V (230 V + 10%) | **27.2%** |
| Readings below 207 V (230 V − 10%) | 6.1% |
| Average household use, by hour | 0.29–0.61 kW |

**What this means.** The street is already too high a quarter of the time and too low some of the time, before any rooftop solar. Every kilowatt exported at midday pushes the high side further. The voltage headroom that European planning rules assume simply does not exist on these streets.

**Voltage rules are not uniform in India.** A 2021 Central Electricity Authority (CEA) panel favoured 230 V ±10%, to be tightened to ±6% later; Maharashtra's regulator allows +10% / −15%. GridTwin treats the band as a **parameter**: ±10% by default, and it tests the stricter ±6% rule.

---

## 4. What exists today and the gap

### 4.1 How utilities handle it today
| Approach | Problem |
|---|---|
| Wait for complaints | Damage and lost solar happen first; low-voltage feeders are rarely monitored |
| Cap or refuse new solar connections | Slows the energy transition and the PM Surya Ghar target |
| Curtail solar (limit export) | Wastes clean energy and, in our test, does not even make the street safe (3 h 45 min still unsafe) |
| Upgrade wires and transformers | Expensive and slow; often unnecessary when existing settings can solve it |
| Dashboards that only show readings | Show the problem after it happens; do not test fixes or predict tomorrow |

### 4.2 Tools that exist
| Category | Examples | What they do | What they do not do for this problem |
|---|---|---|---|
| Open-source power-flow engines | pandapower, OpenDSS, GridLAB-D, PowerModelsDistribution.jl | Calculate voltages and currents accurately | No forecasting, no ranked recommendations, no Indian calibration — they are calculators, not decision tools |
| Commercial planning suites | DIgSILENT PowerFactory, ETAP, CYME, Synergi Electric | Full network studies, hosting-capacity modules | Expensive licences; not pre-calibrated for Indian overhead low-voltage streets; built for engineers |
| Utility ADMS / DERMS platforms | Siemens, Schneider Electric, GE Vernova, Hitachi Energy | Real-time control rooms for large utilities | Need full SCADA/telemetry that Indian rural low-voltage streets do not have |
| Inverter standard models | EPRI OpenDER (IEEE 1547-2018) | Accurate smart-inverter behaviour | A component, not a system |

### 4.3 The gap GridTwin fills
No free, open tool we found combines, for an **Indian low-voltage street**: real-data calibration, a **day-ahead forecast with honest uncertainty**, a **risk probability** of unsafe voltage and overload, a **whole-day, physics-verified fix tournament** that includes the actions named in the problem statement, **hosting capacity**, and an **explicit "no safe action" verdict**.

---

## 5. The GridTwin idea

### 5.1 Five questions instead of one
| Question | GridTwin output | Example (prototype, 15 May) |
|---|---|---|
| Where and when is the street unsafe? | Voltage and loading at every point, every 15 minutes | 6 h 30 min unsafe with solar on every home |
| How much of it is solar's fault? | Replay with and without solar | 5 h 15 min caused by solar; 1 h 15 min happens anyway |
| What is the cheapest fix that is safe all day? | Ranked, physics-verified actions | Tap one notch lower + smart inverters: 0 min unsafe, 0 kWh wasted |
| How likely is tomorrow to be unsafe? | Day-ahead forecast → risk probability | Predicted 6 h 45 min unsafe; reference replay 7 h |
| How much solar can this street take? | Hosting capacity, with and without fixes | 30 kW without a fix → 297 kW with the fix |

### 5.2 Design principles
| Principle | What it means in the system |
|---|---|
| **Real data first** | Indian household use and voltage from smart meters, real weather, Indian overhead-conductor values |
| **AI predicts, physics decides** | ML forecasts the uncertain future; a full AC power flow checks every warning and every fix |
| **Safe all day, on every limit** | A fix counts only if all 96 steps are within voltage limits **and** no wire or transformer is overloaded |
| **Uncertainty is part of the answer** | Forecasts are ranges (P10/P50/P90), and the risk is reported as a probability, not a single guess |
| **Honest verdicts** | When nothing works, GridTwin says **"no safe action"**, names the binding limit and the closest option |
| **Plain language** | Hours not steps, volts not per-unit, fixes named for what they do; every recommendation comes with a one-paragraph explanation |

### 5.3 Where GridTwin sits
GridTwin is a **day-ahead planning and decision-support system**. It runs every evening for tomorrow and on demand for "what if" questions (new connections, stricter rules, bigger panels). It does not need real-time SCADA, which Indian rural low-voltage streets do not have — it needs a feeder map, periodic smart-meter reads and a weather forecast.

---

## 6. Architecture

```
 ┌─────────────────────────── DATA LAYER ───────────────────────────┐
 │ Smart meters (CEEW / DISCOM AMI)   Weather forecast + reanalysis │
 │ Feeder map (GIS / benchmark)       Indian conductor + tap data   │
 └──────────────────────────────┬────────────────────────────────────┘
                                ▼
            [1] Data quality + calibration
                (outage filter, 15-min profiles, upstream voltage,
                 Indian overhead-wire override, per-phase allocation)
                                │
          ┌─────────────────────┴─────────────────────┐
          ▼                                           ▼
 [2] Solar forecast (LightGBM quantile)     [3] Demand forecast (LightGBM quantile)
     P10 / P50 / P90, calibrated                P10 / P50 / P90, calibrated
          └─────────────────────┬─────────────────────┘
                                ▼
            [4] Scenario generator
                forecast samples × solar adoption × band × stress cases
                                │
                                ▼
            [5] PHYSICS ENGINE — AC power flow, 96 steps/day
                balanced (fast) and three-phase unbalanced (per-phase)
                                │
                                ▼
            [6] Violation engine
                over/under-voltage · line overload · transformer overload
                · reverse power flow · solar attribution (with vs without)
                                │
                ┌───────────────┼──────────────────────┐
                ▼               ▼                      ▼
 [7] Risk engine        [8] Corrective-action      [9] Hosting-capacity
  P(unsafe) per step,       tournament               sweep 0–100%+ adoption,
  expected unsafe hours     tap · Volt/VAR ·         with and without fixes
                            Volt/Watt · battery ·
                            switching · curtailment
                            ML shortcut pre-screens,
                            physics verifies
                                │
                     safe all day? ── no ──► NO SAFE ACTION
                                │             + binding limit
                               yes            + closest option
                                ▼
            [10] Ranked plan + plain-language explanation
                                │
                                ▼
            [11] Delivery: dashboard · API · evening report · connection check
```

**Chain of value:** real data → forecast with uncertainty → risk probability → verified action → safe solar capacity → decision.

---

## 7. Every module: methods and techniques

### [1] Data quality and calibration
| Step | Method |
|---|---|
| Demand | CEEW 3-minute kWh × 20 = kW, averaged to 15 minutes |
| Outages | Readings with voltage outside 150–300 V are treated as outages (missing), never as zero demand |
| Meter selection | Meters with ≥70% coverage kept (32 of 38); a simulated day uses meters with a complete day (26 on 15 May 2019) |
| Home assignment | 26 real profiles assigned across 99 homes (seeded random assignment), so every home carries a real Indian load shape |
| Upstream voltage | Median customer voltage across meters at each 15-minute step, applied at the supply side of the transformer. Customer meters sit downstream, so this **understates** over-voltage — our numbers are conservative |
| Indian overhead wire | Benchmark underground cables replaced with **ACSR Rabbit, R = 0.5524 Ω/km (IS 398)**, X = 0.35 Ω/km |
| Phase allocation | Each single-phase home and its rooftop system is assigned to phase A, B or C, matching how Indian homes under 10 kW are actually connected |
| Utility onboarding | A utility's own GIS feeder map and AMI reads replace the benchmark street and the CEEW profiles through the same pipeline |

### [2] Solar forecast
| Item | Definition |
|---|---|
| Model | LightGBM quantile regression, three models for P10, P50, P90 |
| Inputs | Weather forecast **issued the day before** (Open-Meteo Previous Runs): irradiance, cloud cover, temperature; clear-sky irradiance; a physics-based PVWatts estimate from the forecast; hour; day of year |
| Target | kW per installed kW, from pvlib PVWatts on ERA5 reanalysis — an independent source, not the forecast provider |
| Solar physics | pvlib PVWatts, panels tilted 25° facing south, SAPM cell temperature, −0.4%/°C, 14% system losses; average 3.85 kWh per kW per day |
| Splits | Train Jan–Oct 2024 · calibrate Nov–Dec 2024 · test all of 2025 (never seen) |
| Calibration | The P10–P90 interval is scaled on held-out data to ≈80% coverage; quantiles are sorted to prevent crossing |
| Explainability | LightGBM gain and held-out permutation importance: the forecast-based PVWatts estimate carries ~61% of gain, clear-sky irradiance ~14%, day of year ~11% |

**A data check that mattered.** Open-Meteo's historical-forecast and archive services return identical values from 2021 onward, so a model trained on them would look perfect and predict nothing. GridTwin uses genuine forecasts issued the day before, scored against independent ERA5 data.

### [3] Demand forecast
| Item | Definition |
|---|---|
| Model | LightGBM quantile regression, P10/P50/P90 |
| Inputs | Ratio of yesterday to last week, time of day, weekday, temperature change — only information available the evening before |
| Key idea | Predicting the **ratio to yesterday** instead of raw kW lets a model trained on summer work in winter, when homes use about three times less |
| Splits | Train May–Sep 2019 · calibrate Oct 2019 · test Nov–Dec 2019 |

### [4] Scenario generator
Builds the set of days the physics engine replays:
- **Forecast samples:** P10, P50, P90 and intermediate samples drawn from the calibrated quantiles, for solar and demand jointly.
- **Adoption:** 0%, 30%, 60%, 100% of homes with solar, and 10%-step sweeps for hosting capacity.
- **Panel tiers:** 1, 2, 3 kW (PM Surya Ghar subsidy tiers) and 5 kW (larger unsubsidised systems).
- **Rules:** ±10% band (default), strict ±6%, and state variants such as +10% / −15%.
- **Stress cases:** high upstream voltage (1.05 pu, the CEEW-typical level), all panels at full output together, and a cloudy high-ramp day.

### [5] Physics engine
| Item | Definition |
|---|---|
| Solver | AC power flow (Newton–Raphson) with pandapower |
| Street | SimBench `1-LV-rural2--0-sw`: 97 buses, 99 homes, 95 wire sections, 250 kVA 20/0.4 kV transformer, re-parameterised with Indian overhead wire |
| Balanced mode | One solve ≈ 0.03 s; a whole day (96 solves) in seconds — used for sweeps and tournaments |
| Three-phase mode | Unbalanced power flow (`runpp_3ph`) with per-phase homes and panels and an explicit neutral, because single-phase rooftop solar on a three-phase four-wire 230/415 V street concentrates on one phase. It confirms per-phase voltage and every hosting-capacity figure before it is reported |
| Transformer taps | ±2 steps of 2.5%, off-load, one setting per season (how Indian distribution transformers are actually operated). The tap changer type is set explicitly so tap changes take effect in the solver |

### [6] Violation engine
At every 15-minute step, a step is **unsafe** if any of these holds:

| Check | Limit |
|---|---|
| Over-voltage at any bus | > 253 V (±10%) or > 243.8 V (±6%) |
| Under-voltage at any bus | < 207 V (±10%) or < 216.2 V (±6%) |
| Line overload | Loading > 100% of conductor rating |
| Transformer overload | Loading > 100% of 250 kVA |
| Solver non-convergence | Treated as unsafe, never as safe |

It also records **reverse power flow** at the transformer (solar exporting into the upstream network) and runs the same day **without solar**, so the difference is exactly the unsafe time solar causes.

### [7] Risk engine — from forecast uncertainty to a probability
Point forecasts hide risk. GridTwin runs the scenario samples from [4] through the physics engine and reports:
- **P(unsafe) for every 15-minute step** — the share of forecast samples in which that step violates any limit.
- **Expected unsafe hours** tomorrow, and the **P10–P90 range** of unsafe hours.
- **Warning start time, peak voltage and peak loading** with their ranges.
- A **warning level** for the utility: *watch* when P(unsafe) ≥ 20% in any step, *act* when ≥ 50%.

Fix selection is done at the **P90** (high-solar) case, so a recommended setting stays safe on a sunnier-than-expected day — a robust choice in the spirit of chance-constrained optimal power flow (Bienstock et al. 2014; Lubin et al. 2017).

### [8] Corrective-action tournament
Every action is applied at every step of the day and the whole day is replayed.

| Action | What changes in the model | Real-world meaning |
|---|---|---|
| **Transformer tap one or two notches lower** | Output voltage −2.5% per notch, one setting for the day | An engineer changes the off-load tap once for the season |
| **Smart inverters — Volt/VAR** | Inverters absorb reactive power along the IEEE 1547-2018 Category B volt-var curve (EPRI OpenDER model) | A setting on inverters homes already own; no solar lost |
| **Smart inverters — Volt/Watt** | Inverters trim active power only when local voltage exceeds the curve's threshold | Loses a little solar only at the worst moments, at the worst homes |
| **Tap + smart inverters** | Both together | Two cheap settings |
| **Neighbourhood battery** | Volt-droop control: charges in proportion to how far the worst point is above target, discharges in the evening only when there is headroom; **size chosen by a sweep** (25–150 kW, 2–4 h) for the smallest battery that clears the day | A community battery at the worst-affected point |
| **Feeder reconfiguration** | Open/close the street's switches (SimBench provides 192) to move homes to a different path or split the feeder, keeping the network radial; candidate switchings found by a greedy search | "Changing feeder connections" — a no-cost operational action |
| **Limited curtailment** | Each panel may export only 80% or 60% of what it produces | What many utilities do today; kept as the last resort |

**ML shortcut.** A graph neural network, trained on hundreds of thousands of our own power-flow runs, predicts every bus voltage and loading in milliseconds. It **pre-screens** hundreds of action combinations (tap × inverter curve × battery size × switching) and passes the most promising ones to the physics engine. The ML shortcut never approves an action — **every recommended action is re-verified by the full AC power flow for all 96 steps**.

**Ranking (lexicographic, not a weighted sum):**
1. **Safe all day** on voltage **and** loading, with the solver converged at every step — otherwise rejected.
2. Then **least solar thrown away** (the problem statement's "maximise renewable use").
3. Then **fewest switching operations** (operational realism).
4. Then **least battery energy used**, then **least wire losses**.

**No safe action.** If no action passes rule 1, GridTwin reports **"no safe action"**, names the **binding limit** (voltage or loading, and where), and names the closest option and what it would still need (for example, "curtail a further 20%" or "a larger transformer").

### [9] Hosting capacity
GridTwin sweeps solar adoption from 0% upward in 10% steps (and panel size across tiers) and reports the **highest adoption that stays safe**:
- **Without a new fix:** no more unsafe time than the street already has with no solar.
- **With the recommended fix:** zero unsafe steps all day.

The sweep reuses the same engine, runs on forecast days and stress days, and is confirmed in three-phase mode before a figure is reported. This is the number a utility needs to approve new rooftop connections.

### [10] Explanation
Every recommendation carries a short explanation generated **from the verified power-flow numbers only**:
> *"Tomorrow, 99 homes will export about 145 kW at 11:00 while using little. The far end of the street will go above 253 V from about 06:15 to 13:00, peaking at 263 V; the transformer stays below 45% loading. Moving the transformer one notch lower and switching inverters to Volt/VAR brings the peak to 250 V without wasting any solar. Two notches would fix noon but drop evening voltage to 206 V, so it is rejected."*

A language model can rephrase this for residents or officials, but it is only given the verified numbers and cannot change them.

### [11] Delivery
- **Dashboard** for engineers and officials (§17).
- **API** for utility systems.
- **Evening report**: tomorrow's at-risk streets, probability, recommended setting change.
- **Connection check**: before approving a new rooftop system, check the street's remaining hosting capacity.
- **Deployment**: a single web service (FastAPI serving the dashboard) with a public link; streets run in parallel on ordinary cloud machines.

---

## 8. The optimisation problem, formally

**Sets.** Buses $\mathcal{B}$, lines $\mathcal{L}$, 96 time steps $\mathcal{T}$, homes with solar $\mathcal{G}$, switchable branches $\mathcal{S}$, tap positions $\mathcal{K}=\{-2,\dots,2\}$.

**Decisions.** Tap position $k$ (one per season), inverter reactive power $Q^{inv}_{i,t}$ and active-power trim $P^{curt}_{i,t}\ge 0$, battery power $P^{b}_{t}$ with state of charge $SOC_t$, switch states $x_{s}\in\{0,1\}$.

**Physics (AC power flow at every step):**
$$P_{i,t}=\sum_j V_{i,t}V_{j,t}\left(G_{ij}\cos\theta_{ij,t}+B_{ij}\sin\theta_{ij,t}\right),\qquad Q_{i,t}=\sum_j V_{i,t}V_{j,t}\left(G_{ij}\sin\theta_{ij,t}-B_{ij}\cos\theta_{ij,t}\right)$$
with $P_{i,t}=P^{pv}_{i,t}-P^{curt}_{i,t}-P^{load}_{i,t}+P^{b}_{i,t}$ and $Q_{i,t}=Q^{inv}_{i,t}-Q^{load}_{i,t}$.

**Hard limits (all $i,t$):**
$$V^{min}\le V_{i,t}\le V^{max},\quad |S_{\ell,t}|\le S_\ell^{max},\quad |S_{trafo,t}|\le 250\text{ kVA},\quad SOC^{min}\le SOC_t\le SOC^{max},$$
$$|Q^{inv}_{i,t}|\le\sqrt{(S^{inv}_i)^2-(P^{pv}_{i,t})^2},\quad \text{network radial for every switch state.}$$

**Objective (lexicographic):** (1) all hard limits satisfied for every $t$; then (2) minimise $\sum P^{curt}_{i,t}$; then (3) minimise switching operations; then (4) minimise battery throughput and losses.

**Problem class.** With integer taps and binary switches this is a **mixed-integer non-convex AC optimal power flow**. GridTwin solves it as a **tournament over an enumerable action set, each candidate verified by the exact AC power flow**, with the ML shortcut pruning the combinations. Every accepted answer is feasible by construction, because the same physics that detects violations checks the fix.

**Under uncertainty.** Forecast solar $P^{pv}$ is replaced by its P90 value for fix selection (robust), and by samples of the calibrated distribution for the risk probability (chance-constrained view).

---

## 9. Results

All results in this section are measured on our Round 1 prototype, on a real day (15 May 2019): real Mathura demand and voltage, real weather, the 99-home street with Indian overhead wire, safe band 207–253 V.

### 9.1 How solar changes the street
| Homes with 3 kW rooftop solar | Unsafe time per day | Caused by solar | Highest voltage |
|---|---|---|---|
| None | 1 h 15 min | 0 | 256 V |
| 3 in 10 | 3 h | 1 h 45 min | 256 V |
| 6 in 10 | 4 h | 2 h 45 min | 259 V |
| **Every home** | **6 h 30 min** | **5 h 15 min** | **263 V** |
| Every home, strict ±6% rule | 11 h 45 min | 1 h | 263 V |

On this real day the transformer peaks at **44.5%** loading and lines stay below **28%**, so the binding limit is voltage.

### 9.2 Fixes tested on the every-home day (6 h 30 min unsafe without a fix)
| Rank | Fix | Unsafe time left | Voltage range after | Solar thrown away |
|---|---|---|---|---|
| **1** | **Transformer one notch lower + smart inverters** | **0 min** | **212–250 V** | **0 kWh** |
| ✕ | Transformer two notches lower | 45 min (evenings too low) | 206–251 V | 0 kWh |
| ✕ | Transformer one notch lower | 2 h | 212–257 V | 0 kWh |
| ✕ | Smart inverters only | 2 h 45 min | 217–256 V | 0 kWh |
| ✕ | Throw away 40% of solar | 3 h 45 min | 217–258 V | 489 kWh |
| ✕ | Neighbourhood battery 50 kW / 200 kWh | 5 h | 217–263 V | 0 kWh (161 kWh battery use) |
| ✕ | Throw away 20% of solar | 5 h 30 min | 217–261 V | 245 kWh |

**What the winning fix does at 11:00:** the transformer is one notch lower and the inverters absorb **70 kvar**; all **145 kW** of solar is used; the highest voltage falls from **263 V to 250 V**.

**The trap the all-day rule catches:** two notches lower fixes noon but pushes evening voltage to **206 V**, below the 207 V limit. A noon-only check would have recommended it.

**Honest verdict:** under the strict ±6% rule **no fix is enough** — the closest option still leaves **8 h 30 min** unsafe, and GridTwin says so.

### 9.3 Hosting capacity (same real day, 10% steps, 3 kW per home)
| Rule | Safe solar capacity |
|---|---|
| Without a new fix (no more unsafe time than with no solar) | **30 kW** — 10 of 99 homes |
| With tap one notch lower + smart inverters (zero unsafe steps) | **297 kW** — all 99 homes |

Two cheap setting changes raise the street's safe solar capacity **about ten-fold**.

### 9.4 Stress study — what happens beyond a normal day
We pushed the same street harder to find where cheap settings stop being enough. Setup: every home with solar, all panels at full output together, upstream voltage at **1.05 pu** (the CEEW-typical high level), Indian overhead wire.

**The Indian wire alone matters.** Swapping the benchmark's underground cable for ACSR Rabbit, with no solar at all, drops far-end voltage from **230.0 V to 212.9 V** under the benchmark's own load. The benchmark cable shows no problem at any solar level; the Indian wire is what makes the street behave like an Indian street.

**3 kW per home, full output, high upstream voltage:**
| Action | Highest voltage | Transformer loading | Result |
|---|---|---|---|
| No fix | 274.3 V | 148% | Unsafe on voltage and loading |
| Tap only | 263.9 V | 155% | Unsafe |
| Smart inverters only | 259.5 V | 164% | Unsafe; reactive current adds loading |
| Tap + smart inverters | **248.4 V** | **172%** | Voltage fixed, **transformer overloaded** |
| Curtail 40% | 265.2 V | 107% | Unsafe on voltage |

**5 kW per home — genuine "no safe action":**
| Action | Highest voltage | Transformer loading |
|---|---|---|
| Smart inverters only | 263.0 V | 248% |
| Tap + smart inverters | 251.5 V (voltage-safe) | **261%** |
| Curtail 40% | 274.3 V | 148% |

No combination of settings clears both limits. GridTwin reports **no safe action — binding limit: transformer loading**, and names the options that remain: deeper curtailment together with tap + inverters, a battery sized for the midday surplus, or a larger transformer.

**What the stress study proves:**
1. **Voltage-only tools are dangerous.** A fix that clears voltage can overload the transformer (172%); a voltage-only check would call it safe. GridTwin checks voltage **and** loading on every step.
2. **Smart inverters trade voltage for current.** Absorbing reactive power lowers voltage but raises loading — the ranking must see both.
3. **Upstream voltage matters as much as solar.** Moving upstream voltage from 1.00 to 1.05 pu adds about 10 V at the far end at the same solar level.
4. **Stress-case hosting capacity** (voltage only, full output): **40–50% adoption without control, about 100% with Volt/VAR** — the same ten-fold message as the real day.

### 9.5 AI forecasts (tested on data the models never saw)
| | Solar, 2025 | Household demand, Nov–Dec 2019 |
|---|---|---|
| Better than "same as yesterday" | **13%** | **5%** |
| Mean error | 0.040 kW per installed kW | 0.039 kW |
| Real values inside the predicted range (aim 80%) | **82%** | **82%** |

**Day-ahead warning, 15 May 2025, solar on every home:**
| | Predicted a day ahead | Reference replay (ERA5 solar) |
|---|---|---|
| Unsafe time | **6 h 45 min** | **7 h** |
| First unsafe step | 06:30 | 06:15 |
| Peak voltage | 266 V | 266 V |
| Street solar at 11:00 | 175 kW | 177 kW |

The warning uses the day-ahead solar forecast; demand and upstream voltage use the same calendar day from 2019, the latest public smart-meter data.

### 9.6 Engineering quality
- **Automated tests** on every change (engine, violations, taps, scenarios, fixes, hosting capacity, API contracts and input validation, simulators, ML leakage guards), run by GitHub Actions on every pull request.
- **Leakage controls:** chronological disjoint splits; only information available the evening before; independent truth (ERA5).
- **Reproducible from a fresh clone** with public data: download → build profiles → train → precompute → test.

---

## 10. What makes GridTwin different

| Innovation | Why it matters |
|---|---|
| **Calibrated to real Indian conditions** — real smart-meter voltage upstream, Indian overhead-wire resistance | Generic benchmark grids show no problem with Indian loads; calibration reveals the real one (230 V → 212.9 V from the wire alone) |
| **Voltage and overload judged together** | Catches fixes that clear voltage but overload the transformer — the failure mode voltage-only tools miss |
| **Forecast uncertainty → risk probability** | The utility sees *how likely* tomorrow is to be unsafe, not a single guess; fixes are chosen to be safe on a sunnier-than-expected day |
| **Solar attribution** | Separates "the grid was already bad" (1 h 15 min) from "solar made it worse" (5 h 15 min) — what a utility needs for connection decisions |
| **Whole-day fix tournament with the PS actions** | Tap, standards-based smart-inverter curves, sized battery, feeder switching and limited curtailment, each replayed over all 96 steps |
| **Hosting capacity as a first-class output** | 30 kW → 297 kW with two settings — directly usable for approving new rooftop connections |
| **Honest "no safe action"** | Names the binding limit and the closest option instead of silently picking the least-bad fix |
| **AI predicts, physics decides** | The ML shortcut and the forecasts speed things up; the AC power flow has the final word on every action |
| **Honest AI** | Genuine day-ahead forecasts, independent truth, calibrated ranges; we found and avoided a data trap that would have faked a perfect forecast |
| **Plain language** | Explanations built from verified numbers; usable by scheme officials and residents, not only engineers |

---

## 11. Problem-statement traceability

| ENR-02 asks for | GridTwin delivers |
|---|---|
| A network model connected to time-based solar and load data | 99-home street with Indian overhead wire; real 15-minute CEEW demand and voltage; pvlib solar from real weather (§7 [1], [5]) |
| Predict near-term generation and demand | LightGBM quantile forecasts of solar and demand for tomorrow with calibrated P10–P90 ranges (§7 [2], [3]) |
| Power-flow calculations that detect voltage, overheating or overloading problems | AC power flow at 96 steps/day; over/under-voltage, line overload, transformer overload, reverse power flow; balanced and three-phase (§7 [5], [6]) |
| Suggest corrective actions: changing feeder connections, battery use, limited reduction in renewable output | Feeder reconfiguration, sized community battery, limited curtailment — plus transformer tap and smart-inverter curves (§7 [8]) |
| Keep the network safe while maximising renewable use | Lexicographic ranking: safe all day first, then least solar wasted (§8) |
| Compare at least a few corrective actions against network limits | Every action replayed over the full day and ranked; seven in the prototype table (§9.2) |
| Clear before/after demonstration across multiple scenarios | Five adoption scenarios, strict rule, stress cases; side-by-side simulators (§9, §17) |
| Honest report of a scenario where the action fails or is infeasible | Strict ±6% rule: no fix enough (8 h 30 min left); 5 kW stress case: no safe action, binding limit transformer loading (§9.2, §9.4) |

---

## 12. Data sources

| Input | Source | How GridTwin uses it | Type |
|---|---|---|---|
| Household electricity use | CEEW smart meters, Mathura, 2019–2021, every 3 minutes (CC0, Harvard Dataverse) | 15-minute demand for every home | Observed |
| Voltage arriving at the street | Same meters, median across homes | Upstream voltage at each 15-minute step | Observed |
| Weather | Open-Meteo archive for Mathura: irradiance, temperature, wind, cloud | Drives the solar model | Observed (reanalysis) |
| Day-ahead forecasts | Open-Meteo Previous Runs API, forecasts issued the day before, 2024–2025 | Inputs to the solar AI | Observed forecasts |
| Truth for the solar AI | ERA5 reanalysis, 2024–2025 | What the AI is scored against | Observed (reanalysis) |
| Street layout | SimBench `1-LV-rural2--0-sw` | The street in the model; replaced by a utility's GIS map in deployment | Benchmark |
| Indian overhead wire | ACSR Rabbit, R = 0.5524 Ω/km (IS 398); DISCOM conductor schedules | Replaces the benchmark's underground cables | Indian standard |
| Rooftop solar size | PM Surya Ghar subsidy tiers of 1, 2 and 3 kW | Panel sizes in scenarios | Policy |
| Voltage limits | CEA declared-supply-voltage minutes; state regulators | Safe bands ±10%, ±6%, state variants | Regulation |
| Smart-inverter behaviour | IEEE 1547-2018 via EPRI OpenDER | Volt/VAR and Volt/Watt curves | Standard |

Every number in the dashboard carries its type — observed, modeled or benchmark.

---

## 13. Technology stack

| Layer | Technology | Role |
|---|---|---|
| Power-system physics | pandapower 3.5.5 (balanced and three-phase AC power flow), SimBench 1.6.3 | Street model; voltage and loading at every point |
| Smart inverters | EPRI OpenDER (IEEE 1547-2018) | Standards-based Volt/VAR and Volt/Watt |
| Solar physics | pvlib 0.16.1 (PVWatts, sun position, clear-sky) | Solar output from weather |
| Machine learning | LightGBM 4.7.0 quantile regression, scikit-learn, pandas | Solar and demand forecasts with calibrated ranges; feature importance |
| ML shortcut | Graph neural network (PyTorch Geometric) trained on power-flow runs | Millisecond pre-screening of action combinations |
| Backend | Python 3.11, FastAPI | Scenarios, fixes, risk, hosting capacity, simulators, forecasts |
| Frontend | React 19, TypeScript, Vite, Recharts, SVG street map | Story, live map, fix simulator, forecast and risk, hosting capacity |
| Quality | pytest, GitHub Actions CI, pull-request workflow, automatic feature tracker | Every change tested before merge |
| Deployment | Single FastAPI service serving the built dashboard; cloud batch for many streets | Public link; parallel streets |
| Data | CEEW, Open-Meteo, ERA5, SimBench — all public and free | — |

---

## 14. How GridTwin is evaluated

| Layer | Metric | How |
|---|---|---|
| Physics | Max/min voltage, unsafe duration, max line and transformer loading, convergence rate | Direct from the power flow, every step |
| Attribution | Unsafe time with vs without solar | Paired replay of the same day |
| Actions | Unsafe time left, solar wasted (kWh), switching count, battery throughput, losses | Before/after over the full day |
| Forecasts | MAE, skill vs "same as yesterday", P10–P90 coverage | Held-out test periods never used in training or calibration |
| Warning | Unsafe-duration error, warning-start error, peak-voltage error, unsafe-day precision and recall | Multi-day evaluation over 2025, including cloudy and high-ramp days chosen before seeing the outcome |
| Risk | Reliability of P(unsafe): of steps given 30%, about 30% should be unsafe | Calibration curve on held-out days |
| ML shortcut | Voltage error (V), loading error (%), and — decisive — whether its top candidates contain the physics-verified best action | Held-out scenarios; the physics engine is the referee |
| Robustness | Results under ±10% conductor resistance, forecast error, high upstream voltage, full-output stress | Sensitivity sweeps (§9.4) |
| Three-phase | Per-phase voltage vs balanced result; hosting capacity balanced vs unbalanced | Same scenarios in both modes |

**Baselines compared:** no solar; solar with no fix; curtailment 20/40%; tap only; inverters only; battery only; and GridTwin's recommended action.

---

## 15. Impact, users and SDGs

| Who | What they lose today | What GridTwin gives them |
|---|---|---|
| Households | Damaged appliances; inverters that switch off at midday, losing solar they paid for | A street kept within 207–253 V all day, with their solar used |
| Distribution utilities (DISCOMs) | No view of low-voltage streets; complaints; overloaded transformers; blunt caps on new solar | Street-level foresight a day ahead, a risk probability, a ranked verified action, and hosting capacity for connection approvals |
| Government schemes (PM Surya Ghar) | Rooftop solar that cannot be exported safely undermines the scheme | More solar per street without new wires, using settings the grid already has |
| Environment | Curtailed solar is replaced by fossil power | Best fix wastes **0 kWh**; the common alternative wastes **489 kWh** on one street in one day |

**Scale on one 99-home street, one sunny day:** solar on every home produces about **1,223 kWh**; without a fix the street is unsafe for **6 h 30 min**; throwing away 40% of solar still leaves **3 h 45 min** unsafe and wastes **489 kWh**.

**UN Sustainable Development Goals**
- **SDG 7 — Affordable and clean energy:** more rooftop solar connected and used instead of curtailed.
- **SDG 13 — Climate action:** every kWh of solar kept replaces grid power that is still largely coal-based.
- **SDG 11 — Sustainable cities and communities:** safer, more reliable electricity for homes.
- **SDG 9 — Industry, innovation and infrastructure:** smarter use of existing grid assets instead of costly rebuilds.

---

## 16. Feasibility, scale and adoption

**Speed.** One balanced power-flow solve takes about 0.03 s; a full day is 96 solves; the complete tournament for a street runs in about a minute on a laptop, and the ML shortcut cuts the number of full replays needed. Results are cached, so the dashboard answers instantly.

**Scale.** Streets are electrically independent, so thousands run in parallel on ordinary cloud machines overnight. No GPU is needed for the physics; the ML shortcut trains once per feeder type.

**What a utility needs.** A feeder map (GIS), periodic smart-meter reads (not real-time SCADA), transformer tap data, and a weather forecast — all things Indian DISCOMs already have or are rolling out with smart metering.

**Adoption path**
1. **Pilot** on a handful of feeders with high rooftop-solar uptake.
2. **Evening report** to the utility: tomorrow's at-risk streets, probability, and the recommended setting change.
3. **Connection approvals:** check a street's remaining hosting capacity before approving new rooftop systems.
4. **Scheme planning:** estimate how much PM Surya Ghar capacity each feeder can absorb with and without cheap fixes.

**Who pays.** Distribution utilities — they avoid complaints, equipment damage and network upgrades, and can approve more rooftop solar safely.

---

## 17. The dashboard

Numbered screens that follow the story from problem to decision:

1. **The story** — four plain steps: the voltage is already too high (27%); solar pushes it over at midday (1 h 15 min → 6 h 30 min); two cheap settings fix it (0 min, 0 kWh wasted vs 3 h 45 min and 489 kWh for curtailment); the AI warns a day early (6 h 45 min predicted, 7 h in the reference replay).
2. **Live map** — the 99-home street drawn from its layout, each point coloured by voltage (green safe, amber close, red too high) and each wire by loading. Press play to watch a day; points turn red around 11:00. Switch between no solar, 3 in 10, 6 in 10, every home, the strict rule, and three-phase view.
3. **Fixes** — the fix simulator plays two maps side by side, without and with the chosen fix, on one clock; a live line says what the fix is doing ("inverters absorbing 70 kvar"); impact cards show unsafe time, voltage range, peak loading and solar wasted, before and after. All actions ranked below, each with a "simulate" button and its plain-language explanation.
4. **AI forecast and risk** — how the warning is made; tomorrow's P(unsafe) strip across the day; the predicted street next to the reference replay; solar and demand forecast ranges against what happened; feature importance.
5. **Hosting capacity** — how much solar the street can take without and with the recommended fix, the adoption sweep chart, and the no-solar baseline.
6. **Stress lab** — push panel size, upstream voltage and adoption; watch voltage and transformer loading together; see the "no safe action" verdict and its binding limit.

The dashboard works on a phone, supports keyboard navigation, and loads each screen only when it is opened.

---

## 18. Team

| Person | Role | Owns | Speaks to in the demo |
|---|---|---|---|
| Person 1 (team leader) — Abhay Hanchate | Engine and data lead | Data pipeline, street model, power flow, violation engine, fixes and ranking, reconfiguration; repository and submission | The problem, the simulation, why the best fix works |
| Person 2 | ML and API | Solar and demand forecasts, risk engine, early warning, calibration, feature importance, ML shortcut, FastAPI service | The AI, its accuracy and why it is honest |
| Person 3 | QA, testing, docs and pitch | Test plan, edge-case tests, hosting-capacity engine, README, PPT, video, demo script | Results, impact and reproducibility |
| Person 4 | Tech lead, new features | Dashboard, simulators, stress lab, three-phase view, performance, phone layout and accessibility, live deployment | The dashboard, the simulators and the roadmap to utilities |

---

## 19. Judge questions and answers

| Question | Answer |
|---|---|
| **Where is the AI?** | LightGBM quantile models forecast tomorrow's solar and demand as calibrated ranges; the risk engine turns those ranges into a probability of unsafe voltage or overload; a graph-neural-network shortcut pre-screens hundreds of fix combinations. Physics verifies every answer — the AI predicts, the engine decides. |
| **Isn't pandapower doing all the work?** | pandapower is the calculator. Our contribution is the Indian calibration, solar attribution, the voltage-plus-loading violation engine, the risk probability, the all-day fix tournament with the PS actions, hosting capacity, the honest verdict, the forecasts and the simulators. |
| **Is this a digital twin?** | It is a calibrated model of a street that replays real days, forecasts tomorrow and tests actions before they touch the real network. It becomes a live twin as soon as it is fed a utility's AMI stream for a real feeder; the pipeline is built for exactly that swap. |
| **Is this a real Mathura street?** | The layout is a public benchmark street re-parameterised with Indian overhead wire; household use and voltage are real Mathura measurements. A utility plugs in its own feeder map. |
| **How accurate is the forecast?** | Solar: 13% better than "same hour yesterday" on 2025, a year it never saw, with 82% of real values inside the predicted range. Demand: 5% better, 82% coverage. Warning: 6 h 45 min predicted against 7 h in the reference replay. |
| **Why not just curtail solar?** | It wastes 489 kWh on one street in one day and still leaves 3 h 45 min unsafe. |
| **Why is two notches lower rejected?** | It fixes noon but drops evening voltage to 206 V, below the 207 V limit. A fix must be safe all day. |
| **Why did the 50 kW battery not fix it?** | Much of the high voltage comes from upstream, not only from solar; one battery at one point cannot pull the whole street down. It still cuts unsafe time from 6 h 30 min to 5 h. GridTwin sizes the battery by sweep rather than guessing. |
| **Can a fix that solves voltage cause a new problem?** | Yes — our stress study shows tap + smart inverters bringing voltage to 248 V while the transformer reaches 172% loading. That is why GridTwin always checks voltage and loading together. |
| **What if no fix works?** | GridTwin says "no safe action", names the binding limit and the closest option — as it does under the strict ±6% rule and in the 5 kW stress case. |
| **Balanced model — isn't Indian rooftop solar single-phase?** | Yes. GridTwin runs the fast balanced model for sweeps and confirms results in three-phase unbalanced mode with per-phase homes, so one overloaded phase is never hidden by an average. |
| **Where is "changing feeder connections"?** | Feeder reconfiguration is one of the actions: the engine opens and closes the street's switches, keeps it radial, and replays the day. Reconfiguration is a known way to raise hosting capacity (Capitanescu et al. 2015). |
| **How would a utility use it?** | An evening run flags tomorrow's at-risk streets with a probability and the setting change to make; it also checks remaining hosting capacity before approving new rooftop solar. |
| **Does it scale?** | Streets are independent and a day takes seconds, so thousands run in parallel on cloud machines overnight. |
| **What is the business case?** | Utilities avoid complaints, equipment damage and network upgrades, and can approve more rooftop solar safely. |

---

## 20. Slide-by-slide content for the PPT

Map these blocks onto the official template's own slots; drop what has no slot.

| Slide | Title | Content | Visual |
|---|---|---|---|
| 1 | Team and track | Team name, members, HackMatrix 5.0, Energy track, ENR-02 | Logo |
| 2 | The problem | Solar pushes power backwards up the street's wire → voltage above 253 V and overloaded transformers at midday; appliances damaged, inverters trip; utilities curtail or refuse solar; PM Surya Ghar targets 1 crore homes | Street sketch with arrows reversing at noon |
| 3 | Evidence | 38 real Mathura homes: median 245.5 V, 27% of readings above 253 V before any solar; Indian wire alone drops far-end voltage 230 → 213 V | Voltage distribution chart |
| 4 | Our solution | GridTwin: forecast → risk probability → all-day verified fix → hosting capacity → honest verdict; AI predicts, physics decides | Five-question table (§5.1) |
| 5 | How it works | Architecture diagram (§6) | Diagram |
| 6 | AI / ML | Quantile forecasts (13% and 5% better than yesterday, 82% calibrated); risk probability; ML shortcut pre-screen; honest day-ahead inputs | Forecast band chart + P(unsafe) strip |
| 7 | Results | 1 h 15 min → 6 h 30 min unsafe; best fix 0 min, 0 kWh wasted vs curtailment 3 h 45 min, 489 kWh; hosting capacity 30 → 297 kW; warning 6 h 45 min vs 7 h | Story bar chart + fix simulator screenshot |
| 8 | Stress test and honesty | Tap + inverters: 248 V but 172% transformer; 5 kW: no safe action, binding limit loading; strict ±6%: no fix enough | Voltage-vs-loading two-bar chart |
| 9 | Tech stack | pandapower, SimBench, OpenDER, pvlib, LightGBM, GNN shortcut, FastAPI, React, GitHub Actions | Logos |
| 10 | Impact and SDGs | Households, DISCOMs, PM Surya Ghar, environment; SDG 7, 13, 11, 9 | Icons |
| 11 | Feasibility and adoption | Seconds per street-day, parallel at scale; pilot → evening report → connection approvals → scheme planning | Adoption strip |

---

## 21. Three-minute video script

Slides plus the working prototype. Say "our Round 1 prototype" when the dashboard is on screen.

| Time | On screen | Narration |
|---|---|---|
| 0:00–0:20 | Slide 2 | "India is putting solar on 1 crore roofs. At midday that solar flows backwards up the street's wire and pushes voltage above the safe limit — damaging appliances and making inverters switch off." |
| 0:20–0:35 | Slide 3 | "Smart meters in 38 Mathura homes show the street is already at 245 volts on a 230-volt system, above the 253-volt limit 27% of the time — before any solar." |
| 0:35–0:55 | Slide 5 | "GridTwin is a model of the street calibrated with real Indian data. It forecasts tomorrow with an AI that knows its uncertainty, turns that into a risk probability, and tests every fix over the whole day with physics — voltage and overload together." |
| 0:55–1:20 | Prototype · Live map, every home, play to 11:00 | "Here is our Round 1 prototype on a real day. With solar on every home the street is unsafe for six and a half hours — five and a quarter of them caused by solar — peaking at 263 volts." |
| 1:20–1:50 | Prototype · Fixes, simulate tap + inverters, then curtail 40% | "We replay seven fixes. One notch on the transformer plus smart inverters: zero minutes unsafe, zero solar wasted. The common approach, throwing away 40% of solar, still leaves almost four hours unsafe and wastes 489 kWh." |
| 1:50–2:10 | Prototype · Hosting capacity | "The same two settings raise the street's safe solar capacity from 30 kilowatts to 297 — every home." |
| 2:10–2:30 | Prototype · AI forecast | "A day ahead, the AI predicted six hours forty-five minutes of unsafe voltage; the reference replay shows seven." |
| 2:30–2:50 | Slide 8 | "And GridTwin is honest. Push panels to 5 kW and the best settings fix voltage but overload the transformer to 260% — GridTwin says 'no safe action' and names why." |
| 2:50–3:00 | Slide 11 | "GridTwin tells a utility, the evening before, which streets will go unsafe and the cheapest verified way to keep them safe." |

---

## 22. Sources

**Data and policy**
- CEEW — *High frequency smart meter data from two districts in India (Mathura and Bareilly)*, Harvard Dataverse, CC0. https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/GOCHJH
- Open-Meteo — historical weather, archive and Previous Runs APIs. https://open-meteo.com/
- ERA5 reanalysis — Copernicus Climate Data Store (ECMWF).
- SimBench benchmark grids for pandapower. https://github.com/e2nIEE/simbench
- CEA — Minutes of the meeting to finalise declared supply voltage. https://cea.nic.in/wp-content/uploads/dp_r/2022/06/Approved_MoM_of_the_Meeting_to_finalize_Declared_Supply_Voltage.pdf
- PIB — Cabinet approves PM-Surya Ghar: Muft Bijli Yojana for rooftop solar in 1 crore households. https://www.pib.gov.in/PressReleasePage.aspx?PRID=2010130
- IS 398 (Part 2) — Aluminium conductors for overhead transmission (ACSR); CSPDCL ACSR conductor particulars.
- EPRI OpenDER — open-source IEEE 1547-2018 DER model. https://github.com/epri-dev/OpenDER
- GridTwin repository. https://github.com/abhay-hanchate/GridTwin

**Papers** (details checked against Crossref)
1. Thurner, L. et al. (2018). pandapower — An Open-Source Python Tool for Convenient Modeling, Analysis, and Optimization of Electric Power Systems. *IEEE Transactions on Power Systems*. doi:10.1109/TPWRS.2018.2829021
2. Meinecke, S. et al. (2020). SimBench — A Benchmark Dataset of Electric Power Systems to Compare Innovative Solutions Based on Power Flow Analysis. *Energies*. doi:10.3390/en13123290
3. Farivar, M., Neal, R., Clarke, C., Low, S. (2012). Optimal inverter VAR control in distribution systems with high PV penetration. *IEEE PES General Meeting*. doi:10.1109/PESGM.2012.6345736
4. Jahangiri, P., Aliprantis, D. (2014). Distributed Volt/VAr control by PV inverters. *IEEE PES General Meeting*. doi:10.1109/PESGM.2014.6939383
5. Xu, Xue, Chang (2021). Review of Power System Support Functions for Inverter-Based Distributed Energy Resources — Standards, Control Algorithms, and Trends. *IEEE Open Journal of Power Electronics*. doi:10.1109/OJPEL.2021.3056627
6. Ghosh, S., Rahman, S., Pipattanasomporn, M. (2017). Distribution Voltage Regulation Through Active Power Curtailment With PV Inverters and Solar Generation Forecasts. *IEEE Transactions on Sustainable Energy*. doi:10.1109/TSTE.2016.2577559
7. Bienstock, D., Chertkov, M., Harnett, S. (2014). Chance-Constrained Optimal Power Flow: Risk-Aware Network Control under Uncertainty. *SIAM Review*. doi:10.1137/130910312
8. Lubin, M., Dvorkin, Y., Backhaus, S. (2017). A robust approach to chance constrained optimal power flow with renewable generation. *IEEE PES General Meeting*. doi:10.1109/PESGM.2017.8274507
9. Ismael, S. M. et al. (2019). State-of-the-art of hosting capacity in modern power systems with distributed generation. *Renewable Energy*. doi:10.1016/j.renene.2018.07.008
10. Ding, F., Mather, B. (2018). On Distributed PV Hosting Capacity Estimation, Sensitivity Study and Improvement. *IEEE PES General Meeting*. doi:10.1109/PESGM.2018.8585839
11. Capitanescu, F., Ochoa, L. F., Margossian, H., Hatziargyriou, N. D. (2015). Assessing the Potential of Network Reconfiguration to Improve Distributed Generation Hosting Capacity in Active Distribution Systems. *IEEE Transactions on Power Systems*. doi:10.1109/TPWRS.2014.2320895
12. Yang, Y. et al. (2014). Sizing Strategy of Distributed Battery Storage System With High Penetration of Photovoltaic for Voltage Regulation and Peak Load Shaving. *IEEE Transactions on Smart Grid*. doi:10.1109/TSG.2013.2282504
13. Zeraati, M., Hamedani Golshan, M. E., Guerrero, J. M. (2018). Distributed Control of Battery Energy Storage Systems for Voltage Regulation in Distribution Networks With High PV Penetration. *IEEE Transactions on Smart Grid*. doi:10.1109/TSG.2016.2636217
14. Kritzinger, W. et al. (2018). Digital Twin in manufacturing: A categorical literature review and classification. *IFAC-PapersOnLine*. doi:10.1016/j.ifacol.2018.08.474
15. Wright, L., Davidson, S. (2020). How to tell the difference between a model and a digital twin. *Advanced Modeling and Simulation in Engineering Sciences*. doi:10.1186/s40323-020-00147-4
