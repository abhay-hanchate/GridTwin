**1) What the paper does**  
Evaluates the voltage management effectiveness of smart inverter Volt-Var Curve (VVC) control on feeders with distributed rooftop PV and assesses the grid voltage risks associated with tampered/malicious VVC inverter settings during cyber-attacks.

**2) Data used + whether public/Indian**  
* EPRI K1 feeder (12 kV, 7 km, 4.8 MW max load, 321 loads) and an actual "Unnamed" feeder (12 kV, 4.6 km, 7.9 MW max load, 39 loads).  
* Commercial and residential hourly building load profiles and TMY3 solar data for Albuquerque, New Mexico (from US DOE EERE).  
* Public/Indian: DOE load profiles are public; none of the data is Indian (all US-based).

**3) Method + key numbers/results**  
* **Method:** 100-iteration stochastic hosting capacity simulations in OpenDSS varying load (30% to 120%) and PV adoption (10% to 50% of loads; PV sized to 1.35 times peak load). Evaluated four control modes comparing normal VVC (absorbing up to −44% reactive power at 1.05 pu) versus malicious VVC (injecting +99% reactive power at 1.05 pu).  
* **Key numbers/results:**  
  * Distributed rooftop PV caused very little voltage rise, and uncontrolled voltages never exceeded ANSI thresholds (0.95 pu to 1.05 pu).  
  * VVC on distributed rooftop PV had an "insignificant role" in managing voltage; on secondary lines, the low reactive power resulted in negligible voltage change (e.g., inverters absorbed only 1.45 kVar across the K1 feeder path).  
  * Malicious VVC tampering caused "little to no harm" and resulted in no voltage limit violations.  
  * In contrast, for large-scale centralized PV (two 750 kW systems, 1500 kW total at 20% load), VVC was effective, lowering voltage from 1.051 pu to 1.043 pu (absorbing 264 kVar) without regulators, and to 1.034 pu (absorbing 455 kVar) with regulators.  
  * Specific resistive feeder R/X ratios: *not stated*.

**4) Code/repo link if stated**  
* Model/code repo: *not stated*.  
* Load data link: `https://openei.org/doe-opendata/dataset/commercial-and-residential-hourly-load-proﬁles-for-all-tmy3-locations-in-the-united-states`

**5) Limits or red flags**  
* Evaluated only on two US distribution feeders (12 kV primary, 0.24 kV / 0.277 kV secondary), not Indian low-voltage systems.  
* Did not quantify long-term mechanical impacts of VVC on Load Tap Changer (LTC) tap count reduction.  
* Sized PV purely to balance annual load energy (1.35 peak ratio), omitting scenarios with high localized PV generation-to-load mismatches.

**6) Verdict for GridTwin: useful / not useful and why**  
Useful. It provides clear reference evidence that autonomous VVC control on small secondary-connected rooftop PV has negligible voltage impact and that malicious VVC setting tampering poses minimal voltage risk unless PV installations are large and centrally located on primary lines.
