"""Read and rearrange binary STL files (what OpenSCAD writes). Pure Python, no extra packages.

Everything here is local and instant: measuring a model, and laying several copies of it out on
the plate, never needs OpenSCAD or the AI.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from print_explosion_3d.scad.checks import BED_SIZE

_HEADER = 80
_RECORD = struct.Struct("<12fH")  # normal, 3 vertices, attribute bytes
_Triangle = tuple[float, float, float, float, float, float, float, float, float]

DEFAULT_GAP = 6.0  # mm between neighbouring copies on the plate
MAX_COPIES = 100


def read_triangles(data: bytes) -> list[_Triangle] | None:
    """The triangles of a binary STL as (x1, y1, z1, x2, y2, z2, x3, y3, z3). None if not one."""
    if len(data) < _HEADER + 4:
        return None
    (count,) = struct.unpack_from("<I", data, _HEADER)
    end = _HEADER + 4 + count * _RECORD.size
    if count == 0 or len(data) != end:
        return None
    return [rec[3:12] for rec in _RECORD.iter_unpack(data[_HEADER + 4 : end])]


@dataclass(frozen=True, slots=True)
class Footprint:
    """How much room one copy takes on the plate, and where its middle is."""

    width: float
    depth: float
    center_x: float
    center_y: float


def footprint(triangles: list[_Triangle]) -> Footprint:
    xs = [t[i] for t in triangles for i in (0, 3, 6)]
    ys = [t[i] for t in triangles for i in (1, 4, 7)]
    return Footprint(
        max(xs) - min(xs), max(ys) - min(ys), (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    )


def grid_for(
    fp: Footprint,
    bed: tuple[float, float, float] = BED_SIZE,
    gap: float = DEFAULT_GAP,
    margin: float = 5.0,
) -> tuple[int, int]:
    """(columns, rows) of copies that fit on the plate. (0, 0) when even one doesn't."""
    cols = int((bed[0] - 2 * margin + gap) // (fp.width + gap))
    rows = int((bed[1] - 2 * margin + gap) // (fp.depth + gap))
    return (cols, rows) if cols >= 1 and rows >= 1 else (0, 0)


def max_copies(data: bytes) -> int:
    """How many copies fit on the plate at once (at least 1, even if one is already too big)."""
    triangles = read_triangles(data)
    if triangles is None:
        return 1
    cols, rows = grid_for(footprint(triangles))
    return max(1, min(MAX_COPIES, cols * rows))


def tile(data: bytes, copies: int, gap: float = DEFAULT_GAP) -> tuple[bytes, int]:
    """Lay `copies` of the model out in a tidy grid centred on the plate.

    Returns (the new STL, how many copies it holds). If not all of them fit, it holds as many as
    do. One copy (or an unreadable file) comes back untouched.
    """
    triangles = read_triangles(data)
    if triangles is None or copies <= 1:
        return data, 1
    fp = footprint(triangles)
    cols_fit, rows_fit = grid_for(fp, gap=gap)
    if cols_fit * rows_fit < 1:
        return data, 1
    placed = max(1, min(copies, cols_fit * rows_fit, MAX_COPIES))
    cols = min(cols_fit, math.ceil(math.sqrt(placed)))
    rows = math.ceil(placed / cols)
    if rows > rows_fit:
        cols = cols_fit
        rows = math.ceil(placed / cols)

    pitch_x, pitch_y = fp.width + gap, fp.depth + gap
    out = bytearray(b"print-explosion-3d plate layout".ljust(_HEADER, b"\0"))
    out += struct.pack("<I", len(triangles) * placed)
    for n in range(placed):
        row, col = divmod(n, cols)
        in_row = min(cols, placed - row * cols)  # a short last row stays centred
        dx = (col - (in_row - 1) / 2) * pitch_x - fp.center_x
        dy = (row - (rows - 1) / 2) * pitch_y - fp.center_y
        for t in triangles:
            ax, ay, az, bx, by, bz, cx, cy, cz = t
            ux, uy, uz = bx - ax, by - ay, bz - az
            vx, vy, vz = cx - ax, cy - ay, cz - az
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            out += _RECORD.pack(
                nx / length, ny / length, nz / length,
                ax + dx, ay + dy, az, bx + dx, by + dy, bz, cx + dx, cy + dy, cz,
                0,
            )  # fmt: skip
    return bytes(out), placed
