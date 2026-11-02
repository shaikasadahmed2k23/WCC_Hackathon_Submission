"""Authentication and role checks. Authorisation is enforced here on the server."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException

from .config import SESSION_TTL_HOURS
from .db import get_db, now

ROLE_CLEARANCE = {"admin": 2, "approver": 2, "departing": 2, "incoming_peer": 1, "incoming_restricted": 0}
ROLE_LABEL = {
    "admin": "Project admin",
    "approver": "Approver",
    "departing": "Departing member",
    "incoming_peer": "Incoming (peer)",
    "incoming_restricted": "Incoming (restricted)",
}
STAFF = ("admin", "approver", "departing")
REVIEWERS = ("admin", "approver")
SENS_LABEL = {0: "General", 1: "Internal", 2: "Confidential"}


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return salt.hex() + "$" + digest.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 120_000)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def create_session(db, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO sessions(token,user_id,created_at) VALUES(?,?,?)", (token, user_id, now()))
    return token


def current_user(authorization: str = Header(default=""), db=Depends(get_db)):
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Not signed in")
    token = authorization[7:].strip()
    row = db.execute(
        "SELECT u.*, s.created_at AS session_created FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?",
        (token,),
    ).fetchone()
    if not row:
        raise HTTPException(401, "Session expired. Please sign in again.")
    created = datetime.strptime(row["session_created"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created > timedelta(hours=SESSION_TTL_HOURS):
        db.execute("DELETE FROM sessions WHERE token=?", (token,))
        db.commit()
        raise HTTPException(401, "Session expired. Please sign in again.")
    user = dict(row)
    user.pop("password_hash", None)
    user["token"] = token
    return user


def require(*roles):
    def dep(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(403, "Your role does not allow this action")
        return user
    return dep
