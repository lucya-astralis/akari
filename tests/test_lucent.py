"""The Lucent connector: who may ask, whose ID token counts, who makes the first account."""
import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from akari import accounts, lucent

SECRET = "connector-secret-for-tests-0123456789"
PAIRING = {"issuer": "https://lucent.test", "lucent_url": "https://lucent.test", "tool_id": 6,
           "client_id": "akari-test", "client_secret": "client-secret-for-tests",
           "connector_secret_sha256": hashlib.sha256(SECRET.encode()).hexdigest(),
           "ui_url": "https://akari.test", "base_url": "https://akari.test", "paired_at": 1795000000}


@pytest.fixture()
def paired(tmp_path, monkeypatch):
    f = tmp_path / "lucent.json"
    f.write_text(json.dumps(PAIRING))
    monkeypatch.setattr(lucent, "FILE", f)
    return f


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(lucent.router)
    return TestClient(app)


def bearer(secret=SECRET):
    return {"Authorization": f"Bearer {secret}"}


# ---- who may ask ---------------------------------------------------------------------------
def test_an_unpaired_akari_answers_404(client, tmp_path, monkeypatch):
    monkeypatch.setattr(lucent, "FILE", tmp_path / "none.json")
    assert client.get("/lucent/v1/manifest", headers=bearer()).status_code == 404


@pytest.mark.parametrize("headers", [{}, bearer("wrong"), {"Authorization": SECRET}])
def test_only_the_connector_secret_opens_the_api(client, paired, headers):
    assert client.get("/lucent/v1/manifest", headers=headers).status_code == 401


def test_the_manifest_names_akari_and_its_pages(client, paired):
    m = client.get("/lucent/v1/manifest", headers=bearer()).json()
    assert m["kind"] == "akari" and m["contract"] == 1 and m["ui_url"] == "https://akari.test"
    assert [p["id"] for p in m["pages"]] == ["uebersicht", "konten", "system"]
    assert m["icon"].startswith("<svg") and "class=" not in m["icon"]


# ---- ID tokens -----------------------------------------------------------------------------
def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def token(claims: dict, secret=PAIRING["client_secret"], alg="HS256") -> str:
    head = b64u(json.dumps({"alg": alg, "typ": "JWT"}).encode())
    body = b64u(json.dumps(claims).encode())
    sig = b64u(hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}"


def good(**over):
    now = int(time.time())
    return {"iss": PAIRING["issuer"], "aud": PAIRING["client_id"], "sub": "7", "email": "a@lucent.test",
            "iat": now, "exp": now + 300, "nonce": "n-1", **over}


def test_a_good_id_token_names_its_person():
    assert lucent.verify_id_token(token(good()), PAIRING, "n-1")["sub"] == "7"


@pytest.mark.parametrize("claims, nonce, secret", [
    (good(iss="https://other.test"), "n-1", None),
    (good(aud="someone-else"), "n-1", None),
    (good(exp=int(time.time()) - 3600), "n-1", None),
    (good(iat=int(time.time()) + 3600), "n-1", None),
    (good(), "n-2", None),
    (good(sub=""), "n-1", None),
    (good(), "n-1", "a-guessed-secret"),
])
def test_a_bad_id_token_is_refused(claims, nonce, secret):
    with pytest.raises(lucent.LucentError):
        lucent.verify_id_token(token(claims, secret or PAIRING["client_secret"]), PAIRING, nonce)


def test_only_hs256_is_taken():
    with pytest.raises(lucent.LucentError):
        lucent.verify_id_token(token(good(), alg="none"), PAIRING, "n-1")


# ---- the first account, and the ones after it -------------------------------------------------
NEW = {"values": {"name": "lucya", "fullname": "Lucya", "password": "lang-genug-123"}}


@pytest.fixture()
def made(monkeypatch):
    """accounts without root: create and link are recorded, not done."""
    log = []
    monkeypatch.setattr(accounts, "create", lambda name, full, pw, admin=False: log.append(("create", name, admin))
                        or SimpleNamespace(name=name))
    monkeypatch.setattr(accounts, "set_lucent", lambda name, sub, email=None: log.append(("link", name, sub, email)))
    return log


def test_lucent_makes_the_first_account_and_links_it(client, paired, made, monkeypatch):
    monkeypatch.setattr(accounts, "needs_setup", lambda: True)
    r = client.post("/lucent/v1/pages/konten/do/neu", headers=bearer(),
                    json={**NEW, "by": {"sub": "7", "email": "a@lucent.test", "name": "A"}})
    assert r.status_code == 200, r.text
    assert made == [("create", "lucya", True), ("link", "lucya", "https://lucent.test#7", "a@lucent.test")]


def test_the_first_account_needs_a_person(client, paired, made, monkeypatch):
    monkeypatch.setattr(accounts, "needs_setup", lambda: True)
    r = client.post("/lucent/v1/pages/konten/do/neu", headers=bearer(), json={**NEW, "by": "lucent:a@lucent.test"})
    assert r.status_code == 403 and made == []


def test_after_the_first_only_a_linked_admin_may_write(client, paired, made, monkeypatch):
    monkeypatch.setattr(accounts, "needs_setup", lambda: False)
    monkeypatch.setattr(accounts, "by_lucent", lambda sub: None)
    r = client.post("/lucent/v1/pages/konten/do/neu", headers=bearer(),
                    json={**NEW, "by": {"sub": "7", "email": "a@lucent.test"}})
    assert r.status_code == 403 and made == []
    monkeypatch.setattr(accounts, "by_lucent", lambda sub: SimpleNamespace(name="ada", admin=False))
    r = client.post("/lucent/v1/pages/konten/do/neu", headers=bearer(),
                    json={**NEW, "by": {"sub": "7", "email": "a@lucent.test"}})
    assert r.status_code == 403 and made == []
