import base64
import json
import shutil
import threading
from pathlib import Path

import pytest

from print_explosion_3d.ai.base import ProviderError
from print_explosion_3d.ai.fake_provider import FakeProvider
from print_explosion_3d.api import MSG_BUILD_FAILED, Api, params_payload
from print_explosion_3d.config import load_settings
from print_explosion_3d.scad.models import Issue
from print_explosion_3d.scad.runner import RenderResult
from print_explosion_3d.workspace import Workspace

SCAD = """/* [Size] */
// How wide.
width = 40; // [10:100]
// Name on it.
label = "Hi";
cube(width);
"""


def reply(scad=SCAD, extra="<title>Box</title><note>A box.</note>"):
    return f"Here you go.\n```openscad\n{scad}```\n{extra}"


def build(scad: Path, stl: Path) -> RenderResult:
    if "BAD" in scad.read_text():
        return RenderResult(False, issues=(Issue("syntax", "nope"),))
    stl.write_bytes(b"STL")
    return RenderResult(True, stl_path=stl)


class Harness:
    def __init__(self, tmp_path, script=()):
        settings = load_settings({"PE_WORKSPACE_DIR": str(tmp_path)})
        self.provider = FakeProvider(script)
        self.events: list[tuple[str, object]] = []
        self.done = threading.Event()
        self.api = Api(
            settings,
            Workspace(tmp_path / "w", trash=shutil.rmtree),
            provider_factory=lambda _s: self.provider,
            build=build,
        )
        self.api._emit = self._on_event

    def _on_event(self, name, data):
        self.events.append((name, data))
        if name in {"turn_done", "built"}:
            self.done.set()

    def wait(self):
        assert self.done.wait(5), "worker never finished"
        self.done.clear()
        return next(d for n, d in reversed(self.events) if n in {"turn_done", "built"})


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path, [reply()])


def test_first_message_creates_project_designs_and_renames(h):
    assert h.api.send_message("a box")["started"] is True
    done = h.wait()
    assert done["changed"] and done["error"] is None
    assert done["project"]["name"] == "Box"
    assert [p["name"] for p in done["params"][0]["params"]] == ["width", "label"]
    assert base64.b64decode(h.api.get_stl()) == b"STL"
    assert any(n == "text" for n, _ in h.events)
    assert json.dumps(done)  # bridge payloads must be JSON-safe


def test_streamed_text_never_contains_code(h):
    h.api.send_message("a box")
    h.wait()
    for name, data in h.events:
        if name == "text":
            assert "openscad" not in data and "cube" not in data


def test_provider_errors_come_back_as_friendly_text(tmp_path):
    h = Harness(tmp_path, [ProviderError("No key yet.", "no_key")])
    h.api.send_message("hi")
    done = h.wait()
    assert done["error"] == "No key yet." and not done["changed"]


def test_empty_message_and_busy_guard(h):
    assert h.api.send_message("  ") == {"started": False}
    h.api._busy.acquire()
    res = h.api.send_message("hi")
    assert res["started"] is False and "still working" in res["error"]
    assert h.api.new_project() is None and h.api.delete_project("x") is False
    assert h.api.generate()["started"] is False


def test_local_commands_skip_the_ai(h):
    first = h.api.new_project("Bird Feeder")
    assert first
    res = h.api.send_message("start a new project")
    assert res["command"] == "new_project" and res["project"]["name"] == "New project"
    res = h.api.send_message("open my bird feeder")
    assert res["command"] == "open_project" and res["project"]["name"] == "Bird Feeder"
    assert h.provider.calls == []


def test_images_are_decoded_and_stored(h):
    jpeg = base64.b64encode(b"\xff\xd8fake").decode()
    h.api.send_message("copy this", [{"name": "cup.jpg", "data": jpeg}])
    h.wait()
    _, messages = h.provider.calls[0]
    assert messages[-1].images[0].data == b"\xff\xd8fake"
    assert (h.api._current.attachments_dir / "cup.jpg").exists()


