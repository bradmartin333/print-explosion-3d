"""Read binary STL files (what OpenSCAD writes). Pure Python, no extra packages."""

from __future__ import annotations

import struct

_HEADER = 80
_RECORD = struct.Struct("<12fH")  # normal, 3 vertices, attribute bytes
_Triangle = tuple[float, float, float, float, float, float, float, float, float]


def read_triangles(data: bytes) -> list[_Triangle] | None:
    """The triangles of a binary STL as (x1, y1, z1, x2, y2, z2, x3, y3, z3). None if not one."""
    if len(data) < _HEADER + 4:
        return None
    (count,) = struct.unpack_from("<I", data, _HEADER)
    end = _HEADER + 4 + count * _RECORD.size
    if count == 0 or len(data) != end:
        return None
    return [rec[3:12] for rec in _RECORD.iter_unpack(data[_HEADER + 4 : end])]
