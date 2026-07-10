"""初始化 database.db（留言板、心愿单、管理员口令）"""

import datetime as dt
import hashlib
import os
import secrets
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
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

    cur.execute("SELECT COUNT(*) FROM wishlist")
    if cur.fetchone()[0] == 0:
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

    cur.execute("SELECT COUNT(*) FROM messages")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO messages (nickname, content, created_at) VALUES (?, ?, ?)",
            [
                ("李欣", "雅婷，我们要一直幸福下去❤️", "2022-12-25 12:00:00"),
                ("王雅婷", "有你的每一天都是圣诞节🎄", "2022-12-25 12:05:00"),
            ],
        )

    cur.execute("SELECT password_hash FROM admin_credentials WHERE id = 1")
    if cur.fetchone() is None:
        raw_password = os.environ.get("LOVE_ADMIN_PASSWORD", "love")
        salt = secrets.token_hex(16)
        cur.execute(
            "INSERT INTO admin_credentials (id, password_hash, salt, updated_at) VALUES (1, ?, ?, ?)",
            (
                hash_password(raw_password, salt),
                salt,
                dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            ),
        )

    conn.commit()
    conn.close()
    print(f"database.db 初始化完成: {DB_PATH}")
    print("默认管理员口令来自环境变量 LOVE_ADMIN_PASSWORD；未设置时默认值为: love")


if __name__ == "__main__":
    init_db()
