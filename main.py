import base64
import datetime as dt
import hashlib
import json
import os
import secrets
import sqlite3
import threading
import uuid
from typing import Any, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

APP_TITLE = "Love Story API"
APP_VERSION = "3.0.0"
COUPLE_NAMES = "李欣 & 王雅婷"
ANNIVERSARY_DATE = "2022-12-25"
SESSION_TTL_HOURS = 24

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
TIMELINE_PATH = os.path.join(BASE_DIR, "timeline.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")
PHOTOS_DIR = os.path.join(BASE_DIR, "photos")

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
MIME_MAP = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}

TIMELINE_LOCK = threading.Lock()

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(PHOTOS_DIR, exist_ok=True)

app = FastAPI(title=APP_TITLE, version=APP_VERSION)


class MessageCreate(BaseModel):
    nickname: str = Field(..., min_length=1, max_length=20)
    content: str = Field(..., min_length=1, max_length=500)


class MessageUpdate(BaseModel):
    nickname: Optional[str] = Field(default=None, min_length=1, max_length=20)
    content: Optional[str] = Field(default=None, min_length=1, max_length=500)


class WishlistCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


class WishlistUpdate(BaseModel):
    completed: bool


class AdminLoginIn(BaseModel):
    password: str = Field(..., min_length=1, max_length=128)


class TimelineCreateIn(BaseModel):
    date: str = Field(..., min_length=1, max_length=20)
    title: str = Field(..., min_length=1, max_length=120)
    description: str = Field(..., min_length=1, max_length=2000)
    image: str = Field(default="", max_length=5_000_000)


def utcnow_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def build_data_url(data: bytes, ext: str) -> str:
    mime = MIME_MAP.get(ext.lower(), "application/octet-stream")
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def ensure_timeline_file() -> None:
    if os.path.exists(TIMELINE_PATH):
        return
    seed = [
        {
            "date": "2022-12-25",
            "title": "我们的起点 ❤️",
            "description": "在圣诞节这天，我们确定了彼此心意。",
            "image": "",
        }
    ]
    with open(TIMELINE_PATH, "w", encoding="utf-8") as file:
        json.dump(seed, file, ensure_ascii=False, indent=2)


