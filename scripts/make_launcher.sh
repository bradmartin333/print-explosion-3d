#!/bin/bash
# Build ~/Applications/Print Explosion 3D.app. Its executable only calls scripts/launch.sh in the
# repo, so launch logic updates via git; re-running this just refreshes the icon/Info.plist.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${1:-$HOME/Applications/Print Explosion 3D.app}"
NAME="Print Explosion 3D"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat >"$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>$NAME</string>
  <key>CFBundleDisplayName</key><string>$NAME</string>
  <key>CFBundleIdentifier</key><string>com.printexplosion3d.launcher</string><!-- = macos.LAUNCHER_BUNDLE_ID -->
  <key>CFBundleExecutable</key><string>launch</string>
  <key>CFBundleIconFile</key><string>icon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>1</string>
</dict></plist>
PLIST

# Hard-wire the repo path; the script it points to is the part that updates.
cat >"$APP/Contents/MacOS/launch" <<SH
#!/bin/bash
exec /bin/bash "$REPO/scripts/launch.sh"
SH
chmod +x "$APP/Contents/MacOS/launch"

# .icns from assets/icon.png
ICONSET="$(mktemp -d)/icon.iconset"
mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s "$REPO/src/print_explosion_3d/assets/icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s*2)) $((s*2)) "$REPO/src/print_explosion_3d/assets/icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/icon.icns"
touch "$APP"
echo "Built $APP"
