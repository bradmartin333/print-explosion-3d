"""Every shipped sample design must still build, fit the A1 mini and read well in the UI.

These are the demo designs the README screenshots come from, the label template, and the test
fixtures that are meant to be good. If a change to the system prompt, the library or the checks
breaks "designs that used to be fine", this is where it shows up.
"""

from pathlib import Path

import pytest

from print_explosion_3d.api import params_payload
from print_explosion_3d.scad.estimate import analyze
from print_explosion_3d.scad.labels import label_sheet_scad
from print_explosion_3d.scad.params import parse_params
from print_explosion_3d.scad.runner import render
from print_explosion_3d.scad.stl import tile

ROOT = Path(__file__).resolve().parent.parent
# spice_jars_photo is a picture of a shelf for the README (scripts/screenshots.py renders it as a
# stand-in "photo"), not something to print.
NOT_PRINTABLE = {"spice_jars_photo"}
DEMOS = [
    p for p in sorted((ROOT / "scripts" / "demo").glob("*.scad")) if p.stem not in NOT_PRINTABLE
]
BLOCKING_WARNINGS = {"too_big", "floating", "sunk", "off_center", "missing_piece"}

pytestmark = pytest.mark.openscad


def _designs() -> list[tuple[str, str]]:
    designs = [(p.stem, p.read_text(encoding="utf-8")) for p in DEMOS]
    designs += [("labels-default", label_sheet_scad())]
    designs += [
        ("labels-many", label_sheet_scad(["Sugar", "Flour", "Cinnamon sticks", "Rice"] * 4))
    ]
    return designs


@pytest.fixture(scope="module", params=_designs(), ids=lambda d: d[0])
def built(request, tmp_path_factory):
    name, scad = request.param
    folder = tmp_path_factory.mktemp(name)
    src, out = folder / "model.scad", folder / "model.stl"
    src.write_text(scad, encoding="utf-8")
    result = render(src, out)
    return name, scad, result, out


def test_builds_cleanly_and_fits_the_printer(built):
    name, _scad, result, _out = built
    assert result.ok, f"{name}: {result.describe_problems()}"
    codes = {i.code for i in result.issues}
    assert not codes & BLOCKING_WARNINGS, f"{name}: {codes}"


def test_controls_are_explained_in_plain_english(built):
    name, scad, _result, _out = built
    shown = [p for p in parse_params(scad) if not p.hidden]
    assert shown, f"{name} has no controls"
    assert all(p.description for p in shown), f"{name}: a control has no explanation"
    assert params_payload(scad)


def test_printability_notes_are_quiet_and_copies_fit(built):
    name, _scad, _result, out = built
    info = analyze(out.read_bytes())
    assert info is not None and info.ready, f"{name}: {info and info.notes}"
    assert info.max_copies >= 1
    _, placed = tile(out.read_bytes(), 3)
    assert placed == min(3, info.max_copies)
