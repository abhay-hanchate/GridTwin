# GridTwin: full research on the problem, the market and the solution

*Compiled 9 October 2026. Every number has a source link or a label. Where sources disagree, both figures are given.*

**How to read the labels**

| Label | Meaning |
|---|---|
| **[Official]** | Government, regulator or Parliament figure (sometimes reported through a news article) |
| **[Report]** | Research organisation (CEEW, Prayas, NREL, IEEFA, ADB) |
| **[Press]** | Trade press or news; usually reliable, but not an official count |
| **[Ours]** | Measured by GridTwin's own engine on real data (reproducible from this repository) |
| **[Estimate]** | Our own back-of-envelope arithmetic; the method is shown, so treat it as an order of magnitude |
| **[Unverified]** | Seen in one weak source only; do not quote as fact |

---

## Contents

1. [The problem in one page](#1-the-problem-in-one-page)
2. [How the problem works (plain physics)](#2-how-the-problem-works-plain-physics)
3. [How big the problem is: places and people](#3-how-big-the-problem-is-places-and-people)
4. [What the government is doing today](#4-what-the-government-is-doing-today)
5. [Why today's fixes are not enough](#5-why-todays-fixes-are-not-enough)
6. [Existing tools and competitor analysis](#6-existing-tools-and-competitor-analysis)
7. [The GridTwin solution](#7-the-gridtwin-solution)
8. [What GridTwin found (measured results)](#8-what-gridtwin-found-measured-results)
9. [Limits, risks and open questions](#9-limits-risks-and-open-questions)
10. [Glossary: every term you need](#10-glossary-every-term-you-need)
11. [Sources](#11-sources)

---

## 1. The problem in one page

**India is putting solar panels on millions of roofs, very fast.** The PM Surya Ghar scheme pays households to install rooftop solar, with a target of **1 crore (10 million) homes** and a budget of **Rs 75,021 crore**. By mid-2026 roughly **40–51 lakh homes** had systems, about **14–18 GW**, and the pace is over **3 lakh new systems a month**.

**The low-voltage grid in Indian neighbourhoods was not built for this.** It was designed for power to flow one way: from the transformer on the pole to the houses. At midday, rooftop panels push power **backwards** into thin, long overhead wires. That raises the voltage, most of all at the far end of the street.

**What goes wrong:**
- **Voltage goes above the legal limit.** In Uttar Pradesh that is 216–244 V (230 V ± 6%). Appliances get stressed, and **solar inverters switch themselves off**, so the household loses the very solar it paid for.
- **Transformers get overloaded or strained by reverse power.** India already loses about **10% of its distribution transformers every year (about 1.3 million units)**, against 1–2% globally.
- **Phases get unbalanced.** Most Indian homes are **single-phase**, so solar piles up on whichever of the three wires (A, B, C) its houses happen to sit on.

**How it's decided today:**
- Utilities ("DISCOMs") approve connections **one application at a time** using **flat rules**, such as "total solar on a transformer must stay below X% of its rating". X ranges from 15% to 100% depending on the state.
- Since February 2024, systems **up to 10 kW skip the technical feasibility study entirely**.
- In Kerala, transformers in Kochi have **hit their 90% limit**, and new solar connections are being refused.

**The gap:** no tool in Indian DISCOM practice tells a field engineer, the evening before:
- *"Tomorrow this street has a 70% chance of unsafe voltage from 8 am"*;
- *"The cheapest fix that keeps it safe all day is X"*, or honestly *"no fix works; you need a bigger wire"*;
- *"Approve this 5 kW request, but on phase B, not A."*

**GridTwin is that tool.** It's a digital copy of the street, built on real Indian smart-meter data, which turns forecasts into those three answers and verifies every answer with physics.

---

## 2. How the problem works (plain physics)

### 2.1 The street
```
 11,000 V line ──▶ [Distribution transformer]  ──▶  long thin overhead wire  ──▶  50-100 homes
   (from the          (steps 11 kV down to              (has resistance:              (each home is wired
    substation)        400 V / 230 V)                     voltage changes along it)     to ONE of 3 phases)
```

### 2.2 Why voltage changes along a wire
Current flowing through a wire with resistance causes a voltage change, **ΔV ≈ (R × P + X × Q) / V**:
- **At night**, homes *draw* power, so voltage **falls** toward the far end.
- **At midday**, rooftop solar *pushes* power back, so voltage **rises** toward the far end.
- **Indian low-voltage wires** are thin aluminium conductors (for example "ACSR Rabbit", 0.55 Ω per km) and often long. They have **high resistance R relative to reactance X**, so the rise is large ([ADB/GIZ study](#11-sources); [Electrical India](https://www.electricalindia.in/rooftop-solar-after-pm-surya-ghar/)).

### 2.3 Why single-phase homes make it worse
A transformer feeds **three phases** (A, B, C). Most homes connect to just one. If solar homes cluster on phase A, phase A's voltage rises much more than an "average" model predicts. Current also returns through the **neutral wire**, which adds more rise. **[Ours]** On the 99-home test street:

| Wiring assumption | Peak voltage |
|---|---|
| Balanced (every home spread evenly; what older tools assume) | 263.1 V |
| Homes spread round-robin across phases | 268.9 V |
| Homes on random phases | 270.5 V |
| Every home on phase A (worst case) | 294.1 V |

### 2.4 The grid side is already high
Before any solar, voltage arriving from the grid is often already near the limit. **[Report]** CEEW measured about 100 homes in Mathura and Bareilly, UP:
- **70% of areas** were outside 230 V ± 6% for more than half the time;
- **half the households** were outside ± 10% for at least a quarter of the time ([CEEW 2020](https://www.ceew.in/publications/what-smart-meters-can-tell-us)).

So solar is often pushing an **already over-voltage** street further.

### 2.5 What happens when voltage is too high
- **Appliances** (fridges, fans, motors, electronics) run hotter, and their life shortens.
- **Solar inverters trip.** They disconnect when they see high voltage, so the home loses free solar power exactly at midday.
- **Transformers** see reverse flow and overload. Utilities respond by **refusing more connections** (Kerala) or by imposing caps.

---

## 3. How big the problem is: places and people

### 3.1 Solar growth (what's driving the problem)

| Number | Value | Source |
|---|---|---|
| Total solar capacity, India | **>168 GW** (Aug 2026); about 34.45 GW added in Jan–Aug 2026 | [Official via SolarQuarter](https://solarquarter.com/2026/09/11/indias-solar-capacity-crosses-168-gw-as-2026-installations-near-34-45-gw-by-august-2026/) |
| Grid-connected **rooftop** solar | **32.59 GW** (31 Aug 2026), up from 30.11 GW (May) | [Official via SolarQuarter](https://solarquarter.com/2026/09/11/indias-solar-capacity-crosses-168-gw-as-2026-installations-near-34-45-gw-by-august-2026/) |
| PM Surya Ghar target | **1 crore households**, about 30 GW; Rs 75,021 crore; up to 300 free units a month | [Official, Cabinet 2024](https://pv-magazine-india.com/2024/02/29/cabinet-approves-scheme-for-installing-rooftop-solar-in-ten-million-households) |
| PM Surya Ghar subsidy | Rs 30,000 (1 kW), Rs 60,000 (2 kW), **Rs 78,000 (3 kW and above)** | [Official, Cabinet 2024](https://www.moneylife.in/article/union-cabinet-okays-rs75000-crore-rooftop-solar-scheme-for-1-crore-households/73561.html) |
| PM Surya Ghar progress, July 2026 | **39.72 lakh systems, about 14.07 GW, 48 lakh households benefiting** | [Official via Energetica](https://www.energetica-india.net/news/pm-surya-ghar-crosses-39-38-lakh-rooftop-solar-installations-capacity-reaches-14-07-gw) |
| PM Surya Ghar progress, Oct 2026 | **50.99 lakh installations, 17,855 MW**, Rs 33,642 crore subsidy released | One report seen only in a search summary; source page not confirmed **[Unverified]**. A separate July 2026 report gives 14,953 MW ([Sarkari Yojana](https://sarkariyojana.com/shorts/pm-surya-ghar-muft-bijli-yojana-reaches-14953-mw-installed-capacity-by-july-2026/)) |
| Pace | More than 3 lakh systems a month (was about 7,000 before the scheme) | [Press](https://www.reslink.org/blogs/pm-surya-ghar-muft-bijli-yojana-the-complete-2026-guide-for-solar-epcs/) |
| Residential rooftop potential | **637 GW** across about 25 crore households | [Report, CEEW](https://www.ceew.in/press-releases/india-has-637-gw-residential-rooftop-solar-energy-potential-for-over-25-crore-households) |

**Uttar Pradesh (where GridTwin's data comes from):**

| Number | Value | Source |
|---|---|---|
| UP rooftop installations | **7,92,959** by Aug 2026 (73,716 in August alone), on track to become the top state | [Press, FPJ](https://www.freepressjournal.in/uttar-pradesh/up-nears-top-spot-in-rooftop-solar-installations-with-792-lakh-connections-under-pm-surya-ghar-scheme) |
| UP rooftop capacity | **2,307.77 MW** (20 Jul 2026, Lok Sabha reply) | [Official via Energetica](https://www.energetica-india.net/news/up-rises-to-second-position-with-6-74-lakh-residential-rooftop-solar-installations-under-pm-surya-ghar) |
| UP target | **11.27 lakh families**; more than 50% achieved | [Press, SolarQuarter](https://solarquarter.com/2026/07/10/uttar-pradesh-crosses-6-50-lakh-rooftop-solar-installations-under-pm-surya-ghar-muft-bijli-yojana/) |
| UP pace | 500 a day (Jun 2025) → about 2,100 a day (May 2026) → about 2,378 a day (Aug 2026) | [Press](https://solarquarter.com/2026/07/10/uttar-pradesh-crosses-6-50-lakh-rooftop-solar-installations-under-pm-surya-ghar-muft-bijli-yojana/) |
| UP electricity consumers | **About 3.46 crore** (2023-24): 87% domestic, 60% rural | [Press, Statesman](https://www.thestatesman.com/business/uppcls-revenue-surges-by-over-17-in-2023-24-1503321183.html) |

### 3.2 The grid that has to absorb it

| Number | Value | Source |
|---|---|---|
| Distribution transformers in India | **About 1.82 crore (18.2 million)**, about 9.44 lakh MVA | [Press, SolarQuarter (CEA/AIDA context)](https://solarquarter.com/2026/05/18/cea-finalizes-standard-transformer-specifications-to-improve-power-distribution-efficiency-across-india/) |
| Transformer failure rate | **About 10% a year, about 1.3 million failures a year** (CEA meeting); Kerala 1.9%; some northern states **above 20%**; private utilities below 0.5%; global 1–2% | [Press, Mercom (CEA)](https://www.mercomindia.com/cea-steps-in-as-distribution-transformer-failures-hit-1-3-million-a-year) |
| Transformers added 2014–Mar 2026 | 6,96,302 (under central schemes) | [Press, Outlook Business](https://www.outlookbusiness.com/spotlight/news-wire/india-adds-113013-mva-grid-transformation-capacity-in-fy26-meets-90-of-cea-target) |
| Smart meters installed (all schemes) | **7.24 crore** (30 Jun 2026) | [Official via T&D India](https://www.tndindia.com/indias-smart-meter-population-at-7-24-crore-parliament/amp/) |
| RDSS smart meters | **5.73 crore installed of 20.33 crore sanctioned (about 28%)**; DT meters: **18.5 lakh of 52.53 lakh** | [Official via Powerline](https://powerline.net.in/2026/07/24/rdss-momentum-measuring-the-impact-of-distribution-sector-reforms/) |

### 3.3 Places already hitting the wall

| Place | What happened | Source |
|---|---|---|
| **Kochi, Kerala** | KSEB limited new domestic solar connections because transformer loading neared the **90%** regulatory ceiling. A 100 kVA transformer is capped at 81 kW of solar. Officials cited the risk of transformer damage from reverse power. | [Press, Solarbytes](https://solarbytes.info/india-bytes/kseb-restricts-kochi-pv-grid-connections-transformer-saturation-bess-11734481); [Kerala Kaumudi](https://keralakaumudi.com/en/kerala/general/kseb-faces-blackout-risk-as-bess-projects-lag-1803470) |
| **Kerala overall** | 2,508 MW solar by May 2026, of which **about 2,036 MW rooftop** | [Policy Circle](https://policycircle.org/opinion/kerala-power-crisis-solar-growth) |
| **Rajasthan** | DISCOM order (Mar 2026): new single-phase rooftop connections only after **phase balancing**, onto the least-loaded phase | Energetica news report, read during the earlier research round (`docs/GridTwin_V2_Master_Research_Document.md`, source 25); not re-checked today |
| **Mathura and Bareilly, UP** | Grid voltage already outside ± 6% for most of the time in 70% of areas, before mass rooftop solar | [Report, CEEW 2020](https://www.ceew.in/publications/what-smart-meters-can-tell-us) |

### 3.4 How many people are affected: an estimate
No official count exists of homes exposed to solar-caused over-voltage. Here is a transparent estimate:

| Step | Number | Basis |
|---|---|---|
| Homes with rooftop solar (mid–late 2026) | about 40–51 lakh | PM Surya Ghar figures above |
| Homes sharing a transformer with them | each low-voltage transformer feeds about 50–100 homes; solar homes are spread across many transformers | typical Indian LV feeder; our test street has 99 |
| **Order of magnitude of homes on streets with rooftop solar** | **several crore (tens of millions)** of people live on streets where solar now flows back | **[Estimate]**: 40–51 lakh solar homes × their neighbours, with heavy overlap; an upper bound, not a count |
| At the 1-crore target | about 30 GW on residential streets | official target |

**Honest caveat:** being on such a street does **not** mean that household suffers over-voltage. It depends on how many neighbours have solar, the wire, the phase, and how high the grid voltage already is. That is exactly why a street-by-street tool is needed.

### 3.5 Economic cost (what's at stake)
- **Transformers:** about 1.3 million failures a year **[Press]**. A failed transformer means an outage for every home on it, plus replacement cost.
- **Lost solar:** when inverters trip on over-voltage, households lose the generation the subsidy paid for. Elsewhere, utilities fall back on blunt export limits. In South Australia the alternative to smart limits was a **flat 1.5 kW cap** ([ARENA / SAPN](https://www.energynetworks.com.au/news/energy-insider/2021-energy-insider/innovation-allows-more-sun-onto-sas-electricity-grid/)).
- **Subsidy at risk:** Rs 75,021 crore of public money is going into rooftop systems whose output depends on the local grid accepting it.

---

## 4. What the government is doing today

| Measure | What it does | Helps with | Doesn't solve |
|---|---|---|---|
| **PM Surya Ghar** (Feb 2024; Rs 75,021 crore) | Subsidises 1 crore rooftop systems; national portal for applications | Adoption | Grid impact; it *creates* the pressure |
| **Electricity (Rights of Consumers) Amendment Rules 2024** (notified 22 Feb 2024) | Systems **up to 10 kW** are accepted **without a technical feasibility study**; for larger systems the study must finish in **15 days**, else approval is deemed given | Speed of approval | **Nobody checks the cumulative effect** of many small systems on one transformer ([Mercom](https://mercomindia.com/rooftop-solar-10-kw-exempted-feasibility-study-mandate); [Powerline](https://powerline.net.in/2024/02/26/mop-notifies-electricity-rights-of-consumers-amendment-rules-2024/)) |
| **State transformer caps** | Total rooftop solar per transformer limited to a % of its rating, first-come-first-served | A crude safety margin | Ignores the wire, the phase, the grid voltage and the time of day. Caps vary widely: Kerala 90%, many states about 80%, Telangana draft 50%, Haryana 50% (or 15% in another source), Delhi 20%, UP 25% **[Unverified]**, Himachal 30%, Bihar and Jharkhand up to 100%, Tamil Nadu 90% overall with 30% per phase ([CEEW policy review](https://www.ceew.in/publications/demystifying-india-rooftop-solar-policies); [Power Peak Digest](https://powerpeakdigest.com/variation-in-rooftop-solar-regulations-across-indian-states-a-framework-comparison/)) |
| **RDSS** (Revamped Distribution Sector Scheme; **Rs 3,03,758 crore**, GBS Rs 97,631 crore; sunset moved to **31 Mar 2028**) | Smart meters (20.33 crore sanctioned), loss reduction, infrastructure | Data: meters at homes, transformers and feeders | Data alone doesn't decide anything. Only about 28% of meters are installed ([Powerline](https://powerline.net.in/2026/07/24/rdss-momentum-measuring-the-impact-of-distribution-sector-reforms/)) |
| **IS 18968** (BIS adoption of **IEEE 1547-2018**, July 2023) | Smart-inverter standard with India annex; **includes Volt-VAR and Volt-Watt** | Inverters that can help hold voltage | **Binding only once embedded in CEA regulations** ([ISGF](https://indiasmartgrid.org/isgf/public/banner_img/1776667303qPWdKcjk4VE6se1x1gWKy2BlbeZ8DsagXsLtHUCW.pdf); [NREL 2024](https://docs.nrel.gov/docs/fy24osti/87756.pdf)) |
| **CEA Technical Standards for Connectivity of Distributed Generation** (2013, amended 2019) | Connection standards at or below 33 kV | Baseline rules | No published Volt-VAR requirement found for rooftop **[Unverified]** |
| **Supply-voltage rules** | IE Rules 1956 r.54 and state supply codes (UP: 230 V ± 6%); a 2022 CEA meeting reportedly moved toward 230/400 V ± 10%, tightening to ± 6% later | Defines "safe" | Not monitored street by street |
| **Transformer upgrades and standard specs** (CEA, May 2026) | Standardised transformer specifications; about 6.96 lakh transformers added since 2014 | Replaces weak assets | Expensive and slow; doesn't say *which* transformer needs it first |
| **Battery pilots** (KSEB community BESS) | Absorb midday surplus | Local relief | Officials say storage alone can't fully solve transformer saturation ([Solarbytes](https://solarbytes.info/india-bytes/kseb-restricts-kochi-pv-grid-connections-transformer-saturation-bess-11734481)) |
| **Digital-twin programmes** (JVVNL "DUET" with GEAPP and Edge Electra; Rajasthan/ISA; MSEDCL) | Map grid assets, simulate power flow at utility scale | Visibility | Public descriptions don't mention low-voltage rooftop risk, ranked fixes or connection decisions ([Powerline](https://powerline.net.in/2026/01/15/jvvnl-efforts-to-enhance-jaipurs-power-distribution-efficiency/)) |

---

## 5. Why today's fixes are not enough

1. **Flat caps are blind to physics.** The same 80% cap is too loose on a long, thin rural wire and too strict on a short, thick urban one. **[Ours]** On one street the far end can take **4–7 kW** more while the transformer end takes **60+ kW**.
2. **The 10 kW exemption hides cumulative harm.** Each small system is "safe" alone, but together they aren't. **[Ours]** A harmless 2 kW request on a street with four 9.5 kW exempt systems on one phase made **41** time-steps worse.
3. **Nobody looks at phases.** Rajasthan has started ordering phase balancing, but by hand.
4. **No day-ahead warning.** Engineers learn about problems from complaints and failures.
5. **Data without decisions.** RDSS installs meters, but nothing turns them into "do this tomorrow".
6. **Smart-inverter rules aren't enforced yet.** IS 18968 exists, but until CEA embeds it, inverters may ship with the smart functions switched off.

---

## 6. Existing tools and competitor analysis

### 6.1 Categories of tools that exist

| Category | Examples | What they do | Gap for an Indian DISCOM's LV rooftop problem |
|---|---|---|---|
| **Engineering power-flow software** (licensed) | CYME (Eaton), Synergi (DNV), PowerFactory (DIgSILENT), PSS SINCAL (Siemens) | Detailed studies by expert engineers | Expensive; needs specialists; study-by-study, not a daily answer |
| **Hosting-capacity engines** | **EPRI DRIVE** (inside CYME; used for New York hosting-capacity maps, about 230 feeders at one utility) | Max solar per feeder | Heuristic, feeder-level; not day-ahead risk; not built on Indian single-phase LV data ([EPRI Journal](https://eprijournal.com/?p=5644); [CIGRE paper](https://cigre-usnc.org/wp-content/uploads/2018/10/4B_2_C6_Van-Leuven.pdf)) |
| **Open-source engines** | OpenDSS (EPRI), pandapower, power-grid-model, GridLAB-D | Free power-flow calculators | Libraries, not products; you build the decision layer yourself (GridTwin uses pandapower and power-grid-model) |
| **Grid-planning platforms with automated connection checks** | **envelio Intelligent Grid Platform** (Germany): Bayernwerk processes about **10,000 connection requests a month**; E.ON about **410,000 in 2024**; Elektrilevi self-service portal for systems up to 15 kW; "Grid Connection Navigator" (Dec 2025) | Instant connection decisions from a grid model | European grids and data; not available or adapted for Indian DISCOMs; no day-ahead risk ([envelio](https://envelio.com/us/application-online-connection-check); [news](https://us.envelio.com/news/envelio-expands-intelligent-grid-platform-with-the-grid-connection-navigator)) |
| **LV digital twins** | Siemens Gridscale X "LV Insights X", Adaion (UFD, Spain: 52 LV networks) | LV network visibility and hosting capacity | Incumbent and European; heavy integration |
| **Dynamic operating envelopes** (export limits that change by time and place) | **SA Power Networks "flexible exports"** (Australia): up to 10 kW export, set day-ahead in 5-minute steps; exports at the full 10 kW about **98%** of the time vs a flat 1.5 kW alternative | Lets more solar connect safely | Needs smart inverters and comms; Australian market ([ENA](https://www.energynetworks.com.au/news/energy-insider/2021-energy-insider/innovation-allows-more-sun-onto-sas-electricity-grid/); [IEEFA](https://ieefa.org/sites/default/files/2024-12/BN_How%20rapid%20implementation%20of%20flexible%20exports%20could%20maximise%20rooftop%20solar%20_Nov24.pdf)) |
| **DERMS / ADMS** (real-time control) | Hitachi Energy, Schneider EcoStruxure, GE (Opus One), Smarter Grid Solutions | Real-time DER control in control rooms | Large IT projects; need SCADA and comms that most Indian LV networks lack |
| **Utility analytics** | Bidgely, WorkOnGrid (Bengaluru, Rs 22.5 crore round, Apr 2026), Prescinto | Meter analytics, theft, asset health | Not LV voltage physics |

### 6.2 India-specific players (closest overlap)

| Player | What is publicly stated | Overlap with GridTwin |
|---|---|---|
| **JVVNL "DUET"** (Jaipur; GEAPP + Edge Electra) | Digital twin of the network: 1.4 million assets mapped toward 4.5 million; power-flow simulation; stress forecasting; PM-KUSUM plants | **Highest.** Same buyer type and the same "twin" idea, but no stated LV rooftop risk, ranked fixes, phases or connection checks ([Powerline, Jan 2026](https://powerline.net.in/2026/01/15/jvvnl-efforts-to-enhance-jaipurs-power-distribution-efficiency/)) |
| **MSEDCL + GEAPP** (Statement of Intent, Oct 2025) | AI/ML digitalisation, load-flow, DER integration | High (same programme spreading) |
| **Rajasthan / ISA digital twin** | Real-time replica with load-flow and forecasting; vendor not public | High, unknown scope |
| **NREL + TANGEDCO "EMeRGE"** (2021) | Framework and tool to assess rooftop solar impact on Tamil Nadu feeders, including **hosting capacity** and inverter functions | **Indian prior art**: a study and tool, not a day-ahead product ([NREL report](https://www.nrel.gov/docs/fy21osti/78114.pdf)) |
| **Venios + TERI at BRPL Delhi** | Cloud twin pilot; DER impact analysis | High on paper; no published results |
| **Tata Power-DDL** collaborations (AutoGrid demand response; CEEW MoU on rooftop share per transformer) | Pilots and research | Adjacent |

### 6.3 Feature comparison

| Capability | Flat state caps | EPRI DRIVE / CYME | envelio | SA Power Networks DOE | DUET (JVVNL) | **GridTwin** |
|---|---|---|---|---|---|---|
| Built on Indian smart-meter data | n/a | No | No | No | Partly (assets) | **Yes (CEEW, Mathura and Bareilly)** |
| Single-phase homes and phase imbalance | No | Partly | Partly | Yes (per site) | Not stated | **Yes (unbalanced engine)** |
| State voltage rule (UP ± 6%) with source | Implicit | Configurable | Configurable | n/a | Not stated | **Yes (rule library with sources)** |
| **Day-ahead probability of unsafe voltage** | No | No | No | Envelope only | Stress forecast (unclear) | **Yes (100 scenarios, calibrated where it passes)** |
| **Ranked, physics-verified fixes** | No | Manual studies | No | No | Not stated | **Yes (tournament of about 40 options)** |
| Phase reallocation as a fix | No | Manual | No | No | No | **Yes (optimiser)** |
| Per-house export limits | No | No | No | **Yes** | No | **Yes** |
| Honest "no safe action" + what's still needed | No | No | No | No | No | **Yes** |
| Connection check incl. cumulative exempt systems | Cap only | Study | **Yes** | n/a | Not stated | **Yes (phase-aware)** |
| Cost | Free | Licensed | Licensed | In-house | Grant-funded | Open-source stack |

### 6.4 Positioning (honest)
- **GridTwin isn't first** at "digital twin", "hosting capacity" or "connection decisions". envelio automates connections in Europe, NREL did hosting capacity in Tamil Nadu, and JVVNL runs a twin.
- **What we didn't find anywhere public:** for **Indian single-phase rooftop solar on high-resistance LV wire**, a tool that combines a **day-ahead probability**, **ranked physics-verified fixes including phase moves and export limits**, a **state-rule verdict that admits when nothing works**, and a **phase-aware connection check that counts exempt systems**.
- **Best framing:** a **low-voltage rooftop decision layer** that can sit **on top of** an asset twin like DUET, as a partner rather than a rival.
- "Not stated publicly" doesn't mean "not built". Confirm with DISCOM contacts before claiming a gap.

---

## 7. The GridTwin solution

### 7.1 Idea: "AI predicts, physics decides"
- **AI forecasts** tomorrow's sunshine (five weather models), household demand and grid voltage.
- **Physics** (power-flow equations) calculates the voltage on every wire for every 15 minutes.
- **No AI output alone ever approves a fix or a connection.**

### 7.2 What it answers

| Question | Who asks | GridTwin output |
|---|---|---|
| Will tomorrow be unsafe? | Control room, every evening | Chance of unsafe voltage for each 15 minutes, expected unsafe hours with a range, watch (20%) and act (50%) alerts |
| What should we do? | Same engineer | Ranked fixes, all verified on every scenario: least solar wasted, fewest operations, least battery use, widest safety margin. Or "No safe action", plus the limit that blocks it and what's still needed |
| Can we approve this connection? | Planning engineer | Approve / approve with conditions / refuse, the phase to use, the binding limit, and whether it's still safe **counting exempt systems already connected** |
| How much more solar fits? | Planner | Headroom per phase and location; probabilistic hosting capacity |

### 7.3 How it works (pipeline)
```
Data (CEEW meters, weather) ─▶ Forecasts (solar v2, demand, grid voltage)
   ─▶ Scenario generator (100 correlated "tomorrows", Gaussian copula)
   ─▶ Physics engine (power-grid-model; each home on its own phase; IEEE 1547 inverters)
   ─▶ Risk / Fix tournament / Planning tools ─▶ API v2 ─▶ Dashboard + evening report
```

### 7.4 Fixes it can test
- **Transformer tap:** a seasonal knob that lowers the whole street's voltage by 2.5% per step.
- **Smart inverters (IEEE 1547 Volt/VAR, Volt/Watt):** inverters absorb reactive power or trim output only when their own voltage is high.
- **Export caps:** uniform, or **per-house limits for each time step**.
- **Phase reallocation:** move some homes to a less-loaded phase (chosen by an optimiser).
- **Feeder switching:** reroute through a tie switch, keeping the network radial.
- **Community battery:** sized by sweeping options.

### 7.5 Honesty rules built in
- Every number carries **observed / modeled / benchmark**.
- **Failed quality gates are shown**, never hidden.
- Solver failure counts as **unsafe**.
- The UP rule is cited to its source with a verification level.

---

## 8. What GridTwin found (measured results)

All **[Ours]**, reproducible from this repository (`data/results/results.json`, `docs/DECISIONS.md`).

| Finding | Number |
|---|---|
| Engine accuracy vs the trusted reference (pandapower) | within **0.001 V**; about **500–800× faster** (gate G1) |
| Single-phase homes vs the balanced model | peak **268.9 V vs 263.1 V**; 31 vs 26 unsafe steps |
| Sunny demo day (15 May 2025), ± 10% | **ACT** from 06:15; about **9 h** unsafe (7.0–11.8 h); fix: **tap +1 with standard Volt/VAR** |
| Same day, UP ± 6% rule | **No safe action.** The closest fix leaves 25 unsafe steps; evenings fall to 208 V against a 216 V floor; it needs about 8 V more at the far end (heavier conductor or closer transformer) |
| Cloudy day (5 Aug 2025), ± 10% | **OK**: standard Volt/VAR alone is enough |
| Hosting capacity, sunny day | Without a fix, 20–50% of homes can add solar; **with standard Volt/VAR, 80–100%** |
| Far end vs transformer end | far end 4–7 kW of extra solar, transformer end 60+ kW: **place and phase decide** |
| The exempt-system trap | a harmless 2 kW request plus four 9.5 kW exempt systems on one phase made 41 steps worse |
| Live tomorrow (10 Oct 2026) | ACT from 07:30, about 9 h unsafe (3.7–14.3 h), using live forecasts |
| Risk calibration (G8) | ± 10%: slightly better than the historical average after recalibration (+2.3% skill); UP ± 6%: not calibrated, because almost every step is unsafe anyway |

---

## 9. Limits, risks and open questions

- **The street layout is a benchmark** (German SimBench topology with Indian IS 398 conductors), not a surveyed Indian feeder. Real feeder maps would come from a DISCOM (GridTwin can import them from CSV).
- **Meter data is 2019–2021**, about 100 homes in two UP districts. Patterns may have shifted.
- **Wire reactance and zero-sequence values are estimates**; their effect is reported (peak moves about 4 V).
- **Risk percentages are only weakly calibrated** (gate G8).
- **Not verified:** the UP 25% transformer cap, the October 2026 PM Surya Ghar total, and whether CEA has embedded IS 18968's Volt-VAR rules.
- **The weather API is free only for non-commercial use**; a DISCOM deployment needs a licensed source (gate G6).
- **Open questions for DISCOMs:** Do they already track over-voltage complaints by transformer? Is phase information recorded per connection? What do DUET and other twins actually compute?

---

## 10. Glossary: every term you need

### Electricity basics
| Term | Meaning |
|---|---|
| **Voltage (V)** | The electrical "pressure" pushing current. Indian homes get **230 V** single-phase (400 V between phases). |
| **Current (A, ampere)** | How much electricity flows. |
| **Power (W, kW)** | Rate of energy use: voltage × current (for simple loads). 1 kW = 1,000 W. |
| **Energy (kWh, a "unit")** | Power over time: a 1 kW load for 1 hour = 1 kWh = **1 unit** on the bill. |
| **Resistance (R, Ω)** | How much a wire resists current; causes voltage drop or rise and heat. |
| **Reactance (X, Ω)** | AC-only "resistance" from magnetic and electric fields. The **R/X ratio** decides whether reactive power can control voltage well. |
| **Active power (P, kW)** | Power that does useful work. |
| **Reactive power (Q, kvar)** | Power that sloshes back and forth; does no work but affects voltage. |
| **Apparent power (S, kVA)** | Combination of P and Q; transformers and inverters are rated in **kVA**. |
| **Power factor** | P ÷ S; 1.0 is ideal. Homes in GridTwin are modelled at 0.95. |
| **Per unit (pu)** | Voltage as a fraction of normal: 1.0 pu = 230 V; 1.06 pu = 243.8 V. |
| **AC / 50 Hz** | India's grid alternates 50 times a second. |

### The grid
| Term | Meaning |
|---|---|
| **Generation → Transmission → Distribution** | Power plants → high-voltage lines (220–765 kV) → local networks (33 kV, 11 kV, 400/230 V). |
| **Substation** | Where voltage is stepped down (for example 33 kV → 11 kV). |
| **Feeder** | A circuit leaving a substation or transformer to supply an area. |
| **HV / MV / LV** | High / medium / low voltage. GridTwin works on **LV** (the 400/230 V street). |
| **Distribution transformer (DT)** | The box on a pole or plinth that steps **11 kV down to 400/230 V** for 50–100+ homes. Rated in kVA (63, 100, 160, 250 kVA...). |
| **Transformer loading** | How hard the transformer works, as % of its rating; above 100% it overheats. |
| **Tap changer / tap** | A switch on the transformer that adjusts output voltage in steps (about 2.5% each). Off-load taps are set seasonally by hand. |
| **Three-phase / single-phase** | The transformer feeds three wires (phases A, B, C) plus neutral. Most homes connect to **one** phase. |
| **Phase imbalance** | When one phase carries much more load or solar than the others; raises voltage on that phase and current in the neutral. |
| **Neutral** | The return wire; carries the imbalance current. |
| **Conductor / ACSR** | The wire. ACSR = aluminium conductor steel reinforced. Indian sizes: Squirrel, Weasel, **Rabbit**, Racoon, Dog (IS 398 standard). |
| **Radial network** | Tree-shaped: one path from transformer to each home (typical in India). |
| **Overhead line** | Wires on poles (common in India; higher resistance than underground cable). |

### Rooftop solar
| Term | Meaning |
|---|---|
| **Rooftop solar / RTS / PV** | Photovoltaic panels on a roof turning sunlight into electricity. |
| **kWp (kilowatt-peak)** | Panel rating in full sun; a 3 kWp system makes about 3 kW at best, typically 12–15 kWh a day in India. |
| **Inverter** | Converts the panels' DC to AC for the home and grid; trips off if grid voltage is out of range. |
| **Smart inverter** | An inverter with grid-support functions, for example Volt/VAR and Volt/Watt. |
| **Net metering** | One meter counts import minus export; exports earn credit. |
| **Gross metering** | All solar sold to the utility at a set price; the home buys its own use separately. |
| **Export** | Solar not used at home flows into the grid. |
| **Reverse power flow** | Power flowing from the street **back up** through the transformer. |
| **Curtailment** | Deliberately reducing solar output (wastes free energy). |
| **Export limit / cap** | A maximum the home may push into the grid. |
| **Dynamic operating envelope (DOE)** | An export limit that changes by time and place, set from grid conditions (Australia). |
| **Hosting capacity** | How much solar a part of the grid can take before something goes wrong (voltage, overload, protection). |
| **Headroom** | The remaining hosting capacity at a specific place and phase. |

### Voltage control
| Term | Meaning |
|---|---|
| **Over-voltage / under-voltage** | Voltage above / below the allowed band. |
| **Voltage band / rule** | The legal range. UP: 230 V ± 6% = 216–244 V. Also ± 10% = 207–253 V. |
| **Voltage rise** | Increase in voltage along the wire caused by solar export. |
| **Volt/VAR** | Smart-inverter mode: absorb reactive power when voltage is high (IEEE 1547 Category B: up to 44% of rating at 1.08 pu). |
| **Volt/Watt** | Smart-inverter mode: reduce output above 1.06 pu, down to 20% of rating at 1.10 pu. |
| **IEEE 1547-2018 / IS 18968** | The international smart-inverter standard and India's adopted version. |
| **VUF (voltage unbalance factor)** | How unequal the three phase voltages are. |
| **Binding limit** | The specific limit that stops a fix from working (for example "voltage fell to 208 V against a 216 V limit"). |

### Institutions and schemes
| Term | Meaning |
|---|---|
| **DISCOM** | Distribution company (for example UPPCL in UP, KSEB in Kerala, JVVNL in Jaipur). |
| **MNRE** | Ministry of New and Renewable Energy (runs PM Surya Ghar). |
| **MoP** | Ministry of Power. |
| **CEA** | Central Electricity Authority: national technical regulator and standards body. |
| **SERC / UPERC / KSERC** | State electricity regulatory commissions (UP's is UPERC). |
| **BIS** | Bureau of Indian Standards. |
| **PM Surya Ghar Muft Bijli Yojana** | Rooftop solar subsidy for 1 crore homes (2024). |
| **RDSS** | Revamped Distribution Sector Scheme: Rs 3.04 lakh crore distribution reform, including smart meters. |
| **PM-KUSUM** | Scheme for solar pumps and farm-level solar plants. |
| **Supply Code** | State rules on supply quality, including the voltage band. |
| **CEEW / Prayas / NREL / EPRI** | Research organisations (CEEW: Indian think tank; Prayas: Pune energy group; NREL: US national lab; EPRI: US utility research institute). |

### GridTwin's methods
| Term | Meaning |
|---|---|
| **Digital twin** | A computer copy of a real system that you can test changes on safely. |
| **Power flow (load flow)** | Solving the grid's equations to find every voltage and current. |
| **pandapower / power-grid-model** | Open-source power-flow engines; the second is the fast batch engine GridTwin uses. |
| **Balanced vs unbalanced (asymmetric) model** | Assumes homes are spread evenly over phases, vs models each home on its real phase. |
| **Zero sequence** | The part of current that returns through neutral and earth; matters for single-phase homes. |
| **Scenario** | One possible version of tomorrow (sun, demand, grid voltage). |
| **Gaussian copula** | Statistical method that keeps scenarios realistically correlated (for example heavy-demand days have lower grid voltage). |
| **Quantiles P10 / P50 / P90** | Forecast range: 10% chance below P10, median P50, 10% chance above P90. |
| **P(unsafe)** | Share of scenarios in which a 15-minute step is unsafe. |
| **Watch / act** | Alert levels at 20% / 50% chance of unsafe. |
| **Calibration / Brier score** | Whether "60%" really happens 60% of the time; Brier measures probability accuracy (lower is better). |
| **Isotonic recalibration** | Adjusting predicted probabilities to match observed frequencies. |
| **Conformal prediction** | Method that widens forecast ranges so they cover the truth the stated share of the time. |
| **LightGBM** | Fast machine-learning model (gradient-boosted trees) used for forecasts. |
| **NWP** | Numerical weather prediction (weather-forecast models: GFS, ICON, ECMWF...). |
| **MAE / WIS / CRPS** | Forecast error measures (average error; interval score; full-distribution score). |
| **Fix tournament** | Trying all candidate fixes and ranking the safe ones. |
| **Lexicographic ranking** | Rank by the first criterion, break ties with the second, and so on. |
| **CP-SAT** | Google OR-Tools optimiser used to choose phase moves. |
| **Bake-off** | Pre-registered fair comparison of methods; the numbers pick the winner. |
| **Gate (G1–G8)** | A measured pass/fail check before a method is trusted. |
| **Nightly run** | Precomputing tomorrow's answers each evening so the dashboard is instant. |
| **API** | The web addresses the dashboard calls to get answers. |
| **Provenance** | Label saying where a number came from: observed, modeled or benchmark. |

---

## 11. Sources

**Official, regulatory and government**
- PM Surya Ghar approval (Cabinet, Feb 2024): [pv magazine India](https://pv-magazine-india.com/2024/02/29/cabinet-approves-scheme-for-installing-rooftop-solar-in-ten-million-households), [Moneylife](https://www.moneylife.in/article/union-cabinet-okays-rs75000-crore-rooftop-solar-scheme-for-1-crore-households/73561.html), [PIB](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2081250&reg=48&lang=2)
- PM Surya Ghar progress: [Energetica (14.07 GW, Jul 2026)](https://www.energetica-india.net/news/pm-surya-ghar-crosses-39-38-lakh-rooftop-solar-installations-capacity-reaches-14-07-gw), [News on AIR](https://newsonair.gov.in/pm-surya-ghar-muft-bijli-yojana-achieves-10-lakh-rooftop-solar-installations)
- Solar capacity: [SolarQuarter, MNRE data Aug 2026](https://solarquarter.com/2026/09/11/indias-solar-capacity-crosses-168-gw-as-2026-installations-near-34-45-gw-by-august-2026/), [JMK Research FY2026](https://jmkresearch.com/india-installs-record-44-gw-solar-and-6-gw-wind-capacity-in-fy2026/)
- UP progress: [Free Press Journal](https://www.freepressjournal.in/uttar-pradesh/up-nears-top-spot-in-rooftop-solar-installations-with-792-lakh-connections-under-pm-surya-ghar-scheme), [SolarQuarter](https://solarquarter.com/2026/07/10/uttar-pradesh-crosses-6-50-lakh-rooftop-solar-installations-under-pm-surya-ghar-muft-bijli-yojana/), [Energetica](https://www.energetica-india.net/news/up-rises-to-second-position-with-6-74-lakh-residential-rooftop-solar-installations-under-pm-surya-ghar)
- Rights of Consumers Amendment 2024: [Mercom](https://mercomindia.com/rooftop-solar-10-kw-exempted-feasibility-study-mandate), [Powerline](https://powerline.net.in/2024/02/26/mop-notifies-electricity-rights-of-consumers-amendment-rules-2024/), [MSEDCL auto-approval order](https://www.mahadiscom.in/ismart/media/AUTO%20APPROVAL%2010.pdf), [JBVNL office order](https://jbvnl.co.in/SOLAR/Office%20Order%20for%20waiver%20of%20Feasibility%20study%20upto%2010%20KW%20RTS.pdf)
- RDSS and smart meters: [Powerline Jul 2026](https://powerline.net.in/2026/07/24/rdss-momentum-measuring-the-impact-of-distribution-sector-reforms/), [T&D India (7.24 crore)](https://www.tndindia.com/indias-smart-meter-population-at-7-24-crore-parliament/amp/), [Ministry of Power overview](https://powermin.gov.in/en/content/overview-5)
- Transformers: [Mercom (1.3 million failures a year)](https://www.mercomindia.com/cea-steps-in-as-distribution-transformer-failures-hit-1-3-million-a-year), [SolarQuarter (1.82 crore DTs)](https://solarquarter.com/2026/05/18/cea-finalizes-standard-transformer-specifications-to-improve-power-distribution-efficiency-across-india/), [Outlook Business](https://www.outlookbusiness.com/spotlight/news-wire/india-adds-113013-mva-grid-transformation-capacity-in-fy26-meets-90-of-cea-target)
- Smart-inverter standards: [NREL India IEEE 1547 report](https://docs.nrel.gov/docs/fy24osti/87756.pdf), [ISGF roadmap](https://indiasmartgrid.org/isgf/public/banner_img/1776667303qPWdKcjk4VE6se1x1gWKy2BlbeZ8DsagXsLtHUCW.pdf), [CEA connectivity regulations 2013](https://www.cbip.org/cearegulations/CEA%20DATA/Connectivity/Connectivity%20Regulation/Con%20Coneectivity%20Regulations%202013.pdf)
- UP voltage rule: CEEW 2020 report section 4.2 (UPERC 2005); [Indian Electricity Rules 1956 r.54](https://indiankanoon.org/doc/68250522/)

**Research reports**
- [CEEW, What Smart Meters Can Tell Us (2020)](https://www.ceew.in/publications/what-smart-meters-can-tell-us)
- [CEEW, Demystifying India's rooftop solar policies](https://www.ceew.in/publications/demystifying-india-rooftop-solar-policies)
- [CEEW, 637 GW residential rooftop potential](https://www.ceew.in/press-releases/india-has-637-gw-residential-rooftop-solar-energy-potential-for-over-25-crore-households)
- [NREL + TANGEDCO, DER integration framework (2021)](https://www.nrel.gov/docs/fy21osti/78114.pdf); [EMeRGE brochure](https://www.nrel.gov/docs/fy21osti/79996.pdf)
- [Prayas Energy Group, supply quality monitoring (ESMI/eMARC)](https://energy.prayaspune.org/our-work/article-and-blog/electricity-supply-quality-issues-persist)
- [IEEFA, flexible exports (Australia)](https://ieefa.org/sites/default/files/2024-12/BN_How%20rapid%20implementation%20of%20flexible%20exports%20could%20maximise%20rooftop%20solar%20_Nov24.pdf)
- ADB/GIZ Delhi and Bhopal rooftop integration study (2018); see `docs/GridTwin_V2_Master_Research_Document.md`, Appendix A

**Press on grid impact**
- [Electrical India: Rooftop solar after PM Surya Ghar](https://www.electricalindia.in/rooftop-solar-after-pm-surya-ghar/)
- [Construction World: rooftop boom meets grid reality](https://www.constructionworld.in/energy-infrastructure/power-and-renewable-energy/indias-rooftop-solar-boom-meets-grid-reality-check/93832)
- [Solarbytes: Kochi transformer limits](https://solarbytes.info/india-bytes/kseb-restricts-kochi-pv-grid-connections-transformer-saturation-bess-11734481); [Kerala Kaumudi](https://keralakaumudi.com/en/kerala/general/kseb-faces-blackout-risk-as-bess-projects-lag-1803470); [Policy Circle](https://policycircle.org/opinion/kerala-power-crisis-solar-growth)
- [Power Peak Digest: state rooftop regulations compared](https://powerpeakdigest.com/variation-in-rooftop-solar-regulations-across-indian-states-a-framework-comparison/)

**Competitors and tools**
- [EPRI DRIVE (EPRI Journal)](https://eprijournal.com/?p=5644); [CYME + EPRI](https://cyme.com/software/cymeepri); [CIGRE comparison paper](https://cigre-usnc.org/wp-content/uploads/2018/10/4B_2_C6_Van-Leuven.pdf); [SDG&E EPIC report](https://www.sdge.com/sites/default/files/EPIC-1%20Project%204_Module%203_Final%20Report_0.pdf)
- [envelio online connection check](https://envelio.com/us/application-online-connection-check); [Grid Connection Navigator](https://us.envelio.com/news/envelio-expands-intelligent-grid-platform-with-the-grid-connection-navigator); [Elektrilevi case study](https://us.envelio.com/hubfs/website-downloadables/envelio_Case_Study_Elektrilevi_EN.pdf?hsLang=en)
- [SA Power Networks flexible exports (ENA)](https://www.energynetworks.com.au/news/energy-insider/2021-energy-insider/innovation-allows-more-sun-onto-sas-electricity-grid/); [ARENA trial](https://arena.gov.au/news/pioneering-rooftop-solar-trial-to-prove-benefits-for-customers-retailers-and-networks-from-energy-transition)
- [JVVNL DUET (Powerline)](https://powerline.net.in/2026/01/15/jvvnl-efforts-to-enhance-jaipurs-power-distribution-efficiency/)
- Earlier competitor evidence (Siemens, Adaion, Venios, WorkOnGrid, DERMS vendors): `docs/GridTwin_V2_Master_Research_Document.md`, sections 8 and A2

**GridTwin's own evidence**
- `data/results/results.json` (gates G1–G8), `docs/DECISIONS.md` (bake-offs), `docs/DEMO_SCRIPT.md`, `data/results/v2/` (demo results)
