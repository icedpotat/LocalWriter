"""Config: same JSON format as the macOS app, so a config file can be copied between systems."""
import json
import locale
import os
import sys
import uuid
from dataclasses import dataclass, field, asdict, fields

from .l10n import L


def system_ui_language() -> str:
    lang = (locale.getlocale()[0] or os.environ.get("LANG", "") or "en").lower()
    return "de" if lang.startswith("de") else "en"


def config_dir() -> str:
    if sys.platform == "win32":
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "LocalWriter")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "localwriter")


def config_file() -> str:
    return os.path.join(config_dir(), "config.json")


def new_id() -> str:
    return str(uuid.uuid4()).upper()


@dataclass
class Action:
    name: str
    prompt: str
    hotkey: str | None = None
    mode: str | None = None          # replace | preview | before | after | copy
    model: str | None = None
    kind: str | None = None          # None (rewrite) | continue | analyze
    targetLanguage: str | None = None
    id: str = field(default_factory=new_id)   # runtime only, not saved (same as the macOS app)

    @property
    def kind_value(self) -> str:
        return self.kind or "transform"

    def to_json(self):
        d = {k: v for k, v in asdict(self).items() if v is not None and k != "id"}
        return d

    @staticmethod
    def from_json(d):
        known = {f.name for f in fields(Action)} - {"id"}
        return Action(**{k: v for k, v in d.items() if k in known})

    @staticmethod
    def translate(lang: str) -> "Action":
        return Action(name=L("Translate to") + " " + lang,
                      prompt=f"Translate the text into {lang}. Preserve meaning, tone and formatting.",
                      targetLanguage=lang)


@dataclass
class Snippet:
    abbreviation: str = ""
    text: str = ""
    hotkey: str | None = None
    id: str = field(default_factory=new_id)

    @property
    def title(self) -> str:
        first = next((l for l in self.text.split("\n") if l), "")
        short = first[:40] + "…" if len(first) > 40 else first
        return f"{self.abbreviation}  →  {short}" if self.abbreviation else short

    def to_json(self):
        return {k: v for k, v in asdict(self).items() if v is not None}

    @staticmethod
    def from_json(d):
        return Snippet(abbreviation=d.get("abbreviation", ""), text=d.get("text", ""),
                       hotkey=d.get("hotkey"), id=d.get("id") or new_id())


@dataclass
class VaultEntry:
    name: str = ""
    hotkey: str | None = None
    id: str = field(default_factory=new_id)

    def to_json(self):
        return {k: v for k, v in asdict(self).items() if v is not None}

    @staticmethod
    def from_json(d):
        return VaultEntry(name=d.get("name", ""), hotkey=d.get("hotkey"), id=d.get("id") or new_id())


def presets() -> list[Action]:
    return [
        Action(L("Fix grammar & spelling"), hotkey="ctrl+alt+g",
               prompt="Correct spelling, grammar and punctuation. Make minimal changes; keep the author's wording, voice, formatting and line breaks."),
        Action(L("Improve writing"), hotkey="ctrl+alt+i",
               prompt="Improve the writing: make it clearer, more concise and more fluent while preserving the meaning, facts and the author's voice. Keep formatting (lists, line breaks, markdown)."),
        Action(L("Make professional"), prompt="Rewrite in a professional, polished business tone. Preserve meaning and formatting."),
        Action(L("Make casual"), prompt="Rewrite in a relaxed, casual, conversational tone. Preserve meaning."),
        Action(L("Make friendlier"), prompt="Rewrite to sound warmer and friendlier while staying natural. Preserve meaning."),
        Action(L("Shorten"), prompt="Make the text substantially shorter while keeping all key information."),
        Action(L("Expand"), prompt="Expand the text with more detail and explanation while keeping its meaning, tone and formatting."),
        Action(L("Convert to bullet points"), prompt="Restructure the text as a clear, concise bullet-point list. Keep all relevant information."),
        Action(L("Translate to selected language"), prompt="Translate the text. Preserve formatting.", mode="preview"),
        Action(L("Continue writing"), prompt="Continue the text with one or two more sentences or paragraphs that follow naturally.", kind="continue"),
        Action(L("Explain code"), prompt="Explain what this code does: purpose, how it works step by step, inputs/outputs, and any notable pitfalls or bugs. Be concise.", kind="analyze"),
        Action(L("Extract key points"), prompt="Extract the key points of the text as a short bullet list. Only include what is actually stated.", kind="analyze"),
        Action(L("Summarize"), hotkey="ctrl+alt+s", prompt="Summarize the text in a few sentences.", kind="analyze"),
        Action(L("Explain simply"), prompt="Explain the text in simple, plain language so that a non-expert understands it.", kind="analyze"),
        Action(L("Draft a reply"), prompt="The text is a message the user received. Write a polite, helpful reply to it in a matching tone. Output only the reply itself.", mode="preview", kind="analyze"),
        Action(L("Find action items"), prompt="List all tasks, to-dos, deadlines and decisions mentioned in the text as a checklist.", kind="analyze"),
    ]


