from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import json
import logging
import os
import re
import secrets
import sqlite3
import tempfile
import threading
import time
import warnings
from collections import defaultdict, deque
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Iterator
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware


LOGGER = logging.getLogger("love_story")

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR))).expanduser().resolve()
DB_PATH = DATA_DIR / "database.db"
PHOTOS_DIR = DATA_DIR / "photos"
THUMBNAILS_DIR = PHOTOS_DIR / "thumbnails"
STATIC_DIR = BASE_DIR / "static"
INDEX_PATH = BASE_DIR / "index.html"
SESSION_COOKIE_NAME = "love_story_session"
MIB = 1024 * 1024


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true or false")


MAX_UPLOAD_BYTES = _env_int("MAX_UPLOAD_BYTES", 5 * MIB, 64 * 1024, 20 * MIB)
MAX_REQUEST_BODY_BYTES = _env_int(
    "MAX_REQUEST_BODY_BYTES", 6 * MIB, MAX_UPLOAD_BYTES, 24 * MIB
)
MAX_IMAGE_PIXELS = _env_int("MAX_IMAGE_PIXELS", 20_000_000, 1_000_000, 40_000_000)
SESSION_HOURS = _env_int("SESSION_HOURS", 12, 1, 168)
COOKIE_SECURE = _env_bool("COOKIE_SECURE", True)
PUBLIC_ORIGIN = os.getenv("PUBLIC_ORIGIN", "").strip().rstrip("/")
TRUSTED_HOSTS = [
    host.strip()
    for host in os.getenv("TRUSTED_HOSTS", "127.0.0.1,localhost,testserver").split(",")
    if host.strip()
]

DEFAULT_WISHES = (
    "去大理感受慢生活",
    "一起去冰岛看极光",
    "看一场喜欢的演唱会",
    "共同养一只可爱的小猫咪",
    "一起去海边看日出日落",
    "去一次迪士尼乐园",
)
ALLOWED_UPLOAD_TYPES = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_data_lock = threading.RLock()
_upload_semaphore = asyncio.Semaphore(1)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(value: datetime | None = None) -> str:
    current = (value or utc_now()).astimezone(timezone.utc)
    return current.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?", normalized):
        normalized = normalized.replace(" ", "T") + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_timestamp(value: str | None) -> str | None:
    parsed = parse_timestamp(value)
    return utc_iso(parsed) if parsed else value


def db_connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


@contextmanager
def db_session() -> Iterator[sqlite3.Connection]:
    connection = db_connect()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    rounds = 310_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, expected_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds)
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (AttributeError, TypeError, ValueError):
        return False


def validate_password_strength(password: str) -> str:
    if len(password) < 12:
        raise ValueError("新口令至少需要 12 个字符")
    if len(password) > 128:
        raise ValueError("口令不能超过 128 个字符")
    lowered = password.casefold()
    compact = re.sub(r"\s+", "", lowered)
    forbidden = {
        "love2022",
        "password123",
        "123456789012",
        "qwertyuiop12",
        "admin12345678",
    }
    if compact in forbidden or compact.startswith("replace_") or "replacewith" in compact:
        raise ValueError("不能使用默认口令、常见弱口令或配置占位符")
    if len(set(password)) < 6:
        raise ValueError("口令变化过少，请使用更长的随机口令或密码短语")
    return password


def _is_placeholder_password(password: str | None) -> bool:
    if not password:
        return False
    normalized = re.sub(r"[^a-z]", "", password.casefold())
    return password.strip().upper().startswith("REPLACE_") or "replacewith" in normalized


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}


