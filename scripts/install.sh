#!/bin/bash
# One-shot installer for a fresh Mac. Safe to re-run: it only fills in what's missing.
#   bash <(curl -fsSL https://raw.githubusercontent.com/bradmartin333/print-explosion-3d/main/scripts/install.sh)
set -euo pipefail

REPO_URL="https://github.com/bradmartin333/print-explosion-3d.git"
DEST="${PE_INSTALL_DIR:-$HOME/PrintExplosion3D}"
OPENSCAD_APP="/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"
say() { printf '\n==> %s\n' "$*"; }

# 1. Git (comes with the Command Line Tools)
if ! xcode-select -p >/dev/null 2>&1 || ! command -v git >/dev/null; then
  say "Installing Apple's developer tools. Click Install in the window that appears."
  xcode-select --install || true
  echo "When that finishes, run this installer again."
  exit 1
fi

# 2. uv, installed just for this user (no admin password)
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null; then
  say "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# 3. OpenSCAD 2025 or newer (older builds lack the fast Manifold engine)
openscad_year() {
  local bin
  bin="$(command -v openscad || true)"
  [ -x "$OPENSCAD_APP" ] && bin="$OPENSCAD_APP"
  [ -n "$bin" ] && "$bin" --version 2>&1 | grep -Eo '20[0-9]{2}' | head -1
}
YEAR="$(openscad_year || true)"
if [ -z "$YEAR" ] || [ "$YEAR" -lt 2025 ]; then
  say "OpenSCAD 2025 or newer is needed."
  echo "Opening the download page. Install the newest 'Development Snapshot' (drag to Applications),"
  echo "then run this installer again."
  open "https://openscad.org/downloads.html#snapshots"
  exit 1
fi

# 4. The app itself
if [ -d "$DEST/.git" ]; then
  say "Updating $DEST"
  git -C "$DEST" pull --ff-only
else
  say "Downloading the app to $DEST"
  git clone "$REPO_URL" "$DEST"
fi
cd "$DEST"
uv sync --frozen

# 5. AI key (the only thing the user can't get on their own)
if [ ! -f .env ] || ! grep -q '^ANTHROPIC_API_KEY=.\+' .env; then
  say "Paste the AI key you were given (nothing shows as you paste), then press Return:"
  read -rs KEY
  echo
  printf 'ANTHROPIC_API_KEY=%s\n' "$KEY" >.env
  chmod 600 .env
fi

# 6. The Dock-ready app
say "Creating the app in ~/Applications"
mkdir -p "$HOME/Applications"
bash scripts/make_launcher.sh

say "All done! Open 'Print Explosion 3D' from your Applications folder."
open -R "$HOME/Applications/Print Explosion 3D.app" || true
