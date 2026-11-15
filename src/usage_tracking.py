"""Token and cost accounting per question.

Every LLM call goes through config.get_client(), which records the response's
token usage into the active Ledger. The ledger lives in a ContextVar so each
question gets its own, and worker threads share it via contextvars.copy_context()
(see orchestrator._submit).

Prices are USD per million tokens (input, output) and are ESTIMATES used for
the "≈ $0.01 per question" display; check Anthropic's pricing page for current
numbers. Extended-thinking tokens are billed as output and are included in
output_tokens by the API.
"""
import contextlib
import contextvars
import threading

PRICES = {"haiku": (1.0, 5.0), "sonnet": (3.0, 15.0), "opus": (15.0, 75.0)}
_DEFAULT_PRICE = PRICES["sonnet"]          # unknown models are priced conservatively high

_current = contextvars.ContextVar("usage_ledger", default=None)


def price_for(model: str) -> tuple:
    name = (model or "").lower()
    return next((p for key, p in PRICES.items() if key in name), _DEFAULT_PRICE)


class Ledger:
    def __init__(self):
        self._lock = threading.Lock()
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0

    def record(self, model: str, usage) -> None:
        inp = int(getattr(usage, "input_tokens", 0) or 0)
        out = int(getattr(usage, "output_tokens", 0) or 0)
        p_in, p_out = price_for(model)
        with self._lock:
            self.calls += 1
            self.input_tokens += inp
            self.output_tokens += out
            self.cost_usd += (inp * p_in + out * p_out) / 1_000_000

    def summary(self) -> dict:
        with self._lock:
            return {"calls": self.calls, "input_tokens": self.input_tokens,
                    "output_tokens": self.output_tokens, "cost_usd": round(self.cost_usd, 5)}


@contextlib.contextmanager
def track():
    """Start a fresh ledger for the current context. Usage: `with track() as led: ...; led.summary()`."""
    ledger = Ledger()
    token = _current.set(ledger)
    try:
        yield ledger
    finally:
        _current.reset(token)


def record_call(model: str, response) -> None:
    ledger = _current.get()
    usage = getattr(response, "usage", None)
    if ledger is not None and usage is not None:
        ledger.record(model, usage)
