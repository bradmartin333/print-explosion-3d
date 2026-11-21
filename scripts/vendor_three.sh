#!/usr/bin/env bash
# Download the pinned Three.js build into web/vendor/three/ (no npm, no build step).
# Usage: scripts/vendor_three.sh [version]   (default pinned below; bump deliberately)
set -euo pipefail

VERSION="${1:-0.170.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DST="$ROOT/web/vendor/three"
BASE="https://cdn.jsdelivr.net/npm/three@${VERSION}"

mkdir -p "$DST/addons/loaders"
curl -fsSL "$BASE/build/three.module.min.js" -o "$DST/three.module.min.js"
curl -fsSL "$BASE/examples/jsm/loaders/STLLoader.js" -o "$DST/addons/loaders/STLLoader.js"
curl -fsSL "$BASE/LICENSE" -o "$DST/LICENSE"
echo "$VERSION" > "$DST/VERSION"
echo "Vendored three@$VERSION into web/vendor/three/"
