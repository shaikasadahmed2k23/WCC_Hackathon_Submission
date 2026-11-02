"""ContinuityOS API."""
import json
import os
from contextlib import asynccontextmanager
from datetime import date

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .analysis import norm
from .db import audit, connect, get_db, init_db, jload, now
from .github_import import GitHubError, fetch_repo, parse_repo
from .handover import (TYPE_LABEL, build_snapshot, load_claims, readiness, to_markdown, view_snapshot)
from .pipeline import IngestError, ingest_source, reconstruct
from .security import (REVIEWERS, ROLE_CLEARANCE, ROLE_LABEL, SENS_LABEL, STAFF, create_session, current_user, require, verify_password)
from .seed import DEMO_PASSWORD, USERS, seed
from .textproc import sensitivity_level

DEMO_MODE = os.getenv("DEMO_MODE", "1") == "1"


@asynccontextmanager
async def lifespan(app):
    if config.RESEED_ON_START:
        for ext in ("", "-wal", "-shm"):
            try:
                os.remove(config.DATABASE_PATH + ext)
            except FileNotFoundError:
                pass
    init_db()
    conn = connect()
    try:
        seed(conn)
        conn.commit()
    finally:
        conn.close()
    yield


app = FastAPI(title="ContinuityOS API", version="2.0", lifespan=lifespan)


def _project(db, pid):
    p = db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not p:
        raise HTTPException(404, "Project not found")
    return dict(p)


def _clearance(user, db=None, version_id=None):
    c = ROLE_CLEARANCE[user["role"]]
    if db is not None and version_id is not None:
        g = db.execute("SELECT clearance FROM grants WHERE version_id=? AND user_id=?", (version_id, user["id"])).fetchone()
        if g:
            c = max(c, g["clearance"])
    return c


def public_user(u):
    return {"id": u["id"], "name": u["name"], "email": u["email"], "role": u["role"], "role_label": ROLE_LABEL[u["role"]],
            "title": u["title"], "clearance": u["clearance"], "clearance_label": SENS_LABEL[u["clearance"]]}


# ------------------------------------------------------------------ auth
class LoginIn(BaseModel):
    email: str
    password: str


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/config")
def get_config():
    return {"extractor": config.extractor_mode(), "llm_model": config.LLM_MODEL if config.extractor_mode() == "llm" else None,
            "demo": DEMO_MODE, "demo_password": DEMO_PASSWORD if DEMO_MODE else None,
            "demo_accounts": [{"email": e, "name": n, "role": r, "role_label": ROLE_LABEL[r], "title": t}
                              for n, e, r, t in USERS] if DEMO_MODE else []}


@app.post("/api/auth/login")
def login(body: LoginIn, db=Depends(get_db)):
    row = db.execute("SELECT * FROM users WHERE lower(email)=lower(?)", (body.email.strip(),)).fetchone()
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(401, "Incorrect email or password")
    token = create_session(db, row["id"])
    audit(db, dict(row), "auth.login", row["email"])
    return {"token": token, "user": public_user(dict(row))}


@app.post("/api/auth/logout")
def logout(user=Depends(current_user), db=Depends(get_db)):
    db.execute("DELETE FROM sessions WHERE token=?", (user["token"],))
    return {"ok": True}


@app.get("/api/me")
def me(user=Depends(current_user)):
    return public_user(user)


# ------------------------------------------------------------- projects
@app.get("/api/projects")
def projects(user=Depends(current_user), db=Depends(get_db)):
    out = []
    for p in db.execute("SELECT * FROM projects ORDER BY id"):
        d = dict(p)
        d["departing"] = (db.execute("SELECT name FROM users WHERE id=?", (p["departing_user_id"],)).fetchone() or {"name": None})["name"]
        d["sources"] = db.execute("SELECT COUNT(*) n FROM sources WHERE project_id=?", (p["id"],)).fetchone()["n"]
        out.append(d)
    return out


