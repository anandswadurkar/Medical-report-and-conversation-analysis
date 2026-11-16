"""Pull lab results out of text and compare them with the report's own ranges.

Rules this module follows (workspace CLAUDE.md, section 2):

* Units are kept exactly as written. Nothing is converted, and no unit is inferred
  from how large a number is.
* A result is compared only with the reference range printed next to it. There is
  no built-in table of "normal" values, because ranges differ between labs, ages,
  sexes and methods. With no printed range, the status is ``NO_RANGE``.
* When the report's own flag (H, L, ...) disagrees with its printed range, the
  status is ``CONFLICT`` and the reader is told to ask, rather than one being picked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .detect import DocType
from .terms import GLOSSARY


class LabStatus(StrEnum):
    BELOW = "below range"
    WITHIN = "within range"
    ABOVE = "above range"
    NO_RANGE = "no range printed"
    UNCLEAR = "cannot tell"
    CONFLICT = "flag and range disagree"


@dataclass(frozen=True)
class LabResult:
    name: str
    value_text: str  # as written, including any < or > sign
    value: float
    comparator: str  # "", "<", "<=", ">", ">="
    unit: str  # as written, "" when none
    range_low: float | None
    range_high: float | None
    range_text: str  # as written
    report_flag: str  # as written in the report ("H", "L", "HIGH", ...), "" when none
    status: LabStatus
    line: str
    line_number: int  # 1-based


_NUMBER = r"-?\d+(?:\.\d+)?"
_ROW = re.compile(
    rf"^\s*(?P<name>[A-Za-z][A-Za-z0-9 ,'/()%+.\-]*?[A-Za-z0-9)%])\s*(?::|=|\.{{2,}}|\s{{1,}})\s*(?P<cmp><=|>=|<|>)?\s*(?P<value>{_NUMBER})(?![\d/:])(?P<rest>.*)$"
)
_UNIT = re.compile(
    r"^\s*(?P<unit>(?:x\s?10\^?\d+\s*/\s*[A-Za-zµu]+)|(?:10\^?\d+\s*/\s*[A-Za-zµu]+)|(?:[A-Za-zµ%][A-Za-z0-9µ%/^.*]*(?:/[A-Za-z0-9.]+)?))"
)
_RANGE = re.compile(rf"(?P<low>{_NUMBER})\s*(?:-|–|—|to)\s*(?P<high>{_NUMBER})")
_ONE_SIDED = re.compile(rf"(?P<op><=|>=|<|>)\s*(?P<limit>{_NUMBER})")
_FLAG = re.compile(r"(?<![A-Za-z])(?P<flag>HH|LL|H|L|HIGH|LOW|CRIT(?:ICAL)?|ABN(?:ORMAL)?|A|\*)(?![A-Za-z])\s*\)?\s*$")

# Names that look like "word number" lines but are not results.
_NOT_A_TEST = {
    "age",
    "dob",
    "date",
    "time",
    "mrn",
    "page",
    "phone",
    "fax",
    "room",
    "bed",
    "id",
    "accession",
    "account",
    "collected",
    "received",
    "reported",
    "printed",
    "specimen",
    "order",
    "zip",
    "visit",
    "encounter",
    "height",
    "weight",
    "temperature",
    "temp",
    "pulse",
    "bp",
    "hr",
    "rr",
    "spo2",
    "bmi",
    "patient",
    "sex",
    "gender",
}
_UNIT_WORDS_THAT_ARE_FLAGS = {"H", "L", "HH", "LL", "A", "HIGH", "LOW"}

# The lab-test names the glossary knows, used to accept rows that have no range.
_KNOWN_TESTS = {
    spelling.lower() for term in GLOSSARY if term.category == "lab test" for spelling in (term.term, *term.aliases)
}


def _status_from_range(value: float, comparator: str, low: float | None, high: float | None) -> LabStatus:
    if low is None and high is None:
        return LabStatus.NO_RANGE
    if comparator == "":
        if low is not None and value < low:
            return LabStatus.BELOW
        if high is not None and value > high:
            return LabStatus.ABOVE
        return LabStatus.WITHIN
    # "<0.01" means the true value is somewhere below 0.01. Only call it when every
    # value it could be falls on one side.
    if comparator in ("<", "<="):
        if low is not None and value <= low:
            return LabStatus.BELOW
        if low is None and high is not None and value <= high:
            return LabStatus.WITHIN
        return LabStatus.UNCLEAR
    if high is not None and value >= high:
        return LabStatus.ABOVE
    if high is None and low is not None and value >= low:
        return LabStatus.WITHIN
    return LabStatus.UNCLEAR


def _flag_direction(flag: str) -> str:
    upper = flag.upper()
    if upper in ("H", "HH", "HIGH"):
        return "high"
    if upper in ("L", "LL", "LOW"):
        return "low"
    return "abnormal"


def _reconcile(computed: LabStatus, flag: str) -> LabStatus:
    """Return CONFLICT when the report's flag contradicts its own range."""
    if not flag or computed in (LabStatus.NO_RANGE, LabStatus.UNCLEAR):
        return computed
    direction = _flag_direction(flag)
    if direction == "high" and computed is not LabStatus.ABOVE:
        return LabStatus.CONFLICT
    if direction == "low" and computed is not LabStatus.BELOW:
        return LabStatus.CONFLICT
    if direction == "abnormal" and computed is LabStatus.WITHIN:
        return LabStatus.CONFLICT
    return computed


