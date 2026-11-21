// Not a design: a stand-in "photo" of spice jars on a shelf, for the README chat screenshot.
// scripts/screenshots.py exports it to PNG with OpenSCAD's preview colors.
$fn = 72;
module jar(fill, lid) {
  color(fill) cylinder(d = 40, h = 62);
  color([1, 1, 1, 0.35]) translate([0, 0, 62]) cylinder(d = 41, h = 16);
  color(lid) translate([0, 0, 78]) cylinder(d = 42, h = 14);
  color("white") translate([0, -20.6, 22]) rotate([90, 0, 0]) linear_extrude(0.4) square([30, 22], center = true);
}
color([0.55, 0.36, 0.2]) translate([-110, -40, -12]) cube([220, 110, 12]);
color([0.62, 0.42, 0.25]) translate([-110, 30, -12]) cube([220, 40, 70]);
color([0.58, 0.39, 0.22]) translate([-110, 30, 58]) cube([220, 40, 12]);
translate([0, 50, 70]) for (i = [0 : 3]) translate([-75 + i * 50, 0, 0]) jar([[0.75, 0.2, 0.1], [0.35, 0.5, 0.2], [0.9, 0.65, 0.1], [0.45, 0.3, 0.2]][i], [0.15, 0.15, 0.15]);
for (i = [0 : 3]) translate([-75 + i * 50, -5, 0]) jar([[0.85, 0.5, 0.15], [0.3, 0.35, 0.2], [0.8, 0.2, 0.15], [0.95, 0.85, 0.55]][i], [0.75, 0.75, 0.75]);