@app.get("/api/projects/{pid}/overview")
def overview(pid: int, user=Depends(require(*STAFF)), db=Depends(get_db)):
    p = _project(db, pid)
    claims = load_claims(db, pid, ROLE_CLEARANCE[user["role"]], with_evidence=False)
    live = [c for c in claims if c["label"] not in ("rejected", "unsupported")]
    by_label, by_type = {}, {}
    for c in live:
        by_label[c["label"]] = by_label.get(c["label"], 0) + 1
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1
    versions = [dict(r) for r in db.execute(
        "SELECT v.id,v.number,v.status,v.created_at,v.note,u.name approved_by FROM versions v LEFT JOIN users u ON u.id=v.approved_by "
        "WHERE project_id=? ORDER BY number DESC", (pid,))]
    attention = []
    for r in db.execute("SELECT * FROM conflicts WHERE project_id=? AND status='open'", (pid,)):
        attention.append({"kind": "conflict", "text": r["reason"], "ref": r["id"]})
    for c in live:
        if c["type"] == "gap" and c["label"] == "missing" and c["subtype"] == "missing_owner":
            attention.append({"kind": "gap", "text": c["statement"], "ref": c["id"]})
    for c in live:
        if c["type"] == "risk" and c["severity"] == "High" and c["label"] != "verified":
            attention.append({"kind": "risk", "text": c["statement"], "ref": c["id"]})
    recent = [dict(r) for r in db.execute("SELECT * FROM audit WHERE project_id=? ORDER BY id DESC LIMIT 6", (pid,))]
    srcs = db.execute("SELECT COUNT(*) n, COALESCE(SUM(size),0) s FROM sources WHERE project_id=?", (pid,)).fetchone()
    chunks = db.execute("SELECT COUNT(*) n FROM chunks c JOIN sources s ON s.id=c.source_id WHERE s.project_id=?", (pid,)).fetchone()["n"]
    return {"project": p, "departing": (db.execute("SELECT name FROM users WHERE id=?", (p["departing_user_id"],)).fetchone() or {"name": None})["name"],
            "sources": srcs["n"], "chunks": chunks, "claims": len(live), "by_label": by_label, "by_type": by_type,
            "readiness": readiness(db, pid), "versions": versions, "attention": attention[:8], "recent": recent,
            "extractor": config.extractor_mode()}


# -------------------------------------------------------------- sources
def _source_rows(db, pid):
    out = []
    users = {r["id"]: r["name"] for r in db.execute("SELECT id,name FROM users")}
    for s in db.execute("SELECT * FROM sources WHERE project_id=? ORDER BY id", (pid,)):
        d = dict(s)
        d["redactions"] = jload(d["redactions"], {})
        row = db.execute("SELECT COUNT(*) n, COALESCE(MAX(sensitivity),0) m, SUM(CASE WHEN sensitivity>? THEN 1 ELSE 0 END) f "
                         "FROM chunks WHERE source_id=?", (d["sensitivity"], d["id"])).fetchone()
        d["chunks"], d["effective_sensitivity"], d["raised_chunks"] = row["n"], row["m"], row["f"] or 0
        d["claims"] = db.execute("SELECT COUNT(DISTINCT e.claim_id) n FROM claim_evidence e JOIN chunks c ON c.id=e.chunk_id "
                                 "JOIN claims cl ON cl.id=e.claim_id WHERE c.source_id=? AND cl.review_status!='unsupported' AND cl.type!='gap'",
                                 (d["id"],)).fetchone()["n"]
        d["uploaded_by_name"] = users.get(d["uploaded_by"])
        d["sensitivity_label"] = SENS_LABEL[d["sensitivity"]]
        out.append(d)
    return out


@app.get("/api/projects/{pid}/sources")
def list_sources(pid: int, user=Depends(require(*STAFF)), db=Depends(get_db)):
    _project(db, pid)
    return _source_rows(db, pid)


def _ingest_response(db, user, pid, info):
    audit(db, user, "source.added", info["name"], f"{info['chunks']} chunks, {sum(info['redactions'].values())} redactions", pid)
    return info


@app.post("/api/projects/{pid}/sources/upload")
async def upload_source(pid: int, file: UploadFile = File(...), sensitivity: int = Form(0), doc_date: str = Form(""),
                        user=Depends(require(*STAFF)), db=Depends(get_db)):
    _project(db, pid)
    if sensitivity not in (0, 1, 2):
        raise HTTPException(422, "Sensitivity must be 0, 1 or 2")
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    try:
        info = ingest_source(db, pid, file.filename or "upload.txt", data, user["id"], sensitivity, doc_date or None)
    except IngestError as exc:
        raise HTTPException(422, str(exc))
    return _ingest_response(db, user, pid, info)


class NoteIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=200_000)
    sensitivity: int = 0
    doc_date: str | None = None


@app.post("/api/projects/{pid}/sources/note")
def add_note(pid: int, body: NoteIn, user=Depends(require(*STAFF)), db=Depends(get_db)):
    _project(db, pid)
    if body.sensitivity not in (0, 1, 2):
        raise HTTPException(422, "Sensitivity must be 0, 1 or 2")
    try:
        info = ingest_source(db, pid, body.name, body.text, user["id"], body.sensitivity, body.doc_date, kind="doc")
    except IngestError as exc:
        raise HTTPException(422, str(exc))
    return _ingest_response(db, user, pid, info)


class GithubIn(BaseModel):
    repo: str
    sensitivity: int = 0


@app.post("/api/projects/{pid}/sources/github")
def add_github(pid: int, body: GithubIn, user=Depends(require(*STAFF)), db=Depends(get_db)):
    _project(db, pid)
    try:
        owner, repo = parse_repo(body.repo)
        items = fetch_repo(owner, repo)
    except GitHubError as exc:
        raise HTTPException(422, str(exc))
    added, errors = [], []
    for name, text, ddate in items:
        try:
            added.append(_ingest_response(db, user, pid, ingest_source(db, pid, name, text, user["id"], body.sensitivity, ddate,
                                                                       kind="doc", uri=f"https://github.com/{owner}/{repo}")))
        except IngestError as exc:
            errors.append(f"{name}: {exc}")
    if not added:
        raise HTTPException(422, "; ".join(errors) or "Nothing could be imported.")
    return {"added": added, "skipped": errors}


@app.get("/api/sources/{sid}")
def get_source(sid: int, user=Depends(require(*STAFF)), db=Depends(get_db)):
    s = db.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
    if not s:
        raise HTTPException(404, "Source not found")
    clr = ROLE_CLEARANCE[user["role"]]
    chunks = []
    for c in db.execute("SELECT * FROM chunks WHERE source_id=? ORDER BY idx", (sid,)):
        if c["sensitivity"] > clr:
            chunks.append({"idx": c["idx"], "restricted": True, "sens": c["sensitivity"], "location": c["location"]})
        else:
            chunks.append({"idx": c["idx"], "text": c["text"], "location": c["location"], "ts": c["ts"], "speaker": c["speaker"],
                           "sens": c["sensitivity"], "flags": jload(c["flags"], [])})
    d = dict(s)
    d["redactions"] = jload(d["redactions"], {})
    return {"source": d, "chunks": chunks}


class SensIn(BaseModel):
    sensitivity: int


def recompute_clearance(db, pid):
    for c in db.execute("SELECT id FROM claims WHERE project_id=?", (pid,)).fetchall():
        m = db.execute("SELECT MAX(ch.sensitivity) m FROM claim_evidence e JOIN chunks ch ON ch.id=e.chunk_id WHERE e.claim_id=?",
                       (c["id"],)).fetchone()["m"]
        db.execute("UPDATE claims SET clearance=? WHERE id=?", (m or 0, c["id"]))


@app.patch("/api/sources/{sid}")
def set_source_sensitivity(sid: int, body: SensIn, user=Depends(require(*REVIEWERS)), db=Depends(get_db)):
    s = db.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
    if not s:
        raise HTTPException(404, "Source not found")
    if body.sensitivity not in (0, 1, 2):
        raise HTTPException(422, "Sensitivity must be 0, 1 or 2")
    db.execute("UPDATE sources SET sensitivity=? WHERE id=?", (body.sensitivity, sid))
    for c in db.execute("SELECT id,text FROM chunks WHERE source_id=?", (sid,)).fetchall():
        level, _ = sensitivity_level(c["text"])
        db.execute("UPDATE chunks SET sensitivity=? WHERE id=?", (max(body.sensitivity, level), c["id"]))
    recompute_clearance(db, s["project_id"])
    audit(db, user, "source.sensitivity", s["name"], SENS_LABEL[body.sensitivity], s["project_id"])
    return {"ok": True}


