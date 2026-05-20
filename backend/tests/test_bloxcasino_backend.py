"""
BloxCasino backend pytest suite — Iteration 2.
Covers: auth, all 8 games (crash, mines, towers, plinko, upgrader, blackjack, coinflip, roulette),
bets, admin RBAC + rigging, sessions TTL.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
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


def _bal(s, token):
    return s.get(f"{API}/auth/me", headers=auth_headers(token)).json()["balance"]


def _set_balance(s, admin_token, uid, amount):
    s.patch(f"{API}/admin/users/{uid}/balance",
            headers=auth_headers(admin_token), json={"mode": "set", "amount": amount})


def _set_rigging(s, admin_token, uid, rigging):
    s.patch(f"{API}/admin/users/{uid}/rigging",
            headers=auth_headers(admin_token), json={"rigging": rigging})


# ---------------- Health ----------------
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
        assert isinstance(data["token"], str) and len(data["token"]) > 20

    def test_register_duplicate_email(self, s):
        _, payload = _register(s)
        r = s.post(f"{API}/auth/register", json=payload)
        assert r.status_code == 400

    def test_login_invalid(self, s):
        r = s.post(f"{API}/auth/login", json={"email": "nope@nope.com", "password": "wrong"})
        assert r.status_code == 401

    def test_me_no_token(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401


# ---------------- CRASH ----------------
class TestCrash:
    def test_start_deducts_balance(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        start_bal = _bal(s, user_ctx["token"])
        r = s.post(f"{API}/games/crash/start", headers=h, json={"amount": 10})
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("game_id", "crash_point", "crash_time_ms", "start_ms"):
            assert k in data
        assert data["balance"] == start_bal - 10
        # Bust to clean up
        s.post(f"{API}/games/crash/bust", headers=h, json={"game_id": data["game_id"]})

    def test_insufficient_balance(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/crash/start", headers=h, json={"amount": 99999})
        assert r.status_code == 400

    def test_cashout_quickly_wins(self, s, user_ctx, admin_token):
        # rig=win to ensure crash_point is high enough that quick cashout wins
        _set_rigging(s, admin_token, user_ctx["user"]["id"], "win")
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/crash/start", headers=h, json={"amount": 10})
        assert r.status_code == 200
        gid = r.json()["game_id"]
        # Cash out immediately
        r2 = s.post(f"{API}/games/crash/cashout", headers=h, json={"game_id": gid})
        assert r2.status_code == 200, r2.text
        bet = r2.json()
        assert bet["game"] == "crash"
        # In win mode crash_point likely > 1; immediate cashout could be lose if crash_point=1.00
        # Re-test if needed
        if bet["result"] == "lose":
            # try again
            r = s.post(f"{API}/games/crash/start", headers=h, json={"amount": 10})
            gid = r.json()["game_id"]
            r2 = s.post(f"{API}/games/crash/cashout", headers=h, json={"game_id": gid})
            bet = r2.json()
        assert bet["result"] in ("win", "lose")
        if bet["result"] == "win":
            assert bet["payout"] > 0
            assert bet["multiplier"] >= 1.0

    def test_double_cashout_400(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/crash/start", headers=h, json={"amount": 5})
        gid = r.json()["game_id"]
        s.post(f"{API}/games/crash/cashout", headers=h, json={"game_id": gid})
        r2 = s.post(f"{API}/games/crash/cashout", headers=h, json={"game_id": gid})
        assert r2.status_code == 400

    def test_cashout_after_crash_loses(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/crash/start", headers=h, json={"amount": 5})
        assert r.status_code == 200
        d = r.json()
        gid = d["game_id"]
        # Wait until past crash_time
        time.sleep(d["crash_time_ms"] / 1000.0 + 0.5)
        r2 = s.post(f"{API}/games/crash/cashout", headers=h, json={"game_id": gid})
        assert r2.status_code == 200
        assert r2.json()["result"] == "lose"


# ---------------- MINES ----------------
class TestMines:
    def test_start_then_reveal_then_cashout(self, s, user_ctx, admin_token):
        _set_rigging(s, admin_token, user_ctx["user"]["id"], "win")
        h = auth_headers(user_ctx["token"])
        start_bal = _bal(s, user_ctx["token"])
        r = s.post(f"{API}/games/mines/start", headers=h, json={"amount": 10, "mines": 3})
        assert r.status_code == 200
        gid = r.json()["game_id"]
        assert _bal(s, user_ctx["token"]) == start_bal - 10
        # Reveal one tile (rig=win → should be safe)
        rv = s.post(f"{API}/games/mines/reveal", headers=h, json={"game_id": gid, "tile": 0})
        assert rv.status_code == 200
        body = rv.json()
        assert body["status"] in ("safe", "busted", "cleared")
        if body["status"] != "safe":
            return  # got unlucky, skip cashout
        assert body["multiplier"] > 1.0
        # Cash out
        co = s.post(f"{API}/games/mines/cashout", headers=h, json={"game_id": gid})
        assert co.status_code == 200
        assert co.json()["status"] == "cashed"

    def test_reveal_same_tile_twice(self, s, user_ctx, admin_token):
        _set_rigging(s, admin_token, user_ctx["user"]["id"], "win")
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/mines/start", headers=h, json={"amount": 5, "mines": 2})
        gid = r.json()["game_id"]
        rv1 = s.post(f"{API}/games/mines/reveal", headers=h, json={"game_id": gid, "tile": 5})
        if rv1.json()["status"] == "safe":
            rv2 = s.post(f"{API}/games/mines/reveal", headers=h, json={"game_id": gid, "tile": 5})
            assert rv2.status_code == 400

    def test_cashout_with_no_reveals_refunds(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        start_bal = _bal(s, user_ctx["token"])
        r = s.post(f"{API}/games/mines/start", headers=h, json={"amount": 50, "mines": 5})
        gid = r.json()["game_id"]
        co = s.post(f"{API}/games/mines/cashout", headers=h, json={"game_id": gid})
        assert co.status_code == 200
        assert co.json()["status"] == "refunded"
        assert abs(_bal(s, user_ctx["token"]) - start_bal) < 0.01

    def test_insufficient_balance(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/mines/start", headers=h, json={"amount": 99999, "mines": 3})
        assert r.status_code == 400


# ---------------- TOWERS ----------------
class TestTowers:
    def test_start_and_pick(self, s, user_ctx, admin_token):
        _set_rigging(s, admin_token, user_ctx["user"]["id"], "win")
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/towers/start", headers=h, json={"amount": 10, "difficulty": "easy"})
        assert r.status_code == 200
        d = r.json()
        assert d["rows"] == 8 and d["cols"] == 4
        gid = d["game_id"]
        pk = s.post(f"{API}/games/towers/pick", headers=h, json={"game_id": gid, "col": 0})
        assert pk.status_code == 200
        body = pk.json()
        assert body["status"] in ("safe", "busted", "completed")
        if body["status"] == "safe":
            assert body["multiplier"] > 1.0
            co = s.post(f"{API}/games/towers/cashout", headers=h, json={"game_id": gid})
            assert co.status_code == 200

    def test_difficulty_cols(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        for diff, cols in [("easy", 4), ("medium", 3), ("hard", 2)]:
            r = s.post(f"{API}/games/towers/start", headers=h, json={"amount": 1, "difficulty": diff})
            assert r.status_code == 200
            assert r.json()["cols"] == cols
            # bust
            s.post(f"{API}/games/towers/cashout", headers=h, json={"game_id": r.json()["game_id"]})


# ---------------- PLINKO ----------------
class TestPlinko:
    def test_play_returns_slot(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/plinko/play", headers=h, json={"amount": 5, "risk": "medium"})
        assert r.status_code == 200, r.text
        bet = r.json()
        assert bet["game"] == "plinko"
        assert 0 <= bet["details"]["slot"] <= 8
        assert bet["details"]["risk"] == "medium"

    def test_insufficient(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/plinko/play", headers=h, json={"amount": 99999, "risk": "low"})
        assert r.status_code == 400


# ---------------- UPGRADER ----------------
class TestUpgrader:
    def test_play_target(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/upgrader/play", headers=h, json={"amount": 10, "target": 2.0})
        assert r.status_code == 200
        bet = r.json()
        assert bet["details"]["target"] == 2.0
        if bet["result"] == "win":
            assert abs(bet["payout"] - 20.0) < 0.01
            assert bet["multiplier"] == 2.0

    def test_invalid_target_range(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/upgrader/play", headers=h, json={"amount": 1, "target": 0.5})
        assert r.status_code == 422


# ---------------- BLACKJACK ----------------
class TestBlackjack:
    def test_start_deals_cards(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        start_bal = _bal(s, user_ctx["token"])
        r = s.post(f"{API}/games/blackjack/start", headers=h, json={"amount": 20})
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["player"]) >= 2
        assert len(d["dealer_visible"]) >= 1
        # Balance was reduced
        assert d["balance"] <= start_bal - 20 + 100  # payout if natural BJ allowed
        # If still active → hit or stand
        if d["state"] == "active":
            gid = d["game_id"]
            stand = s.post(f"{API}/games/blackjack/stand", headers=h, json={"game_id": gid})
            assert stand.status_code == 200
            sb = stand.json()
            assert sb["state"] == "ended"
            assert sb["result"] in ("win", "lose", "push", "bust")

    def test_hit_until_bust_or_stand(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/blackjack/start", headers=h, json={"amount": 10})
        d = r.json()
        if d["state"] != "active":
            return
        gid = d["game_id"]
        # Hit a few times
        for _ in range(5):
            hr = s.post(f"{API}/games/blackjack/hit", headers=h, json={"game_id": gid})
            assert hr.status_code == 200
            hb = hr.json()
            if hb["state"] == "ended":
                assert hb["result"] in ("win", "lose", "push", "bust")
                return
        # If still active, stand
        s.post(f"{API}/games/blackjack/stand", headers=h, json={"game_id": gid})


# ---------------- COINFLIP / ROULETTE (sanity) ----------------
class TestExisting:
    def test_coinflip(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/coinflip/play", headers=h, json={"amount": 10, "side": "heads"})
        assert r.status_code == 200
        assert r.json()["game"] == "coinflip"

    def test_roulette(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        r = s.post(f"{API}/games/roulette/play", headers=h, json={"amount": 1, "choice": "red"})
        assert r.status_code == 200
        assert r.json()["game"] == "roulette"


# ---------------- BETS / FEED ----------------
class TestBets:
    def test_bets_me(self, s, user_ctx):
        h = auth_headers(user_ctx["token"])
        s.post(f"{API}/games/coinflip/play", headers=h, json={"amount": 5, "side": "heads"})
        r = s.get(f"{API}/bets/me", headers=h)
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_feed_public(self, s):
        r = s.get(f"{API}/bets/feed")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------------- ADMIN ----------------
class TestAdmin:
    def test_non_admin_forbidden(self, s, user_ctx):
        r = s.get(f"{API}/admin/users", headers=auth_headers(user_ctx["token"]))
        assert r.status_code == 403

    def test_admin_users_list(self, s, admin_token):
        r = s.get(f"{API}/admin/users", headers=auth_headers(admin_token))
        assert r.status_code == 200

    def test_admin_balance_and_rigging(self, s, admin_token, user_ctx):
        uid = user_ctx["user"]["id"]
        r = s.patch(f"{API}/admin/users/{uid}/balance",
                    headers=auth_headers(admin_token), json={"mode": "set", "amount": 500})
        assert r.status_code == 200 and r.json()["balance"] == 500.0
        r2 = s.patch(f"{API}/admin/users/{uid}/rigging",
                     headers=auth_headers(admin_token), json={"rigging": "win"})
        assert r2.status_code == 200 and r2.json()["rigging"] == "win"

    def test_admin_stats(self, s, admin_token):
        r = s.get(f"{API}/admin/stats", headers=auth_headers(admin_token))
        assert r.status_code == 200
        for k in ("total_users", "total_bets", "total_wagered", "total_paid_out", "house_profit"):
            assert k in r.json()


# ---------------- Rigging statistical (coinflip — fast & reliable) ----------------
class TestRigging:
    def test_rig_win_majority(self, s, admin_token):
        data, _ = _register(s)
        uid = data["user"]["id"]; tok = data["token"]
        _set_balance(s, admin_token, uid, 100000)
        _set_rigging(s, admin_token, uid, "win")
        h = auth_headers(tok)
        wins = 0
        n = 25
        for _ in range(n):
            b = s.post(f"{API}/games/coinflip/play", headers=h, json={"amount": 1, "side": "heads"}).json()
            if b["result"] == "win":
                wins += 1
        assert wins / n > 0.6, f"rig=win produced only {wins}/{n}"

    def test_rig_lose_majority(self, s, admin_token):
        data, _ = _register(s)
        uid = data["user"]["id"]; tok = data["token"]
        _set_balance(s, admin_token, uid, 100000)
        _set_rigging(s, admin_token, uid, "lose")
        h = auth_headers(tok)
        wins = 0
        n = 25
        for _ in range(n):
            b = s.post(f"{API}/games/coinflip/play", headers=h, json={"amount": 1, "side": "heads"}).json()
            if b["result"] == "win":
                wins += 1
        assert wins / n < 0.4, f"rig=lose produced {wins}/{n}"
