# GridTwin v2: verified research report

Date: 8 Oct 2026 · Written for the GridTwin team, to settle the v2 plan.
Method: web search for sources, Gemini (`antigravity/gemini-3.7-flash-high` through OmniRoute) to read papers and pages, GitHub API for repo facts, Harvard Dataverse API for dataset facts, and our own simulation to re-test one claim. Per-source Gemini summaries are in `research/summaries/`.

## 0. How much was actually checked

| Level | What | Count |
|---|---|---|
| Read in depth (Gemini on full text or page) | Papers, reports, repo pages, news | 22 |
| Facts pulled from an official API | GitHub repos (stars, licence, last push): 24 found. Dataverse CEEW record: licence and file list | 25 |
| Checked by me directly | CEEW report raw text (voltage-rule and 70% claims); my own Volt/VAR simulation re-run | 2 |
| Seen only in search snippets | Papers, vendors, datasets, news. Useful leads, not verified | about 45 |
| Blocked or unreadable | NREL India PDF (NREL domain renamed, links dead), BIS draft (link expired), MDPI ERA5-India paper (403), one RenewableWatch article (gateway busy) | 4 |

So the claim is about 90 items touched, of which about 45 are verified to some depth. Everything below is marked verified, snippet-only or unverified. The 50–60 target is reached only if snippet-only leads are counted.

## 1. Verdicts on the earlier research

| Claim (source) | Verdict | Evidence |
|---|---|---|
| "2022 CEA/BIS decided 230 V, +10% then ±6%" (report 5) | **Not found** | No CEA text found. The nearest Indian rule is a state code with ±6% for low tension. |
| "2025 Gujarat GUVNL study confirms tail-end voltage rise" (report 5) | **Not found / likely misattributed** | Searches found no GUVNL study. A 2026 paper by Gujarat authors exists, but it uses the IEEE 906-bus European feeder, not a GUVNL network. |
| Mathura median 245.5 V, 27% above 253 V (Final Doc) | **Supported** | CEEW report: half of households were outside ±10% for at least 25% of the time. The 27.2% figure was not re-derived here. |
| "±6% is a future tightening; our S5 is a stress case" (Final Doc) | **Wrong for UP** | CEEW report: "prescribed 230 V ±6% (216–244 V) (UPERC 2005)"; 70% of areas were outside it for more than 50% of the time. Verified in raw text. Confirm against the Supply Code itself. |
| "No open digital twin for LV feeders" (report 2) | **Mostly true** | Open engines exist (pandapower, power-grid-model, OpenDSS) but no open end-to-end twin. Vendor twins exist (section 6). |
| "Volt/VAR costs no solar" (report 5) | **True here, with a cost** | Our run: standard curve gives 0 unsafe steps, 220.5–250.1 V, but transformer loading rises 44% to 66%. A Gujarat-authored paper reports reactive loss rising 3.3×. |
| "Volt/VAR works on rooftop PV" (report 5) | **Depends on R/X** | A Sandia study found it "insignificant" on low-resistance US secondaries. It clears our high-R/X Indian-wire street. R/X is the deciding variable. |
| "Hosting capacity is a single number" (Final Doc §9.3) | **Weak** | Literature treats it as a distribution over scenarios (closed-form Monte Carlo, 1,000 samples gave under 3% error). |
| GNN shortcut (Final Doc) | **Not worth it** | Best GNN result is about 37× faster than OpenDSS on millisecond solves, no solar tested, no code. Our solve is about 0.03 s. |
| ERA5 is a poor "truth" for solar | **Overstated** | Abstract-level only: against 27 IMD stations ERA5 RMSE is about 20.8 W/m², MBE −0.8%, r 0.94, slightly under in monsoon cloud. CERES is best. The real gap is that there is no measured PV output. |
| Australia "40% of inverters misconfigured", UK 16 A cap, German PF ≥ 0.95, battery $200–400/kWh (report 5) | **Unchecked** | Not verified in this round. Do not put these on a slide. |
| Reports 1 and 2 paper list (Hokmabad, Hein, Oliveira, Du, de Jongh) | **Mostly unchecked** | Only de la Varga (real, arXiv 2307.16822) and Hoogsteyn (real, MIT repo) were checked. |

## 2. Facts that change the problem framing (India)

