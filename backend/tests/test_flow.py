import json
import sqlite3

from app import config
from app.extract_llm import extract_with_llm
from app.pipeline import reconstruct
from app.db import connect

CONF_WORDS = ["40,000", "Camp#us2026"]


def claims(client, h, pid=1):
    r = client.get(f"/api/projects/{pid}/claims", headers=h)
    assert r.status_code == 200
    return r.json()


def test_auth(client, H):
    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/auth/login", json={"email": "meera@campusconnect.example", "password": "nope"}).status_code == 401
    assert client.get("/api/me", headers=H["meera"]).json()["role"] == "approver"


def test_seed_reconstruction(client, H):
    cs = claims(client, H["meera"])
    types = {c["type"] for c in cs}
    assert {"decision", "risk", "action", "gap", "question", "dependency", "owner", "contact"} <= types
    conf = client.get("/api/projects/1/conflicts", headers=H["meera"]).json()
    assert {c["vclass"] for c in conf} == {"region", "deadline"}
    # every supported claim has a quote that really exists in its source chunk
    for c in cs:
        if c["label"] in ("supported",):
            ev = c["evidence"][0]
            ctx = [x for x in ev["context"] if x["hl"]][0]
            assert ev["quote"].lower().split()[0] in ctx["text"].lower()
    assert any(c["recurring"] for c in cs if c["type"] == "risk")


def test_secret_is_never_stored(client):
    raw = open(config.DATABASE_PATH, "rb").read()
    for ext in ("-wal",):
        try:
            raw += open(config.DATABASE_PATH + ext, "rb").read()
        except FileNotFoundError:
            pass
    assert b"Camp#us2026" not in raw


def test_role_permissions_on_staff_endpoints(client, H):
    for who in ("rahul", "nisha"):
        assert client.get("/api/projects/1/claims", headers=H[who]).status_code == 403
        assert client.get("/api/projects/1/sources", headers=H[who]).status_code == 403
        assert client.post("/api/projects/1/reconstruct", headers=H[who]).status_code == 403
        assert client.patch("/api/claims/1", json={"action": "confirm"}, headers=H[who]).status_code == 403
    assert client.patch("/api/claims/1", json={"action": "confirm"}, headers=H["priya"]).status_code == 403  # departing cannot approve claims
    assert client.get("/api/users", headers=H["priya"]).status_code == 403


def test_approval_gates(client, H):
    r = client.post("/api/projects/1/versions/approve", json={}, headers=H["meera"])
    assert r.status_code == 409 and "conflicting" in r.json()["detail"]
    for c in client.get("/api/projects/1/conflicts", headers=H["meera"]).json():
        res = client.post(f"/api/conflicts/{c['id']}/resolve", json={"resolution": "b" if c["vclass"] == "region" else "unresolved",
                                                                       "note": "test"}, headers=H["meera"])
        assert res.status_code == 200
    r = client.post("/api/projects/1/versions/approve", json={}, headers=H["meera"])
    assert r.status_code == 409 and "not been reviewed" in r.json()["detail"]
    assert client.post("/api/projects/1/claims/confirm-supported", headers=H["meera"]).json()["confirmed"] > 5


def test_edit_gap_answer_and_approve(client, H):
    cs = claims(client, H["meera"])
    gap = next(c for c in cs if c["type"] == "gap" and c["subtype"] == "missing_owner" and "domain" in c["statement"])
    assert gap["label"] == "missing"
    r = client.post(f"/api/claims/{gap['id']}/answer", json={"text": "Rahul Verma will renew it; registrar login is in the vault."}, headers=H["priya"])
    assert r.status_code == 200
    act = next(c for c in cs if c["type"] == "action" and "domain" in c["statement"].lower())
    r = client.patch(f"/api/claims/{act['id']}", json={"action": "edit", "owner": "Rahul Verma", "due": "2026-11-18"}, headers=H["meera"])
    assert r.status_code == 200
    r = client.post("/api/projects/1/versions/approve", json={"note": "Round 2 test", "accept_unreviewed": True}, headers=H["meera"])
    assert r.status_code == 200, r.text
    vid = r.json()["id"]
    users = {u["email"].split("@")[0]: u["id"] for u in client.get("/api/users", headers=H["meera"]).json()}
    r = client.post(f"/api/versions/{vid}/share", json={"user_ids": [users["rahul"], users["nisha"]]}, headers=H["meera"])
    assert r.status_code == 200
    assert client.post(f"/api/versions/{vid}/share", json={"user_ids": [users["priya"]]}, headers=H["meera"]).status_code == 422


