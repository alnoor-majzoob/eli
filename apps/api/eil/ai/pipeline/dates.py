"""Due-date resolution (plan §8.7): ISO, relative phrases, ambiguous flag."""

from __future__ import annotations

import re
from datetime import date, timedelta

_ISO_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_RELATIVE_RE = re.compile(r"(?:in|after)\s+(\d+)\s+days?")
_DAYS_RE = re.compile(r"(\d+)\s+days?")
_AMBIGUOUS_RE = re.compile(
    r"(?:soon|asap|early next week|next week|próximo|قريبا|بعد وقت|soon after)",
    re.IGNORECASE,
)


def parse_due_text(text: str, anchor: date) -> tuple[date | None, bool]:
    """Parse a due phrase against ``anchor`` (artifact date); returns (date, ambiguous)."""
    match = _ISO_RE.search(text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3))), False
    lowered = text.lower().strip()
    match = _RELATIVE_RE.search(lowered) or _DAYS_RE.search(lowered)
    if match:
        return anchor + timedelta(days=int(match.group(1))), False
    if _AMBIGUOUS_RE.search(text):
        return None, True
    return None, True
