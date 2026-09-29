# GridTwin test plan

This plan covers the checks used before a demo or pull request. GridTwin is a modeled benchmark feeder informed by Mathura measurements; a passing test run does not certify a real utility feeder or a customer connection.

## 1. Automated checks

Run these commands from the repository root with the Python virtual environment active. The frontend build command runs from `frontend/`.

```bash
pytest -q tests
```

```bash
cd frontend
npm install
npm run build
```

The Python suite covers:

| Area | Checks |
| --- | --- |
| Grid and engine | Indian overhead-line parameters, transformer taps, topology coordinates, full-day 96-step run, solver failures, solar-attributed voltage violations |
| API health and core results | Health response, scenario list, run-result contract and provenance, action ranking, summary data |
| Hosting capacity | Default estimate, 10% adoption sweep, capacity with and without the recommended fix, unsupported voltage-band validation |
| Forecast API | Ordered prediction bands, valid solar and demand targets, per-home demand units, unknown target validation, unavailable date response |
| Invalid requests | Unknown scenario, unknown corrective action, missing meter-day data, unsupported hosting-capacity band |
| Simulators | Fix before/after results and inverter response; forecast-versus-actual response |
| Feature tracker | Tracker update behavior and generated status table |

## 2. Manual dashboard checks

Start the app using the [README setup instructions](../README.md#run-it), then open `http://127.0.0.1:8000`. Confirm `/api/health` returns `{"status":"ok"}` first.

| Screen | Steps | Expected result |
| --- | --- | --- |
| The story | Open tab 1 and wait for the cards and charts to load. | Four plain-language steps show the measured voltage context, solar impact, recommended fix, and day-ahead warning. Links move to the relevant screens. |
| Live map | Open tab 2. Choose the all-homes solar scenario (S4), press Play, then pause or move the time slider. | The clock and map update together; unsafe buses are marked; the voltage chart and power chart follow the selected time. |
| Fixes | Open tab 3. Select the combined tap +1 and Volt/VAR action and play the simulator. Compare the two maps, then inspect the ranked list. | Both sides replay the same time. The selected fix removes unsafe intervals in the default S4 case; the ranking reports safety and solar curtailment. |
| AI forecast | Open tab 4 and wait for the comparison to finish. | The day-ahead prediction and observed solar case are shown side by side, with solar/demand forecast curves and model metrics. The 2019 demand proxy is disclosed. |
| Hosting capacity | Open tab 5. | The page shows capacity with and without tap +1 and smart inverters, the adoption sweep, the no-solar baseline, and the 10% resolution and modeled-day limitation. |

Manual checks are a short smoke test, not exhaustive browser, mobile, accessibility, or real-feeder validation.

## 3. Results recorded for this revision

- Python: `pytest -q tests` — **26 passed**.
- Frontend: `npm run build` — **succeeded**. Vite reports a large-chunk advisory (>500 kB); it does not fail the build and is a performance follow-up.
- Setup smoke check: API health and dashboard root responded successfully after following the fresh-clone setup steps.
- Browser/device checks: use the manual checklist above; no cross-device result is claimed here.

## 4. Findings and bug report format

No functional defect was observed in the automated checks and setup smoke check recorded above. Keep newly reproduced defects here during a QA pass, and create a GitHub issue with the same details when the team triages the finding.

| ID / link | Severity | Status | Finding |
| --- | --- | --- | --- |
| — | — | No functional defects observed | The large Vite chunk advisory is a non-blocking performance follow-up, not a functional bug. |

When reporting a defect, include:

1. **Title and affected screen/API:** one concise description.
2. **Environment:** commit or branch, OS/browser, Python/Node versions as applicable.
3. **Reproduction:** numbered steps or the exact request and parameters.
4. **Expected result:** what should happen.
5. **Actual result:** what happened, including error text.
6. **Evidence:** screenshot, response body, or relevant log, with sensitive data removed.
7. **Impact:** who is blocked and how often it occurs.

## 5. Scope and interpretation

- The default checks use committed, precomputed data. Rebuilding from raw data is a separate, longer pipeline documented in the README.
- Forecast demand and upstream voltage use the same calendar day from the latest available 2019 meter data as a proxy for the 2025 forecast day; the UI labels this assumption.
- Hosting capacity is estimated in 10-percentage-point steps for one modeled benchmark day. It is not a surveyed feeder study or utility interconnection approval.
- A green test run means the checked software contracts and modeled results behave as expected; it does not validate all possible input dates, browsers, devices, or real electrical networks.
