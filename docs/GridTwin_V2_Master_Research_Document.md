# GridTwin v2: master research document

**Date:** 8 Oct 2026 · **Status:** research complete, ready to turn into the build plan
**Combines:** the Final Project Document, the Round 1 build, the four research docs you supplied, and two verification rounds (about 130 items touched, 31 read in depth; method in Appendix B).
**Evidence rule:** every claim is tagged **[V]** verified (read in full text, raw text, or an official API), **[S]** seen only in a search snippet or abstract, **[U]** unverified or not found.

---

## 1. Executive summary

1. **The problem is real and getting more urgent in India.** About 50 lakh households had rooftop solar by Aug 2026 (14.8 GW) [S]. Kerala's KSEB has already stopped new connections in parts of Kochi because transformers are near the 90% loading limit [V]. Rajasthan ordered phase balancing at the transformer on 2 Mar 2026 [V].
2. **A regulation gap makes GridTwin timely.** Rooftop systems up to 10 kW are exempt from technical feasibility studies [S], and state transformer caps range from 20% to 90% with little scientific basis (GIZ) [S]. Nobody is checking cumulative transformer headroom.
3. **Round 1 had four real weaknesses:** it used 1 of about 6 available smart-meter data slices; its "smart inverter" was a fixed power factor, not the standard curve; its demand model barely beat persistence (0.9% skill); and the Final Document promised things the code does not do (risk probabilities, switching, three-phase, GNN).
4. **Round 1 also framed the voltage rule wrongly.** The CEEW report cites the UP Supply Code 2005 as prescribing 230 V ±6% [V]. Our "strict ±6% failure case" is the rule that applies in UP today.
5. **Your research docs are useful as idea menus, not as evidence.** Of 15 citation items I could check, 8 are real, 1 is partial, and 6 do not verify (section 3).
6. **The whitespace is a combination, not a single idea.** Each piece (probabilistic risk, predictive Volt/VAR, operating envelopes, phase identification) has prior art abroad. I found no source combining them for Indian low-voltage, single-phase, high-R/X streets with ranked physics-verified fixes and transformer-level connection decisions (section 9).
7. **Recommended v2 focus:** real-data upgrade, state rule library, standard Volt/VAR with cost accounting, phase-balancing fix, transformer headroom engine, calibrated risk, and per-house export limits (section 10).

---

## 2. Where we stand: Round 1 build vs the Final Document

| Final Document promise | Round 1 reality | Verdict |
|---|---|---|
| Real Indian data, CEEW Mathura | Uses Mathura 2019 only, 38 homes, 26 usable profiles | Works, but uses a fraction of the dataset |
| Standard smart inverters (IEEE 1547) | Fixed power factor 0.9 (`engine/actions.py:8`) | **Wrong.** Standard curve alone gives 0 unsafe steps (my run) |
| Risk probability, watch/act levels | Three deterministic replays (P10/P50/P90) | Missing |
| Feeder switching, battery sweep | Fixed 50 kW / 200 kWh battery; no switching | Missing |
| Three-phase confirmation | Balanced only | Missing |
| Stress cases (274 V / 148%, 5 kW) | Cannot be produced by the code | Not reproducible |
| Demand forecast "5% better, 82% coverage" | Repo report says **0.9% and 75.3%** | Stale numbers in the document |
| GNN shortcut, OpenDER | Neither exists | Remove |
| 55 tests, 17+ routes, CI, dashboard with 5 tabs | Confirmed (55 passed) | Solid |
| 241-day warning check (precision 0.991, recall 0.982) | Present in the repo reports | Solid, but uses 2019 demand as a proxy for 2025 |

Strengths worth keeping: real calibrated street, solar attribution, honest "no safe action", all-day fix ranking, leakage controls, tests and CI.

---

## 3. Assessment of the research docs you supplied

### 3.1 Verdict per doc

