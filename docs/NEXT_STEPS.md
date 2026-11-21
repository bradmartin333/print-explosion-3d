# Next steps

Scratch list for the next session. Append freely; move finished items into `ROADMAP.md` or delete them.

## Open after M5 / M6

1. **Bambu Studio with a model already open.** Open a model in Bambu Studio, then press "Open in
   Bambu Studio" in the app. If it replaces her project or asks to confirm, switch `bambu.py` to
   `open -n`. Needs Bambu Studio launched, so it's a manual check.
2. **One Dock icon.** Run `scripts/make_launcher.sh`, open the app, and check `lsappinfo list` for a
   single entry. If there are two, build the small compiled stub (clang ships with the CLT).
3. **Installer dry run.** `scripts/install.sh` has only passed `bash -n`. Run it on a clean user
   account, or at least with `PE_INSTALL_DIR` pointed at a temp folder.
4. **Pin to Dock.** Decide whether the installer should do it (roadmap says to ask Brad first).
5. **Real screenshots.** README and `docs/screenshots/` still hold placeholders. Capture the window
   by hand (no Screen Recording permission here). While at it, look at the new project dropdown with
   thumbnails and the row alignment by eye; only heights were checked numerically.
6. **Commit and push.** M5 and M6 are uncommitted on `main`, and her Mac updates from `main`, so
   items 1-3 should pass first.
7. **Version number.** `pyproject.toml` says 0.1.0 while `CHANGELOG.md` is at 0.4.0. Decide whether
   to bump it.

## Dropped
- BOSL2 library and AMS lite multi-color 3MF (removed from the roadmap).

## Your notes
