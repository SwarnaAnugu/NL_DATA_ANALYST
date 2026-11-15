"""Detects API/infrastructure failures so they are never scored as model behaviour.

A run where the key ran out of credit, was rate limited, or lost network would
otherwise look like "the pipeline abstained on 38% of questions". Both runners
refuse to publish results from such a run."""

INFRA_MARKERS = (
    "BadRequestError", "AuthenticationError", "PermissionDeniedError", "RateLimitError",
    "APIConnectionError", "APITimeoutError", "InternalServerError", "OverloadedError",
    "APIStatusError", "credit balance",
)


def is_infra_error(detail) -> bool:
    return bool(detail) and any(m in str(detail) for m in INFRA_MARKERS)


def refuse_if_contaminated(infra_count: int, total: int) -> None:
    """Exit loudly (code 2) instead of writing misleading results."""
    if infra_count:
        print(f"\n!! INVALID RUN: {infra_count} of {total} jobs failed because of API/infrastructure errors "
              "(credit balance, rate limit, network or auth), not because of model behaviour.\n"
              "!! Results were NOT written, so your previous results are untouched. Fix the cause and re-run.")
        raise SystemExit(2)
