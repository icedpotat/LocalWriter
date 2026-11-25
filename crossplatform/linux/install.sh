#!/bin/sh
# Installs LocalWriter for the current user (no root needed): ~/.local/bin + app-menu entry.
set -e
cd "$(dirname "$0")"
mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons
cp LocalWriter ~/.local/bin/LocalWriter
cp localwriter.png ~/.local/share/icons/localwriter.png
cat > ~/.local/share/applications/localwriter.desktop <<DESK
[Desktop Entry]
Type=Application
Name=LocalWriter
Comment=Rewrite selected text with a local AI, snippets and a password vault
Exec=$HOME/.local/bin/LocalWriter
Icon=$HOME/.local/share/icons/localwriter.png
Categories=Utility;
DESK
echo "Installed. Start it from your app menu or run: ~/.local/bin/LocalWriter"