@app.delete("/api/sources/{sid}")
def delete_source(sid: int, user=Depends(require("admin")), db=Depends(get_db)):
    s = db.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
    if not s:
        raise HTTPException(404, "Source not found")
    db.execute("DELETE FROM sources WHERE id=?", (sid,))
    db.execute("DELETE FROM claims WHERE project_id=? AND id NOT IN (SELECT claim_id FROM claim_evidence)", (s["project_id"],))
    db.execute("DELETE FROM conflicts WHERE project_id=? AND (claim_a NOT IN (SELECT id FROM claims) OR claim_b NOT IN (SELECT id FROM claims))",
               (s["project_id"],))
    audit(db, user, "source.deleted", s["name"], "", s["project_id"])
    return {"ok": True}


# ------------------------------------------------------- reconstruction
@app.post("/api/projects/{pid}/reconstruct")
def run_reconstruct(pid: int, user=Depends(require(*STAFF)), db=Depends(get_db)):
    _project(db, pid)
    try:
        summary = reconstruct(db, pid)
    except IngestError as exc:
        raise HTTPException(422, str(exc))
    audit(db, user, "reconstruction.run", "project", f"{summary['claims']} claims, {summary['conflicts']} conflicts, mode={summary['mode']}", pid)
    return summary


# --------------------------------------------------------------- claims
@app.get("/api/projects/{pid}/claims")
def list_claims(pid: int, user=Depends(require(*STAFF)), db=Depends(get_db)):
    _project(db, pid)
    return load_claims(db, pid, ROLE_CLEARANCE[user["role"]])


class ClaimPatch(BaseModel):
    action: str
    statement: str | None = Field(default=None, max_length=1200)
    owner: str | None = Field(default=None, max_length=80)
    due: str | None = None
    severity: str | None = None


def _claim(db, cid, user):
    c = db.execute("SELECT * FROM claims WHERE id=?", (cid,)).fetchone()
    if not c or c["clearance"] > ROLE_CLEARANCE[user["role"]]:
        raise HTTPException(404, "Claim not found")
    return dict(c)


@app.patch("/api/claims/{cid}")
def patch_claim(cid: int, body: ClaimPatch, user=Depends(require(*REVIEWERS)), db=Depends(get_db)):
    c = _claim(db, cid, user)
    if c["review_status"] == "unsupported" and body.action in ("confirm", "edit"):
        raise HTTPException(409, "The model's quote was not found in the source, so this claim cannot be confirmed. Reject it instead.")
    if body.action == "confirm":
        db.execute("UPDATE claims SET review_status='confirmed', reviewed_by=?, updated_at=? WHERE id=?", (user["id"], now(), cid))
    elif body.action == "reject":
        db.execute("UPDATE claims SET review_status='rejected', reviewed_by=?, updated_at=? WHERE id=?", (user["id"], now(), cid))
    elif body.action == "restore":
        db.execute("UPDATE claims SET review_status='pending', reviewed_by=NULL, updated_at=? WHERE id=?", (now(), cid))
    elif body.action == "edit":
        if body.severity and body.severity not in ("High", "Medium", "Low"):
            raise HTTPException(422, "Severity must be High, Medium or Low")
        if body.due and not __import__("re").match(r"^\d{4}-\d{2}-\d{2}$", body.due):
            raise HTTPException(422, "Due date must be YYYY-MM-DD")
        db.execute(
            "UPDATE claims SET statement=COALESCE(?,statement), owner=?, due=?, severity=COALESCE(?,severity), review_status='edited', "
            "reviewed_by=?, original_statement=COALESCE(original_statement,statement), updated_at=? WHERE id=?",
            (body.statement.strip() if body.statement else None, (body.owner or None), (body.due or None), body.severity, user["id"], now(), cid))
    else:
        raise HTTPException(422, "Unknown action")
    audit(db, user, f"claim.{body.action}", f"{c['type']} #{cid}", c["statement"][:120], c["project_id"])
    return {"ok": True}


class AnswerIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