def test_claim_level_permissions_no_leak(client, H):
    vid = client.get("/api/my/handovers", headers=H["meera"]).json()[0]["id"]
    meera = client.get(f"/api/versions/{vid}/view", headers=H["meera"]).json()
    rahul = client.get(f"/api/versions/{vid}/view", headers=H["rahul"]).json()
    nisha = client.get(f"/api/versions/{vid}/view", headers=H["nisha"]).json()
    assert meera["hidden"]["total"] == 0
    assert len(nisha["claims"]) < len(rahul["claims"]) < len(meera["claims"])
    assert nisha["hidden"]["total"] > 0 and rahul["hidden"]["total"] > 0
    m, r_, n = (json.dumps(x) for x in (meera, rahul, nisha))
    assert "40,000" in m
    for w in CONF_WORDS:
        assert w not in r_ and w not in n
    assert "anita.sharma@razorpay.example" in r_ and "anita.sharma@razorpay.example" not in n
    assert "REDACTED" not in n or "REDACTED:password" not in n
    # exports are filtered with the same rules
    exp = client.get(f"/api/versions/{vid}/export?format=md", headers=H["nisha"]).text
    assert "40,000" not in exp and "anita.sharma" not in exp
    exp_j = client.get(f"/api/versions/{vid}/export?format=json", headers=H["rahul"]).text
    assert "40,000" not in exp_j
    # unshared users and unknown versions look identical
    assert client.get("/api/versions/999/view", headers=H["rahul"]).status_code == 404


def test_access_request_flow(client, H):
    vid = client.get("/api/my/handovers", headers=H["meera"]).json()[0]["id"]
    before = len(client.get(f"/api/versions/{vid}/view", headers=H["nisha"]).json()["claims"])
    assert client.post(f"/api/versions/{vid}/access-requests", json={"reason": "I need the contact list for the fest"}, headers=H["nisha"]).status_code == 200
    reqs = client.get("/api/access-requests", headers=H["meera"]).json()
    assert reqs[0]["status"] == "pending"
    assert client.post(f"/api/access-requests/{reqs[0]['id']}/decide", json={"approve": True}, headers=H["meera"]).status_code == 200
    after = client.get(f"/api/versions/{vid}/view", headers=H["nisha"]).json()
    assert len(after["claims"]) > before
    assert "40,000" not in json.dumps(after)  # internal grant never reaches confidential


def test_preview_as_role(client, H):
    vid = client.get("/api/my/handovers", headers=H["meera"]).json()[0]["id"]
    p = client.get(f"/api/versions/{vid}/view?preview_as=incoming_restricted", headers=H["meera"]).json()
    assert p["preview"] and p["hidden"]["total"] > 0 and "40,000" not in json.dumps(p)
    assert client.get(f"/api/versions/{vid}/view?preview_as=admin", headers=H["rahul"]).status_code == 403


def test_acknowledge(client, H):
    vid = client.get("/api/my/handovers", headers=H["rahul"]).json()[0]["id"]
    assert client.post(f"/api/versions/{vid}/acknowledge", headers=H["rahul"]).status_code == 200
    assert client.get(f"/api/versions/{vid}/view", headers=H["rahul"]).json()["acknowledged_at"]
    assert client.post(f"/api/versions/{vid}/acknowledge", headers=H["meera"]).status_code == 403


def test_review_survives_rerun(client, H):
    before = {c["statement"]: c["label"] for c in claims(client, H["meera"]) if c["label"] == "verified"}
    assert before
    assert client.post("/api/projects/1/reconstruct", headers=H["meera"]).status_code == 200
    after = {c["statement"]: c["label"] for c in claims(client, H["meera"]) if c["label"] == "verified"}
    assert set(before) <= set(after)
    edited = [c for c in claims(client, H["meera"]) if c["review_status"] == "edited"]
    assert edited and edited[0]["owner"] == "Rahul Verma"


