"""Cache-or-job for heavy v2 results.

A request either finds its result on disk (results_dir/v2/<key>.json, written atomically) or starts one background
job; identical requests share that job. Cache keys include the code version, so a code change never serves a stale
result. index.json lists what the nightly run precomputed (used for the default date).
"""
from __future__ import annotations

import hashlib
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from backend.cache import cache_path, load_or_compute
from backend.v2 import metrics

STATES = ("queued", "running", "done", "failed")


def cache_key(route: str, version: str, **params) -> str:
    text = "|".join([route, version] + [f"{k}={params[k]}" for k in sorted(params)])
    return f"{route}_{hashlib.sha256(text.encode()).hexdigest()[:20]}"


class JobStore:
    def __init__(self, results_dir: Path, workers: int = 2):
        self.dir = Path(results_dir) / "v2"
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="gridtwin-job")
        self.lock = threading.Lock()
        self.jobs: dict[str, dict] = {}            # job id -> {"status", "key", "result"?, "error"?}
        self.by_key: dict[str, str] = {}           # cache key -> job id still in flight

    def cached(self, key: str) -> dict | None:
        path = cache_path(self.dir, key)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def get_or_submit(self, key: str, compute: Callable[[], dict]) -> tuple[dict | None, dict | None]:
        """(result, None) when cached; (None, job) when a job runs (new or shared)."""
        result = self.cached(key)
        if result is not None:
            metrics.CACHE.labels("hit").inc()
            return result, None
        metrics.CACHE.labels("miss").inc()
        with self.lock:
            if key in self.by_key:
                return None, self.view(self.by_key[key])
            job_id = uuid.uuid4().hex[:12]
            self.jobs[job_id] = {"status": "queued", "key": key}
            self.by_key[key] = job_id
            metrics.JOBS_QUEUED.inc()
        self.pool.submit(self._run, job_id, key, compute)
        return None, self.view(job_id)

    def _run(self, job_id: str, key: str, compute: Callable[[], dict]) -> None:
        self.jobs[job_id]["status"] = "running"
        try:
            result = load_or_compute(self.dir, key, compute)
            self.jobs[job_id].update(status="done", result=result)
        except Exception as exc:                     # the message is shown; the trace stays in the server log
            import logging
            logging.getLogger("gridtwin.v2").exception("job %s failed", job_id)
            self.jobs[job_id].update(status="failed", error=getattr(exc, "message", None) or str(exc))
        finally:
            with self.lock:
                self.by_key.pop(key, None)
                metrics.JOBS_QUEUED.dec()

    def view(self, job_id: str) -> dict | None:
        job = self.jobs.get(job_id)
        if job is None:
            return None
        out = {"job_id": job_id, "status": job["status"]}
        if job["status"] == "done":
            out["result"] = job["result"]
        if job["status"] == "failed":
            out["error"] = job["error"]
        return out

    def index(self) -> dict:
        path = self.dir / "index.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"entries": []}