def _get_setting(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute(
        "SELECT value FROM app_settings WHERE key = ?", (key,)
    ).fetchone()
    return row["value"] if row else None


def _set_setting(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        """
        INSERT INTO app_settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def _credential_version(connection: sqlite3.Connection) -> int:
    raw = _get_setting(connection, "admin_credential_version")
    try:
        return max(1, int(raw or "1"))
    except ValueError:
        return 1


def _migrate_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nickname TEXT NOT NULL CHECK(length(nickname) BETWEEN 1 AND 30),
            content TEXT NOT NULL CHECK(length(content) BETWEEN 1 AND 500),
            created_at TEXT NOT NULL
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
        CREATE TABLE IF NOT EXISTS timeline (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            image TEXT NOT NULL DEFAULT '',
            thumbnail TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS uploads (
            path TEXT PRIMARY KEY,
            thumbnail_path TEXT NOT NULL,
            original_name TEXT NOT NULL,
            byte_size INTEGER NOT NULL,
            width INTEGER NOT NULL,
            height INTEGER NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_admin_sessions_expires
            ON admin_sessions(expires_at);
        CREATE INDEX IF NOT EXISTS idx_timeline_date ON timeline(date);
        """
    )
    session_columns = _table_columns(connection, "admin_sessions")
    if "credential_version" not in session_columns:
        connection.execute(
            "ALTER TABLE admin_sessions ADD COLUMN credential_version INTEGER NOT NULL DEFAULT 1"
        )


def _migrate_timestamps(connection: sqlite3.Connection) -> None:
    for row in connection.execute("SELECT id, created_at FROM messages").fetchall():
        normalized = normalize_timestamp(row["created_at"])
        if normalized and normalized != row["created_at"]:
            connection.execute(
                "UPDATE messages SET created_at = ? WHERE id = ?", (normalized, row["id"])
            )
    for row in connection.execute(
        "SELECT id, completed_at FROM wishlist WHERE completed_at IS NOT NULL"
    ).fetchall():
        normalized = normalize_timestamp(row["completed_at"])
        if normalized and normalized != row["completed_at"]:
            connection.execute(
                "UPDATE wishlist SET completed_at = ? WHERE id = ?", (normalized, row["id"])
            )


def _clean_text(value: Any, fallback: str, maximum: int) -> str:
    cleaned = html.unescape(re.sub(r"<[^>]+>", "", str(value or ""))).strip()
    return (cleaned or fallback)[:maximum]


def validate_internal_image_path(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return ""
    if len(cleaned) > 512:
        raise ValueError("图片路径不能超过 512 个字符")
    if cleaned.startswith("data:"):
        raise ValueError("不再支持 Base64 data URL，请先上传图片")
    if "\\" in cleaned or any(ord(character) < 32 for character in cleaned):
        raise ValueError("图片路径格式不正确")
    parsed = urlsplit(cleaned)
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("图片只能使用本站 /static/ 或 /photos/ 路径")
    if not cleaned.startswith(("/static/", "/photos/")):
        raise ValueError("图片只能使用本站 /static/ 或 /photos/ 路径")
    pure_path = PurePosixPath(cleaned)
    if ".." in pure_path.parts or "." in pure_path.parts or "//" in cleaned:
        raise ValueError("图片路径不能包含目录跳转")
    if pure_path.name in {"", ".", ".."}:
        raise ValueError("图片路径必须指向文件")
    return cleaned


def _legacy_image_path(value: Any, source: Path) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("data:image/"):
        LOGGER.warning("Skipping legacy Base64 image while importing %s", source)
        return ""
    try:
        return validate_internal_image_path(raw)
    except ValueError:
        LOGGER.warning("Skipping unsupported legacy image path from %s", source)
        return ""


def _legacy_timeline_rows(payload: Any, source: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            date_value = str(item.get("date", "")).strip()
            try:
                datetime.strptime(date_value, "%Y-%m-%d")
            except ValueError:
                LOGGER.warning("Skipping legacy timeline row with invalid date in %s", source)
                continue
            rows.append(
                {
                    "id": str(item.get("id") or "").strip(),
                    "date": date_value,
                    "title": _clean_text(item.get("title"), "珍贵回忆", 80),
                    "description": _clean_text(item.get("description"), "共同走过的时光", 1000),
                    "image": _legacy_image_path(item.get("image"), source),
                    "thumbnail": _legacy_image_path(item.get("thumbnail"), source),
                }
            )
        return rows

    if not isinstance(payload, dict):
        return rows
    for event in payload.get("events", []):
        if not isinstance(event, dict):
            continue
        start = event.get("start_date", {})
        text = event.get("text", {})
        media = event.get("media", {})
        try:
            date_value = (
                f"{int(start['year']):04d}-{int(start.get('month', 1)):02d}-"
                f"{int(start.get('day', 1)):02d}"
            )
            datetime.strptime(date_value, "%Y-%m-%d")
        except (KeyError, TypeError, ValueError):
            continue
        rows.append(
            {
                "id": "",
                "date": date_value,
                "title": _clean_text(text.get("headline"), "珍贵回忆", 80),
                "description": _clean_text(text.get("text"), "共同走过的时光", 1000),
                "image": _legacy_image_path(media.get("url"), source),
                "thumbnail": "",
            }
        )
    return rows


def _import_legacy_timeline(connection: sqlite3.Connection) -> int:
    if connection.execute("SELECT 1 FROM timeline LIMIT 1").fetchone():
        return 0
    candidates = [DATA_DIR / "timeline.json", BASE_DIR / "timeline.json"]
    source = next((path for path in candidates if path.exists()), None)
    if source is None:
        return 0
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to import legacy timeline from {source}: {exc}") from exc

    rows = _legacy_timeline_rows(payload, source)
    seen_ids: set[str] = set()
    now = utc_iso()
    for row in rows:
        candidate = row["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", candidate) or candidate in seen_ids:
            candidate = secrets.token_hex(8)
            while candidate in seen_ids:
                candidate = secrets.token_hex(8)
        seen_ids.add(candidate)
        connection.execute(
            """
            INSERT INTO timeline
                (id, date, title, description, image, thumbnail, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate,
                row["date"],
                row["title"],
                row["description"],
                row["image"],
                row["thumbnail"],
                now,
                now,
            ),
        )
    if rows:
        LOGGER.info("Imported %d timeline rows from %s", len(rows), source)
    return len(rows)


def _prune_sessions(connection: sqlite3.Connection) -> None:
    now = utc_now()
    expired = []
    for row in connection.execute("SELECT token_hash, expires_at FROM admin_sessions"):
        expires_at = parse_timestamp(row["expires_at"])
        if expires_at is None or expires_at <= now:
            expired.append((row["token_hash"],))
    if expired:
        connection.executemany(
            "DELETE FROM admin_sessions WHERE token_hash = ?", expired
        )


def initialize_database(admin_password: str | None = None) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
    configured_password = admin_password if admin_password is not None else os.getenv("ADMIN_PASSWORD")
    if _is_placeholder_password(configured_password):
        raise RuntimeError("ADMIN_PASSWORD still contains a REPLACE_* placeholder")

    with _data_lock, db_session() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        _migrate_schema(connection)
        _set_setting(connection, "admin_credential_version", str(_credential_version(connection)))

        password_hash = _get_setting(connection, "admin_password_hash")
        rotated_default = False
        if password_hash is None:
            if not configured_password:
                raise RuntimeError(
                    "A new database requires a strong ADMIN_PASSWORD or init_db.py --password"
                )
            try:
                validate_password_strength(configured_password)
            except ValueError as exc:
                raise RuntimeError(f"ADMIN_PASSWORD is not strong enough: {exc}") from exc
            _set_setting(connection, "admin_password_hash", hash_password(configured_password))
        elif verify_password("love2022", password_hash):
            if not configured_password:
                raise RuntimeError(
                    "The legacy default admin password is active; set a strong ADMIN_PASSWORD"
                )
            try:
                validate_password_strength(configured_password)
            except ValueError as exc:
                raise RuntimeError(f"ADMIN_PASSWORD is not strong enough: {exc}") from exc
            _set_setting(connection, "admin_password_hash", hash_password(configured_password))
            _set_setting(
                connection,
                "admin_credential_version",
                str(_credential_version(connection) + 1),
            )
            connection.execute("DELETE FROM admin_sessions")
            rotated_default = True

        if connection.execute("SELECT COUNT(*) FROM wishlist").fetchone()[0] == 0:
            connection.executemany(
                "INSERT INTO wishlist (title) VALUES (?)",
                ((title,) for title in DEFAULT_WISHES),
            )
        if connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0:
            connection.executemany(
                "INSERT INTO messages (nickname, content, created_at) VALUES (?, ?, ?)",
                (
                    ("李欣", "雅婷，我们要一直幸福下去。", "2022-12-25T04:00:00Z"),
                    ("王雅婷", "有你的每一天都是圣诞节。", "2022-12-25T04:05:00Z"),
                ),
            )

        _migrate_timestamps(connection)
        imported = _import_legacy_timeline(connection)
        _prune_sessions(connection)
        connection.execute("PRAGMA optimize")
    return {"timeline_imported": imported, "default_password_rotated": rotated_default}


def reset_admin_password(new_password: str) -> None:
    validate_password_strength(new_password)
    with _data_lock, db_session() as connection:
        _migrate_schema(connection)
        _set_setting(connection, "admin_password_hash", hash_password(new_password))
        _set_setting(
            connection,
            "admin_credential_version",
            str(_credential_version(connection) + 1),
        )
        connection.execute("DELETE FROM admin_sessions")


def _resolve_internal_file(url_path: str) -> Path | None:
    try:
        normalized = validate_internal_image_path(url_path)
    except ValueError:
        return None
    if normalized.startswith("/static/"):
        root = STATIC_DIR.resolve()
        relative = normalized.removeprefix("/static/")
    else:
        root = PHOTOS_DIR.resolve()
        relative = normalized.removeprefix("/photos/")
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _prepare_rgb(image: Image.Image) -> Image.Image:
    transposed = ImageOps.exif_transpose(image)
    if transposed.mode in {"RGBA", "LA"} or "transparency" in transposed.info:
        rgba = transposed.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return transposed.convert("RGB")


def _save_thumbnail(source: Path, destination: Path) -> tuple[int, int]:
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(source) as opened:
            if opened.width * opened.height > MAX_IMAGE_PIXELS:
                raise ValueError("image pixel count exceeds the configured limit")
            image = _prepare_rgb(opened)
            original_size = image.size
            image.thumbnail((640, 640), Image.Resampling.LANCZOS)
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            image.save(temporary, format="WEBP", quality=76, method=4)
            os.replace(temporary, destination)
            return original_size


def rebuild_missing_thumbnails(limit: int | None = None) -> dict[str, int]:
    THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
    with db_session() as connection:
        rows = connection.execute(
            """
            SELECT id, image FROM timeline
            WHERE image <> '' AND (thumbnail IS NULL OR thumbnail = '')
            ORDER BY date, id
            """
        ).fetchall()
    if limit is not None:
        rows = rows[: max(0, limit)]

    created = 0
    skipped = 0
    for row in rows:
        source = _resolve_internal_file(row["image"])
        if source is None or not source.is_file():
            skipped += 1
            continue
        fingerprint = hashlib.sha256(row["image"].encode("utf-8")).hexdigest()[:16]
        destination = THUMBNAILS_DIR / f"legacy-{fingerprint}.webp"
        try:
            if not destination.exists():
                _save_thumbnail(source, destination)
            thumbnail_url = f"/photos/thumbnails/{destination.name}"
            with _data_lock, db_session() as connection:
                connection.execute(
                    "UPDATE timeline SET thumbnail = ?, updated_at = ? WHERE id = ?",
                    (thumbnail_url, utc_iso(), row["id"]),
                )
            created += 1
        except (OSError, UnidentifiedImageError, ValueError, Image.DecompressionBombError) as exc:
            LOGGER.warning("Unable to create thumbnail for %s: %s", row["image"], exc)
            skipped += 1
    return {"created": created, "skipped": skipped}


def cleanup_orphan_uploads(grace_hours: int = 24) -> dict[str, int]:
    cutoff = utc_now() - timedelta(hours=max(0, grace_hours))
    removed = 0
    with _data_lock, db_session() as connection:
        references = {
            value
            for row in connection.execute("SELECT image, thumbnail FROM timeline")
            for value in (row["image"], row["thumbnail"])
            if value
        }
        uploads = connection.execute(
            "SELECT path, thumbnail_path, created_at FROM uploads"
        ).fetchall()
        for upload in uploads:
            created_at = parse_timestamp(upload["created_at"])
            if upload["path"] in references or upload["thumbnail_path"] in references:
                continue
            if created_at and created_at > cutoff:
                continue
            for path_value in (upload["path"], upload["thumbnail_path"]):
                candidate = _resolve_internal_file(path_value)
                if candidate and candidate.is_file():
                    candidate.unlink(missing_ok=True)
            connection.execute("DELETE FROM uploads WHERE path = ?", (upload["path"],))
            removed += 1
    return {"removed": removed}


def _cleanup_uploaded_path_if_unreferenced(path_value: str) -> None:
    if not path_value.startswith("/photos/"):
        return
    with _data_lock, db_session() as connection:
        referenced = connection.execute(
            """
            SELECT 1 FROM timeline
            WHERE image IN (?, ?) OR thumbnail IN (?, ?)
            LIMIT 1
            """,
            (path_value, path_value, path_value, path_value),
        ).fetchone()
        if referenced:
            return
        upload = connection.execute(
            "SELECT path, thumbnail_path FROM uploads WHERE path = ? OR thumbnail_path = ?",
            (path_value, path_value),
        ).fetchone()
        if not upload:
            return
        connection.execute("DELETE FROM uploads WHERE path = ?", (upload["path"],))
    for candidate_value in (upload["path"], upload["thumbnail_path"]):
        candidate = _resolve_internal_file(candidate_value)
        if candidate and candidate.is_file():
            candidate.unlink(missing_ok=True)


def initialize_application() -> dict[str, Any]:
    result = initialize_database()
    cleanup_orphan_uploads(grace_hours=24)
    return result


class MessageCreate(BaseModel):
    nickname: str = Field(min_length=1, max_length=30)
    content: str = Field(min_length=1, max_length=500)

    @field_validator("nickname", "content")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("内容不能为空")
        return cleaned


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def strong_new_password(cls, value: str) -> str:
        return validate_password_strength(value)


class TimelinePayload(BaseModel):
    date: str
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1000)
    image: str = Field(default="", max_length=512)
    thumbnail: str = Field(default="", max_length=512)

    @field_validator("date")
    @classmethod
    def valid_date(cls, value: str) -> str:
        datetime.strptime(value, "%Y-%m-%d")
        return value

    @field_validator("title", "description")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("内容不能为空")
        return cleaned

    @field_validator("image", "thumbnail")
    @classmethod
    def valid_image(cls, value: str) -> str:
        return validate_internal_image_path(value)


class TimelineCreate(TimelinePayload):
    pass


class TimelineUpdate(TimelinePayload):
    pass


class WishlistUpdate(BaseModel):
    completed: bool


class RequestBodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(self, app: Any, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope.get("method") not in UNSAFE_METHODS:
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                content_length = int(raw_length)
            except ValueError:
                response = JSONResponse({"detail": "Content-Length 格式不正确"}, status_code=400)
                await response(scope, receive, send)
                return
            if content_length < 0:
                response = JSONResponse({"detail": "Content-Length 格式不正确"}, status_code=400)
                await response(scope, receive, send)
                return
            if content_length > self.max_body_bytes:
                response = JSONResponse({"detail": "请求体过大"}, status_code=413)
                await response(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise RequestBodyTooLarge
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLarge:
            response = JSONResponse({"detail": "请求体过大"}, status_code=413)
            await response(scope, receive, send)


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._checks = 0

    def check(self, bucket: str, client: str, limit: int, period: float) -> int | None:
        now = time.monotonic()
        cutoff = now - period
        key = (bucket, client)
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return max(1, int(period - (now - events[0])) + 1)
            events.append(now)
            self._checks += 1
            if self._checks % 256 == 0:
                empty_or_old = [
                    event_key
                    for event_key, values in self._events.items()
                    if not values or values[-1] <= cutoff
                ]
                for event_key in empty_or_old:
                    self._events.pop(event_key, None)
        return None


RATE_LIMITER = SlidingWindowRateLimiter()
RATE_LIMITS = {
    ("POST", "/api/admin/login"): ("login", 5, 60.0),
    ("POST", "/api/messages"): ("messages", 10, 60.0),
    ("POST", "/api/admin/upload"): ("upload", 6, 60.0),
}


def _normalize_origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("origin is invalid")
    host = parsed.hostname.lower()
    port = parsed.port
    if port and not ((parsed.scheme == "http" and port == 80) or (parsed.scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    return f"{parsed.scheme.lower()}://{host}"


def _request_client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@dataclass(frozen=True)
class AdminSession:
    token_hash: str
    expires_at: str


def _request_token(request: Request) -> str:
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME, "").strip()
    if cookie_token:
        return cookie_token
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    return ""


def require_admin(request: Request) -> AdminSession:
    token = _request_token(request)
    if not token:
        raise HTTPException(401, "需要管理员登录")
    digest = token_hash(token)
    now = utc_now()
    with db_session() as connection:
        _prune_sessions(connection)
        row = connection.execute(
            """
            SELECT expires_at, credential_version
            FROM admin_sessions WHERE token_hash = ?
            """,
            (digest,),
        ).fetchone()
        if row is None:
            raise HTTPException(401, "登录已过期，请重新登录")
        expires_at = parse_timestamp(row["expires_at"])
        if expires_at is None or expires_at <= now:
            connection.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (digest,))
            raise HTTPException(401, "登录已过期，请重新登录")
        if int(row["credential_version"]) != _credential_version(connection):
            connection.execute("DELETE FROM admin_sessions WHERE token_hash = ?", (digest,))
            raise HTTPException(401, "登录已失效，请重新登录")
    return AdminSession(token_hash=digest, expires_at=utc_iso(expires_at))


Admin = Annotated[AdminSession, Depends(require_admin)]


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_application()
    yield


app = FastAPI(
    title="李欣与王雅婷的恋爱纪念站",
    version="4.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)
app.add_middleware(BodySizeLimitMiddleware, max_body_bytes=MAX_REQUEST_BODY_BYTES)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=TRUSTED_HOSTS or ["*"])


@app.middleware("http")
async def request_policy(request: Request, call_next: Any) -> Response:
    if request.method in UNSAFE_METHODS:
        origin = request.headers.get("origin")
        if PUBLIC_ORIGIN:
            try:
                valid_origin = origin is not None and _normalize_origin(origin) == _normalize_origin(PUBLIC_ORIGIN)
            except ValueError:
                valid_origin = False
            if not valid_origin:
                return JSONResponse({"detail": "请求来源不受信任"}, status_code=403)

        policy = RATE_LIMITS.get((request.method, request.url.path))
        if policy:
            bucket, limit, period = policy
            retry_after = RATE_LIMITER.check(bucket, _request_client(request), limit, period)
            if retry_after is not None:
                return JSONResponse(
                    {"detail": "请求过于频繁，请稍后重试"},
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                )

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' blob:; media-src 'self'; connect-src 'self'; "
        "object-src 'none'; base-uri 'self'; frame-ancestors 'self'; form-action 'self'"
    )
    if request.url.path.startswith("/api/admin"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    try:
        with db_session() as connection:
            connection.execute("SELECT 1").fetchone()
    except sqlite3.Error as exc:
        raise HTTPException(503, "数据库暂不可用") from exc
    return {"status": "ok", "version": app.version}


def _timeline_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "date": row["date"],
        "title": row["title"],
        "description": row["description"],
        "image": row["image"],
        "thumbnail": row["thumbnail"],
    }


@app.get("/api/timeline")
def get_timeline() -> list[dict[str, Any]]:
    with db_session() as connection:
        rows = connection.execute(
            """
            SELECT id, date, title, description, image, thumbnail
            FROM timeline ORDER BY date, id
            """
        ).fetchall()
    return [_timeline_dict(row) for row in rows]


@app.post("/api/timeline", status_code=201)
def add_timeline(item: TimelineCreate, _: Admin) -> dict[str, Any]:
    record = item.model_dump()
    record["id"] = secrets.token_hex(8)
    now = utc_iso()
    with _data_lock, db_session() as connection:
        connection.execute(
            """
            INSERT INTO timeline
                (id, date, title, description, image, thumbnail, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"],
                record["date"],
                record["title"],
                record["description"],
                record["image"],
                record["thumbnail"],
                now,
                now,
            ),
        )
    return record


@app.put("/api/admin/timeline/{timeline_id}")
def update_timeline(timeline_id: str, item: TimelineUpdate, _: Admin) -> dict[str, Any]:
    with _data_lock, db_session() as connection:
        existing = connection.execute(
            "SELECT image, thumbnail FROM timeline WHERE id = ?", (timeline_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(404, "这条时光记录不存在")
        payload = item.model_dump()
        connection.execute(
            """
            UPDATE timeline
            SET date = ?, title = ?, description = ?, image = ?, thumbnail = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                payload["date"],
                payload["title"],
                payload["description"],
                payload["image"],
                payload["thumbnail"],
                utc_iso(),
                timeline_id,
            ),
        )
    for previous in (existing["image"], existing["thumbnail"]):
        if previous and previous not in {payload["image"], payload["thumbnail"]}:
            _cleanup_uploaded_path_if_unreferenced(previous)
    return {"id": timeline_id, **payload}


@app.delete("/api/admin/timeline/{timeline_id}", status_code=204)
def delete_timeline(timeline_id: str, _: Admin) -> Response:
    with _data_lock, db_session() as connection:
        existing = connection.execute(
            "SELECT image, thumbnail FROM timeline WHERE id = ?", (timeline_id,)
        ).fetchone()
        if existing is None:
            raise HTTPException(404, "这条时光记录不存在")
        connection.execute("DELETE FROM timeline WHERE id = ?", (timeline_id,))
    for previous in (existing["image"], existing["thumbnail"]):
        if previous:
            _cleanup_uploaded_path_if_unreferenced(previous)
    return Response(status_code=204)


@app.get("/api/messages")
def get_messages() -> list[dict[str, Any]]:
    with db_session() as connection:
        rows = connection.execute(
            """
            SELECT id, nickname, content, created_at
            FROM messages ORDER BY id DESC LIMIT 200
            """
        ).fetchall()
    return [
        {
            "id": row["id"],
            "nickname": row["nickname"],
            "content": row["content"],
            "created_at": normalize_timestamp(row["created_at"]),
        }
        for row in rows
    ]


@app.post("/api/messages", status_code=201)
def add_message(message: MessageCreate) -> dict[str, Any]:
    created_at = utc_iso()
    with db_session() as connection:
        cursor = connection.execute(
            "INSERT INTO messages (nickname, content, created_at) VALUES (?, ?, ?)",
            (message.nickname, message.content, created_at),
        )
    return {
        "id": cursor.lastrowid,
        "nickname": message.nickname,
        "content": message.content,
        "created_at": created_at,
    }


@app.delete("/api/messages/{message_id}", status_code=204)
def delete_message(message_id: int, _: Admin) -> Response:
    with db_session() as connection:
        cursor = connection.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    if cursor.rowcount == 0:
        raise HTTPException(404, "留言不存在")
    return Response(status_code=204)


def _wishlist_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "completed": bool(row["completed"]),
        "completed_at": normalize_timestamp(row["completed_at"]),
    }


@app.get("/api/wishlist")
def get_wishlist() -> list[dict[str, Any]]:
    with db_session() as connection:
        rows = connection.execute(
            "SELECT id, title, completed, completed_at FROM wishlist ORDER BY id"
        ).fetchall()
    return [_wishlist_dict(row) for row in rows]


@app.patch("/api/wishlist/{wish_id}")
def update_wish(wish_id: int, request: WishlistUpdate, _: Admin) -> dict[str, Any]:
    with db_session() as connection:
        row = connection.execute(
            "SELECT id, title, completed, completed_at FROM wishlist WHERE id = ?",
            (wish_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "心愿不存在")
        desired = bool(request.completed)
        if bool(row["completed"]) != desired:
            completed_at = utc_iso() if desired else None
            connection.execute(
                "UPDATE wishlist SET completed = ?, completed_at = ? WHERE id = ?",
                (int(desired), completed_at, wish_id),
            )
            row = connection.execute(
                "SELECT id, title, completed, completed_at FROM wishlist WHERE id = ?",
                (wish_id,),
            ).fetchone()
    return _wishlist_dict(row)


@app.post("/api/admin/login")
def admin_login(login: LoginRequest, response: Response) -> dict[str, Any]:
    with _data_lock, db_session() as connection:
        password_hash = _get_setting(connection, "admin_password_hash")
        if password_hash is None or not verify_password(login.password, password_hash):
            raise HTTPException(401, "口令错误")
        _prune_sessions(connection)
        token = secrets.token_urlsafe(32)
        expires_at = utc_now() + timedelta(hours=SESSION_HOURS)
        connection.execute(
            """
            INSERT INTO admin_sessions
                (token_hash, expires_at, created_at, credential_version)
            VALUES (?, ?, ?, ?)
            """,
            (
                token_hash(token),
                utc_iso(expires_at),
                utc_iso(),
                _credential_version(connection),
            ),
        )
        sessions = connection.execute(
            "SELECT token_hash FROM admin_sessions ORDER BY created_at DESC"
        ).fetchall()
        if len(sessions) > 10:
            connection.executemany(
                "DELETE FROM admin_sessions WHERE token_hash = ?",
                ((row["token_hash"],) for row in sessions[10:]),
            )
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_HOURS * 3600,
        expires=expires_at,
        path="/",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )
    return {"authenticated": True, "expires_at": utc_iso(expires_at)}


@app.get("/api/admin/session")
def admin_session(session: Admin) -> dict[str, Any]:
    return {"authenticated": True, "expires_at": session.expires_at}


@app.post("/api/admin/logout", status_code=204)
def admin_logout(request: Request, response: Response) -> Response:
    token = _request_token(request)
    if token:
        with db_session() as connection:
            connection.execute(
                "DELETE FROM admin_sessions WHERE token_hash = ?", (token_hash(token),)
            )
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )
    response.status_code = 204
    return response


@app.put("/api/admin/password", status_code=204)
def change_password(change: PasswordChange, _: Admin) -> Response:
    with _data_lock, db_session() as connection:
        current_hash = _get_setting(connection, "admin_password_hash")
        if current_hash is None or not verify_password(change.current_password, current_hash):
            raise HTTPException(401, "当前口令错误")
        _set_setting(connection, "admin_password_hash", hash_password(change.new_password))
        _set_setting(
            connection,
            "admin_credential_version",
            str(_credential_version(connection) + 1),
        )
        connection.execute("DELETE FROM admin_sessions")
    response = Response(status_code=204)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )
    return response


def safe_stem(filename: str) -> str:
    stem = Path(filename).stem.strip()[:50]
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", stem).strip("-_")
    return cleaned or "memory"


def _process_uploaded_image(
    file_object: tempfile.SpooledTemporaryFile[bytes],
    content_type: str,
    original_name: str,
) -> dict[str, Any]:
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    token = secrets.token_hex(8)
    stem = safe_stem(original_name)
    image_name = f"{stem}-{token}.webp"
    thumbnail_name = f"{stem}-{token}-thumb.webp"
    destination = PHOTOS_DIR / image_name
    thumbnail_destination = THUMBNAILS_DIR / thumbnail_name
    destination_temp = destination.with_suffix(".webp.tmp")
    thumbnail_temp = thumbnail_destination.with_suffix(".webp.tmp")

    try:
        file_object.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(file_object) as opened:
                actual_format = (opened.format or "").upper()
                expected_format = ALLOWED_UPLOAD_TYPES[content_type]
                if actual_format != expected_format:
                    raise ValueError("文件内容与声明的图片格式不一致")
                if opened.width * opened.height > MAX_IMAGE_PIXELS:
                    raise ValueError("图片像素过大")
                image = _prepare_rgb(opened)
                width, height = image.size
                image.save(destination_temp, format="WEBP", quality=84, method=4)
                thumbnail = image.copy()
                thumbnail.thumbnail((640, 640), Image.Resampling.LANCZOS)
                thumbnail.save(thumbnail_temp, format="WEBP", quality=76, method=4)
        os.replace(destination_temp, destination)
        os.replace(thumbnail_temp, thumbnail_destination)
    except Exception:
        destination_temp.unlink(missing_ok=True)
        thumbnail_temp.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        thumbnail_destination.unlink(missing_ok=True)
        raise

    return {
        "url": f"/photos/{image_name}",
        "thumbnail_url": f"/photos/thumbnails/{thumbnail_name}",
        "filename": image_name,
        "width": width,
        "height": height,
        "byte_size": destination.stat().st_size,
    }


@app.post("/api/admin/upload", status_code=201)
async def upload_photo(_: Admin, file: UploadFile = File(...)) -> dict[str, Any]:
    if file.content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(415, "仅支持 JPG、PNG 或 WebP 图片")

    async with _upload_semaphore:
        spooled: tempfile.SpooledTemporaryFile[bytes] = tempfile.SpooledTemporaryFile(
            max_size=MIB, mode="w+b"
        )
        total = 0
        try:
            while chunk := await file.read(64 * 1024):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "图片不能超过 5 MiB")
                spooled.write(chunk)
            if total == 0:
                raise HTTPException(400, "图片内容为空")
            try:
                result = await asyncio.to_thread(
                    _process_uploaded_image,
                    spooled,
                    file.content_type,
                    file.filename or "memory",
                )
            except (
                UnidentifiedImageError,
                OSError,
                ValueError,
                Image.DecompressionBombError,
                Image.DecompressionBombWarning,
            ) as exc:
                raise HTTPException(400, str(exc) or "图片无法安全解析") from exc
        finally:
            spooled.close()
            await file.close()

    try:
        with db_session() as connection:
            connection.execute(
                """
                INSERT INTO uploads
                    (path, thumbnail_path, original_name, byte_size, width, height, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result["url"],
                    result["thumbnail_url"],
                    (file.filename or "memory")[:255],
                    result["byte_size"],
                    result["width"],
                    result["height"],
                    utc_iso(),
                ),
            )
    except Exception:
        for path_value in (result["url"], result["thumbnail_url"]):
            candidate = _resolve_internal_file(path_value)
            if candidate:
                candidate.unlink(missing_ok=True)
        raise
    return result


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/photos", StaticFiles(directory=PHOTOS_DIR, check_dir=False), name="photos")


@app.get("/", include_in_schema=False)
@app.get("/admin", include_in_schema=False)
def serve_app() -> FileResponse:
    if not INDEX_PATH.exists():
        raise HTTPException(404, "index.html 不存在")
    return FileResponse(INDEX_PATH)
