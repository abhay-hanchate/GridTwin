#!/bin/bash
run() { n="$1"; u="$2"; need="$3"; python -I research/omni_read.py read "$u" "$need" > "research/summaries/$n.md" 2>&1; echo "done $n"; }
run era5_india_atmosphere2025 "https://www.mdpi.com/2073-4433/16/8/957" "ERA5 vs IMD ground stations over India: bias, RMSE, correlation of surface solar radiation for ERA5 and other reanalyses; which dataset is best for India" &
run state_est_delavarga "https://arxiv.org/pdf/2307.16822" "Learning-based state estimation with limited real-time measurements: method, test grid, accuracy numbers, code availability, applicability to LV with sparse smart meters" &
run doe_local_voltage "https://arxiv.org/pdf/2305.13079" "Robust dynamic operating envelopes using only local voltage measurement: method, results, applicability to LV feeders without telemetry, code" &
run doe_allocation_2026 "https://arxiv.org/pdf/2605.07989" "Allocation of dynamic operating envelopes in radial distribution networks: fairness/allocation method, results, code" &
wait
run gujarat_voltvar_2026 "https://jjee.ttu.edu.jo/docs/vol11no4/76_JJEE-2026-01-29-V11N4-25.pdf" "Smart-inverter Volt/VAR in PV-enriched networks (Gujarat authors): curve settings used, results, India relevance, caveats" &
run sandia_voltvar_rooftop "https://psecommunity.org/wp-content/plugins/wpor/includes/file/2303/LAPSE-2023.25933-1v1.pdf" "Volt-VAR curve effectiveness with rooftop PV inverters and tampered settings: findings, limitations of Volt-VAR on resistive feeders" &
run prayas_quality_supply "https://www.prayaspune.org/peg/quality-of-electricity-supply" "Prayas eMARC smart meter dataset: households, regions, period, voltage findings, whether data is public and how to access" &
run oe1_ideal_repo "https://github.com/Team-Nando/OE1-Ideal" "Operating envelope ideal algorithm repo: what it computes, network used, license, how reusable with pandapower/OpenDSS" &
wait
