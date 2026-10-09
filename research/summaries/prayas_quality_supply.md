**1) What the paper does**  
Analyzes minute-wise electricity supply quality, reliability, and voltage variation across urban, semi-urban, and rural Indian households.  
Evaluates regional, seasonal, and time-of-day outage patterns and supply voltage levels to assess local distribution network performance.

**2) Data used + whether public/Indian**  
* **Dataset:** Prayas eMARC smart meter minute-wise consumption and supply voltage data.  
* **Sample size:** 115 households.  
* **Period:** January 2018 to June 2020.  
* **Geographical scope:** Indian (Pune City [urban], Pune district, Aurangabad district, Kanpur Rural district, and Gonda district [semi-urban and rural]).  
* **Public availability:** Dashboards are publicly accessible at `http://emarc.watchyourpower.org/visualisation.php`; direct public download links for raw CSV data are not stated (author contact provided: `aditya@prayaspune.org`).

**3) Method + key numbers/results**  
* **Method:** Categorizes minute-wise measurements into no supply, low, normal, and high voltage (using regulatory benchmarks such as Maharashtra SERC’s 230 V ± 10%), analyzing spatial, seasonal, and diurnal trends.  
* **Supply Hours (Average / Minimum):** Pune City (23.8 h / 23.6 h), Pune district (22.5 h / 21.2 h), Aurangabad (22.2 h / 17.9 h), Kanpur Rural (17.2 h / 11.0 h), Gonda (18.1 h / 14.2 h).  
* **Evening Supply (5 PM–11 PM Average):** Pune City (5.9 h), Pune district (5.7 h), Aurangabad (5.7 h), Kanpur Rural (4.7 h), Gonda (4.8 h).  
* **Voltage Findings:** Pune City rarely experienced out-of-band voltages. Rural/semi-urban areas experienced frequent and sustained low voltage; high voltage was uncommon except in Gonda, where one rural household sustained ~280 V for >6 hours/day between September 2019 and February 2020. Morning voltage dips occurred in Pune/Aurangabad, whereas Kanpur Rural/Gonda saw morning voltage rises in summer. Supply hours were lowest in monsoon and highest in winter.

**4) Code/repo link if stated**  
Not stated (visualization dashboard at `http://emarc.watchyourpower.org/visualisation.php`).

**5) Limits or red flags**  
* Limited sample size (115 households across 5 regions).  
* Distribution transformer (DT) sizing, loading, and feeder distance to households were not recorded due to data paucity.  
* Article does not provide a direct link or API to programmatically download the raw time-series datasets.

**6) Verdict for GridTwin: useful / not useful and why**  
**Useful.** It provides real-world Indian LV feeder empirical baselines (actual voltage distributions, extreme overvoltage up to 280 V, sustained low-voltage conditions, and outage profiles) critical for calibrating GridTwin’s low-voltage power flow and rooftop solar overvoltage trip simulations.
