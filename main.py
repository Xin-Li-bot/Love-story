import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database.db"
TIMELINE_PATH = BASE_DIR / "timeline.json"
STATIC_DIR = BASE_DIR / "static"
PHOTOS_DIR = BASE_DIR / "photos"
INDEX_PATH = BASE_DIR / "index.html"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SESSION_HOURS = 12
ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
DEFAULT_WISHES = (
    "去大理感受慢生活",
    "一起去冰岛看极光",
    "看一场喜欢的演唱会",
    "共同养一只可爱的小猫咪",
    "一起去海边看日出日落",
    "去一次迪士尼乐园",
)

STATIC_DIR.mkdir(exist_ok=True)
PHOTOS_DIR.mkdir(exist_ok=True)
_timeline_lock = threading.Lock()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db_session():
    conn = db_connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return f"pbkdf2_sha256$210000${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, expected_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (TypeError, ValueError):
        return False


def initialize_database(default_password: str | None = None) -> None:
    password = default_password or os.getenv("ADMIN_PASSWORD", "love2022")
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nickname TEXT NOT NULL CHECK(length(nickname) BETWEEN 1 AND 30),
                content TEXT NOT NULL CHECK(length(content) BETWEEN 1 AND 500),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS wishlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0, 1)),
                completed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS admin_sessions (
                token_hash TEXT PRIMARY KEY,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        if conn.execute("SELECT COUNT(*) FROM wishlist").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO wishlist (title) VALUES (?)", ((item,) for item in DEFAULT_WISHES)
            )
        if conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO messages (nickname, content, created_at) VALUES (?, ?, ?)",
                (
                    ("李欣", "雅婷，我们要一直幸福下去。", "2022-12-25 12:00:00"),
                    ("王雅婷", "有你的每一天都是圣诞节。", "2022-12-25 12:05:00"),
                ),
            )
        if conn.execute(
            "SELECT 1 FROM app_settings WHERE key = 'admin_password_hash'"
        ).fetchone() is None:
            conn.execute(
                "INSERT INTO app_settings (key, value) VALUES ('admin_password_hash', ?)",
                (hash_password(password),),
            )


initialize_database()

