"""Small value types shared by the OpenSCAD runner and the bed checks."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class Issue:
    """One problem found while building or checking a design.

    `code` is a stable machine-readable tag (the UI and the designer branch on it); `message` is
    plain text written for the AI fix round-trip, never shown to the end user as-is.
    """

    code: str
    message: str
    severity: Severity = "error"
    line: int | None = None
    file: str | None = None

    def __str__(self) -> str:
        where = f" (line {self.line})" if self.line is not None else ""
        return f"{self.message}{where}"


@dataclass(frozen=True, slots=True)
class BBox:
    """Axis-aligned bounding box in millimetres."""

    min: tuple[float, float, float]
    max: tuple[float, float, float]

    @classmethod
    def of(cls, lo: Sequence[float], hi: Sequence[float]) -> BBox:
        return cls(
            (float(lo[0]), float(lo[1]), float(lo[2])),
            (float(hi[0]), float(hi[1]), float(hi[2])),
        )

    @property
    def size(self) -> tuple[float, float, float]:
        return (
            self.max[0] - self.min[0],
            self.max[1] - self.min[1],
            self.max[2] - self.min[2],
        )

    @property
    def center_xy(self) -> tuple[float, float]:
        return ((self.min[0] + self.max[0]) / 2, (self.min[1] + self.max[1]) / 2)
