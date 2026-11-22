#!/bin/bash
# Symlinks the daemon and service into place, copies the example config if none exists,
# and starts the service.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
config="${XDG_CONFIG_HOME:-$HOME/.config}/steam-input-hotkeys/config.toml"

if ! /usr/bin/python3 -c 'import Xlib.ext.xinput' 2>/dev/null; then
    echo "python-xlib is missing. Install it first (Arch: python-xlib, Debian/Ubuntu: python3-xlib, Fedora: python3-xlib)." >&2
    exit 1
fi

mkdir -p ~/.local/bin ~/.config/systemd/user "$(dirname "$config")"
ln -sf "$here/steam-input-hotkeys" ~/.local/bin/steam-input-hotkeys
ln -sf "$here/systemd/steam-input-hotkeys.service" ~/.config/systemd/user/steam-input-hotkeys.service
[ -e "$config" ] || cp "$here/config.example.toml" "$config"

systemctl --user daemon-reload
systemctl --user enable --now steam-input-hotkeys
echo "Installed. Edit $config, then: systemctl --user reload steam-input-hotkeys"