@app.post("/api/claims/{cid}/answer")
def answer_claim(cid: int, body: AnswerIn, user=Depends(require(*STAFF)), db=Depends(get_db)):
    c = _claim(db, cid, user)
    if c["type"] not in ("gap", "question"):
        raise HTTPException(409, "Only gaps and open questions can be answered")
    db.execute("UPDATE claims SET answer=?, answered_by=?, answered_at=?, updated_at=? WHERE id=?",
               (body.text.strip(), user["id"], now(), now(), cid))
    audit(db, user, "claim.answered", f"{c['type']} #{cid}", body.text[:120], c["project_id"])
    return {"ok": True}


@app.post("/api/projects/{pid}/claims/confirm-supported")
def confirm_supported(pid: int, user=Depends(require(*REVIEWERS)), db=Depends(get_db)):
    claims = load_claims(db, pid, 2, with_evidence=False)
    ids = [c["id"] for c in claims if c["label"] == "supported" and c["type"] != "gap" and c["review_status"] == "pending"]
    for i in ids:
        db.execute("UPDATE claims SET review_status='confirmed', reviewed_by=?, updated_at=? WHERE id=?", (user["id"], now(), i))
    audit(db, user, "claim.bulk_confirm", f"{len(ids)} claims", "Confirmed all supported, non-conflicting claims", pid)
    return {"confirmed": len(ids)}


# ------------------------------------------------------------ conflicts
@app.get("/api/projects/{pid}/conflicts")
def list_conflicts(pid: int, user=Depends(require(*STAFF)), db=Depends(get_db)):
    claims = {c["id"]: c for c in load_claims(db, pid, ROLE_CLEARANCE[user["role"]])}
    out = []
    for r in db.execute("SELECT * FROM conflicts WHERE project_id=? ORDER BY status='open' DESC, id", (pid,)):
        if r["claim_a"] in claims and r["claim_b"] in claims:
            d = dict(r)
            d["a"], d["b"] = claims[r["claim_a"]], claims[r["claim_b"]]
            out.append(d)
    return out


class ResolveIn(BaseModel):
    resolution: str
    note: str | None = Field(default=None, max_length=500)


@app.post("/api/conflicts/{cid}/resolve")
def resolve_conflict(cid: int, body: ResolveIn, user=Depends(require(*REVIEWERS)), db=Depends(get_db)):
    r = db.execute("SELECT * FROM conflicts WHERE id=?", (cid,)).fetchone()
    if not r:
        raise HTTPException(404, "Conflict not found")
    if body.resolution not in ("a", "b", "unresolved"):
        raise HTTPException(422, "Resolution must be a, b or unresolved")
    status = "accepted" if body.resolution == "unresolved" else "resolved"
    if body.resolution in ("a", "b"):
        keep, drop = (r["claim_a"], r["claim_b"]) if body.resolution == "a" else (r["claim_b"], r["claim_a"])
        db.execute("UPDATE claims SET review_status='confirmed', reviewed_by=?, updated_at=? WHERE id=?", (user["id"], now(), keep))
        db.execute("UPDATE claims SET review_status='rejected', reviewed_by=?, updated_at=? WHERE id=?", (user["id"], now(), drop))
    db.execute("UPDATE conflicts SET status=?, resolution=?, note=?, resolved_by=?, resolved_at=? WHERE id=?",
               (status, body.resolution, body.note, user["id"], now(), cid))
    audit(db, user, "conflict.resolved", f"conflict #{cid}", f"{body.resolution}: {body.note or ''}", r["project_id"])
    return {"ok": True}


# ------------------------------------------------------------- timeline
@app.get("/api/projects/{pid}/timeline")
def timeline(pid: int, user=Depends(require(*STAFF)), db=Depends(get_db)):
    claims = load_claims(db, pid, ROLE_CLEARANCE[user["role"]])
    events = []
    for c in claims:
        if c["label"] in ("rejected", "unsupported") or c["type"] in ("owner", "state", "contact"):
            continue
        ev = c["evidence"][0] if c["evidence"] else None
        d = (c.get("event_date") or "")[:10]
        if not d and ev:
            row = db.execute("SELECT doc_date FROM sources WHERE id=?", (ev["source_id"],)).fetchone()
            d = row["doc_date"] if row else None
        if not d:
            continue
        events.append({"date": d, "claim_id": c["id"], "type": c["type"], "text": c["statement"], "label": c["label"],
                       "source": ev["source_name"] if ev else None, "due": c.get("due")})
    events.sort(key=lambda e: (e["date"], e["claim_id"]), reverse=True)
    return events


