"""LocalWriter for Windows & Linux: tray app. Global hotkeys rewrite the selected text via a local Ollama model."""
import os
import sys
import threading
import time
from datetime import datetime

from PySide6.QtCore import QMimeData, QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QIcon, QKeySequence, QPainter, QPalette, QPixmap, QShortcut
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QStyleFactory,
                               QSystemTrayIcon, QVBoxLayout)

from . import keys, ollama, vault
from . import platform_utils as plat
from .config import Action, Config, config_file
from .l10n import L, current as current_lang, set_language

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------- threading bridge ----------

class Bridge(QObject):
    sig = Signal(object)

    def __init__(self):
        super().__init__()
        self.sig.connect(self._run, Qt.QueuedConnection)

    @Slot(object)
    def _run(self, fn): fn()


_bridge: Bridge | None = None
_main_thread = threading.main_thread()


def post(fn):
    """Run fn on the GUI thread (async)."""
    _bridge.sig.emit(fn)


def on_main(fn):
    """Run fn on the GUI thread and return its result (call from worker threads)."""
    if threading.current_thread() is _main_thread:
        return fn()
    box, ev = {}, threading.Event()

    def run():
        try: box["v"] = fn()
        except Exception as e: box["e"] = e  # noqa: BLE001,E701
        ev.set()
    post(run); ev.wait()
    if "e" in box: raise box["e"]
    return box.get("v")


def bg(fn):
    threading.Thread(target=fn, daemon=True).start()


# ---------- clipboard (main thread only) ----------

def cb(): return QApplication.clipboard()


def snapshot():
    md = cb().mimeData()
    return {f: bytes(md.data(f)) for f in md.formats()} if md else {}


def restore(snap):
    md = QMimeData()
    for f, d in snap.items(): md.setData(f, d)
    cb().setMimeData(md)


def set_text(text, concealed=False):
    md = QMimeData(); md.setText(text)
    if concealed:   # keep secrets out of clipboard history / managers
        md.setData("ExcludeClipboardContentFromMonitorProcessing", b"\x00")
        md.setData("CanIncludeInClipboardHistory", b"\x00\x00\x00\x00")
        md.setData("CanUploadToCloudClipboard", b"\x00\x00\x00\x00")
        md.setData("x-kde-passwordManagerHint", b"secret")
    cb().setMimeData(md)


def notify(title, msg):
    if App.instance and App.instance.tray:
        App.instance.tray.showMessage(title, msg, QSystemTrayIcon.Information, 5000)
    else:
        print(title, msg, file=sys.stderr)


# ---------- snippets ----------

def resolve_snippet(s: str) -> tuple[str, int]:
    now = datetime.now()
    de = current_lang() == "de"
    t = (s.replace("{date}", now.strftime("%d.%m.%Y") if de else now.strftime("%b %d, %Y").replace(" 0", " "))
          .replace("{time}", now.strftime("%H:%M") if de else now.strftime("%I:%M %p").lstrip("0"))
          .replace("{isodate}", now.strftime("%Y-%m-%d")))
    if "{clipboard}" in t:
        t = t.replace("{clipboard}", on_main(lambda: cb().text()) or "")
    back = 0
    if "{cursor}" in t:
        i = t.index("{cursor}"); back = len(t) - i - len("{cursor}"); t = t[:i] + t[i + 8:]
    return t, back


