# Release and rollback

**Release.**
1. Everything merged on `v2/build`; `python scripts/check.py` green (lint, tests, frontend build).
2. `python -m pytest -m perf`, `python -m pytest -m realdata`, and `npm run test` in `frontend/`.
3. `python -m scripts.evaluate` writes `data/results/results.json`; the Proof page and the documents quote only that
   file. `python -m scripts.demo_script` regenerates `docs/DEMO_SCRIPT.md` from it.
4. Open a pull request from `v2/build` to `main`; merge when CI is green.
5. Tag `main`: `git tag -a v2.x.y -m "..."` and `git push origin v2.x.y`.

**Rollback.**
- Code: `git checkout v2.0.0` (the first v2 release, which still contains the Round 1 dashboard and API) or a later
  tag. The last Round 1 state is commit `41df5d6` (`main` before v2 was merged).
- Cache: delete `data/results/v2/` so nothing computed by the newer code is served, then run
  `python -m scripts.nightly` to rebuild it.
- Models: `git checkout <tag> -- ml/models`.

**Who decides.** Both people, together, before the demo.
