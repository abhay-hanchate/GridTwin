import subprocess
repos="""amazon-science/chronos-forecasting google-research/timesfm unit8co/darts Nixtla/statsforecast Nixtla/mlforecast pyomo/pyomo open-meteo/open-meteo NREL/SAM NatLabRockies/SAM powsybl/powsybl-core openmod/awesome-energy-system-modelling lf-energy/awesome-energy-gridfm PyPSA/pypsa-earth emhass/emhass davidusb-geek/emhass energy-modelling-toolkit/oemof-solph OpenEnergyPlatform/oemof-tabular microsoft/FLAML optuna/optuna shap/shap fastapi/fastapi pgmpy/pgmpy dss-extensions/dss_python epri-dev/OpenDSS PNNL-CompBio/GridAPPS-D GRIDAPPSD/gridappsd-python NatLabRockies/OEDI-SMART-DS lanl-ansi/PowerModels.jl google/or-tools geopandas/geopandas networkx/networkx""".split()
for r in repos:
    p=subprocess.run(["gh","api",f"repos/{r}","--jq",'[.full_name,.stargazers_count,(.license.spdx_id//"none"),.pushed_at[:10],.archived]|@tsv'],capture_output=True,text=True)
    print(p.stdout.strip() if p.returncode==0 else f"{r}\tNOT FOUND")
