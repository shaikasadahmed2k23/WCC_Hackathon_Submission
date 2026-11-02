"""Deterministic claim extraction.

Each sentence in a chunk is classified with transparent patterns. The sentence itself is the
evidence quote, so every claim produced here is, by construction, a substring of its source.
"""
import re

from .textproc import EMAIL_RX, PHONE_RX, parse_date_text, split_sentences

RX = {
    "question": re.compile(
        r"\?\s*$|\b(open question|unresolved|tbd|to be decided|not yet decided|unclear|nobody knows|no one knows|who will|who owns|who is going to)(?!\w)", re.I),
    "decision": re.compile(
        r"\b(decision\s*:|decided|we (?:will|'ll|are going to) (?:use|go with|keep|move|switch|drop|adopt|stay|stop|replace)|"
        r"agreed (?:to|that|on)|going with|chose|chosen|finali[sz]ed|settled on|approved|instead of|"
        r"switch(?:ed|ing)? (?:to|from)|drop(?:ped)? the|"
        r"(?:moved|migrated|switched) (?:the |our )?[\w\- ]{1,30}? to)(?!\w)", re.I),
    "dependency": re.compile(
        r"\b(depends? on|dependency|dependencies|blocked by|waiting (?:for|on)|prerequisite|"
        r"requires? (?:approval|kyc|sign[- ]?off|review)|needs? (?:approval|kyc|sign[- ]?off))(?!\w)", re.I),
    "risk": re.compile(
        r"\b(risk|blockers?|fails?|failing|failures?|flaky|not (?:yet )?(?:been )?tested|untested|breaks?|broken|outage|"
        r"locks? the|never (?:run|deploy|delete|restart)|do not (?:run|deploy|delete|merge|push|restart)|"
        r"don'?t (?:run|deploy|delete|merge|push|restart)|warning|careful|expires?|expiry|vulnerab\w*|data loss|"
        r"single point|bus factor|may (?:fail|break|slip|be delayed)|might (?:fail|break|slip)|"
        r"(?:run(?:s|ning)?|ran) out of memory|out of memory|drops? keys|no retry|without a backup|must stay)(?!\w)", re.I),
    "action": re.compile(
        r"\b(todo|to-do|action(?: item)?\s*:|next action|follow[- ]?up|needs? to|need to|must(?! stay)|has to|have to|"
        r"will (?:test|run|renew|document|review|fix|check|schedule|send|confirm|take over|transfer|migrate|rotate|add|update|set up|ship)|"
        r"rotate|please (?:run|test|renew|check|update)|needs? (?:a |another )?review|should be (?:done|renewed|tested|documented))(?!\w)", re.I),
    "ownership": re.compile(
        r"\b(owns?|owned by|owner\s*:|responsible for|in charge of|is (?:coordinating|handling|maintaining|managing|leading|running)|"
        r"maintains?|point of contact|assigned to)(?!\w)", re.I),
}
LABEL_PREFIX = re.compile(r"^(?:[-*>•]+\s*|\d+[.)]\s+)?(?:\*\*)?(?:(?:decision|risk|action(?: item)?|open question|note|todo|warning|confidential)\s*[:\-–]|(?:fyi|btw)[\s,:\-–]+)\s*(?:\*\*)?\s*", re.I)
BULLET = re.compile(r"^(?:[-*>•]+\s*|\d+[.)]\s+)")

# Value lexicons for conflict detection: class -> (context words, {alias: canonical})
LEX = {
    "region": (r"deploy|host|region|server|instance|moved|migrated|running|runs|cluster", {
        "mumbai": "Mumbai", "ap-south-1": "Mumbai", "singapore": "Singapore", "ap-southeast-1": "Singapore",
        "us-east-1": "N. Virginia", "virginia": "N. Virginia", "oregon": "Oregon", "frankfurt": "Frankfurt", "london": "London"}),
    "database": (r"database|db\b|datastore|stored? in|backed by|uses?|use\b|instead of|migrat", {
        "postgresql": "PostgreSQL", "postgres": "PostgreSQL", "mysql": "MySQL", "mongodb": "MongoDB",
        "sqlite": "SQLite", "firestore": "Firestore", "dynamodb": "DynamoDB"}),
    "hosting": (r"deploy|hosted|hosting|runs on|running on", {
        "aws": "AWS", "render": "Render", "vercel": "Vercel", "railway": "Railway", "heroku": "Heroku",
        "netlify": "Netlify", "azure": "Azure", "gcp": "GCP", "fly.io": "Fly.io"}),
    "payments": (r"fee|payment|checkout|collection|collect", {
        "razorpay": "Razorpay", "stripe": "Stripe", "paypal": "PayPal", "cashfree": "Cashfree", "payu": "PayU"}),
}