def parse_lab_line(line: str, line_number: int = 1, require_known_name: bool = False) -> LabResult | None:
    """Parse one line as a lab result, or return None when it is not one.

    >>> r = parse_lab_line("Hemoglobin 10.9 g/dL (12.0-15.5) L")
    >>> (r.name, r.value, r.unit, r.range_low, r.range_high, r.report_flag, r.status.value)
    ('Hemoglobin', 10.9, 'g/dL', 12.0, 15.5, 'L', 'below range')
    >>> parse_lab_line("Collected: 03/14/2026 08:12") is None
    True
    """
    match = _ROW.match(line)
    if not match:
        return None
    name = match.group("name").strip(" .:")
    if name.lower() in _NOT_A_TEST or not re.search(r"[A-Za-z]{2,}", name):
        return None
    if len(name) > 40:  # a sentence with a number in it, not a result row
        return None
    comparator = match.group("cmp") or ""
    value_text = f"{comparator}{match.group('value')}"
    value = float(match.group("value"))
    rest = match.group("rest")

    unit = ""
    unit_match = _UNIT.match(rest)
    if unit_match and unit_match.group("unit").upper() not in _UNIT_WORDS_THAT_ARE_FLAGS:
        unit = unit_match.group("unit").rstrip(".,;")
        rest = rest[unit_match.end() :]

    flag_match = _FLAG.search(rest)
    report_flag = flag_match.group("flag") if flag_match else ""
    if flag_match:
        rest = rest[: flag_match.start()]

    low = high = None
    range_text = ""
    range_match = _RANGE.search(rest)
    if range_match:
        low, high = float(range_match.group("low")), float(range_match.group("high"))
        if low > high:
            raise ValueError(
                f"line {line_number}: reference range {range_match.group(0)!r} has its low end above its high end"
            )
        range_text = range_match.group(0)
    else:
        one_sided = _ONE_SIDED.search(rest)
        if one_sided:
            limit = float(one_sided.group("limit"))
            if one_sided.group("op").startswith("<"):
                high = limit
            else:
                low = limit
            range_text = one_sided.group(0)

    known = name.lower() in _KNOWN_TESTS or any(
        word.lower() in _KNOWN_TESTS for word in re.split(r"[ ,/()]+", name) if len(word) > 1
    )
    # Without a range or a recognised test name, "Size 1.2 cm" would become a lab
    # result, so such rows are dropped.
    if require_known_name and not known:
        return None
    if not range_text and not known:
        return None

    computed = _status_from_range(value, comparator, low, high)
    return LabResult(
        name=name,
        value_text=value_text,
        value=value,
        comparator=comparator,
        unit=unit,
        range_low=low,
        range_high=high,
        range_text=range_text,
        report_flag=report_flag,
        status=_reconcile(computed, report_flag),
        line=line.strip(),
        line_number=line_number,
    )


def extract_lab_results(text: str, doc_type: DocType = DocType.UNKNOWN) -> list[LabResult]:
    """Return every line of ``text`` that parses as a lab result.

    In a conversation, numbers come up in sentences ("my sugar was 140"); only rows
    with a recognised test name are taken there, to avoid turning chat into a table.
    """
    if doc_type is DocType.CONVERSATION:
        return []
    results = []
    for number, line in enumerate(text.splitlines(), start=1):
        result = parse_lab_line(line, number)
        if result is not None:
            results.append(result)
    return results
