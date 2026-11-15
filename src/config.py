"""Central configuration: paths, model names, and a lazily-created API client.

Why a lazy client? Creating anthropic.Anthropic() at import time crashes the
whole app if the key is missing, and makes the pipeline impossible to test
without network access. get_client() builds it on first use and tests can
swap it out with set_client().
"""
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

DB_PATH = REPO_ROOT / os.environ.get("DATABASE_PATH", "data/nl_data_analyst.db")

# Model routing: Haiku for high-frequency narrow classification,
# Sonnet for SQL generation, critique and explanation.
FAST_MODEL = os.environ.get("NL_FAST_MODEL", "claude-haiku-4-5")
SMART_MODEL = os.environ.get("NL_SMART_MODEL", "claude-sonnet-4-6")

# Execution guardrails
MAX_QUESTION_CHARS = 600  # longer input is rejected before any API call
MAX_ROWS = 1000          # rows returned to the app; more are cut off and flagged
QUERY_TIMEOUT_S = 10     # wall-clock limit per query

DEMO_DB_ARCHIVE = REPO_ROOT / "demo_data" / "nl_data_analyst.db.xz"

_client = None


def ensure_db() -> Path:
    """Make sure the SQLite file exists. The real database is gitignored, so on
    a fresh clone (or a Streamlit Cloud deploy) we unpack the compressed copy
    committed under demo_data/ the first time the app starts."""
    if DB_PATH.exists():
        return DB_PATH
    if not DEMO_DB_ARCHIVE.exists():
        raise FileNotFoundError(
            f"No database at {DB_PATH} and no archive at {DEMO_DB_ARCHIVE}. "
            "Run: python src/db/load_data.py (needs the Olist CSVs in data/)."
        )
    import lzma
    import shutil
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB_PATH.with_suffix(".tmp")
    with lzma.open(DEMO_DB_ARCHIVE, "rb") as src, open(tmp, "wb") as dst:
        shutil.copyfileobj(src, dst)
    tmp.replace(DB_PATH)   # atomic: a half-written file never looks like a database
    return DB_PATH


class _TrackedMessages:
    def __init__(self, inner):
        self._inner = inner

    def create(self, **kwargs):
        response = self._inner.messages.create(**kwargs)
        from usage_tracking import record_call
        record_call(kwargs.get("model", ""), response)
        return response


class _TrackedClient:
    """Thin wrapper so every LLM call is recorded in the active usage ledger."""
    def __init__(self, inner):
        self.messages = _TrackedMessages(inner)


def get_client():
    global _client
    if _client is None:
        import anthropic
        # A stalled call must not hang the demo: 60s per request, 2 automatic retries.
        _client = anthropic.Anthropic(timeout=60.0, max_retries=2)
    return _TrackedClient(_client)


def set_client(client) -> None:
    """Swap the API client (used by tests)."""
    global _client
    _client = client
