# Runbooks

One page per thing that goes wrong. Each says what you see, how to check, how to fix it, and who decides.

| Runbook | When |
|---|---|
| [weather_api_down.md](weather_api_down.md) | The live solar forecast or the nightly run cannot reach Open-Meteo |
| [stale_model.md](stale_model.md) | `data/monitor/WARN` exists, or the model files fail their checksum |
| [cache_corruption.md](cache_corruption.md) | The API serves an error or old numbers for a precomputed case |
| [solver_failures.md](solver_failures.md) | Many steps are unsafe because the power flow did not converge |
| [data_refresh.md](data_refresh.md) | Rebuilding the processed data from the raw files |
| [release_rollback.md](release_rollback.md) | Cutting a release, or going back to the last good one |

Steps marked *(API, Phase 8)* use parts of the v2 API that Person A builds in Phase 8; until they land, use the
script-level check next to them.
