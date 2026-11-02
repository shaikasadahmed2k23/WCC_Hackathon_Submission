"""Verification and analysis passes: quote verification, de-duplication, conflicts, gaps, recurrence."""
import hashlib
import re

from .extract_rules import LEX, tokens, value_of
from .textproc import split_sentences

REASON_RX = re.compile(r"\b(because|since|due to|reason|so that|to avoid|to keep|to reduce|in order to|otherwise|as the|as it)\b", re.I)
CHANGE_RX = re.compile(r"\b(switch|drop|replace|instead of|move|migrat|use |go with|adopt|stop)\b", re.I)
PROBLEM_TERMS = ["memory", "outage", "lock", "timeout", "race", "crash", "retry", "expire", "backup"]
TECH_TERMS = ["redis", "postgres", "postgresql", "mysql", "mongodb", "firebase", "supabase", "docker", "nginx", "celery", "kafka",
              "rabbitmq", "razorpay", "stripe", "twilio", "sendgrid", "sentry", "cloudflare", "capacitor", "flutter", "oauth", "s3"]
CLASS_NAME = {"region": "deployment region", "database": "database", "hosting": "hosting provider",
              "payments": "payment provider", "deadline": "deadline", "owner": "owner"}


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def fingerprint(ctype: str, quote: str, subtype: str = "") -> str:
    return hashlib.sha1(f"{ctype}|{subtype}|{norm(quote)}".encode()).hexdigest()[:16]


def locate(quote: str, text: str):
    """Find quote in text tolerant to whitespace and case. Returns (start, end) or None."""
    words = quote.split()
    if not words:
        return None
    rx = r"\s+".join(re.escape(w) for w in words)
    m = re.search(rx, text, re.I)
    return (m.start(), m.end()) if m else None


def verify(candidate: dict, chunk_text: dict, all_chunks: list):
    """Return evidence dict or None. The quote must exist verbatim in the cited chunk
    (or, failing that, uniquely elsewhere in the project) and must actually support the statement."""
    quote = candidate["quote"].strip()
    if len(quote) < 12:
        return None
    cid = candidate["chunk_id"]
    span = locate(quote, chunk_text.get(cid, ""))
    if span is None:
        hits = [(c["id"], locate(quote, c["text"])) for c in all_chunks]
        hits = [(i, s) for i, s in hits if s]
        if len(hits) != 1:
            return None
        cid, span = hits[0]
    st, qt = tokens(candidate["statement"]), tokens(quote)
    if st and len(st & qt) / len(st) < 0.4:
        return None
    return {"chunk_id": cid, "quote": chunk_text[cid][span[0]:span[1]], "start": span[0], "end": span[1]}


def annotate_values(c: dict):
    cls, val = value_of(c["quote"] if c.get("quote") else c["statement"])
    c["vclass"], c["vvalue"] = cls, val


def merge_duplicates(claims: list):
    out = []
    for c in claims:
        merged = False
        ct = tokens(c["statement"])
        for o in out:
            if o["type"] != c["type"]:
                continue
            ot = tokens(o["statement"])
            overlap = len(ct & ot)
            cont = overlap / max(1, min(len(ct), len(ot)))
            if not ((overlap >= 4 and cont >= 0.6) or (overlap >= 3 and cont >= 0.9)):
                continue
            if o.get("owner") and c.get("owner") and o["owner"] != c["owner"]:
                continue
            if o.get("due") and c.get("due") and o["due"] != c["due"]:
                continue
            o["owner"] = o.get("owner") or c.get("owner")
            o["due"] = o.get("due") or c.get("due")
            for ev in c["evidence"]:
                if all(ev["chunk_id"] != e["chunk_id"] for e in o["evidence"]):
                    o["evidence"].append(ev)
            merged = True
            break
        if not merged:
            out.append(c)
    return out


