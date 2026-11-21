// ============================================
// printer-profile.scad — Bambu Lab A1 mini, 0.4 mm nozzle, PLA, textured PEI plate
// Included automatically by printable-lib.scad.
//
// Adapted from andreahaku/openscad_claude_skill @ 3483e23 (MIT) —
// see third_party/openscad-skill/ for the original and its calibration notes.
// Variable names are kept identical so printable-lib.scad works unchanged.
// ============================================
//
// The clearances below are sensible PLA defaults, not measurements. To measure:
// print third_party/openscad-skill's calibration comb (upstream templates/calibration-comb.scad),
// read the hole that fits a 6.00 mm pin each way, and record hole - 6.00 here.

// --- Provenance -----------------------------------------------------------
profile_measured = false;
profile_printer  = "Bambu Lab A1 mini";
profile_filament = "PLA";
profile_nozzle   = 0.4;
profile_date     = "";

// --- Clearances (mm added to a hole diameter to reach the wanted fit) -----
clearance_press  = 0.15;
clearance_close  = 0.25;
clearance_slide  = 0.30;
clearance_loose  = 0.40;

// --- Horizontal expansion (per side, + means the printer prints fat) ------
xy_expansion = 0.00;

// --- Print constraints ----------------------------------------------------
min_wall        = 1.2;   // three 0.4 mm perimeters
min_floor       = 0.8;   // four 0.2 mm layers
max_overhang    = 45;    // degrees from vertical before support is needed
bed_size        = [180, 180, 180];   // A1 mini build volume
first_layer_chamfer = 0.5;           // bottom-edge chamfer: no elephant foot, easy release
