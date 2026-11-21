#!/bin/bash
# Launch Print Explosion 3D. Called by the Dock app; lives in the repo so launch logic updates
# through git. Every step is best-effort except the last: the user must always get a window.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$HOME/Library/Logs/PrintExplosion3D"
mkdir -p "$LOG_DIR"
exec >>"$LOG_DIR/launch.log" 2>&1
echo "--- $(date) ---"

export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$REPO" || exit 1

# Only fast-forward, only on main, never over local changes.
if [ "$(git branch --show-current 2>/dev/null)" = "main" ] && [ -z "$(git status --porcelain 2>/dev/null)" ]; then
  git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=15 pull --ff-only --quiet 2>&1 || echo "pull skipped"
fi
uv sync --frozen --quiet 2>&1 || echo "sync skipped"
exec uv run --frozen print-explosion