def test_set_params_writes_into_the_file_and_generate_rebuilds(h):
    h.api.send_message("a box")
    h.wait()
    assert h.api.set_params({"width": 55, "label": "Mia"})["saved"] is True
    assert "width = 55;" in h.api._current.read_scad()
    assert h.api.generate()["started"] is True
    done = h.wait()
    assert done["error"] is None
    assert done["params"][0]["params"][0]["value"] == 55


def test_set_params_rejects_unknown_and_bad_values(h):
    h.api.send_message("a box")
    h.wait()
    assert h.api.set_params({"nope": 1})["saved"] is False
    assert h.api.set_params({"width": "wide"})["saved"] is False
    assert "width = 40;" in h.api._current.read_scad()


def test_failed_rebuild_restores_the_last_good_design(h):
    h.api.send_message("a box")
    h.wait()
    h.api._current.save_scad(SCAD + "BAD\n")  # as if an edit made it unbuildable
    h.api.generate()
    done = h.wait()
    assert done["error"] == MSG_BUILD_FAILED
    assert h.api._current.read_scad() == SCAD


def test_open_project_payload_has_chat_params_and_model(h):
    h.api.send_message("a box")
    h.wait()
    folder = h.api._current.folder
    h.api.new_project("Other")
    opened = h.api.open_project(folder)
    assert opened and opened["has_stl"] and opened["params"] and opened["chat"]["display"]
    assert h.api.boot()["project"]["folder"] == folder
    assert json.dumps(h.api.boot())


def test_export_and_bambu_need_a_model(h):
    assert h.api.export_stl()["saved"] is False
    assert h.api.open_in_bambu()["opened"] is False


def test_bambu_uses_open_command(h, monkeypatch):
    h.api.send_message("a box")
    h.wait()
    calls = []

    class Done:
        returncode = 0

    monkeypatch.setattr(
        "print_explosion_3d.bambu.subprocess.run", lambda cmd, **kw: calls.append(cmd) or Done()
    )
    monkeypatch.setattr("print_explosion_3d.bambu.find_bambu", lambda: Path("/x/BambuStudio.app"))
    assert h.api.open_in_bambu() == {"opened": True}
    assert calls[0][:3] == ["open", "-a", "/x/BambuStudio.app"]
    assert calls[0][3].endswith("Box.stl")  # named after the project, not "model"


def test_bambu_missing_shows_the_file_instead(h, monkeypatch):
    h.api.send_message("a box")
    h.wait()
    calls = []

    class Done:
        returncode = 0

    monkeypatch.setattr(
        "print_explosion_3d.bambu.subprocess.run", lambda cmd, **kw: calls.append(cmd) or Done()
    )
    monkeypatch.setattr("print_explosion_3d.bambu.find_bambu", lambda: None)
    res = h.api.open_in_bambu()
    assert res["opened"] is False and res["revealed"] is True and "Bambu Studio" in res["error"]
    assert calls[0][:2] == ["open", "-R"]


def test_params_payload_skips_hidden_and_vectors_and_survives_junk():
    scad = "/* [Hidden] */\nsecret = 1;\n/* [Main] */\npos = [1,2,3];\nsize = 5; // [1:10]\n"
    payload = params_payload(scad)
    assert [p["name"] for s in payload for p in s["params"]] == ["size"]
    assert params_payload("\x00 not scad {{{") == []


def test_thumbnails_round_trip(h):
    h.api.send_message("a box")
    h.wait()
    png = base64.b64encode(b"\x89PNGfake").decode()
    assert h.api.save_thumbnail("data:image/png;base64," + png) is True
    folder = h.api.list_projects()[0]["folder"]
    assert h.api.project_thumbs()[folder].endswith(png)
    assert h.api.save_thumbnail("not a data url") is False
    assert h.api.save_thumbnail("data:image/png;base64," + "A" * 600_000) is False