def default_actions() -> list[Action]:
    p = presets()
    return [p[0], p[1], p[12], p[14]]


DEFAULTS = dict(
    ollamaURL="http://localhost:11434", model="qwen3.5:9b", mode="replace", language="auto",
    languages=["English", "German", "French", "Spanish", "Italian", "Dutch", "Portuguese", "Polish",
               "Turkish", "Russian", "Ukrainian", "Chinese", "Japanese", "Korean", "Arabic"],
    pickerHotkey="ctrl+alt+space", temperature=0.3, appearance="system", menuBarIcon="✍︎",
    previewFontSize=14.0, previewFloating=True, showOriginal=True,
    featureAI=True, featureSnippets=True, featureVault=True, featureCompare=True,
    snippetsEnabled=True, snippetTrigger="immediate",
    vaultHotkey="ctrl+alt+v", vaultAuthTimeout=20.0, vaultUnlockFor=0.0, vaultMethod="paste",
)


class Config:
    def __init__(self, data: dict | None = None):
        data = data or {}
        for k, v in DEFAULTS.items():
            setattr(self, k, data.get(k, v if not isinstance(v, list) else list(v)))
        self.uiLanguage = data.get("uiLanguage", system_ui_language())
        self.actions = [Action.from_json(a) for a in data["actions"]] if "actions" in data else default_actions()
        self.snippets = ([Snippet.from_json(s) for s in data["snippets"]] if "snippets" in data else
                         [Snippet(";date", "{date}"), Snippet(";br", L("Best regards,") + "\n")])
        self.vault = [VaultEntry.from_json(v) for v in data.get("vault", [])]
        # Windows/Linux only: PBKDF2 hash of the vault password (see vault.py)
        self.vaultPasswordHash = data.get("vaultPasswordHash")

    @staticmethod
    def load() -> "Config":
        try:
            with open(config_file(), encoding="utf-8") as f:
                return Config(json.load(f))
        except FileNotFoundError:
            c = Config(); c.save(); return c
        except Exception as e:  # noqa: BLE001
            print("Config error:", e, file=sys.stderr)
            return Config()

    def to_json(self) -> dict:
        d = {k: getattr(self, k) for k in DEFAULTS}
        d["uiLanguage"] = self.uiLanguage
        d["actions"] = [a.to_json() for a in self.actions]
        d["snippets"] = [s.to_json() for s in self.snippets]
        d["vault"] = [v.to_json() for v in self.vault]
        if self.vaultPasswordHash:
            d["vaultPasswordHash"] = self.vaultPasswordHash
        return d

    def save(self):
        os.makedirs(config_dir(), exist_ok=True)
        tmp = config_file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.to_json(), f, indent=2, sort_keys=True, ensure_ascii=False)
        os.replace(tmp, config_file())

    @property
    def ui_language_name(self) -> str:
        return "German" if self.uiLanguage == "de" else "English"

    def all_hotkeys(self) -> list[str]:
        hk = [self.pickerHotkey]
        if self.featureAI: hk += [a.hotkey for a in self.actions]
        if self.featureSnippets: hk += [s.hotkey for s in self.snippets]
        if self.featureVault: hk += [v.hotkey for v in self.vault] + [self.vaultHotkey]
        return [h.lower() for h in hk if h]
