# Data sources and licences

What GridTwin uses, under which terms, and what that obliges us to do. Checked on 9 Oct 2026 unless a row says
otherwise. Tags: **[V]** read at the source, **[U]** not yet verified.

## Datasets

| Source | Used for | Licence or terms | Obligation | Status |
|---|---|---|---|---|
| CEEW, "High frequency smart meter data from two districts in India" (Harvard Dataverse, doi:10.7910/DVN/GOCHJH) | Household demand, customer voltage, both districts | CC0 1.0 | None; we cite the source anyway | [V] (plan research) |
| Open-Meteo API: historical archive, previous-runs (day-ahead NWP), forecast | Weather, ERA5 solar truth, live solar forecast | Free tier: **non-commercial use only**, under 10,000 calls a day, 5,000 an hour, 600 a minute; data under **CC BY 4.0** | Attribute Open-Meteo; a commercial deployment needs a paid Open-Meteo plan | [V] terms page; the exact attribution wording on the licence page could not be read (rendered by script) [U] |
| ERA5 reanalysis (Copernicus Climate Change Service), through Open-Meteo | Solar truth for training and monitoring | Copernicus licence | Acknowledge Copernicus C3S as the ERA5 source | [U] terms not re-read in the build |
| NWP models through Open-Meteo: ECMWF IFS, NOAA GFS, DWD ICON, ECCC GEM, Météo-France ARPEGE | Solar v2 ensemble | Covered by Open-Meteo's CC BY 4.0 terms; each provider's own open-data terms apply upstream | Attribute Open-Meteo; check provider terms before commercial use | [U] provider terms |
| SimBench benchmark grids (the `simbench` package) | Street topology for every archetype | Database: **Open Database License (ODbL 1.0)**; contents: Database Contents License (DbCL 1.0); code: BSD-3-Clause | Attribute SimBench; a **derived database** we publish (the scaled archetypes) must be offered under ODbL | [V] package LICENSE file |
| IS 398 Part II conductor table (BIS) | Conductor resistance and ampacity in the archetypes | Indian Standard; values taken from a scanned reproduction | Cite the standard; check values against the BIS copy | [U] values not checked against BIS |
| Karnataka 72 kWp plant (IEEE DataPort) | Yield calibration (A7) | Needs an IEEE DataPort login; licence not read | Not used: gate G7 outcome (b) | [U] |
| RECON-SL | Optional cross-country demand check | CC BY 4.0 (plan research) | Attribute if used | Not used yet |

## Software that ships

Runtime Python dependencies (versions pinned in `constraints.txt`), from the installed package metadata:

| Package | Licence |
|---|---|
| pandapower, pandas, numba, jinja2, simbench (code) | BSD |
| pvlib, networkx, scikit-learn, uvicorn | BSD-3-Clause |
| power-grid-model | MPL-2.0 (file-level copyleft: changes to its files must stay MPL-2.0; using it unchanged is fine) |
| lightgbm, fastapi, holidays, pydantic-settings | MIT |
| ortools, requests, pyarrow | Apache-2.0 |
| prometheus-client | Apache-2.0 and BSD-2-Clause |

Frontend runtime: React and Recharts (MIT). Benchmark only, never shipped: Chronos-2 and its dependencies
(`requirements-ml.txt`).

Referenced, not copied: Open-Meteo's server code (AGPL-3.0; we call the API and include none of its code),
ppOPF and the Hosting-Capacity repository.

## Gate G6: result

**Open-Meteo's free API allows non-commercial use only** (terms page, read 9 Oct 2026). The hackathon demo and
research use fit that. A DISCOM deployment counts as commercial use of the service and must move to a paid
Open-Meteo plan, or to another licensed weather source, before release. The README says so.
