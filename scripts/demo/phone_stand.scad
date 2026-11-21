// Phone Stand: holds a phone upright on the kitchen counter.
use <printable-lib.scad>

/* [Size] */
// How wide the stand is, in mm.
width = 70; // [40:120]
// How thick the phone is with its case, in mm.
phone_thickness = 12; // [6:20]
// How far the phone leans back, in degrees.
lean = 20; // [5:35]

/* [Options] */
// A gap in the front lip for a charging cable.
cable_slot = true;

/* [Hidden] */
base_d = 80;
base_h = 6;
back_h = 70;
t = 5;
chamfer = 0.6;

module stand() difference() {
  union() {
    // base
    translate([-width / 2, -base_d / 2, 0]) cube([width, base_d, base_h]);
    // front lip
    translate([-width / 2, -base_d / 2 + 6, 0]) cube([width, t, base_h + 10]);
    // back support, leaning back
    translate([-width / 2, -base_d / 2 + 6 + t + phone_thickness, 0])
      rotate([-lean, 0, 0]) cube([width, t, back_h]);
    // brace under the back support
    translate([-width / 2, 0, 0]) rotate([90, 0, 90])
      linear_extrude(width) polygon([[-base_d / 2 + 6 + t + phone_thickness, base_h], [base_d / 2, base_h], [-base_d / 2 + 6 + t + phone_thickness + back_h * sin(lean) * 0.6, back_h * cos(lean) * 0.6]]);
  }
  if (cable_slot) translate([-8, -base_d / 2 - 1, base_h]) cube([16, t + 8, 20]);
  translate([-width, -base_d, -50]) cube([2 * width, 2 * base_d, 50]);
  translate([-width, base_d / 2, -1]) cube([2 * width, base_d, 200]);
}

// Bottom chamfer so it comes off the plate easily. Only the base touches the plate.
intersection() {
  stand();
  hull() {
    translate([0, 0, chamfer / 2]) cube([width - 2 * chamfer, base_d - 2 * chamfer, chamfer], center = true);
    translate([-width / 2, -base_d / 2, chamfer]) cube([width, base_d, 2 * back_h]);
  }
}
