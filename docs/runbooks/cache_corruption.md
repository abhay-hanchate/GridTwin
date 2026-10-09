# Cache corruption or stale results

**Symptom.** A precomputed case returns an error, a `running` state that never finishes, or numbers that do not
match a fresh run.

**Check.**
1. Cache keys include the code version (`sha256(date|network|rule|fix|code_version)`), so a code change cannot
   serve old results; a mismatch points at damaged files.
2. Look under `data/results/v2/` *(API, Phase 8)*: a zero-byte or truncated JSON file is the usual cause.
3. `GET /api/v2/readiness` reports missing data, models or cache *(API, Phase 8)*.

**Fix.**
1. Delete the damaged file, or the whole `data/results/v2/` folder.
2. Rebuild with `python scripts/nightly.py` *(Phase 8)*. Meanwhile a cache miss starts a background job, so users
   see `running` rather than an error.

**Who decides.** Anyone may delete and rebuild the cache; it holds nothing that cannot be recomputed.