| Doc | What it is | Useful? | Why |
|---|---|---|---|
| `deep-research-report.md` (report 1) | Generic literature survey with nine recommendations | **Medium-low** | Good idea menu (real PV data, voltage prediction from partial meters, adaptive Volt/VAR, ANM, hybrid twin). No priorities, no India specifics, no reference list. |
| `deep-research-report (2).md` and `(3).md` (identical, 26 KB) | Gap analysis, 8 "novel" features, data schema, 2026–2030 roadmap | **Medium** | Best of the four for structure. The gaps it names are real (sparse observability, phase and topology unknowns, India-specific data). Several citations do not verify and the roadmap is for a company, not a hackathon. |
| `deep-research-report (5).md` | Mitigation menu and the case for day-ahead prediction | **Medium** | The mitigation matrix and the "why prediction adds value" argument are sound and match Round 1. Two headline Indian claims could not be found. |
| `Untitled (4).pdf` (Round 1 document) | Describes the Round 1 build | **High as a record** | Accurate for what was built on 28 Sep, but out of date (demand numbers). |

Note: earlier I summarised `deep-research-report.md` without having opened it. I have now read it and the summary matches, but treat that earlier summary as unverified.

### 3.2 Citation check of the research docs

| Citation (source doc) | Result |
|---|---|
| Mokhtar et al. 2019, voltage profile from partial smart meters (report 1) | **Real**: arXiv 1906.08374; journal version in Energy and AI 2021 [S] |
| McDermott and Abate 2019, adaptive voltage regulation, 300 s time constant (report 1) | **Real**: PNNL, IEEE PVSC 2019 [S] |
| Haider, distributed OPF with a retail market (report 1, 2) | **Real**: MIT thesis; year unconfirmed [S] |
| Collins 2015, multi-agent DER (report 1) | **Not found** |
| "Solar-Forecasting-XGBoost" and "SolarMagix" datasets (report 1) | **Not found** under those names; similar real datasets exist (Hong Kong rooftop, North Macedonia, DKASC) [S] |
| Hokmabad 2025, LightGBM + self-attention day-ahead solar (report 2) | **Real**: IEEE Trans. Sustainable Energy 2025 [S] |
| Oliveira 2019, dynamic hosting capacity (report 2) | **Real**: Energies 2019 [S] |
| de Jongh 2023, topology and parameter identification (report 2) | **Real**: arXiv 2308.09521, IEEE TPWRD 2025 [S] |
| de la Varga, learning-based state estimation (report 2) | **Real** and read in full [V] |
| Hoogsteyn, phase identification (report 2) | **Real**, repo MIT-licensed [V] |
| Du 2021, probabilistic HC with holomorphic embedding (report 2) | **Partial**: a 2021 Frontiers paper exists; authors unconfirmed [S] |
| Hein 2026, voltage control review (report 2) | **Not found**; nearest is a 2016 review |
| Chuangpishit 2021, HC best practice (report 2) | **Not found** under that name; an NREL/IREC best-practice report exists |
| Babu and Khatod 2024, distributed Volt/VAR (report 2) | **Not found** |
| "2022 CEA/BIS decision to standardise 230 V" and "2025 GUVNL study" (report 5) | **Not found** |

Tally of the 15 items above: 8 real, 1 partial, 6 not found. **Do not quote any "not found" item on a slide.** Use the real ones.

### 3.3 What to keep from the docs

Keep: real measured PV for calibration; voltage prediction from partial meters; phase identification; probabilistic hosting capacity; predictive Volt/VAR; the mitigation matrix; the value-of-prediction argument.
Drop: the 2026–2030 roadmap, the ER diagram, the "conceptual" heatmap and scatter charts, and any claim marked not found.

---

## 4. India context (verified where marked)

