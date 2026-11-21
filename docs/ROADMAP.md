# Roadmap

Architecture and conventions live in `CLAUDE.md`; this file is just the checklist.

## M0 — Kickoff ✅
- [x] uv package (Python 3.13), deps: anthropic, pywebview, python-dotenv; dev: ruff, pytest, ty
- [x] `config.py` with defaults + `.env` template generator
- [x] Vendored OpenSCAD skill snapshot (`third_party/openscad-skill`) + runtime lib with A1 mini profile
- [x] pywebview window spike: 3-panel layout, JS bridge, Three.js viewer (Z-up, shadow, no grid,
      spin + click-to-pause, zoom/angle sliders)
- [x] `scripts/smoke_ui.py` (canvas snapshot), tests for config and lib render
- [x] App name in menu bar/Dock + app icon (`macos.py`, `scripts/make_icon.py`)

## M1 — OpenSCAD pipeline ✅
- [x] `scad/runner.py`: binary resolution, Manifold + binstl, `--summary-file` bbox, timeout,
      background thread, stderr → structured errors (line numbers, message); `PE_RENDER_TIMEOUT`
- [x] Bed checks: fits 180³, rests on z = 0, not empty
- [x] `scad/params.py`: Customizer parser (number, range/step, dropdown incl. `value:Label`, bool,
      string, sections, `[Hidden]`), in-place value write-back
- [x] Fixture tests for each of the above

## M2 — Workspace ✅
- [x] `workspace/store.py`: `~/Documents/Print Explosion 3D/<project>/` with `project.json`,
      `model.scad`, `history/` (cap 20), `chat.json` (raw replay + display text), `attachments/`,
      `model.stl`; top-level `state.json` (last opened)
- [x] Autosave + status; delete → macOS Trash (NSFileManager); stale cleanup on startup
- [x] Local fuzzy project lookup ("open my bird feeder")

## M3 — AI layer ✅
- [x] `ai/base.py` neutral types (user / assistant / note, text, images, opaque raw replay)
- [x] `ai/anthropic_provider.py`: beta stream, cache_control, adaptive thinking, effort,
      `fallbacks: "default"`, friendly errors (no key, low credit balance, offline, refusal)
- [x] `ai/fake_provider.py`
- [x] `designer/system_prompt.md` curated from the vendored skill + printing rules + response protocol
- [x] `designer/protocol.py` (regex extraction) and turn loop: AI design → auto-render →
      auto-fix (≤ `PE_MAX_AUTO_FIXES`)
- [x] Resume = fresh conversation seeded with memory note + current .scad
- [x] `usage.jsonl` cost log; tests with FakeProvider and a mocked SDK client

## M4 — UI ✅
- [x] Chat: streaming, "Design updated" chip, image attach/paste/drop (downscale to 1568 px JPEG),
      choice chips, New / Delete project, autosave status, project switcher
- [x] Viewer: STL over the bridge (base64) → STLLoader; keep current look
- [x] Adjust panel: sections, slider + number, dropdown, checkbox, text; Update the model; Save STL (dialog);
      Open in Bambu Studio

## M5 — Mac integration & deploy (in progress)
- [ ] (needs a manual check with Bambu Studio running) `bambu.py`: `open -a BambuStudio <stl>`; check whether a running instance gets a new project
      or needs `open -n`
- [x] `scripts/install.sh` (CLT/git, user-local uv, OpenSCAD ≥ 2025, clone, `.env`, launcher .app)
- [x] Dock launcher: generated `~/Applications/Print Explosion 3D.app` (Info.plist, `.icns` from
      `assets/icon.png` via `sips` + `iconutil`); its executable only calls `scripts/launch.sh` in the
      repo so launch logic updates via git. Logs to `~/Library/Logs/PrintExplosion3D`
- [ ] Verify with `lsappinfo` that the Dock shows one icon when the launcher hands off to Python;
      if it shows two, fall back to a tiny compiled stub (clang ships with git's CLT)
- [ ] Optional (ask Brad first): install script pins the launcher to her Dock
- [x] Update check on start: background `git fetch origin main` (short timeout, silent offline);
      offer an update only if `main` is ahead, fast-forwardable, and the working tree is clean
      (auto-disables on a dev checkout)
- [x] Update banner: "A new version is ready. [Update now] [Later]" + top entry of `CHANGELOG.md`
      read from `origin/main`; Update now → `git pull --ff-only` → `uv sync --frozen` → relaunch;
      failures show a friendly "try again later"

## M6 — Polish / later ✅
- [x] Project thumbnails via `viewer.snapshot()`
- [x] Optional cost readout (`PE_SHOW_COST`)
- [x] Inch hints next to mm values
