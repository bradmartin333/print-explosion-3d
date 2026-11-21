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

translate([0, (stake_length - plate_h) / 2, 0]) union() {
  translate([-plate_w / 2, 0, 0]) cube([plate_w, plate_h, t]);
  hull() {
    translate([-5, -stake_length + 8, 0]) cube([10, stake_length - 8, t]);
    translate([-1, -stake_length, 0]) cube([2, 1, t]);
  }
  translate([0, plate_h / 2, t - 0.01])
    linear_extrude(1.2) text(label, size = letter_height, font = "Liberation Sans:style=Bold", halign = "center", valign = "center");
}
