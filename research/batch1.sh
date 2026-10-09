#!/bin/bash
# usage: each line "name|url|need"
run() { n="$1"; u="$2"; need="$3"; python -I research/omni_read.py read "$u" "$need" > "research/summaries/$n.md" 2>&1; echo "done $n"; }
run nrel_ieee1547_india "https://www.nrel.gov/docs/fy24osti/87756.pdf" "How IEEE 1547-2018 should be adapted for India: Volt-VAR/Volt-Watt settings, Indian grid code status, rooftop PV capacity, inverter requirements, anything about LV voltage limits in India" &
run phase_hosting_capacity "https://arxiv.org/pdf/2405.20682" "Effect of phase selection on hosting capacity accuracy/speed for unbalanced LV feeders: method, numbers, code, test feeders" &
run powerflow_multinet "https://arxiv.org/pdf/2403.00892" "GNN surrogate for unbalanced multiphase power flow: accuracy, speedup, training data size, code link, whether usable for a 100-bus LV feeder" &
run phase_id_survey "https://arxiv.org/pdf/2204.06372" "Best-performing smart-meter phase identification methods, data requirements (resolution, duration), accuracy numbers, open datasets/code" &
wait
run stochastic_hc "https://arxiv.org/pdf/1902.08780" "Probabilistic hosting capacity method for LV, distribution shape, sampling count, how to report P10/P50/P90 hosting capacity" &
run openaccess_tools "https://arxiv.org/pdf/2603.23103" "Comparison of open-source power system tools (pandapower, OpenDSS, GridLAB-D etc): which is best for unbalanced LV time-series hosting capacity with smart inverters; performance numbers" &
run teri_dt_lv "https://www.teriin.org/research-paper/application-digital-twins-low-voltage-electricity-grid-challenges-and-opportunities" "Digital twin for LV grids in India: challenges, data needs, what exists, gaps" &
run recon_sl "https://arxiv.org/pdf/2609.28783" "South Asian (Sri Lanka) residential smart meter dataset: size, resolution, voltage included?, license, access link; comparable to Indian conditions?" &
wait