| Fact | Source | Status |
|---|---|---|
| 50.06 lakh households with rooftop solar by 4 Aug 2026, 14.8 GW; record 5.06 lakh installs in July 2026; target 75 lakh by Dec 2026 | Search (MNRE statement reported by press) | Snippet-only |
| Rooftop solar up to **10 kW is exempt from the technical feasibility study** (Rights of Consumers Amendment Rules 2024); larger systems get a 15-day window and are deemed feasible if the DISCOM is silent | Mercom, Telangana notification | Snippet-only |
| DT caps on rooftop PV vary by state: Delhi 20%, Rajasthan 30%, Karnataka 80%, Tamil Nadu 90%, Odisha 75%. GIZ: "limited scientific basis" | GIZ 2018 presentation; TN and Odisha reports | Snippet-only |
| Only 42% of distribution transformers were metered at 31 Mar 2024; 52.5 lakh DT meters sanctioned under RDSS | CEA status via T&D India; RDSS reply | Snippet-only |
| 7.24 crore smart meters installed by 30 Jun 2026; RDSS sunset moved to 31 Mar 2028 | Parliament reply via T&D India | Snippet-only |
| Rajasthan DISCOMs (2 Mar 2026): single-phase rooftop connections released only after **phase balancing at the DT**; new connections go to the least-loaded phase | Energetica India (read by Gemini) | Verified (news report of an office order) |
| BIS has adopted IEEE 1547-2018 for India; drafts differ on whether there is a National Annexure A | NREL abstract, BIS drafts (snippets) | Unverified detail |
| Rural Indian feeders are voltage-limited, urban ones are thermal-limited; up to 75% of DT capacity hosts without upgrades | ADB/MNRE study, Delhi + Bhopal | Verified |

## 3. Datasets (verified where marked)

| Dataset | What | Licence | Status | Use in v2 |
|---|---|---|---|---|
| CEEW smart meters (Dataverse) | About 93 single-phase meters, Mathura **and Bareilly**, 3-min voltage/current/kWh, May 2019 to Oct 2021 | CC0 (API-verified) | **Round 1 used only Mathura 2019 (38 homes).** Mathura 2020 and 2021 and all of Bareilly are unused. | Biggest cheap upgrade: 2.4 years, 2 districts. Real seasonality for demand and upstream voltage. |
| Prayas eMARC | 115 households, minute data, Pune, Aurangabad, Kanpur Rural, Gonda, Jan 2018 to Jun 2020 | Not stated | Dashboard public; raw download not stated | Second Indian voltage source (rural, up to 280 V). Needs an email to Prayas. |
| RECON-SL (Sri Lanka) | 1,438 smart-metered homes, 15-min, includes voltage and current, rooftop solar tracked | CC BY 4.0 | Verified (Gemini) | South Asian stand-in for held-out testing. About 20% complete at 15-min. |
| Kaggle / IEEE DataPort 2-plant set | 2 utility-scale plants, 34 days, 15-min inverter + weather | Not checked | Snippet-only | Calibrate PV model. Not rooftop. |
| IEEE DataPort Karnataka | 72 kWp plant, hourly, May 2021 to Sep 2024 | Not checked | Snippet-only; a user comment doubts the file | Possible measured series. Check file first. |
| IMD / SRRA ground irradiance | 45 IMD stations, 51 SRRA stations | Access route not found | Unverified | Would validate ERA5. |
| Satellite irradiance for India | NREL 10 km hourly 2002 to 2012; INSAT-3D products | Public (NREL) | Snippet-only | Old; CAMS coverage of India not confirmed. |
| Indian LV feeder model | None open. GIZ feeders came from BRPL and MPMKVVCL; release unknown | n/a | Searched, not found | Keep SimBench with Indian wire; use ADB conductor data (Dog, Rabbit, Raccoon ACSR) as the justification. |

**Gap confirmed:** no open Indian rooftop-solar generation data and no open Indian LV feeder topology were found.

## 4. Repositories (GitHub API, 8 Oct 2026)

