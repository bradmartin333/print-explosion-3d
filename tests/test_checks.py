import re

from print_explosion_3d.config import SCAD_LIB_DIR
from print_explosion_3d.scad.checks import BED_SIZE, check_bed
from print_explosion_3d.scad.models import BBox


def box(lo, hi):
    return BBox.of(lo, hi)


def codes(bbox):
    return [i.code for i in check_bed(bbox)]


def test_bed_size_matches_printer_profile():
    profile = (SCAD_LIB_DIR / "printer-profile.scad").read_text()
    match = re.search(r"bed_size\s*=\s*\[([^\]]+)\]", profile)
    assert match
    assert tuple(float(v) for v in match[1].split(",")) == BED_SIZE


def test_good_model_has_no_issues():
    assert codes(box((-20, -15, 0), (20, 15, 12))) == []


def test_exactly_bed_sized_model_fits():
    assert codes(box((-90, -90, 0), (90, 90, 180))) == []


def test_too_big_in_any_axis():
    assert codes(box((-100, -10, 0), (100, 10, 10))) == ["too_big"]
    assert codes(box((-10, -10, 0), (10, 10, 181))) == ["too_big"]


def test_floating_and_sunk():
    assert codes(box((-5, -5, 3), (5, 5, 13))) == ["floating"]
    assert codes(box((-5, -5, -2), (5, 5, 8))) == ["sunk"]


def test_tiny_float_noise_on_the_floor_is_fine():
    assert codes(box((-5, -5, -1e-6), (5, 5, 10))) == []


def test_flat_or_zero_size_is_empty():
    assert codes(box((0, 0, 0), (0, 0, 0))) == ["empty"]
    assert codes(box((-5, -5, 0), (5, 5, 0))) == ["empty"]


def test_off_center_is_only_a_warning():
    (issue,) = check_bed(box((0, 0, 0), (10, 10, 10)))
    assert (issue.code, issue.severity) == ("off_center", "warning")