| Fact | Status |
|---|---|
| UP Supply Code 2005 prescribes 230 V ±6% (216–244 V); CEEW found 70% of areas outside it for over half the time | **[V]** raw text of the CEEW report |
| Half of sampled households outside ±10% for at least 25% of the time; evening drops of 25–30% in some pockets; surges above 350 V | **[V]** CEEW report |
| Rural Indian feeders are voltage-limited; urban feeders are thermal-limited; about 75% of transformer capacity hosts without upgrades | **[V]** ADB/GIZ study, Delhi and Bhopal |
| Kochi: KSEB limited new domestic solar connections; transformer loading near the 90% norm; many rooftop users export surplus by day (17 Apr 2026) | **[V]** news report read by Gemini |
| Rajasthan DISCOMs, 2 Mar 2026: single-phase rooftop connections only after phase balancing at the transformer; new connections to the least-loaded phase | **[V]** news report of an office order |
| 10 kW exemption from technical feasibility studies; states set transformer caps (Delhi 20%, Rajasthan 30%, Karnataka 80%, Tamil Nadu 90%, Odisha 75%) | **[S]** |
| 50.06 lakh households, 14.8 GW (4 Aug 2026); 75 lakh target by Dec 2026 | **[S]** |
| 7.24 crore smart meters (30 Jun 2026); only 42% of distribution transformers metered (Mar 2024); 52.5 lakh DT meters sanctioned | **[S]** |
| BIS has adopted IEEE 1547-2018 for India; details of national changes unclear | **[S]/[U]** |
| NREL India IEEE 1547 report (Mar 2024): current Indian codes lack ride-through, frequency droop and trip thresholds | **[S]** abstract only; PDF unreachable |
| Pune study (2025): rooftop solar and EV charging effect on transformer loss of life | **[S]** abstract only |

---

## 5. Data

| Source | What | Licence | Status | Use in v2 |
|---|---|---|---|---|
| CEEW smart meters (Harvard Dataverse) | About 93 single-phase meters, Mathura and Bareilly, 3-min voltage, current, kWh, May 2019 to Oct 2021 | CC0 **[V]** | Round 1 used only Mathura 2019 | Train on all of Mathura; **test on Bareilly (a held-out district)**; real seasonality |
| Prayas eMARC | 115 households, minute data, Pune, Aurangabad, Kanpur Rural, Gonda, 2018–2020 | Not stated | Dashboard public; raw data by email | Second voltage source, rural |
| RECON-SL (Sri Lanka) | 1,438 smart-metered homes, 15-min, voltage and current | CC BY 4.0 **[V]** | 20% complete at 15-min | South Asian cross-check |
| Two Indian plants (Kaggle / IEEE DataPort) | 34 days, 15-min, inverter + weather | Not checked | **[S]** | Calibrate PV model; utility-scale |
| Karnataka 72 kWp plant (IEEE DataPort) | Hourly, 2021–2024 | Not checked | **[S]**; a comment doubts the file | Possible measured series |
| ERA5 vs 27 IMD stations | RMSE about 20.8 W/m², MBE −0.8%, r 0.94; CERES best | n/a | **[S]** abstract | ERA5 is acceptable irradiance truth; the real gap is no measured PV output |
| Open-Meteo | Weather and day-ahead forecasts | Code AGPL-3.0 **[V]**; API terms not checked | In use | Check API terms before any commercial use |
| Hong Kong rooftop PV (60 stations, 5-min) | Measured rooftop PV | Not checked | **[S]** | Format model for a future Indian collection |
| Indian LV feeder model | None open | n/a | Searched, none found | Keep SimBench with Indian wire; justify with ADB conductor data |

**Gap confirmed:** no open Indian rooftop generation series and no open Indian LV topology.

---

## 6. State of the art by component, and what it means for us

