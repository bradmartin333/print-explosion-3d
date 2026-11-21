#!/usr/bin/env bash
# Refresh the vendored OpenSCAD skill snapshot in third_party/openscad-skill/.
# Usage: scripts/update_openscad_skill.sh <commit-or-branch>
# After running, review `git diff third_party/` and port relevant changes into the derived files
# listed in third_party/openscad-skill/PROVENANCE.md, then update the commit hash there.
set -euo pipefail

REF="${1:?usage: $0 <commit-or-branch>}"
REPO="https://github.com/andreahaku/openscad_claude_skill.git"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DST="$ROOT/third_party/openscad-skill"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git clone --quiet "$REPO" "$TMP/skill"
git -C "$TMP/skill" checkout --quiet "$REF"
SHA="$(git -C "$TMP/skill" rev-parse HEAD)"

mkdir -p "$DST/references" "$DST/templates"
cp "$TMP/skill/SKILL.md" "$TMP/skill/README.md" "$DST/"
cp "$TMP/skill/references/language-reference.md" "$DST/references/"
cp "$TMP/skill/templates/printable-lib.scad" "$TMP/skill/templates/printer-profile.scad" "$DST/templates/"

echo "Vendored openscad-skill at $SHA"
echo "Next: git diff third_party/ ; port changes to derived files ; update PROVENANCE.md commit."
