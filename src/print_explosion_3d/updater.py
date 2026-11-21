"""Update check and apply. The app updates from `main` on GitHub via plain git.

`check()` is silent on any failure (offline, not a git checkout, dev tree with changes) and only
reports an update when `origin/main` is ahead, fast-forwardable and the working tree is clean.
`apply()` pulls and syncs dependencies; `relaunch()` restarts through the Dock app or
`scripts/launch.sh`.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from print_explosion_3d.config import REPO_ROOT
from print_explosion_3d.macos import launcher_app

BRANCH = "main"
FETCH_TIMEOUT = 8
SYNC_TIMEOUT = 300
MSG_UPDATE_FAILED = "I couldn't update just now. Please try again later."

_ENTRY = re.compile(r"^##\s+.*$", re.MULTILINE)


@dataclass(frozen=True)
class UpdateInfo:
    available: bool
    notes: str = ""  # the top CHANGELOG entry, plain text


def _git(
    repo: Path, *args: str, timeout: float = FETCH_TIMEOUT
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def top_changelog_entry(text: str) -> str:
    """The newest entry (first `## ` heading and its bullets), heading dropped."""
    heads = list(_ENTRY.finditer(text))
    if not heads:
        return ""
    end = heads[1].start() if len(heads) > 1 else len(text)
    return text[heads[0].end() : end].strip()


def check(repo: Path = REPO_ROOT) -> UpdateInfo:
    """Is there a newer version on origin/main that can be applied cleanly? Never raises."""
    none = UpdateInfo(False)
    try:
        if _git(repo, "rev-parse", "--is-inside-work-tree").returncode != 0:
            return none
        if _git(repo, "branch", "--show-current").stdout.strip() != BRANCH:
            return none  # dev checkout on another branch
        if _git(repo, "status", "--porcelain").stdout.strip():
            return none  # local changes: never touch them
        if _git(repo, "fetch", "--quiet", "origin", BRANCH).returncode != 0:
            return none
        remote = f"origin/{BRANCH}"
        ahead = _git(repo, "rev-list", "--count", f"HEAD..{remote}").stdout.strip()
        if not ahead.isdigit() or int(ahead) == 0:
            return none
        if _git(repo, "merge-base", "--is-ancestor", "HEAD", remote).returncode != 0:
            return none  # diverged: can't fast-forward
        log = _git(repo, "show", f"{remote}:CHANGELOG.md")
        notes = top_changelog_entry(log.stdout) if log.returncode == 0 else ""
        return UpdateInfo(True, notes)
    except (OSError, subprocess.SubprocessError):
        return none


def apply(repo: Path = REPO_ROOT) -> bool:
    """Pull and sync dependencies. True on success; the caller relaunches."""
    try:
        if _git(repo, "pull", "--ff-only", "origin", BRANCH, timeout=60).returncode != 0:
            return False
        sync = subprocess.run(
            ["uv", "sync", "--frozen"],
            cwd=repo,
            capture_output=True,
            timeout=SYNC_TIMEOUT,
            check=False,
        )
        return sync.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def relaunch_command(repo: Path, app: Path | None) -> list[str]:
    """How to start a fresh copy.

    Opened from the Dock app: reopen that app through LaunchServices (`-n`, since this copy is
    still running), so the new window stays under the same Dock icon. A plain child process
    would get a second icon. Otherwise run the launch script, or the module as a last resort.
    """
    if app is not None:
        return ["/usr/bin/open", "-n", str(app)]
    script = repo / "scripts" / "launch.sh"
    if script.exists():
        return ["/bin/bash", str(script)]
    return [sys.executable, "-m", "print_explosion_3d.app"]


def relaunch(repo: Path = REPO_ROOT) -> None:
    """Start a fresh copy through the launcher, then quit this one."""
    cmd = relaunch_command(repo, launcher_app())
    quiet = subprocess.DEVNULL
    subprocess.Popen(cmd, cwd=repo, start_new_session=True, stdout=quiet, stderr=quiet)
    os._exit(0)
