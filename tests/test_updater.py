import subprocess
from pathlib import Path

import pytest

from print_explosion_3d import updater


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repos(tmp_path):
    origin = tmp_path / "origin"
    origin.mkdir()
    git(origin, "init", "-b", "main")
    (origin / "CHANGELOG.md").write_text("# Changelog\n\n## 0.1.0\n- old\n")
    git(origin, "add", ".")
    git(origin, "commit", "-m", "one")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", str(origin), str(clone)], check=True, capture_output=True)
    return origin, clone


def publish(origin: Path) -> None:
    log = "# Changelog\n\n## 0.2.0\n- new thing\n- another\n\n## 0.1.0\n- old\n"
    (origin / "CHANGELOG.md").write_text(log)
    git(origin, "commit", "-am", "two")


def test_top_entry():
    text = "# C\n\nintro\n\n## 0.2\n- a\n- b\n\n## 0.1\n- c\n"
    assert updater.top_changelog_entry(text) == "- a\n- b"
    assert updater.top_changelog_entry("nothing") == ""


def test_up_to_date(repos):
    _, clone = repos
    assert not updater.check(clone).available


def test_update_available_with_notes(repos):
    origin, clone = repos
    publish(origin)
    info = updater.check(clone)
    assert info.available
    assert "new thing" in info.notes and "old" not in info.notes


def test_dirty_tree_disables(repos):
    origin, clone = repos
    publish(origin)
    (clone / "scratch.txt").write_text("x")
    assert not updater.check(clone).available


def test_dev_branch_disables(repos):
    origin, clone = repos
    publish(origin)
    git(clone, "checkout", "-b", "dev")
    assert not updater.check(clone).available


def test_diverged_disables(repos):
    origin, clone = repos
    publish(origin)
    (clone / "local.txt").write_text("x")
    git(clone, "add", ".")
    git(clone, "commit", "-m", "local")
    assert not updater.check(clone).available


def test_not_a_repo_or_offline(tmp_path, repos):
    assert not updater.check(tmp_path).available
    _, clone = repos
    git(clone, "remote", "set-url", "origin", str(tmp_path / "gone"))
    assert not updater.check(clone).available


def test_relaunch_reopens_the_dock_app(tmp_path):
    app = tmp_path / "Print Explosion 3D.app"
    assert updater.relaunch_command(tmp_path, app) == ["/usr/bin/open", "-n", str(app)]


def test_relaunch_falls_back_to_the_launch_script(tmp_path):
    script = tmp_path / "scripts" / "launch.sh"
    script.parent.mkdir()
    script.write_text("#!/bin/bash\n")
    assert updater.relaunch_command(tmp_path, None) == ["/bin/bash", str(script)]
    script.unlink()
    assert updater.relaunch_command(tmp_path, None)[1:] == ["-m", "print_explosion_3d.app"]