def test_upload_validation_and_injection(client, H):
    assert client.post("/api/projects/1/sources/upload", files={"file": ("x.bin", b"\x00\x01\x02" * 50)}, headers=H["priya"]).status_code == 422
    assert client.post("/api/projects/1/sources/upload", files={"file": ("e.txt", b"   ")}, headers=H["priya"]).status_code == 422
    inj = open("../sample_uploads/handover-call-injection-test.txt", "rb").read()
    r = client.post("/api/projects/1/sources/upload", files={"file": ("injection.txt", inj)}, data={"sensitivity": "0"}, headers=H["priya"])
    assert r.status_code == 200
    assert client.post("/api/projects/1/sources/upload", files={"file": ("injection2.txt", inj)}, headers=H["priya"]).status_code == 422  # duplicate
    client.post("/api/projects/1/reconstruct", headers=H["priya"])
    cs = claims(client, H["meera"])
    mine = [c for c in cs if "injection" in " ".join(c["sources"])]
    assert mine and all(c["label"] != "verified" for c in mine)
    assert not any("ignore all previous" in c["statement"].lower() for c in cs)
    assert not any("reveal" in c["statement"].lower() for c in cs)
    assert client.post("/api/projects/1/sources/upload", files={"file": ("n.md", b"Date: 2026-10-30\nDecision: we will rotate the key because it leaked. AKIAABCDEFGHIJKLMNOP is the key.")},
                       headers=H["priya"]).status_code == 200


def test_llm_output_must_be_verified(client):
    """A model that invents a claim, or misquotes the source, cannot produce a supported claim."""
    db = connect()
    chunks = [dict(r) for r in db.execute("SELECT id,text,speaker FROM chunks LIMIT 12")]
    real = chunks[0]
    real_quote = real["text"].split(". ")[0][:80] if len(real["text"]) > 40 else real["text"]

    def fake_llm(msgs):
        return json.dumps({"claims": [
            {"chunk_id": real["id"], "type": "decision", "statement": "Invented decision about Kubernetes", "quote": "We will migrate everything to Kubernetes next week"},
            {"chunk_id": real["id"], "type": "risk", "statement": real_quote, "quote": real_quote, "severity": "High"},
            {"chunk_id": 99999, "type": "risk", "statement": "bad id", "quote": "bad bad bad bad bad bad"},
        ]})
    cands, err = extract_with_llm(chunks, fake_llm)
    assert err is None and len(cands) == 2  # invalid chunk id dropped immediately
    from app.analysis import verify
    ct = {c["id"]: c["text"] for c in chunks}
    assert verify(cands[0], ct, chunks) is None
    assert verify(cands[1], ct, chunks) is not None
    db.close()


def test_audit_and_overview(client, H):
    a = client.get("/api/audit", headers=H["priya"]).json()
    assert any(x["action"] == "handover.approved" for x in a)
    o = client.get("/api/projects/1/overview", headers=H["meera"]).json()
    assert o["sources"] >= 6 and o["readiness"]["score"] >= 0 and o["extractor"] == "rules"


def test_github_import_with_mocked_api(client, H, monkeypatch):
    import base64
    from app import github_import as gh
    from app.github_import import parse_repo
    assert parse_repo("https://github.com/octocat/Hello-World") == ("octocat", "Hello-World")
    assert client.post("/api/projects/1/sources/github", json={"repo": "not a repo"}, headers=H["priya"]).status_code == 422

    def fake_get(path):
        if path.endswith("/readme"):
            return {"content": base64.b64encode(b"# Demo\n\nThe service is deployed on Render in Frankfurt region.").decode()}
        return [{"number": 7, "state": "open", "created_at": "2026-10-20T10:00:00Z", "user": {"login": "dev1"}, "title": "Login fails on mobile",
                 "body": "The refresh token rotation fails intermittently. We must fix this before release."}]
    monkeypatch.setattr(gh, "_get", fake_get)
    r = client.post("/api/projects/1/sources/github", json={"repo": "acme/demo", "sensitivity": 0}, headers=H["priya"])
    assert r.status_code == 200, r.text
    assert len(r.json()["added"]) == 2
