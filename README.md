# steam-input-hotkeys

Make Steam Input key bindings trigger desktop commands on Wayland.

## The problem

You bind a controller button, or a radial menu entry, to a key in Steam Input, and you have a
compositor shortcut for that key (Hyprland `bind`, KDE/GNOME custom shortcut, Sway `bindsym`).
Pressing the button does nothing.

On a Linux desktop, Steam Input sends keyboard bindings through **XTest** into **XWayland**,
not through a real input device. The Wayland compositor never sees those key presses, so its
shortcuts never fire. Tools that read evdev devices (input-remapper, evdev scripts) don't see
them either, and X11 hotkey daemons that grab keys (sxhkd, xbindkeys) only fire while an X11
window has focus.

## How this fixes it

XInput2 *raw* key events on the XWayland root window are delivered to any X client that asks
for them, whatever window has focus. `steam-input-hotkeys` listens there and runs the shell
command you bound to each key. Anything Steam Input can press becomes a desktop action:
buttons, back paddles, chords, radial menus, touch menus, action sets.

It should work on any Wayland compositor with XWayland. So far it's tested on Hyprland only.

## Install

Needs Python 3.11+ and python-xlib (Arch: `python-xlib`, Debian/Ubuntu/Fedora: `python3-xlib`).

```bash
git clone https://github.com/xplodingeggo/steam-input-hotkeys
cd steam-input-hotkeys
./install.sh
```

This symlinks the script into `~/.local/bin`, installs and starts a systemd user service, and
copies `config.example.toml` to `~/.config/steam-input-hotkeys/config.toml` if you don't have one.

## Configure

`~/.config/steam-input-hotkeys/config.toml`:

```toml
[keys]
F14 = "playerctl play-pause"
F15 = "wpctl set-mute @DEFAULT_AUDIO_SOURCE@ toggle"
"ctrl+F16" = "notify-send 'Hello from my controller'"
F13 = { command = "some-command", cooldown = 1 }
```

- Keys are X keysym names (`F14`, `Page_Down`, `Pause`, `Scroll_Lock`, `KP_5`, ...).
- Optional modifiers: `ctrl`, `shift`, `alt`, `super`, joined with `+`. Modifiers are not
  exclusive: a plain `F14` binding also fires for Ctrl+F14.
- `cooldown` (seconds, default 0.3) ignores repeats of the same binding.
- Commands run with `/bin/sh -c`, detached, in the service's environment.

After editing: `systemctl --user reload steam-input-hotkeys`. If the new config has an error,
the old bindings stay and the error goes to `journalctl --user -u steam-input-hotkeys`.

Then in Steam Input, bind a button or a radial menu entry to that key (*Keyboard → F14*).

To see what name a binding sends, run `steam-input-hotkeys --listen` and press it.

## Choosing keys

Steam's key press also reaches whatever X11 window has focus, which includes Proton games. Use
keys games ignore. F13–F24 are ideal if your Steam Input keyboard list has them. Otherwise
use combos like `ctrl+shift+F12`, or rarely used keys like `Pause`, `Scroll_Lock` or keypad keys.

## Example: save a replay clip

With [GPU Screen Recorder](https://git.dec05eba.com/gpu-screen-recorder/about/) running a replay
buffer (`-r`), `SIGUSR1` saves a clip. Bind it to a key, then put that key in a Steam Input
radial menu next to your other actions:

```toml
[keys]
F13 = { command = "pkill -SIGUSR1 -x gpu-screen-reco", cooldown = 1 }
```

(`gpu-screen-reco` is the process name truncated to 15 characters, as `pkill -x` matches it.)

## Limitations

- Needs XWayland running. Most setups start it at login. If it starts later or restarts, the
  daemon reconnects every 5 seconds.
- Only key presses are handled. Steam's mouse output is not.
- If Steam ever switches to a real virtual keyboard device or to libei, compositor shortcuts
  will work directly and you won't need this tool.

## License

MIT
