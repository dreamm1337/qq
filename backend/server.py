from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import math
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal

import bcrypt
import jwt
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.cors import CORSMiddleware


# -------------------- Config --------------------
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
STARTING_BALANCE = float(os.environ.get("STARTING_BALANCE", "1000"))
SESSION_TTL_MIN = 30

# Crash math
CRASH_GROWTH = 0.18  # multiplier = e^(elapsed_sec * GROWTH)

# -------------------- DB --------------------
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# -------------------- App --------------------
app = FastAPI(title="BloxCasino API")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)


# -------------------- Models --------------------
class UserOut(BaseModel):
    id: str
    email: str
    username: str
    role: str
    balance: float
    rigging: str
    created_at: str


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=4, max_length=128)
    username: str = Field(min_length=2, max_length=24)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class AuthOut(BaseModel):
    user: UserOut
    token: str


class BetOut(BaseModel):
    id: str
    user_id: str
    username: str
    game: str
    amount: float
    payout: float
    result: str
    multiplier: float
    details: dict
    created_at: str


class AdminBalanceIn(BaseModel):
    mode: Literal["set", "add"] = "set"
    amount: float


class AdminRiggingIn(BaseModel):
    rigging: Literal["none", "win", "lose"]


# Game inputs
class CrashStartIn(BaseModel):
    amount: float = Field(gt=0)
    auto_cashout: Optional[float] = Field(default=None, gt=1.0, le=1000.0)


class GameIdIn(BaseModel):
    game_id: str


class MinesStartIn(BaseModel):
    amount: float = Field(gt=0)
    mines: int = Field(ge=1, le=24)


class MinesRevealIn(BaseModel):
    game_id: str
    tile: int = Field(ge=0, le=24)


class TowersStartIn(BaseModel):
    amount: float = Field(gt=0)
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class TowersPickIn(BaseModel):
    game_id: str
    col: int = Field(ge=0, le=3)


class CoinflipIn(BaseModel):
    amount: float = Field(gt=0)
    side: Literal["heads", "tails"]


class RouletteIn(BaseModel):
    amount: float = Field(gt=0)
    choice: Literal["red", "black", "green"]


class PlinkoIn(BaseModel):
    amount: float = Field(gt=0)
    risk: Literal["low", "medium", "high"] = "medium"


class UpgraderIn(BaseModel):
    amount: float = Field(gt=0)
    target: float = Field(ge=1.1, le=50.0)


class BlackjackHitStandIn(BaseModel):
    game_id: str


class BlackjackStartIn(BaseModel):
    amount: float = Field(gt=0)


# -------------------- Helpers --------------------
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def user_to_out(u: dict) -> UserOut:
    return UserOut(
        id=u["id"],
        email=u["email"],
        username=u["username"],
        role=u.get("role", "user"),
        balance=float(u.get("balance", 0)),
        rigging=u.get("rigging", "none"),
        created_at=u.get("created_at", ""),
    )


def bet_to_out(b: dict) -> BetOut:
    return BetOut(
        id=b["id"],
        user_id=b["user_id"],
        username=b.get("username", ""),
        game=b["game"],
        amount=float(b["amount"]),
        payout=float(b.get("payout", 0)),
        result=b["result"],
        multiplier=float(b.get("multiplier", 0)),
        details=b.get("details", {}),
        created_at=b.get("created_at", ""),
    )


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> dict:
    token = None
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if not token:
        token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token")
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


async def adjust_balance(user_id: str, delta: float) -> float:
    res = await db.users.find_one_and_update(
        {"id": user_id},
        {"$inc": {"balance": delta}},
        return_document=True,
        projection={"_id": 0},
    )
    return float(res["balance"]) if res else 0.0


async def record_bet(user: dict, game: str, amount: float, payout: float,
                     multiplier: float, result: str, details: dict) -> dict:
    bet = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "username": user["username"],
        "game": game,
        "amount": float(amount),
        "payout": float(payout),
        "multiplier": float(multiplier),
        "result": result,
        "details": details,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.bets.insert_one(dict(bet))
    return bet


def rigged_random(user: dict) -> float:
    rig = user.get("rigging", "none")
    r = random.random()
    if rig == "win":
        r = r ** 3
    elif rig == "lose":
        r = 1 - (1 - r) ** 3
    return r


def rigged_coin(user: dict, win_side_prob: float = 0.5) -> bool:
    """Returns True if 'win side' is chosen. Bias by rigging."""
    rig = user.get("rigging", "none")
    if rig == "win":
        return random.random() < min(0.95, win_side_prob + 0.30)
    if rig == "lose":
        return random.random() < max(0.05, win_side_prob - 0.30)
    return random.random() < win_side_prob


