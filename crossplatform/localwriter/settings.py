"""Settings window: General, Appearance, Shortcuts, Snippets, Vault, Compare."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QSlider, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit,
                               QVBoxLayout, QWidget)

from . import diff, keys, ollama, vault
from . import platform_utils as plat
from .config import Action, Snippet, VaultEntry, config_file, presets
from .l10n import L, set_language


def _bg(fn):
    from .app import bg
    bg(fn)


def _post(fn):
    from .app import post
    post(fn)


class HotkeyButton(QPushButton):
    """Click, then press a combination. Esc cancels, Backspace/Delete removes."""

    def __init__(self, app, value, on_change, allow_clear=True):
        super().__init__()
        self.app, self.value, self.on_change, self.allow_clear = app, value, on_change, allow_clear
        self.recording = False
        self.setToolTip(L("Click and press a key combination. Esc cancels, Delete removes it."))
        self.clicked.connect(self.start)
        self.setFocusPolicy(Qt.StrongFocus)
        self.update_text()

    def update_text(self):
        dup = self.value and self.app.cfg.all_hotkeys().count(self.value.lower()) > 1
        self.setText(L("Press keys…") if self.recording else (keys.display(self.value) or L("No hotkey")))
        self.setStyleSheet("color: #d33" if dup and not self.recording else "")

    def start(self):
        self.recording = True; self.app.keyboard.paused = True; self.grabKeyboard(); self.update_text()

    def stop(self):
        self.recording = False; self.app.keyboard.paused = False; self.releaseKeyboard(); self.update_text()

    def focusOutEvent(self, e):
        if self.recording: self.stop()
        super().focusOutEvent(e)

    def keyPressEvent(self, e):
        if not self.recording: return super().keyPressEvent(e)
        k = e.key()
        if k == Qt.Key_Escape: self.stop(); return
        if k in (Qt.Key_Backspace, Qt.Key_Delete):
            if self.allow_clear: self.set(None)
            self.stop(); return
        if k in (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta, Qt.Key_AltGr): return
        mods = e.modifiers()
        parts = []
        if mods & Qt.ControlModifier: parts.append("ctrl")
        if mods & Qt.AltModifier: parts.append("alt")
        if mods & Qt.ShiftModifier: parts.append("shift")
        if mods & Qt.MetaModifier: parts.append("cmd")
        names = {Qt.Key_Space: "space", Qt.Key_Return: "return", Qt.Key_Enter: "return", Qt.Key_Tab: "tab"}
        if k in names: key = names[k]
        elif Qt.Key_F1 <= k <= Qt.Key_F12: key = f"f{k - Qt.Key_F1 + 1}"
        else:
            key = QKeySequence(k).toString().lower()
            if len(key) != 1: return
        if not parts: return   # a hotkey needs a modifier
        self.set("+".join(parts + [key])); self.stop()

    def set(self, v):
        self.value = v; self.on_change(v)


def _wrap(w):
    sa = QScrollArea(); sa.setWidgetResizable(True); sa.setFrameShape(QFrame.NoFrame); sa.setWidget(w); return sa


def _note(text):
    l = QLabel(text); l.setWordWrap(True); l.setStyleSheet("color: gray"); return l


class SettingsWindow(QWidget):
    TABS = ["general", "appearance", "shortcuts", "snippets", "vault", "compare"]

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(L("LocalWriter Settings"))
        self.resize(760, 640)
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget(); lay.addWidget(self.tabs)
        self.compare_state = {"left": None, "right": None}
        self.refresh()

    @property
    def cfg(self): return self.app.cfg

    def changed(self, hotkeys=False, rebuild=False):
        self.app.save(hotkeys)
        if rebuild: QTimer.singleShot(0, self.refresh)

    def refresh(self):
        cur = self.tabs.currentIndex()
        self.tabs.clear(); self.tab_keys = []
        c = self.cfg
        for key, title, build, on in [("general", L("General"), self.general, True),
                                      ("appearance", L("Appearance"), self.appearance, True),
                                      ("shortcuts", L("Shortcuts"), self.shortcuts, c.featureAI),
                                      ("snippets", L("Snippets"), self.snippets, c.featureSnippets),
                                      ("vault", L("Vault"), self.vault, c.featureVault),
                                      ("compare", L("Compare"), self.compare, c.featureCompare)]:
            if on: self.tabs.addTab(_wrap(build()), title); self.tab_keys.append(key)
        if 0 <= cur < self.tabs.count(): self.tabs.setCurrentIndex(cur)

    def show_tab(self, key):
        if key in self.tab_keys: self.tabs.setCurrentIndex(self.tab_keys.index(key))

    def setter(self, attr, hotkeys=False, rebuild=False, conv=lambda v: v):
        def f(v):
            setattr(self.cfg, attr, conv(v)); self.changed(hotkeys, rebuild)
        return f

    def combo(self, items, current, on_change):
        cb = QComboBox()
        for v, label in items: cb.addItem(label, v)
        i = cb.findData(current)
        if i < 0: cb.addItem(str(current), current); i = cb.count() - 1
        cb.setCurrentIndex(i)
        cb.currentIndexChanged.connect(lambda _: on_change(cb.currentData()))
        return cb

    # ---- General ----
    def general(self):
        w = QWidget(); v = QVBoxLayout(w); c = self.cfg

        g = QGroupBox(L("Interface")); f = QFormLayout(g)

        def lang(x):
            c.uiLanguage = x; set_language(x); self.changed(); self.setWindowTitle(L("LocalWriter Settings")); QTimer.singleShot(0, self.refresh)
        f.addRow(L("App language"), self.combo([("en", "English"), ("de", "Deutsch")], c.uiLanguage, lang))
        auto = QCheckBox(L("Start with the system")); auto.setChecked(plat.autostart_enabled())
        auto.toggled.connect(plat.set_autostart); f.addRow(auto)
        v.addWidget(g)

        g = QGroupBox(L("Features")); f = QVBoxLayout(g)
        for attr, title, sub in [("featureAI", L("AI writing tools"), L("Rewrite, translate and analyze selected text with Ollama")),
                                 ("featureSnippets", L("Snippets"), L("Text expansion by abbreviation or hotkey")),
                                 ("featureVault", L("Vault"), L("Passwords protected by your vault password")),
                                 ("featureCompare", L("Compare files"), L("Metadata and content diff of two files"))]:
            cbx = QCheckBox(f"{title} — {sub}"); cbx.setChecked(getattr(c, attr))
            cbx.toggled.connect(self.setter(attr, hotkeys=True, rebuild=True)); f.addWidget(cbx)
        v.addWidget(g)

        if c.featureAI:
            g = QGroupBox("Ollama"); f = QFormLayout(g)
            url = QLineEdit(c.ollamaURL); url.editingFinished.connect(lambda: self.setter("ollamaURL")(url.text().strip()))
            f.addRow(L("Server URL"), url)
            row = QHBoxLayout()
            model = QComboBox(); model.setEditable(True)
            model.addItems(sorted(set(self.app.models + [c.model]))); model.setCurrentText(c.model)
            model.currentTextChanged.connect(lambda t: t and self.setter("model")(t))
            status = QLabel(L("%d models installed") % len(self.app.models) if self.app.models else L("Ollama not reachable or no models installed."))
            status.setStyleSheet("color: gray")
            ref = QPushButton(L("Refresh"))

            def refresh_models():
                def work():
                    self.app.refresh_models(); _post(self.refresh)
                _bg(work)
            ref.clicked.connect(refresh_models)
            row.addWidget(model, 1); row.addWidget(ref)
            f.addRow(L("Default model"), row); f.addRow("", status)
            temp = QSlider(Qt.Horizontal); temp.setRange(0, 100); temp.setValue(int(c.temperature * 100))
            tl = QLabel(f"{c.temperature:.2f}")
            temp.valueChanged.connect(lambda x: (tl.setText(f"{x / 100:.2f}"), setattr(c, "temperature", x / 100)))
            temp.sliderReleased.connect(lambda: self.changed())
            tr = QHBoxLayout(); tr.addWidget(temp, 1); tr.addWidget(tl)
            f.addRow(L("Creativity (temperature)"), tr)
            v.addWidget(g)

            g = QGroupBox(L("Behavior")); f = QFormLayout(g)
            f.addRow(L("Default mode"), self.combo([("replace", L("Replace directly")), ("preview", L("Show editable preview"))],
                                                   c.mode, self.setter("mode")))
            f.addRow(L("Output language"), self.combo([("auto", L("Same as the text"))] + [(l, l) for l in c.languages],
                                                      c.language, self.setter("language")))
            langs = QLineEdit(", ".join(c.languages))
            ap = QPushButton(L("Apply"))
            ap.clicked.connect(lambda: self.setter("languages", rebuild=True)([x.strip() for x in langs.text().split(",") if x.strip()]))
            lr = QHBoxLayout(); lr.addWidget(langs, 1); lr.addWidget(ap)
            f.addRow(L("Output languages to offer (comma-separated)"), lr)
            v.addWidget(g)

        g = QGroupBox(L("System")); f = QVBoxLayout(g)
        if plat.is_wayland():
            f.addWidget(_note("⚠️ " + L("Global hotkeys and typing don't work under Wayland. Log in with an X11 (Xorg) session.")))
        row = QHBoxLayout()
        b1 = QPushButton(L("Open config file")); b1.clicked.connect(lambda: plat.open_path(config_file()))
        b2 = QPushButton(L("Reload config file")); b2.clicked.connect(lambda: (self.app.reload(), self.refresh()))
        row.addWidget(b1); row.addWidget(b2); row.addStretch(); f.addLayout(row)
        f.addWidget(_note(config_file()))
        v.addWidget(g); v.addStretch()
        return w

    # ---- Appearance ----
    def appearance(self):
        w = QWidget(); v = QVBoxLayout(w); c = self.cfg
        g = QGroupBox(L("Appearance")); f = QFormLayout(g)
        f.addRow(L("Theme"), self.combo([("system", L("System")), ("light", L("Light")), ("dark", L("Dark"))], c.appearance,
                                        lambda x: (self.setter("appearance")(x), self.app.apply_appearance())))
        v.addWidget(g)
        g = QGroupBox(L("Preview window")); f = QFormLayout(g)
        fs = QSpinBox(); fs.setRange(9, 32); fs.setValue(int(c.previewFontSize))
        fs.valueChanged.connect(self.setter("previewFontSize", conv=float)); f.addRow(L("Font size"), fs)
        for attr, label in [("previewFloating", L("Keep window above other windows")), ("showOriginal", L("Show original text"))]:
            cbx = QCheckBox(label); cbx.setChecked(getattr(c, attr)); cbx.toggled.connect(self.setter(attr)); f.addRow(cbx)
        v.addWidget(g); v.addStretch()
        return w

    # ---- Shortcuts ----
    def shortcuts(self):
        w = QWidget(); v = QVBoxLayout(w); c = self.cfg
        g = QGroupBox(L("Action picker")); f = QFormLayout(g)
        f.addRow(L("Action picker"), HotkeyButton(self.app, c.pickerHotkey,
                                                  lambda x: self.setter("pickerHotkey", True, True)(x or "ctrl+alt+space"), allow_clear=False))
        f.addRow(_note(L("Shows all actions, a custom instruction and the output language at the mouse pointer.")))
        dups = sorted({h for h in c.all_hotkeys() if c.all_hotkeys().count(h) > 1})
        if dups: f.addRow(_note("⚠️ " + L("Used more than once: ") + ", ".join(keys.display(d) for d in dups)))
        if getattr(self.app, "failed_hotkeys", None):
            f.addRow(_note("⚠️ " + L("Some hotkeys could not be registered: ") + ", ".join(self.app.failed_hotkeys)))
        v.addWidget(g)

        g = QGroupBox(L("Your actions")); gl = QVBoxLayout(g)
        for i, a in enumerate(c.actions): gl.addWidget(self.action_editor(i, a))
        row = QHBoxLayout()
        nb = QPushButton("+ " + L("New action"))
        nb.clicked.connect(lambda: (c.actions.append(Action(L("New action"), prompt="")), self.changed(rebuild=True)))
        rb = QPushButton(L("Reset to defaults…")); rb.clicked.connect(self.reset_actions)
        row.addWidget(nb); row.addStretch(); row.addWidget(rb); gl.addLayout(row)
        v.addWidget(g)

        g = QGroupBox(L("More actions you can add")); gl = QVBoxLayout(g)
        gl.addWidget(_note(L("Add a preset, then assign any hotkey to it.")))
        have = {a.prompt for a in c.actions}
        for p in presets():
            if p.prompt in have: continue
            row = QHBoxLayout(); row.addWidget(QLabel(p.name), 1)
            b = QPushButton(L("Add"))
            b.clicked.connect(lambda _=False, p=p: (c.actions.append(Action(p.name, p.prompt, None, p.mode, None, p.kind)), self.changed(rebuild=True)))
            row.addWidget(b); gl.addLayout(row)
        row = QHBoxLayout(); row.addWidget(QLabel(L("Add a translate action for")), 1)
        lc = QComboBox(); lc.addItems(c.languages); row.addWidget(lc)
        b = QPushButton(L("Add")); row.addWidget(b)
        b.clicked.connect(lambda: (c.actions.append(Action.translate(lc.currentText())), self.changed(rebuild=True)))
        gl.addLayout(row)
        v.addWidget(g); v.addStretch()
        return w

    def action_editor(self, i, a):
        c = self.cfg
        box = QFrame(); box.setFrameShape(QFrame.StyledPanel); f = QFormLayout(box)
        top = QHBoxLayout()
        name = QLineEdit(a.name); name.editingFinished.connect(lambda: (setattr(a, "name", name.text()), self.changed()))
        top.addWidget(name, 1)
        top.addWidget(HotkeyButton(self.app, a.hotkey, lambda x: (setattr(a, "hotkey", x), self.changed(True, True))))
        for sym, tip, fn in [("↑", L("Move up"), lambda: self.move(i, -1)), ("↓", L("Move down"), lambda: self.move(i, 1)),
                             ("⧉", L("Duplicate"), lambda: (c.actions.insert(i + 1, Action(a.name + " " + L("(copy)"), a.prompt, None, a.mode, a.model, a.kind, a.targetLanguage)), self.changed(rebuild=True))),
                             ("✕", L("Delete"), lambda: (c.actions.pop(i), self.changed(True, True)))]:
            b = QPushButton(sym); b.setToolTip(tip); b.setFixedWidth(30); b.clicked.connect(fn); top.addWidget(b)
        f.addRow(top)
        f.addRow(L("Type"), self.combo([("transform", L("Rewrite selection")), ("continue", L("Continue text (appends after selection)")),
                                        ("analyze", L("Analyze (result shown in window)"))], a.kind_value,
                                       lambda x: (setattr(a, "kind", None if x == "transform" else x), self.changed())))
        f.addRow(L("Mode"), self.combo([(None, L("Default")), ("replace", L("Replace")), ("preview", L("Preview")),
                                        ("before", L("Insert before selection")), ("after", L("Insert after selection")),
                                        ("copy", L("Copy to clipboard"))], a.mode, lambda x: (setattr(a, "mode", x), self.changed())))
        f.addRow(L("Model"), self.combo([(None, L("Default"))] + [(m, m) for m in sorted(set(self.app.models))], a.model,
                                        lambda x: (setattr(a, "model", x), self.changed())))
        f.addRow(L("Output language"), self.combo([(None, L("Default"))] + [(l, l) for l in c.languages], a.targetLanguage,
                                                  lambda x: (setattr(a, "targetLanguage", x), self.changed())))
        p = QPlainTextEdit(a.prompt); p.setPlaceholderText(L("Describe what should happen with the selected text.")); p.setFixedHeight(64)
        p.textChanged.connect(lambda: setattr(a, "prompt", p.toPlainText()))
        p.focusOutEvent = lambda e, p=p: (self.changed(), QPlainTextEdit.focusOutEvent(p, e))
        f.addRow(L("Instruction for the model"), p)
        return box

    def move(self, i, d):
        j = i + d
        if 0 <= j < len(self.cfg.actions):
            a = self.cfg.actions; a[i], a[j] = a[j], a[i]; self.changed(rebuild=True)

    def reset_actions(self):
        if QMessageBox.question(self, L("Reset all actions to the defaults?"), L("Your own actions and hotkey changes will be lost.")) \
                == QMessageBox.Yes:
            from .config import default_actions
            self.cfg.actions = default_actions(); self.changed(True, True)

    # ---- Snippets ----
    def snippets(self):
        w = QWidget(); v = QVBoxLayout(w); c = self.cfg
        g = QGroupBox(L("Snippets")); f = QFormLayout(g)
        en = QCheckBox(L("Expand abbreviations while typing")); en.setChecked(c.snippetsEnabled); en.toggled.connect(self.setter("snippetsEnabled"))
        f.addRow(en)
        f.addRow(L("When"), self.combo([("immediate", L("Immediately")), ("delimiter", L("After space or punctuation"))],
                                       c.snippetTrigger, self.setter("snippetTrigger")))
        f.addRow(_note(L("Placeholders: {date} {time} {isodate} {clipboard} {cursor} (cursor ends up there)")))
        f.addRow(_note(L("Tip: start abbreviations with a character you rarely type, like ; or //.")))
        v.addWidget(g)
        g = QGroupBox(L("Your snippets")); gl = QVBoxLayout(g)
        if not c.snippets: gl.addWidget(_note(L("No snippets yet.")))
        for i, s in enumerate(c.snippets):
            box = QFrame(); box.setFrameShape(QFrame.StyledPanel); bl = QVBoxLayout(box)
            top = QHBoxLayout()
            ab = QLineEdit(s.abbreviation); ab.setPlaceholderText(L("Abbreviation")); ab.setFixedWidth(160)
            ab.editingFinished.connect(lambda s=s, ab=ab: (setattr(s, "abbreviation", ab.text()), self.changed()))
            top.addWidget(ab); top.addStretch()
            top.addWidget(HotkeyButton(self.app, s.hotkey, lambda x, s=s: (setattr(s, "hotkey", x), self.changed(True, True))))
            d = QPushButton("✕"); d.setFixedWidth(30); d.setToolTip(L("Delete"))
            d.clicked.connect(lambda _=False, i=i: (c.snippets.pop(i), self.changed(True, True))); top.addWidget(d)
            bl.addLayout(top)
            t = QPlainTextEdit(s.text); t.setFixedHeight(60)
            t.textChanged.connect(lambda s=s, t=t: setattr(s, "text", t.toPlainText()))
            t.focusOutEvent = lambda e, t=t: (self.changed(), QPlainTextEdit.focusOutEvent(t, e))
            bl.addWidget(t); gl.addWidget(box)
        nb = QPushButton("+ " + L("New snippet"))
        nb.clicked.connect(lambda: (c.snippets.append(Snippet()), self.changed(rebuild=True)))
        gl.addWidget(nb, 0, Qt.AlignLeft)
        v.addWidget(g); v.addStretch()
        return w

    # ---- Vault ----
    def vault(self):
        w = QWidget(); v = QVBoxLayout(w); c = self.cfg
        g = QGroupBox(L("Vault")); f = QFormLayout(g)
        f.addRow(_note(L("Secrets are stored in your system keyring (Windows Credential Manager / Secret Service), never in the config file. Every use asks for your vault password.")))
        if not vault.keyring_available():
            f.addRow(_note("⚠️ " + L("No keyring available. Install gnome-keyring or KWallet.")))
        f.addRow(L("Vault picker"), HotkeyButton(self.app, c.vaultHotkey,
                                                 lambda x: self.setter("vaultHotkey", True, True)(x or "ctrl+alt+v"), allow_clear=False))
        to = QSpinBox(); to.setRange(0, 600); to.setSuffix(" s"); to.setValue(int(c.vaultAuthTimeout))
        to.valueChanged.connect(self.setter("vaultAuthTimeout", conv=float)); f.addRow(L("Time to authenticate"), to)
        uf = QSpinBox(); uf.setRange(0, 86400); uf.setSuffix(" s"); uf.setSpecialValueText(L("never")); uf.setValue(int(c.vaultUnlockFor))
        uf.valueChanged.connect(self.setter("vaultUnlockFor", conv=float)); f.addRow(L("Stay unlocked after use"), uf)
        f.addRow(L("Insert by"), self.combo([("paste", L("Pasting (hidden from clipboard managers)")),
                                             ("type", L("Typing (for fields that block pasting)"))], c.vaultMethod, self.setter("vaultMethod")))
        cp = QPushButton(L("Change vault password…") if c.vaultPasswordHash else L("Set a vault password"))

        def change_pw():
            if c.vaultPasswordHash and not self.app.authenticate(L("show and edit the vault")): return
            self.app.set_vault_password(); self.refresh()
        cp.clicked.connect(change_pw); f.addRow(cp)
        v.addWidget(g)

        g = QGroupBox(L("Entries")); gl = QVBoxLayout(g)
        if not self._vault_open or self.vault_secrets is None:
            gl.addWidget(_note(L("%d entries") % len(c.vault)))
            ub = QPushButton("🔓 " + L("Unlock to view and edit"))

            def unlock():
                if self.app.authenticate(L("show and edit the vault")):
                    self.vault_secrets = vault.load(); self._vault_open = True; self.refresh(); self.show_tab("vault")
            ub.clicked.connect(unlock); gl.addWidget(ub, 0, Qt.AlignLeft)
        else:
            secrets = self.vault_secrets
            if not c.vault: gl.addWidget(_note(L("No entries yet.")))
            for i, e in enumerate(c.vault):
                row = QHBoxLayout()
                n = QLineEdit(e.name); n.setPlaceholderText(L("Name"))
                n.editingFinished.connect(lambda e=e, n=n: (setattr(e, "name", n.text()), self.changed()))
                s = QLineEdit(secrets.get(e.id, "")); s.setEchoMode(QLineEdit.Password); s.setPlaceholderText(L("Secret"))
                s.editingFinished.connect(lambda e=e, s=s: (secrets.__setitem__(e.id, s.text()), vault.save(secrets)))
                eye = QPushButton("👁"); eye.setFixedWidth(30); eye.setToolTip(L("Show/hide"))
                eye.clicked.connect(lambda _=False, s=s: s.setEchoMode(QLineEdit.Normal if s.echoMode() == QLineEdit.Password else QLineEdit.Password))
                hk = HotkeyButton(self.app, e.hotkey, lambda x, e=e: (setattr(e, "hotkey", x), self.changed(True, True)))
                d = QPushButton("✕"); d.setFixedWidth(30)
                d.clicked.connect(lambda _=False, i=i, e=e: (c.vault.pop(i), secrets.pop(e.id, None), vault.save(secrets), self.changed(True, True)))
                for x, st in [(n, 2), (s, 2), (eye, 0), (hk, 0), (d, 0)]: row.addWidget(x, st)
                gl.addLayout(row)
            row = QHBoxLayout()
            nb = QPushButton("+ " + L("New entry")); nb.clicked.connect(lambda: (c.vault.append(VaultEntry(L("New entry"))), self.changed(rebuild=True)))
            lb = QPushButton("🔒 " + L("Lock"))
            lb.clicked.connect(lambda: (self.app.vault_lock.lock(), setattr(self, "vault_secrets", None), setattr(self, "_vault_open", False), self.refresh()))
            row.addWidget(nb); row.addStretch(); row.addWidget(lb); gl.addLayout(row)
        v.addWidget(g); v.addStretch()
        return w

    _vault_open = False
    vault_secrets = None

    # ---- Compare ----
    def compare(self):
        w = QWidget(); v = QVBoxLayout(w); st = self.compare_state
        row = QHBoxLayout()
        for side in ("left", "right"):
            b = QPushButton((st[side].path if st[side] else L("Choose…")))
            b.clicked.connect(lambda _=False, side=side: self.pick_file(side)); row.addWidget(b, 1)
        sw = QPushButton(L("Swap")); sw.clicked.connect(lambda: (st.update(left=st["right"], right=st["left"]), self.refresh()))
        row.addWidget(sw); v.addLayout(row)
        l, r = st["left"], st["right"]
        if not (l and r):
            v.addWidget(_note(L("Choose or drop two files to compare their metadata and content.")))
            v.addWidget(_note(L("Text, code, PDF, Word (.docx), RTF and HTML are supported.")))
            v.addStretch(); return w
        if l.sha256 == r.sha256: v.addWidget(QLabel("✅ " + L("The files are byte-for-byte identical.")))

        # metadata
        t = QTableWidget(0, 3); t.setHorizontalHeaderLabels(["", l.path.split("/")[-1].split("\\")[-1], r.path.split("/")[-1].split("\\")[-1]])
        t.verticalHeader().hide(); t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        fmt = lambda d: d.strftime("%Y-%m-%d %H:%M:%S") if d else "–"  # noqa: E731
        num = lambda f, n: "–" if f.text is None else f"{n:,}"  # noqa: E731
        for label, a, b in [(L("Size"), f"{l.size:,} B", f"{r.size:,} B"), (L("Created"), fmt(l.created), fmt(r.created)),
                            (L("Modified"), fmt(l.modified), fmt(r.modified)), (L("Type"), l.kind, r.kind),
                            (L("Permissions"), l.permissions, r.permissions), (L("Lines"), num(l, len(l.lines)), num(r, len(r.lines))),
                            (L("Words"), num(l, l.words), num(r, r.words)),
                            (L("Characters"), num(l, len(l.text or "")), num(r, len(r.text or ""))), ("SHA-256", l.sha256, r.sha256)]:
            i = t.rowCount(); t.insertRow(i)
            for j, val in enumerate([label, a, b]):
                it = QTableWidgetItem(val)
                if j and a != b: it.setBackground(QColor(255, 200, 0, 60))
                t.setItem(i, j, it)
        t.setFixedHeight(30 * 10); v.addWidget(QLabel("<b>" + L("Metadata") + "</b>")); v.addWidget(t)
        v.addWidget(_note(L("Values that differ are highlighted.")))

        if l.text is None or r.text is None:
            v.addWidget(_note(L("At least one file is not a text file — only metadata can be compared."))); v.addStretch(); return w
        res = diff.compute(l.lines, r.lines)
        v.addWidget(QLabel("<b>" + L("Content") + "</b>  " + (L("%.0f%% identical lines") % (res.similarity * 100)).replace("%%", "%")
                           + f"   +{res.added}  −{res.removed}  ~{res.changed}"))
        only = QCheckBox(L("Only changes")); only.setChecked(st.get("only", True))
        only.toggled.connect(lambda x: (st.__setitem__("only", x), self.refresh(), self.show_tab("compare"))); v.addWidget(only)
        colors = {"changed": QColor(255, 200, 0, 60), "removed": QColor(255, 60, 60, 60), "added": QColor(60, 200, 60, 60)}
        rows = [x for x in res.rows if not (st.get("only", True) and x.kind == "same")][:5000]
        dt = QTableWidget(len(rows), 4); dt.setHorizontalHeaderLabels(["#", "", "#", ""]); dt.verticalHeader().hide()
        dt.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch); dt.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        for i, x in enumerate(rows):
            for j, val in enumerate([x.left_no, x.left, x.right_no, x.right]):
                it = QTableWidgetItem("" if val is None else str(val))
                if x.kind in colors: it.setBackground(colors[x.kind])
                dt.setItem(i, j, it)
        dt.resizeColumnToContents(0); dt.resizeColumnToContents(2); dt.setMinimumHeight(260)
        if not rows: v.addWidget(_note(L("No differences in content.")))
        else: v.addWidget(dt)

        if self.cfg.featureAI and res.same != len(res.rows):
            v.addWidget(QLabel("<b>" + L("AI summary") + "</b>"))
            out = QTextEdit(st.get("ai", "")); out.setReadOnly(True); out.setMinimumHeight(120)
            b = QPushButton(L("Explain the differences with AI") if not st.get("ai") else L("Regenerate"))

            def explain():
                out.setPlainText(L("Generating…"))
                prompt = ("Compare two versions of a file and explain the differences concisely: what was added, removed or changed "
                          "and what it means. Use short bullet points.")
                user = f"File A: {l.path}\nFile B: {r.path}\n\nChanges (- = only in A, + = only in B):\n{res.unified()}"

                def work():
                    try: s = ollama.clean(ollama.chat(prompt + f"\nAnswer in {self.cfg.ui_language_name}.", user, self.cfg.model, self.cfg), None)
                    except Exception as e: s = "⚠️ " + str(e)  # noqa: BLE001
                    st["ai"] = s; _post(lambda: out.setPlainText(s))
                _bg(work)
            b.clicked.connect(explain)
            v.addWidget(b, 0, Qt.AlignLeft); v.addWidget(out)
            v.addWidget(_note(L("Uses the model %@ — everything stays on this Mac.").replace("%@", self.cfg.model).replace("Mac", "PC")))
        v.addStretch()
        return w

    def pick_file(self, side):
        paths, _ = QFileDialog.getOpenFileNames(self, L("Choose a file (or two at once)"))
        if not paths: return
        st = self.compare_state; st["ai"] = ""
        if len(paths) >= 2:
            st["left"], st["right"] = diff.load(paths[0]), diff.load(paths[1])
        else:
            st[side] = diff.load(paths[0])
        self.refresh(); self.show_tab("compare")
