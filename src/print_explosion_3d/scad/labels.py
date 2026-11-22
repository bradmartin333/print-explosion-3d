"""A ready-made label sheet: a row of name tags with raised words, built without the AI.

The words live in an ordinary text setting, so the Adjust panel edits them like any other design
and the designer can still change the design later in chat.
"""

from __future__ import annotations

import re

DEFAULT_NAMES = ("Sugar", "Flour", "Salt", "Rice")
MAX_NAMES_TEXT = 200

_SPLIT = re.compile(r"\s*(?:,|;|\n|\band\b|&)\s*", re.IGNORECASE)

_TEMPLATE = """// Label sheet: a set of name labels with raised words, laid out to fit on one plate.
use <printable-lib.scad>

/* [Words] */
// The words for each label, separated by commas.
names = "__NAMES__"; // __MAX__

/* [Size] */
// How wide each label is, in mm.
label_width = 60; // [30:120]
// How tall each label is, in mm.
label_height = 25; // [15:60]
// How thick the label is, in mm.
thickness = 2.4; // [1.6:0.2:5]
// How tall the letters are, in mm.
letter_height = 9; // [5:20]

/* [Hidden] */
gap = 4;
raise = 0.8;
chamfer = 0.5;
bed = 170;
char_width = 0.62; // how wide a letter is compared with its height, roughly

function _first(s, i = 0) = i >= len(s) ? i : s[i] == " " ? _first(s, i + 1) : i;
function _last(s, i) = i < 0 ? -1 : s[i] == " " ? _last(s, i - 1) : i;
function _sub(s, a, b, acc = "") = a > b ? acc : _sub(s, a + 1, b, str(acc, s[a]));
function _trim(s) = _sub(s, _first(s), _last(s, len(s) - 1));
function _split(s, i = 0, cur = "", out = []) =
  i >= len(s) ? concat(out, [cur])
  : s[i] == "," ? _split(s, i + 1, "", concat(out, [cur]))
  : _split(s, i + 1, str(cur, s[i]), out);
function _clean(list) = [for (w = list) let(t = _trim(w)) if (len(t) > 0) t];

words = _clean(_split(names));
cols = max(1, floor((bed + gap) / (label_width + gap)));
rows = max(1, floor((bed + gap) / (label_height + gap)));
shown = [for (i = [0 : min(len(words), cols * rows) - 1]) words[i]];
used_cols = min(cols, max(1, len(shown)));
used_rows = ceil(max(1, len(shown)) / used_cols);

module plate() {
  hull() {
    linear_extrude(0.01) offset(delta = -chamfer)
      square([label_width, label_height], center = true);
    translate([0, 0, chamfer]) linear_extrude(thickness - chamfer)
      square([label_width, label_height], center = true);
  }
}

module one_label(word) {
  fit = (label_width - 8) / (char_width * len(word));
  size = max(5, min(letter_height, fit));
  plate();
  translate([0, 0, thickness - 0.01]) linear_extrude(raise + 0.01)
    text(word, size = size, halign = "center", valign = "center");
}

for (i = [0 : len(shown) - 1]) {
  c = i % used_cols;
  r = floor(i / used_cols);
  translate([
    (c - (used_cols - 1) / 2) * (label_width + gap),
    ((used_rows - 1) / 2 - r) * (label_height + gap),
    0
  ]) one_label(shown[i]);
}
"""


def parse_names(text: str) -> list[str]:
    """Pull the words out of "sugar, flour and salt". Empty if the text isn't a clear list."""
    parts = [p.strip(" .!\"'") for p in _SPLIT.split(text.strip())]
    return [p for p in parts if p]


def label_sheet_scad(names: list[str] | None = None) -> str:
    """The design text for a label sheet with these words (a few sample words if none)."""
    words = names or list(DEFAULT_NAMES)
    joined = ", ".join(words).replace("\\", "").replace('"', "")[:MAX_NAMES_TEXT]
    return _TEMPLATE.replace("__NAMES__", joined).replace("__MAX__", str(MAX_NAMES_TEXT))
