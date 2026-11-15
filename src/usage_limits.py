"""Cost protection for a public demo: every question costs real API money.

Two caps: per browser session, and a global daily cap shared by everyone.
In-memory counters are enough here: a Streamlit Cloud app is one process, and
if it restarts the counters reset, which is acceptable for a portfolio demo."""
import os
import threading
from datetime import date

SESSION_LIMIT = int(os.environ.get("NL_SESSION_LIMIT", "15"))
DAILY_LIMIT = int(os.environ.get("NL_DAILY_LIMIT", "300"))

_lock = threading.Lock()
_daily = {"day": None, "count": 0}


def try_consume_daily() -> bool:
    """Reserve one question from today's global budget. False if exhausted."""
    with _lock:
        today = date.today()
        if _daily["day"] != today:
            _daily["day"], _daily["count"] = today, 0
        if _daily["count"] >= DAILY_LIMIT:
            return False
        _daily["count"] += 1
        return True


def reset_for_tests() -> None:
    with _lock:
        _daily["day"], _daily["count"] = None, 0
