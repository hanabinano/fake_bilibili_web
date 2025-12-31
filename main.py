import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from algo import manager as ac_manager

# 基础路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
UPLOAD_DIR = os.path.join(STATIC_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "data.db")
FILTER_FILE = os.path.join(BASE_DIR, "filter_words.json")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, "avatars"), exist_ok=True)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 简单签名 Token
SECRET_KEY = os.environ.get("APP_SECRET", "dev-secret-key")
TOKEN_EXPIRE_SECONDS = 60 * 60 * 24  # 24h


# ---------- 工具与初始化 ----------
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            avatar TEXT,
            nickname TEXT,
            bio TEXT,
            gender TEXT,
            region TEXT,
            role TEXT DEFAULT 'user',
            banned INTEGER DEFAULT 0,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            cover TEXT,
            category TEXT,
            tags TEXT,
            file_path TEXT NOT NULL,
            uploader_id INTEGER,
            plays INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            favorites INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS likes (
            user_id INTEGER,
            video_id INTEGER,
            PRIMARY KEY (user_id, video_id)
        );
        CREATE TABLE IF NOT EXISTS favorites (
            user_id INTEGER,
            video_id INTEGER,
            PRIMARY KEY (user_id, video_id)
        );
        CREATE TABLE IF NOT EXISTS coins (
            user_id INTEGER,
            video_id INTEGER,
            PRIMARY KEY (user_id, video_id)
        );
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER,
            user_id INTEGER,
            content TEXT,
            parent_id INTEGER,
            deleted INTEGER DEFAULT 0,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS danmaku (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER,
            user_id INTEGER,
            content TEXT,
            color TEXT,
            time REAL,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            video_id INTEGER,
            progress REAL,
            updated_at TEXT,
            UNIQUE(user_id, video_id)
        );
        CREATE TABLE IF NOT EXISTS watch_later (
            user_id INTEGER,
            video_id INTEGER,
            PRIMARY KEY (user_id, video_id)
        );
        CREATE TABLE IF NOT EXISTS follows (
            follower_id INTEGER,
            followee_id INTEGER,
            PRIMARY KEY (follower_id, followee_id)
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,
            message TEXT,
            created_at TEXT,
            read INTEGER DEFAULT 0
        );
    """
    )
    # 默认管理员
    cur.execute("SELECT id FROM users WHERE username=?", ("admin",))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (username, password_hash, role, nickname, created_at) VALUES (?, ?, 'admin', ?, ?)",
            (
                "admin",
                hash_password("admin123"),
                "管理员",
                datetime.utcnow().isoformat(),
            ),
        )
    conn.commit()
    conn.close()


def hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()


def sign_token(user_id: int, role: str) -> str:
    payload = {
        "uid": user_id,
        "role": role,
        "exp": int(time.time()) + TOKEN_EXPIRE_SECONDS,
        "rnd": secrets.token_hex(4),
    }
    raw = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(SECRET_KEY.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def verify_token(token: str) -> Dict[str, Any]:
    try:
        raw, sig = token.split(".")
        expect = hmac.new(SECRET_KEY.encode(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expect):
            raise ValueError("bad signature")
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()).decode())
        if payload.get("exp", 0) < int(time.time()):
            raise ValueError("expired")
        return payload
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def success(data: Any = None, message: str = "ok"):
    return {"code": 0, "message": message, "data": data}


def make_notification(conn: sqlite3.Connection, user_id: int, msg: str, ntype: str):
    conn.execute(
        "INSERT INTO notifications (user_id, type, message, created_at) VALUES (?, ?, ?, ?)",
        (user_id, ntype, msg, datetime.utcnow().isoformat()),
    )


def clean_content(text: str) -> str:
    return ac_manager.ac_filter.filter(text)


def load_filter_words() -> List[str]:
    if os.path.exists(FILTER_FILE):
        try:
            with open(FILTER_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [str(w) for w in data]
        except Exception as e:
            print(f"Failed to load filter words: {e}")
    return ["404"]


def save_filter_words(words: List[str]):
    with open(FILTER_FILE, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)


# ---------- 依赖 ----------
def extract_token(authorization: Optional[str], token_q: Optional[str]) -> str:
    if token_q:
        return token_q
    if authorization and authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1]
    if authorization:
        return authorization
    raise HTTPException(status_code=401, detail="Not authenticated")


def get_current_user(
    authorization: Optional[str] = Header(None, convert_underscores=False),
    token: Optional[str] = Query(None, alias="token"),
):
    auth_token = extract_token(authorization, token)
    payload = verify_token(auth_token)
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (payload["uid"],)).fetchone()
    conn.close()
    if not user or user["banned"]:
        raise HTTPException(status_code=403, detail="User banned or not found")
    return user


def get_optional_user(
    authorization: Optional[str] = Header(None, convert_underscores=False),
    token: Optional[str] = Query(None, alias="token"),
):
    try:
        auth_token = extract_token(authorization, token)
    except HTTPException:
        return None
    payload = verify_token(auth_token)
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (payload["uid"],)).fetchone()
    conn.close()
    if not user or user["banned"]:
        return None
    return user


def require_admin(user=Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


# ---------- 模型 ----------
class RegisterInput(BaseModel):
    username: str
    password: str
    email: Optional[str] = None


class LoginInput(BaseModel):
    username: str
    password: str


class ProfileInput(BaseModel):
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    bio: Optional[str] = None
    gender: Optional[str] = None
    region: Optional[str] = None


class PasswordInput(BaseModel):
    old_password: str
    new_password: str


class CommentInput(BaseModel):
    content: str
    parent_id: Optional[int] = None


class DanmakuInput(BaseModel):
    content: str
    color: str = "#FFFFFF"
    video_time: float


class FilterWordsInput(BaseModel):
    words: List[str]


# ---------- 路由 ----------
@app.on_event("startup")
def on_startup():
    init_db()
    print(f"STATIC DIR: {STATIC_DIR}")
    ac_manager.set_filter_words(load_filter_words())


@app.get("/", include_in_schema=False)
def read_index():
    # 直接跳转到静态首页，方便域名根路径访问
    return FileResponse(os.path.join(STATIC_DIR, "index.html")) if os.path.exists(
        os.path.join(STATIC_DIR, "index.html")
    ) else {"message": "index.html missing"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    icon_path = os.path.join(STATIC_DIR, "favicon.ico")
    if os.path.exists(icon_path):
        return FileResponse(icon_path)
    # 没有文件也返回 204，避免 404 噪声
    return Response(status_code=204)


@app.get("/video.html", include_in_schema=False)
def video_page():
    path = os.path.join(STATIC_DIR, "video.html")
    if os.path.exists(path):
        return FileResponse(path)
    return {"message": "video.html missing"}


# --- 用户与权限 ---
@app.post("/api/auth/register")
def register(data: RegisterInput):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO users (username, password_hash, email, nickname, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                data.username,
                hash_password(data.password),
                data.email,
                data.username,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")
    user_id = cur.lastrowid
    conn.close()
    token = sign_token(user_id, "user")
    return success({"token": token, "user_id": user_id})


@app.post("/api/auth/login")
def login(data: LoginInput):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (data.username,)).fetchone()
    conn.close()
    if not user or user["password_hash"] != hash_password(data.password):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    token = sign_token(user["id"], user["role"])
    return success({"token": token, "user_id": user["id"], "role": user["role"]})


@app.post("/api/auth/logout")
def logout():
    return success(message="logout (client discard token)")


@app.get("/api/auth/me")
def me(user=Depends(get_current_user)):
    data = dict(user)
    data.pop("password_hash", None)
    return success(data)


@app.put("/api/user/profile")
def update_profile(body: ProfileInput, user=Depends(get_current_user)):
    conn = get_db()
    conn.execute(
        "UPDATE users SET nickname=?, avatar=?, bio=?, gender=?, region=? WHERE id=?",
        (body.nickname, body.avatar, body.bio, body.gender, body.region, user["id"]),
    )
    conn.commit()
    conn.close()
    return success()


@app.post("/api/user/avatar")
async def upload_avatar(file: UploadFile = File(...), user=Depends(get_current_user)):
    ext = os.path.splitext(file.filename)[1] or ".png"
    fname = f"a_{user['id']}_{int(time.time())}{ext}"
    avatar_dir = os.path.join(UPLOAD_DIR, "avatars")
    os.makedirs(avatar_dir, exist_ok=True)
    avatar_path = os.path.join(avatar_dir, fname)
    with open(avatar_path, "wb") as f:
        f.write(await file.read())
    url = f"/static/uploads/avatars/{fname}"
    conn = get_db()
    conn.execute("UPDATE users SET avatar=? WHERE id=?", (url, user["id"]))
    conn.commit()
    conn.close()
    return success({"avatar": url})


@app.post("/api/user/password")
def change_password(body: PasswordInput, user=Depends(get_current_user)):
    if hash_password(body.old_password) != user["password_hash"]:
        raise HTTPException(status_code=400, detail="Old password wrong")
    conn = get_db()
    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(body.new_password), user["id"]))
    conn.commit()
    conn.close()
    return success()


@app.post("/api/user/reset")
def admin_reset_password(username: str, new_password: str, _: Any = Depends(require_admin)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_password(new_password), username))
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    conn.commit()
    conn.close()
    return success()


# --- 视频上传/播放 ---
@app.post("/api/videos/upload")
async def upload_video(
    title: str = Form(...),
    description: str = Form(""),
    category: str = Form("默认"),
    tags: str = Form(""),
    file: UploadFile = File(...),
    cover: Optional[UploadFile] = File(None),
    user=Depends(get_current_user),
):
    video_dir = os.path.join(UPLOAD_DIR, "videos")
    cover_dir = os.path.join(UPLOAD_DIR, "covers")
    os.makedirs(video_dir, exist_ok=True)
    os.makedirs(cover_dir, exist_ok=True)

    ext = os.path.splitext(file.filename)[1]
    filename = f"v_{int(time.time())}_{secrets.token_hex(4)}{ext}"
    video_path = os.path.join(video_dir, filename)
    with open(video_path, "wb") as f:
        f.write(await file.read())

    cover_path = ""
    if cover:
        cext = os.path.splitext(cover.filename)[1]
        cname = f"c_{int(time.time())}_{secrets.token_hex(4)}{cext}"
        cpath = os.path.join(cover_dir, cname)
        with open(cpath, "wb") as f:
            f.write(await cover.read())
        cover_path = f"/static/uploads/covers/{cname}"

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO videos (title, description, cover, category, tags, file_path, uploader_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            description,
            cover_path,
            category,
            tags,
            f"/static/uploads/videos/{filename}",
            user["id"],
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    vid = cur.lastrowid
    conn.close()
    return success({"video_id": vid})


@app.get("/api/videos")
def list_videos(
    page: int = 1,
    size: int = 10,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    order: str = "hot",
):
    offset = (page - 1) * size
    conn = get_db()
    q = "SELECT * FROM videos WHERE status='active'"
    params: List[Any] = []
    if category:
        q += " AND category=?"
        params.append(category)
    if tag:
        q += " AND tags LIKE ?"
        params.append(f"%{tag}%")
    if order == "new":
        q += " ORDER BY datetime(created_at) DESC"
    else:
        q += " ORDER BY (plays + likes*2 + coins*2 + favorites*3) DESC"
    q += " LIMIT ? OFFSET ?"
    params.extend([size, offset])
    rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    conn.close()
    return success(rows)


@app.get("/api/videos/{vid}")
def video_detail(vid: int, user=Depends(get_optional_user)):
    conn = get_db()
    video = conn.execute(
        """
        SELECT v.*, u.nickname AS uploader_name, u.avatar AS uploader_avatar, u.username AS uploader_username
        FROM videos v
        LEFT JOIN users u ON v.uploader_id = u.id
        WHERE v.id=? AND v.status='active'
        """,
        (vid,),
    ).fetchone()
    if not video:
        conn.close()
        raise HTTPException(status_code=404, detail="Video not found")
    data = dict(video)
    data["uploader_name"] = data.get("uploader_name") or data.get("uploader_username") or f"UP主 {video['uploader_id']}"
    data["uploader_avatar"] = data.get("uploader_avatar") or ""
    if user:
        liked = conn.execute("SELECT 1 FROM likes WHERE user_id=? AND video_id=?", (user["id"], vid)).fetchone()
        faved = conn.execute("SELECT 1 FROM favorites WHERE user_id=? AND video_id=?", (user["id"], vid)).fetchone()
        coin = conn.execute("SELECT 1 FROM coins WHERE user_id=? AND video_id=?", (user["id"], vid)).fetchone()
        data["liked"] = bool(liked)
        data["favorited"] = bool(faved)
        data["coined"] = bool(coin)
    conn.close()
    return success(data)


@app.post("/api/videos/{vid}/play")
def inc_play(vid: int):
    conn = get_db()
    conn.execute("UPDATE videos SET plays = plays + 1 WHERE id=?", (vid,))
    conn.commit()
    conn.close()
    return success()


def toggle_relation(table: str, user_id: int, vid: int, delta_field: str):
    conn = get_db()
    cur = conn.cursor()
    existed = cur.execute(f"SELECT 1 FROM {table} WHERE user_id=? AND video_id=?", (user_id, vid)).fetchone()
    if existed:
        cur.execute(f"DELETE FROM {table} WHERE user_id=? AND video_id=?", (user_id, vid))
        cur.execute(f"UPDATE videos SET {delta_field} = {delta_field} - 1 WHERE id=?", (vid,))
        action = "cancel"
    else:
        cur.execute(f"INSERT INTO {table} (user_id, video_id) VALUES (?, ?)", (user_id, vid))
        cur.execute(f"UPDATE videos SET {delta_field} = {delta_field} + 1 WHERE id=?", (vid,))
        action = "add"
    conn.commit()
    conn.close()
    return action


@app.post("/api/videos/{vid}/like")
def like_video(vid: int, user=Depends(get_current_user)):
    action = toggle_relation("likes", user["id"], vid, "likes")
    if action == "add":
        conn = get_db()
        uploader = conn.execute("SELECT uploader_id FROM videos WHERE id=?", (vid,)).fetchone()
        if uploader:
            make_notification(conn, uploader["uploader_id"], f"你的视频 {vid} 被点赞", "like")
            conn.commit()
        conn.close()
    return success({"action": action})


@app.post("/api/videos/{vid}/favorite")
def favorite_video(vid: int, user=Depends(get_current_user)):
    action = toggle_relation("favorites", user["id"], vid, "favorites")
    return success({"action": action})


@app.post("/api/videos/{vid}/coin")
def coin_video(vid: int, user=Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    existed = cur.execute("SELECT 1 FROM coins WHERE user_id=? AND video_id=?", (user["id"], vid)).fetchone()
    if existed:
        conn.close()
        return success({"action": "skip"})
    cur.execute("INSERT INTO coins (user_id, video_id) VALUES (?, ?)", (user["id"], vid))
    cur.execute("UPDATE videos SET coins = coins + 1 WHERE id=?", (vid,))
    conn.commit()
    conn.close()
    return success({"action": "add"})


@app.post("/api/videos/{vid}/watchlater")
def watch_later(vid: int, user=Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    existed = cur.execute("SELECT 1 FROM watch_later WHERE user_id=? AND video_id=?", (user["id"], vid)).fetchone()
    if existed:
        cur.execute("DELETE FROM watch_later WHERE user_id=? AND video_id=?", (user["id"], vid))
        action = "remove"
    else:
        cur.execute("INSERT INTO watch_later (user_id, video_id) VALUES (?, ?)", (user["id"], vid))
        action = "add"
    conn.commit()
    conn.close()
    return success({"action": action})


# --- 评论 ---
@app.post("/api/videos/{vid}/comments")
def post_comment(vid: int, body: CommentInput, user=Depends(get_current_user)):
    content = clean_content(body.content.strip())
    if not content:
        raise HTTPException(status_code=400, detail="Empty content")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO comments (video_id, user_id, content, parent_id, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (vid, user["id"], content, body.parent_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    if body.parent_id:
        parent = cur.execute("SELECT user_id FROM comments WHERE id=?", (body.parent_id,)).fetchone()
        if parent:
            make_notification(conn, parent["user_id"], f"你的评论有新回复", "reply")
    conn.commit()
    conn.close()
    return success({"comment_id": cur.lastrowid})


@app.get("/api/videos/{vid}/comments")
def list_comments(vid: int, page: int = 1, size: int = 10):
    offset = (page - 1) * size
    conn = get_db()
    parents = conn.execute(
        """
        SELECT c.*, u.nickname, u.avatar FROM comments c
        LEFT JOIN users u ON c.user_id=u.id
        WHERE c.video_id=? AND c.deleted=0 AND c.parent_id IS NULL
        ORDER BY datetime(c.created_at) DESC
        LIMIT ? OFFSET ?
        """,
        (vid, size, offset),
    ).fetchall()
    parent_ids = [p["id"] for p in parents]
    replies = []
    if parent_ids:
        placeholders = ",".join("?" * len(parent_ids))
        replies = conn.execute(
            f"""
            SELECT c.*, u.nickname, u.avatar FROM comments c
            LEFT JOIN users u ON c.user_id=u.id
            WHERE c.parent_id IN ({placeholders}) AND c.deleted=0
            ORDER BY datetime(c.created_at) ASC
            """,
            parent_ids,
        ).fetchall()
    conn.close()
    reply_map: Dict[int, List[Dict[str, Any]]] = {}
    for r in replies:
        reply_map.setdefault(r["parent_id"], []).append(dict(r))
    data = []
    for p in parents:
        item = dict(p)
        item["replies"] = reply_map.get(p["id"], [])
        data.append(item)
    return success(data)


@app.delete("/api/comments/{cid}")
def delete_comment(cid: int, user=Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    comment = cur.execute("SELECT user_id FROM comments WHERE id=?", (cid,)).fetchone()
    if not comment:
        conn.close()
        raise HTTPException(status_code=404, detail="not found")
    if comment["user_id"] != user["id"] and user["role"] != "admin":
        conn.close()
        raise HTTPException(status_code=403, detail="no permission")
    cur.execute("UPDATE comments SET deleted=1 WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    return success()


# --- 弹幕 ---
@app.post("/api/videos/{vid}/danmaku")
def send_danmaku(vid: int, body: DanmakuInput, user=Depends(get_current_user)):
    content = clean_content(body.content.strip())
    if not content:
        raise HTTPException(status_code=400, detail="empty content")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO danmaku (video_id, user_id, content, color, time, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (vid, user["id"], content, body.color, body.video_time, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return success({"id": cur.lastrowid})


@app.get("/api/videos/{vid}/danmaku")
def list_danmaku(vid: int):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT d.content, d.color, d.time, d.user_id, u.nickname, u.avatar
        FROM danmaku d
        LEFT JOIN users u ON d.user_id = u.id
        WHERE d.video_id=?
        ORDER BY d.time ASC
        """,
        (vid,),
    ).fetchall()
    conn.close()
    return success([dict(r) for r in rows])


