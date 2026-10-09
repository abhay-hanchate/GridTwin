**1) What the paper does**  
Proposes a fast "fixed-voltage" Monte Carlo method using a 3-phase linear power flow to evaluate probabilistic solar PV hosting capacity on LV networks.  
Analyzes hosting capacity explicitly as a function of customer penetration level rather than aggregating all scenarios together.

**2) Data used + whether public/Indian**  
- Data: 4 UK LV distribution feeders from Electricity North West Limited (ENWL) (N1.1, N2.1, N3.1, N4.1 with 24–175 loads and 375–2287 buses) and the IEEE European LV test feeder (55 loads, 907 buses). Each load assigned static 0.3 kW demand at 0.95 lagging power factor.  
- Public: Yes (ENWL and IEEE test feeder links provided).  
- Indian: No.

**3) Method + key numbers/results**  
- **Method:** Fixed-voltage method that directly calculates the maximum allowable generation per scenario $\hat{P}^{gen} = \min(\lfloor\text{diag}(F\Lambda)^{-1}(\mathbf{1}_{Nlds}v^+ - \bar{v})\rfloor)$ using a 3-phase linearized power flow model, eliminating iterative bisection.  
- **Sampling count:** $N_{MC} = 1000$ Monte Carlo runs yielded relative errors under 3% (0.15% to 2.68% across networks).  
- **Computational gain:** Execution time reduced to 0.17–5.57 s (fixed-voltage) compared to 1.20–102.83 s (fixed-power bisection across 8–23 iterations).  
- **Distribution / Percentiles:** Cites prior work [4] showing hosting capacity bounds are roughly Gaussian. Reports hosting capacity via boxplots (minimum, maximum, median, interquartile range) and the 5% risk level ($\Phi_{5\%}$). P10/P90 are not stated. $\Phi_{5\%}$ follows an S-shaped curve vs penetration, and allowable power per generator at 25% penetration is 50–100% greater than at 100% penetration.

**4) Code/repo link if stated**  
Not stated (links provided for OpenDSS, ENWL data, and IEEE test feeders, but no repo link for the paper's code).

**5) Limits or red flags**  
- Assumes uniform PV export capacity across all connected households in a scenario.  
- Evaluates only voltage rise under static load conditions; thermal limits, voltage unbalance, and temporal load/solar variations are not evaluated.  
- Relies on a linearized power flow model that assumes voltage angles do not deviate significantly from nominal.

**6) Verdict for GridTwin: useful / not useful and why**  
**Useful.** The closed-form fixed-voltage formulation provides an efficient algorithm for Monte Carlo hosting capacity calculations on unbalanced 3-phase LV grids without iterative power flow runs, validates that 1,000 samples achieve $<3\%$ error, and demonstrates the necessity of evaluating hosting capacity as a function of penetration percentage.
