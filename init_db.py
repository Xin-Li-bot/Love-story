"""独立运行脚本：初始化 SQLite 数据库（首次部署时执行）
用法：python init_db.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nickname TEXT NOT NULL,
        content  TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS wishlist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title      TEXT NOT NULL,
        completed  INTEGER DEFAULT 0,
        completed_at TEXT
    )""")

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

    conn.commit()
    conn.close()
    print("✅ 数据库初始化完成：", DB_PATH)


if __name__ == "__main__":
    init_db()
