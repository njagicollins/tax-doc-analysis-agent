"""Mask personal data before any text is sent to an LLM.

Names become employee IDs (the LLM can still say "E007", and humans can look
that up). SSNs are removed completely. A final guard refuses to send anything
that still looks like an SSN or a known name.
"""

import re

SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
SSN_MASK = "[SSN]"


class PiiLeakError(Exception):
    """Text about to leave the system still contains personal data."""


def name_pattern(name: str) -> re.Pattern[str]:
    """Whole names only: "Ann Lee" must not match inside "Joann Leeds"."""
    return re.compile(rf"\b{re.escape(name)}\b", flags=re.IGNORECASE)


def mask(text: str, roster: dict[str, str]) -> str:
    """Replace every known name with its employee ID, and every SSN with [SSN].

    roster maps employee ID -> full name, e.g. {"E001": "Patrick Sanchez"}.
    """
    # Longest names first, so "Ann Lee-Smith" is replaced before "Ann Lee"
    for employee_id, name in sorted(roster.items(), key=lambda item: -len(item[1])):
        text = name_pattern(name).sub(employee_id, text)
    return SSN.sub(SSN_MASK, text)


def assert_no_pii(text: str, roster: dict[str, str]) -> None:
    """Last line of defence: fail loudly instead of sending personal data."""
    if SSN.search(text):
        raise PiiLeakError("text still contains an SSN")
    for employee_id, name in roster.items():
        if name_pattern(name).search(text):
            # Name the employee ID, never the person: error messages get logged
            raise PiiLeakError(f"text still contains the name of {employee_id}")
