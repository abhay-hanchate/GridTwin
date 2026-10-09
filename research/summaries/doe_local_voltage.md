**1) What the paper does**  
Proposes a decentralized framework to calculate real-time dynamic operating envelopes (RT-DOEs) using only local PCC voltage measurements without communication, and a chance-constrained time-ahead DOE framework using forecasted voltage scenarios.

**2) Data used + whether public/Indian**  
* **Data used:** A 76-node, 75-branch Spanish low-voltage distribution network with 52 loads across 28 nodes, plus 1000 load profile scenarios.  
* **Public:** Yes (hosted on GitHub).  
* **Indian:** No (Spanish/European LV network).

**3) Method + key numbers/results**  
* **Method:** Uses local volt-watt/volt-var curves—specifically Avoiding Negative Reinforcement Control (ANRC) for $P$ and Positive Reinforcement Control (PRC) for $Q$ combined with inverter capacity and power factor constraints for real-time DOEs. For day-ahead DOEs, compares Method 1 (M1: chance constraint on voltage scenarios via empirical CDF) and Method 2 (M2: chance constraint on scenario-specific DOEs).  
* **Key numbers/results:** Tested with $U_{\max} = 1.08\text{ pu}$, $U_{\min} = 0.92\text{ pu}$, $\Delta_{\text{perm}} = 0.04\text{ pu}$, power factor limit $= 0.9$, and 5% chance constraint. M1 achieved virtually identical accuracy to M2 ($\Delta P_E = 0$, $\Delta Q_E = 0.23$) while being over $2\times$ faster (mean computation time: 0.89 s for M1 vs. 1.9 s for M2 across 1000 Monte Carlo runs) and reducing required communication from 1000 time-series to just 2 ($U_L$ and $U_H$).

**4) Code/repo link if stated**  
Network and load data link is stated: `https://github.com/umar-hashmi/FNAData` (Algorithm code repo: not stated).

**5) Limits or red flags**  
* Real-time local control is heuristic/rule-based and lacks centralized coordination, which may lead to over/under-compensation or locational unfairness.  
* Evaluated on a European benchmark; does not explicitly model high single-phase solar phase unbalance common in Indian LV feeders.  
* Severe voltage deviations combined with power factor limits can result in an empty/null feasible operating set.  
* Time-ahead robust envelopes (DA-DOE) still require centralized power flows and communication of boundary profiles.

**6) Verdict for GridTwin: useful / not useful and why**  
**Useful.** The real-time formulation requires zero telemetry, no network topology/impedance parameters, and relies solely on local nodal voltage measurements, making it directly deployable for autonomous solar inverter control and edge-side envelope generation on unmonitored Indian LV feeders.
