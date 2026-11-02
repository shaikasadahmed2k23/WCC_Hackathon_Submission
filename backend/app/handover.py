"""Claim loading, labels, readiness, versioned snapshots, role-filtered views, continuation plan."""
import json
from datetime import date, datetime, timedelta

from .db import jload, now
from .security import SENS_LABEL

TYPE_ORDER = ["decision", "owner", "action", "risk", "dependency", "state", "question", "gap", "contact"]
TYPE_LABEL = {"decision": "Decision", "owner": "Ownership", "action": "Action", "risk": "Risk", "dependency": "Dependency",
              "state": "Project state", "question": "Open question", "gap": "Gap", "contact": "Contact"}


def label_for(c: dict, in_open_conflict: bool) -> str:
    if c["review_status"] == "unsupported":
        return "unsupported"
    if c["review_status"] == "rejected":
        return "rejected"
    if c["type"] == "gap":
        return "stated" if c.get("answer") else "missing"
    if in_open_conflict:
        return "conflicting"
    if c["review_status"] in ("confirmed", "edited"):
        return "verified"
    if c["origin"] == "inferred":
        return "inferred"
    return "supported"


def _evidence(db, claim_id):
    out = []
    for e in db.execute(
        "SELECT e.*, c.text, c.location, c.ts, c.speaker, c.sensitivity AS sens, c.idx, s.id AS source_id, s.name AS source_name, "
        "s.kind AS source_kind, s.doc_date FROM claim_evidence e JOIN chunks c ON c.id=e.chunk_id JOIN sources s ON s.id=c.source_id "
        "WHERE e.claim_id=? ORDER BY e.id", (claim_id,)):
        out.append(dict(e))
    return out


def context_for(db, ev: dict):
    items = []
    for r in db.execute("SELECT * FROM chunks WHERE source_id=? AND idx BETWEEN ? AND ? ORDER BY idx",
                        (ev["source_id"], ev["idx"] - 1, ev["idx"] + 1)):
        item = {"text": r["text"], "speaker": r["speaker"], "ts": r["ts"], "location": r["location"], "sens": r["sensitivity"],
                "hl": r["id"] == ev["chunk_id"]}
        if item["hl"]:
            item["start"], item["end"] = ev["start"], ev["end"]
        items.append(item)
    return items


def load_claims(db, project_id, clearance=2, with_evidence=True, include_hidden_states=True):
    conf_ids = {}
    open_conf = set()
    for r in db.execute("SELECT * FROM conflicts WHERE project_id=?", (project_id,)):
        for k in (r["claim_a"], r["claim_b"]):
            conf_ids.setdefault(k, []).append(r["id"])
            if r["status"] in ("open", "accepted"):
                open_conf.add(k)
    users = {r["id"]: r["name"] for r in db.execute("SELECT id,name FROM users")}
    out = []
    for r in db.execute("SELECT * FROM claims WHERE project_id=? ORDER BY id", (project_id,)):
        c = dict(r)
        if c["clearance"] > clearance:
            continue
        c["label"] = label_for(c, c["id"] in open_conf)
        c["conflict_ids"] = conf_ids.get(c["id"], [])
        c["clearance_label"] = SENS_LABEL[c["clearance"]]
        c["reviewed_by_name"] = users.get(c["reviewed_by"])
        c["answered_by_name"] = users.get(c["answered_by"])
        ev = _evidence(db, c["id"])
        c["source_count"] = len({e["source_id"] for e in ev})
        c["sources"] = sorted({e["source_name"] for e in ev})
        if with_evidence:
            c["evidence"] = [{"source_id": e["source_id"], "source_name": e["source_name"], "source_kind": e["source_kind"],
                              "location": e["location"], "quote": e["quote"], "speaker": e["speaker"], "ts": e["ts"],
                              "sens": e["sens"], "context": context_for(db, e)} for e in ev]
        c.pop("fingerprint", None)
        out.append(c)
    return out


def readiness(db, project_id):
    claims = load_claims(db, project_id, 2, with_evidence=False)
    active = [c for c in claims if c["label"] not in ("rejected", "unsupported")]
    core = [c for c in active if c["type"] != "gap"]
    reviewed = [c for c in core if c["label"] == "verified" or c["review_status"] in ("confirmed", "edited")]
    open_gaps = [c for c in active if c["type"] == "gap" and c["label"] == "missing"]
    open_conf = db.execute("SELECT COUNT(*) n FROM conflicts WHERE project_id=? AND status='open'", (project_id,)).fetchone()["n"]
    base = round(100 * len(reviewed) / len(core)) if core else 0
    pen_c = min(40, 10 * open_conf)
    pen_g = min(20, 2 * len(open_gaps))
    return {"score": max(0, base - pen_c - pen_g), "claims": len(core), "reviewed": len(reviewed), "unreviewed": len(core) - len(reviewed),
            "open_conflicts": open_conf, "open_gaps": len(open_gaps), "penalty_conflicts": pen_c, "penalty_gaps": pen_g,
            "base": base}


def build_snapshot(db, project_id):
    p = dict(db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())
    claims = [c for c in load_claims(db, project_id, 2) if c["label"] not in ("rejected", "unsupported")]
    keep = {c["id"] for c in claims}
    conflicts = []
    for r in db.execute("SELECT * FROM conflicts WHERE project_id=?", (project_id,)):
        if r["claim_a"] in keep and r["claim_b"] in keep:
            conflicts.append({k: r[k] for k in ("id", "claim_a", "claim_b", "vclass", "reason", "status", "resolution", "note")})
    sources = [{"id": s["id"], "name": s["name"], "kind": s["kind"], "doc_date": s["doc_date"], "sensitivity": s["sensitivity"]}
               for s in db.execute("SELECT * FROM sources WHERE project_id=?", (project_id,))]
    return {"project": {"id": p["id"], "name": p["name"], "description": p["description"], "workspace": p["workspace"]},
            "generated_at": now(), "sources": sources, "claims": claims, "conflicts": conflicts, "readiness": readiness(db, project_id)}


