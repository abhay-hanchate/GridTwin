"""Safe, atomic JSON caching for compute-heavy API responses."""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Callable

CACHE_KEY = re.compile(r"^[A-Za-z0-9_.-]+$")


class CorruptCacheError(RuntimeError):
    pass


def cache_path(directory: Path, key: str) -> Path:
    """Resolve a cache path and reject separators or traversal before touching disk."""
    if not CACHE_KEY.fullmatch(key):
        raise ValueError("cache key contains unsupported characters")
    root = directory.resolve()
    path = (root / f"{key}.json").resolve()
    if path.parent != root:
        raise ValueError("cache path escapes the results directory")
    return path


def load_or_compute(directory: Path, key: str, compute: Callable[[], dict]) -> dict:
    path = cache_path(directory, key)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CorruptCacheError(f"cached result {path.name} is unreadable") from exc

    result = compute()
    directory.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return result
