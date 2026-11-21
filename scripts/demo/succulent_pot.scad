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
flare = 1.15; // the top is this much wider than the bottom
$fn = 64;

// The pot's shape at the bottom, with softened corners.
module outline() offset(r = 2) circle(d = width / flare - 4, $fn = sides);

// Rise h mm with the pot's twist and flare per mm, so the inside follows the outside exactly.
module rise(h) linear_extrude(h, twist = twist * h / height, slices = 40, scale = 1 + (flare - 1) * h / height) children();

difference() {
  rise(height) outline();
  // The inside: the outline shrunk by the wall, starting above the floor and open at the top.
  intersection() {
    rise(height + 1) offset(r = -wall) outline();
    translate([-width, -width, floor_t]) cube([2 * width, 2 * width, height + 2]);
  }
  if (drain_hole) translate([0, 0, -1]) cylinder(d = 10, h = floor_t + 2);
  // bottom chamfer
  difference() {
    translate([0, 0, -0.01]) cylinder(d = width * 1.5, h = chamfer);
    translate([0, 0, -0.02]) linear_extrude(chamfer + 0.02, scale = 1.02) offset(r = -chamfer) outline();
  }
}