def _bucket(due: str | None, today: date):
    if not due:
        return None
    try:
        d = datetime.strptime(due, "%Y-%m-%d").date()
    except ValueError:
        return None
    if d < today:
        return "overdue"
    if d <= today + timedelta(days=1):
        return "day1"
    if d <= today + timedelta(days=7):
        return "week"
    if d <= today + timedelta(days=30):
        return "month"
    return "later"


PLAN_TITLES = {"overdue": "Overdue", "day1": "First 24 hours", "week": "First week", "month": "First 30 days", "later": "Later"}


def build_plan(claims: list, today: date | None = None):
    today = today or date.today()
    buckets = {k: [] for k in PLAN_TITLES}

    def add(bucket, text, c, kind, owner=None):
        buckets[bucket].append({"text": text, "owner": owner or "Unassigned", "due": c.get("due"), "claim_id": c["id"], "kind": kind,
                                "label": c["label"]})
    for c in claims:
        t = c["type"]
        if t == "action":
            add(_bucket(c.get("due"), today) or "week", c["statement"], c, "Action", c.get("owner"))
        elif t == "risk" and c.get("severity") == "High":
            add("day1" if c.get("recurring") else "week", "Mitigate: " + c["statement"], c, "Risk", c.get("owner"))
        elif t == "dependency":
            add(_bucket(c.get("due"), today) or "month", c["statement"], c, "Dependency", c.get("owner"))
        elif t == "gap" and c["label"] == "missing":
            add("week", ("Assign an owner: " if c.get("subtype") == "missing_owner" else "Find out: ") + c["statement"], c, "Gap")
        elif t == "question":
            add("week", "Get an answer: " + c["statement"], c, "Question")
    return [{"key": k, "title": PLAN_TITLES[k], "items": v} for k, v in buckets.items() if v]


def view_snapshot(snapshot: dict, clearance: int):
    """Filter a frozen snapshot to what this clearance may see. Hidden content is never sent to the client."""
    visible, hidden = [], {}
    for c in snapshot["claims"]:
        if c["clearance"] <= clearance:
            cc = dict(c)
            cc["evidence"] = [dict(e, context=[x if x["sens"] <= clearance else {"restricted": True, "hl": False, "sens": x["sens"]}
                                               for x in e["context"]]) for e in c["evidence"]]
            visible.append(cc)
        else:
            hidden[c["type"]] = hidden.get(c["type"], 0) + 1
    vis_ids = {c["id"] for c in visible}
    conflicts = [x for x in snapshot["conflicts"] if x["claim_a"] in vis_ids and x["claim_b"] in vis_ids]
    return {"project": snapshot["project"], "generated_at": snapshot["generated_at"], "claims": visible,
            "hidden": {"total": sum(hidden.values()), "by_type": hidden}, "conflicts": conflicts,
            "plan": build_plan(visible), "readiness": snapshot["readiness"], "clearance": clearance,
            "clearance_label": SENS_LABEL[clearance], "source_count": len(snapshot["sources"])}


LABEL_TEXT = {"verified": "Verified", "supported": "Supported, not reviewed", "inferred": "Inferred", "conflicting": "Conflicting",
              "missing": "Missing", "stated": "Stated by a person, no document evidence"}


def to_markdown(view: dict, version_number: int, approved_by: str | None):
    lines = [f"# Handover: {view['project']['name']}", "",
             f"Version {version_number}" + (f", approved by {approved_by}" if approved_by else "") + f". Generated {view['generated_at']}.",
             f"Prepared for access level: {view['clearance_label']}. "
             + (f"{view['hidden']['total']} item(s) were withheld because of access level." if view["hidden"]["total"] else ""), ""]
    for t in TYPE_ORDER:
        group = [c for c in view["claims"] if c["type"] == t]
        if not group:
            continue
        lines += [f"## {TYPE_LABEL[t]}s" if not TYPE_LABEL[t].endswith("s") else f"## {TYPE_LABEL[t]}", ""]
        for c in group:
            meta = [LABEL_TEXT.get(c["label"], c["label"])]
            if c.get("owner"):
                meta.append(f"owner: {c['owner']}")
            if c.get("due"):
                meta.append(f"due: {c['due']}")
            if c.get("severity"):
                meta.append(f"severity: {c['severity']}")
            lines.append(f"- {c['statement']} _({'; '.join(meta)})_")
            if c.get("answer"):
                lines.append(f"  - Answer from {c.get('answered_by_name') or 'a team member'}: {c['answer']}")
            for e in c["evidence"][:2]:
                lines.append(f"  - Source: {e['source_name']}, {e['location']}")
        lines.append("")
    if view["conflicts"]:
        lines += ["## Conflicting information", ""]
        for x in view["conflicts"]:
            lines.append(f"- {x['reason']} ({x['status']})")
        lines.append("")
    lines += ["## Continuation plan", ""]
    for b in view["plan"]:
        lines.append(f"### {b['title']}")
        for it in b["items"]:
            lines.append(f"- {it['text']} (owner: {it['owner']}{', due ' + it['due'] if it['due'] else ''})")
        lines.append("")
    return "\n".join(lines)
