"""Ingestion and reconstruction pipelines."""
import hashlib
import re
from collections import Counter

from .analysis import (annotate_values, detect_conflicts, detect_gaps, fingerprint, mark_recurring, merge_duplicates, verify)
from .config import MAX_UPLOAD_BYTES, extractor_mode
from .db import jload, now
from .extract_llm import call_llm, extract_with_llm
from .extract_rules import extract_from_chunk
from .textproc import (chunk_text, decode_bytes, detect_doc_date, detect_kind, redact, sensitivity_level)

import json


class IngestError(ValueError):
    pass


def ingest_source(db, project_id, name, data, uploaded_by=None, sensitivity=0, doc_date=None, kind=None, uri=None):
    if isinstance(data, bytes):
        if len(data) > MAX_UPLOAD_BYTES:
            raise IngestError(f"File is larger than {MAX_UPLOAD_BYTES // 1024 // 1024} MB.")
        try:
            text = decode_bytes(data)
        except ValueError as exc:
            raise IngestError(str(exc))
    else:
        text = data
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip():
        raise IngestError("The file is empty.")
    digest = hashlib.sha256(text.encode()).hexdigest()
    if db.execute("SELECT 1 FROM sources WHERE project_id=? AND content_hash=?", (project_id, digest)).fetchone():
        raise IngestError("This content has already been added to the project.")
    kind = kind or detect_kind(name, text)
    clean, counts = redact(text)
    pieces = chunk_text(kind, name, clean)
    if not pieces:
        raise IngestError("No readable content was found in this file.")
    doc_date = doc_date or detect_doc_date(name, clean)
    if not doc_date and kind == "chat" and pieces and pieces[0].get("ts"):
        doc_date = pieces[0]["ts"][:10]
    cur = db.execute(
        "INSERT INTO sources(project_id,name,kind,uri,uploaded_by,sensitivity,doc_date,redactions,size,content_hash,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (project_id, name, kind, uri, uploaded_by, int(sensitivity), doc_date, json.dumps(counts), len(text), digest, now()))
    sid = cur.lastrowid
    flagged = 0
    for i, p in enumerate(pieces):
        level, flags = sensitivity_level(p["text"])
        eff = max(int(sensitivity), level)
        if eff > int(sensitivity) or flags:
            flagged += 1
        db.execute("INSERT INTO chunks(source_id,idx,text,location,ts,speaker,sensitivity,flags) VALUES(?,?,?,?,?,?,?,?)",
                   (sid, i, p["text"], p["location"], p["ts"], p["speaker"], eff, json.dumps(flags)))
    return {"id": sid, "name": name, "kind": kind, "chunks": len(pieces), "redactions": counts, "flagged_chunks": flagged,
            "doc_date": doc_date}


def collect_people(db, sources, chunks):
    people = {r["name"] for r in db.execute("SELECT name FROM users")}
    for ch in chunks:
        src = sources[ch["source_id"]]
        if ch.get("speaker"):
            people.add(ch["speaker"])
        if src["kind"] == "task":
            m = re.search(r"owner: ([^|]+)", ch["text"]) or re.search(r"assignee: ([^|]+)", ch["text"])
            if m:
                people.add(m.group(1).strip())
        for m in re.finditer(r"(?im)^attendees\s*:\s*(.+)$", ch["text"]):
            for n in m.group(1).split(","):
                people.add(n.strip())
    return {p for p in people if re.match(r"^(?:Dr\.?\s+|Mr\.?\s+|Ms\.?\s+|Prof\.?\s+)?[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2}$", p or "")}


def reconstruct(db, project_id, llm=None):
    sources = {r["id"]: dict(r) for r in db.execute("SELECT * FROM sources WHERE project_id=?", (project_id,))}
    chunks = [dict(r) for r in db.execute(
        "SELECT c.* FROM chunks c JOIN sources s ON s.id=c.source_id WHERE s.project_id=? ORDER BY c.source_id,c.idx", (project_id,))]
    if not chunks:
        raise IngestError("Add at least one source before reconstructing.")
    chunk_text_by_id = {c["id"]: c["text"] for c in chunks}
    chunk_by_id = {c["id"]: c for c in chunks}
    people = collect_people(db, sources, chunks)
    mode = extractor_mode()

    cands = []
    for ch in chunks:
        for cand in extract_from_chunk(ch, sources[ch["source_id"]], people):
            cand.update(chunk_id=ch["id"], origin="rules", extractor="rules")
            cands.append(cand)
    llm_error, llm_count = None, 0
    if mode == "llm":
        lc, llm_error = extract_with_llm([{"id": c["id"], "text": c["text"], "speaker": c["speaker"]} for c in chunks], llm or call_llm)
        for cand in lc:
            cand.update(origin="llm", extractor="llm")
        cands += lc
        llm_count = len(lc)

    claims, unsupported = [], []
    for cand in cands:
        ev = verify(cand, chunk_text_by_id, chunks)
        c = {**cand, "review_status": "pending", "recurring": 0}
        if ev is None:
            c["review_status"] = "unsupported"
            c["evidence"] = [{"chunk_id": cand["chunk_id"], "quote": cand["quote"][:300], "start": 0, "end": 0}]
            unsupported.append(c)
            continue
        c["evidence"] = [ev]
        c["quote"] = ev["quote"]
        annotate_values(c)
        claims.append(c)
    claims = merge_duplicates(claims)
    for c in claims:
        c["fingerprint"] = fingerprint(c["type"], c["evidence"][0]["quote"])
    for c in unsupported:
        c.update(vclass=None, vvalue=None, fingerprint=fingerprint("unsupported-" + c["type"], c["quote"]))
    mark_recurring(claims)
    claims += detect_gaps(claims, chunk_text_by_id, chunks, sources)
    claims += unsupported

    def cinfo_for(chunk_id):
        ch = chunk_by_id[chunk_id]
        s = sources[ch["source_id"]]
        return {"source_name": s["name"], "date": (ch.get("ts") or s.get("doc_date") or s["created_at"])[:10]}
    cinfo = {cid: cinfo_for(cid) for cid in chunk_by_id}
    conflicts = detect_conflicts(claims, cinfo)

    # preserve human decisions across re-runs
    old = {r["fingerprint"]: dict(r) for r in db.execute("SELECT * FROM claims WHERE project_id=?", (project_id,))}
    old_conf = {}
    for r in db.execute("SELECT * FROM conflicts WHERE project_id=?", (project_id,)):
        if r["status"] != "open" and r["fp_a"] and r["fp_b"]:
            old_conf[frozenset((r["fp_a"], r["fp_b"]))] = dict(r)
    db.execute("DELETE FROM conflicts WHERE project_id=?", (project_id,))
    db.execute("DELETE FROM claims WHERE project_id=?", (project_id,))

    ids = []
    for c in claims:
        clearance = max(chunk_by_id[e["chunk_id"]]["sensitivity"] for e in c["evidence"])
        prev = old.get(c["fingerprint"])
        status, reviewed_by = c["review_status"], None
        statement, owner, due, original = c["statement"], c.get("owner"), c.get("due"), None
        answer = answered_by = answered_at = None
        if prev:
            if prev["review_status"] in ("confirmed", "edited", "rejected") and c["review_status"] != "unsupported":
                status, reviewed_by = prev["review_status"], prev["reviewed_by"]
                if prev["review_status"] == "edited":
                    statement, owner, due, original = prev["statement"], prev["owner"], prev["due"], prev["original_statement"]
            answer, answered_by, answered_at = prev["answer"], prev["answered_by"], prev["answered_at"]
        cur = db.execute(
            "INSERT INTO claims(project_id,type,subtype,statement,owner,due,severity,origin,extractor,review_status,reviewed_by,clearance,"
            "event_date,fingerprint,recurring,vclass,vvalue,answer,answered_by,answered_at,original_statement,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, c["type"], c.get("subtype"), statement, owner, due, c.get("severity"), c["origin"], c.get("extractor"),
             status, reviewed_by, clearance, c.get("event_date"), c["fingerprint"], c.get("recurring", 0), c.get("vclass"),
             c.get("vvalue"), answer, answered_by, answered_at, original, now(), now()))
        cid = cur.lastrowid
        ids.append(cid)
        for e in c["evidence"]:
            db.execute("INSERT INTO claim_evidence(claim_id,chunk_id,quote,start,end) VALUES(?,?,?,?,?)",
                       (cid, e["chunk_id"], e["quote"], e["start"], e["end"]))
    n_conf = 0
    for i, j, cls, reason in conflicts:
        fa, fb = claims[i]["fingerprint"], claims[j]["fingerprint"]
        prev = old_conf.get(frozenset((fa, fb)))
        db.execute(
            "INSERT INTO conflicts(project_id,claim_a,claim_b,vclass,reason,status,resolution,note,resolved_by,resolved_at,fp_a,fp_b) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (project_id, ids[i], ids[j], cls, reason, prev["status"] if prev else "open", prev["resolution"] if prev else None,
             prev["note"] if prev else None, prev["resolved_by"] if prev else None, prev["resolved_at"] if prev else None, fa, fb))
        n_conf += 1
    by_type = Counter(c["type"] for c in claims if c["review_status"] != "unsupported")
    return {"mode": mode, "claims": sum(by_type.values()), "by_type": dict(by_type), "unsupported": len(unsupported),
            "conflicts": n_conf, "sources": len(sources), "chunks": len(chunks), "llm_candidates": llm_count, "llm_error": llm_error}
