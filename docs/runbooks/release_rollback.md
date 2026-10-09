# Release and rollback

**Release.**
1. Everything merged on `v2/build`; `python scripts/check.py` green (lint, tests, frontend build).
2. `python -m pytest -m perf`, `python -m pytest -m realdata`, and `npm run test` in `frontend/`.
3. `python scripts/evaluate.py` writes `data/results/results.json` *(task P10.4)*; the Proof page and the
   documents quote only that file.
4. Tag: `git tag v2.0.0`.

**Rollback.**
- Code: `git checkout v1-baseline` (the Round 1 demo, tagged at commit 3977cbb) or the previous v2 tag.
- Dashboard only: the Round 1 dashboard is the default build; the v2 layout appears only when built with
  `VITE_DASHBOARD=v2`, so rebuilding without it returns to Round 1.
- Cache: delete `data/results/v2/` so nothing computed by the newer code is served *(Phase 8)*.
- Models: `git checkout <tag> -- ml/models`.

**Who decides.** Both people, together, before the demo.
