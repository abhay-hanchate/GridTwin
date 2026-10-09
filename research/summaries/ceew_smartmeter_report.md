**1) What the paper does**
The report analyzes high-frequency smart meter data to assess electricity supply quality (voltage profile, outages) and household consumption patterns in urban Uttar Pradesh. It evaluates tail-end grid reliability, peak residential demand drivers (especially air conditioners), and distribution planning implications.

**2) Data used + whether public/Indian**
* **Data:** 3-minute interval smart meter readings (480 points/day) and socio-economic/appliance survey data from May to October 2019.
* **Public/Indian:** Indian (Mathura and Bareilly districts, Uttar Pradesh). Raw dataset availability is not stated.

**3) Method + key numbers/results**
* **Meter count & fields:** 93 single-phase smart meters (Sumeru Verde). Captured fields (10 parameters): `Meter_id`, `x_Timestamp`, `t_kWh`, `t_kVAh`, `z_Avg.Voltage..Volt.`, `z_Max.Voltage..Volt.`, `z_Min.Voltage..Volt.`, `z_Avg.Current..Amp.`, `z_Max.Current.Amp`, `z_Min.Current..Amp.`, `y_Freq..Hz.`.
* **Outages & Supply Duration:** Households received an average of 22 hours/day of supply (2 hours/day outage). Notified Town Areas (NTAs) faced 3.5 hours/day outage (6 interruptions/day) vs. district headquarters at 1.3 hours/day (3.5 interruptions/day). Most outages occurred during daytime. Household outages (2 hours/day) were far higher than 11 kV feeder reports (3.5–4.8 hours/month in July 2019).
* **Voltage Quality & Distribution:**
  * 70% of sampled residential areas had supply voltages outside the prescribed 230 V ± 6% range (216–244 V) for >50% of total duration.
  * For the 230 V ± 10% range, every second household received voltage outside the range for ≥25% of the duration.
  * High-voltage supply and surges exceeding 350 V were observed across almost all areas (except two).
  * Low-voltage issues (<207 V) and steep voltage drops of 25–30% occurred during peak evening hours in specific pockets (e.g., Chamunda Colony).
* **Demand & Sanctioned Load:** Average monthly consumption was 280 units (range: 15–970 units). 30% of households exceeded sanctioned load at least once; one-sixth did so for ≥3 consecutive months (driven by AC use).
* **Rooftop Solar Info:** No empirical rooftop solar generation data collected; solar is only mentioned qualitatively as a recommendation for peak-shaving and distributed generation.

**4) Code/repo link if stated**
Not stated.

**5) Limits or red flags**
* Small, purposively selected sample (93 households; 3-phase connections excluded).
* Data loss averaged ~15% (ranging 3% to 33% across meters) due to GPRS network drops, SIM data exhaustion, software bugs, and surge damage.
* No actual rooftop solar PV systems were installed or monitored in the sample.

**6) Verdict for GridTwin: useful / not useful and why**
**Useful.** It provides highly relevant empirical baseline distribution grid data for Indian LV networks—specifically real-world tail-end voltage distributions, extreme over/under-voltage shares, peak-hour voltage drops (25–30%), and exact 3-minute smart meter telemetry structures.