def test_cost_readout_is_opt_in(tmp_path):
    from print_explosion_3d.ai.usage import total_cost

    log = tmp_path / "usage.jsonl"
    log.write_text(
        '{"time": "2000-01-01T00:00:00", "cost_usd": 1.0}\n'
        '{"time": "2999-01-01T00:00:00", "cost_usd": 0.25}\nnot json\n'
    )
    assert total_cost(log) == pytest.approx(1.25)
    assert total_cost(log, "2500-01-01T00:00:00") == pytest.approx(0.25)
    assert total_cost(tmp_path / "missing.jsonl") == 0.0

    off = Harness(tmp_path / "a")
    assert off.api.cost_text() is None
    on = Harness(tmp_path / "b")
    on.api._settings = load_settings({"PE_WORKSPACE_DIR": str(tmp_path / "b"), "PE_SHOW_COST": "1"})
    assert on.api.cost_text() == "AI cost this time: about $0.00"


def test_update_check_can_be_turned_off(tmp_path, monkeypatch):
    from print_explosion_3d import updater

    calls = []
    monkeypatch.setattr(
        updater, "check", lambda: calls.append(1) or updater.UpdateInfo(True, "- x")
    )
    h = Harness(tmp_path)
    assert h.api.check_update() == {"available": True, "notes": "- x"}
    h.api._settings = load_settings({"PE_WORKSPACE_DIR": str(tmp_path), "PE_UPDATE_CHECK": "false"})
    assert h.api.check_update() == {"available": False, "notes": ""}
    assert len(calls) == 1  # no git fetch at all when it's off


# --- v0.6: undo, copies, labels, sharing, preferences ---------------------------------------


def test_undo_steps_back_and_rebuilds(h):
    h.api.send_message("a box")
    h.wait()
    assert h.api.undo() == {"started": False, "error": "There's nothing to go back to yet."}
    h.api.set_params({"width": 70})
    assert h.api.undo()["started"] is True
    done = h.wait()
    assert done["error"] is None and "width = 40;" in h.api._current.read_scad()
    assert done["can_undo"] is False


def test_local_commands_undo_duplicate_and_copies(h):
    h.api.send_message("a box")
    h.wait()
    h.api.set_params({"width": 70})
    assert h.api.send_message("undo")["command"] == "undo"
    h.wait()
    dup = h.api.send_message("make a copy")
    assert dup["command"] == "duplicate" and dup["project"]["name"] == "Box copy"
    assert dup["project"]["has_stl"] and dup["project"]["chat"]["display"]
    assert h.api.send_message("print 3 of these")["command"] == "copies"
    assert len(h.provider.calls) == 1  # none of those used the AI


def test_copies_never_exceed_what_fits(h, monkeypatch):
    h.api.send_message("a box")
    h.wait()
    h.api._current.stl_path.write_bytes(stl_of_box(100, 100))
    res = h.api.set_copies(9)
    assert res["copies"] == 1 and res["max_copies"] == 1 and "Only 1" in res["note"]
    h.api._current.stl_path.write_bytes(stl_of_box(20, 20))
    assert h.api.set_copies(4)["copies"] == 4
    ready, placed = h.api._print_file(h.api._current)
    assert placed == 4 and ready.name == "Box x4.stl"


def test_model_info_is_plain_english(h):
    h.api.send_message("a box")
    h.wait()
    assert h.api.model_info() is None  # the fake build writes junk, not an STL
    h.api._current.stl_path.write_bytes(stl_of_box(40, 40, 20))
    info = h.api.model_info()
    assert info["ready"] is True and info["size"].startswith("40 \N{MULTIPLICATION SIGN} 40")
    assert info["time"].startswith("about") and info["plastic"].endswith("of plastic")
    assert json.dumps(info)


