"""Keyboard: one global listener (pynput) handles hotkeys, modifier tracking and snippet typing;
a Controller synthesizes Ctrl+C / Ctrl+V / typing. Callbacks are handed to the Qt main thread via `post`."""
import threading
import time

from pynput import keyboard
from pynput.keyboard import Key, KeyCode

_kb = keyboard.Controller()
_injecting = 0                 # >0 while we synthesize keys: the listener ignores those events
_lock = threading.Lock()

MODS = {Key.ctrl, Key.ctrl_l, Key.ctrl_r, Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr,
        Key.shift, Key.shift_l, Key.shift_r, Key.cmd, Key.cmd_l, Key.cmd_r}

_NAMED = {"space": "<space>", "return": "<enter>", "enter": "<enter>", "tab": "<tab>", "escape": "<esc>",
          "ctrl": "<ctrl>", "control": "<ctrl>", "alt": "<alt>", "opt": "<alt>", "option": "<alt>",
          "shift": "<shift>", "cmd": "<cmd>", "command": "<cmd>", "win": "<cmd>", "super": "<cmd>"}


def to_pynput(combo: str) -> str | None:
    """'ctrl+alt+g' -> '<ctrl>+<alt>+g'. None if invalid."""
    parts = [p.strip() for p in combo.lower().split("+") if p.strip()]
    out, has_key = [], False
    for p in parts:
        if p in _NAMED:
            out.append(_NAMED[p]); has_key |= p in ("space", "return", "enter", "tab", "escape")
        elif len(p) == 1 or (p.startswith("f") and p[1:].isdigit()):
            out.append(p if len(p) == 1 else f"<{p}>"); has_key = True
        else:
            return None
    return "+".join(out) if has_key else None


def display(combo: str | None) -> str:
    if not combo: return ""
    names = {"ctrl": "Ctrl", "control": "Ctrl", "alt": "Alt", "opt": "Alt", "option": "Alt", "shift": "Shift",
             "cmd": "Win", "command": "Win", "space": "Space", "return": "Enter", "tab": "Tab", "escape": "Esc"}
    return "+".join(names.get(p, p.upper()) for p in combo.lower().split("+"))


class Keyboard:
    """Global listener. `post(fn)` must run fn on the GUI thread."""

    def __init__(self, post):
        self.post = post
        self.held: set = set()
        self.hotkeys: list[tuple[keyboard.HotKey, object]] = []
        self.on_char = None          # snippet expander hook: fn(key) on every non-injected key press
        self.paused = False          # while recording a hotkey in Settings
        self.listener = keyboard.Listener(on_press=self._press, on_release=self._release)
        self.listener.daemon = True
        self.listener.start()

    def set_hotkeys(self, mapping: list[tuple[str, object]]) -> list[str]:
        """mapping: [(combo, callback)]. Returns combos that are invalid."""
        failed, hks = [], []
        for combo, cb in mapping:
            p = to_pynput(combo) if combo else None
            if not p:
                if combo: failed.append(combo)
                continue
            try:
                hks.append((keyboard.HotKey(keyboard.HotKey.parse(p), lambda cb=cb: self.post(cb)), cb))
            except ValueError:
                failed.append(combo)
        self.hotkeys = hks
        return failed

    def _canon(self, key):
        try:
            return self.listener.canonical(key)
        except Exception:  # noqa: BLE001
            return key

    def _press(self, key):
        if _injecting: return
        self.held.add(key)
        if self.paused: return
        k = self._canon(key)
        for hk, _ in self.hotkeys:
            hk.press(k)
        if self.on_char:
            self.on_char(key, self.modifiers_down())

    def _release(self, key):
        if _injecting: return
        self.held.discard(key)
        k = self._canon(key)
        for hk, _ in self.hotkeys:
            hk.release(k)

    def modifiers_down(self) -> bool:
        return bool(self.held & MODS)

    def ctrl_or_cmd_down(self) -> bool:
        """Ctrl/Win held (a shortcut, not typing). AltGr (= Ctrl+Alt on Windows) still counts as typing."""
        if self.held & {Key.alt_gr, Key.alt_r}:
            return False
        return bool(self.held & {Key.ctrl, Key.ctrl_l, Key.ctrl_r, Key.cmd, Key.cmd_l, Key.cmd_r})

    def wait_modifiers_released(self, timeout=1.0):
        end = time.time() + timeout
        while self.modifiers_down() and time.time() < end:
            time.sleep(0.02)
        self.held.clear()   # a release we missed must not block forever


class _Injecting:
    def __enter__(self):
        global _injecting
        with _lock: _injecting += 1

    def __exit__(self, *a):
        global _injecting
        time.sleep(0.03)
        with _lock: _injecting -= 1


def _release_modifiers():
    for m in (Key.ctrl, Key.alt, Key.shift, Key.cmd):
        try: _kb.release(m)
        except Exception: pass  # noqa: BLE001,E701


def press_combo(*keys):
    with _Injecting():
        _release_modifiers()
        for k in keys: _kb.press(k)
        for k in reversed(keys): _kb.release(k)


def copy():  press_combo(Key.ctrl, "c")
def paste(): press_combo(Key.ctrl, "v")


def tap(key, times=1):
    with _Injecting():
        for _ in range(times):
            _kb.press(key); _kb.release(key)


def type_text(s: str):
    with _Injecting():
        _release_modifiers()
        for ch in s:
            _kb.type(ch); time.sleep(0.004)


LEFT, RIGHT, BACKSPACE = Key.left, Key.right, Key.backspace
RESET_KEYS = {Key.enter, Key.tab, Key.esc, Key.delete, Key.left, Key.right, Key.up, Key.down,
              Key.home, Key.end, Key.page_up, Key.page_down}


def key_char(key) -> str | None:
    if isinstance(key, KeyCode) and key.char and key.char.isprintable():
        return key.char
    if key == Key.space:
        return " "
    return None
