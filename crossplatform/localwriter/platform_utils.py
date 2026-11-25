"""OS-specific bits: remembering/refocusing the window the user typed in, autostart, opening files."""
import os
import shutil
import subprocess
import sys

IS_WIN = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")


def is_wayland() -> bool:
    return IS_LINUX and (os.environ.get("XDG_SESSION_TYPE") == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY")))


if IS_WIN:
    import ctypes
    from ctypes import wintypes
    _user32 = ctypes.windll.user32

    def foreground_window():
        return _user32.GetForegroundWindow()

    def window_pid(hwnd) -> int:
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def focus_window(hwnd):
        if not hwnd:
            return
        # Windows refuses SetForegroundWindow from background processes unless we briefly attach to the
        # foreground thread's input queue.
        fg = _user32.GetForegroundWindow()
        cur = ctypes.windll.kernel32.GetCurrentThreadId()
        fg_thread = _user32.GetWindowThreadProcessId(fg, None)
        _user32.AttachThreadInput(fg_thread, cur, True)
        _user32.SetForegroundWindow(hwnd)
        _user32.AttachThreadInput(fg_thread, cur, False)

else:
    _xdotool = shutil.which("xdotool")

    def foreground_window():
        if not _xdotool or is_wayland():
            return None
        try:
            return subprocess.run([_xdotool, "getactivewindow"], capture_output=True, text=True, timeout=1).stdout.strip() or None
        except Exception:  # noqa: BLE001
            return None

    def window_pid(win) -> int:
        if not win or not _xdotool:
            return 0
        try:
            return int(subprocess.run([_xdotool, "getwindowpid", win], capture_output=True, text=True, timeout=1).stdout.strip() or 0)
        except Exception:  # noqa: BLE001
            return 0

    def focus_window(win):
        if win and _xdotool:
            subprocess.run([_xdotool, "windowactivate", "--sync", win], capture_output=True, timeout=2)


def is_own_window(win) -> bool:
    return bool(win) and window_pid(win) == os.getpid()


def open_path(path: str):
    if IS_WIN:
        os.startfile(path)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", path])


# ---- autostart ----

def _exe_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" -m localwriter'


if IS_WIN:
    import winreg
    _RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def autostart_enabled() -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN) as k:
                winreg.QueryValueEx(k, "LocalWriter")
                return True
        except OSError:
            return False

    def set_autostart(on: bool):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, "LocalWriter", 0, winreg.REG_SZ, _exe_command())
            else:
                try: winreg.DeleteValue(k, "LocalWriter")
                except OSError: pass
else:
    _DESKTOP = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "autostart", "localwriter.desktop")

    def autostart_enabled() -> bool:
        return os.path.exists(_DESKTOP)

    def set_autostart(on: bool):
        if on:
            os.makedirs(os.path.dirname(_DESKTOP), exist_ok=True)
            exe = os.environ.get("APPIMAGE") or _exe_command()
            with open(_DESKTOP, "w") as f:
                f.write(f"[Desktop Entry]\nType=Application\nName=LocalWriter\nExec={exe}\nX-GNOME-Autostart-enabled=true\n")
        elif os.path.exists(_DESKTOP):
            os.remove(_DESKTOP)
