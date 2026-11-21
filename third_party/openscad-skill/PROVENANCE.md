# openscad-skill (vendored)

- Upstream: https://github.com/andreahaku/openscad_claude_skill
- Commit: `3483e23dd4c5b41144ba69dac13d7b56ecdf0c0c` (2026-10-17)
- License: MIT, as declared in the upstream README's "License" section. The upstream repo ships no
  LICENSE file, so `LICENSE` here is the standard MIT text attributed to the author.
- Refresh: `scripts/update_openscad_skill.sh <commit>`

## Why it is vendored instead of "installed"

The app runs on the plain Messages API on a Mac with no Claude Code, so a Claude Code skill
directory can't be used directly. API-hosted Agent Skills would need the code-execution
container (extra cost and latency per session), and OpenSCAD isn't available in that sandbox.
Instead, this pinned snapshot is the **reference source** for two derived artifacts:

| Derived file | What changed from upstream |
|---|---|
| `src/print_explosion_3d/scad/lib/printable-lib.scad` | Attribution header only. |
| `src/print_explosion_3d/scad/lib/printer-profile.scad` | Re-targeted to Bambu Lab A1 mini / PLA (bed 180³), English provenance strings, added `first_layer_chamfer`. Same variable names. |
| `src/print_explosion_3d/designer/system_prompt.md` (M3) | Curated condensation of SKILL.md Quick/Refine guidance + `references/language-reference.md`, rewritten for an in-app chat (no bash scripts, no PNG reads). |

Files kept here unchanged: `SKILL.md`, `README.md`, `references/language-reference.md`,
`templates/printable-lib.scad`, `templates/printer-profile.scad`.
