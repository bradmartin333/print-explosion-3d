// Plant Spike: a tall, thin stake. Its small footprint makes it likely to wobble while printing,
// so the preview card says so (used for the README's "Heads up" picture).
use <printable-lib.scad>

/* [Size] */
// How thick the spike is, in mm.
thickness = 12; // [8:30]
// How long the spike is, in mm.
spike_length = 90; // [40:150]

/* [Hidden] */
chamfer = 0.6;
$fn = 48;

cylinder(d1 = thickness - 2 * chamfer, d2 = thickness, h = chamfer);
translate([0, 0, chamfer]) cylinder(d = thickness, h = spike_length - 14 - chamfer);
translate([0, 0, spike_length - 14]) cylinder(d1 = thickness, d2 = 2, h = 14); // a gentle point
