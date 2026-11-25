# LocalWriter ✍︎

**Select text in any app → press a hotkey → a local AI rewrites it.**
Everything runs on your own computer through [Ollama](https://ollama.com). Nothing is sent to the cloud.

Works on **macOS**, **Windows** and **Linux**. The interface is in English or German.

<!-- TODO screenshot: ![Rewriting a sentence with a hotkey](docs/screenshots/demo.gif) -->

| | |
|---|---|
| ✏️ **AI writing tools** | Fix grammar, improve, shorten, change the tone, translate, summarize, explain code, draft replies… |
| ⚡ **Snippets** | Type `;br` and it becomes "Best regards,". Dates, clipboard and cursor placeholders work too. |
| 🔒 **Vault** | Paste passwords with a hotkey after Touch ID (Mac) or your vault password (Windows/Linux). |
| 🔍 **Compare files** | Side-by-side diff of two files (text, code, PDF, Word, RTF, HTML) plus an AI summary of the changes. |

---

## 1. Install Ollama and a model (all systems)

LocalWriter needs Ollama, which runs the AI model locally.

1. Download and install Ollama: **https://ollama.com/download**
2. Open a terminal (Windows: *PowerShell*) and download a model. Pick the row that matches your computer:

   | Your computer | Command | Download |
   |---|---|---|
   | 16 GB RAM or more (recommended) | `ollama pull qwen3.5:9b` | 7.6 GB |
   | 8 GB RAM | `ollama pull qwen3.5:4b` | ~3 GB |
   | Older or very low-end computer | `ollama pull qwen3.5:2b` | ~2 GB |

   Bigger models write better, smaller ones answer faster. You can switch any time.
3. LocalWriter uses `qwen3.5:9b` by default. If you downloaded a different one, pick it under **Settings → General → Default model**.

## 2. Install LocalWriter

Get the latest version from the **[Releases page](../../releases/latest)**.

<details open>
<summary><b>🍎 macOS</b> (13 Ventura or newer, Apple Silicon)</summary>

1. Download **`LocalWriter-macOS.zip`** and double-click it.
2. Drag **LocalWriter.app** into your **Applications** folder.
3. The first time, **right-click the app → Open → Open** (the app isn't notarized by Apple, so a normal double-click is blocked once).
4. Allow LocalWriter under **System Settings → Privacy & Security → Accessibility**, then quit and reopen it.
5. A ✍︎ appears in the menu bar. You're ready.

*Start at login: System Settings → General → Login Items → +.*
</details>

<details>
<summary><b>🪟 Windows</b> (10 / 11)</summary>

1. Download **`LocalWriter-Windows.exe`** and run it.
2. If Windows SmartScreen says *"Windows protected your PC"*, click **More info → Run anyway** (the app isn't code-signed).
3. A ✍ icon appears in the system tray (bottom right; it may be hidden behind the **^** arrow).
4. To start it with Windows: right-click the tray icon → **Settings… → Start with the system**.
</details>

<details>
<summary><b>🐧 Linux</b> (X11 session)</summary>

1. Download **`LocalWriter-Linux-x86_64.tar.gz`** and unpack it:
   ```sh
   tar xzf LocalWriter-Linux-x86_64.tar.gz
   cd LocalWriter-Linux && ./install.sh
   ```
2. Start **LocalWriter** from your app menu.
3. Recommended: install `xdotool` so results are pasted back into the right window:
   ```sh
   sudo apt install xdotool        # Debian/Ubuntu
   sudo dnf install xdotool        # Fedora
   ```

> **⚠️ Wayland:** Wayland doesn't let apps read global hotkeys or type into other windows. Choose **"Ubuntu on Xorg"** (or similar) on the login screen.
> **GNOME:** to see the tray icon, install the *AppIndicator and KStatusNotifierItem Support* extension.
</details>

## 3. Use it

1. **Select some text** in any app (email, browser, Word, an editor…).
2. **Press a hotkey:**

| Hotkey | What it does |
|---|---|
| <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>G</kbd> (Mac: ⌃⌥G) | Fix grammar & spelling |
| <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>I</kbd> (Mac: ⌃⌥I) | Improve writing |
| <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>S</kbd> (Mac: ⌃⌥S) | Summarize (shown in a window) |
| <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Space</kbd> (Mac: ⌃⌥Space) | **Picker**: a menu with every action, translate, custom instruction, snippets and vault |
| <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>V</kbd> (Mac: ⌃⌥V) | Vault picker |

3. The text is replaced, or a window opens where you can edit the result and choose **Copy**, **Insert before**, **Insert after** or **Replace**.

**Don't remember a hotkey?** Use the picker (<kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>Space</kbd>). Everything is in there.

<!-- TODO screenshot: ![The picker menu](docs/screenshots/picker.png) -->

## Customizing

Open **Settings** from the tray/menu-bar icon.

- **Shortcuts:** click a hotkey button and press a new combination. Add more ready-made actions (*Make professional*, *Shorten*, *Explain code*, *Translate to French*…) with one click, or write your own instruction.
- **Snippets:** abbreviation → text. Placeholders: `{date}` `{time}` `{isodate}` `{clipboard}` `{cursor}`.
- **Vault:** add an entry, give it a hotkey. Secrets are stored in the system keychain (macOS Keychain, Windows Credential Manager, GNOME Keyring/KWallet), **never** in the config file.
- **Features:** don't need the vault or file compare? Switch them off under **General → Features**.

<!-- TODO screenshot: ![Settings window](docs/screenshots/settings.png) -->

All settings are in one JSON file, the same format on every system:

| System | Config file |
|---|---|
| macOS / Linux | `~/.config/localwriter/config.json` |
| Windows | `%APPDATA%\LocalWriter\config.json` |

## Troubleshooting

| Problem | Fix |
|---|---|
| Nothing happens when I press a hotkey | **Mac:** Accessibility permission missing. Remove LocalWriter from *Privacy & Security → Accessibility*, add it again, restart the app. **Linux:** you're probably on Wayland (see above). **All:** another app may use the same hotkey; pick a different one in Settings → Shortcuts. |
| "Ollama not reachable" | Make sure Ollama is running (`ollama list` in a terminal should work). |
| Result is in the wrong language | Settings → General → **Output language**. *Same as the text* answers in the language of your selection. |
| The result went to the clipboard, not into my text | You switched windows while the AI was working. Just paste with <kbd>Ctrl</kbd>/<kbd>⌘</kbd>+<kbd>V</kbd>. |
| Slow | Use a smaller model (e.g. `qwen3.5:4b`). The first run after a while is slower because the model has to load. |

---

## Building from source

Don't want to run a downloaded binary? Build it yourself. Every release is built from this repository by
[GitHub Actions](.github/workflows/release.yml), and `SHA256SUMS.txt` in each release lets you check that the file you downloaded wasn't changed.

```sh
git clone https://github.com/PainteT/LocalWriter.git
cd LocalWriter
```

**macOS** (needs Xcode or the Command Line Tools: `xcode-select --install`)
```sh
cd macos
./build.sh install      # builds, copies to /Applications and launches
```

**Windows & Linux** (needs Python 3.10+)
```sh
cd crossplatform
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux: source .venv/bin/activate
pip install -r requirements.txt

python -m localwriter            # run directly from source, or…
pip install pyinstaller pillow
python build.py                  # …build a single file into crossplatform/dist/
```
Linux also needs `pip install secretstorage` for the vault, plus Qt's X11 libraries (`sudo apt install libxcb-cursor0`).

### Project layout

```
macos/          Native Swift/AppKit app (menu bar, Touch ID, Keychain)
crossplatform/  Python + Qt app for Windows and Linux (same features and config format)
.github/        Release workflow: builds all three on every version tag
```

### Making a release

```sh
git tag v1.0.0
git push origin v1.0.0
```
GitHub Actions builds macOS, Windows and Linux and attaches them to a new release, usually within about 10 minutes.

## Privacy

- Your text goes only to the Ollama server you configure (by default `localhost`, i.e. your own computer).
- No telemetry, no accounts, no network access except to Ollama.
- Vault secrets stay in your system's keychain.

## License

[MIT](LICENSE)