STOP_NAMES = {"The", "This", "That", "We", "Team", "Next", "Decision", "Action", "Risk", "Note", "Open", "Please", "Somebody",
              "Someone", "Nobody", "FYI", "It", "He", "She", "They", "There", "Date", "Attendees", "Warning", "Priority"}


def tokens(text: str):
    stop = {"the", "and", "for", "that", "this", "with", "from", "are", "was", "will", "has", "have", "not", "but", "its", "our",
            "can", "all", "any", "been", "into", "than", "then", "also", "after", "before", "when", "which", "who", "what", "how",
            "should", "would", "could", "need", "needs", "must", "does", "did", "yet", "still", "only", "just", "they", "them"}
    found = {t.rstrip(".") for t in re.findall(r"[a-z0-9][a-z0-9\-/\.]{2,}", text.lower())}
    for t in list(found):
        if "." in t and not t.replace(".", "").isdigit():
            found.update(p for p in t.split(".") if len(p) >= 3)
    return {t for t in found if t not in stop}


def clean_statement(s: str) -> str:
    s = LABEL_PREFIX.sub("", s.strip())
    s = BULLET.sub("", s)
    s = s.replace("**", "").replace("`", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:1].upper() + s[1:] if s else s


def find_owner(sentence: str, speaker, people):
    if re.search(r"\b(I'll|I will|I'm going to|I am going to)\b", sentence) and speaker:
        return speaker
    names = sorted(people, key=len, reverse=True)
    # Full-name or first-name mentions, mapped back to the canonical full name.
    lookup = {}
    for full in names:
        lookup[full.lower()] = full
        first = re.sub(r"^(?:dr|mr|ms|mrs|prof)\.?\s+", "", full, flags=re.I).split()[0].lower()
        lookup.setdefault(first, full)
    alt = "|".join(re.escape(k) for k in sorted(lookup, key=len, reverse=True))
    if not alt:
        return None
    subj = re.search(
        rf"(?<![A-Za-z])({alt})(?:'s)?\b\s+(?:will|owns?|is|has|to|should|must|can|handles?|maintains?|runs?|takes?|following|coordinat\w+|leads?|manages?)\b",
        sentence, re.I)
    if subj:
        return lookup[subj.group(1).lower()]
    obj = re.search(rf"(?:owner|assigned to|owned by|handled by|led by)\s*[:\-]?\s*({alt})\b", sentence, re.I)
    if obj:
        return lookup[obj.group(1).lower()]
    return None


def find_due(sentence: str):
    m = re.search(r"\b(?:by|before|due|until|deadline|on)\b[^.;]{0,25}", sentence, re.I)
    if m:
        d = parse_date_text(m.group(0))
        if d:
            return d
    return parse_date_text(sentence)