# -------------------------------------------------------------- versions
class ApproveIn(BaseModel):
    note: str | None = Field(default=None, max_length=500)
    accept_unreviewed: bool = False


@app.get("/api/projects/{pid}/versions")
def list_versions(pid: int, user=Depends(require(*STAFF)), db=Depends(get_db)):
    out = []
    for v in db.execute("SELECT v.*, u.name approved_by_name FROM versions v LEFT JOIN users u ON u.id=v.approved_by "
                        "WHERE project_id=? ORDER BY number DESC", (pid,)):
        d = {k: v[k] for k in ("id", "number", "status", "note", "created_at", "approved_by_name")}
        snap = jload(v["snapshot"], {})
        d["claims"] = len(snap.get("claims", []))
        d["readiness"] = snap.get("readiness", {}).get("score")
        d["shares"] = db.execute("SELECT COUNT(*) n, SUM(acknowledged_at IS NOT NULL) a FROM shares WHERE version_id=?", (v["id"],)).fetchone()
        d["shared_with"] = [dict(r) for r in db.execute(
            "SELECT u.name, s.acknowledged_at FROM shares s JOIN users u ON u.id=s.user_id WHERE s.version_id=?", (v["id"],))]
        d["shares"], d["acknowledged"] = d["shares"]["n"], d["shares"]["a"] or 0
        out.append(d)
    return out


@app.post("/api/projects/{pid}/versions/approve")
def approve(pid: int, body: ApproveIn, user=Depends(require(*REVIEWERS)), db=Depends(get_db)):
    _project(db, pid)
    r = readiness(db, pid)
    if r["open_conflicts"]:
        raise HTTPException(409, f"{r['open_conflicts']} conflicting claim(s) must be resolved, or explicitly accepted as unresolved, before approval.")
    if r["unreviewed"] and not body.accept_unreviewed:
        raise HTTPException(409, f"{r['unreviewed']} claim(s) have not been reviewed. Review them, or approve with the unreviewed claims clearly labelled.")
    snap = build_snapshot(db, pid)
    n = (db.execute("SELECT COALESCE(MAX(number),0) m FROM versions WHERE project_id=?", (pid,)).fetchone()["m"]) + 1
    cur = db.execute("INSERT INTO versions(project_id,number,status,note,created_by,approved_by,created_at,snapshot) VALUES(?,?,?,?,?,?,?,?)",
                     (pid, n, "approved", body.note, user["id"], user["id"], now(), json.dumps(snap)))
    audit(db, user, "handover.approved", f"version {n}", body.note or "", pid)
    return {"id": cur.lastrowid, "number": n}


def _flat(snap):
    return {f"{c['type']}|{norm(c['statement'])}": c for c in snap.get("claims", [])}


@app.get("/api/versions/{vid}/diff")
def diff(vid: int, user=Depends(require(*STAFF)), db=Depends(get_db)):
    v = db.execute("SELECT * FROM versions WHERE id=?", (vid,)).fetchone()
    if not v:
        raise HTTPException(404, "Version not found")
    prev = db.execute("SELECT * FROM versions WHERE project_id=? AND number<? ORDER BY number DESC LIMIT 1", (v["project_id"], v["number"])).fetchone()
    cur_f = _flat(jload(v["snapshot"], {}))
    old_f = _flat(jload(prev["snapshot"], {})) if prev else {}
    brief = lambda c: {"type": c["type"], "statement": c["statement"], "label": c["label"]}
    return {"against": prev["number"] if prev else None,
            "added": [brief(c) for k, c in cur_f.items() if k not in old_f],
            "removed": [brief(c) for k, c in old_f.items() if k not in cur_f],
            "relabelled": [{**brief(c), "was": old_f[k]["label"]} for k, c in cur_f.items() if k in old_f and old_f[k]["label"] != c["label"]]}


class ShareIn(BaseModel):
    user_ids: list[int]


