**1) What the paper does**  
Proposes a zero-shot cold-start PV yield forecasting pipeline that generates synthetic production history from plant metadata and ERA5 weather via physics models to condition Time Series Foundation Models (TSFMs).  
Evaluates five TSFMs across three operational context strategies (Cold-Start Baseline, Real Feedback, Self-Forecast Feedback) without target-site parameter updates.

**2) Data used + whether public/Indian**  
* **Data:** 440 PV sites across four cohorts: Ausgrid (300 residential sites, Australia), DKASC (10 desert sites, Australia), UK-PV (100 temperate sites, UK), and PVDAQ (30 sites across climate zones, USA), paired with ERA5 reanalysis weather data via Open-Meteo.  
* **Public/Indian:** Public (all 4 cohorts and ERA5 are publicly available). Not Indian (no Indian sites included).

**3) Method + key numbers/results**  
* **Method:** Stage 1 creates a synthetic daily yield history ($\tilde{y}_{1:T}$) from metadata (tilt, azimuth, capacity, loss priors) and ERA5 meteorology using either PVGIS or OPAQUE (an open, satellite-free physics pipeline based on pvlib/Hay-Davies/NOCT/PVWatts). Stage 2 feeds this context into zero-shot TSFMs (TabPFN-TS, Chronos-2, TimesFM 2.5, Moirai 2.0, TiRex) and baselines (naive, seasonal-naive, Prophet). Tested under Cold-Start Baseline (CSB: 365-day single pass), Real Feedback (RF: 15-day rolling with measured data), and Self-Forecast Feedback (SFF: 15-day rolling with recursive model predictions). *Note: LightGBM is not evaluated / not stated.*  
* **Key Numbers/Results:**  
  * **Real Feedback (RF):** Covariate-aware TSFMs beat baselines by ~1.7–2×. TabPFN-TS achieves lowest error on OPAQUE (MAE 0.514, RMSE 0.721 $\text{kWh}\cdot\text{kWp}^{-1}\text{d}^{-1}$, WAPE 15.46%) and PVGIS (MAE 0.512, RMSE 0.717 $\text{kWh}\cdot\text{kWp}^{-1}\text{d}^{-1}$, WAPE 15.39%). Chronos-2 achieves OPAQUE MAE 0.537, RMSE 0.737, WAPE 16.14%.  
  * **Self-Forecast Feedback (SFF):** Chronos-2 is most robust against recursive drift (OPAQUE: MAE 0.985, RMSE 1.203 $\text{kWh}\cdot\text{kWp}^{-1}\text{d}^{-1}$, WAPE 30.67%; PVGIS: MAE 0.908, RMSE 1.113 $\text{kWh}\cdot\text{kWp}^{-1}\text{d}^{-1}$, WAPE 28.24%). TabPFN-TS gets OPAQUE SFF WAPE 31.91%. TiRex collapses without covariates (OPAQUE SFF WAPE 49.77%).  
  * **Cold-Start Baseline (CSB):** Errors double vs RF. On OPAQUE, Prophet achieves MAE 1.006, RMSE 1.221 (WAPE 31.30%), TabPFN-TS achieves MAE 1.016, RMSE 1.238 (WAPE 31.55%), and Chronos-2 achieves MAE 1.019, RMSE 1.244 (WAPE 31.64%). On PVGIS, Chronos-2 leads CSB (MAE 0.907, RMSE 1.114, WAPE 28.14%).  
  * **Synthetic Context Invariance:** Performance is driven by having plausible temporal context rather than the specific simulator (OPAQUE vs PVGIS RF WAPE differs by <0.5 pp).

**4) Code/repo link if stated**  
* **Paper Code/Repo:** not stated.  
* **Referenced Public Repos/Links:** Ausgrid preprocessed data (`https://github.com/pierre-haessig/ausgrid-solar-data`), DKASC portal (`http://dkasolarcentre.com.au/historical-data/download`), NREL PVDAQ (`https://data.openei.org/submissions/4568`), UK Power Networks (`https://ukpowernetworks.opendatasoft.com/`), Open-Meteo (`https://open-meteo.com/`).

**5) Limits or red flags**  
* Daily time resolution only (sub-hourly/hourly operational grid dynamics are not modeled).  
* Uses perfect-foresight ERA5 meteorological reanalysis as future horizon covariates (optimistic; ignores Numerical Weather Prediction forecast errors).  
* Standard tabular baselines like LightGBM/XGBoost are omitted (only compared against Prophet, naive, and seasonal-naive).  
* Single-seed evaluation; no target-site parameter fine-tuning.

**6) Verdict for GridTwin: useful / not useful and why**  
* **Verdict:** Useful.  
* **Why:** Provides a proven, satellite-free blueprint (OPAQUE physics via pvlib + ERA5/Open-Meteo paired with Chronos-2 or TabPFN-TS) to solve the "day-0" cold-start forecasting problem for unmetered or newly installed Indian rooftop PV systems before real smart-meter telemetry is accumulated. However, GridTwin must extend the physics and foundation model pipeline from daily to sub-hourly/hourly resolution and incorporate real Indian weather forecast inputs.
