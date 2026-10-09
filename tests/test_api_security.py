import json

import pytest

from backend.cache import CorruptCacheError, cache_path, load_or_compute


@pytest.mark.parametrize("key", ["../escape", "folder/name", r"folder\name", "name with spaces"])
def test_cache_key_rejects_traversal_and_separators(tmp_path, key):
    with pytest.raises(ValueError):
        cache_path(tmp_path, key)


def test_cache_write_is_valid_json_and_reused(tmp_path):
    calls = 0

    def compute():
        nonlocal calls
        calls += 1
        return {"value": 7}

    assert load_or_compute(tmp_path, "safe-key", compute) == {"value": 7}
    assert json.loads((tmp_path / "safe-key.json").read_text()) == {"value": 7}
    assert load_or_compute(tmp_path, "safe-key", compute) == {"value": 7}
    assert calls == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_corrupt_cache_fails_closed(tmp_path):
    (tmp_path / "broken.json").write_text("not json")
    with pytest.raises(CorruptCacheError):
        load_or_compute(tmp_path, "broken", lambda: {"replacement": True})