@app.get("/api/videos/{vid}/danmaku/highlight")
def danmaku_highlight(vid: int, top: int = 3):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT CAST(time AS INT) AS second, COUNT(*) AS cnt
        FROM danmaku
        WHERE video_id=?
        GROUP BY second
        ORDER BY cnt DESC
        LIMIT ?
        """,
        (vid, top),
    ).fetchall()
    conn.close()
    return success([{"second": r["second"], "count": r["cnt"]} for r in rows])


@app.get("/api/danmaku/filterwords")
def get_filter_words(_: Any = Depends(require_admin)):
    return success({"words": load_filter_words()})


@app.post("/api/danmaku/filterwords")
def update_filter_words(body: FilterWordsInput, _: Any = Depends(require_admin)):
    words = [w.strip() for w in body.words if w.strip()]
    save_filter_words(words)
    ac_manager.set_filter_words(words)
    return success({"words": words})


# --- 搜索 & 推荐 ---
@app.get("/api/search")
def search_videos(keyword: str, page: int = 1, size: int = 10):
    offset = (page - 1) * size
    conn = get_db()
    rows = conn.execute(
        """
        SELECT * FROM videos
        WHERE status='active' AND (title LIKE ? OR tags LIKE ?)
        ORDER BY datetime(created_at) DESC
        LIMIT ? OFFSET ?
        """,
        (f"%{keyword}%", f"%{keyword}%", size, offset),
    ).fetchall()
    conn.close()
    return success([dict(r) for r in rows])


@app.get("/api/recommend")
def recommend(limit: int = 10):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT * FROM videos WHERE status='active'
        ORDER BY (plays + likes*2 + favorites*3 + coins*2) DESC, datetime(created_at) DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return success([dict(r) for r in rows])


@app.get("/api/rank")
def rank(range: str = "week", limit: int = 10):
    days = 7 if range == "week" else 30
    since = (datetime.utcnow() - timedelta(days=days)).isoformat()
    conn = get_db()
    rows = conn.execute(
        """
        SELECT * FROM videos
        WHERE status='active' AND datetime(created_at) >= datetime(?)
        ORDER BY (plays + likes*2 + favorites*3 + coins*2) DESC
        LIMIT ?
        """,
        (since, limit),
    ).fetchall()
    conn.close()
    return success([dict(r) for r in rows])


# --- 关注/动态 ---
@app.post("/api/follow/{target_id}")
def follow(target_id: int, user=Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    existed = cur.execute(
        "SELECT 1 FROM follows WHERE follower_id=? AND followee_id=?", (user["id"], target_id)
    ).fetchone()
    if existed:
        cur.execute("DELETE FROM follows WHERE follower_id=? AND followee_id=?", (user["id"], target_id))
        action = "unfollow"
    else:
        cur.execute("INSERT INTO follows (follower_id, followee_id) VALUES (?, ?)", (user["id"], target_id))
        make_notification(conn, target_id, f"{user['username']} 关注了你", "follow")
        action = "follow"
    conn.commit()
    conn.close()
    return success({"action": action})


@app.get("/api/following")
def following(user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT followee_id FROM follows WHERE follower_id=?", (user["id"],)
    ).fetchall()
    conn.close()
    return success([r["followee_id"] for r in rows])


@app.get("/api/fans")
def fans(user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT follower_id FROM follows WHERE followee_id=?", (user["id"],)
    ).fetchall()
    conn.close()
    return success([r["follower_id"] for r in rows])


@app.get("/api/feed")
def feed(user=Depends(get_current_user)):
    conn = get_db()
    ids = [r["followee_id"] for r in conn.execute("SELECT followee_id FROM follows WHERE follower_id=?", (user["id"],))]
    if not ids:
        conn.close()
        return success([])
    placeholders = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT * FROM videos WHERE uploader_id IN ({placeholders}) AND status='active' ORDER BY datetime(created_at) DESC LIMIT 20",
        ids,
    ).fetchall()
    conn.close()
    return success([dict(r) for r in rows])


# --- 历史记录 / 稍后再看 ---
@app.post("/api/history")
def save_history(video_id: int, progress: float = 0.0, user=Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO history (user_id, video_id, progress, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, video_id) DO UPDATE SET progress=excluded.progress, updated_at=excluded.updated_at
        """,
        (user["id"], video_id, progress, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return success()


@app.get("/api/history")
def list_history(user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT h.video_id, h.progress, v.title, v.cover, v.file_path
        FROM history h
        LEFT JOIN videos v ON h.video_id=v.id
        WHERE h.user_id=?
        ORDER BY datetime(h.updated_at) DESC
        LIMIT 30
        """,
        (user["id"],),
    ).fetchall()
    conn.close()
    return success([dict(r) for r in rows])


@app.get("/api/watchlater")
def list_watchlater(user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT w.video_id, v.title, v.cover FROM watch_later w
        LEFT JOIN videos v ON w.video_id=v.id
        WHERE w.user_id=?
        """,
        (user["id"],),
    ).fetchall()
    conn.close()
    return success([dict(r) for r in rows])


# --- 消息通知 ---
@app.get("/api/notifications")
def notifications(user=Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY datetime(created_at) DESC LIMIT 50",
        (user["id"],),
    ).fetchall()
    conn.close()
    return success([dict(r) for r in rows])


# --- 后台管理 ---
@app.get("/api/admin/users")
def admin_users(page: int = 1, size: int = 20, _: Any = Depends(require_admin)):
    offset = (page - 1) * size
    conn = get_db()
    rows = conn.execute(
        "SELECT id, username, role, banned, created_at FROM users LIMIT ? OFFSET ?", (size, offset)
    ).fetchall()
    conn.close()
    return success([dict(r) for r in rows])


@app.post("/api/admin/users/{uid}/ban")
def admin_ban(uid: int, banned: int = 1, _: Any = Depends(require_admin)):
    conn = get_db()
    conn.execute("UPDATE users SET banned=? WHERE id=?", (banned, uid))
    conn.commit()
    conn.close()
    return success()


@app.post("/api/admin/videos/{vid}/delete")
def admin_delete_video(vid: int, _: Any = Depends(require_admin)):
    conn = get_db()
    conn.execute("UPDATE videos SET status='deleted' WHERE id=?", (vid,))
    conn.commit()
    conn.close()
    return success()


@app.post("/api/admin/comments/{cid}/delete")
def admin_delete_comment(cid: int, _: Any = Depends(require_admin)):
    conn = get_db()
    conn.execute("UPDATE comments SET deleted=1 WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    return success()


@app.get("/api/admin/stats")
def admin_stats(_: Any = Depends(require_admin)):
    conn = get_db()
    stats = {
        "user_count": conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"],
        "video_count": conn.execute("SELECT COUNT(*) c FROM videos WHERE status='active'").fetchone()["c"],
        "comment_count": conn.execute("SELECT COUNT(*) c FROM comments").fetchone()["c"],
    }
    top = conn.execute(
        """
        SELECT id, title, plays, likes, favorites, coins
        FROM videos WHERE status='active'
        ORDER BY (plays + likes*2 + favorites*3 + coins*2) DESC
        LIMIT 5
        """
    ).fetchall()
    conn.close()
    stats["top_videos"] = [dict(r) for r in top]
    return success(stats)
