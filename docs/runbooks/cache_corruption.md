# Cache corruption or stale results

**Symptom.** A precomputed case returns an error, a `running` state that never finishes, or numbers that do not
match a fresh run. With `GRIDTWIN_OFFLINE=1`, every page answers "offline mode serves only precomputed results".

**Check.**
1. Cache keys include the code version (a hash of `engine/` and `backend/v2/compute.py`), so a code change cannot
   serve old results. It also means the committed offline demo goes stale after any engine commit: the nightly
   workflow's step "Is the committed offline demo current?" warns about it, or compare by hand:
   `python -c "from backend.v2.settings import results_version; print(results_version())"` against
   `code_version` in `data/results/v2/index.json`.
2. Look under `data/results/v2/`: a zero-byte or truncated JSON file is the usual cause of damage.
3. `GET /api/v2/readiness` reports missing data, models or the precomputed index.

**Fix.**
1. Stale demo: `python -m scripts.nightly` (about half an hour: the fix tournaments and hosting capacity are the
   slow parts), then commit `data/results/v2`.
2. Damaged file: delete it, or the whole `data/results/v2/` folder, and rebuild as in step 1. Meanwhile, online, a
   cache miss starts a background job, so users see `running` rather than an error.
3. The evening run on GitHub (workflow "Nightly", job `evening`) uploads its results as the artifact
   `evening-<run id>`; downloading it into `data/results/v2` is an alternative to rebuilding locally.

**Who decides.** Anyone may delete and rebuild the cache; it holds nothing that cannot be recomputed. The engine
owner (Person A) commits the refreshed demo after an engine change.