def init_db() -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS wishlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            completed_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_credentials (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_sessions (
            token TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """
    )

    cur.execute("SELECT COUNT(*) AS c FROM wishlist")
    if cur.fetchone()["c"] == 0:
        cur.executemany(
            "INSERT INTO wishlist (title, completed, completed_at) VALUES (?, ?, ?)",
            [
                ("去大理感受慢生活", 0, None),
                ("一起去冰岛看极光", 0, None),
                ("看一场浪漫的周杰伦演唱会", 0, None),
                ("共同养一只可爱的小猫咪", 0, None),
                ("一起去海边看日出日落", 0, None),
                ("去一次迪士尼乐园", 0, None),
            ],
        )

    cur.execute("SELECT COUNT(*) AS c FROM messages")
    if cur.fetchone()["c"] == 0:
        cur.executemany(
            "INSERT INTO messages (nickname, content, created_at) VALUES (?, ?, ?)",
            [
                ("李欣", "雅婷，我们要一直幸福下去❤️", "2022-12-25 12:00:00"),
                ("王雅婷", "有你的每一天都是圣诞节🎄", "2022-12-25 12:05:00"),
            ],
        )

    cur.execute("SELECT password_hash, salt FROM admin_credentials WHERE id = 1")
    row = cur.fetchone()
    if row is None:
        initial_password = os.environ.get("LOVE_ADMIN_PASSWORD", "love")
        salt = secrets.token_hex(16)
        cur.execute(
            "INSERT INTO admin_credentials (id, password_hash, salt, updated_at) VALUES (1, ?, ?, ?)",
            (hash_password(initial_password, salt), salt, utcnow_iso()),
        )

    conn.commit()
    conn.close()
    ensure_timeline_file()


def parse_iso_utc(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def cleanup_expired_sessions(conn: sqlite3.Connection) -> None:
    conn.execute(
        "DELETE FROM admin_sessions WHERE expires_at <= ?",
        (utcnow_iso(),),
    )


def verify_admin_password(password: str) -> bool:
    conn = get_db()
    row = conn.execute(
        "SELECT password_hash, salt FROM admin_credentials WHERE id = 1"
    ).fetchone()
    conn.close()
    if row is None:
        return False
    return hash_password(password, row["salt"]) == row["password_hash"]


def create_admin_session() -> dict[str, str]:
    token = secrets.token_urlsafe(32)
    created = dt.datetime.now(dt.timezone.utc)
    expires = created + dt.timedelta(hours=SESSION_TTL_HOURS)
    conn = get_db()
    cleanup_expired_sessions(conn)
    conn.execute(
        "INSERT INTO admin_sessions (token, created_at, expires_at) VALUES (?, ?, ?)",
        (token, created.isoformat().replace("+00:00", "Z"), expires.isoformat().replace("+00:00", "Z")),
    )
    conn.commit()
    conn.close()
    return {
        "token": token,
        "expires_at": expires.isoformat().replace("+00:00", "Z"),
    }


def require_admin(x_admin_token: Optional[str] = Header(default=None)) -> str:
    if not x_admin_token:
        raise HTTPException(status_code=401, detail="缺少管理员令牌")
    conn = get_db()
    cleanup_expired_sessions(conn)
    row = conn.execute(
        "SELECT token, expires_at FROM admin_sessions WHERE token = ?",
        (x_admin_token,),
    ).fetchone()
    if row is None:
        conn.commit()
        conn.close()
        raise HTTPException(status_code=401, detail="管理员会话已失效")
    if parse_iso_utc(row["expires_at"]) <= dt.datetime.now(dt.timezone.utc):
        conn.execute("DELETE FROM admin_sessions WHERE token = ?", (x_admin_token,))
        conn.commit()
        conn.close()
        raise HTTPException(status_code=401, detail="管理员会话已过期")
    conn.commit()
    conn.close()
    return x_admin_token


def read_timeline() -> list[dict[str, Any]]:
    if not os.path.exists(TIMELINE_PATH):
        return []
    with open(TIMELINE_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, list) else []


def save_timeline(items: list[dict[str, Any]]) -> None:
    with open(TIMELINE_PATH, "w", encoding="utf-8") as file:
        json.dump(items, file, ensure_ascii=False, indent=2)


def normalize_timeline_item(payload: TimelineCreateIn) -> dict[str, str]:
    return {
        "date": payload.date.strip(),
        "title": payload.title.strip(),
        "description": payload.description.strip(),
        "image": payload.image.strip(),
    }


def scan_local_images(directory: str, base_url: str) -> list[str]:
    if not os.path.isdir(directory):
        return []
    images: list[str] = []
    for name in sorted(os.listdir(directory)):
        ext = os.path.splitext(name)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            images.append(f"{base_url}/{name}")
    return images


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/meta")
def get_meta() -> dict[str, str]:
    return {
        "couple": COUPLE_NAMES,
        "anniversary": ANNIVERSARY_DATE,
    }


@app.get("/api/timeline")
def get_timeline() -> list[dict[str, Any]]:
    with TIMELINE_LOCK:
        items = read_timeline()
    return sorted(items, key=lambda item: item.get("date", ""))


@app.post("/api/admin/timeline")
def add_timeline(item: TimelineCreateIn, _: str = Depends(require_admin)) -> dict[str, Any]:
    normalized = normalize_timeline_item(item)
    if not normalized["date"] or not normalized["title"] or not normalized["description"]:
        raise HTTPException(status_code=400, detail="日期、标题、描述不能为空")

    with TIMELINE_LOCK:
        items = read_timeline()
        items.append(normalized)
        items.sort(key=lambda entry: entry.get("date", ""))
        save_timeline(items)
    return {"status": "success", "item": normalized}


@app.get("/api/gallery")
def get_gallery() -> list[str]:
    timeline_images = []
    for item in get_timeline():
        image = str(item.get("image", "")).strip()
        if image:
            timeline_images.append(image)
    merged = timeline_images + scan_local_images(STATIC_DIR, "/static") + scan_local_images(PHOTOS_DIR, "/photos")
    deduplicated = list(dict.fromkeys(merged))
    return deduplicated


@app.get("/api/messages")
def list_messages() -> list[dict[str, Any]]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, nickname, content, created_at, updated_at FROM messages ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.post("/api/messages")
def create_message(payload: MessageCreate) -> dict[str, Any]:
    nickname = payload.nickname.strip()
    content = payload.content.strip()
    if not nickname or not content:
        raise HTTPException(status_code=400, detail="昵称和内容不能为空")
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO messages (nickname, content) VALUES (?, ?)",
        (nickname, content),
    )
    conn.commit()
    mid = cursor.lastrowid
    row = conn.execute(
        "SELECT id, nickname, content, created_at, updated_at FROM messages WHERE id = ?",
        (mid,),
    ).fetchone()
    conn.close()
    return {"status": "success", "item": dict(row)}


@app.put("/api/admin/messages/{message_id}")
def update_message(
    message_id: int,
    payload: MessageUpdate,
    _: str = Depends(require_admin),
) -> dict[str, Any]:
    updates: list[str] = []
    params: list[Any] = []
    if payload.nickname is not None:
        nickname = payload.nickname.strip()
        if not nickname:
            raise HTTPException(status_code=400, detail="昵称不能为空")
        updates.append("nickname = ?")
        params.append(nickname)
    if payload.content is not None:
        content = payload.content.strip()
        if not content:
            raise HTTPException(status_code=400, detail="内容不能为空")
        updates.append("content = ?")
        params.append(content)
    if not updates:
        raise HTTPException(status_code=400, detail="没有可更新字段")

    updates.append("updated_at = datetime('now', 'localtime')")
    params.append(message_id)

    conn = get_db()
    cursor = conn.execute(
        f"UPDATE messages SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="留言不存在")
    conn.commit()
    row = conn.execute(
        "SELECT id, nickname, content, created_at, updated_at FROM messages WHERE id = ?",
        (message_id,),
    ).fetchone()
    conn.close()
    return {"status": "success", "item": dict(row)}


@app.delete("/api/admin/messages/{message_id}")
def delete_message(message_id: int, _: str = Depends(require_admin)) -> dict[str, str]:
    conn = get_db()
    cursor = conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="留言不存在")
    return {"status": "success"}


@app.get("/api/wishlist")
def list_wishlist() -> list[dict[str, Any]]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, completed, created_at, completed_at FROM wishlist ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


@app.post("/api/admin/wishlist")
def create_wishlist(payload: WishlistCreate, _: str = Depends(require_admin)) -> dict[str, Any]:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="心愿标题不能为空")
    conn = get_db()
    cursor = conn.execute("INSERT INTO wishlist (title) VALUES (?)", (title,))
    conn.commit()
    row = conn.execute(
        "SELECT id, title, completed, created_at, completed_at FROM wishlist WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()
    conn.close()
    return {"status": "success", "item": dict(row)}


@app.patch("/api/wishlist/{wish_id}")
def update_wishlist(wish_id: int, payload: WishlistUpdate) -> dict[str, Any]:
    completed = 1 if payload.completed else 0
    completed_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M") if completed else None
    conn = get_db()
    cursor = conn.execute(
        "UPDATE wishlist SET completed = ?, completed_at = ? WHERE id = ?",
        (completed, completed_at, wish_id),
    )
    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="心愿不存在")
    conn.commit()
    row = conn.execute(
        "SELECT id, title, completed, created_at, completed_at FROM wishlist WHERE id = ?",
        (wish_id,),
    ).fetchone()
    conn.close()
    return {"status": "success", "item": dict(row)}


@app.post("/api/admin/login")
def admin_login(payload: AdminLoginIn) -> dict[str, Any]:
    if not verify_admin_password(payload.password):
        raise HTTPException(status_code=401, detail="口令错误")
    return {"status": "success", **create_admin_session()}


@app.post("/api/admin/logout")
def admin_logout(x_admin_token: Optional[str] = Header(default=None)) -> dict[str, str]:
    if not x_admin_token:
        return {"status": "success"}
    conn = get_db()
    conn.execute("DELETE FROM admin_sessions WHERE token = ?", (x_admin_token,))
    conn.commit()
    conn.close()
    return {"status": "success"}


@app.post("/api/admin/upload-photo")
async def upload_photo(
    file: UploadFile = File(...),
    mode: str = Form("file"),
    _: str = Depends(require_admin),
) -> dict[str, str]:
    original_name = file.filename or ""
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="仅支持常见图片格式")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")

    if mode == "base64":
        return {"status": "success", "url": build_data_url(content, ext), "mode": "base64"}

    if mode != "file":
        raise HTTPException(status_code=400, detail="mode 只能是 file 或 base64")

    filename = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(PHOTOS_DIR, filename)
    with open(save_path, "wb") as output:
        output.write(content)
    return {"status": "success", "url": f"/photos/{filename}", "mode": "file"}


def read_index_html() -> str:
    path = os.path.join(BASE_DIR, "index.html")
    if not os.path.exists(path):
        return "<h1>index.html not found</h1>"
    with open(path, "r", encoding="utf-8") as file:
        return file.read()


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/photos", StaticFiles(directory=PHOTOS_DIR), name="photos")


@app.get("/", response_class=HTMLResponse)
def serve_home() -> str:
    return read_index_html()


@app.get("/admin", response_class=HTMLResponse)
def serve_admin() -> str:
    return read_index_html()
