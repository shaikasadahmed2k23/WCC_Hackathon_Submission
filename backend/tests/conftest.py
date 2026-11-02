import os
import sys
import tempfile

import pytest

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_PATH"] = os.path.join(_tmp, "test.db")
os.environ["FRONTEND_DIST"] = os.path.join(_tmp, "nodist")
os.environ["EXTRACTOR"] = "rules"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PW = "continuity123"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def login(client, who):
    r = client.post("/api/auth/login", json={"email": f"{who}@campusconnect.example", "password": PW})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


@pytest.fixture(scope="module")
def H(client):
    return {w: login(client, w) for w in ("sanjay", "meera", "priya", "rahul", "nisha")}