def detect_conflicts(claims: list, cinfo: dict):
    """claims have 'evidence'; cinfo maps chunk_id -> {source_name, date}. Returns [(i, j, vclass, reason)]."""
    found = {}

    def when(c):
        ev = c["evidence"][0]
        info = cinfo[ev["chunk_id"]]
        return (c.get("event_date") or info.get("date") or "")[:10], info["source_name"]

    def add(i, j, cls, va, vb):
        key = (min(i, j), max(i, j))
        if key in found:
            return
        a, b = claims[i], claims[j]
        (da, sa), (db_, sb) = when(a), when(b)
        label = CLASS_NAME.get(cls, cls)
        reason = (f"Different {label}: {sa}{f' ({da})' if da else ''} says {va}; {sb}{f' ({db_})' if db_ else ''} says {vb}. "
                  f"The later source may be more current, but a reviewer needs to confirm.")
        found[key] = (key[0], key[1], cls, reason)

    live = [(i, c) for i, c in enumerate(claims) if c["review_status"] != "unsupported"]
    for x, (i, a) in enumerate(live):
        for j, b in live[x + 1:]:
            if a["evidence"][0]["chunk_id"] == b["evidence"][0]["chunk_id"]:
                continue
            if a.get("vclass") and a.get("vclass") == b.get("vclass") and a["vvalue"] != b["vvalue"]:
                add(i, j, a["vclass"], a["vvalue"], b["vvalue"])
                continue
            if a["type"] in ("action", "risk", "dependency", "decision") and b["type"] in ("action", "risk", "dependency", "decision"):
                ta, tb = tokens(a["statement"]), tokens(b["statement"])
                overlap = len(ta & tb)
                if overlap >= 3 and overlap / max(1, min(len(ta), len(tb))) >= 0.6:
                    if a.get("due") and b.get("due") and a["due"] != b["due"]:
                        add(i, j, "deadline", a["due"], b["due"])
                    elif a.get("owner") and b.get("owner") and a["owner"] != b["owner"] and a["type"] == "action" == b["type"]:
                        add(i, j, "owner", a["owner"], b["owner"])
    return list(found.values())


def detect_gaps(claims: list, chunk_text: dict, chunks: list, sources: dict):
    """Return gap claims describing what the sources cannot answer."""
    gaps = []
    by_pos = {(c["source_id"], c["idx"]): c for c in chunks}
    chunk_by_id = {c["id"]: c for c in chunks}

    def gap(subtype, statement, base_claim=None, evidence=None):
        ev = evidence or (base_claim["evidence"][:1] if base_claim else [])
        if not ev:
            return
        gaps.append({"type": "gap", "subtype": subtype, "statement": statement, "owner": None, "due": None, "severity": None,
                     "origin": "gap", "extractor": "rules", "event_date": base_claim.get("event_date") if base_claim else None,
                     "evidence": ev, "review_status": "pending", "vclass": None, "vvalue": None, "recurring": 0,
                     "fingerprint": fingerprint("gap", ev[0]["quote"], subtype)})

    for c in claims:
        if c["review_status"] == "unsupported":
            continue
        if c["type"] == "action" and not c.get("owner"):
            gap("missing_owner", f"No owner is recorded for: {c['statement'].rstrip('.')}", c)
        if c["type"] == "decision" and CHANGE_RX.search(c["statement"]):
            ev = c["evidence"][0]
            ch = chunk_by_id[ev["chunk_id"]]
            texts = [ch["text"]]
            nxt = by_pos.get((ch["source_id"], ch["idx"] + 1))
            if nxt and sources[ch["source_id"]]["kind"] != "chat":
                texts.append(nxt["text"])
            if not any(REASON_RX.search(t) for t in texts) and not REASON_RX.search(c["statement"]):
                gap("missing_rationale", f"The reason for this decision is not recorded: {c['statement'].rstrip('.')}", c)
        if c["type"] == "question":
            continue

    mentions = {}
    for ch in chunks:
        kind = sources[ch["source_id"]]["kind"]
        low = ch["text"].lower()
        for term in TECH_TERMS:
            if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", low):
                mentions.setdefault(term, []).append((kind, ch))
    seen_terms = set()
    for term, lst in mentions.items():
        if term in ("postgres", "postgresql") and ("postgres" in seen_terms or "postgresql" in seen_terms):
            continue
        if all(k in ("chat", "note") for k, _ in lst):
            ch = lst[0][1]
            sent = next((s for s in split_sentences(ch["text"]) if term in s.lower()), None)
            if not sent:
                continue
            span = locate(sent, ch["text"])
            if not span:
                continue
            ev = [{"chunk_id": ch["id"], "quote": ch["text"][span[0]:span[1]], "start": span[0], "end": span[1]}]
            gap("undocumented", f"{term.capitalize() if term != 'oauth' else 'OAuth'} is mentioned only in chat. No document or task describes how it is set up or who controls it.",
                None, ev)
            seen_terms.add(term)
    return gaps


def mark_recurring(claims: list):
    for term in PROBLEM_TERMS:
        chunk_ids = set()
        risky = []
        for c in claims:
            if c["review_status"] == "unsupported" or c["type"] not in ("risk", "decision"):
                continue
            if term in c["statement"].lower():
                chunk_ids.add(c["evidence"][0]["chunk_id"])
                if c["type"] == "risk":
                    risky.append(c)
        if len(chunk_ids) >= 2:
            for c in risky:
                c["recurring"] = 1
