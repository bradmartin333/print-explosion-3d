"""Size, print time, plastic and "will it print?" notes for a built model, in plain English.

All of it is rough on purpose ("~2 hr"): a volume-based guess for a 0.4 mm nozzle, PLA and a
light infill on a Bambu A1 mini. It never calls OpenSCAD, a slicer or the AI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from print_explosion_3d.scad.stl import read_triangles

PLA_DENSITY = 1.24  # g/cm3
WALL_MM = 1.2  # outer shell, as sliced
INFILL = 0.15
FLOW_MM3_PER_S = 6.0  # realistic average, not the nozzle's peak
LAYER_MM = 0.2
LAYER_OVERHEAD_S = 4.0
WARMUP_S = 150.0

OVERHANG_NORMAL_Z = -0.75  # a face tilted further out than ~45 degrees from upright
OVERHANG_MIN_AREA = 40.0  # mm2: smaller hanging patches bridge fine
OVERHANG_MIN_Z = 0.8  # skip the bottom chamfer
TALL_RATIO = 4.0
MM_PER_INCH = 25.4


@dataclass(frozen=True, slots=True)
class ModelInfo:
    size: tuple[float, float, float]  # mm
    volume: float  # mm3
    grams: float
    minutes: float
    overhang_area: float  # mm2 hanging out over nothing
    notes: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.notes


def _dims(values: tuple[float, ...], unit: str, scale: float = 1.0, digits: int = 0) -> str:
    sign = " \N{MULTIPLICATION SIGN} "
    return sign.join(f"{v / scale:.{digits}f}" for v in values) + f" {unit}"


def size_text(size: tuple[float, float, float]) -> str:
    return f"{_dims(size, 'mm')} ({_dims(size, 'in', MM_PER_INCH, 1)})"


def time_text(minutes: float) -> str:
    rounded = max(5, round(minutes / 5.0) * 5)
    hours, mins = divmod(rounded, 60)
    if hours and mins:
        return f"~{hours} hr {mins} min"
    return f"~{hours} hr" if hours else f"~{mins} min"


def analyze(data: bytes) -> ModelInfo | None:
    """Measure a binary STL. None if it can't be read."""
    triangles = read_triangles(data)
    if triangles is None:
        return None
    volume = area = overhang = 0.0
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    for ax, ay, az, bx, by, bz, cx, cy, cz in triangles:
        for x, y, z in ((ax, ay, az), (bx, by, bz), (cx, cy, cz)):
            lo[0], hi[0] = min(lo[0], x), max(hi[0], x)
            lo[1], hi[1] = min(lo[1], y), max(hi[1], y)
            lo[2], hi[2] = min(lo[2], z), max(hi[2], z)
        volume += (
            ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
        ) / 6
        ux, uy, uz = bx - ax, by - ay, bz - az
        vx, vy, vz = cx - ax, cy - ay, cz - az
        nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
        twice = math.sqrt(nx * nx + ny * ny + nz * nz)
        if twice == 0:
            continue
        tri_area = twice / 2
        area += tri_area
        if nz / twice < OVERHANG_NORMAL_Z and min(az, bz, cz) > OVERHANG_MIN_Z:
            overhang += tri_area
    volume = abs(volume)
    size = (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])

    shell = min(volume, area * WALL_MM)
    plastic = shell + INFILL * (volume - shell)  # mm3
    grams = plastic / 1000 * PLA_DENSITY
    seconds = WARMUP_S + plastic / FLOW_MM3_PER_S + size[2] / LAYER_MM * LAYER_OVERHEAD_S

    notes: list[str] = []
    if overhang > OVERHANG_MIN_AREA:
        notes.append("Parts hang over empty space and may need supports")
    footprint = min(size[0], size[1])
    if footprint > 0 and size[2] / footprint > TALL_RATIO:
        notes.append("Tall and narrow, so it may wobble or snap")
    return ModelInfo(size, volume, grams, seconds / 60, overhang, notes)
