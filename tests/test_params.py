from pathlib import Path

import pytest

from print_explosion_3d.scad.params import (
    Option,
    ParamError,
    apply_values,
    parse_params,
    visible_sections,
)

SOURCE = (Path(__file__).parent / "fixtures" / "params.scad").read_text()
PARAMS = {p.name: p for p in parse_params(SOURCE)}


def test_finds_literal_parameters_only():
    assert list(PARAMS) == [
        "width",
        "height",
        "wall_thickness",
        "size",
        "shape",
        "holes",
        "lid",
        "label",
        "no_comment_here",
        "secret",
    ]  # not: expression, $fn, after_module


def test_range_slider_with_integer_default_step():
    p = PARAMS["width"]
    assert (p.kind, p.value, p.min, p.max, p.step) == ("number", 40, 10, 100, 1)
    assert p.section == "Size"
    assert p.description == "How wide the box is"
    assert p.label == "Width"


def test_range_with_explicit_step_and_float_value():
    p = PARAMS["height"]
    assert (p.value, p.min, p.max, p.step) == (12.5, 5, 50, 0.5)


def test_plain_number_has_no_constraints():
    p = PARAMS["wall_thickness"]
    assert (p.value, p.min, p.max, p.options) == (1.6, None, None, ())
    assert p.label == "Wall thickness"


def test_vector_gets_a_range_per_component():
    p = PARAMS["size"]
    assert (p.kind, p.value, p.min, p.max) == ("vector", [20, 30, 5], 1, 100)


def test_string_dropdown_with_and_without_labels():
    p = PARAMS["shape"]
    assert p.kind == "string"
    assert p.options == (
        Option("round", "round"),
        Option("square", "square"),
        Option("hex", "Six sides"),
    )


def test_numeric_dropdown_with_labels():
    p = PARAMS["holes"]
    assert p.options == (Option(0, "Zero"), Option(2, "Two"), Option(4, "Four"))


def test_bool_and_text_max_length_and_missing_comment():
    assert (PARAMS["lid"].kind, PARAMS["lid"].value) == ("bool", True)
    label = PARAMS["label"]
    assert (label.value, label.max_length) == ("Hello // world", 12)
    assert PARAMS["no_comment_here"].description == ""  # comment above is a blank line away


def test_hidden_section_and_visible_grouping():
    assert PARAMS["secret"].hidden
    sections = visible_sections(list(PARAMS.values()))
    assert list(sections) == ["Size", "Style"]
    assert "secret" not in [p.name for ps in sections.values() for p in ps]


def test_parameters_without_a_section_land_in_general():
    (p,) = parse_params("// Size\nx = 3;\n")
    assert p.section == "General"
    assert p.description == "Size"


def test_write_back_changes_only_the_value():
    out = apply_values(SOURCE, {"width": 55, "lid": False, "shape": "square"})
    assert "width = 55; // [10:100]" in out
    assert "lid = false;" in out
    assert 'shape = "square"; // [round, square, hex:Six sides]' in out
    before, after = SOURCE.splitlines(), out.splitlines()
    assert len(before) == len(after)
    assert sum(a != b for a, b in zip(before, after, strict=True)) == 3


def test_write_back_round_trips_through_the_parser():
    out = apply_values(
        SOURCE,
        {
            "height": 7.25,
            "size": [1, 2.5, 3],
            "holes": "4",
            "label": 'say "hi"',
            "wall_thickness": "2",
        },
    )
    p = {q.name: q for q in parse_params(out)}
    assert p["height"].value == 7.25
    assert p["size"].value == [1, 2.5, 3]
    assert p["holes"].value == 4
    assert p["label"].value == 'say "hi"'
    assert p["wall_thickness"].value == 2


def test_text_is_trimmed_to_max_length_and_kept_on_one_line():
    out = apply_values(SOURCE, {"label": "a very long name\nacross lines"})
    assert {q.name: q for q in parse_params(out)}["label"].value == "a very long"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("nope", 1),
        ("width", "wide"),
        ("width", float("nan")),
        ("width", True),
        ("lid", "maybe"),
        ("shape", "triangle"),
        ("size", [1, 2]),
        ("expression", 3),
    ],
)
def test_bad_write_back_raises_and_never_half_applies(name, value):
    with pytest.raises(ParamError):
        apply_values(SOURCE, {"width": 20, name: value})


def test_write_back_keeps_trailing_comment_without_space():
    out = apply_values("a = 3;//[1:9]\n", {"a": 5})
    assert out == "a = 5;//[1:9]\n"