| Component | Best prior art found | Reusable? | Gap left |
|---|---|---|---|
| Probabilistic voltage risk | arXiv 2410.12438 (VaR/CVaR, LSTM + GMM, curtailment and reactive actions); arXiv 2605.02340 (intensity-duration-frequency risk, 1,000 scenarios, 11M runs); Mons group (probabilistic LV with quarter-hourly smart meter data) | Ideas and metrics | All balanced or single-phase MV/IEEE; none India; none day-ahead plus ranked fixes |
| Probabilistic hosting capacity | Deakin 2019 (closed form, 1,000 samples under 3% error); risk-based HC raises capacity about 18% at a 5% risk level | Yes | UK/EU feeders, voltage only |
| Phase effects | arXiv 2405.20682: optimal phase choice 474.5 kW vs 258.5 kW random on a real feeder | Yes | No Volt/VAR; European |
| Phase identification | Hoogsteyn (voltage correlation to transformer reference, 95–100%) | Yes (MIT code) | CEEW meters have no phase labels, so we cannot validate on Indian data |
| Topology | arXiv 2409.09073 (GIS-only ILP, code public); de Jongh 2025 | Partly | No Indian validation |
| Smart-inverter control | IEEE 1547 curve points 0.94/0.99/1.01/1.06 pu (Gujarat-authored 2026); PNNL adaptive voltage regulation; Sandia (weak on low-R/X secondaries) | Yes | Effect depends on R/X; reactive losses 3.3× |
| Predictive Volt/VAR | arXiv 2604.07106 (three-stage, forecast-error cascade); Waterloo thesis (day-ahead + sequential) | Ideas | Not LV, not India |
| Operating envelopes | Robust DOE from local voltage (2305.13079); LACE allocation (2605.07989); Team-Nando OE1-Ideal (BSD) | Yes | No Indian equivalent; single-phase equivalents |
| Forecasting | LightGBM strong on day-ahead PV; Chronos/TimesFM competitive after fine-tuning (nMAE about 3.7–3.8% vs LSTM 6.7% in a Texas benchmark); physics-synthetic history helps new sites with no history (2606.07457) | Benchmark them | None tested on Indian data |
| Calibration | Conformal prediction beat quantile regression by 14% on interval score (Dutch PV) | Yes (MAPIE) | Not linked to voltage-violation probability in anything I found |
| State estimation | de la Varga (needs PMUs); power-grid-model has asymmetric estimation | Partly | Needs sparse DT + consumer meters |
| GNN surrogate | PowerFlowMultiNet: 15–38× faster than OpenDSS, no DER tested, no code | **No** | Our solve is about 0.03 s |
| Grounded assistants | NREL network-operator assistant concept; MIT thesis; Aalborg XAI | Concept only | Not for LV rooftop solar |

---

## 7. Repositories and tools (GitHub API, 8 Oct 2026; 44 repos found)

