# Print Explosion 3D

Single-window Mac app: chat (and photos) → OpenSCAD design → spinning preview → simple controls →
STL / Bambu Studio. The end user is a non-technical parent with a Bambu Lab A1 mini. The app is in
production; the README is the product spec.

## Audience rules
- UI copy is plain English. No "parameters", "SCAD", "render", "manifold" in anything she sees.
- She never sees code, stack traces, or OpenSCAD errors. Errors become friendly text, or an automatic
  fix round-trip with the AI.
- No file browser is needed for normal use. Projects are found and resumed by name in the chat.

## Commands
```sh
uv sync                                   # install/refresh deps (launcher runs `uv sync --frozen`)
uv run print-explosion                    # run the app (PE_DEBUG=1 enables Web Inspector)
uv run pytest                             # tests; live_api tests excluded by default
uv run pytest -m live_api                 # opt-in tests that SPEND CREDITS
uv run ruff check --fix && uv run ruff format
uv run ty check
uv run python scripts/smoke_ui.py        # real window: bridge, WebGL, app name; PNG → build/smoke.png
uv run python scripts/screenshots.py     # README screenshots → docs/screenshots/ (needs OpenSCAD)
uv run python scripts/make_icon.py       # regenerate assets/icon.svg + icon.png
uv run python -m print_explosion_3d.config > .env.example  # regenerate the settings template
scripts/vendor_three.sh [ver]             # re-vendor Three.js (pinned 0.170.0)
scripts/update_openscad_skill.sh <ref>    # refresh third_party/openscad-skill snapshot
```
Run ruff, ty and pytest before calling work done. UI changes also get `scripts/smoke_ui.py`. Look
at the PNG. It's WebKit's own snapshot of the whole window, because screencapture isn't available
here (no Screen Recording permission).

## Layout
- `src/print_explosion_3d/`
  - `config.py`: `SPEC` is the single source of truth for settings. Each has a default, and bad
    values fall back to it instead of raising.
  - `app.py`: `launch()` brands the process, creates the pywebview window, starts the loop.
    `api.py` is the JS bridge: thin, and only public methods are exposed.
  - `macos.py`: menu bar/Dock name for a bare Python process (CFBundleName + a private
    LaunchServices rename, all failures swallowed). Icon is `assets/icon.png`.
  - `ai/`: `Provider` protocol, `anthropic_provider.py`, `fake_provider.py`.
  - `designer/`: system prompt, response-protocol parsing, turn loop with auto-fix.
  - `scad/`: `runner.py` and `params.py`. `lib/` is on `OPENSCADPATH` and holds
    printable-lib + the A1 mini profile.
  - `workspace/` (projects on disk) and `bambu.py` (open in Bambu Studio).
- `web/`: vanilla ES modules, no build step. `js/viewer.js` is Three.js (Z-up, shadow, no grid).
  `vendor/three/` is pinned and vendored; don't hand-edit it.
- `third_party/openscad-skill/`: pinned upstream snapshot (MIT). `PROVENANCE.md` lists which repo
  files derive from it.
- `tests/`: `fixtures/` holds .scad samples. Mark tests that need OpenSCAD with
  `@pytest.mark.openscad`.

## AI rules (credits are scarce)
- Import the Anthropic SDK **only** in `ai/anthropic_provider.py`. Everything else uses the
  neutral `Provider` types, so another provider can be dropped in.
- Default model is `claude-sonnet-5-5`, effort `medium`, adaptive thinking, streaming via
  `client.beta.messages.stream` with `fallbacks: "default"` (beta
  `server-side-fallback-2026-07-01`). No forced `tool_choice` and no assistant prefill: both 400 on
  this model. Check `stop_reason == "refusal"` before reading content.
- **Caching:** the system prompt is byte-stable. Never put timestamps, project names or per-user
  data in it; those go in messages. Use top-level `cache_control`. Verify with
  `usage.cache_read_input_tokens`.
