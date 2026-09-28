# GridTwin

**HackMatrix 5.0 · ENR-02 — Renewable Distribution Grid Digital Twin**

GridTwin simulates a low-voltage distribution feeder under growing rooftop solar using real Indian household demand and real solar data, detects unsafe voltage, and recommends corrective actions that it has re-simulated and verified — or honestly reports that no safe action exists.

> Work in progress. Setup, architecture and results are added as each feature lands.

## Repository layout

| Folder | Purpose |
| --- | --- |
| `engine/` | Data profiles, grid model, power flow, corrective actions, ranking |
| `ml/` | Solar and demand forecasting |
| `backend/` | FastAPI service |
| `frontend/` | React dashboard |
| `scripts/` | Data download and precompute scripts |
| `tests/` | Engine, API and regression tests |
| `docs/` | Assumptions and methodology |
