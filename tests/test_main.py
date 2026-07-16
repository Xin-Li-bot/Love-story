from __future__ import annotations

import importlib
import io
import json
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image


ADMIN_PASSWORD = "Correct-Horse-Battery-42"
NEW_ADMIN_PASSWORD = "Another-Long-Random-Phrase-73"
ORIGIN = "http://testserver"


def load_main(monkeypatch: pytest.MonkeyPatch, data_dir: Path, password: str | None = ADMIN_PASSWORD):
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("TRUSTED_HOSTS", "testserver,localhost,127.0.0.1")
    monkeypatch.setenv("COOKIE_SECURE", "false")
    monkeypatch.setenv("MAX_IMAGE_PIXELS", "20000000")
    monkeypatch.setenv("MAX_OUTPUT_DIMENSION", "2560")
    if password is None:
        monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("ADMIN_PASSWORD", password)
    sys.modules.pop("main", None)
    return importlib.import_module("main")


@pytest.fixture
def app_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    module = load_main(monkeypatch, tmp_path / "data")
    yield module
    sys.modules.pop("main", None)


def login(client: TestClient, password: str = ADMIN_PASSWORD):
    return client.post(
        "/api/admin/login",
        json={"password": password},
        headers={"Origin": ORIGIN},
    )


def test_fresh_database_requires_a_strong_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_main(monkeypatch, tmp_path / "missing-password", password=None)
    with pytest.raises(RuntimeError, match="requires a strong ADMIN_PASSWORD"):
        with TestClient(module.app, base_url=ORIGIN):
            pass


def test_placeholder_password_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_main(
        monkeypatch,
        tmp_path / "placeholder",
        password="REPLACE_WITH_A_NEW_LONG_RANDOM_PASSWORD_BEFORE_FIRST_START",
    )
    with pytest.raises(RuntimeError, match="REPLACE_"):
        with TestClient(module.app, base_url=ORIGIN):
            pass


def test_cookie_session_origin_and_password_invalidation(app_module) -> None:
    with TestClient(app_module.app, base_url=ORIGIN) as client:
        rejected = client.post("/api/admin/login", json={"password": ADMIN_PASSWORD})
        assert rejected.status_code == 403

        response = login(client)
        assert response.status_code == 200
        assert "token" not in response.json()
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie
        assert "SameSite=strict" in cookie
        assert "Secure" not in cookie

        session = client.get("/api/admin/session")
        assert session.status_code == 200
        assert session.json()["authenticated"] is True
        assert session.json()["expires_at"].endswith("Z")

        changed = client.put(
            "/api/admin/password",
            json={
                "current_password": ADMIN_PASSWORD,
                "new_password": NEW_ADMIN_PASSWORD,
            },
            headers={"Origin": ORIGIN},
        )
        assert changed.status_code == 204
        assert client.get("/api/admin/session").status_code == 401
        assert login(client).status_code == 401
        assert login(client, NEW_ADMIN_PASSWORD).status_code == 200