| Repo | Stars | Licence | Last push | Role |
|---|---|---|---|---|
| e2nIEE/pandapower | 1,293 | BSD-3 (API: unasserted) | 7 Oct 2026 | Engine; keep |
| PowerGridModel/power-grid-model | 248 | MPL-2.0 | 8 Oct 2026 | Fast asymmetric power flow + state estimation |
| e2nIEE/simbench | 143 | unasserted | 22 Sep 2026 | Street model |
| pvlib/pvlib-python | 1,690 | BSD-3 | 8 Oct 2026 | Solar physics |
| NatLabRockies/SAM | 490 | BSD-3 | 7 Oct 2026 | Cross-check PV model |
| OpenSTEF/openstef | 171 | MPL-2.0 | 8 Oct 2026 | Probabilistic forecasting pipeline |
| scikit-learn-contrib/MAPIE | 1,602 | BSD-3 | 8 Oct 2026 | Conformal intervals |
| amazon-science/chronos-forecasting | 6,016 | Apache-2.0 | 5 Oct 2026 | Foundation-model benchmark |
| google-research/timesfm | 34,163 | Apache-2.0 | 29 Sep 2026 | Foundation-model benchmark |
| unit8co/darts | 9,537 | Apache-2.0 | 8 Oct 2026 | Forecasting toolkit |
| Nixtla/mlforecast, statsforecast | 1,284 / 4,922 | Apache-2.0 | Oct 2026 | Baselines |
| optuna/optuna, shap/shap | 14,899 / 25,799 | MIT | Oct 2026 | Tuning, explanations |
| Pyomo/pyomo | 2,539 | unasserted | 6 Oct 2026 | Optimisation models |
| google/or-tools | 14,163 | Apache-2.0 | 8 Oct 2026 | Phase assignment / switching search |
| lanl-ansi/PowerModels.jl | 484 | unasserted | 29 Sep 2026 | Reference OPF |
| dss-extensions/DSS-Python, OpenDSSDirect.py | 80 / 116 | BSD-3 / unasserted | 26 Feb 2026 | Cross-check engine |
| NatLabRockies/PyDSS | 42 | unasserted | 25 Sep 2026 | Used by GNN papers |
| epri-dev/OpenDER | 76 | unasserted | 23 Jun 2025 | Named in Final Doc, not used |
| Team-Nando (VoltWatt HC, OE1-Ideal) | 1 | BSD-3 | 28 Apr 2026 | Operating-envelope reference |
| AlexanderHoogsteyn/PhaseIdentification | 5 | MIT | 11 Apr 2022 | Phase-ID reference |
| tomislavantic/ppOPF | 9 | none stated | 26 Mar 2025 | 3-phase OPF reference; licence unclear |
| wenbowangnrel/Hosting-Capacity-Analysis | 1 | none | 12 Jul 2023 | Reference only |
| open-meteo/open-meteo | 6,310 | **AGPL-3.0** | 8 Oct 2026 | Weather source; check terms |
| davidusb-geek/emhass | 697 | MIT | 8 Oct 2026 | Energy-management reference |
| Grid2op/grid2op, powsybl-core, gridlab-d, PyPSA, CIM-Graph, ditto | various | MPL/BSD/MIT | 2024–2026 | Not needed for v2 |
| FastAPI, networkx, geopandas, pgmpy, FLAML | various | MIT/BSD | Oct 2026 | Supporting stack |

---

## 8. Landscape and competitors

| Player | What they do | Overlap | Evidence |
|---|---|---|---|
| Venios (DE) with TERI, BRPL Delhi | Cloud digital twin pilot; DER impact analysis promised | High on paper; no results published | [S] |
| Edge Electra with JVVNL (Jaipur) | Whole-network digital twin, "predictive utility" | Medium; network-wide, status unknown | [S] |
| ISA / Rajasthan digital twin | 15 consortia responded; winner unknown | Unknown | [S] |
| MSEDCL digital twin (Dec 2025) | Solar integration; vendor unknown | Unknown | [S] |
| Gridspertise with Tata Power-DDL | Secondary-substation automation | Low | [S] |
| TERI + BSES (2025 MoU) | 3-year DER, storage, twin, AI research | Research partner | [S] |
| WorkOnGrid (Bengaluru, ₹22.5 cr, 7 Apr 2026) | Utility data platform: theft, faulty meters, maintenance, natural-language queries; **no rooftop hosting capacity or voltage analysis stated** | Adjacent; possible data partner | **[V]** |
| Bidgely (US/India) | Theft, load forecasting, grid stability analytics | Adjacent | [S] |
| Prescinto, Renkube, The Solar Labs | Solar monitoring, AI for renewables, site assessment | Adjacent (plant-side) | [S] |
| SolarSquare, Freyr, ZunRoof | Rooftop installers | Channel, not competitors | [S] |
| CYME (Eaton), Synergi (DNV), PowerFactory (DIgSILENT) | Commercial hosting-capacity modules | Engineer tools, licensed, not Indian-calibrated | [S] |
| Smarter Grid Solutions (Mitsubishi Electric) | Active network management and DERMS; 521 MW (vendor claim) | Real-time, needs control infrastructure | [S] |
| Opus One (GE Digital DERMS), Camus | DERMS, flexible limits | Real-time, needs SCADA | [S] |
| Utilidata | Edge AI voltage optimisation, pivoting to data centres | Different market now | [S] |
| Genus, Itron | DT monitoring hardware and analytics | Potential data source | [S] |

