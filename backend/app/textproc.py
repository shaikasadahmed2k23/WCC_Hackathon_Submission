"""Text handling: decoding, redaction, sensitivity flags, parsing and chunking.

Everything here is deterministic. Secrets are masked before any text is stored,
displayed or sent to a language model.
"""
import csv
import io
import json
import re
from datetime import datetime

# ----------------------------------------------------------------- redaction
_PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("api_key", re.compile(r"\b(?:sk|gsk|rk|pk_live|sk_live)[-_][A-Za-z0-9_\-]{16,}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("aadhaar", re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")),
    ("pan", re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")),
]
_SECRET_ASSIGN = re.compile(
    r"(?i)\b(password|passwd|pwd|passcode|secret|api[ _-]?key|access[ _-]?token|token)\b(\s*(?:is|=|:)\s*)(\S+)"
)
_CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")


def _luhn(num: str) -> bool:
    digits = [int(c) for c in num if c.isdigit()]
    if not 13 <= len(digits) <= 16:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def redact(text: str):
    """Mask secrets and identifiers. Returns (clean_text, {type: count})."""
    counts: dict[str, int] = {}

    def bump(kind):
        counts[kind] = counts.get(kind, 0) + 1

    for kind, rx in _PATTERNS:
        def sub(m, kind=kind):
            bump(kind)
            return f"[REDACTED:{kind}]"
        text = rx.sub(sub, text)

    def card_sub(m):
        if _luhn(m.group(0)):
            bump("card_number")
            return "[REDACTED:card_number]"
        return m.group(0)
    text = _CARD.sub(card_sub, text)

    def assign_sub(m):
        value = m.group(3).rstrip(".,;)")
        tail = m.group(3)[len(value):]
        looks_secret = len(value) >= 6 and (any(c.isdigit() for c in value) or any(not c.isalnum() for c in value))
        if value.startswith("[REDACTED") or not looks_secret:
            return m.group(0)
        bump("password" if "pass" in m.group(1).lower() or "pwd" in m.group(1).lower() else "secret")
        return f"{m.group(1)}{m.group(2)}[REDACTED:{'password' if 'pass' in m.group(1).lower() or 'pwd' in m.group(1).lower() else 'secret'}]{tail}"
    text = _SECRET_ASSIGN.sub(assign_sub, text)
    return text, counts


# ----------------------------------------------------------- sensitivity
_CONF = re.compile(
    r"\b(confidential|do not share|don't share|not for (?:juniors|volunteers|the public)|core committee|"
    r"salary|stipend|disciplinary|harassment|medical)", re.I)
_INTERNAL = re.compile(r"\b(internal|budget|sponsorship|invoice|vendor contract|quotation)\b", re.I)
EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RX = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?\d{5}[\s-]?\d{5}(?!\d)")


def sensitivity_level(text: str):
    """Return (level 0-2, flags). Level is a floor; uploaders can only raise it."""
    flags = []
    level = 0
    if _CONF.search(text):
        level = 2
        flags.append("confidential-language")
    if "[REDACTED" in text:
        level = 2
        flags.append("redacted-secret")
    if EMAIL_RX.search(text) or PHONE_RX.search(text):
        level = max(level, 1)
        flags.append("contact-details")
    if _INTERNAL.search(text):
        level = max(level, 1)
        flags.append("internal-language")
    return level, flags


# ----------------------------------------------------------------- dates
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_D1 = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_D2 = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?:,?\s+(\d{4}))?", re.I)
_D3 = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b", re.I)