app = FastAPI(
    title="李欣与王雅婷的恋爱纪念站",
    version="3.0.0",
    docs_url=None,
    redoc_url=None,
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


class MessageCreate(BaseModel):
    nickname: str = Field(min_length=1, max_length=30)
    content: str = Field(min_length=1, max_length=500)

    @field_validator("nickname", "content")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("内容不能为空")
        return value


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class TimelineCreate(BaseModel):
    date: str
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1000)
    image: str = Field(default="", max_length=14_000_000)

    @field_validator("date")
    @classmethod
    def valid_date(cls, value: str) -> str:
        datetime.strptime(value, "%Y-%m-%d")
        return value

    @field_validator("title", "description")
    @classmethod
    def clean_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("image")
    @classmethod
    def valid_image(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        allowed = value.startswith(("/static/", "/photos/", "data:image/"))
        if not allowed:
            raise ValueError("图片必须来自本站或使用 Base64 data URL")
        return value


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def require_admin(authorization: Annotated[str | None, Header()] = None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "需要管理员登录")
    token = authorization.removeprefix("Bearer ").strip()
    with db_session() as conn:
        conn.execute("DELETE FROM admin_sessions WHERE expires_at <= ?", (utc_now().isoformat(),))
        row = conn.execute(
            "SELECT 1 FROM admin_sessions WHERE token_hash = ? AND expires_at > ?",
            (token_hash(token), utc_now().isoformat()),
        ).fetchone()
    if row is None:
        raise HTTPException(401, "登录已过期，请重新登录")


Admin = Annotated[None, Depends(require_admin)]


def read_timeline() -> list[dict]:
    if not TIMELINE_PATH.exists():
        return []
    try:
        payload = json.loads(TIMELINE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(500, f"时间线数据无法读取：{exc}") from exc
    if isinstance(payload, list):
        return payload
    # Compatibility with the original TimelineJS structure.
    items = []
    for event in payload.get("events", []):
        start = event.get("start_date", {})
        text = event.get("text", {})
        media = event.get("media", {})
        try:
            date = f"{int(start['year']):04d}-{int(start.get('month', 1)):02d}-{int(start.get('day', 1)):02d}"
        except (KeyError, TypeError, ValueError):
            continue
        description = re.sub(r"<[^>]+>", "", str(text.get("text", ""))).strip()
        items.append(
            {
                "date": date,
                "title": str(text.get("headline", "珍贵回忆")),
                "description": description,
                "image": str(media.get("url", "")),
            }
        )
    return items


def write_timeline(items: list[dict]) -> None:
    temp_path = TIMELINE_PATH.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temp_path, TIMELINE_PATH)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/timeline")
def get_timeline():
    return sorted(read_timeline(), key=lambda item: item.get("date", ""))


@app.post("/api/timeline", status_code=201)
def add_timeline(item: TimelineCreate, _: Admin):
    with _timeline_lock:
        items = read_timeline()
        record = item.model_dump()
        record["id"] = secrets.token_hex(6)
        items.append(record)
        items.sort(key=lambda row: row.get("date", ""))
        write_timeline(items)
    return record


@app.get("/api/messages")
def get_messages():
    with db_session() as conn:
        rows = conn.execute(
            "SELECT id, nickname, content, created_at FROM messages ORDER BY id DESC LIMIT 200"
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/messages", status_code=201)
def add_message(message: MessageCreate):
    with db_session() as conn:
        cursor = conn.execute(
            "INSERT INTO messages (nickname, content) VALUES (?, ?)",
            (message.nickname, message.content),
        )
        row = conn.execute(
            "SELECT id, nickname, content, created_at FROM messages WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
    return dict(row)


@app.delete("/api/messages/{message_id}", status_code=204)
def delete_message(message_id: int, _: Admin):
    with db_session() as conn:
        cursor = conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    if cursor.rowcount == 0:
        raise HTTPException(404, "留言不存在")


@app.get("/api/wishlist")
def get_wishlist():
    with db_session() as conn:
        rows = conn.execute(
            "SELECT id, title, completed, completed_at FROM wishlist ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/wishlist/{wish_id}/toggle")
def toggle_wish(wish_id: int, _: Admin):
    with db_session() as conn:
        row = conn.execute("SELECT completed FROM wishlist WHERE id = ?", (wish_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "心愿不存在")
        completed = 0 if row["completed"] else 1
        completed_at = datetime.now().strftime("%Y-%m-%d %H:%M") if completed else None
        conn.execute(
            "UPDATE wishlist SET completed = ?, completed_at = ? WHERE id = ?",
            (completed, completed_at, wish_id),
        )
    return {"completed": completed, "completed_at": completed_at}


@app.post("/api/admin/login")
def admin_login(request: LoginRequest):
    with db_session() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'admin_password_hash'"
        ).fetchone()
        if row is None or not verify_password(request.password, row["value"]):
            raise HTTPException(401, "口令错误")
        token = secrets.token_urlsafe(32)
        expires = utc_now() + timedelta(hours=SESSION_HOURS)
        conn.execute(
            "INSERT INTO admin_sessions (token_hash, expires_at, created_at) VALUES (?, ?, ?)",
            (token_hash(token), expires.isoformat(), utc_now().isoformat()),
        )
    return {"token": token, "expires_at": expires.isoformat()}


@app.post("/api/admin/logout", status_code=204)
def admin_logout(
    _: Admin, authorization: Annotated[str | None, Header()] = None
):
    token = (authorization or "").removeprefix("Bearer ").strip()
    with db_session() as conn:
        conn.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (token_hash(token),))


@app.put("/api/admin/password", status_code=204)
def change_password(request: PasswordChange, _: Admin):
    with db_session() as conn:
        row = conn.execute(
            "SELECT value FROM app_settings WHERE key = 'admin_password_hash'"
        ).fetchone()
        if row is None or not verify_password(request.current_password, row["value"]):
            raise HTTPException(401, "当前口令错误")
        conn.execute(
            "UPDATE app_settings SET value = ? WHERE key = 'admin_password_hash'",
            (hash_password(request.new_password),),
        )
        conn.execute("DELETE FROM admin_sessions")


def safe_stem(filename: str) -> str:
    stem = Path(filename).stem.strip()[:50]
    stem = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", stem).strip("-_")
    return stem or "memory"


def image_signature_matches(content_type: str, content: bytes) -> bool:
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/gif":
        return content.startswith((b"GIF87a", b"GIF89a"))
    if content_type == "image/webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False


@app.post("/api/admin/upload", status_code=201)
async def upload_photo(_: Admin, file: UploadFile = File(...)):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(415, "仅支持 JPG、PNG、WebP 或 GIF 图片")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "图片不能超过 10MB")
    if not content:
        raise HTTPException(400, "图片内容为空")
    if not image_signature_matches(file.content_type, content):
        raise HTTPException(400, "文件内容与图片格式不匹配")
    suffix = ALLOWED_IMAGE_TYPES[file.content_type]
    filename = f"{safe_stem(file.filename or 'memory')}-{secrets.token_hex(4)}{suffix}"
    destination = PHOTOS_DIR / filename
    destination.write_bytes(content)
    return {"url": f"/photos/{filename}", "filename": filename}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/photos", StaticFiles(directory=PHOTOS_DIR), name="photos")


@app.get("/", include_in_schema=False)
@app.get("/admin", include_in_schema=False)
def serve_app():
    if not INDEX_PATH.exists():
        raise HTTPException(404, "index.html 不存在")
    return FileResponse(INDEX_PATH)
