#!/bin/bash
run() { n="$1"; u="$2"; need="$3"; for i in 1 2 3; do python -I research/omni_read.py read "$u" "$need" > "research/summaries/$n.md" 2>&1 && ! grep -q "HTTP 5" "research/summaries/$n.md" && break; sleep 5; done; echo "done $n"; }
run risk_nongaussian "https://arxiv.org/pdf/2410.12438" "Day-ahead or forecast voltage risk with VaR/CVaR and curtailment/reactive actions: horizon, network, data, results, code. Is this the same as day-ahead probability of voltage violation with fix selection for LV rooftop solar?" &
run decision_focused_vvc "https://arxiv.org/pdf/2604.07106" "Three-stage forecast-driven Volt/VAR: how day-ahead PV forecast errors propagate, network used, results, code" &
run risk_planning_genai "https://arxiv.org/pdf/2605.02340" "Risk-based PV-rich distribution planning with generative AI: scenario generation, risk metric definition, network, results, code" &
run topology_id_2409 "https://arxiv.org/html/2409.09073v1" "LV topology identification from smart meter data: method, data needed, accuracy, tested on real or synthetic network, code" &
wait
run tsfm_power_2604 "https://arxiv.org/pdf/2604.22077" "Time-series foundation models for power system forecasting: solar and load results versus classical models, CRPS numbers, which models best, recommendations" &
run tsfm_pv_coldstart "https://arxiv.org/pdf/2606.07457" "Foundation models with physics-informed synthetic histories for PV forecasting with no history: method, results versus LightGBM or physics, relevance to new Indian rooftop systems with no history" &
run kochi_transformer "https://now.solar/2026/04/17/kochi-rooftop-pv-growth-has-hit-transformer-limits-solarbytes/" "Kochi KSEB limit on new solar connections: transformer loading threshold, number of areas, utility statements, date, what data or tool they lacked" &
run workongrid "https://inc42.com/buzz/ai-startup-workongrid-nets-%e2%82%b922-5-cr-to-fuel-international-expansion/" "WorkOnGrid: what product does, customers, whether it does rooftop solar hosting capacity or voltage analysis, funding, date" &
wait
run bolognani_topology_ieee "https://ieeexplore.ieee.org/document/9641748" "Topology identification of radial distribution networks using smart meter data: method and accuracy" &
run klonari_probabilistic "https://www.intechopen.com/profiles/174062" "Probabilistic LV analysis with smart meter data (Mons): method, data, findings" &
run pune_dt_lifeloss "https://doaj.org/article/84d99a1b341849049ef9d117d7b5f647" "Pune residential DT loss of life with rooftop solar plus EV charging: method, dataset, results, tools" &
run egridgpt_nrel "https://nrel.gov/docs/fy24osti/87050.pdf" "NREL digital twin plus AI network operator virtual assistant: architecture, LLM grounding approach, results" &
wait