# -------------------- Sessions --------------------
async def create_session(user_id: str, game: str, amount: float, data: dict) -> dict:
    sess = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "game": game,
        "state": "active",
        "amount": float(amount),
        "data": data,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=SESSION_TTL_MIN),
    }
    await db.game_sessions.insert_one(dict(sess))
    return sess


async def load_active_session(game_id: str, user_id: str, game: str) -> dict:
    sess = await db.game_sessions.find_one(
        {"id": game_id, "user_id": user_id, "game": game}, {"_id": 0}
    )
    if not sess:
        raise HTTPException(status_code=404, detail="Game session not found")
    if sess.get("state") != "active":
        raise HTTPException(status_code=400, detail="Game already finished")
    return sess


async def end_session(game_id: str, data_update: dict) -> None:
    upd = {"state": "ended"}
    for k, v in data_update.items():
        upd[f"data.{k}"] = v
    await db.game_sessions.update_one({"id": game_id}, {"$set": upd})


# -------------------- Auth --------------------
@api_router.post("/auth/register", response_model=AuthOut)
async def register(payload: RegisterIn, response: Response):
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    if await db.users.find_one({"username": payload.username}):
        raise HTTPException(status_code=400, detail="Username already taken")

    user_doc = {
        "id": str(uuid.uuid4()),
        "email": email,
        "username": payload.username,
        "password_hash": hash_password(payload.password),
        "role": "user",
        "balance": STARTING_BALANCE,
        "rigging": "none",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(dict(user_doc))
    token = create_access_token(user_doc["id"], user_doc["email"])
    response.set_cookie(key="access_token", value=token, httponly=True, secure=False,
                        samesite="lax", max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/")
    return AuthOut(user=user_to_out(user_doc), token=token)


@api_router.post("/auth/login", response_model=AuthOut)
async def login(payload: LoginIn, response: Response):
    email = payload.email.lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], user["email"])
    response.set_cookie(key="access_token", value=token, httponly=True, secure=False,
                        samesite="lax", max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/")
    return AuthOut(user=user_to_out(user), token=token)


@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api_router.get("/auth/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)):
    return user_to_out(user)


# -------------------- CRASH (stateful with manual cashout) --------------------
def crash_time_ms(crash_point: float) -> int:
    return int(math.log(max(1.0001, crash_point)) / CRASH_GROWTH * 1000)


def crash_mult_at(elapsed_ms: float) -> float:
    return math.exp((elapsed_ms / 1000.0) * CRASH_GROWTH)


def determine_crash_point(user: dict) -> float:
    r = rigged_random(user)
    if r < 0.01:
        return 1.00
    return min(1000.0, max(1.0, round(0.99 / (1 - r), 2)))


@api_router.post("/games/crash/start")
async def crash_start(payload: CrashStartIn, user: dict = Depends(get_current_user)):
    if user["balance"] < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    await adjust_balance(user["id"], -payload.amount)
    crash_point = determine_crash_point(user)
    start_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    sess = await create_session(user["id"], "crash", payload.amount, {
        "crash_point": crash_point,
        "start_ms": start_ms,
        "auto_cashout": payload.auto_cashout,
    })
    new_balance = (await db.users.find_one({"id": user["id"]}, {"_id": 0, "balance": 1}))["balance"]
    return {
        "game_id": sess["id"],
        "crash_point": crash_point,  # client uses to know when to stop animation
        "crash_time_ms": crash_time_ms(crash_point),
        "start_ms": start_ms,
        "auto_cashout": payload.auto_cashout,
        "balance": float(new_balance),
    }


@api_router.post("/games/crash/cashout", response_model=BetOut)
async def crash_cashout(payload: GameIdIn, user: dict = Depends(get_current_user)):
    # Atomically claim the session
    sess = await db.game_sessions.find_one_and_update(
        {"id": payload.game_id, "user_id": user["id"], "game": "crash", "state": "active"},
        {"$set": {"state": "ended"}},
        return_document=True, projection={"_id": 0},
    )
    if not sess:
        raise HTTPException(status_code=400, detail="Game not active")

    data = sess["data"]
    crash_point = float(data["crash_point"])
    start_ms = int(data["start_ms"])
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    elapsed = max(0, now_ms - start_ms)
    cp_time = crash_time_ms(crash_point)

    if elapsed >= cp_time:
        # Crashed before cashout
        bet = await record_bet(user, "crash", sess["amount"], 0.0, 0.0, "lose",
                               {"crash_point": crash_point, "cashed_at": None})
        return bet_to_out(bet)

    current_mult = round(min(crash_mult_at(elapsed), crash_point), 2)
    payout = round(sess["amount"] * current_mult, 2)
    await adjust_balance(user["id"], payout)
    bet = await record_bet(user, "crash", sess["amount"], payout, current_mult, "win",
                           {"crash_point": crash_point, "cashed_at": current_mult})
    return bet_to_out(bet)


@api_router.post("/games/crash/bust")
async def crash_bust(payload: GameIdIn, user: dict = Depends(get_current_user)):
    """Client tells server the round crashed without cashout — record lose."""
    sess = await db.game_sessions.find_one_and_update(
        {"id": payload.game_id, "user_id": user["id"], "game": "crash", "state": "active"},
        {"$set": {"state": "ended"}},
        return_document=True, projection={"_id": 0},
    )
    if not sess:
        return {"ok": True}
    data = sess["data"]
    crash_point = float(data["crash_point"])
    bet = await record_bet(user, "crash", sess["amount"], 0.0, 0.0, "lose",
                           {"crash_point": crash_point, "cashed_at": None})
    return {"ok": True, "bet": bet_to_out(bet).model_dump()}


# -------------------- MINES (stateful, click-to-reveal) --------------------
def mines_multiplier(picks: int, mines: int, total: int = 25) -> float:
    safe = total - mines
    if picks <= 0 or picks > safe:
        return 0.0
    try:
        return round(0.95 * math.comb(total, picks) / math.comb(safe, picks), 2)
    except (ValueError, ZeroDivisionError):
        return 0.0


def place_mines_bombs(user: dict, mines: int, planned_picks: Optional[List[int]] = None) -> List[int]:
    """Place bombs with rigging — at session start we don't yet know picks,
    but we can bias placement based on user rigging using current revealed set."""
    all_tiles = list(range(25))
    random.shuffle(all_tiles)
    return all_tiles[:mines]


@api_router.post("/games/mines/start")
async def mines_start(payload: MinesStartIn, user: dict = Depends(get_current_user)):
    if user["balance"] < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    if payload.mines >= 25:
        raise HTTPException(status_code=400, detail="Too many mines")
    await adjust_balance(user["id"], -payload.amount)
    bombs = place_mines_bombs(user, payload.mines)
    sess = await create_session(user["id"], "mines", payload.amount, {
        "mines": payload.mines,
        "bombs": bombs,
        "revealed_safe": [],
    })
    new_balance = (await db.users.find_one({"id": user["id"]}, {"_id": 0, "balance": 1}))["balance"]
    return {
        "game_id": sess["id"],
        "mines": payload.mines,
        "amount": payload.amount,
        "balance": float(new_balance),
    }


@api_router.post("/games/mines/reveal")
async def mines_reveal(payload: MinesRevealIn, user: dict = Depends(get_current_user)):
    sess = await load_active_session(payload.game_id, user["id"], "mines")
    data = sess["data"]
    mines = int(data["mines"])
    bombs = set(data["bombs"])
    revealed = list(data["revealed_safe"])
    if payload.tile in revealed:
        raise HTTPException(status_code=400, detail="Tile already revealed")

    # Apply rigging here: if user is rigged to lose, with probability force this tile to be a bomb
    # by SWAPPING bomb positions (only if this tile isn't already a bomb).
    rig = user.get("rigging", "none")
    if payload.tile not in bombs:
        if rig == "lose" and random.random() < 0.55:
            # Move a random existing bomb to this tile
            non_bombs = [t for t in range(25) if t not in bombs and t not in revealed]
            if payload.tile in non_bombs:
                old_bomb = random.choice(list(bombs))
                bombs.remove(old_bomb)
                bombs.add(payload.tile)
                await db.game_sessions.update_one(
                    {"id": sess["id"]}, {"$set": {"data.bombs": list(bombs)}}
                )
    else:
        # Tile IS a bomb; if rigged WIN, with prob swap it with a safe tile
        if rig == "win" and random.random() < 0.70:
            safe_non_revealed = [t for t in range(25) if t not in bombs and t not in revealed]
            if safe_non_revealed:
                new_pos = random.choice(safe_non_revealed)
                bombs.remove(payload.tile)
                bombs.add(new_pos)
                await db.game_sessions.update_one(
                    {"id": sess["id"]}, {"$set": {"data.bombs": list(bombs)}}
                )

    if payload.tile in bombs:
        # BOOM — game over, no payout
        await end_session(sess["id"], {"busted_on": payload.tile})
        bet = await record_bet(user, "mines", sess["amount"], 0.0, 0.0, "lose",
                               {"mines": mines, "bombs": list(bombs), "revealed": revealed,
                                "busted_on": payload.tile})
        return {
            "status": "busted",
            "tile": payload.tile,
            "is_bomb": True,
            "bombs": list(bombs),
            "multiplier": 0.0,
            "bet": bet_to_out(bet).model_dump(),
        }

    revealed.append(payload.tile)
    await db.game_sessions.update_one(
        {"id": sess["id"]}, {"$set": {"data.revealed_safe": revealed}}
    )
    current_mult = mines_multiplier(len(revealed), mines)
    safe_total = 25 - mines

    # Auto cashout if all safe tiles revealed
    if len(revealed) >= safe_total:
        await end_session(sess["id"], {"auto_cashed": True})
        payout = round(sess["amount"] * current_mult, 2)
        await adjust_balance(user["id"], payout)
        bet = await record_bet(user, "mines", sess["amount"], payout, current_mult, "win",
                               {"mines": mines, "bombs": list(bombs), "revealed": revealed,
                                "auto_cashed": True})
        return {
            "status": "cleared",
            "tile": payload.tile,
            "is_bomb": False,
            "bombs": list(bombs),
            "revealed": revealed,
            "multiplier": current_mult,
            "next_multiplier": current_mult,
            "bet": bet_to_out(bet).model_dump(),
        }

    next_mult = mines_multiplier(len(revealed) + 1, mines)
    return {
        "status": "safe",
        "tile": payload.tile,
        "is_bomb": False,
        "multiplier": current_mult,
        "next_multiplier": next_mult,
        "revealed": revealed,
    }


@api_router.post("/games/mines/cashout")
async def mines_cashout(payload: GameIdIn, user: dict = Depends(get_current_user)):
    sess = await db.game_sessions.find_one_and_update(
        {"id": payload.game_id, "user_id": user["id"], "game": "mines", "state": "active"},
        {"$set": {"state": "ended"}},
        return_document=True, projection={"_id": 0},
    )
    if not sess:
        raise HTTPException(status_code=400, detail="Game not active")
    data = sess["data"]
    mines = int(data["mines"])
    revealed = data["revealed_safe"]
    bombs = data["bombs"]
    if len(revealed) == 0:
        # Refund
        await adjust_balance(user["id"], sess["amount"])
        return {"status": "refunded", "bombs": bombs, "multiplier": 0.0}
    mult = mines_multiplier(len(revealed), mines)
    payout = round(sess["amount"] * mult, 2)
    await adjust_balance(user["id"], payout)
    bet = await record_bet(user, "mines", sess["amount"], payout, mult, "win",
                           {"mines": mines, "bombs": bombs, "revealed": revealed})
    return {
        "status": "cashed",
        "multiplier": mult,
        "payout": payout,
        "bombs": bombs,
        "bet": bet_to_out(bet).model_dump(),
    }


# -------------------- TOWERS --------------------
TOWERS_CONFIG = {
    "easy":   {"rows": 8, "cols": 4, "mines": 1},  # safe prob 3/4
    "medium": {"rows": 8, "cols": 3, "mines": 1},  # safe prob 2/3
    "hard":   {"rows": 8, "cols": 2, "mines": 1},  # safe prob 1/2
}


def towers_multiplier(level: int, cfg: dict) -> float:
    safe = cfg["cols"] - cfg["mines"]
    if level <= 0:
        return 0.0
    return round(0.95 * (cfg["cols"] / safe) ** level, 2)


@api_router.post("/games/towers/start")
async def towers_start(payload: TowersStartIn, user: dict = Depends(get_current_user)):
    if user["balance"] < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    await adjust_balance(user["id"], -payload.amount)
    cfg = TOWERS_CONFIG[payload.difficulty]
    bombs = [random.randrange(cfg["cols"]) for _ in range(cfg["rows"])]
    sess = await create_session(user["id"], "towers", payload.amount, {
        "difficulty": payload.difficulty,
        "rows": cfg["rows"], "cols": cfg["cols"],
        "bombs": bombs, "path": [],
    })
    new_balance = (await db.users.find_one({"id": user["id"]}, {"_id": 0, "balance": 1}))["balance"]
    return {
        "game_id": sess["id"],
        "rows": cfg["rows"], "cols": cfg["cols"],
        "difficulty": payload.difficulty,
        "amount": payload.amount,
        "balance": float(new_balance),
    }


@api_router.post("/games/towers/pick")
async def towers_pick(payload: TowersPickIn, user: dict = Depends(get_current_user)):
    sess = await load_active_session(payload.game_id, user["id"], "towers")
    data = sess["data"]
    cfg = TOWERS_CONFIG[data["difficulty"]]
    path = list(data["path"])
    row = len(path)
    if row >= cfg["rows"]:
        raise HTTPException(status_code=400, detail="No more rows")
    if payload.col < 0 or payload.col >= cfg["cols"]:
        raise HTTPException(status_code=400, detail="Invalid column")
    bombs = list(data["bombs"])

    # Rigging influence
    rig = user.get("rigging", "none")
    is_bomb = bombs[row] == payload.col
    if not is_bomb and rig == "lose" and random.random() < 0.55:
        bombs[row] = payload.col
        is_bomb = True
        await db.game_sessions.update_one({"id": sess["id"]}, {"$set": {"data.bombs": bombs}})
    elif is_bomb and rig == "win" and random.random() < 0.75:
        # Move bomb to another col
        other_cols = [c for c in range(cfg["cols"]) if c != payload.col]
        bombs[row] = random.choice(other_cols)
        is_bomb = False
        await db.game_sessions.update_one({"id": sess["id"]}, {"$set": {"data.bombs": bombs}})

    if is_bomb:
        await end_session(sess["id"], {"busted_on": {"row": row, "col": payload.col}})
        bet = await record_bet(user, "towers", sess["amount"], 0.0, 0.0, "lose",
                               {"difficulty": data["difficulty"], "bombs": bombs, "path": path,
                                "busted_on": {"row": row, "col": payload.col}})
        return {
            "status": "busted",
            "row": row, "col": payload.col,
            "bombs": bombs,
            "bet": bet_to_out(bet).model_dump(),
        }

    path.append(payload.col)
    await db.game_sessions.update_one({"id": sess["id"]}, {"$set": {"data.path": path}})
    current_mult = towers_multiplier(len(path), cfg)

    # Auto-cashout on top
    if len(path) >= cfg["rows"]:
        await end_session(sess["id"], {"completed": True})
        payout = round(sess["amount"] * current_mult, 2)
        await adjust_balance(user["id"], payout)
        bet = await record_bet(user, "towers", sess["amount"], payout, current_mult, "win",
                               {"difficulty": data["difficulty"], "bombs": bombs, "path": path,
                                "completed": True})
        return {
            "status": "completed",
            "row": row, "col": payload.col,
            "bombs": bombs, "path": path,
            "multiplier": current_mult,
            "bet": bet_to_out(bet).model_dump(),
        }

    next_mult = towers_multiplier(len(path) + 1, cfg)
    return {
        "status": "safe",
        "row": row, "col": payload.col,
        "path": path,
        "multiplier": current_mult,
        "next_multiplier": next_mult,
    }


@api_router.post("/games/towers/cashout")
async def towers_cashout(payload: GameIdIn, user: dict = Depends(get_current_user)):
    sess = await db.game_sessions.find_one_and_update(
        {"id": payload.game_id, "user_id": user["id"], "game": "towers", "state": "active"},
        {"$set": {"state": "ended"}},
        return_document=True, projection={"_id": 0},
    )
    if not sess:
        raise HTTPException(status_code=400, detail="Game not active")
    data = sess["data"]
    cfg = TOWERS_CONFIG[data["difficulty"]]
    path = data["path"]
    bombs = data["bombs"]
    if len(path) == 0:
        await adjust_balance(user["id"], sess["amount"])
        return {"status": "refunded", "bombs": bombs}
    mult = towers_multiplier(len(path), cfg)
    payout = round(sess["amount"] * mult, 2)
    await adjust_balance(user["id"], payout)
    bet = await record_bet(user, "towers", sess["amount"], payout, mult, "win",
                           {"difficulty": data["difficulty"], "bombs": bombs, "path": path})
    return {
        "status": "cashed",
        "multiplier": mult, "payout": payout, "bombs": bombs,
        "bet": bet_to_out(bet).model_dump(),
    }


# -------------------- COINFLIP --------------------
@api_router.post("/games/coinflip/play", response_model=BetOut)
async def play_coinflip(payload: CoinflipIn, user: dict = Depends(get_current_user)):
    if user["balance"] < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    await adjust_balance(user["id"], -payload.amount)
    won = rigged_coin(user, 0.5)
    flip = payload.side if won else ("tails" if payload.side == "heads" else "heads")
    multiplier = 1.95 if won else 0.0
    payout = round(payload.amount * multiplier, 2) if won else 0.0
    if payout > 0:
        await adjust_balance(user["id"], payout)
    bet = await record_bet(user, "coinflip", payload.amount, payout, multiplier,
                           "win" if won else "lose",
                           {"flip": flip, "side": payload.side})
    return bet_to_out(bet)


# -------------------- ROULETTE --------------------
@api_router.post("/games/roulette/play", response_model=BetOut)
async def play_roulette(payload: RouletteIn, user: dict = Depends(get_current_user)):
    if user["balance"] < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    await adjust_balance(user["id"], -payload.amount)
    r = rigged_random(user)
    if r < 7 / 15:
        result_color = "red"
    elif r < 14 / 15:
        result_color = "black"
    else:
        result_color = "green"
    won = result_color == payload.choice
    multiplier = (14.0 if result_color == "green" else 2.0) if won else 0.0
    payout = round(payload.amount * multiplier, 2) if won else 0.0
    if payout > 0:
        await adjust_balance(user["id"], payout)
    bet = await record_bet(user, "roulette", payload.amount, payout, multiplier,
                           "win" if won else "lose",
                           {"result": result_color, "choice": payload.choice})
    return bet_to_out(bet)


# -------------------- PLINKO --------------------
PLINKO_ROWS = 8
PLINKO_TABLE = {
    "low":    [5.6, 2.1, 1.1, 1.0, 0.5, 1.0, 1.1, 2.1, 5.6],
    "medium": [13.0, 3.0, 1.3, 0.7, 0.4, 0.7, 1.3, 3.0, 13.0],
    "high":   [29.0, 4.0, 1.5, 0.3, 0.2, 0.3, 1.5, 4.0, 29.0],
}


@api_router.post("/games/plinko/play")
async def play_plinko(payload: PlinkoIn, user: dict = Depends(get_current_user)):
    if user["balance"] < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    await adjust_balance(user["id"], -payload.amount)

    table = PLINKO_TABLE[payload.risk]
    rig = user.get("rigging", "none")

    # Pick the landing slot first, then construct a deterministic path of L/R decisions
    if rig == "win" and random.random() < 0.6:
        slot = random.choice([0, len(table) - 1])
    elif rig == "lose" and random.random() < 0.7:
        # middle slots have lowest multiplier
        slot = random.randint(PLINKO_ROWS // 2 - 1, PLINKO_ROWS // 2 + 1)
    else:
        # Slightly weighted toward center (binomial)
        slot = sum(1 for _ in range(PLINKO_ROWS) if random.random() < 0.5)

    multiplier = table[slot]
    payout = round(payload.amount * multiplier, 2)
    if payout > 0:
        await adjust_balance(user["id"], payout)
    # Reconstruct a plausible path: 'slot' right moves, 'rows-slot' left moves, shuffled
    path = [1] * slot + [0] * (PLINKO_ROWS - slot)
    random.shuffle(path)
    result = "win" if payout > payload.amount else "lose"
    bet = await record_bet(user, "plinko", payload.amount, payout, multiplier, result,
                           {"risk": payload.risk, "slot": slot, "path": path,
                            "table": table})
    return bet_to_out(bet)


# -------------------- UPGRADER --------------------
@api_router.post("/games/upgrader/play")
async def play_upgrader(payload: UpgraderIn, user: dict = Depends(get_current_user)):
    if user["balance"] < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    await adjust_balance(user["id"], -payload.amount)
    target = float(payload.target)
    base_win_prob = max(0.0, min(0.95, 0.95 / target))
    won = rigged_coin(user, base_win_prob)
    multiplier = target if won else 0.0
    payout = round(payload.amount * multiplier, 2) if won else 0.0
    if payout > 0:
        await adjust_balance(user["id"], payout)
    # Roll a random angle 0..360; "win zone" = first base_win_prob*360 degrees
    win_arc = round(360 * base_win_prob, 2)
    if won:
        angle = round(random.uniform(0, win_arc), 2)
    else:
        angle = round(random.uniform(win_arc, 360), 2)
    bet = await record_bet(user, "upgrader", payload.amount, payout, multiplier,
                           "win" if won else "lose",
                           {"target": target, "win_arc": win_arc, "angle": angle})
    return bet_to_out(bet)


# -------------------- BLACKJACK --------------------
def draw_card(rig_bonus: int = 0) -> dict:
    """Returns a card {rank: 1-13, suit: ♥♦♣♠}. rig_bonus shifts rank slightly."""
    rank = random.randint(1, 13)
    suit = random.choice(["♥", "♦", "♣", "♠"])
    return {"rank": rank, "suit": suit}


def card_value(rank: int) -> int:
    if rank == 1:
        return 11
    if rank >= 10:
        return 10
    return rank


def hand_total(cards: List[dict]) -> int:
    total = sum(card_value(c["rank"]) for c in cards)
    aces = sum(1 for c in cards if c["rank"] == 1)
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total


def rigged_draw(user: dict, target_low: bool = False) -> dict:
    """If target_low True, prefer drawing low cards (bust the dealer);
    if False, normal draw. Use rigging to bias."""
    rig = user.get("rigging", "none")
    # Default: uniform
    if rig == "win" and target_low:
        # Help player: dealer gets high cards (bust)
        rank = random.choices(list(range(1, 14)), weights=[1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3])[0]
    elif rig == "lose" and target_low:
        # Hurt player: dealer gets low cards (safe)
        rank = random.choices(list(range(1, 14)), weights=[3, 3, 3, 3, 3, 2, 2, 1, 1, 1, 1, 1, 1])[0]
    elif rig == "win" and not target_low:
        # Player gets favorable cards
        rank = random.choices(list(range(1, 14)), weights=[3, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3])[0]
    elif rig == "lose" and not target_low:
        rank = random.choices(list(range(1, 14)), weights=[1, 2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 1])[0]
    else:
        rank = random.randint(1, 13)
    return {"rank": rank, "suit": random.choice(["♥", "♦", "♣", "♠"])}


def bj_state_response(sess: dict) -> dict:
    data = sess["data"]
    return {
        "game_id": sess["id"],
        "state": sess["state"],
        "amount": sess["amount"],
        "player": data["player"],
        "dealer": data["dealer"],
        "player_total": hand_total(data["player"]),
        "dealer_visible": data["dealer"][:1] if sess["state"] == "active" else data["dealer"],
        "dealer_total": hand_total(data["dealer"]) if sess["state"] != "active" else card_value(data["dealer"][0]["rank"]),
        "result": data.get("result"),
        "payout": data.get("payout", 0),
        "multiplier": data.get("multiplier", 0),
    }


@api_router.post("/games/blackjack/start")
async def bj_start(payload: BlackjackStartIn, user: dict = Depends(get_current_user)):
    if user["balance"] < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    await adjust_balance(user["id"], -payload.amount)

    player = [rigged_draw(user, target_low=False), rigged_draw(user, target_low=False)]
    dealer = [rigged_draw(user, target_low=True), rigged_draw(user, target_low=True)]

    pt = hand_total(player)
    dt = hand_total(dealer)

    sess = await create_session(user["id"], "blackjack", payload.amount, {
        "player": player, "dealer": dealer,
        "result": None, "payout": 0, "multiplier": 0,
    })

    # Natural blackjack check
    if pt == 21 or dt == 21:
        await _bj_resolve(user, sess)
        sess = await db.game_sessions.find_one({"id": sess["id"]}, {"_id": 0})

    new_balance = (await db.users.find_one({"id": user["id"]}, {"_id": 0, "balance": 1}))["balance"]
    resp = bj_state_response(sess)
    resp["balance"] = float(new_balance)
    return resp


@api_router.post("/games/blackjack/hit")
async def bj_hit(payload: BlackjackHitStandIn, user: dict = Depends(get_current_user)):
    sess = await load_active_session(payload.game_id, user["id"], "blackjack")
    data = sess["data"]
    player = list(data["player"])
    player.append(rigged_draw(user, target_low=False))
    await db.game_sessions.update_one({"id": sess["id"]}, {"$set": {"data.player": player}})
    sess["data"]["player"] = player

    if hand_total(player) > 21:
        await _bj_resolve(user, sess, force_player_bust=True)
        sess = await db.game_sessions.find_one({"id": sess["id"]}, {"_id": 0})
    return bj_state_response(sess)


@api_router.post("/games/blackjack/stand")
async def bj_stand(payload: BlackjackHitStandIn, user: dict = Depends(get_current_user)):
    sess = await load_active_session(payload.game_id, user["id"], "blackjack")
    await _bj_resolve(user, sess)
    sess = await db.game_sessions.find_one({"id": sess["id"]}, {"_id": 0})
    return bj_state_response(sess)


async def _bj_resolve(user: dict, sess: dict, force_player_bust: bool = False) -> None:
    data = sess["data"]
    player = list(data["player"])
    dealer = list(data["dealer"])
    pt = hand_total(player)

    if force_player_bust or pt > 21:
        result = "bust"
        payout = 0.0
        multiplier = 0.0
    else:
        # Dealer plays
        while hand_total(dealer) < 17:
            dealer.append(rigged_draw(user, target_low=True))
        dt = hand_total(dealer)
        if dt > 21 or pt > dt:
            # Blackjack pays 3:2
            if pt == 21 and len(player) == 2:
                multiplier = 2.5
            else:
                multiplier = 2.0
            payout = round(sess["amount"] * multiplier, 2)
            result = "win"
        elif pt == dt:
            multiplier = 1.0  # push
            payout = round(sess["amount"], 2)
            result = "push"
        else:
            multiplier = 0.0
            payout = 0.0
            result = "lose"

    if payout > 0:
        await adjust_balance(user["id"], payout)

    await db.game_sessions.update_one(
        {"id": sess["id"]},
        {"$set": {
            "state": "ended",
            "data.dealer": dealer,
            "data.result": result,
            "data.payout": payout,
            "data.multiplier": multiplier,
        }},
    )

    res_label = "win" if result == "win" else ("win" if result == "push" else "lose")
    await record_bet(user, "blackjack", sess["amount"], payout, multiplier, res_label,
                     {"player": player, "dealer": dealer, "outcome": result})


# -------------------- BETS HISTORY --------------------
@api_router.get("/bets/me", response_model=List[BetOut])
async def my_bets(user: dict = Depends(get_current_user)):
    cursor = db.bets.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(50)
    items = await cursor.to_list(50)
    return [bet_to_out(b) for b in items]


@api_router.get("/bets/feed", response_model=List[BetOut])
async def live_feed():
    cursor = db.bets.find({}, {"_id": 0}).sort("created_at", -1).limit(20)
    items = await cursor.to_list(20)
    return [bet_to_out(b) for b in items]


# -------------------- ADMIN --------------------
@api_router.get("/admin/users", response_model=List[UserOut])
async def admin_list_users(_: dict = Depends(require_admin)):
    cursor = db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1)
    items = await cursor.to_list(500)
    return [user_to_out(u) for u in items]


@api_router.patch("/admin/users/{user_id}/balance", response_model=UserOut)
async def admin_set_balance(user_id: str, payload: AdminBalanceIn, _: dict = Depends(require_admin)):
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.mode == "set":
        await db.users.update_one({"id": user_id}, {"$set": {"balance": float(payload.amount)}})
    else:
        await db.users.update_one({"id": user_id}, {"$inc": {"balance": float(payload.amount)}})
    updated = await db.users.find_one({"id": user_id}, {"_id": 0})
    return user_to_out(updated)


@api_router.patch("/admin/users/{user_id}/rigging", response_model=UserOut)
async def admin_set_rigging(user_id: str, payload: AdminRiggingIn, _: dict = Depends(require_admin)):
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.update_one({"id": user_id}, {"$set": {"rigging": payload.rigging}})
    updated = await db.users.find_one({"id": user_id}, {"_id": 0})
    return user_to_out(updated)


@api_router.get("/admin/bets", response_model=List[BetOut])
async def admin_all_bets(_: dict = Depends(require_admin)):
    cursor = db.bets.find({}, {"_id": 0}).sort("created_at", -1).limit(200)
    items = await cursor.to_list(200)
    return [bet_to_out(b) for b in items]


@api_router.get("/admin/stats")
async def admin_stats(_: dict = Depends(require_admin)):
    total_users = await db.users.count_documents({})
    total_bets = await db.bets.count_documents({})
    agg = await db.bets.aggregate([
        {"$group": {"_id": None,
                    "wagered": {"$sum": "$amount"},
                    "paid_out": {"$sum": "$payout"}}}
    ]).to_list(1)
    wagered = float(agg[0]["wagered"]) if agg else 0.0
    paid = float(agg[0]["paid_out"]) if agg else 0.0
    return {
        "total_users": total_users,
        "total_bets": total_bets,
        "total_wagered": wagered,
        "total_paid_out": paid,
        "house_profit": wagered - paid,
    }


# -------------------- Health --------------------
@api_router.get("/")
async def root():
    return {"message": "BloxCasino API", "version": "2.0"}


# -------------------- Init --------------------
@app.on_event("startup")
async def startup_event():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("username", unique=True)
    await db.users.create_index("id", unique=True)
    await db.bets.create_index("created_at")
    await db.bets.create_index("user_id")
    await db.game_sessions.create_index("id", unique=True)
    await db.game_sessions.create_index("user_id")
    await db.game_sessions.create_index("expires_at", expireAfterSeconds=0)

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@bloxcasino.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "id": str(uuid.uuid4()),
            "email": admin_email,
            "username": "admin",
            "password_hash": hash_password(admin_password),
            "role": "admin",
            "balance": 1000000.0,
            "rigging": "none",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info("Seeded admin user: %s", admin_email)
    else:
        if not verify_password(admin_password, existing.get("password_hash", "")):
            await db.users.update_one(
                {"email": admin_email},
                {"$set": {"password_hash": hash_password(admin_password), "role": "admin"}},
            )


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