@app.get("/api/users")
def users(user=Depends(require(*REVIEWERS)), db=Depends(get_db)):
    return [public_user(dict(r)) for r in db.execute("SELECT * FROM users ORDER BY id")]


@app.post("/api/versions/{vid}/share")
def share(vid: int, body: ShareIn, user=Depends(require(*REVIEWERS)), db=Depends(get_db)):
    v = db.execute("SELECT * FROM versions WHERE id=?", (vid,)).fetchone()
    if not v:
        raise HTTPException(404, "Version not found")
    names = []
    for uid in body.user_ids:
        u = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not u or not u["role"].startswith("incoming"):
            raise HTTPException(422, "Handovers can only be shared with incoming members")
        db.execute("INSERT OR IGNORE INTO shares(version_id,user_id,shared_by,shared_at) VALUES(?,?,?,?)", (vid, uid, user["id"], now()))
        names.append(u["name"])
    audit(db, user, "handover.shared", f"version {v['number']}", ", ".join(names), v["project_id"])
    return {"shared": names}


def _can_view(db, user, vid):
    v = db.execute("SELECT v.*, p.name pname FROM versions v JOIN projects p ON p.id=v.project_id WHERE v.id=?", (vid,)).fetchone()
    if not v:
        raise HTTPException(404, "Handover not found")
    if user["role"] in STAFF:
        return dict(v), None
    sh = db.execute("SELECT * FROM shares WHERE version_id=? AND user_id=?", (vid, user["id"])).fetchone()
    if not sh:
        raise HTTPException(404, "Handover not found")
    return dict(v), dict(sh)


@app.get("/api/my/handovers")
def my_handovers(user=Depends(current_user), db=Depends(get_db)):
    if user["role"] in STAFF:
        q = db.execute("SELECT v.id,v.number,v.created_at,p.name project, NULL shared_at, NULL acknowledged_at FROM versions v "
                       "JOIN projects p ON p.id=v.project_id ORDER BY v.id DESC")
    else:
        q = db.execute("SELECT v.id,v.number,v.created_at,p.name project, s.shared_at, s.acknowledged_at FROM shares s "
                       "JOIN versions v ON v.id=s.version_id JOIN projects p ON p.id=v.project_id WHERE s.user_id=? ORDER BY v.id DESC", (user["id"],))
    return [dict(r) for r in q]


@app.get("/api/versions/{vid}/view")
def view_version(vid: int, preview_as: str | None = None, user=Depends(current_user), db=Depends(get_db)):
    v, sh = _can_view(db, user, vid)
    clr = _clearance(user, db, vid)
    if preview_as:
        if user["role"] not in REVIEWERS:
            raise HTTPException(403, "Only approvers and admins can preview other roles")
        if preview_as not in ROLE_CLEARANCE:
            raise HTTPException(422, "Unknown role")
        clr = ROLE_CLEARANCE[preview_as]
    view = view_snapshot(jload(v["snapshot"], {}), clr)
    approver = (db.execute("SELECT name FROM users WHERE id=?", (v["approved_by"],)).fetchone() or {"name": None})["name"]
    req = db.execute("SELECT status FROM access_requests WHERE version_id=? AND user_id=? ORDER BY id DESC LIMIT 1", (vid, user["id"])).fetchone()
    view.update({"version": {"id": vid, "number": v["number"], "note": v["note"], "approved_by": approver, "created_at": v["created_at"]},
                 "acknowledged_at": sh["acknowledged_at"] if sh else None, "can_acknowledge": bool(sh),
                 "access_request": req["status"] if req else None, "role": preview_as or user["role"],
                 "role_label": ROLE_LABEL[preview_as or user["role"]], "preview": bool(preview_as)})
    if sh and not sh["acknowledged_at"]:
        pass
    audit(db, user, "handover.previewed" if preview_as else "handover.viewed", f"version {v['number']}",
          f"as {ROLE_LABEL[preview_as]}" if preview_as else f"clearance {SENS_LABEL[clr]}", v["project_id"])
    return view


