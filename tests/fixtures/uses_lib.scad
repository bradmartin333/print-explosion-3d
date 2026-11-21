// Smoke fixture: proves OPENSCADPATH resolves the bundled lib and the printer profile.
use <printable-lib.scad>
include <printer-profile.scad>

assert(bed_size == [180, 180, 180], "A1 mini profile not loaded");

difference() {
    rounded_box([40, 30, 12], r=3);
    translate([20, 15, -0.01]) screw_clearance_hole(d=3, h=12.02);
}
