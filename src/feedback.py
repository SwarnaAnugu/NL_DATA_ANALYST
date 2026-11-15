"""Append-only thumbs up/down log. One JSON object per line."""
import json
import time
from pathlib import Path

from config import REPO_ROOT

FEEDBACK_PATH = REPO_ROOT / "data" / "feedback.jsonl"


def record_feedback(question: str, sql: str | None, rating: str, path: Path = FEEDBACK_PATH) -> None:
    """rating is 'up' or 'down'. Never raises: feedback must not break the app."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"ts": time.time(), "question": question, "sql": sql, "rating": rating}
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass
