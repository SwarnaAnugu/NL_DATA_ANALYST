import pytest
from eval.infra import is_infra_error, refuse_if_contaminated


def test_detects_infra_errors_but_not_model_behaviour():
    assert is_infra_error("BadRequestError(\"Error code: 400 - Your credit balance is too low\")")
    assert is_infra_error("RateLimitError('429')")
    assert is_infra_error("APIConnectionError('Connection error.')")
    assert not is_infra_error("no such column: foo")
    assert not is_infra_error("critic rejected the repaired query")
    assert not is_infra_error(None)


def test_contaminated_run_exits_nonzero_and_clean_run_passes(capsys):
    refuse_if_contaminated(0, 10)
    with pytest.raises(SystemExit) as e:
        refuse_if_contaminated(3, 10)
    assert e.value.code == 2 and "INVALID RUN" in capsys.readouterr().out