def parse_date_text(s: str, default_year: int = 2026):
    """First recognisable date in s as ISO yyyy-mm-dd, else None."""
    if not s:
        return None
    m = _D1.search(s)
    if m:
        return _valid(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _D2.search(s)
    if m:
        return _valid(int(m.group(3) or default_year), _MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
    m = _D3.search(s)
    if m:
        return _valid(int(m.group(3) or default_year), _MONTHS[m.group(1)[:3].lower()], int(m.group(2)))
    return None


def _valid(y, mo, d):
    try:
        return datetime(y, mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


def detect_doc_date(name: str, text: str):
    m = re.search(r"(?im)^\s*(?:date|updated|last updated)\s*[:\-]\s*(\d{4}-\d{2}-\d{2})", text[:1500])
    if m:
        return m.group(1)
    m = _D1.search(name)
    return m.group(0) if m else None


# --------------------------------------------------------------- decoding
def decode_bytes(data: bytes) -> str:
    if b"\x00" in data[:4096]:
        raise ValueError("This looks like a binary file. Upload text-based files (txt, md, csv, json, chat exports).")
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    raise ValueError("Could not decode this file as text.")


# --------------------------------------------------------------- parsing
CHAT_RE = re.compile(
    r"^\[?(?P<d>\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}),?\s+(?P<t>\d{1,2}:\d{2})(?::\d{2})?\s*(?P<ap>[APap][Mm])?\]?\s*[-–]?\s*"
    r"(?P<who>[^:\n]{1,40}?):\s(?P<msg>.*)$"
)


def _chat_ts(d, t, ap):
    if "/" in d:
        dd, mm, yy = d.split("/")
        yy = int(yy)
        yy = yy + 2000 if yy < 100 else yy
        iso = f"{yy:04d}-{int(mm):02d}-{int(dd):02d}"
    else:
        iso = d
    hh, mi = t.split(":")
    hh = int(hh)
    if ap:
        if ap.lower() == "pm" and hh < 12:
            hh += 12
        if ap.lower() == "am" and hh == 12:
            hh = 0
    return f"{iso}T{hh:02d}:{mi}"


def parse_chat(text: str):
    msgs = []
    for lineno, line in enumerate(text.splitlines(), 1):
        m = CHAT_RE.match(line.strip())
        if m:
            msgs.append({"speaker": m.group("who").strip(), "ts": _chat_ts(m.group("d"), m.group("t"), m.group("ap")),
                         "text": m.group("msg").strip(), "line": lineno})
        elif msgs and line.strip():
            msgs[-1]["text"] += "\n" + line.strip()
    return msgs


def looks_like_chat(text: str) -> bool:
    lines = [l for l in text.splitlines()[:60] if l.strip()]
    hits = sum(1 for l in lines if CHAT_RE.match(l.strip()))
    return hits >= 3 and hits >= len(lines) * 0.5


def detect_kind(name: str, text: str) -> str:
    n = name.lower()
    if n.endswith((".csv", ".tsv")):
        return "task"
    if looks_like_chat(text):
        return "chat"
    if n.endswith(".json"):
        return "data"
    return "doc"


# --------------------------------------------------------------- chunking
def _rows_to_chunks(rows, label="row"):
    chunks = []
    for i, row in enumerate(rows, 2 if label == "row" else 1):
        parts = []
        for k, v in row.items():
            v = "" if v is None else str(v).strip()
            if v:
                parts.append(f"{k}: {v[:600]}")
        if parts:
            chunks.append({"text": " | ".join(parts), "location": f"{label} {i}", "ts": None, "speaker": None})
    return chunks


def chunk_text(kind: str, name: str, text: str):
    if kind == "chat":
        return [{"text": m["text"], "location": f"line {m['line']}", "ts": m["ts"], "speaker": m["speaker"]}
                for m in parse_chat(text)]
    if kind == "task":
        delim = "\t" if name.lower().endswith(".tsv") else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delim)
        return _rows_to_chunks([{(k or "").strip().lower(): v for k, v in r.items()} for r in reader])
    if kind == "data":
        try:
            obj = json.loads(text)
        except Exception:
            obj = None
        if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
            return _rows_to_chunks([{str(k).lower(): (v if not isinstance(v, (dict, list)) else json.dumps(v)) for k, v in x.items()} for x in obj], "item")
        if isinstance(obj, dict):
            flat = []

            def walk(prefix, val):
                if isinstance(val, dict):
                    for k, v in val.items():
                        walk(f"{prefix}.{k}" if prefix else k, v)
                elif isinstance(val, list):
                    for i, v in enumerate(val):
                        walk(f"{prefix}[{i}]", v)
                else:
                    flat.append(f"{prefix}: {val}")
            walk("", obj)
            text = "\n".join(flat)
    return _paragraph_chunks(text)


def _paragraph_chunks(text: str, max_chars: int = 520):
    lines = text.splitlines()
    chunks, buf, start, pending_heading = [], [], None, None

    def flush(end):
        nonlocal buf, start, pending_heading
        if not buf:
            return
        body = "\n".join(buf).strip()
        if body:
            if pending_heading:
                body = pending_heading[0] + "\n" + body
                s = pending_heading[1]
            else:
                s = start
            chunks.append({"text": body, "location": f"lines {s}-{end}" if end != s else f"line {s}", "ts": None, "speaker": None})
        buf, start, pending_heading = [], None, None

    for no, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            flush(no - 1)
            continue
        if stripped.startswith("#"):
            flush(no - 1)
            pending_heading = (stripped, no)
            continue
        if start is None:
            start = no
        if buf and sum(len(b) for b in buf) + len(stripped) > max_chars:
            flush(no - 1)
            start = no
        buf.append(stripped)
    flush(len(lines))
    if pending_heading:
        chunks.append({"text": pending_heading[0], "location": f"line {pending_heading[1]}", "ts": None, "speaker": None})
    return chunks


# --------------------------------------------------------- sentence split
_ABBR = ["Dr.", "Mr.", "Ms.", "Mrs.", "Prof.", "e.g.", "i.e.", "vs.", "No.", "Rs.", "approx."]


def split_sentences(text: str):
    """Split into sentences, keeping each as an exact substring of the input."""
    protected = text
    for a in _ABBR:
        protected = protected.replace(a, a.replace(".", "\x00"))
    out = []
    for line in protected.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])", line)
        for p in parts:
            p = p.replace("\x00", ".").strip()
            if p:
                out.append(p)
    return out
