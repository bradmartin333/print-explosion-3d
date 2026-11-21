"""Bed checks: does a built model fit the A1 mini and sit where Bambu Studio expects?"""

from __future__ import annotations

from print_explosion_3d.scad.models import BBox, Issue

# Keep in sync with `bed_size` in lib/printer-profile.scad (a test enforces this).
BED_SIZE: tuple[float, float, float] = (180.0, 180.0, 180.0)

_EPS = 1e-3  # float noise from the kernel; far below anything printable
_FLOOR_TOLERANCE = 0.01  # mm: how far from z = 0 still counts as resting on the plate
_CENTER_TOLERANCE = 1.0  # mm: off-centre by more than this earns a warning


def _dims(size: tuple[float, float, float]) -> str:
    return " x ".join(f"{v:.1f}".removesuffix(".0") for v in size) + " mm"


def check_bed(bbox: BBox, bed: tuple[float, float, float] = BED_SIZE) -> list[Issue]:
    """Return problems with `bbox`. Errors block the preview; warnings are advice."""
    size = bbox.size
    if any(v != v or v <= _EPS for v in size):  # NaN or flat in any axis
        return [Issue("empty", f"The design has no printable volume (measured {_dims(size)}).")]

    issues: list[Issue] = []

    if any(s > b + _EPS for s, b in zip(size, bed, strict=True)):
        issues.append(
            Issue(
                "too_big",
                f"The model is {_dims(size)} but the printer only fits {_dims(bed)}. "
                "Scale it down or split it into parts.",
            )
        )

    z = bbox.min[2]
    if z > _FLOOR_TOLERANCE:
        issues.append(
            Issue(
                "floating",
                f"The model floats {z:.2f} mm above the plate. Its lowest point must be at z = 0.",
            )
        )
    elif z < -_FLOOR_TOLERANCE:
        issues.append(
            Issue(
                "sunk",
                f"Part of the model is {-z:.2f} mm below the plate. "
                "Its lowest point must be at z = 0.",
            )
        )

    cx, cy = bbox.center_xy
    if abs(cx) > _CENTER_TOLERANCE or abs(cy) > _CENTER_TOLERANCE:
        issues.append(
            Issue(
                "off_center",
                f"The model is centred at x = {cx:.1f}, y = {cy:.1f} instead of the middle "
                "of the plate (0, 0).",
                severity="warning",
            )
        )

    return issues
