"""
BloxCasino backend pytest suite.
Covers: auth (register/login/me), games (crash/coinflip/roulette/mines), bets, admin RBAC + rigging.
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hardcore-zhukovsky-7.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@bloxcasino.com"
ADMIN_PASSWORD = "admin123"


# ---------------- Fixtures ----------------
@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


def _register(s, suffix=None):
    suffix = suffix or uuid.uuid4().hex[:8]
    payload = {
        "email": f"TEST_{suffix}@test.com",
        "password": "pass1234",
        "username": f"TEST_{suffix}",
    }
    r = s.post(f"{API}/auth/register", json=payload)
    assert r.status_code == 200, r.text
    return r.json(), payload


@pytest.fixture(scope="session")
def admin_token(s):
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture
def user_ctx(s):
    data, payload = _register(s)
    return {"token": data["token"], "user": data["user"], "payload": payload}


def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ---------------- Health / Root ----------------
def test_api_root(s):
    r = s.get(f"{API}/")
    assert r.status_code == 200
    assert "BloxCasino" in r.json().get("message", "")


# ---------------- Auth ----------------
class TestAuth:
    def test_register_starting_balance(self, s):
        data, _ = _register(s)
        assert data["user"]["balance"] == 1000.0
        assert data["user"]["role"] == "user"
        assert data["user"]["rigging"] == "none"
        assert isinstance(data["token"], str) and len(data["token"]) > 20

    def test_register_duplicate_email(self, s):
        data, payload = _register(s)
        r = s.post(f"{API}/auth/register", json=payload)
        assert r.status_code == 400

    def test_login_valid(self, s):
        _, payload = _register(s)
        r = s.post(f"{API}/auth/login", json={"email": payload["email"], "password": payload["password"]})
        assert r.status_code == 200
        assert "token" in r.json()

    def test_login_invalid(self, s):
        r = s.post(f"{API}/auth/login", json={"email": "nope@nope.com", "password": "wrong"})
        assert r.status_code == 401

    def test_me_with_bearer(self, s, user_ctx):
        r = s.get(f"{API}/auth/me", headers=auth_headers(user_ctx["token"]))
        assert r.status_code == 200
        assert r.json()["email"] == user_ctx["user"]["email"]

    def test_me_without_token(self, s):
        # Use bare requests to avoid session-level cookies
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401


# ---------------- Games ----------------
class TestCrash:
    def test_play_and_balance_changes(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/crash/play", headers=h, json={"amount": 10, "auto_cashout": 2.0})
        assert r.status_code == 200, r.text
        bet = r.json()
        assert bet["game"] == "crash"
        assert bet["amount"] == 10
        assert "crash_point" in bet["details"]
        # Verify balance updated via /me
        me = s.get(f"{API}/auth/me", headers=h).json()
        expected = 1000 - 10 + (10 * 2.0 if bet["result"] == "win" else 0)
        assert abs(me["balance"] - expected) < 0.01

    def test_insufficient_balance(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/crash/play", headers=h, json={"amount": 9999, "auto_cashout": 2})
        assert r.status_code == 400


class TestCoinflip:
    def test_payout_195(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        # Play multiple times to ensure at least 1 win and only one deduction
        for _ in range(5):
            r = s.post(f"{API}/games/coinflip/play", headers=h, json={"amount": 10, "side": "heads"})
            assert r.status_code == 200
            b = r.json()
            if b["result"] == "win":
                assert b["multiplier"] == 1.95
                assert abs(b["payout"] - 19.5) < 0.01

    def test_only_single_deduction(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        start = s.get(f"{API}/auth/me", headers=h).json()["balance"]
        r = s.post(f"{API}/games/coinflip/play", headers=h, json={"amount": 100, "side": "heads"})
        assert r.status_code == 200
        b = r.json()
        end = s.get(f"{API}/auth/me", headers=h).json()["balance"]
        if b["result"] == "win":
            assert abs(end - (start - 100 + 195)) < 0.01
        else:
            assert abs(end - (start - 100)) < 0.01


class TestRoulette:
    def test_red_black_multiplier(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        seen = set()
        for _ in range(15):
            r = s.post(f"{API}/games/roulette/play", headers=h, json={"amount": 1, "choice": "red"})
            assert r.status_code == 200
            b = r.json()
            seen.add(b["result"])
            if b["result"] == "win":
                assert b["multiplier"] == 2.0

    def test_green_multiplier(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        for _ in range(30):
            r = s.post(f"{API}/games/roulette/play", headers=h, json={"amount": 1, "choice": "green"})
            assert r.status_code == 200
            b = r.json()
            if b["result"] == "win":
                assert b["multiplier"] == 14.0
                break


class TestMines:
    def test_basic_play(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/mines/play", headers=h, json={"amount": 10, "mines": 3, "picks": [0, 1, 2]})
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["game"] == "mines"
        if b["result"] == "win":
            # 0.95 * C(25,3)/C(22,3) ≈ 1.39
            assert b["multiplier"] > 1.0

    def test_invalid_too_many_picks(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/mines/play", headers=h,
                   json={"amount": 10, "mines": 24, "picks": list(range(5))})
        assert r.status_code == 400


# ---------------- Bets ----------------
class TestBets:
    def test_bets_me(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        s.post(f"{API}/games/coinflip/play", headers=h, json={"amount": 5, "side": "heads"})
        r = s.get(f"{API}/bets/me", headers=h)
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list) and len(items) >= 1
        assert items[0]["user_id"] == user_ctx["user"]["id"]

    def test_feed_public(self, s):
        r = s.get(f"{API}/bets/feed")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------- Admin ----------------
class TestAdmin:
    def test_non_admin_403(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        r = s.get(f"{API}/admin/users", headers=h)
        assert r.status_code == 403

    def test_admin_list_users(self, s, admin_token):
        r = s.get(f"{API}/admin/users", headers=auth_headers(admin_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_set_balance(self, s, admin_token, user_ctx):
        uid = user_ctx["user"]["id"]
        r = s.patch(f"{API}/admin/users/{uid}/balance",
                    headers=auth_headers(admin_token), json={"mode": "set", "amount": 500})
        assert r.status_code == 200
        assert r.json()["balance"] == 500.0
        # Verify via /me
        me = s.get(f"{API}/auth/me", headers=auth_headers(user_ctx["token"])).json()
        assert me["balance"] == 500.0

    def test_admin_add_balance(self, s, admin_token, user_ctx):
        uid = user_ctx["user"]["id"]
        s.patch(f"{API}/admin/users/{uid}/balance",
                headers=auth_headers(admin_token), json={"mode": "set", "amount": 100})
        r = s.patch(f"{API}/admin/users/{uid}/balance",
                    headers=auth_headers(admin_token), json={"mode": "add", "amount": 50})
        assert r.status_code == 200
        assert abs(r.json()["balance"] - 150.0) < 0.01

    def test_admin_set_rigging_win_statistical(self, s, admin_token, user_ctx):
        """Rig=win should give >65% wins on coinflip over 30 plays."""
        uid = user_ctx["user"]["id"]
        # Give huge balance
        s.patch(f"{API}/admin/users/{uid}/balance",
                headers=auth_headers(admin_token), json={"mode": "set", "amount": 100000})
        r = s.patch(f"{API}/admin/users/{uid}/rigging",
                    headers=auth_headers(admin_token), json={"rigging": "win"})
        assert r.status_code == 200
        assert r.json()["rigging"] == "win"

        h = auth_headers(user_ctx["token"])
        wins = 0
        n = 30
        for _ in range(n):
            b = s.post(f"{API}/games/coinflip/play", headers=h, json={"amount": 1, "side": "heads"}).json()
            if b["result"] == "win":
                wins += 1
        assert wins / n > 0.65, f"rig=win only produced {wins}/{n}"

    def test_admin_set_rigging_lose_statistical(self, s, admin_token, user_ctx):
        uid = user_ctx["user"]["id"]
        s.patch(f"{API}/admin/users/{uid}/balance",
                headers=auth_headers(admin_token), json={"mode": "set", "amount": 100000})
        s.patch(f"{API}/admin/users/{uid}/rigging",
                headers=auth_headers(admin_token), json={"rigging": "lose"})
        h = auth_headers(user_ctx["token"])
        wins = 0
        n = 30
        for _ in range(n):
            b = s.post(f"{API}/games/coinflip/play", headers=h, json={"amount": 1, "side": "heads"}).json()
            if b["result"] == "win":
                wins += 1
        assert wins / n < 0.35, f"rig=lose still produced {wins}/{n} wins"

    def test_admin_bets_and_stats(self, s, admin_token):
        r1 = s.get(f"{API}/admin/bets", headers=auth_headers(admin_token))
        assert r1.status_code == 200
        r2 = s.get(f"{API}/admin/stats", headers=auth_headers(admin_token))
        assert r2.status_code == 200
        st = r2.json()
        for k in ("total_users", "total_bets", "total_wagered", "total_paid_out", "house_profit"):
            assert k in st
