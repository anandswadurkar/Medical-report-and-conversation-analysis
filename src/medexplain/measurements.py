"""Find sizes written in millimetres or centimetres and give them in inches.

Only explicit metric length units are read; a bare number is never treated as a
size. The conversion is exact (1 inch = 25.4 mm by definition).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MM_PER_INCH = 25.4
_MM_PER_UNIT = {"mm": 1.0, "cm": 10.0}

_NUMBER = r"\d+(?:\.\d+)?"
_SIZE = re.compile(
    rf"(?<![\w.])(?P<dims>{_NUMBER}(?:\s*(?:x|×|by)\s*{_NUMBER}){{0,2}})\s*(?P<unit>mm|cm)(?![A-Za-z])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Measurement:
    text: str
    dimensions_mm: tuple[float, ...]
    unit: str  # as written
    start: int

    @property
    def largest_mm(self) -> float:
        return max(self.dimensions_mm)

    @property
    def plain(self) -> str:
        """The size in inches, for example 'about 0.16 inches (4 mm)'."""
        inches = [mm / MM_PER_INCH for mm in self.dimensions_mm]
        rendered = " x ".join(f"{value:.2g}" if value < 1 else f"{value:.1f}" for value in inches)
        return f"about {rendered} inches ({self.text})"


def find_measurements(text: str) -> list[Measurement]:
    """Return every metric size in ``text``.

    >>> [m.dimensions_mm for m in find_measurements("A 4 mm nodule and a 1.2 x 0.8 cm cyst.")]
    [(4.0,), (12.0, 8.0)]
    """
    found = []
    for match in _SIZE.finditer(text):
        unit = match.group("unit").lower()
        numbers = re.findall(_NUMBER, match.group("dims"))
        dimensions = tuple(float(number) * _MM_PER_UNIT[unit] for number in numbers)
        found.append(Measurement(match.group(0), dimensions, match.group("unit"), match.start()))
    return found


def unique_measurements(measurements: list[Measurement]) -> list[Measurement]:
    """Drop repeats of the same size (reports restate sizes in the impression)."""
    seen: set[tuple[float, ...]] = set()
    unique = []
    for measurement in measurements:
        if measurement.dimensions_mm not in seen:
            seen.add(measurement.dimensions_mm)
            unique.append(measurement)
    return unique