**Finding:** across all of these I found no product offering day-ahead low-voltage risk plus a ranked fix list plus transformer-level hosting capacity for Indian rooftop solar, and no Indian DISCOM hosting-capacity map. This is absence of evidence from a limited search, not proof.

---

## 9. Whitespace and innovation

### 9.1 Prior-art check on each idea

| Idea | Prior art exists? | What is genuinely new for us |
|---|---|---|
| Probabilistic day-ahead voltage risk | **Yes** (2410.12438, 2605.02340, Mons group) | Applying it to unbalanced, high-R/X Indian low-voltage streets, tied to ranked physics-verified fixes. Do **not** claim the risk idea is new. |
| Predictive Volt/VAR | **Yes** (Waterloo, 2604.07106) | LV and Indian conditions; cost accounting (reactive loss, transformer loading, R/X map) |
| Operating envelopes | **Yes** (Australia, open code) | No Indian equivalent found; framed as the alternative to blunt curtailment |
| Phase identification | **Yes** (Hoogsteyn) | Using it as an **action**: assign the next connection to a phase (Rajasthan rule) and score its effect |
| Transformer hosting capacity | **Yes** (US utility maps) | None in India; replaces arbitrary state caps; works with the 10 kW feasibility exemption |
| Conformal calibration of PV forecasts | **Yes** (Renkema) | Linking calibrated forecast intervals to voltage-violation probability: I found no paper doing this (search not exhaustive) |
| LLM / explainable assistant | Concept only (NREL, MIT) | Numbers-only explanations from verified power flow |

### 9.2 Defensible whitespace statement

> Existing work proves each ingredient abroad. We found no tool that, for an Indian low-voltage street with single-phase rooftop solar and high-resistance overhead wire, gives a DISCOM a **calibrated day-ahead risk**, a **physics-verified ranked fix** (including the phase to assign and per-house export limits), and a **transformer-level connection decision**, with an honest "no safe action" verdict and the state's own voltage rule.

### 9.3 Innovation list for v2

| # | Innovation | Why it is defensible |
|---|---|---|
| I1 | **Rule-aware verdicts** (UP ±6%, ±10%, state variants), with the rule's source shown | Changes verdicts; CEEW cites UPERC ±6% |
| I2 | **Phase-reallocation as a fix**, scored in the tournament | Rajasthan order; optimal phase choice raised capacity about 84% over random assignment in one real feeder study |
| I3 | **Cost-aware smart inverters**: standard curve, plus reactive loss, transformer loading and an R/X map showing when Volt/VAR works | Sandia vs our result vs 3.3× reactive loss |
| I4 | **Transformer headroom engine** replacing flat percentage caps; ranks which transformers to meter first | Kochi, GIZ caps, 42% DT metering |
| I5 | **Calibrated risk engine** with a reliability curve | Conformal tooling exists; reliability proof is ours to show |
| I6 | **Day-ahead per-house export limits** instead of blanket curtailment | Problem statement asks for limited reduction in renewable output |
| I7 | **Held-out district test** (train Mathura, test Bareilly) | Real generalisation evidence Round 1 lacked |
| I8 | **Cold-start forecasting for new rooftop sites** using physics-synthetic history | New PM Surya Ghar systems have no history |
| I9 | **Numbers-only explanations** | Honest AI story that judges can test |

---

## 10. Proposed v2 scope (priority order)

Effort is my estimate; nothing here is built yet.

