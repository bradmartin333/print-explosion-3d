// Herb Marker: a garden stake with the plant's name on it.
use <printable-lib.scad>

/* [Words] */
// The name on the marker.
label = "BASIL";

/* [Size] */
// How long the stake is, in mm.
stake_length = 90; // [50:150]
// How tall the letters are, in mm.
letter_height = 12; // [6:20]

/* [Hidden] */
plate_w = 80;
plate_h = 26;
t = 3;
chamfer = 0.6;

// Each child is a flat, convex 2D piece. Stand each up h mm with a chamfer around its bottom
// edge so it comes off the plate easily.
module chamfered(h) {
  for (i = [0 : $children - 1]) hull() {
    linear_extrude(0.01) offset(delta = -chamfer) children(i);
    translate([0, 0, chamfer]) linear_extrude(h - chamfer) children(i);
  }
}

translate([0, (stake_length - plate_h) / 2, 0]) {
  chamfered(t) {
    translate([-plate_w / 2, 0]) square([plate_w, plate_h]);
    // The stake runs up into the sign so the join is solid.
    hull() {
      translate([-5, -stake_length + 8]) square([10, stake_length - 8 + plate_h / 2]);
      translate([-1, -stake_length]) square([2, 1]);
    }
  }
  translate([0, plate_h / 2, t - 0.01])
    linear_extrude(1.2) text(label, size = letter_height, font = "Liberation Sans:style=Bold", halign = "center", valign = "center");
}