def test_make_labels_is_local_and_builds(h):
    res = h.api.send_message("make labels for sugar, flour and salt")
    assert res["command"] == "labels" and res["project"]["building"] is True
    h.wait()
    scad = h.api._current.read_scad()
    assert 'names = "sugar, flour, salt";' in scad
    assert h.provider.calls == []
    # A description is for the AI to design, not a list of words.
    assert h.api._local_command("make labels for my spice jars") is None
    assert h.api.send_message("make some labels")["command"] == "labels"
    h.wait()
    assert "Sugar, Flour" in h.api._current.read_scad()


def test_share_and_open_a_project(h, tmp_path):
    h.api.send_message("a box")
    h.wait()
    target = tmp_path / "Box.pe3d"

    class Window:
        def __init__(self, path):
            self.path = path

        def create_file_dialog(self, *_a, **_k):
            return str(self.path)

    h.api._window = Window(target)
    assert h.api.export_project() == {"saved": True, "name": "Box.pe3d"}
    res = h.api.import_project()
    assert (res["opened"] and res["project"]["name"] == "Box 2") or res["project"]["name"] == "Box"
    assert res["project"]["scad"] == SCAD
    target.write_bytes(b"not a zip")
    assert h.api.import_project()["error"].startswith("That doesn't look")


def test_preferences_are_validated_and_saved(h):
    assert h.api.get_prefs()["text_size"] == "normal"
    prefs = h.api.set_prefs({"text_size": "large", "still": True, "evil": 1, "high_contrast": "x"})
    assert prefs["text_size"] == "large" and prefs["still"] is True
    assert prefs["high_contrast"] is False and "evil" not in prefs
    assert h.api.set_prefs({"text_size": "gigantic"})["text_size"] == "large"
    assert h.api.boot()["prefs"] == prefs


def stl_of_box(w, d, h_=10):
    """A closed binary STL of a box centred on the plate."""
    import struct

    x, y = w / 2, d / 2
    v = [
        (-x, -y, 0),
        (x, -y, 0),
        (x, y, 0),
        (-x, y, 0),
        (-x, -y, h_),
        (x, -y, h_),
        (x, y, h_),
        (-x, y, h_),
    ]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    tris = [t for a, b, c, d_ in quads for t in ((a, b, c), (a, c, d_))]
    out = b"\0" * 80 + struct.pack("<I", len(tris))
    for t in tris:
        out += struct.pack("<12fH", 0, 0, 0, *[c for i in t for c in v[i]], 0)
    return out


def test_model_picker_lists_validates_and_starts_a_fresh_conversation(tmp_path):
    seen = []

    def factory(settings):
        seen.append((settings.provider, settings.model))
        return FakeProvider([reply(), reply()])

    h = Harness(tmp_path)
    h.api._provider_factory = factory
    listed = h.api.list_models()
    assert listed["current"] == "anthropic:claude-sonnet-5-5"
    assert {c["key"] for c in listed["choices"]} >= {"anthropic:claude-opus-5-5"}
    h.api.send_message("a box")
    h.wait()
    first_designer = h.api._designer
    assert h.api.set_model("nope")["ok"] is False
    assert h.api.set_model("anthropic:claude-opus-5-5")["ok"] is True
    assert h.api._designer is None and first_designer is not None
    h.api.send_message("taller")
    h.wait()
    assert seen == [("anthropic", "claude-sonnet-5-5"), ("anthropic", "claude-opus-5-5")]
    h.api.set_prefs({"still": True})  # saving a look-and-feel choice keeps the model choice
    assert h.api.list_models()["current"] == "anthropic:claude-opus-5-5"


def test_a_hand_set_model_still_shows_in_the_picker(tmp_path):
    h = Harness(tmp_path)
    h.api._settings = load_settings({"PE_WORKSPACE_DIR": str(tmp_path), "PE_MODEL": "my-model"})
    listed = h.api.list_models()
    assert listed["current"] == "anthropic:my-model"
    assert listed["choices"][0]["label"] == "Custom (from settings)"