| Priority | Module | What changes from Round 1 | Evidence base |
|---|---|---|---|
| P0 | Data v2: all CEEW slices, seasonal upstream-voltage model, train/test by district | Replaces 1 slice with 6; fixes weak demand model | Dataverse API |
| P0 | Rule library with source citations; rename S5 | Corrects the framing | CEEW raw text |
| P0 | Standard Volt/VAR + Volt/Watt, with loading and reactive-loss accounting | Replaces fixed pf 0.9 | My run: 0 unsafe steps, 220.5–250.1 V, trafo 66% |
| P1 | Phase model and phase-reallocation fix | New | Rajasthan order, arXiv 2405.20682 |
| P1 | Transformer headroom and connection check | Replaces flat caps | Kochi, GIZ |
| P1 | Risk engine with conformal calibration and reliability curve | Replaces P10/P50/P90 replays | MAPIE, 2410.12438 |
| P2 | Per-house export limits (operating envelopes) | Replaces uniform curtailment | Team-Nando OE code, 2305.13079 |
| P2 | Forecast benchmark: LightGBM vs Chronos-2/TimesFM, with cold-start variant | Evidence-based model choice | 2604.22077, 2606.07457 |
| P2 | Feeder switching and battery sweep (problem statement actions) | Currently missing | Final Doc |
| P3 | Engine evaluation: power-grid-model vs pandapower | Possible speed-up | Repo facts |
| P3 | Sparse state estimation from DT + consumer meters | New | de la Varga, power-grid-model |

**Remove from claims:** GNN shortcut, OpenDER, "three-phase confirmed" unless built, stress-study numbers until regenerated, any "not found" item from section 3.2.

---

## 11. Evaluation plan (how v2 proves itself)

| Claim | Test |
|---|---|
| Better data | Demand skill vs persistence on a held-out district (Bareilly), beyond Round 1's 0.9% |
| Risk is calibrated | Reliability curve: steps given 30% risk are unsafe about 30% of the time |
| Volt/VAR value is honest | Table of unsafe steps, peak voltage, transformer loading and reactive loss across R/X values |
| Phase fix works | Unsafe steps and neutral/phase unbalance with vs without reallocation |
| Headroom engine is useful | Agreement with full power-flow replay on held-out streets and days |
| Forecast choice | Same splits, same covariates, same metrics for LightGBM, Chronos-2, TimesFM |
| Honest verdicts | Cases where the answer is "no safe action" are reported with the binding limit |

---

## 12. Risks and unknowns

| Item | Why it matters |
|---|---|
| No open Indian rooftop generation or LV topology data | Street stays a benchmark; say so openly |
| CEEW meters are single-phase with no phase labels | Phase assignment is simulated; cannot be validated on Indian data |
| UP ±6% rule rests on the CEEW citation | Confirm against the Supply Code text |
| NREL India report body, BIS annexure, CEA 2019 DG regulations unread | IEEE 1547 settings for India need confirmation |
| Open-Meteo API terms | Code is AGPL; API terms for commercial use unchecked |
| ppOPF and the Hosting-Capacity repo licences | Use as references only |
| About 45 sources are snippet-only | Do not cite them as findings without a full read |
| Competitor search was limited | "No competitor found" is not proof |

---

## 13. Decisions for the final plan

1. Confirm P0 and P1 scope, and how much of P2 to attempt.
2. Switch engine to power-grid-model, or stay on pandapower and cross-check.
3. Rename S5 and state the UP rule in the Final Document.
4. Email Prayas for raw data; ask a DISCOM or WorkOnGrid about a DT-level sample.
5. How the pitch words the whitespace given section 9.1.

---

## Appendix A: source register

Status key: **R** read in depth by Gemini or by me, **A** official API, **S** snippet only, **X** blocked.