@app.get("/api/versions/{vid}/export")
def export(vid: int, format: str = Query("md"), user=Depends(current_user), db=Depends(get_db)):
    v, _ = _can_view(db, user, vid)
    view = view_snapshot(jload(v["snapshot"], {}), _clearance(user, db, vid))
    approver = (db.execute("SELECT name FROM users WHERE id=?", (v["approved_by"],)).fetchone() or {"name": None})["name"]
    audit(db, user, "handover.exported", f"version {v['number']}", format, v["project_id"])
    if format == "json":
        slim = {k: view[k] for k in ("project", "generated_at", "claims", "hidden", "conflicts", "plan", "clearance_label")}
        for c in slim["claims"]:
            for e in c["evidence"]:
                e.pop("context", None)
        return JSONResponse(slim, headers={"Content-Disposition": f'attachment; filename="handover-v{v["number"]}.json"'})
    return PlainTextResponse(to_markdown(view, v["number"], approver), headers={"Content-Disposition": f'attachment; filename="handover-v{v["number"]}.md"'})


@app.post("/api/versions/{vid}/acknowledge")
def acknowledge(vid: int, user=Depends(current_user), db=Depends(get_db)):
    v, sh = _can_view(db, user, vid)
    if not sh:
        raise HTTPException(403, "Only recipients can acknowledge receipt")
    if not sh["acknowledged_at"]:
        db.execute("UPDATE shares SET acknowledged_at=? WHERE id=?", (now(), sh["id"]))
        audit(db, user, "handover.acknowledged", f"version {v['number']}", "", v["project_id"])
    return {"ok": True}


class AccessReqIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


@app.post("/api/versions/{vid}/access-requests")
def request_access(vid: int, body: AccessReqIn, user=Depends(current_user), db=Depends(get_db)):
    v, sh = _can_view(db, user, vid)
    if not sh:
        raise HTTPException(403, "Only recipients can request access")
    if db.execute("SELECT 1 FROM access_requests WHERE version_id=? AND user_id=? AND status='pending'", (vid, user["id"])).fetchone():
        raise HTTPException(409, "You already have a pending request")
    db.execute("INSERT INTO access_requests(version_id,user_id,reason,created_at) VALUES(?,?,?,?)", (vid, user["id"], body.reason, now()))
    audit(db, user, "access.requested", f"version {v['number']}", body.reason[:120], v["project_id"])
    return {"ok": True}


@app.get("/api/access-requests")
def list_access_requests(user=Depends(require(*REVIEWERS)), db=Depends(get_db)):
    return [dict(r) for r in db.execute(
        "SELECT a.*, u.name user_name, u.role user_role, v.number version_number FROM access_requests a JOIN users u ON u.id=a.user_id "
        "JOIN versions v ON v.id=a.version_id ORDER BY a.status='pending' DESC, a.id DESC")]


class DecideIn(BaseModel):
    approve: bool


@app.post("/api/access-requests/{rid}/decide")
def decide(rid: int, body: DecideIn, user=Depends(require(*REVIEWERS)), db=Depends(get_db)):
    r = db.execute("SELECT a.*, u.clearance ucl, u.name uname FROM access_requests a JOIN users u ON u.id=a.user_id WHERE a.id=?", (rid,)).fetchone()
    if not r or r["status"] != "pending":
        raise HTTPException(404, "Request not found or already decided")
    db.execute("UPDATE access_requests SET status=?, decided_by=?, decided_at=? WHERE id=?",
               ("approved" if body.approve else "denied", user["id"], now(), rid))
    if body.approve:
        db.execute("INSERT OR REPLACE INTO grants(version_id,user_id,clearance) VALUES(?,?,?)", (r["version_id"], r["user_id"], min(2, r["ucl"] + 1)))
    audit(db, user, "access.approved" if body.approve else "access.denied", r["uname"], f"version {r['version_id']}")
    return {"ok": True}


@app.get("/api/audit")
def audit_log(limit: int = 100, user=Depends(require(*STAFF)), db=Depends(get_db)):
    return [dict(r) for r in db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (min(limit, 500),))]


# --------------------------------------------------------------- static
if config.FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=config.FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        f = (config.FRONTEND_DIST / path).resolve()
        if path and f.is_file() and str(f).startswith(str(config.FRONTEND_DIST.resolve())):
            return FileResponse(f)
        return FileResponse(config.FRONTEND_DIST / "index.html")
