import json
import os
import shutil
from pathlib import Path

import pytest

from print_explosion_3d.api import Api
from print_explosion_3d.config import load_settings
from print_explosion_3d.workspace import HISTORY_LIMIT, Workspace, find_projects


@pytest.fixture
def trashed():
    return []


@pytest.fixture
def ws(tmp_path, trashed):
    def fake_trash(path: Path) -> None:
        trashed.append(path.name)
        shutil.rmtree(path)

    return Workspace(tmp_path / "ws", trash=fake_trash)


def test_create_makes_folder_unique_and_remembers_last(ws):
    a = ws.create("Bird Feeder")
    b = ws.create("Bird Feeder")
    assert (a.folder, b.folder) == ("Bird Feeder", "Bird Feeder 2")
    assert b.name == "Bird Feeder"
    assert ws.last_opened() == "Bird Feeder 2"
    assert ws.open_last().folder == "Bird Feeder 2"


def test_unsafe_names_are_cleaned(ws):
    assert ws.create("../../etc/passwd?").folder == "etc passwd"
    assert ws.create("...").folder == "Untitled"


def test_get_rejects_path_escape(ws):
    ws.create("x")
    assert ws.get("..") is None
    assert ws.get("../ws") is None
    assert ws.get("missing") is None


def test_save_scad_roundtrip_and_history(ws):
    p = ws.create("Box")
    assert p.save_scad("a = 1;") is True
    assert p.history() == []  # nothing earlier to keep
    assert p.save_scad("a = 1;") is False  # unchanged
    assert p.save_scad("a = 2;") is True
    assert p.read_scad() == "a = 2;"
    assert [h.read_text() for h in p.history()] == ["a = 1;"]


def test_history_is_capped_keeping_newest(ws):
    p = ws.create("Box")
    for i in range(HISTORY_LIMIT + 8):
        p.save_scad(f"v = {i};")
    kept = [h.read_text() for h in p.history()]
    assert len(kept) == HISTORY_LIMIT
    assert kept[-1] == f"v = {HISTORY_LIMIT + 6};"  # the version just before the current one
    assert kept[0] == "v = 7;"


def test_chat_roundtrip_and_bad_files_read_empty(ws):
    p = ws.create("Box")
    assert p.read_chat() == {}
    p.save_chat({"messages": [{"role": "user", "text": "héllo"}]})
    assert p.read_chat()["messages"][0]["text"] == "héllo"
    p.chat_path.write_text("{not json")
    assert p.read_chat() == {}
    (p.path / "project.json").write_text("[]")
    assert p.name == "Box"


def test_save_updates_listing_order(ws):
    a, b = ws.create("A"), ws.create("B")
    a.update_meta(updated="2020-01-01T00:00:00+00:00")
    b.update_meta(updated="2021-01-01T00:00:00+00:00")
    a.save_scad("x = 1;")
    assert next(i.folder for i in ws.list_projects()) == "A"


def test_delete_goes_through_trash_and_clears_last(ws, trashed):
    p = ws.create("Gone")
    assert ws.delete(p.folder) is True
    assert trashed == ["Gone"]
    assert ws.last_opened() is None
    assert ws.delete("Gone") is False


def test_failed_trash_keeps_project(tmp_path):
    def boom(_: Path) -> None:
        raise OSError("nope")

    ws = Workspace(tmp_path, trash=boom)
    p = ws.create("Keep")
    assert ws.delete(p.folder) is False
    assert p.path.exists()


def test_attachments_never_overwrite(ws):
    p = ws.create("Box")
    first = p.add_attachment("My Photo.JPG", b"1")
    second = p.add_attachment("My Photo.JPG", b"2")
    assert first != second
    assert first.read_bytes() == b"1"
    assert first.suffix == ".jpg"


def test_clean_stale(ws):
    p = ws.create("Box")
    p.save_scad("a = 1;")
    p.save_stl(b"stl")
    old = p.scad_path.stat().st_mtime - 100
    os.utime(p.stl_path, (old, old))  # older than the design → stale
    kept = p.add_attachment("used.jpg", b"x")
    p.add_attachment("orphan.jpg", b"x")
    p.save_chat({"messages": [{"attachments": [kept.name]}]})
    (p.path / ".model.scad.tmp").write_text("half")
    assert ws.clean_stale() == 3
    assert not p.stl_path.exists()
    assert [f.name for f in p.attachments_dir.iterdir()] == ["used.jpg"]


def test_stale_empty_projects_only_after_grace(ws, trashed):
    empty = ws.create("Blank")
    ws.create("Busy").save_scad("a = 1;")
    mtime = empty.path.stat().st_mtime
    assert ws.clean_stale(now=mtime + 60) == 0
    assert ws.clean_stale(now=mtime + 3 * 24 * 3600) == 1
    assert trashed == ["Blank"]


def projects(ws, *names):
    for n in names:
        ws.create(n)
    return ws.list_projects()


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("open my bird feeder", "Bird Feeder"),
        ("can you go back to the birdfeeder project", "Bird Feeder"),
        ("feeder", "Bird Feeder"),
        ("resume phone stand", "Phone Stand"),
        ("the fone stnad", "Phone Stand"),
    ],
)
def test_fuzzy_lookup(ws, query, expected):
    found = find_projects(query, projects(ws, "Bird Feeder", "Phone Stand", "Coat Hook"))
    assert found[0].name == expected


def test_lookup_no_match_and_filler_only(ws):
    ps = projects(ws, "Bird Feeder")
    assert find_projects("rocket ship", ps) == []
    assert find_projects("open my project", ps) == []


def test_api_flow(tmp_path):
    settings = load_settings({"PE_WORKSPACE_DIR": str(tmp_path)})
    api = Api(settings, Workspace(tmp_path / "w", trash=shutil.rmtree))
    assert api.open_project() is None
    assert api.save_design("a = 1;")["saved"] is False
    made = api.new_project("Bird Feeder")
    assert made is not None
    assert api.save_design("a = 1;") == {"saved": True, "status": "All changes saved"}
    reopened = api.open_project()
    assert reopened and reopened["scad"] == "a = 1;"
    assert api.find_project("open my bird feeder")[0]["folder"] == made["folder"]
    assert json.dumps(api.list_projects())  # bridge payloads must be JSON-safe
    assert api.delete_project(made["folder"]) is True
    assert api.list_projects() == []


@pytest.mark.skipif(os.uname().sysname != "Darwin", reason="macOS Trash")
def test_real_trash_moves_folder(tmp_path):
    from print_explosion_3d.workspace.trash import move_to_trash

    target = tmp_path / "pe-trash-test"
    target.mkdir()
    (target / "f").write_text("x")
    move_to_trash(target)
    assert not target.exists()
