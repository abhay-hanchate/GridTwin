**1) What the paper does**  
Provides a Python/Pyomo tool (`ppOPF`) to solve 3-phase unbalanced Optimal Power Flow (OPF) on distribution networks structured with `pandapower`. It optimizes DER active power bounds/export across three different mathematical formulations.

**2) Data used + whether public/Indian**  
Benchmark CIGRE LV network (`Test network.zip`) with active power time series and phase connection Excel files; public, not Indian.

**3) Method + key numbers/results**  
Implements three 3-phase OPF formulations in Pyomo: nonlinear nonconvex (*current-voltage*, *power-voltage*) and linearized (*lindist*). Predefined objective maximizes DER export (or minimizes DER import) to output objective value, voltage magnitude, apparent power flow, and active DER power. Repo metrics: 31 commits, 9 stars, 4 forks.

**4) Code/repo link if stated**  
https://github.com/tomislavantic/ppOPF

**5) Limits or red flags**  
- Non-commercial license (`CC-BY-NC-4.0`).  
- Volt-VAR control, battery storage, and tap changers are not stated/supported.  
- Low project maturity (0 releases, 31 commits, minimal documentation).

**6) Verdict for GridTwin: useful / not useful and why**  
**Useful (with limitations):** Serves as a useful implementation reference for setting up 3-phase unbalanced OPF formulations (especially 3-phase LinDistFlow) with `pandapower` network definitions and Pyomo. However, it cannot be used directly in commercial settings due to the `CC-BY-NC-4.0` license, and missing controls (battery, Volt-VAR, tap) must be built independently.
