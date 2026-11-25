"""Builds a standalone LocalWriter for the current OS into crossplatform/dist/.
Usage:  python build.py            (needs: pip install -r requirements.txt pyinstaller pillow)"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sep = ";" if sys.platform == "win32" else ":"
args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--name", "LocalWriter",
        "--windowed", "--onefile",
        "--icon", os.path.join(HERE, "localwriter", "icon.png"),
        "--add-data", f"{os.path.join(HERE, 'localwriter', 'de.json')}{sep}localwriter",
        "--add-data", f"{os.path.join(HERE, 'localwriter', 'icon.png')}{sep}localwriter",
        "--collect-data", "langdetect",
        "--hidden-import", "keyring.backends",
        os.path.join(HERE, "run.py")]
if sys.platform.startswith("linux"):
    args += ["--hidden-import", "pynput.keyboard._xorg", "--hidden-import", "pynput.mouse._xorg",
             "--collect-submodules", "keyring.backends", "--hidden-import", "secretstorage"]
elif sys.platform == "win32":
    args += ["--hidden-import", "pynput.keyboard._win32", "--hidden-import", "pynput.mouse._win32",
             "--hidden-import", "keyring.backends.Windows"]
subprocess.check_call(args, cwd=HERE)
print("Built", os.path.join(HERE, "dist"))
