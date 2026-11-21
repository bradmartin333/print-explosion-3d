// Succulent Pot: a small faceted pot with a gentle twist.
use <printable-lib.scad>

/* [Size] */
// How wide the pot is across, in mm.
width = 80; // [40:150]
// How tall the pot is, in mm.
height = 70; // [30:150]
// How far the sides twist from bottom to top, in degrees.
twist = 30; // [0:60]

/* [Options] */
// How many flat sides the pot has.
sides = 6; // [5:Five, 6:Six, 8:Eight]
// A hole in the bottom so extra water can drain.
drain_hole = true;

/* [Hidden] */
wall = 2;
floor_t = 2;
chamfer = 0.6;
$fn = 64;

difference() {
  linear_extrude(height, twist = twist, slices = 40, scale = 1.15)
    offset(r = 2) circle(d = width / 1.15 - 4, $fn = sides);
  translate([0, 0, floor_t])
    linear_extrude(height, twist = twist, slices = 40, scale = 1.15 + 0.06)
      circle(d = width / 1.15 - 2 * wall, $fn = sides);
  if (drain_hole) translate([0, 0, -1]) cylinder(d = 10, h = floor_t + 2);
  // bottom chamfer
  difference() {
    translate([0, 0, -0.01]) cylinder(d = width * 1.5, h = chamfer);
    translate([0, 0, -0.02]) linear_extrude(chamfer + 0.02, scale = 1.02) offset(r = 2 - chamfer) circle(d = width / 1.15 - 4, $fn = sides);
  }
}
