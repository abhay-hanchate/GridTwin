# Weather API down

**Symptom.** `python -m ml.live_solar_v2` fails with `Open-Meteo multi-model request failed` or
`only N NWP models returned complete data; need 3`; the nightly run fails.

**Check.**
1. `curl -s "https://api.open-meteo.com/v1/forecast?latitude=27.49&longitude=77.67&hourly=shortwave_radiation&models=icon_global"`:
   no answer means the service or the network is down; HTTP 429 means the free limits (10,000 calls a day,
   600 a minute) were hit.
2. If only some models are missing, the forecast still runs with three or more; fewer than three is a refusal by
   design, not a bug.
3. The archive (`archive-api.open-meteo.com`) sometimes times out on long date ranges; `scripts/download_data.py`
   can simply be run again, finished files are skipped.

**Fix.**
- Network or service down: keep serving the last good forecast and show it as stale with its age
  *(API, Phase 8: the response carries the age)*. Never invent a forecast.
- Limits hit: wait for the window to reset. Only the nightly run calls the API; the dashboard reads cached results.
- Demo without network: `GRIDTWIN_OFFLINE=1` serves the bundled results *(API, Phase 8)*.

**Who decides.** Whoever runs the demo or deployment. Moving to a paid or different weather source is a licence
decision (`docs/DATA_SOURCES.md`, gate G6).
