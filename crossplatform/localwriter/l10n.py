"""English strings are the keys; de.json holds the German translations (shared with the macOS app's table)."""
import json
import os

_current = "en"
with open(os.path.join(os.path.dirname(__file__), "de.json"), encoding="utf-8") as f:
    _german: dict[str, str] = json.load(f)

# Strings only the Windows/Linux version uses
_german.update({
    "Vault password": "Tresor-Passwort",
    "Set a vault password": "Tresor-Passwort festlegen",
    "Change vault password…": "Tresor-Passwort ändern…",
    "Wrong password.": "Falsches Passwort.",
    "Passwords don't match.": "Passwörter stimmen nicht überein.",
    "Repeat password": "Passwort wiederholen",
    "Enter the vault password to %s": "Tresor-Passwort eingeben, um %s",
    "Secrets are stored in your system keyring (Windows Credential Manager / Secret Service), never in the config file. Every use asks for your vault password.":
        "Geheimnisse liegen im System-Schlüsselbund (Windows-Anmeldeinformationsverwaltung / Secret Service), nie in der Konfigurationsdatei. Jede Verwendung fragt nach dem Tresor-Passwort.",
    "Passwords protected by your vault password": "Passwörter, geschützt durch das Tresor-Passwort",
    "Global hotkeys and typing don't work under Wayland. Log in with an X11 (Xorg) session.":
        "Globale Tastenkürzel und Tippen funktionieren unter Wayland nicht. Bitte mit einer X11-(Xorg-)Sitzung anmelden.",
    "Start with the system": "Mit dem System starten",
    "LocalWriter is running in the system tray.": "LocalWriter läuft im Infobereich der Taskleiste.",
    "Edit freely · Ctrl+Enter %s · Ctrl+R retry · Esc close": "Frei bearbeitbar · Strg+Enter %s · Strg+R neu erzeugen · Esc schließen",
    "Choose file": "Datei wählen",
    "No keyring available. Install gnome-keyring or KWallet.": "Kein Schlüsselbund verfügbar. Bitte gnome-keyring oder KWallet installieren.",
})


def set_language(lang: str):
    global _current
    _current = lang


def current() -> str:
    return _current


def L(s: str) -> str:
    return _german.get(s, s) if _current == "de" else s
