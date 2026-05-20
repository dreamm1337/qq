from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import math
import random
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal

import bcrypt
import jwt
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from motor.motor_asyncio import AsyncIOMotorClient
from starlette.middleware.cors import CORSMiddleware


# -------------------- Config --------------------
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day for simple casino app
STARTING_BALANCE = float(os.environ.get("STARTING_BALANCE", "1000"))

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
    rigging: str  # 'none' | 'win' | 'lose'
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
    result: str  # win | lose
    multiplier: float
    details: dict
    created_at: str


class CrashIn(BaseModel):
    amount: float = Field(gt=0)
    auto_cashout: float = Field(gt=1.0, le=1000.0)


class CoinflipIn(BaseModel):
    amount: float = Field(gt=0)
    side: Literal["heads", "tails"]


class RouletteIn(BaseModel):
    amount: float = Field(gt=0)
    choice: Literal["red", "black", "green"]


class MinesIn(BaseModel):
    amount: float = Field(gt=0)
    mines: int = Field(ge=1, le=24)
    picks: List[int] = Field(min_length=1, max_length=24)  # tile indices 0..24


class AdminBalanceIn(BaseModel):
    mode: Literal["set", "add"] = "set"
    amount: float


class AdminRiggingIn(BaseModel):
    rigging: Literal["none", "win", "lose"]


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


# -------------------- Bet record + activity --------------------
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


async def adjust_balance(user_id: str, delta: float) -> float:
    res = await db.users.find_one_and_update(
        {"id": user_id},
        {"$inc": {"balance": delta}},
        return_document=True,
        projection={"_id": 0},
    )
    return float(res["balance"]) if res else 0.0


# -------------------- Rigging RNG --------------------
def rigged_random(user: dict) -> float:
    """Returns a float in [0, 1). If user rigging is set, biases the value."""
    rig = user.get("rigging", "none")
    r = random.random()
    if rig == "win":
        # bias toward 0 (low values → more likely to win in most checks)
        r = r ** 3  # heavy bias toward 0
    elif rig == "lose":
        # bias toward 1
        r = 1 - (1 - r) ** 3
    return r


# -------------------- Auth Endpoints --------------------
@api_router.post("/auth/register", response_model=AuthOut)
async def register(payload: RegisterIn, response: Response):
    email = payload.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    username_taken = await db.users.find_one({"username": payload.username})
    if username_taken:
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
    response.set_cookie(
        key="access_token", value=token, httponly=True, secure=False,
        samesite="lax", max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/",
    )
    return AuthOut(user=user_to_out(user_doc), token=token)


@api_router.post("/auth/login", response_model=AuthOut)
async def login(payload: LoginIn, response: Response):
    email = payload.email.lower()
    user = await db.users.find_one({"email": email}, {"_id": 0})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], user["email"])
    response.set_cookie(
        key="access_token", value=token, httponly=True, secure=False,
        samesite="lax", max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60, path="/",
    )
    return AuthOut(user=user_to_out(user), token=token)


@api_router.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}