| Repo | Stars | Licence | Last push | Role |
|---|---|---|---|---|
| e2nIEE/pandapower | 1,293 | BSD-3 (API says NOASSERTION) | 7 Oct 2026 | Current engine; keep |
| PowerGridModel/power-grid-model | 248 | MPL-2.0 | 8 Oct 2026 | C++ core, asymmetric power flow and state estimation. Candidate fast engine. |
| e2nIEE/simbench | 143 | NOASSERTION | 22 Sep 2026 | Street model; keep |
| OpenSTEF/openstef | 171 | MPL-2.0 | 8 Oct 2026 | Probabilistic forecasting pipeline to borrow from |
| scikit-learn-contrib/MAPIE | 1,602 | BSD-3 | 8 Oct 2026 | Conformal calibration for P10/P90 |
| pvlib/pvlib-python | 1,690 | BSD-3 | 8 Oct 2026 | Solar physics; keep |
| dss-extensions/OpenDSSDirect.py, DSS-Python | 116, 80 | NOASSERTION, BSD-3 | 26 Feb 2026 | Cross-check engine |
| NatLabRockies/PyDSS | 42 | NOASSERTION | 25 Sep 2026 | Used by the GNN surrogate paper |
| epri-dev/OpenDER | 76 | NOASSERTION | 23 Jun 2025 | Named in Final Doc but not used. Either use or remove. |
| Grid2op/grid2op | 477 | MPL-2.0 | 7 Oct 2026 | RL environments; not needed |
| AlexanderHoogsteyn/PhaseIdentification | 5 | MIT | 11 Apr 2022 | Phase-ID reference; old but licensed |
| tomislavantic/ppOPF | 9 | none (Gemini read CC-BY-NC) | 26 Mar 2025 | 3-phase OPF on pandapower; licence unclear |
| Team-Nando (Volt-Watt HC, OE1-Ideal, OEs-The-Basics) | 1 | BSD-3 | 28 Apr 2026 | Operating-envelope and hosting-capacity tutorials |
| wenbowangnrel/Hosting-Capacity-Analysis | 1 | none | 12 Jul 2023 | Reference only; no licence |
| LIRNEasia/lacuna | n/a | n/a | n/a | RECON-SL code; the API lookup used a guessed repo name and 404'd, so unconfirmed |

## 5. Papers worth building on (read by Gemini)

| Paper | Why it matters | Limits |
|---|---|---|
| Gaebler et al., ADB/GIZ 2018: Indian distribution systems with rooftop PV (Delhi, Bhopal) | Indian feeder parameters; rural = voltage, urban = thermal; 75% DT hosting | Slides; no R/X matrices |
| CEEW 2020, "What smart meters can tell us" | 93 meters; UPERC ±6% rule; 70% of areas outside it; 25–30% evening voltage drops | No solar in sample; about 15% data loss |
| CSTEP 2026, feeder-level rooftop impact | Indian 11 kV feeder, 23 DTs, 8,760 h currents | Snapshot at 9 a.m. only, PowerFactory, no LV |
| Deakin et al. 2019, stochastic HC | Closed-form probabilistic HC; 1,000 samples under 3% error | UK feeders; voltage only |
| arXiv 2405.20682, phase selection and hosting capacity | Optimal phase choice gave 474.5 kW vs 258.5 kW for random assignment on a real 64-node feeder | European feeders; no Volt/VAR |
| arXiv 2204.06372 (Hoogsteyn repo), phase ID | Voltage correlation with transformer reference: 95–100% | European/Irish data |
| PowerFlowMultiNet 2024 | Unbalanced GNN surrogate, 15–38× speedup | No solar/DER; no code |
| de la Varga et al. 2025, state estimation | Pseudo-measurements for sparse data | Assumes PMUs; synthetic IEEE-33 |
| Robust DOE from local voltage, 2023 | Export limits with no telemetry; chance-constrained day-ahead variant | Spanish feeder |
| LACE DOE allocation, 2026 | Fast solver-free envelope allocation | Single-phase equivalent |
| Gujarat-authored Volt/VAR, 2026 | IEEE 1547 curve points (0.94 / 0.99 / 1.01 / 1.06 pu); 18 of 21 homes breach at 100% PV; reactive loss 3.3× | IEEE 906-bus, Phase A only |
| Sandia Volt/VAR study | Volt/VAR ineffective on low-R/X secondaries | US feeders |
| Renkema et al. 2024, conformal PV | 14% better interval score than quantile regression | Dutch; abstract only |
| TERI, digital twins for LV grids | Names the Indian use cases (topology, phase, congestion) | Landing page only |

## 6. Landscape and competitors

