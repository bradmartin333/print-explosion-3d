import struct

from print_explosion_3d.scad.estimate import ModelInfo, size_text, time_text
from print_explosion_3d.scad.estimate import analyze as _analyze
from print_explosion_3d.scad.labels import label_sheet_scad, parse_names
from print_explosion_3d.scad.params import parse_params
from print_explosion_3d.scad.stl import read_triangles


def analyze(data: bytes) -> ModelInfo:
    info = _analyze(data)
    assert info is not None
    return info


def box(w, d, h, z0=0.0):
    x, y = w / 2, d / 2
    v = [(-x, -y, z0), (x, -y, z0), (x, y, z0), (-x, y, z0)]
    v += [(a, b, z0 + h) for a, b, _ in v]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    tris = [t for a, b, c, d_ in quads for t in ((a, b, c), (a, c, d_))]
    out = b"\0" * 80 + struct.pack("<I", len(tris))
    for t in tris:
        out += struct.pack("<12fH", 0, 0, 0, *[c for i in t for c in v[i]], 0)
    return out


def test_read_rejects_junk():
    assert read_triangles(b"") is None
    assert read_triangles(b"x" * 200) is None
    assert len(read_triangles(box(10, 10, 10)) or []) == 12


def test_analyze_measures_a_box():
    info = analyze(box(40, 20, 10))
    assert info.volume == 8000 or abs(info.volume - 8000) < 1e-3
    assert [round(v) for v in info.size] == [40, 20, 10]
    assert info.ready
    assert size_text(info.size) == "40 {0} 20 {0} 10 mm (1.6 {0} 0.8 {0} 0.4 in)".format(
        "\N{MULTIPLICATION SIGN}"
    )


def test_overhangs_and_tall_parts_get_a_heads_up():
    shelf = analyze(box(60, 60, 5, z0=30))  # a slab floating in mid-air: its underside hangs
    assert any("supports" in n for n in shelf.notes) and not shelf.ready
    tall = analyze(box(10, 10, 80))
    assert any("Tall and narrow" in n for n in tall.notes)


def test_time_text():
    assert time_text(2) == "~5 min"
    assert time_text(130) == "~2 hr 10 min"
    assert time_text(120) == "~2 hr"


def test_labels_parse_and_template_parses():
    assert parse_names("Sugar, flour and Salt.") == ["Sugar", "flour", "Salt"]
    assert parse_names("") == []
    scad = label_sheet_scad(['A "quote"', "B"])
    params = {p.name: p for p in parse_params(scad)}
    assert params["names"].value == "A quote, B" and params["names"].max_length == 200
    assert all(p.description for p in params.values() if p.section != "Hidden")
