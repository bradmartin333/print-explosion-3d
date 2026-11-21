# Screenshots

Used by the main README. Regenerate them from the real window with:

```sh
uv run python scripts/screenshots.py      # writes hero, chat, adjust and projects PNGs here
```

It seeds a throwaway workspace with the designs in `scripts/demo/`, builds them with OpenSCAD, and
plays a short chat through the real UI with a scripted designer (no API key, no credits). Captures
come from WebKit's own page snapshot, so no Screen Recording permission is needed.

- `hero.png`: full window mid-design (scaled to 1600 px wide)
- `chat.png`: conversation with a photo, "Design updated" chips, quick replies
- `adjust.png`: Adjust panel next to the model (scaled to 1600 px wide)
- `projects.png`: project switcher with pictures

`uv run python scripts/smoke_ui.py` writes a full-window `build/smoke.png` for quick checks.