| # | Source | Type | Status |
|---|---|---|---|
| 1 | ADB/GIZ Gaebler 2018, Delhi and Bhopal | Report | R |
| 2 | CEEW 2020 "What smart meters can tell us" | Report | R |
| 3 | CSTEP 2026 feeder-level rooftop impact | Paper | R |
| 4 | Deakin 2019, stochastic hosting capacity (arXiv 1902.08780) | Paper | R |
| 5 | arXiv 2405.20682, phase selection and hosting capacity | Paper | R |
| 6 | arXiv 2204.06372, phase identification | Paper | R |
| 7 | PowerFlowMultiNet (arXiv 2403.00892) | Paper | R |
| 8 | de la Varga (arXiv 2307.16822) | Paper | R |
| 9 | Robust DOE from local voltage (arXiv 2305.13079) | Paper | R |
| 10 | LACE DOE allocation (arXiv 2605.07989) | Paper | R |
| 11 | Gujarat-authored Volt/VAR (JJEE 2026) | Paper | R |
| 12 | Sandia Volt-VAR rooftop study | Paper | R |
| 13 | Prayas eMARC | Dataset page | R |
| 14 | RECON-SL (arXiv 2609.28783) | Dataset paper | R |
| 15 | TERI digital twin for LV grids | Landing page | R |
| 16 | arXiv 2603.23103, open-access tools | Paper | R |
| 17 | arXiv 2410.12438, non-Gaussian voltage risk | Paper | R |
| 18 | arXiv 2604.07106, decision-focused Volt/VAR | Paper | R |
| 19 | arXiv 2605.02340, risk-based PV hosting with generative AI | Paper | R |
| 20 | arXiv 2409.09073, GIS-only topology ILP | Paper | R |
| 21 | arXiv 2604.22077, foundation models for power forecasting | Paper | R |
| 22 | arXiv 2606.07457, physics-synthetic history for PV | Paper | R |
| 23 | Klonari et al. (Mons), probabilistic LV | Chapter abstract | R |
| 24 | Renkema et al. 2024, conformal PV forecasts | Abstract | R |
| 25 | Energetica: Rajasthan phase-balancing order | News | R |
| 26 | Kochi transformer limit (17 Apr 2026) | News | R |
| 27 | WorkOnGrid funding (7 Apr 2026) | News | R |
| 28 | ppOPF repo | Repo | R |
| 29 | Team-Nando Volt-Watt HC repo | Repo | R |
| 30 | wenbowangnrel Hosting-Capacity-Analysis | Repo | R |
| 31 | Team-Nando OE1-Ideal | Repo | R |
| 32 | CEEW dataset record (Dataverse) | Dataset | A |
| 33–76 | 44 GitHub repos (section 7 and earlier batch) | Repos | A |
| 77 | CEEW report raw text (±6% rule, 70% claim) | Report | R (me) |
| 78 | Standard Volt/VAR simulation on our street | Own test | R (me) |
| 79 | NREL India IEEE 1547 report (NREL/TP-6A40-87756) | Report | X (abstract only) |
| 80 | BIS IEEE 1547 drafts | Standard | X |
| 81 | MDPI ERA5 vs IMD stations (Atmosphere 2025) | Paper | X (abstract only) |
| 82 | Pune EV + rooftop solar transformer loss of life | Paper | X (abstract only) |
| 83 | RenewableWatch power-quality article | News | X |
| 84 | IEEE topology paper (Bolognani/IEEE 9641748) | Paper | X (paywalled) |
| 85–129 | About 45 further papers, vendors, datasets and news items seen only in search results (examples: Esau 2023, Arshad 2018, Waterloo predictive Volt/VAR thesis, IIT BHU MPC Volt/VAR, Kenari 2024, LLM-operator paper, NREL assistant concept, Aalborg XAI, Mokhtar 2019, Hokmabad 2025, Oliveira 2019, de Jongh 2023, McDermott and Abate 2019, Hong Kong rooftop dataset, Venios, Edge Electra, Gridspertise, SGS, Bidgely, CYME, Synergi) | Mixed | S |

## Appendix B: method

Searches: web search (standard mode). Reading: Gemini `antigravity/gemini-3.7-flash-high` through a local OmniRoute gateway, one structured summary per source (files in `research/summaries/`). Repo and dataset facts: GitHub API and Harvard Dataverse API. My own checks: CEEW raw-text search and a Volt/VAR simulation on the Round 1 street. Gemini summaries are model-generated and were spot-checked for the claims that carry weight (the ±6% rule, the 70% figure, the repo licences). Counts: 31 sources read in depth, 44 repos plus 1 dataset record via API, 2 own checks, 6 blocked, about 45 snippet-only.
