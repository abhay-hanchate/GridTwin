1) **What the paper does**  
Models a real Indian 11 kV industrial feeder with 23 distribution transformers in DIgSILENT PowerFactory to assess load growth (FY 2030 at 3.3% CAGR) and rooftop solar (80% load offset). It evaluates active/reactive power losses, transformer overloading, and voltage profiles under peak-hour conditions.

2) **Data used + whether public/Indian**  
* **Data:** Single-line network topology, geo-coordinates, conductor lengths, ratings of a 33/11 kV substation ((8 × 1) MVA and (5 × 1) MVA transformers) and 23 DTs (16 stepping down to 440 V, 7 at 11 kV), 8,760 hours of phase currents (FY 2024–25), and monthly DT-level billing energy (kWh).  
* **Public/Indian:** Indian utility data (provided by an Indian DISCOM); not stated if publicly available.

3) **Method + key numbers/results**  
* **Method:** Instantaneous peak-hour load-flow in DIgSILENT PowerFactory (peak instant: 29 April 2024, 9 a.m. IST). Unmetered DT peak loads were allocated via annual energy share, capped at safe loading limits (115% for 2 largest DTs, 95% for others, power factor 0.95), and tested across 3 scenarios (BAU 2025, BAU 2030, BAU 2030 with 80% RTPV offset).  
* **Key numbers/results:**  
  * *BAU 2025:* External grid: 2.2 MW, 0.8 Mvar, 2.3 MVA; System losses: 0.1 MW active, 0.1 Mvar reactive; 6 DTs overloaded (>90% capacity).  
  * *BAU 2030:* External grid: 2.6 MW, 1 Mvar, 2.8 MVA; System losses: 0.1 MW active, 0.2 Mvar reactive; tail-end DT voltage degrades.  
  * *BAU 2030 with RTPV (80% offset):* External grid draw drops to 1.3 MW, 0.5 Mvar, 1.4 MVA; System losses drop to 0.0 MW active, 0.1 Mvar reactive; Overloaded DTs reduce from 6 to 2.

4) **Code/repo link if stated**  
Not stated.

5) **Limits or red flags**  
* Only simulates a single snapshot peak hour (9 a.m.), not a full 8,760-hour time-series power flow.  
* Evaluates solar at 9 a.m., missing midday peak generation and reverse power flow / overvoltage impacts.  
* Low-voltage (440 V) consumer lines and individual rooftop PVs are not modelled; loads and solar are lumped at the DT primary/secondary level.  
* Penetration threshold of 80% is an assumed fixed scenario rather than a mathematically determined hosting capacity limit.  
* Proprietary tool (DIgSILENT PowerFactory) used without open-source models or datasets.

6) **Verdict for GridTwin: useful / not useful and why**  
**Partially useful.** The DT peak allocation heuristic from unmetered billing data and the industrial 11 kV network parameters provide practical Indian context. However, it is not useful for low-voltage (sub-DT) digital twin modeling because it lacks low-voltage network topology, individual solar inverter dynamics, time-series feeder data, and open-source code/data.
