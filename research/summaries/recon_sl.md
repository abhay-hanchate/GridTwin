**1) What the paper does**
Describes the Residential Electricity Consumption Dataset for Sri Lanka (RECON-SL), linking longitudinal household surveys with utility billing and smart meter data. It establishes an open-access multi-resolution benchmark for residential load profiling, energy behavior, and policy analysis in South Asia.

**2) Data used + whether public/Indian**
* **Data:** 4,063 households from Lanka Electricity Company (LECO) across 7 western coastal branches in Sri Lanka, covering monthly billing data (4,063 households), smart meter data (1,438 households), and 3 longitudinal survey waves. 
* **Public:** Yes, publicly available under Creative Commons Attribution 4.0 International (CC BY 4.0).
* **Indian:** No (Sri Lankan / South Asian).

**3) Method + key numbers/results**
* **Method:** Stratified random sampling across LECO branches and meter types; face-to-face CAPI surveys across 3 waves; extraction and alignment of utility smart meter and billing time-series; cross-validation against billing records.
* **Key numbers:**
  * **Size & households:** 4,063 total households; 1,438 smart-metered households; >50 million meter readings; >11,000 household interviews across 3 waves (Wave 1: 4,063; Wave 2: 3,500; Wave 3: 3,397; retention rate 83.6%).
  * **Resolution:** Monthly (101,575 records), 6-hour (2,174,877 records), and 15-minute (21,970,542 records).
  * **Completeness:** 15-minute data is 20.2% complete for requested dates (35.5% for available dates); 6-hour data is 47.7% complete for requested dates (51.7% for available dates); monthly data is 92.6% complete for requested dates (100.0% for available dates).
  * **Electrical parameters:** Raw smart meter streams include voltage, current, and frequency measurements alongside active consumption.
  * **Timeframe:** October 2022 to January 2025 (meter readings: 2023-01-01 to 2024-12-23; surveys: 15 November 2023 to 12 January 2025).

**4) Code/repo link if stated**
* **Code repo:** https://github.com/LIRNEasia/lacuna
* **Data access:** https://dx.doi.org/10.21227/n1dk-q860 (also hosted on IEEE DataPort, Zenodo, and Kaggle).

**5) Limits or red flags**
* Significant missingness/gaps in 15-minute smart meter data (20.2% overall completeness) due to transmission and server failures.
* Geographic scope restricted exclusively to LECO’s western coastal service area (not nationally representative).
* Metering is whole-house level only (no sub-metered appliance-level disaggregation).
* Survey variables (e.g., expenditure) rely on self-reporting and recall; exact household income is not provided.
* Historical data not suitable for live or real-time operational grid control.

**6) Verdict for GridTwin: useful / not useful and why**
* **Verdict:** Useful.
* **Why:** It provides an open-access (CC BY 4.0) South Asian smart meter dataset with 1,438 households at 15-minute resolution that explicitly includes voltage, current, and frequency data, along with rooftop solar adoption tracking. Climatic conditions, housing typologies, and appliance usage patterns along coastal Sri Lanka closely mirror southern and coastal Indian distribution networks.
