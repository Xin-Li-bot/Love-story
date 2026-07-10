import os
import json
import sqlite3
import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Love Story API", version="2.0.0")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
TIMELINE_PATH = os.path.join(BASE_DIR, "timeline.json")
PHOTOS_DIR = os.path.join(BASE_DIR, "photos")
STATIC_DIR = os.path.join(BASE_DIR, "static")

os.makedirs(PHOTOS_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

ADMIN_PASSWORD = "love"  # ← 部署后请修改


# ──────────────────────────── DB ────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
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


try:
    init_db()
except Exception as e:
    print(f"DB init warning: {e}")


# ──────────────────────────── Schemas ────────────────────────────
class MessageIn(BaseModel):
    nickname: str
    content: str


class LoginIn(BaseModel):
    password: str


class TimelineIn(BaseModel):
    password: str
    date: str
    title: str
    description: str
    image: Optional[str] = ""


# ──────────────────────────── Timeline ────────────────────────────
@app.get("/api/timeline")
def get_timeline():
    if not os.path.exists(TIMELINE_PATH):
        return []
    with open(TIMELINE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@app.post("/api/timeline")
def add_timeline(req: TimelineIn):
    if req.password != ADMIN_PASSWORD:
        raise HTTPException(401, "密码错误")
    data = []
    if os.path.exists(TIMELINE_PATH):
        with open(TIMELINE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    item = {"date": req.date, "title": req.title,
            "description": req.description, "image": req.image or ""}
    data.append(item)
    data.sort(key=lambda x: x.get("date", ""))
    with open(TIMELINE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"status": "success", "data": item}


# ──────────────────────────── Messages ────────────────────────────
@app.get("/api/messages")
def get_messages():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, nickname, content, created_at FROM messages ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/messages")
def add_message(msg: MessageIn):
    if not msg.nickname.strip() or not msg.content.strip():
        raise HTTPException(400, "昵称和内容不能为空")
    conn = get_db()
    conn.execute("INSERT INTO messages (nickname, content) VALUES (?, ?)",
                 (msg.nickname, msg.content))
    conn.commit()
    conn.close()
    return {"status": "success"}


@app.delete("/api/messages/{mid}")
def del_message(mid: int, password: str = Query(...)):
    if password != ADMIN_PASSWORD:
        raise HTTPException(401, "密码错误")
    conn = get_db()
    conn.execute("DELETE FROM messages WHERE id = ?", (mid,))
    conn.commit()
    conn.close()
    return {"status": "success"}


# ──────────────────────────── Wishlist ────────────────────────────
@app.get("/api/wishlist")
def get_wishlist():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, title, completed, completed_at FROM wishlist ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/wishlist/toggle/{wid}")
def toggle_wish(wid: int, password: str = Query(...)):
    if password != ADMIN_PASSWORD:
        raise HTTPException(401, "密码错误")
    conn = get_db()
    row = conn.execute("SELECT completed FROM wishlist WHERE id = ?", (wid,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "心愿不存在")
    new_val = 1 - row["completed"]
    comp_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M") if new_val else None
    conn.execute("UPDATE wishlist SET completed=?, completed_at=? WHERE id=?",
                 (new_val, comp_time, wid))
    conn.commit()
    conn.close()
    return {"status": "success", "completed": new_val, "completed_at": comp_time}


# ──────────────────────────── Admin ────────────────────────────
@app.post("/api/admin/login")
def admin_login(req: LoginIn):
    if req.password == ADMIN_PASSWORD:
        return {"status": "success"}
    raise HTTPException(401, "口令错误")


@app.post("/api/admin/upload")
async def upload_photo(file: UploadFile = File(...), password: str = Form(...)):
    if password != ADMIN_PASSWORD:
        raise HTTPException(401, "密码错误")
    import time
    name, ext = os.path.splitext(file.filename)
    fname = f"{name}_{int(time.time())}{ext}"
    with open(os.path.join(PHOTOS_DIR, fname), "wb") as f:
        f.write(await file.read())
    return {"status": "success", "url": f"/photos/{fname}"}


# ──────────────────────────── Static Mounts ────────────────────────────
app.mount("/photos", StaticFiles(directory=PHOTOS_DIR), name="photos")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ──────────────────────────── SPA Entry ────────────────────────────
def _serve_html():
    p = os.path.join(BASE_DIR, "index.html")
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>index.html not found</h1>"


@app.get("/", response_class=HTMLResponse)
def root():
    return _serve_html()


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    """访问 /admin 会自动打开管理员登录弹窗"""
    return _serve_html()
