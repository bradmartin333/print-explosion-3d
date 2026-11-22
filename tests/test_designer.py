import json
from pathlib import Path

import pytest

from print_explosion_3d.ai.base import Image, ProviderError, Reply, Usage
from print_explosion_3d.ai.fake_provider import FakeProvider
from print_explosion_3d.designer import Designer, load_system_prompt
from print_explosion_3d.designer.session import MSG_GAVE_UP, MSG_REFUSED
from print_explosion_3d.scad.models import Issue
from print_explosion_3d.scad.runner import RenderResult
from print_explosion_3d.workspace import Workspace


def design(body="cube(10);", extra=""):
    return f"Here you go.\n```openscad\n{body}\n```\n{extra}"


@pytest.fixture
def project(tmp_path):
    return Workspace(tmp_path / "ws", trash=lambda p: None).create("Box")


class Builder:
    """Stands in for OpenSCAD: fails while the source contains 'BAD'."""

    def __init__(self, fail_codes=("syntax",)):
        self.fail_codes = fail_codes
        self.built: list[str] = []

    def __call__(self, scad: Path, stl: Path) -> RenderResult:
        text = scad.read_text()
        self.built.append(text)
        if "BAD" in text:
            issues = tuple(Issue(c, f"{c} problem") for c in self.fail_codes)
            return RenderResult(False, issues=issues)
        stl.write_bytes(b"STL")
        return RenderResult(True, stl_path=stl)


def make(project, script, build=None, fixes=2, tmp_path=None):
    provider = FakeProvider(script)
    usage = project.path.parent / "usage.jsonl"
    d = Designer(
        provider, project, build=build or Builder(), max_auto_fixes=fixes, usage_path=usage
    )
    return d, provider, usage


def test_system_prompt_is_stable_and_free_of_per_user_data():
    assert load_system_prompt() == load_system_prompt()
    text = load_system_prompt()
    assert "`openscad`" in text
    assert "<choices>" in text and "<note>" in text and "<title>" in text


def test_design_builds_saves_and_logs(project):
    reply = design("cube(10);", "<title>Box</title>\n<note>A 10 mm cube.</note>")
    d, provider, usage = make(project, [reply])
    seen = []
    r = d.send("make a cube", on_text=seen.append, on_status=lambda s: None)

    assert r.ok and r.changed and r.title == "Box"
    assert r.text == "Here you go."
    assert seen  # streamed
    assert project.read_scad() == "cube(10);\n"
    assert project.stl_path.read_bytes() == b"STL"
    assert project.note == "A 10 mm cube."
    assert not list(project.path.glob(".*.tmp"))
    assert d.display[-1] == {"role": "assistant", "text": "Here you go.", "chip": True}
    assert json.loads(project.chat_path.read_text())["display"][0]["role"] == "user"
    lines = usage.read_text().splitlines()
    assert json.loads(lines[0])["label"] == "turn"
    assert provider.calls[0][0] == load_system_prompt()


def test_chat_without_design_changes_nothing(project):
    d, _, _ = make(project, ["What size?\n<choices>Small|Big</choices>"])
    r = d.send("make something")
    assert r.ok and not r.changed
    assert r.choices == ("Small", "Big")
    assert project.read_scad() == ""


def test_auto_fix_round_trip_then_success(project):
    builder = Builder()
    d, provider, usage = make(project, [design("BAD"), design("cube(5);")], build=builder)
    r = d.send("a cube")
    assert r.ok and r.changed and r.auto_fixes == 1
    assert project.read_scad() == "cube(5);\n"
    # The second call saw a note describing the failure, after the replayed first turn.
    second = provider.calls[1][1]
    assert second[-1].role == "note"
    assert "syntax problem" in second[-1].text
    assert second[-2].role == "assistant"
    assert [json.loads(line)["label"] for line in usage.read_text().splitlines()] == ["turn", "fix"]


def test_auto_fix_is_capped_and_good_design_survives(project):
    project.save_scad("cube(1);\n")
    builder = Builder()
    d, provider, _ = make(project, [design("BAD")] * 3, build=builder, fixes=2)
    r = d.send("break it")
    assert not r.ok and r.error == MSG_GAVE_UP and r.error_kind == "build"
    assert r.auto_fixes == 2
    assert len(provider.calls) == 3
    assert project.read_scad() == "cube(1);\n"  # the good file is untouched
    assert d.display[-1]["role"] == "info"
    assert d.messages[-1].role == "note"


