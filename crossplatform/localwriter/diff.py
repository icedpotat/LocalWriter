"""File comparison: metadata + side-by-side line diff (same output as the macOS app's Compare tab)."""
import difflib
import hashlib
import html
import mimetypes
import os
import re
import stat
import zipfile
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FileInfo:
    path: str
    size: int = 0
    created: datetime | None = None
    modified: datetime | None = None
    kind: str = ""
    permissions: str = ""
    sha256: str = ""
    text: str | None = None

    @property
    def lines(self): return self.text.splitlines() if self.text is not None else []
    @property
    def words(self): return len(self.text.split()) if self.text is not None else 0


def load(path: str) -> FileInfo:
    f = FileInfo(path)
    st = os.stat(path)
    f.size = st.st_size
    f.modified = datetime.fromtimestamp(st.st_mtime)
    f.created = datetime.fromtimestamp(getattr(st, "st_birthtime", st.st_ctime))
    mode = stat.S_IMODE(st.st_mode)
    f.permissions = stat.filemode(st.st_mode)[1:] + f"  ({mode:o})"
    f.kind = mimetypes.guess_type(path)[0] or (os.path.splitext(path)[1].lstrip(".") or "file")
    with open(path, "rb") as fh:
        data = fh.read()
    f.sha256 = hashlib.sha256(data).hexdigest()
    try:
        f.text = extract_text(path, data)
    except Exception:  # noqa: BLE001
        f.text = None
    return f


def _strip_tags(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?</\1>", "", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</h\d>|</li>", "\n", s)
    return html.unescape(re.sub(r"<[^>]+>", "", s))


def extract_text(path: str, data: bytes) -> str | None:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
    if ext in (".docx", ".odt"):
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml" if ext == ".docx" else "content.xml").decode("utf-8", "replace")
        xml = re.sub(r"</w:p>|</text:p>|</text:h>", "\n", xml)
        xml = re.sub(r"<w:tab/>", "\t", xml)
        return html.unescape(re.sub(r"<[^>]+>", "", xml))
    if ext in (".html", ".htm"):
        return _strip_tags(data.decode("utf-8", "replace"))
    if ext == ".rtf":
        s = data.decode("latin-1")
        s = re.sub(r"\\par[d]?", "\n", s)
        s = re.sub(r"\\'([0-9a-f]{2})", lambda m: bytes.fromhex(m.group(1)).decode("cp1252", "replace"), s)
        s = re.sub(r"\\[a-z]+-?\d* ?|[{}]", "", s)
        return s
    if b"\0" in data[:8000]:
        if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
            return data.decode("utf-16")
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


@dataclass
class Row:
    left_no: int | None
    left: str | None
    right_no: int | None
    right: str | None
    kind: str           # same | changed | removed | added


@dataclass
class DiffResult:
    rows: list[Row] = field(default_factory=list)
    added: int = 0
    removed: int = 0
    changed: int = 0
    same: int = 0

    @property
    def similarity(self): return 1.0 if not self.rows else self.same / len(self.rows)

    def unified(self, limit=12000) -> str:
        s = ""
        for r in self.rows:
            if r.kind == "same": continue
            if r.left is not None: s += f"- {r.left}\n"
            if r.right is not None: s += f"+ {r.right}\n"
            if len(s) > limit: return s + "…\n"
        return s


def compute(a: list[str], b: list[str]) -> DiffResult:
    res = DiffResult()
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                res.rows.append(Row(i1 + k + 1, a[i1 + k], j1 + k + 1, b[j1 + k], "same")); res.same += 1
            continue
        for k in range(max(i2 - i1, j2 - j1)):
            l = i1 + k if i1 + k < i2 else None
            r = j1 + k if j1 + k < j2 else None
            kind = "changed" if l is not None and r is not None else ("removed" if l is not None else "added")
            setattr(res, kind, getattr(res, kind) + 1)
            res.rows.append(Row(l + 1 if l is not None else None, a[l] if l is not None else None,
                                r + 1 if r is not None else None, b[r] if r is not None else None, kind))
    return res
