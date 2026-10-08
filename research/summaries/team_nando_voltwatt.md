1) **What the paper does**  
Provides a Jupyter Notebook and Python tutorial using OpenDSS (via `dss-python`) to assess the impact of inverter Volt-Watt control on voltages and PV hosting capacity in three-phase unbalanced LV distribution networks.

2) **Data used + whether public/Indian**  
LV network model (`TestLVCircuit`) and seasonal residential PV profile files (`Residential_PV_profile_Autumn.npy`, `Summer.npy`, `Spring.npy`, `Winter.npy`). Public (GitHub repo); Indian: not stated.

3) **Method + key numbers/results**  
- **Method:** Time-series power flow simulations of 3-phase unbalanced LV networks using `dss-python`/OpenDSS to model inverter Volt-Watt control functions and evaluate hosting capacity.  
- **Key numbers/results:** Not stated in the repository overview text (contained within the `.ipynb` and solution PDF).

4) **Code/repo link if stated**  
`https://github.com/Team-Nando/Tutorial-DERHostingCapacity-3-VoltWatt_LV`

5) **Limits or red flags**  
Page text provides repository structure and instructions rather than direct simulation metrics; specific Indian grid topology/parameters are not stated.

6) **Verdict for GridTwin: useful / not useful and why**  
Useful. It delivers open-source (BSD 3-Clause license) Python and OpenDSS scripts specifically structured to implement time-series Volt-Watt controls and evaluate LV rooftop PV hosting capacity.
