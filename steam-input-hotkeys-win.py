"""Run commands when Steam Input (or anything else using SendInput) presses a key. Windows.

A global low-level keyboard hook sees keys Steam Input injects into the game, whatever
window has focus. Same config format as the Linux daemon.

Usage:
  python steam-input-hotkeys-win.py [--config PATH]   run the daemon
  python steam-input-hotkeys-win.py --listen          print the name of every key that arrives
"""
import argparse
import ctypes
import os
import subprocess
import sys
import threading
import time
import tomllib
from ctypes import wintypes
from pathlib import Path

DEFAULT_CONFIG = Path(os.environ.get("APPDATA", Path.home())) / "steam-input-hotkeys" / "config.toml"
DEFAULT_COOLDOWN = 0.3

# name -> virtual-key code; F1-F24, A-Z and 0-9 are added below
KEYS = {
    "Backspace": 0x08, "Tab": 0x09, "Enter": 0x0D, "Pause": 0x13, "Escape": 0x1B, "Space": 0x20,
    "Page_Up": 0x21, "Page_Down": 0x22, "End": 0x23, "Home": 0x24,
    "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28,
    "Print": 0x2C, "Insert": 0x2D, "Delete": 0x2E, "Scroll_Lock": 0x91,
    "KP_0": 0x60, "KP_1": 0x61, "KP_2": 0x62, "KP_3": 0x63, "KP_4": 0x64,
    "KP_5": 0x65, "KP_6": 0x66, "KP_7": 0x67, "KP_8": 0x68, "KP_9": 0x69,
    "Volume_Mute": 0xAD, "Volume_Down": 0xAE, "Volume_Up": 0xAF,
    "Media_Next": 0xB0, "Media_Prev": 0xB1, "Media_Stop": 0xB2, "Media_Play_Pause": 0xB3,
}
KEYS.update({f"F{i}": 0x6F + i for i in range(1, 25)})
KEYS.update({c: ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"})
NAMES = {v: k for k, v in KEYS.items()}
# modifier -> virtual keys that count as held (generic, left, right)
MODIFIERS = {"ctrl": (0x11,), "shift": (0x10,), "alt": (0x12,), "super": (0x5B, 0x5C)}

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.CallNextHookEx.restype = LRESULT
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
WH_KEYBOARD_LL = 13
WM_KEYDOWN, WM_SYSKEYDOWN = 0x100, 0x104


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


def log(msg):
    print(msg, flush=True)


class Binding:
    def __init__(self, trigger, value):
        parts = [p.strip() for p in trigger.split("+")]
        if parts[-1] not in KEYS:
            raise ValueError(f"{trigger!r}: unknown key {parts[-1]!r} (run --listen to see names)")
        self.trigger = trigger
        self.vk = KEYS[parts[-1]]
        self.mods = []
        for m in parts[:-1]:
            if m.lower() not in MODIFIERS:
                raise ValueError(f"{trigger!r}: unknown modifier {m!r} (use {', '.join(MODIFIERS)})")
            self.mods.append(MODIFIERS[m.lower()])
        if isinstance(value, str):
            value = {"command": value}
        if not isinstance(value, dict) or not isinstance(value.get("command"), str):
            raise ValueError(f"{trigger!r}: expected a command string or a table with `command`")
        self.command = value["command"]
        self.cooldown = float(value.get("cooldown", DEFAULT_COOLDOWN))
        self.last = 0.0

    def matches(self, vk):
        return vk == self.vk and all(any(user32.GetAsyncKeyState(k) & 0x8000 for k in m) for m in self.mods)

    def fire(self):
        now = time.monotonic()
        if now - self.last < self.cooldown:
            return
        self.last = now
        log(f"{self.trigger}: {self.command}")
        # CREATE_NO_WINDOW: no console flash over the game
        subprocess.Popen(self.command, shell=True, stdin=subprocess.DEVNULL, creationflags=0x08000000)


def load_config(path):
    with open(path, "rb") as f:
        keys = tomllib.load(f).get("keys", {})
    if not isinstance(keys, dict):
        raise ValueError("`keys` must be a table")
    return [Binding(trigger, value) for trigger, value in keys.items()]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--listen", action="store_true", help="print key names instead of running commands")
    args = ap.parse_args()

    bindings = []
    if not args.listen:
        try:
            bindings = load_config(args.config)
        except (OSError, ValueError, tomllib.TOMLDecodeError) as e:
            sys.exit(f"steam-input-hotkeys: {args.config}: {e}")
        log(f"{len(bindings)} binding(s) from {args.config}")

    down = set()  # held keys, to ignore autorepeat

    def proc(code, wparam, lparam):
        if code >= 0:
            vk = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents.vkCode
            if wparam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                if vk not in down:
                    down.add(vk)
                    if args.listen:
                        log(NAMES.get(vk, hex(vk)))
                    else:
                        for b in bindings:
                            if b.matches(vk):
                                # off the hook thread: Windows drops hooks that stall
                                threading.Thread(target=b.fire, daemon=True).start()
            else:
                down.discard(vk)
        return user32.CallNextHookEx(None, code, wparam, lparam)

    cb = HOOKPROC(proc)  # keep a reference or the hook is garbage collected
    if not user32.SetWindowsHookExW(WH_KEYBOARD_LL, cb, kernel32.GetModuleHandleW(None), 0):
        sys.exit(f"SetWindowsHookEx failed: {ctypes.get_last_error()}")
    log("listening for keys")
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        pass


if __name__ == "__main__":
    main()
