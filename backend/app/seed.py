"""Synthetic demo workspace: CampusConnect, a student-club events app whose backend lead is graduating.
All people, accounts and data are fictional."""
from .config import SEED_DATA_DIR
from .db import audit, now
from .pipeline import ingest_source, reconstruct
from .security import ROLE_CLEARANCE, hash_password

DEMO_PASSWORD = "continuity123"
USERS = [
    ("Sanjay Kulkarni", "sanjay@campusconnect.example", "admin", "Project admin"),
    ("Meera Iyer", "meera@campusconnect.example", "approver", "Faculty coordinator (approver)"),
    ("Priya Nair", "priya@campusconnect.example", "departing", "Backend lead, graduating"),
    ("Rahul Verma", "rahul@campusconnect.example", "incoming_peer", "Incoming backend lead"),
    ("Nisha Rao", "nisha@campusconnect.example", "incoming_restricted", "Incoming volunteer"),
]
# (file, display name, sensitivity, doc_date)
SOURCES = [
    ("README.md", "campusconnect/README.md", 0, "2026-08-20"),
    ("architecture.md", "campusconnect/docs/architecture.md", 0, "2026-09-02"),
    ("meeting-notes-2026-09-12.md", "Core team meeting 12 Sep 2026.md", 1, "2026-09-12"),
    ("meeting-notes-2026-10-10.md", "Core team meeting 10 Oct 2026.md", 1, "2026-10-10"),
    ("tasks.csv", "Task board export 28 Oct 2026.csv", 1, "2026-10-28"),
    ("team-chat-export.txt", "Core team chat export (Sep to Oct 2026).txt", 1, None),
]


def seed(db):
    if db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]:
        return
    pw = hash_password(DEMO_PASSWORD)
    ids = {}
    for name, email, role, title in USERS:
        cur = db.execute("INSERT INTO users(name,email,password_hash,role,title,clearance) VALUES(?,?,?,?,?,?)",
                         (name, email, pw, role, title, ROLE_CLEARANCE[role]))
        ids[role] = cur.lastrowid
    cur = db.execute("INSERT INTO projects(name,description,workspace,departing_user_id,created_at) VALUES(?,?,?,?,?)",
                     ("CampusConnect", "Events and club-membership app for the GPCET technical clubs. Backend lead is graduating in November.",
                      "GPCET Tech Clubs", ids["departing"], now()))
    pid = cur.lastrowid
    admin = {"id": ids["admin"], "name": "Sanjay Kulkarni"}
    for fname, display, sens, ddate in SOURCES:
        data = (SEED_DATA_DIR / fname).read_bytes()
        ingest_source(db, pid, display, data, uploaded_by=ids["departing"], sensitivity=sens, doc_date=ddate)
    audit(db, admin, "workspace.seeded", "CampusConnect", "Synthetic demo data loaded", pid)
    summary = reconstruct(db, pid)
    audit(db, None, "reconstruction.run", "CampusConnect", f"{summary['claims']} claims, {summary['conflicts']} conflicts", pid)