@api_router.get("/auth/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)):
    return user_to_out(user)


# -------------------- Game Endpoints --------------------
@api_router.post("/games/crash/play", response_model=BetOut)
async def play_crash(payload: CrashIn, user: dict = Depends(get_current_user)):
    if user["balance"] < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    # Deduct bet
    await adjust_balance(user["id"], -payload.amount)

    # Determine crash point. Use standard 1% house-edge formula:
    # crash = max(1, floor((100/(1-r)) - 1) / ... ) — use provably-fair style
    r = rigged_random(user)
    # 99% of the time multiplier follows 1/(1-r), 1% instant crash
    if r < 0.01:
        crash_point = 1.00
    else:
        crash_point = max(1.0, round(0.99 / (1 - r), 2))
        crash_point = min(crash_point, 1000.0)

    won = crash_point >= payload.auto_cashout
    multiplier = payload.auto_cashout if won else 0.0
    payout = payload.amount * multiplier if won else 0.0
    if payout > 0:
        await adjust_balance(user["id"], payout)

    bet = await record_bet(
        user, "crash", payload.amount, payout, multiplier,
        "win" if won else "lose",
        {"crash_point": crash_point, "auto_cashout": payload.auto_cashout},
    )
    return bet_to_out(bet)


@api_router.post("/games/coinflip/play", response_model=BetOut)
async def play_coinflip(payload: CoinflipIn, user: dict = Depends(get_current_user)):
    if user["balance"] < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    await adjust_balance(user["id"], -payload.amount)

    r = rigged_random(user)
    # 50/50 with house edge approximated by 1.95x payout
    flip = "heads" if r < 0.5 else "tails"
    won = flip == payload.side
    multiplier = 1.95 if won else 0.0
    payout = payload.amount * multiplier if won else 0.0
    if payout > 0:
        await adjust_balance(user["id"], payout)

    bet = await record_bet(
        user, "coinflip", payload.amount, payout, multiplier,
        "win" if won else "lose",
        {"flip": flip, "side": payload.side},
    )
    return bet_to_out(bet)


@api_router.post("/games/roulette/play", response_model=BetOut)
async def play_roulette(payload: RouletteIn, user: dict = Depends(get_current_user)):
    if user["balance"] < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")

    await adjust_balance(user["id"], -payload.amount)

    r = rigged_random(user)
    # 7/15 red, 7/15 black, 1/15 green (like CSGO roulette)
    if r < 7 / 15:
        result_color = "red"
    elif r < 14 / 15:
        result_color = "black"
    else:
        result_color = "green"

    won = result_color == payload.choice
    if won:
        multiplier = 14.0 if result_color == "green" else 2.0
    else:
        multiplier = 0.0
    payout = payload.amount * multiplier if won else 0.0
    if payout > 0:
        await adjust_balance(user["id"], payout)

    bet = await record_bet(
        user, "roulette", payload.amount, payout, multiplier,
        "win" if won else "lose",
        {"result": result_color, "choice": payload.choice},
    )
    return bet_to_out(bet)


def mines_multiplier(picks: int, mines: int, total: int = 25) -> float:
    """Multiplier with ~5% house edge: 0.95 * C(25, picks) / C(25-mines, picks)"""
    safe = total - mines
    if picks > safe:
        return 0.0
    try:
        return round(0.95 * math.comb(total, picks) / math.comb(safe, picks), 2)
    except (ValueError, ZeroDivisionError):
        return 0.0


@api_router.post("/games/mines/play", response_model=BetOut)
async def play_mines(payload: MinesIn, user: dict = Depends(get_current_user)):
    if user["balance"] < payload.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    if payload.mines + len(payload.picks) > 25:
        raise HTTPException(status_code=400, detail="Too many picks for mine count")
    picks = list(set(payload.picks))
    if not all(0 <= i < 25 for i in picks):
        raise HTTPException(status_code=400, detail="Invalid tile index")

    await adjust_balance(user["id"], -payload.amount)

    # Place mines with rigging influence
    all_tiles = list(range(25))
    rig = user.get("rigging", "none")
    if rig == "lose":
        # 70% chance: force at least one of the user's picks to be a bomb
        if random.random() < 0.7:
            forced_bomb = random.choice(picks)
            remaining = [t for t in all_tiles if t != forced_bomb]
            random.shuffle(remaining)
            bombs = [forced_bomb] + remaining[: payload.mines - 1]
        else:
            random.shuffle(all_tiles)
            bombs = all_tiles[: payload.mines]
    elif rig == "win":
        # 80% chance: place all bombs outside user's picks if possible
        non_picks = [t for t in all_tiles if t not in picks]
        if len(non_picks) >= payload.mines and random.random() < 0.8:
            random.shuffle(non_picks)
            bombs = non_picks[: payload.mines]
        else:
            random.shuffle(all_tiles)
            bombs = all_tiles[: payload.mines]
    else:
        random.shuffle(all_tiles)
        bombs = all_tiles[: payload.mines]

    bombs_set = set(bombs)
    hit_bomb = any(p in bombs_set for p in picks)

    won = not hit_bomb
    multiplier = mines_multiplier(len(picks), payload.mines) if won else 0.0
    payout = payload.amount * multiplier if won else 0.0
    if payout > 0:
        await adjust_balance(user["id"], payout)

    bet = await record_bet(
        user, "mines", payload.amount, payout, multiplier,
        "win" if won else "lose",
        {"picks": picks, "bombs": list(bombs), "mines": payload.mines},
    )
    return bet_to_out(bet)


# -------------------- Bet history --------------------
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


# -------------------- Admin Endpoints --------------------
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
        {"$group": {
            "_id": None,
            "wagered": {"$sum": "$amount"},
            "paid_out": {"$sum": "$payout"},
        }}
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
    return {"message": "BloxCasino API", "version": "1.0"}


# -------------------- Init --------------------
@app.on_event("startup")
async def startup_event():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("username", unique=True)
    await db.users.create_index("id", unique=True)
    await db.bets.create_index("created_at")
    await db.bets.create_index("user_id")

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
        # Keep admin password in sync with env
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
