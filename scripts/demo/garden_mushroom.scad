// Garden Mushroom: a toadstool for the flower bed. Its wide cap hangs out over the stem, so the
// preview card warns that it may need supports (used for the README's "Heads up" picture).
use <printable-lib.scad>

/* [Size] */
// How wide the cap is, in mm.
cap_width = 70; // [40:120]
// How tall the whole mushroom is, in mm.
height = 60; // [40:100]

/* [Hidden] */
stem_d = 18;
cap_h = 22;
chamfer = 0.6;
$fn = 64;

// Stem, with a small chamfer around the bottom edge.
cylinder(d1 = stem_d - 2 * chamfer, d2 = stem_d, h = chamfer);
translate([0, 0, chamfer]) cylinder(d = stem_d, h = height - cap_h - chamfer + 1);

// Cap: half a flattened ball, flat underneath.
translate([0, 0, height - cap_h])
  intersection() {
    scale([1, 1, cap_h / (cap_width / 2)]) sphere(d = cap_width);
    translate([-cap_width, -cap_width, 0]) cube([2 * cap_width, 2 * cap_width, cap_h + 1]);
  }