def value_of(sentence: str):
    """Return (class, canonical value) for the first lexicon class the sentence speaks about."""
    low = sentence.lower()
    for cls, (ctx, aliases) in LEX.items():
        if not re.search(ctx, low):
            continue
        hits = []
        for alias, canon in aliases.items():
            for m in re.finditer(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", low):
                hits.append((m.start(), canon))
        if not hits:
            continue
        hits.sort()
        canon_hits = [c for _, c in hits]
        chosen = canon_hits[0]
        move = re.search(r"\b(?:moved|migrated|switched|switch|move)\b.*?\bto\b", low)
        if move:
            after = [(p, c) for p, c in hits if p > move.end() - 2]
            if after:
                chosen = after[0][1]
        if cls == "hosting" and chosen == "AWS" and ("s3" in low):
            continue
        return cls, chosen
    return None, None


def severity_of(sentence: str):
    low = sentence.lower()
    if re.search(r"\b(minor|cosmetic|nice to have)\b", low):
        return "Low"
    if re.search(r"prod|production|data loss|lock|outage|expire|security|payment|backup|not (?:yet )?(?:been )?tested|untested|break|registration|out of memory", low):
        return "High"
    return "Medium"


def _row_fields(text: str):
    out = {}
    for part in text.split(" | "):
        if ": " in part:
            k, v = part.split(": ", 1)
            out[k.strip().lower()] = v.strip()
    return out


def _pick(row, names):
    for n in names:
        if n in row and row[n]:
            return row[n]
    return None


def extract_from_chunk(chunk: dict, source: dict, people):
    """Return candidate claims for one chunk. Each has a verbatim 'quote'."""
    out = []
    text = chunk["text"]
    if source["kind"] == "task" or (source["kind"] == "data" and ": " in text and " | " in text):
        row = _row_fields(text)
        title = _pick(row, ["title", "task", "summary", "name"])
        if title:
            status = (_pick(row, ["status", "state"]) or "").lower()
            owner = _pick(row, ["owner", "assignee", "assigned to", "assigned_to"])
            due = parse_date_text(_pick(row, ["due", "due date", "deadline"]) or "")
            if status not in ("done", "closed", "complete", "completed", "resolved"):
                out.append({"type": "action", "statement": clean_statement(title), "quote": text[:300], "owner": owner,
                            "due": due, "severity": None, "event_date": chunk.get("ts")})
            notes = _pick(row, ["notes", "description", "comment", "comments", "blocked by", "blocked_by"])
            if notes and status not in ("done", "closed", "complete", "completed", "resolved"):
                for s in split_sentences(notes):
                    for kind in ("dependency", "risk"):
                        if RX[kind].search(s):
                            out.append({"type": kind, "statement": clean_statement(f"{title}: {s}"), "quote": s, "owner": owner,
                                        "due": due, "severity": severity_of(s) if kind == "risk" else None,
                                        "event_date": chunk.get("ts")})
                            break
        return out

    speaker = chunk.get("speaker")
    is_chat = source["kind"] == "chat"
    for sent in split_sentences(text):
        q = BULLET.sub("", sent).strip()
        if len(q) < 18 or q.startswith("#") or re.match(r"(?i)^(date|attendees)\s*:", q):
            continue
        if len(q.split()) < 4:
            continue
        has_contact = bool(EMAIL_RX.search(q) or PHONE_RX.search(q))
        kinds = []
        if RX["question"].search(q):
            if not is_chat or (len(q.split()) >= 8 and re.search(r"\b(who|which|when)\b", q, re.I)):
                kinds.append("question")
        if not kinds:
            for k in ("decision", "dependency", "risk", "action"):
                if RX[k].search(q):
                    kinds.append(k)
                    break
        if has_contact and not kinds:
            kinds.append("contact")
        if not kinds and RX["ownership"].search(q):
            kinds.append("owner")
        if not kinds:
            cls, val = value_of(q)
            if cls:
                kinds.append("state")
        if not kinds:
            continue
        kind = kinds[0]
        owner = find_owner(q, speaker, people)
        out.append({
            "type": kind, "statement": clean_statement(q), "quote": q, "owner": owner,
            "due": find_due(q) if kind in ("action", "decision", "dependency", "risk") else None,
            "severity": severity_of(q) if kind == "risk" else None,
            "event_date": chunk.get("ts"),
        })
        if has_contact and kind != "contact":
            out.append({"type": "contact", "statement": clean_statement(q), "quote": q, "owner": None, "due": None,
                        "severity": None, "event_date": chunk.get("ts")})
        if kind not in ("owner", "contact") and RX["ownership"].search(q) and owner:
            out.append({"type": "owner", "statement": clean_statement(q), "quote": q, "owner": owner, "due": None,
                        "severity": None, "event_date": chunk.get("ts")})
    return out
