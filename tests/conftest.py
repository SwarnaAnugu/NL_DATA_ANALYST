import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import config  # noqa: E402

config.ensure_db()   # unpack the demo database on a fresh clone / CI


class FakeLLM:
    """Stand-in for the Anthropic client. Routes on the system prompt so each
    pipeline stage gets a scripted reply. `sql_queue` is consumed by SQL
    generation calls in order; `critiques` by critique calls."""

    def __init__(self, scope=True, ambiguous=False, sql_queue=(), critiques=(), caveat=None, rewrite=None):
        self.scope, self.ambiguous = scope, ambiguous
        self.sql_queue = list(sql_queue)
        self.critiques = list(critiques)
        self.caveat = caveat
        self.rewrite = rewrite          # standalone question returned for follow-ups (None = unchanged)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    @staticmethod
    def _resp(text):
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])

    def _create(self, **kw):
        import json
        system = kw.get("system", "")
        self.calls.append(system[:40])
        if "rewrite follow-up messages" in system:
            if self.rewrite == "BOOM":
                raise RuntimeError("rewrite service down")
            last = kw["messages"][0]["content"].rsplit("New message: ", 1)[1]
            return self._resp(json.dumps({"standalone_question": self.rewrite or last,
                                          "was_rewritten": self.rewrite is not None}))
        if "gatekeeper" in system:
            return self._resp(json.dumps({"is_in_scope": self.scope, "reason": "x"}))
        if "checking whether a natural-language question" in system:
            return self._resp(json.dumps({"is_ambiguous": self.ambiguous,
                                          "clarifying_question": "Best by what?" if self.ambiguous else None,
                                          "reasoning": "x"}))
        if "writing SQLite queries" in system:
            return self._resp(self.sql_queue.pop(0))
        if "reviewing a SQL query" in system:
            return self._resp(json.dumps(self.critiques.pop(0)))
        if "explaining a database query result" in system:
            return self._resp("Here is the answer.")
        if "misleading due to known structural limitations" in system:
            return self._resp(json.dumps({"needs_caveat": self.caveat is not None, "reason": None,
                                          "caveat_text": self.caveat}))
        raise AssertionError(f"unrecognised stage: {system[:60]}")


@pytest.fixture
def fake_llm():
    def install(**kw):
        fake = FakeLLM(**kw)
        config.set_client(fake)
        return fake
    yield install
    config.set_client(None)


@pytest.fixture(autouse=True)
def _fresh_answer_cache():
    """Every test starts with an empty, enabled cache so tests can't leak answers."""
    import answer_cache
    answer_cache.enable()
    answer_cache.clear()
    yield
    answer_cache.enable()
    answer_cache.clear()