- **History is append-only.** Store each assistant turn's raw content blocks and replay them
  unchanged, including thinking blocks. Editing or deleting past turns breaks the cache and Sonnet
  5.5's preserved thinking. Resuming an old project starts a *new* conversation seeded with the
  project's memory note and its current .scad.
- App-originated info (she edited a value, a build failed) goes in as a neutral `note` message. The
  Anthropic adapter maps it to a mid-conversation `{"role": "system"}` message.
- Prefer regex and local logic over model calls: code extraction, Customizer parsing, project
  lookup (`difflib`), and obvious commands like "start a new project". Never add a "helper" model
  call where a regex would do.
- Cap automatic fix round-trips at `PE_MAX_AUTO_FIXES`. Log `usage` per call to `usage.jsonl` in
  the workspace.
- Tests never hit a real API. Use `FakeProvider` or a mocked client; `live_api` is opt-in only.

## Response protocol (designer ↔ app)
The model replies with short prose, then **one** fenced ` ```openscad ` block holding the full file,
then optional tags parsed by regex:
- `<title>Bird Feeder</title>`: project name, sent on the first design.
- `<note>…</note>`: a one-line project memory used to resume later.
- `<choices>Round|Square</choices>`: quick-reply buttons for a clarifying question.

The prose must not contain code. The UI hides the code block behind a "Design updated" chip.

## OpenSCAD
- Find the binary in this order: `OPENSCAD_BIN` → `PATH` → `/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD`.
  Requires a 2025+ build: always run `--backend Manifold --export-format binstl`, and use
  `--summary-file` for the bounding box.
- Set `OPENSCADPATH` to `src/print_explosion_3d/scad/lib`, and have designs `use <printable-lib.scad>`.
  Never put `~` in `use <>`/`include <>`.
- Designs declare their knobs in Customizer syntax at the top (`name = 10; // [1:100]`,
  `/* [Section] */`, `/* [Hidden] */`), each with a plain-English comment on the line above. Edits
  she makes in the side panel are written back into the .scad in place, so the AI always sees
  current values.

## Printing rules (Bambu Lab A1 mini, 0.4 mm nozzle, PLA, textured PEI)
- Must fit 180 × 180 × 180 mm. Center the model on XY with its largest flat face on z = 0.
- No supports: overhangs ≤ 45°, and use chamfers rather than fillets on faces that point down.
  Bridges ≤ 10 mm.
- A 0.4–0.6 mm chamfer on bottom edges lets it print with no brim and come off the plate easily.
  Avoid tall, thin parts with a small footprint.
- Walls ≥ 1.2 mm, floors ≥ 0.8 mm. Text ≥ 5 mm tall and ≥ 0.6 mm raised or recessed.

## Deploy constraints (her Mac updates via `git pull`)
- The launcher runs `git pull --ff-only` → `uv sync --frozen` → `uv run print-explosion`, so a
  change must never need manual steps on her machine. Commit `uv.lock`.
- Every new setting goes in `config.SPEC` with a working default. Only `ANTHROPIC_API_KEY` is
  required.
- Everything except the AI chat must work offline.
- Her app updates from `main` (update check + banner), so `main` must always be shippable.
  Any change she'll notice gets a plain-English entry at the top of `CHANGELOG.md`; the
  update banner shows that entry.
- `.env.example` is generated from `config.SPEC`. After changing `SPEC`, regenerate it with
  `uv run python -m print_explosion_3d.config > .env.example`. A permission rule here blocks
  Claude from reading or writing `.env*` files, so ask Brad to run that command.

## README
Keep `README.md` up to date as the repo evolves. When a change affects what the app does, how it's
installed or run, its settings, or its screenshots, update the README in the same change. It is the
public face of the project: plain English first, technical detail last. The screenshots in
`docs/screenshots/` come from `scripts/screenshots.py`, which runs the real app on the demo designs in
`scripts/demo/`. Re-run it when the UI or those designs change.

## Git
Work on the current branch. Ask before creating a worktree, and if one is used, merge it back,
remove it and delete its branch before finishing. Commit only when asked.