class Expander:
    """Watches typing and expands abbreviations (runs on the listener thread)."""

    def __init__(self, app):
        self.app, self.buf, self.expanding = app, "", False

    def on_key(self, key, mods):
        cfg = self.app.cfg
        if not (cfg.featureSnippets and cfg.snippetsEnabled) or self.expanding: return
        if self.app.keyboard.ctrl_or_cmd_down(): self.buf = ""; return
        if key == keys.BACKSPACE: self.buf = self.buf[:-1]; return
        if key in keys.RESET_KEYS: self.buf = ""; return
        ch = keys.key_char(key)
        if ch is None: return
        if cfg.snippetTrigger == "delimiter" and (ch.isspace() or ch in ".,!?"):
            s = self.match(self.buf)
            self.buf = ""
            if s: self.expand(s, len(s.abbreviation) + 1, ch)
            return
        self.buf = (self.buf + ch)[-80:]
        if cfg.snippetTrigger != "delimiter":
            s = self.match(self.buf)
            if s: self.buf = ""; self.expand(s, len(s.abbreviation), "")

    def match(self, buf):
        best = None
        for s in self.app.cfg.snippets:
            a = s.abbreviation
            if not a or not buf.endswith(a): continue
            if a[0].isalnum():
                before = buf[:-len(a)][-1:] if len(buf) > len(a) else ""
                if before and before.isalnum(): continue
            if not best or len(a) > len(best.abbreviation): best = s
        return best

    def expand(self, s, delete, suffix):
        if plat.is_own_window(plat.foreground_window()): return
        self.expanding = True

        def run():
            try:
                time.sleep(0.03)
                keys.tap(keys.BACKSPACE, delete)
                text, back = resolve_snippet(s.text)
                self.app.paste_text(text + suffix, cursor_back=(back + len(suffix)) if "{cursor}" in s.text else 0)
                time.sleep(0.3)
            finally:
                self.expanding = False
        bg(run)


# ---------- preview window ----------

class PreviewWindow(QDialog):
    def __init__(self, title, original, cfg, primary, on_deliver, on_retry):
        super().__init__(None)
        self.setWindowTitle(title)
        self.setAttribute(Qt.WA_DeleteOnClose)
        if cfg.previewFloating: self.setWindowFlag(Qt.WindowStaysOnTopHint)
        self.resize(680, 440)
        self.on_deliver, self.on_retry = on_deliver, on_retry
        lay = QVBoxLayout(self)
        if cfg.showOriginal:
            o = QLabel(L("Original: ") + original[:300] + ("…" if len(original) > 300 else ""))
            o.setWordWrap(True); o.setStyleSheet("color: gray; font-size: 11px"); lay.addWidget(o)
        self.edit = QPlainTextEdit(L("Generating…")); self.edit.setReadOnly(True)
        f = self.edit.font(); f.setPointSizeF(cfg.previewFontSize); self.edit.setFont(f)
        lay.addWidget(self.edit, 1)
        row = QHBoxLayout()
        retry = QPushButton("↻ " + L("Retry")); retry.clicked.connect(self.retry)
        close = QPushButton(L("Close")); close.clicked.connect(self.close)
        row.addWidget(retry); row.addWidget(close); row.addStretch()
        btns = {}
        for p, label, tip in [("copy", L("Copy"), L("Copy the result and close")),
                              ("before", L("Insert before"), L("Keep the selection and insert the result above it")),
                              ("after", L("Insert after"), L("Keep the selection and insert the result below it (e.g. a reply)")),
                              ("replace", L("Replace"), L("Replace the selection with the result"))]:
            b = QPushButton(label); b.setToolTip(tip); b.clicked.connect(lambda _=False, p=p: self.finish(p))
            row.addWidget(b); btns[p] = b
        btns[primary].setDefault(True)
        lay.addLayout(row)
        hint = QLabel(L("Edit freely · Ctrl+Enter %s · Ctrl+R retry · Esc close") % btns[primary].text().lower())
        hint.setStyleSheet("color: gray; font-size: 11px"); lay.addWidget(hint)
        QShortcut(QKeySequence("Ctrl+Return"), self, lambda: self.finish(primary))
        QShortcut(QKeySequence("Ctrl+R"), self, self.retry)

    def set_result(self, s):
        self.edit.setPlainText(s); self.edit.setReadOnly(False); self.edit.setFocus()

    def retry(self):
        self.edit.setReadOnly(True); self.edit.setPlainText(L("Generating…")); self.on_retry()

    def finish(self, p):
        s = self.edit.toPlainText(); self.close(); self.on_deliver(s, p)

    def show_front(self):
        self.show(); self.raise_(); self.activateWindow()


# ---------- app ----------

def make_icon() -> QIcon:
    p = os.path.join(HERE, "icon.png")
    if os.path.exists(p): return QIcon(p)
    pm = QPixmap(64, 64); pm.fill(Qt.transparent)
    qp = QPainter(pm); qp.setFont(QFont("", 40)); qp.setPen(QColor("#888")); qp.drawText(pm.rect(), Qt.AlignCenter, "✍"); qp.end()
    return QIcon(pm)