def test_old_error_notices_clear_once_a_later_turn_works(project):
    d, _, _ = make(project, [design("BAD"), design("cube(5);")], fixes=0)
    assert not d.send("break it").ok
    assert [e["role"] for e in d.display].count("info") == 1
    assert d.send("try again").ok
    saved = project.read_chat()["display"]
    assert all(e["role"] != "info" for e in d.display + saved)  # the failure notice is gone


def test_zero_fixes_means_no_retry(project):
    d, provider, _ = make(project, [design("BAD")], fixes=0)
    assert not d.send("x").ok
    assert len(provider.calls) == 1


def test_environment_failure_skips_the_ai(project):
    d, provider, _ = make(project, [design("BAD")], build=Builder(("no_openscad",)))
    r = d.send("x")
    assert r.error_kind == "no_openscad"
    assert len(provider.calls) == 1


def test_provider_error_rolls_the_turn_back(project):
    d, _, _ = make(project, [ProviderError("No internet.", "offline"), "Hello"])
    r = d.send("hi")
    assert r.error == "No internet." and r.error_kind == "offline"
    assert d.messages == [] and d.display == []
    assert d.send("hi").ok  # retry works from a clean slate


def test_refusal_rolls_back(project):
    d, _, _ = make(project, [Reply(text="", refused=True, usage=Usage())])
    r = d.send("x")
    assert r.error == MSG_REFUSED
    assert d.messages == []


def test_history_is_append_only_with_raw_replay(project):
    raw = ({"type": "thinking", "thinking": "", "signature": "s"}, {"type": "text", "text": "A"})
    script = [Reply(text=design("cube(3);"), raw=raw), "Sure"]
    d, provider, _ = make(project, script)
    d.send("one")
    d.send("two")
    first, second = provider.calls
    assert second[1][: len(first[1]) + 1][-1].raw == raw  # assistant turn replayed unchanged
    assert second[1][: len(first[1])] == first[1]  # earlier prefix identical


def test_her_edits_reach_the_ai_as_a_note(project):
    d, provider, _ = make(project, [design("cube(10);"), "Ok"])
    d.send("cube")
    project.save_scad("cube(99);\n")  # side-panel edit
    d.send("thanks")
    msgs = provider.calls[1][1]
    notes = [m for m in msgs if m.role == "note"]
    assert any("cube(99);" in m.text for m in notes)
    assert msgs[-1].role == "user"


def test_resume_seeds_a_fresh_conversation(project):
    project.save_scad("cube(7);\n")
    project.update_meta(note="A seven mm cube.")
    d, provider, _ = make(project, ["Welcome back"])
    assert [m.role for m in d.messages] == ["note"]
    assert "A seven mm cube." in d.messages[0].text and "cube(7);" in d.messages[0].text
    d.send("hi")
    assert provider.calls[0][1][0].role == "note"


def test_photos_are_stored_and_displayed(project):
    d, provider, _ = make(project, ["Nice mug!"])
    d.send("copy this", images=[Image("image/jpeg", b"jpgdata", "mug.jpg")])
    assert (project.attachments_dir / "mug.jpg").read_bytes() == b"jpgdata"
    assert d.display[0]["images"] == ["mug.jpg"]
    assert provider.calls[0][1][-1].images[0].data == b"jpgdata"
    assert project.clean_stale() == 0  # the photo is referenced by the saved chat


def test_new_designer_for_same_project_keeps_display(project):
    d, _, _ = make(project, ["Hello"])
    d.send("hi")
    d2, _, _ = make(project, [])
    assert [e["role"] for e in d2.display] == ["user", "assistant"]
    assert d2.messages == []  # empty project: nothing to seed


@pytest.mark.openscad
def test_real_build_end_to_end_with_auto_fix(project):
    from print_explosion_3d.scad.runner import render

    bad = design("use <printable-lib.scad>\nnonexistent_module();")
    good = design(
        "use <printable-lib.scad>\nwidth = 30; // [10:100]\nrounded_box([width, 20, 10], r=2);"
    )
    d = Designer(FakeProvider([bad, good]), project, build=render, max_auto_fixes=2)
    r = d.send("a little box")
    assert r.ok and r.changed and r.auto_fixes == 1
    assert project.stl_path.stat().st_size > 100
    assert "rounded_box" in project.read_scad()
