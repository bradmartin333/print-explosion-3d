from print_explosion_3d.designer.protocol import parse_reply, visible_prose

FULL = """Here is your bird feeder. I made it 80 mm wide.

```openscad
use <printable-lib.scad>
width = 80; // [20:200]
cube(width);
```

<title>Bird Feeder</title>
<note>Bird feeder, 80 mm wide.</note>
<choices>Round | Square|</choices>
"""


def test_full_reply():
    p = parse_reply(FULL)
    assert p.scad == "use <printable-lib.scad>\nwidth = 80; // [20:200]\ncube(width);\n"
    assert p.title == "Bird Feeder"
    assert p.note == "Bird feeder, 80 mm wide."
    assert p.choices == ("Round", "Square")
    assert p.prose == "Here is your bird feeder. I made it 80 mm wide."


def test_plain_chat_has_no_design():
    p = parse_reply("Sure! What size should it be?\n<choices>Small|Big</choices>")
    assert p.scad is None
    assert p.choices == ("Small", "Big")
    assert p.prose == "Sure! What size should it be?"


def test_last_block_wins_and_other_fences_are_hidden():
    text = (
        "Hi\n```openscad\ncube(1);\n```\nthen\n```python\nprint(1)\n```\n```openscad\ncube(2);\n```"
    )
    p = parse_reply(text)
    assert p.scad == "cube(2);\n"
    assert "```" not in p.prose
    assert "print" not in p.prose


def test_empty_block_is_not_a_design():
    assert parse_reply("```openscad\n\n```").scad is None


def test_choices_capped():
    p = parse_reply("<choices>a|b|c|d|e|f|g|h</choices>")
    assert len(p.choices) == 6


def test_visible_prose_is_safe_mid_stream():
    assert visible_prose("Making it now.\n```openscad\ncube(") == "Making it now."
    assert visible_prose("Done. <titl") == "Done."
    assert visible_prose("Done.\n<title>Bird") == "Done."
    assert visible_prose("a < b is fine") == "a < b is fine"
