// Parameters for the customizer fixture.

/* [Size] */
// How wide the box is
width = 40; // [10:100]
// How tall it is, in steps of half a millimetre
height = 12.5; // [5:0.5:50]
// Wall thickness
wall_thickness = 1.6;
// How big each side is
size = [20, 30, 5]; // [1:100]

/* [Style] */
// Which shape to use
shape = "round"; // [round, square, hex:Six sides]
// Number of holes
holes = 2; // [0:Zero, 2:Two, 4:Four]
// Add a lid
lid = true;
// Text on the top
label = "Hello // world"; // 12
no_comment_here = 5;

expression = width * 2;
$fn = 64;

/* [Hidden] */
secret = 7;

module thing() { cube(1); }
after_module = 99;
