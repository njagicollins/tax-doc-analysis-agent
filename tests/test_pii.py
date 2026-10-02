import pytest

from taxagent.agent.pii import PiiLeakError, assert_no_pii, mask

ROSTER = {"E001": "Patrick Sanchez", "E002": "Ann Lee", "E003": "Ann Lee-Smith"}


def test_names_become_employee_ids():
    text = "Patrick Sanchez was paid a bonus."

    assert mask(text, ROSTER) == "E001 was paid a bonus."


def test_ssns_are_removed():
    assert mask("SSN 143-95-1680 on file", ROSTER) == "SSN [SSN] on file"


def test_matching_ignores_case():
    assert mask("PATRICK SANCHEZ", ROSTER) == "E001"


def test_longer_names_are_replaced_first():
    assert mask("Ann Lee-Smith and Ann Lee", ROSTER) == "E003 and E002"


def test_names_inside_other_words_are_left_alone():
    assert mask("Joann Leeds", ROSTER) == "Joann Leeds"


def test_masked_text_passes_the_guard():
    text = mask("Patrick Sanchez, 143-95-1680", ROSTER)

    assert_no_pii(text, ROSTER)  # no error


@pytest.mark.parametrize(
    "leaky", ["Employee 143-95-1680", "about Patrick Sanchez", "ann lee"]
)
def test_guard_refuses_personal_data(leaky):
    with pytest.raises(PiiLeakError):
        assert_no_pii(leaky, ROSTER)


def test_guard_error_does_not_repeat_the_personal_data():
    with pytest.raises(PiiLeakError) as error:
        assert_no_pii("about Patrick Sanchez", ROSTER)

    assert "Patrick" not in str(error.value)
