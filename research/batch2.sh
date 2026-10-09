#!/bin/bash
run() { n="$1"; u="$2"; need="$3"; python -I research/omni_read.py read "$u" "$need" > "research/summaries/$n.md" 2>&1; echo "done $n"; }
run cstep_feeder_2026 "https://cstep.in/wp-content/uploads/2026/04/1771641859.pdf" "Indian sub-11kV feeder rooftop solar impact study: network data, penetration thresholds for voltage and transformer overload, mitigation options, methods and tools used, any data/code" &
run ceew_smartmeter_report "https://www.ceew.in/sites/default/files/ceew-study-on-what-can-smart-meters-tell-us-report.pdf" "Voltage quality findings from Mathura/Bareilly smart meters: voltage distribution, share outside limits, outages, meter count, data fields, any rooftop solar info" &
run renkema_conformal "https://research.wur.nl/en/publications/enhancing-the-reliability-of-probabilistic-pv-power-forecasts-usi/" "Conformal prediction for day-ahead probabilistic PV forecasts: methods, improvement vs quantile regression, code/data availability" &
run ppopf_repo "https://github.com/tomislavantic/ppOPF" "What ppOPF offers: 3-phase OPF on pandapower, supported controls (Volt-VAR, battery, tap), license, maturity, examples" &
wait
run team_nando_voltwatt "https://github.com/Team-Nando/Tutorial-DERHostingCapacity-3-VoltWatt_LV" "Tutorial on LV hosting capacity with Volt-Watt in OpenDSS: network used, steps, reusable code, license" &
run wenbo_hc "https://github.com/wenbowangnrel/Hosting-Capacity-Analysis" "Equitable hosting capacity repo: language, method, inputs, smart inverters, license" &
run energetica_phase_balance "https://www.energetica-india.net/news/rajasthan-discoms-mandate-phase-balancing-for-single-phase-rooftop-solar-connections" "Rajasthan DISCOM phase balancing order: date, rules, problems cited, what data a DISCOM needs to comply" &
run renewablewatch_pq "https://renewablewatch.in/2025/02/13/reliability-concerns-impact-of-rooftop-solar-on-power-quality" "Indian evidence of rooftop solar power quality impacts: voltage, harmonics, studies cited, DISCOM views" &
wait
