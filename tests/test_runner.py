import os
import threading
from pathlib import Path

import pytest

from print_explosion_3d.scad.runner import (
    Renderer,
    find_openscad,
    parse_diagnostics,
    parse_version,
    render,
)

FIXTURES = Path(__file__).parent / "fixtures" / "scad"
HAVE_OPENSCAD = find_openscad(os.environ.get("OPENSCAD_BIN")) is not None
needs_openscad = [
    pytest.mark.openscad,
    pytest.mark.skipif(not HAVE_OPENSCAD, reason="OpenSCAD not installed"),
]


SLOW_SCAD = "for (i = [0:30]) for (j = [0:30])\n  translate([i, j, 0]) sphere(10, $fn=400);\n"


# --- pure parsing (no OpenSCAD needed) -------------------------------------------------------


def test_parse_diagnostics_extracts_lines_and_drops_noise():
    stderr = """\
WARNING: Ignoring unknown module 'foo' in file a.scad, line 2
ERROR: Assertion 'false' failed: "too big" in file a.scad, line 4
TRACE: called by 'assert' in file a.scad, line 4
ECHO: "hi"
ERROR: Parser error: syntax error in file b.scad, line 3
Can't parse file 'b.scad'!
WARNING: Bad range parameter in for statement: too many elements (5) in file a.scad, line 7
WARNING: Ignoring unknown module 'foo' in file a.scad, line 2
"""
    issues = parse_diagnostics(stderr)
    assert [(i.code, i.severity, i.line) for i in issues] == [
        ("missing_piece", "error", 2),  # promoted: the design builds wrong without it
        ("assertion", "error", 4),
        ("syntax", "error", 3),
        ("warning", "warning", 7),
    ]  # duplicates collapsed
    assert issues[0].message == "Ignoring unknown module 'foo'"
    assert issues[2].message == "syntax error"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("OpenSCAD version 2026.10.11", (2026, 10)),
        ("OpenSCAD version 2021.01", (2021, 1)),
        ("OpenSCAD version 2025.03.15.nightly", (2025, 3)),
        ("garbage", None),
    ],
)
def test_parse_version(text, expected):
    assert parse_version(text) == expected


def test_find_openscad_prefers_a_valid_configured_path(tmp_path):
    fake = tmp_path / "openscad"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    assert find_openscad(str(fake)) == fake


def test_find_openscad_ignores_a_bad_configured_path():
    # A typo in .env must not break the app: fall through to PATH/Applications (or None).
    assert find_openscad("/no/such/openscad") == find_openscad(None)


def test_missing_binary_is_a_result_not_an_exception(tmp_path, monkeypatch):
    monkeypatch.setattr("print_explosion_3d.scad.runner.find_openscad", lambda _=None: None)
    result = render(FIXTURES / "ok_box.scad", tmp_path / "o.stl")
    assert not result.ok
    assert result.issues[0].code == "no_openscad"


# --- real builds -----------------------------------------------------------------------------


def build(name, tmp_path, **kw):
    return render(FIXTURES / name, tmp_path / "out.stl", **kw)


class TestRealBuilds:
    pytestmark = needs_openscad

    def test_good_design_builds_with_bbox(self, tmp_path):
        r = build("ok_box.scad", tmp_path)
        assert r.ok and r.errors == [] and r.warnings == []
        assert r.stl_path == tmp_path / "out.stl"
        assert r.stl_path.stat().st_size == 84 + 50 * 12  # binary STL, 12 triangles
        assert r.bbox is not None
        assert r.bbox.size == (40, 30, 12)
        assert r.bbox.min == (-20, -15, 0)
        assert not (tmp_path / "out.stl.part").exists()

    def test_uses_bundled_lib(self, tmp_path):
        r = render(Path(__file__).parent / "fixtures" / "uses_lib.scad", tmp_path / "o.stl")
        assert r.ok, r.describe_problems()

    @pytest.mark.parametrize(
        ("name", "code", "line"),
        [
            ("syntax_error.scad", "syntax", 3),
            ("assert_fail.scad", "assertion", 2),
            ("unknown_module.scad", "missing_piece", 2),
            ("empty.scad", "empty", None),
            ("too_big.scad", "too_big", None),
            ("floating.scad", "floating", None),
            ("sunk.scad", "sunk", None),
            ("recursion.scad", "error", 1),
        ],
    )
    def test_bad_designs_fail_with_structured_errors(self, name, code, line, tmp_path):
        r = build(name, tmp_path)
        assert not r.ok
        assert r.stl_path is None
        assert not (tmp_path / "out.stl").exists()
        hit = [i for i in r.errors if i.code == code]
        assert hit, r.describe_problems()
        if line is not None:
            assert hit[0].line == line
        assert r.describe_problems()

    def test_off_center_builds_with_a_warning(self, tmp_path):
        r = build("off_center.scad", tmp_path)
        assert r.ok
        assert [i.code for i in r.warnings] == ["off_center"]

    def test_failed_build_keeps_the_last_good_stl(self, tmp_path):
        assert build("ok_box.scad", tmp_path).ok
        good = (tmp_path / "out.stl").read_bytes()
        assert not build("syntax_error.scad", tmp_path).ok
        assert (tmp_path / "out.stl").read_bytes() == good

    def test_timeout(self, tmp_path):
        slow = tmp_path / "slow.scad"
        slow.write_text(SLOW_SCAD)
        r = render(slow, tmp_path / "o.stl", timeout=0.3)
        assert [i.code for i in r.issues] == ["timeout"]

    def test_cancel(self, tmp_path):
        event = threading.Event()
        event.set()
        slow = tmp_path / "slow.scad"
        slow.write_text(SLOW_SCAD)
        r = render(slow, tmp_path / "o.stl", cancel=event)
        assert [i.code for i in r.issues] == ["cancelled"]

    def test_renderer_runs_in_background_and_calls_back(self, tmp_path):
        renderer = Renderer()
        done = threading.Event()
        seen = []

        def on_done(result):
            seen.append((threading.current_thread().name, result))
            done.set()

        future = renderer.submit(FIXTURES / "ok_box.scad", tmp_path / "o.stl", on_done)
        assert future.result(timeout=60).ok
        assert done.wait(5)
        assert seen[0][0].startswith("scad-render")
        assert seen[0][1].ok
        renderer.shutdown()