class App:
    instance = None

    def __init__(self, qapp):
        App.instance = self
        self.qapp = qapp
        self.cfg = Config.load()
        set_language(self.cfg.uiLanguage)
        self.models: list[str] = []
        self.busy = False
        self.previews = []
        self.vault_lock = vault.Lock()
        self.settings = None
        self.tray = QSystemTrayIcon(make_icon())
        self.tray.setToolTip("LocalWriter")
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self.build_menu)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(lambda r: self.open_settings() if r == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()
        self.keyboard = keys.Keyboard(post)
        self.expander = Expander(self)
        self.keyboard.on_char = self.expander.on_key
        self.apply_appearance()
        self.register_hotkeys()
        bg(self.refresh_models)
        if plat.is_wayland():
            notify("LocalWriter", L("Global hotkeys and typing don't work under Wayland. Log in with an X11 (Xorg) session."))
        else:
            notify("LocalWriter", L("LocalWriter is running in the system tray."))

    # --- config ---
    def save(self, hotkeys=False):
        self.cfg.save()
        if hotkeys: self.register_hotkeys()

    def reload(self):
        self.cfg = Config.load(); set_language(self.cfg.uiLanguage); self.register_hotkeys(); self.apply_appearance()

    def refresh_models(self):
        self.models = ollama.models(self.cfg)

    def apply_appearance(self):
        self.qapp.setStyle(QStyleFactory.create("Fusion"))
        mode = self.cfg.appearance
        if mode == "system":
            self.qapp.setPalette(self.qapp.style().standardPalette())
            if hasattr(self.qapp.styleHints(), "setColorScheme"):
                self.qapp.styleHints().setColorScheme(Qt.ColorScheme.Unknown)
            return
        if hasattr(self.qapp.styleHints(), "setColorScheme"):
            self.qapp.styleHints().setColorScheme(Qt.ColorScheme.Dark if mode == "dark" else Qt.ColorScheme.Light)
        if mode == "dark":
            p = QPalette()
            for role, c in [(QPalette.Window, "#2b2b2b"), (QPalette.WindowText, "#e6e6e6"), (QPalette.Base, "#1e1e1e"),
                            (QPalette.AlternateBase, "#2f2f2f"), (QPalette.Text, "#e6e6e6"), (QPalette.Button, "#3a3a3a"),
                            (QPalette.ButtonText, "#e6e6e6"), (QPalette.Highlight, "#3d6fd6"), (QPalette.HighlightedText, "#ffffff"),
                            (QPalette.ToolTipBase, "#2b2b2b"), (QPalette.ToolTipText, "#e6e6e6"), (QPalette.PlaceholderText, "#8a8a8a")]:
                p.setColor(role, QColor(c))
            self.qapp.setPalette(p)
        else:
            self.qapp.setPalette(self.qapp.style().standardPalette())

    def register_hotkeys(self):
        c = self.cfg
        m = [(c.pickerHotkey, self.show_picker)]
        if c.featureAI:
            m += [(a.hotkey, lambda a=a: self.trigger(a)) for a in c.actions if a.hotkey]
        if c.featureSnippets:
            m += [(s.hotkey, lambda s=s: bg(lambda: self.insert_snippet(s))) for s in c.snippets if s.hotkey]
        if c.featureVault:
            m += [(v.hotkey, lambda v=v: self.vault_insert(v.id)) for v in c.vault if v.hotkey]
            m.append((c.vaultHotkey, self.show_vault_picker))
        self.failed_hotkeys = self.keyboard.set_hotkeys(m)
        if self.failed_hotkeys:
            notify("LocalWriter", L("Some hotkeys could not be registered: ") + ", ".join(self.failed_hotkeys))

    # --- paste / copy (worker thread) ---
    def paste_text(self, text, concealed=False, cursor_back=0):
        snap = on_main(snapshot)
        on_main(lambda: set_text(text, concealed))
        time.sleep(0.08)
        keys.paste()
        if cursor_back: keys.tap(keys.LEFT, min(cursor_back, 2000))
        time.sleep(0.5)
        on_main(lambda: restore(snap))

    def copy_selection(self) -> str | None:
        self.keyboard.wait_modifiers_released()
        snap = on_main(snapshot)
        on_main(lambda: cb().clear())
        keys.copy()
        text = None
        for _ in range(40):
            time.sleep(0.02)
            text = on_main(lambda: cb().text())
            if text: break
        on_main(lambda: restore(snap))
        return text

    def deliver(self, out, placement, kind, target):
        if placement == "copy":
            on_main(lambda: set_text(out)); return
        plat.focus_window(target); time.sleep(0.12)
        if placement == "replace":
            self.paste_text(out); return
        sep = "" if kind == "continue" else "\n\n"
        keys.tap(keys.RIGHT if placement == "after" else keys.LEFT); time.sleep(0.05)
        self.paste_text(sep + out if placement == "after" else out + sep)

    # --- core flow ---
    def trigger(self, action: Action, override_mode=None):
        if self.busy: QApplication.beep(); return
        target = plat.foreground_window()
        if plat.is_own_window(target): target = None

        def run():
            text = self.copy_selection()
            if not text or not text.strip():
                post(QApplication.beep); return
            kind = action.kind_value
            mode = override_mode or action.mode or ("preview" if kind == "analyze" else self.cfg.mode)
            if kind == "continue" and mode == "replace": mode = "after"
            model = action.model or self.cfg.model
            if mode == "preview":
                post(lambda: self.run_preview(action, text, model, target))
            else:
                self.run_direct(action, text, model, mode, target)
        bg(run)

    def run_direct(self, a, text, model, placement, target):
        self.set_busy(True)
        try:
            out = ollama.run(text, a, model, self.cfg)
        except Exception as e:  # noqa: BLE001
            post(lambda: notify(L("LocalWriter error"), str(e))); return
        finally:
            self.set_busy(False)
        if placement == "copy":
            self.deliver(out, "copy", a.kind_value, target); post(lambda: notify("LocalWriter", L("Result copied to clipboard.")))
        elif target is None or plat.foreground_window() == target:
            self.deliver(out, placement, a.kind_value, target)
        else:
            self.deliver(out, "copy", a.kind_value, target)
            post(lambda: notify("LocalWriter", L("You switched apps — result copied to clipboard.")))

    def set_busy(self, b):
        self.busy = b
        post(lambda: self.tray.setToolTip("LocalWriter" + (" …" if b else "")))

    def run_preview(self, a, text, model, target):
        kind = a.kind_value
        primary = "copy" if kind == "analyze" else "after" if kind == "continue" else "replace"

        def go():
            def work():
                try: out = ollama.run(text, a, model, self.cfg)
                except Exception as e: out = "⚠️ " + str(e)  # noqa: BLE001
                post(lambda: w.set_result(out) if w in self.previews else None)
            bg(work)
        w = PreviewWindow(f"{a.name} — {model}", text, self.cfg, primary,
                          lambda out, p: bg(lambda: self.deliver(out, p, kind, target)), go)
        self.previews.append(w)
        w.destroyed.connect(lambda *_: self.previews.remove(w) if w in self.previews else None)
        w.show_front(); go()

    # --- menus ---
    def build_menu(self):
        bg(self.refresh_models)
        self.fill_menu(self.menu, None, tray=True)

    def fill_menu(self, m: QMenu, target, tray=False):
        m.clear()
        c = self.cfg

        def act(menu, title, fn, hotkey=None, checked=None):
            a = QAction(title + (f"\t{keys.display(hotkey)}" if hotkey else ""), menu)
            if checked is not None: a.setCheckable(True); a.setChecked(checked)
            a.triggered.connect(fn); menu.addAction(a); return a

        def run_later(fn):   # let the menu close and the previous window regain focus first
            return lambda: (plat.focus_window(target), QTimer.singleShot(200, fn))

        if c.featureAI:
            for title, group in [(L("Rewrite"), [a for a in c.actions if a.kind_value != "analyze"]),
                                 (L("Analyze"), [a for a in c.actions if a.kind_value == "analyze"])]:
                if not group: continue
                if not m.isEmpty(): m.addSeparator()
                m.addSection(title)
                for a in group: act(m, a.name, run_later(lambda a=a: self.trigger(a)), a.hotkey)
            m.addSeparator()
            tm = m.addMenu(L("Translate to"))
            for l in c.languages: act(tm, l, run_later(lambda l=l: self.trigger(Action.translate(l))))
            tm.addSeparator()
            act(tm, L("Other language…"), lambda: self.translate_other(target))
            act(m, L("Custom instruction…"), lambda: self.custom_instruction(target))
        if tray:
            act(m, L("Show picker at mouse"), lambda: QTimer.singleShot(200, self.show_picker), c.pickerHotkey)
        if c.featureSnippets or c.featureVault: m.addSeparator()
        if c.featureSnippets:
            sm = m.addMenu(L("Snippets"))
            for s in c.snippets:
                act(sm, s.title, lambda s=s: (plat.focus_window(target), bg(lambda: (time.sleep(0.2), self.insert_snippet(s)))), s.hotkey)
            if c.snippets: sm.addSeparator()
            act(sm, L("Expand abbreviations while typing"), self.toggle_snippets, checked=c.snippetsEnabled)
            act(sm, L("Edit snippets…"), lambda: self.open_settings("snippets"))
        if c.featureVault:
            vm = m.addMenu(L("Vault"))
            for v in c.vault: act(vm, v.name, lambda v=v: self.vault_insert(v.id, target), v.hotkey)
            if c.vault: vm.addSeparator()
            act(vm, L("Edit vault…"), lambda: self.open_settings("vault"))
        if c.featureAI:
            m.addSeparator(); m.addSection(L("Options"))
            mm = m.addMenu(L("Mode"))
            for k, lab in [("replace", L("Replace directly")), ("preview", L("Show editable preview"))]:
                act(mm, lab, lambda k=k: self.set_cfg("mode", k), checked=c.mode == k)
            lm = m.addMenu(L("Output language"))
            for l in ["auto"] + c.languages:
                act(lm, L("Same as the text") if l == "auto" else l, lambda l=l: self.set_cfg("language", l), checked=c.language == l)
            if tray:
                mo = m.addMenu(L("Model") + f"  ({c.model})")
                for name in sorted(set(self.models + [c.model])):
                    act(mo, name, lambda n=name: self.set_cfg("model", n), checked=c.model == name)
        if tray:
            m.addSeparator()
            act(m, L("Settings…"), lambda: self.open_settings())
            more = m.addMenu(L("More"))
            if c.featureCompare: act(more, L("Compare files…"), lambda: self.open_settings("compare"))
            act(more, L("Edit config file…"), lambda: plat.open_path(config_file()))
            act(more, L("Reload config"), lambda: (self.reload(), notify("LocalWriter", L("Config reloaded"))))
            if c.featureVault: act(more, L("Lock vault now"), lambda: (self.vault_lock.lock(), notify(L("Vault"), L("Vault locked."))))
            act(m, L("Quit LocalWriter"), self.qapp.quit)

    def set_cfg(self, k, v):
        setattr(self.cfg, k, v); self.save()
        if self.settings: self.settings.refresh()

    def toggle_snippets(self):
        self.set_cfg("snippetsEnabled", not self.cfg.snippetsEnabled)

    def show_picker(self):
        target = plat.foreground_window()
        if plat.is_own_window(target): target = None
        m = QMenu()
        self.fill_menu(m, target)
        if m.isEmpty(): self.open_settings(); return
        self._picker = m
        m.popup(QCursor.pos()); m.activateWindow()

    def show_vault_picker(self):
        target = plat.foreground_window()
        if not self.cfg.vault: self.open_settings("vault"); return
        if len(self.cfg.vault) == 1: self.vault_insert(self.cfg.vault[0].id, target); return
        m = QMenu(); m.addSection(L("Vault"))
        for v in self.cfg.vault:
            a = m.addAction("🔑 " + v.name); a.triggered.connect(lambda _=False, v=v: self.vault_insert(v.id, target))
        self._picker = m
        m.popup(QCursor.pos()); m.activateWindow()

    def _ask_text(self, title, label, placeholder, extra=None):
        d = QDialog(); d.setWindowTitle(title); d.setWindowFlag(Qt.WindowStaysOnTopHint)
        lay = QVBoxLayout(d); lay.addWidget(QLabel(label))
        f = QLineEdit(); f.setPlaceholderText(placeholder); f.setMinimumWidth(360); lay.addWidget(f)
        if extra: lay.addWidget(extra)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(d.accept); bb.rejected.connect(d.reject); lay.addWidget(bb)
        d.show(); d.raise_(); d.activateWindow(); f.setFocus()
        ok = d.exec() == QDialog.Accepted
        return f.text().strip() if ok else None

    def translate_other(self, target):
        l = self._ask_text(L("Translate to"), L("Translate to"), L("e.g. Swedish, Greek, Swiss German"))
        plat.focus_window(target)
        if l: QTimer.singleShot(250, lambda: self.trigger(Action.translate(l)))

    def custom_instruction(self, target):
        kind = QComboBox(); kind.addItems([L("Rewrite selection"), L("Show result in window")])
        t = self._ask_text(L("Custom instruction"), L("What should be done with the selected text?"),
                           L("e.g. turn into bullet points"), kind)
        plat.focus_window(target)
        if t:
            a = Action(L("Custom"), prompt=t, kind="analyze" if kind.currentIndex() == 1 else None)
            QTimer.singleShot(250, lambda: self.trigger(a))

    # --- snippets & vault ---
    def insert_snippet(self, s):
        self.keyboard.wait_modifiers_released()
        text, back = resolve_snippet(s.text)
        self.paste_text(text, cursor_back=back)

    def authenticate(self, reason) -> bool:
        """Main thread. Asks for the vault password (dialog closes after vaultAuthTimeout seconds)."""
        if self.vault_lock.is_unlocked: return True
        if not self.cfg.vaultPasswordHash:
            if not self.set_vault_password(): return False
            self.vault_lock.unlock_for(self.cfg.vaultUnlockFor); return True
        d = QInputDialog(); d.setWindowTitle(L("Vault")); d.setWindowFlag(Qt.WindowStaysOnTopHint)
        d.setLabelText(L("Enter the vault password to %s") % reason); d.setTextEchoMode(QLineEdit.Password)
        if self.cfg.vaultAuthTimeout > 0:
            QTimer.singleShot(int(self.cfg.vaultAuthTimeout * 1000), d.reject)
        d.show(); d.raise_(); d.activateWindow()
        if d.exec() != QDialog.Accepted: return False
        if not vault.check_password(d.textValue(), self.cfg.vaultPasswordHash):
            QMessageBox.warning(None, L("Vault"), L("Wrong password.")); return False
        self.vault_lock.unlock_for(self.cfg.vaultUnlockFor)
        return True

    def set_vault_password(self) -> bool:
        a, ok = QInputDialog.getText(None, L("Set a vault password"), L("Vault password"), QLineEdit.Password)
        if not ok or not a: return False
        b, ok = QInputDialog.getText(None, L("Set a vault password"), L("Repeat password"), QLineEdit.Password)
        if not ok: return False
        if a != b: QMessageBox.warning(None, L("Vault"), L("Passwords don't match.")); return False
        self.cfg.vaultPasswordHash = vault.hash_password(a); self.save(); return True

    def vault_insert(self, entry_id, target=None):
        target = target or plat.foreground_window()
        if plat.is_own_window(target): target = None
        entry = next((v for v in self.cfg.vault if v.id == entry_id), None)
        if not entry: return
        self.keyboard.wait_modifiers_released(0.5)
        if not self.authenticate(L("insert “%@”").replace("%@", entry.name)):
            plat.focus_window(target); return
        secret = vault.load().get(entry_id)
        if not secret:
            notify(L("Vault"), L("This entry has no value yet.")); return

        def run():
            plat.focus_window(target); time.sleep(0.25)
            if self.cfg.vaultMethod == "type": keys.type_text(secret)
            else: self.paste_text(secret, concealed=True)
        bg(run)

    def open_settings(self, tab=None):
        from .settings import SettingsWindow
        if not self.settings:
            self.settings = SettingsWindow(self)
            self.settings.destroyed.connect(lambda *_: setattr(self, "settings", None))
        if tab: self.settings.show_tab(tab)
        self.settings.show(); self.settings.raise_(); self.settings.activateWindow()


def main():
    global _bridge
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("local.localwriter")
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setApplicationName("LocalWriter")
    qapp.setWindowIcon(make_icon())
    _bridge = Bridge()
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("No system tray found. On GNOME install the 'AppIndicator and KStatusNotifierItem Support' extension.", file=sys.stderr)
    App(qapp)
    if "--settings" in sys.argv: App.instance.open_settings()
    sys.exit(qapp.exec())
