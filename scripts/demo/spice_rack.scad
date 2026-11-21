// Spice Rack: a stepped shelf so every jar label is easy to read.
use <printable-lib.scad>

/* [Size] */
// How many jars fit side by side on each step.
jars_per_row = 3; // [2:3]
// How wide one jar is, in mm.
jar_width = 45; // [30:53]
// How many steps.
steps = 3; // [1:3]
// How much higher each step is than the one in front of it, in mm.
step_rise = 20; // [10:30]

/* [Options] */
// The shape of the two side walls.
side_style = "slanted"; // [slanted:Slanted, square:Square]
// A small edge along the front of each step so jars can't slide off.
front_lip = true;

/* [Hidden] */
wall = 3;
gap = 2;
lip_h = 4;
lip_t = 2;
chamfer = 0.6;
inner_w = jars_per_row * (jar_width + gap);
width = inner_w + 2 * wall;
step_depth = jar_width + 6;
depth = steps * step_depth;
side_h = steps * step_rise + lip_h + 12;

module steps_block() {
  for (i = [0 : steps - 1])
    translate([-inner_w / 2, -depth / 2 + i * step_depth, 0])
      cube([inner_w, depth - i * step_depth, (i + 1) * step_rise]);
}

module lips() {
  if (front_lip)
    for (i = [0 : steps - 1])
      translate([-inner_w / 2, -depth / 2 + i * step_depth, (i + 1) * step_rise - 0.01])
        cube([inner_w, lip_t, lip_h]);
}

module side_wall() {
  front_h = step_rise + lip_h + 12;
  rotate([90, 0, 90])
    linear_extrude(wall)
      if (side_style == "slanted")
        polygon([[-depth / 2, 0], [depth / 2, 0], [depth / 2, side_h], [-depth / 2 + 8, front_h], [-depth / 2, front_h - 8]]);
      else
        translate([-depth / 2, 0]) square([depth, side_h]);
}

module rack() {
  steps_block();
  lips();
  for (x = [-width / 2, inner_w / 2]) translate([x, 0, 0]) side_wall();
}

// Bottom chamfer so it comes off the plate easily.
intersection() {
  rack();
  hull() {
    translate([0, 0, chamfer / 2]) cube([width - 2 * chamfer, depth - 2 * chamfer, chamfer], center = true);
    translate([-width / 2, -depth / 2, chamfer]) cube([width, depth, side_h]);
  }
}
