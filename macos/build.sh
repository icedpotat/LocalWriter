#!/bin/zsh
# Builds LocalWriter.app. Usage: ./build.sh [install]   (install copies to /Applications and launches)
# Set VERSION=1.2.3 to stamp a version (the release workflow does this).
set -e
cd "$(dirname "$0")"
APP=build/LocalWriter.app
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
if [[ ! -f Resources/AppIcon.icns ]]; then   # regenerate the icon if it was deleted
  swift tools/make_icon.swift && iconutil -c icns Resources/AppIcon.iconset -o Resources/AppIcon.icns
  rm -rf Resources/AppIcon.iconset
fi
cp Resources/AppIcon.icns "$APP/Contents/Resources/"
swiftc -O -swift-version 5 -target arm64-apple-macos13 Sources/*.swift -o "$APP/Contents/MacOS/LocalWriter"
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>local.localwriter</string>
  <key>CFBundleName</key><string>LocalWriter</string>
  <key>CFBundleExecutable</key><string>LocalWriter</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>${VERSION:-1.0}</string>
  <key>CFBundleVersion</key><string>${VERSION:-1}</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
</dict></plist>
EOF
# Sign with a real certificate if available: Accessibility permission is tied to the signature, and an
# ad-hoc signature changes on every build (macOS then silently ignores the old permission entry).
IDENTITY=$(security find-identity -v -p codesigning | grep -m1 -oE '"(Apple Development|Developer ID Application)[^"]*"' | tr -d '"' || true)
if [[ -n "$IDENTITY" ]]; then
  codesign --force --sign "$IDENTITY" --identifier local.localwriter "$APP"
  echo "Signed with: $IDENTITY"
else
  codesign --force --sign - --identifier local.localwriter "$APP"
  echo "Ad-hoc signed — re-grant Accessibility after each rebuild"
fi
echo "Built $APP"
if [[ "$1" == "install" ]]; then
  pkill -x LocalWriter || true
  rm -rf /Applications/LocalWriter.app && cp -R "$APP" /Applications/
  open /Applications/LocalWriter.app
  echo "Installed and launched /Applications/LocalWriter.app"
fi