def test_legacy_default_password_is_rotated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_main(monkeypatch, tmp_path / "legacy-default")
    module.DATA_DIR.mkdir(parents=True)
    connection = sqlite3.connect(module.DB_PATH)
    connection.executescript(
        """
        CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE admin_sessions (
            token_hash TEXT PRIMARY KEY,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    connection.execute(
        "INSERT INTO app_settings (key, value) VALUES ('admin_password_hash', ?)",
        (module.hash_password("love2022"),),
    )
    connection.execute(
        "INSERT INTO admin_sessions VALUES ('stale', '2099-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
    )
    connection.commit()
    connection.close()

    with TestClient(module.app, base_url=ORIGIN) as client:
        assert login(client, "love2022").status_code == 401
        assert login(client).status_code == 200
    connection = sqlite3.connect(module.DB_PATH)
    assert connection.execute("SELECT COUNT(*) FROM admin_sessions").fetchone()[0] == 1
    connection.close()


def test_existing_custom_hash_starts_without_plaintext_environment_password(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_main(monkeypatch, tmp_path / "existing-custom", password=None)
    module.DATA_DIR.mkdir(parents=True)
    connection = sqlite3.connect(module.DB_PATH)
    connection.execute(
        "CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO app_settings (key, value) VALUES ('admin_password_hash', ?)",
        (module.hash_password(ADMIN_PASSWORD),),
    )
    connection.commit()
    connection.close()
    with TestClient(module.app, base_url=ORIGIN) as client:
        assert login(client).status_code == 200


def test_timeline_import_preserves_rows_but_drops_base64_and_never_rewrites_json(
    app_module,
) -> None:
    app_module.DATA_DIR.mkdir(parents=True)
    legacy_path = app_module.DATA_DIR / "timeline.json"
    legacy = [
        {
            "id": "memory-one",
            "date": "2024-01-02",
            "title": "第一段",
            "description": "保留站内图片",
            "image": "/static/20221225_告白.jpg",
        },
        {
            "id": "memory-two",
            "date": "2024-02-03",
            "title": "第二段",
            "description": "旧 Base64 只移除图片",
            "image": "data:image/png;base64,AAAA",
        },
    ]
    original_json = json.dumps(legacy, ensure_ascii=False, indent=2)
    legacy_path.write_text(original_json, encoding="utf-8")

    with TestClient(app_module.app, base_url=ORIGIN) as client:
        timeline = client.get("/api/timeline").json()
        assert [item["id"] for item in timeline] == ["memory-one", "memory-two"]
        assert timeline[0]["image"].startswith("/static/")
        assert timeline[1]["image"] == ""

        assert login(client).status_code == 200
        invalid = client.post(
            "/api/timeline",
            json={
                "date": "2024-03-04",
                "title": "拒绝 Base64",
                "description": "只允许站内短路径",
                "image": "data:image/png;base64,AAAA",
                "thumbnail": "",
            },
            headers={"Origin": ORIGIN},
        )
        assert invalid.status_code == 422
        created = client.post(
            "/api/timeline",
            json={
                "date": "2024-03-04",
                "title": "SQLite 记录",
                "description": "运行期不再写 JSON",
                "image": "",
                "thumbnail": "",
            },
            headers={"Origin": ORIGIN},
        )
        assert created.status_code == 201
    assert legacy_path.read_text(encoding="utf-8") == original_json


def test_wishlist_patch_is_idempotent_and_uses_utc(app_module) -> None:
    with TestClient(app_module.app, base_url=ORIGIN) as client:
        assert login(client).status_code == 200
        wish_id = client.get("/api/wishlist").json()[0]["id"]
        first = client.patch(
            f"/api/wishlist/{wish_id}",
            json={"completed": True},
            headers={"Origin": ORIGIN},
        )
        second = client.patch(
            f"/api/wishlist/{wish_id}",
            json={"completed": True},
            headers={"Origin": ORIGIN},
        )
        assert first.status_code == second.status_code == 200
        assert first.json()["completed"] is True
        assert second.json()["completed_at"] == first.json()["completed_at"]
        assert first.json()["completed_at"].endswith("Z")


def test_upload_reencodes_to_webp_strips_metadata_and_creates_thumbnail(app_module) -> None:
    source = Image.new("RGB", (1200, 800), "#ad7480")
    exif = Image.Exif()
    exif[0x010E] = "private description"
    payload = io.BytesIO()
    source.save(payload, format="JPEG", quality=90, exif=exif)

    with TestClient(app_module.app, base_url=ORIGIN) as client:
        assert login(client).status_code == 200
        response = client.post(
            "/api/admin/upload",
            files={"file": ("private-photo.jpg", payload.getvalue(), "image/jpeg")},
            headers={"Origin": ORIGIN},
        )
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["url"].endswith(".webp")
        assert result["thumbnail_url"].endswith("-thumb.webp")

    original_path = app_module.PHOTOS_DIR / result["url"].removeprefix("/photos/")
    thumbnail_path = app_module.PHOTOS_DIR / result["thumbnail_url"].removeprefix("/photos/")
    with Image.open(original_path) as encoded:
        assert encoded.format == "WEBP"
        assert not encoded.getexif()
        assert encoded.size == (1200, 800)
    with Image.open(thumbnail_path) as thumbnail:
        assert thumbnail.format == "WEBP"
        assert max(thumbnail.size) <= 640


def test_large_jpeg_is_downsampled_before_web_delivery(app_module) -> None:
    source = Image.new("RGB", (3060, 4080), "#668272")
    payload = io.BytesIO()
    source.save(payload, format="JPEG", quality=85)

    with TestClient(app_module.app, base_url=ORIGIN) as client:
        assert login(client).status_code == 200
        response = client.post(
            "/api/admin/upload",
            files={"file": ("phone-photo.jpg", payload.getvalue(), "image/jpeg")},
            headers={"Origin": ORIGIN},
        )
        assert response.status_code == 201, response.text
        result = response.json()
        assert max(result["width"], result["height"]) <= app_module.MAX_OUTPUT_DIMENSION


def test_request_body_limit_and_security_headers(app_module) -> None:
    with TestClient(app_module.app, base_url=ORIGIN) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.headers["x-content-type-options"] == "nosniff"
        assert "script-src 'self'" in health.headers["content-security-policy"]

        oversized = client.post(
            "/api/messages",
            content=b"{}",
            headers={
                "Origin": ORIGIN,
                "Content-Type": "application/json",
                "Content-Length": str(app_module.MAX_REQUEST_BODY_BYTES + 1),
            },
        )
        assert oversized.status_code == 413
