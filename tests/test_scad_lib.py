import os
import shutil
import subprocess
from pathlib import Path

import pytest

from print_explosion_3d.config import SCAD_LIB_DIR

FIXTURES = Path(__file__).parent / "fixtures"
OPENSCAD = os.environ.get("OPENSCAD_BIN") or shutil.which("openscad")

pytestmark = [
    pytest.mark.openscad,
    pytest.mark.skipif(OPENSCAD is None, reason="OpenSCAD not installed"),
]


def test_bundled_lib_renders_with_manifold(tmp_path):
    assert OPENSCAD is not None
    out = tmp_path / "out.stl"
    result = subprocess.run(
        [
            OPENSCAD,
            "--backend",
            "Manifold",
            "--export-format",
            "binstl",
            "-o",
            str(out),
            str(FIXTURES / "uses_lib.scad"),
        ],
        env={**os.environ, "OPENSCADPATH": str(SCAD_LIB_DIR)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "ERROR" not in result.stderr
    # Binary STL: 80-byte header + 4-byte count + 50 bytes per triangle.
    assert out.stat().st_size > 84 + 50 * 12
