"""Answer cache: identical questions are answered instantly and for free.

Why it is safe: the dataset is static, so an answer never goes stale. Only
successful answers are cached (a failure or a clarifying question is never
replayed). The benchmark and scenario runners call disable() so repeats measure
the real pipeline, not the cache.

The cache can be pre-warmed from a JSON file (see eval/warm_cache.py), which
makes the demo's example buttons instant, free, and independent of the API.
"""
import copy
import json
import re
import threading
from collections import OrderedDict
from pathlib import Path

MAX_ENTRIES = 256

_lock = threading.Lock()
_entries: "OrderedDict[str, dict]" = OrderedDict()
_enabled = True


def normalize(question: str) -> str:
    """Case, whitespace and trailing punctuation don't change a question's meaning."""
    q = re.sub(r"\s+", " ", (question or "").strip().lower())
    return q.rstrip("?!. ").strip()


def disable() -> None:
    global _enabled
    _enabled = False


def enable() -> None:
    global _enabled
    _enabled = True


def clear() -> None:
    with _lock:
        _entries.clear()


def get(question: str):
    """Return a copy of the cached result, or None."""
    if not _enabled:
        return None
    key = normalize(question)
    with _lock:
        hit = _entries.get(key)
        if hit is None:
            return None
        _entries.move_to_end(key)
        return copy.deepcopy(hit)


def contains(question: str) -> bool:
    if not _enabled:
        return False
    with _lock:
        return normalize(question) in _entries


def put(question: str, result: dict) -> None:
    """Cache a successful result only."""
    if not _enabled or result.get("status") != "success":
        return
    with _lock:
        _entries[normalize(question)] = copy.deepcopy(result)
        _entries.move_to_end(normalize(question))
        while len(_entries) > MAX_ENTRIES:
            _entries.popitem(last=False)


def save_file(path: Path) -> int:
    with _lock:
        payload = [{"question": q, "result": r} for q, r in _entries.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, default=str))
    return len(payload)


def load_file(path: Path) -> int:
    """Load pre-warmed answers. A missing or corrupt file loads nothing (never raises)."""
    try:
        payload = json.loads(Path(path).read_text())
        loaded = 0
        for item in payload:
            result = item["result"]
            if result.get("status") == "success":
                result["rows"] = [tuple(r) for r in result.get("rows", [])]
                with _lock:
                    _entries[item["question"]] = result
                loaded += 1
        return loaded
    except (OSError, ValueError, KeyError, TypeError):
        return 0