| Player | What | Overlap with GridTwin |
|---|---|---|
| Venios (Germany) with TERI, BRPL Delhi | Cloud digital twin pilot; DER impact analysis promised | High on paper; no results published |
| Edge Electra with JVVNL (Jaipur), DUET | Whole-network digital twin plus predictive utility | Medium; focus is network-wide, status unknown |
| ISA / Rajasthan digital twin | 15 consortia responded; winner not found | Unknown |
| Gridspertise with Tata Power-DDL | Secondary-substation automation, asset twin | Low |
| MSEDCL digital twin (Dec 2025 headline) | Solar integration; vendor unknown | Unknown |
| TERI + BSES (2025 MoU) | 3-year DER, storage, digital twin, AI | Research partner, not a product |
| CYME (Eaton), Synergi (DNV), PowerFactory (DIgSILENT) | Commercial hosting-capacity modules | Engineer tools; licensed; not Indian-calibrated |
| Opus One (now GE Digital DERMS), Camus | Real-time DERMS and flexible limits | Real-time, needs SCADA |
| Utilidata | Edge AI voltage optimisation; pivoting to data centres | Different market now |
| Genus, Itron | DT monitoring hardware and analytics | Hardware vendors; potential data source |

**Finding:** across all of the above I found no product that offers day-ahead LV risk, a fix tournament and hosting capacity for Indian rooftop solar. No Indian DISCOM publishes a hosting-capacity map. Search coverage was limited, so this is an absence of evidence, not proof.

## 7. Whitespace and v2 features, ranked

Effort is my estimate, not sourced.

| # | Feature | Why (evidence) | Effort | India fit |
|---|---|---|---|---|
| 1 | **Use all CEEW data** (Mathura 2019–21, Bareilly 2019–21) | CC0, about 93 meters, 2.4 years. Round 1 used 38 homes, one season. Fixes the weak demand model (0.9% skill) and gives real seasonal voltage. | Medium | Very high |
| 2 | **State rule library**, UP ±6% as current | CEEW cites UPERC 2005 ±6%. Our S5 "failure" is the UP rule today. | Low | Very high |
| 3 | **Standard Volt/VAR + Volt/Watt with cost accounting** | Tested: 0 unsafe steps, 66% transformer loading. Add reactive losses and an R/X sensitivity run (Sandia vs Indian wire). | Low–medium | High |
| 4 | **DT headroom and phase-balancing engine** | Rajasthan order of 2 Mar 2026; state caps with no scientific basis; 10 kW feasibility exemption. Output: per-DT headroom, which phase to give the next connection, which DTs to meter first. | Medium | Very high; matches live regulation |
| 5 | **Probabilistic hosting capacity** (P10/P50/P90) | Literature standard; closed-form Monte Carlo is cheap. | Medium | High |
| 6 | **Day-ahead per-house export limits** (operating envelopes) | Australian DEIP practice; open BSD code; local-voltage variant needs no telemetry. Replaces blunt curtailment, which the problem statement asks to limit. | Medium–high | High; no Indian equivalent found |
| 7 | **Conformal-calibrated risk engine** | MAPIE is active and BSD-3. No paper found linking conformal PV forecasts to voltage-violation probability (search not exhaustive). | Medium | Medium |
| 8 | Sparse state estimation from DT + consumer meters | power-grid-model has asymmetric state estimation. DT meters exist (52.5 lakh sanctioned). | High | High; stretch goal |
| 9 | Measured-PV calibration | Karnataka 72 kWp and 2-plant sets; no rooftop data exists openly. | Low | Medium |

**Cut from Round 1 claims:** GNN shortcut, OpenDER, GNN-based "ML pre-screen" language, "3-phase confirmed" unless built, and any slide stat from report 5 marked unchecked in section 1.

## 8. Unverified or blocked: do not cite yet

- NREL India IEEE 1547 report body (only the abstract is confirmed; PDFs 404 after NREL's rename).
- BIS adoption detail and any National Annexure A voltage settings.
- CEA 2019 DG connectivity amendment text.
- The 2022 CEA decision and the GUVNL study.
- ERA5-over-India numbers (abstract snippet only).
- Maharashtra +10%/−15% (from the Final Doc, not re-checked).
- Vendor cost, speed, and funding figures.

## 9. Decisions the final plan must make

1. How many of features 1–9 fit before the freeze (Fri 9 Oct 12:00 is tomorrow). Features 1–3 are the realistic ones.
2. Whether to switch the engine to power-grid-model. It is faster and has state estimation, but it is a rewrite risk.
3. Whether to state in the Final Document that ±6% is the UP rule today, and rename S5 accordingly.
4. Whether to email Prayas for raw data and ask a DISCOM for a DT-level sample.
5. How to present the competitor gap honestly given limited search coverage.
