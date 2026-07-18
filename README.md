# Love Story

一个由静态前端、FastAPI 和 SQLite 组成的恋爱纪念站。页面包含恋爱计时、时间线、相册、心愿单、留言板和管理后台；服务端负责数据持久化、管理员认证、图片上传及静态文件访问。

> [!IMPORTANT]
> 仓库里的代码和配置**不会自动替代现网部署**。合并或推送代码后，仍需在服务器创建新 release、安装 Python 3.12 依赖、切换 `current` 软链接、迁移数据并重启服务。
>
> `ADMIN_PASSWORD` 只应在部署时设置为一个全新的随机密码。仅修改仓库、仅修改环境文件但不执行实际部署，都不会改变线上数据库中已有的密码。部署流程会在明确提供新密码时轮换历史默认密码；如果数据库已经使用自定义密码，请通过交互式重置命令或后台“修改口令”操作，不要假设重启会覆盖它。

## 现网基线

以下是 2026-07-16 的实测快照，用于制定资源预算，不代表仓库已经自动部署到该机器：

| 项目 | 当前值 |
| --- | --- |
| 云平台 / 区域 | Aliyun，`us-west-1` |
| 系统 | Debian 11.3 |
| 规格 | 2 vCPU，标称 0.5 GiB；`free` 可见约 439 MiB |
| 磁盘 | 20 GiB，总计约 12 GiB 可用 |
| Swap | 已配置 2 GiB |
| 当前入口 | 仅 HTTP 公网 IP `47.251.117.78`，暂无域名/TLS |
| Nginx | `sites-available/default` 反代 `127.0.0.1:8000`，旧上传上限 12 MiB |
| 应用目录 | `/opt/love-story` |
| systemd | `love-story.service`，旧服务以 root 运行 |
| 旧环境文件 | `/etc/love-story.env`，当前仅有 `ADMIN_PASSWORD` |
| 旧内存限制 | `MemoryMax=220M` |
| 单 worker RSS | 约 36 MiB |
| 旧 Python | 3.9.2 |
| 当前运行数据 | 约 33 MiB |
| 当前时间线 | 38 条且均有 ID；28 张 `/static/`、8 张 `/photos/`、2 条无图；Base64 为 0 |

仓库的新依赖要求 Python 3.10 以上。现网已经通过 uv 0.11.28 将 Python 3.12.13 隔离安装在 `/opt/uv-python`；它不替换 Debian 的系统 Python 3.9。应用 release 继续使用各自的 `.venv`，并改为非 root 运行。当前默认管理员口令已经核验为无效，但部署时仍必须显式设置新密码。

当前无 TLS 时只能暂时使用以下现网值：

```dotenv
PUBLIC_ORIGIN=http://47.251.117.78
TRUSTED_HOSTS=47.251.117.78,127.0.0.1
COOKIE_SECURE=false
```

`COOKIE_SECURE=false` 只是 HTTP 兼容选项，管理员会话可被同网段监听或中间人截获。取得域名和证书后必须切到 HTTPS，并将其改为 `true`。

## 架构

```text
Browser
  ├─ index.html
  ├─ static/site.css
  ├─ static/app.js
  └─ static/vendor/*
          │ same-origin fetch
          ▼
Nginx :80/:443
  ├─ /static/*  ──> release 中的只读静态资源
  ├─ /photos/*  ──> /var/lib/love-story/photos
  └─ /api/*, /admin, / ──> Uvicorn 127.0.0.1:8000
                                  │
                                  ▼
                            FastAPI main:app
                              ├─ SQLite（含时间线）
                              └─ uploaded photos
```

生产入口只有 `main:app`。`Love story.py`、`.streamlit/`、旧 Codespaces 启动命令和 `update_timeline.py` 属于历史实现，不应作为生产启动入口；特别是旧脚本会把图片编码进 JSON，不适合 0.5 GiB 机器。

### 前端

- 恋爱天数和纪念日倒计时。
- 纪念日中心：可设置每年循环或一次性的纪念日，前台以倒计时/正计时卡片展示「距下一次」或「已过/还剩」，后台可增删改。
- 数据小结：纯客户端聚合展示相恋天数、时光记忆、相册照片、心愿达成、纪念日与收到祝福等统计，不新增后端端点。
- 心情日历：GitHub 式热力图展示近一年每日心情（5 档色阶，含小记），后台按日期打卡（同日 upsert 覆盖）。
- 时间胶囊：写给未来的信，公开接口在开启日期前只返回标题与倒计时、隐藏正文（服务端锁），到期后展示正文；后台可增删改。
- 约会转盘：管理员维护约会点子，前台点击后在若干候选间快速轮显再缓停选中（纯原生 JS，无 canvas）。
- 今日情话：管理员维护情话，前台按日期确定性展示「今日一句」，并可「换一句」随机切换。
- 四级下拉导航分组：我们的日子（恋爱进度 · 数据小结 · 纪念日中心）、回忆（时光机 · 相册 · 心情日历）、心意（心愿单 · 留言板 · 时间胶囊）、趣味（约会转盘 · 今日情话）；纯 CSS hover/focus 下拉，移动端沿用折叠菜单。
- 时间线卡片、相册、灯箱与背景音乐。
- 心愿单和公开留言板。
- 管理员登录、时间线维护、纪念日维护、心情/胶囊/转盘/情话维护、图片上传、留言删除和密码修改。
- Tailwind CSS 在构建阶段生成 `static/site.css`；浏览器不再运行 Tailwind Play CDN。
- 主脚本为 `static/app.js`，Lucide 与 canvas-confetti 固定版本并从 `static/vendor/` 同源加载。
- `app.js` 与 `site.css` 使用 `no-cache` 重新验证；带版本号的 vendor 文件可长缓存，避免发布后旧前端与新 API 错配。
- 现网实际前端入口为 `static/refactor-app.js` 与 `static/refactor.css`，以 `?v=` 版本号强制刷新（当前 `?v=20260721`，随每次前端发布递增）。
- 心情日历热力图采用主题感知配色：格子按 `data-level`（0–5）由 CSS 着色，亮/暗色模式分别有对应色阶，并统一加 1px 边框，确保浅色级别在亮色背景、暗色背景下均可辨识。
- 约会转盘 / 今日情话 / 时间胶囊内置示例内容（仅在对应数据表为空时通过种子脚本一次性写入，不覆盖后台已录入内容）。

自托管 vendor 文件应按 SHA-256 校验，防止手工更新时混入非预期内容：

| 文件 | 固定版本 | SHA-256 |
| --- | --- | --- |
| `static/vendor/lucide-0.468.0.min.js` | Lucide 0.468.0 UMD | `3411692820CB8D47543F69496AA25FD603A358F4498046F41C508A5A3342210E` |
| `static/vendor/canvas-confetti-1.9.3.min.js` | canvas-confetti 1.9.3 | `CFC4A191C3AE300777C25E27AA81CB2D25BB898C8632AA61787F305876A981C8` |

前端只调用同源 API。所有来自用户或数据库的文本在插入 DOM 前必须转义；管理员凭据不得写入源码、构建产物或浏览器持久存储。

### 后端与 API

| 方法与路径 | 用途 | 访问级别 |
| --- | --- | --- |
| `GET /api/health` | 健康检查 | 公开 |
| `GET /api/timeline` | 获取时间线 | 公开 |
| `POST /api/timeline` | 新增时间线 | 管理员 |
| `PUT /api/admin/timeline/{id}` | 更新时间线 | 管理员 |
| `DELETE /api/admin/timeline/{id}` | 删除时间线 | 管理员 |
| `GET /api/anniversaries` | 获取纪念日 | 公开 |
| `POST /api/anniversaries` | 新增纪念日 | 管理员 |
| `PUT /api/admin/anniversaries/{id}` | 更新纪念日 | 管理员 |
| `DELETE /api/admin/anniversaries/{id}` | 删除纪念日 | 管理员 |
| `GET /api/messages` | 最近留言 | 公开 |
| `POST /api/messages` | 新增留言 | 公开、受限流 |
| `DELETE /api/messages/{id}` | 删除留言 | 管理员 |
| `GET /api/wishlist` | 获取心愿单 | 公开 |
| `PATCH /api/wishlist/{id}` | 更新心愿完成状态 | 管理员 |
| `GET /api/capsules` | 获取时间胶囊（未到期隐藏正文） | 公开 |
| `GET /api/admin/capsules` | 获取全部胶囊（含正文，供后台编辑） | 管理员 |
| `POST /api/capsules` | 新增胶囊 | 管理员 |
| `PUT /api/admin/capsules/{id}` | 更新胶囊 | 管理员 |
| `DELETE /api/admin/capsules/{id}` | 删除胶囊 | 管理员 |
| `GET /api/moods` | 获取心情记录 | 公开 |
| `PUT /api/admin/moods/{date}` | 按日期 upsert 心情 | 管理员 |
| `DELETE /api/admin/moods/{date}` | 删除某日心情 | 管理员 |
| `GET /api/date-ideas` | 获取约会点子 | 公开 |
| `POST /api/date-ideas` | 新增约会点子 | 管理员 |
| `DELETE /api/admin/date-ideas/{id}` | 删除约会点子 | 管理员 |
| `GET /api/love-quotes` | 获取情话 | 公开 |
| `POST /api/love-quotes` | 新增情话 | 管理员 |
| `DELETE /api/admin/love-quotes/{id}` | 删除情话 | 管理员 |
| `POST /api/admin/login` | 管理员登录 | 公开、严格限流 |
| `GET /api/admin/session` | 检查当前管理员会话 | 会话探测 |
| `POST /api/admin/logout` | 注销会话 | 管理员 |
| `PUT /api/admin/password` | 修改管理员密码 | 管理员 |
| `POST /api/admin/upload` | 上传并规范化图片 | 管理员 |

管理接口的最终认证方式以当前 `main.py` 和 `static/app.js` 为准。生产必须使用同源请求、受信任 Host、精确的公开 Origin 和安全会话策略；不要在 Nginx 中信任来自任意公网地址的 `X-Forwarded-For`。

## 数据与目录

### SQLite 表

| 表 | 主要字段 | 说明 |
| --- | --- | --- |
| `messages` | `id`、`nickname`、`content`、`created_at` | 留言 |
| `wishlist` | `id`、`title`、`completed`、`completed_at` | 心愿清单 |
| `timeline` | `id`、`date`、`title`、`description`、`image`、`thumbnail`、`created_at`、`updated_at` | 时间线与原图/缩略图路径 |
| `app_settings` | `key`、`value` | 密码哈希及应用设置 |
| `admin_sessions` | `token_hash`、`expires_at`、`created_at`、`credential_version` | 只保存会话令牌哈希；修改口令后版本失效 |
| `uploads` | `path`、`thumbnail_path`、`byte_size`、`width`、`height`、`created_at` | 跟踪后台上传文件，供安全清理孤儿文件 |
| `capsules` | `id`、`title`、`body`、`unlock_date`、`created_at`、`updated_at` | 时间胶囊；`unlock_date` 前公开接口隐藏 `body` |
| `moods` | `date`（主键）、`level`(1-5)、`note`、`updated_at` | 心情日历，按日期 upsert |
| `date_ideas` | `id`、`text`、`created_at` | 约会转盘点子 |
| `love_quotes` | `id`、`text`、`created_at` | 今日情话 |

SQLite 使用 WAL。运行中不要只复制 `database.db`，也不要手工删除 `database.db-wal` 或 `database.db-shm`；一致性备份应使用 SQLite `.backup`。

时间线在当前架构中存入 SQLite。初始化只在 `timeline` 表为空时导入旧 JSON，候选顺序是 `DATA_DIR/timeline.json`，其次才是 release 根目录的 `timeline.json`。所以迁移前必须先把线上最新 JSON 放入 DATA_DIR；仓库中的文件只是兜底，不应覆盖线上更新。导入完成后 JSON 不再是生产运行时的可写数据库。

### 生产数据目录

生产环境通过样例配置把 `DATA_DIR` 设为：

```text
/var/lib/love-story/
├── database.db
├── database.db-wal
├── database.db-shm
└── photos/
```

代码 release 放在 `/opt/love-story/releases/RELEASE_ID`，`/opt/love-story/current` 是指向当前 release 的只读软链接。数据不进入 release，也不随回滚而消失。

`static/` 中随代码发布的内置图片与音乐是只读资源；`photos/` 中由后台上传的文件是运行数据。两者必须分别备份和授权。

### 图片处理

- 只允许 JPEG、PNG 和 WebP；GIF 与其他格式会被拒绝。
- Nginx 和应用把完整 multipart 请求限制为 6 MiB，原始上传文件不超过 5 MiB。
- 服务端验证真实格式、完整解码和像素数；代码默认上限为 20,000,000 像素，生产样例进一步收紧到 16,000,000。
- 上传图会在最长边 2560 像素内重编码为 WebP，移除 EXIF/GPS 元数据、生成不可预测的新文件名和独立缩略图；JPEG 会在完整解码前请求低分辨率 DCT 层，降低内存峰值。
- 不把 Base64 图片写进 SQLite 或旧 `timeline.json`；时间线只保存本站相对路径。
- 新增/修改 API 拒绝 Base64；旧 JSON 导入时也跳过 `data:image` 并记录告警，相关照片需通过后台重新上传，避免把大字符串带入 SQLite。
- 替换或删除时间线后应清理无人引用的照片，并监控 `DATA_DIR` 占用。

## 环境变量

生产样例见 [`.env.example`](.env.example)。真实文件建议放在 `/etc/love-story/love-story.env`，权限为 `root:love-story 0640`。

| 变量 | 示例 | 说明 |
| --- | --- | --- |
| `DATA_DIR` | `/var/lib/love-story` | SQLite、时间线与上传照片的持久目录 |
| `ADMIN_PASSWORD` | 强随机值 | 仅用于首次初始化或旧默认口令迁移；成功设置数据库口令后从环境文件删除 |
| `PUBLIC_ORIGIN` | `https://love.example.com` | 唯一对外 Origin，包含协议且不带尾斜杠 |
| `TRUSTED_HOSTS` | `love.example.com,www.love.example.com,127.0.0.1` | 逗号分隔的合法 Host |
| `COOKIE_SECURE` | `true` | HTTPS 必须为 true；HTTP IP 临时为 false |
| `SESSION_HOURS` | `12` | 管理员会话有效期，允许 1–168 小时 |
| `MAX_REQUEST_BODY_BYTES` | `6291456` | 含 multipart 边界的完整请求体上限 |
| `MAX_UPLOAD_BYTES` | `5242880` | 原始图片文件上限（5 MiB） |
| `MAX_IMAGE_PIXELS` | `16000000` | 生产图片像素上限；低内存主机应保守设置 |
| `MAX_OUTPUT_DIMENSION` | `2560` | 网页原图最长边；限制解码后驻留内存与客户端流量 |

新口令至少 12 个字符，并拒绝旧默认口令、常见弱口令、变化过少的字符串及 `REPLACE_*` 占位符。已有自定义密码哈希的数据库可以在不保留 `ADMIN_PASSWORD` 明文的情况下启动；该变量仍用于新库初始化或旧默认口令迁移。

生成密码时可在安全终端执行：

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

不要把真实密码写进 shell history、systemd unit、Nginx 配置、GitHub Issue 或聊天记录。编辑生产环境文件后用 `sudo systemctl restart love-story` 才会让进程读取新环境；已有数据库密码是否轮换仍取决于初始化/重置流程，而不是单纯重启。初始化或交互式重置成功后，应从生产环境文件删除 `ADMIN_PASSWORD`，数据库中的 Argon2 哈希足以供后续启动使用。

## 本地开发

### Python

推荐 Python 3.12。Linux/macOS：

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Windows PowerShell：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

设置本地环境，不要依赖应用自动加载 `.env`：

```bash
export DATA_DIR="$PWD/.local-data"
export ADMIN_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
export PUBLIC_ORIGIN='http://127.0.0.1:8000'
export TRUSTED_HOSTS='127.0.0.1,localhost'
export COOKIE_SECURE=false
```

启动：

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

`--reload` 只能用于本地开发。生产不能使用 reload，也不能增加 worker 数。

### 前端构建

推荐 Node.js 20 LTS，在开发机或 CI 构建，不要在 0.5 GiB 现网服务器运行长期 Node 进程：

```bash
npm ci
npm run build:css
```

构建结果为 `static/site.css`。`index.html`、`static/app.js`、`static/vendor/*` 与该 CSS 必须一起进入 release。修改 Tailwind 类名或 `assets/input.css` 后需要重新构建。

## 首次生产部署

以下命令以 Debian 11、部署根目录 `/opt/love-story` 为例。先阅读命令并替换所有 `REPLACE_*`、`SERVER_PUBLIC_IP` 和 `love.example.com` 占位符。

### 1. 先备份旧站

```bash
sudo systemctl stop love-story
sudo install -d -m 0700 /root/love-story-pre-migration
sudo sqlite3 /opt/love-story/database.db \
  ".timeout 10000" \
  ".backup '/root/love-story-pre-migration/database.db'"
sudo cp -a /opt/love-story/timeline.json /root/love-story-pre-migration/
sudo tar -C /opt/love-story -czf \
  /root/love-story-pre-migration/photos.tar.gz photos
```

如果旧路径不同，先用 `systemctl cat love-story` 和 `findmnt` 核对。不要在应用运行时使用普通 `cp` 代替 SQLite 在线备份。把迁移备份再复制到另一台机器或对象存储。

### 2. 安装系统工具并创建非 root 用户

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git nginx sqlite3 tar
sudo useradd --system --home-dir /var/lib/love-story \
  --shell /usr/sbin/nologin love-story
sudo usermod -aG love-story www-data
sudo install -d -o root -g love-story -m 0750 \
  /opt/love-story /opt/love-story/releases
sudo install -d -o love-story -g love-story -m 0750 \
  /var/lib/love-story /var/lib/love-story/photos
```

若用户已存在，`useradd` 报错可以忽略，但必须检查 UID、组和目录权限。Nginx 以 `www-data` 读取 `/opt/love-story/current/static` 与 `/var/lib/love-story/photos`，所以它需要 `love-story` 组的只读权限；变更附加组后要完整重启 Nginx，而不只是 reload。

### 3. 安装隔离 Python 3.12

不要替换 `/usr/bin/python3`。现网已经在 `/opt/uv-python` 安装 Python 3.12.13，可先验证：

```bash
uv --version
sudo env UV_PYTHON_INSTALL_DIR=/opt/uv-python uv python list
sudo env UV_PYTHON_INSTALL_DIR=/opt/uv-python uv python find 3.12
```

以下是全新机器或安装损坏时的重建步骤。使用固定版本的 uv 下载隔离 Python；执行远程安装脚本前先下载并人工检查：

```bash
curl -LsSf https://astral.sh/uv/0.11.28/install.sh \
  -o /tmp/install-uv.sh
less /tmp/install-uv.sh
sudo env UV_INSTALL_DIR=/usr/local/bin sh /tmp/install-uv.sh
sudo install -d -o root -g root -m 0755 /opt/uv-python
sudo env UV_PYTHON_INSTALL_DIR=/opt/uv-python \
  uv python install 3.12 --no-bin
```

uv 使用预构建的 `python-build-standalone`，不会修改 Debian 系统 Python。参考 [uv 安装说明](https://docs.astral.sh/uv/getting-started/installation/) 与 [Python 管理说明](https://docs.astral.sh/uv/guides/install-python/)。

### 4. 创建 release

优先部署由 CI 针对已审查 commit 生成并校验哈希的产物。若直接从 GitHub 部署，必须按完整 commit SHA 拉取并复核，不能把目录命名成某个 SHA 却实际使用默认分支当时的 HEAD：

```bash
REVIEWED_COMMIT=REPLACE_WITH_FULL_REVIEWED_COMMIT_SHA
RELEASE_ID="$REVIEWED_COMMIT"
RELEASE_DIR=/opt/love-story/releases/$RELEASE_ID
sudo git init "$RELEASE_DIR"
sudo git -C "$RELEASE_DIR" remote add origin \
  https://github.com/REPLACE_OWNER/REPLACE_REPOSITORY.git
sudo git -C "$RELEASE_DIR" fetch --depth 1 origin "$REVIEWED_COMMIT"
sudo git -C "$RELEASE_DIR" checkout --detach FETCH_HEAD
ACTUAL_COMMIT="$(sudo git -C "$RELEASE_DIR" rev-parse HEAD)"
if [ "$ACTUAL_COMMIT" != "$REVIEWED_COMMIT" ]; then
  echo "Refusing unreviewed commit: $ACTUAL_COMMIT" >&2
  exit 1
fi
sudo env UV_PYTHON_INSTALL_DIR=/opt/uv-python \
  uv venv --managed-python --python 3.12 "$RELEASE_DIR/.venv"
sudo env UV_PYTHON_INSTALL_DIR=/opt/uv-python \
  uv pip install --no-cache \
  --python "$RELEASE_DIR/.venv/bin/python" \
  -r "$RELEASE_DIR/requirements.txt"
sudo chown -R root:love-story "$RELEASE_DIR"
sudo chmod -R u=rwX,g=rX,o= "$RELEASE_DIR"
```

前端构建产物应由 CI 或开发机提前生成并包含在 release 中。若必须现场构建，构建结束后删除 `node_modules`，并在 `free -h`、`swapon --show` 正常时执行。

### 5. 创建环境文件

```bash
sudo install -d -o root -g love-story -m 0750 /etc/love-story
sudo install -o root -g love-story -m 0640 \
  "$RELEASE_DIR/.env.example" \
  /etc/love-story/love-story.env
sudoedit /etc/love-story/love-story.env
```

必须替换管理员密码和所有域名/IP 占位符。当前只有 HTTP IP 时使用 `COOKIE_SECURE=false`；申请域名和证书后使用 `true`。

### 6. 迁移旧数据

服务保持停止：

```bash
sudo sqlite3 /root/love-story-pre-migration/database.db \
  ".backup '/var/lib/love-story/database.db'"
sudo install -o love-story -g love-story -m 0640 \
  /root/love-story-pre-migration/timeline.json \
  /var/lib/love-story/timeline.json
sudo tar -C /var/lib/love-story -xzf \
  /root/love-story-pre-migration/photos.tar.gz
sudo chown -R love-story:love-story /var/lib/love-story
sudo find /var/lib/love-story -type d -exec chmod 0750 {} +
sudo find /var/lib/love-story -type f -exec chmod 0640 {} +
```

若旧站没有数据库、时间线或上传目录，跳过对应命令。`static/` 内置素材随代码 release 提供，不复制到 `DATA_DIR`。

新服务启动时会迁移 `DATA_DIR/database.db` 的 SQLite schema，但不会擅自复制 release 根目录中的旧数据库；上面的 SQLite `.backup` 恢复步骤是必需的。若 `timeline` 表为空，则按 `DATA_DIR/timeline.json`、`BASE_DIR/timeline.json` 的顺序导入。首次成功启动后检查数据库完整性、时间线条数和随机图片，再保留旧文件到至少一次恢复演练完成。

本次现网时间线已经核验为 38 条、全部有 ID、没有 Base64，最长图片路径 57 个字符，因此无需 Base64 转换。迁移后应保持 38 条；2 条无图记录可以继续保留。若以后导入其他旧 JSON，`data:image` 会被跳过并告警，而不是写入 SQLite。

迁移完成后生成历史图片缩略图；JPEG 会先选择较低分辨率解码层，命令再逐张处理，避免并发解码挤占 0.5 GiB 主机内存：

```bash
sudo -u love-story env DATA_DIR=/var/lib/love-story \
  "$RELEASE_DIR/.venv/bin/python" "$RELEASE_DIR/manage.py" rebuild-thumbnails
```

### 7. 设置或轮换管理员密码

全新数据库会在首次初始化时读取 `ADMIN_PASSWORD`。已有数据库不会因为仓库中出现新默认值而安全地自动覆盖现有自定义密码。

交互式重置应以非 root 服务用户执行，密码通过 `getpass` 输入而不是命令行参数：

```bash
sudo -u love-story env \
  DATA_DIR=/var/lib/love-story \
  "$RELEASE_DIR/.venv/bin/python" \
  "$RELEASE_DIR/manage.py" reset-password
```

重置成功后从 `/etc/love-story/love-story.env` 删除整行 `ADMIN_PASSWORD=...`，检查明文变量已经不存在；若服务正在运行则重启以清除进程环境：

```bash
sudoedit /etc/love-story/love-story.env
! sudo grep -q '^ADMIN_PASSWORD=' /etc/love-story/love-story.env
sudo systemctl try-restart love-story
```

兼容入口也可使用 `"$RELEASE_DIR/init_db.py" --reset-password`。

如果当前版本的 `init_db.py --help` 还没有 `--reset-password`，不要把明文密码放在 `--password` 或 shell history 中；先部署包含交互式重置功能的版本。也可以在确认旧口令仍有效时，通过后台“修改口令”完成轮换。

首次部署必须先在环境文件中设置新密码，再执行初始化/迁移。只有部署到现网并实际运行这些步骤，历史默认密码才会被轮换；修改本地代码本身没有任何线上效果。

### 8. 原子切换 release

先验证导入和版本：

```bash
sudo -u love-story env \
  "$RELEASE_DIR/.venv/bin/python" -c \
  "import fastapi, starlette, uvicorn, pydantic, PIL; print('imports ok')"
sudo ln -sfn "$RELEASE_DIR" /opt/love-story/current
```

### 9. 安装 systemd

```bash
sudo install -o root -g root -m 0644 \
  /opt/love-story/current/deploy/love-story.service \
  /etc/systemd/system/love-story.service
sudo systemctl daemon-reload
sudo systemd-analyze verify /etc/systemd/system/love-story.service
sudo systemctl enable --now love-story
sudo systemctl status love-story --no-pager
curl --fail --silent http://127.0.0.1:8000/api/health
```

unit 固定为：

- `127.0.0.1:8000`，不直接暴露 Uvicorn。
- 单 worker。
- `--limit-concurrency 16`、backlog 64。
- `MemoryHigh=180M`、`MemoryMax=220M`。
- 非 root `love-story` 用户。
- 只有 `/var/lib/love-story` 可写。

### 10. 安装 Nginx

仓库提供两个互斥模板：

- `deploy/nginx-love-story-http.conf`：当前无域名时的临时 HTTP 配置。
- `deploy/nginx-love-story.conf`：取得域名和 TLS 证书后的正式配置。

二者定义了同名限流区，**绝不能同时启用**。

临时 HTTP：

```bash
sudo cp -a /etc/nginx/sites-available/default \
  /root/nginx-default.before-love-story
sudo rm -f /etc/nginx/sites-enabled/default
sudo install -o root -g root -m 0644 \
  /opt/love-story/current/deploy/nginx-love-story-http.conf \
  /etc/nginx/conf.d/love-story.conf
sudo nginx -t
sudo systemctl restart nginx
```

旧配置的 `client_max_body_size 12m` 会被新模板降为 6m；应用进一步把解码后的图片限制在 5 MiB。

同时检查 Aliyun 安全组和主机防火墙：只开放管理所需的 SSH 来源以及公网 80；取得证书后开放 443。不要开放 8000，`ss -ltnp` 应显示它只绑定 `127.0.0.1`。

取得域名后：

1. DNS 指向服务器。
2. 先用 ACME webroot 或 standalone 方式签发证书。
3. 替换 `nginx-love-story.conf` 中所有 `love.example.com`。
4. 将环境文件改为 HTTPS Origin、域名 Host 和 `COOKIE_SECURE=true`。
5. 用 TLS 模板替换 HTTP 模板，执行 `nginx -t` 后 reload。
6. 重启应用并验证管理员登录。

TLS 模板会增加 HSTS；只有确认 HTTPS 和所有子域均可用后才启用 `includeSubDomains`。

### 11. 验证日志轮转并安装备份

```bash
sudo logrotate --debug /etc/logrotate.conf

sudo install -o root -g love-story -m 0750 \
  /opt/love-story/current/deploy/backup.sh \
  /usr/local/sbin/love-story-backup
sudo install -o root -g root -m 0644 \
  /opt/love-story/current/deploy/love-story-backup.service \
  /opt/love-story/current/deploy/love-story-backup.timer \
  /etc/systemd/system/
sudo install -d -o love-story -g love-story -m 0700 /var/backups/love-story
sudo systemctl daemon-reload
sudo systemctl enable --now love-story-backup.timer
sudo systemctl start love-story-backup.service
sudo systemctl status love-story-backup.service --no-pager
```

Debian 11 的 `/etc/logrotate.d/nginx` 已匹配 `/var/log/nginx/*.log`，因此会自动轮转 `love-story-access.log` 与 `love-story-error.log`。不要再为这两个文件安装第二条规则，否则 `logrotate` 会报 `duplicate log entry` 并跳过 Nginx 规则。始终检查完整的 `/etc/logrotate.conf`，而不是只检查单个片段。

`deploy/journald-love-story.conf` 是整机级别的可选限制，会影响所有 systemd 日志。安装前先评估其他服务：

```bash
sudo install -d -m 0755 /etc/systemd/journald.conf.d
sudo install -o root -g root -m 0644 \
  /opt/love-story/current/deploy/journald-love-story.conf \
  /etc/systemd/journald.conf.d/love-story.conf
sudo systemctl restart systemd-journald
```

## 从旧版目录迁移

迁移前必须同时备份：

1. `database.db`，通过 SQLite `.backup`。
2. `timeline.json`。
3. `photos/`。
4. 当前 systemd unit、`/etc/love-story.env` 和 Nginx 配置。
5. 当前 release 或 Git commit SHA。

推荐布局：

```text
/opt/uv-python/             # uv 管理的隔离 Python 3.12.13
/opt/love-story/
├── releases/
│   ├── 20260716T120000Z/
│   │   ├── .venv/
│   │   └── ...
│   └── NEXT_RELEASE/
└── current -> releases/20260716T120000Z
```

切换前先在新 release 上做导入检查；切换软链接后重启 systemd。出现错误时可把 `current` 指回上一个 release，但不要回滚 `DATA_DIR`，除非同时确认数据库 schema 兼容或执行完整数据恢复。

## 备份与恢复

### 自动备份

`deploy/backup.sh`：

- 强制要求 `database.db` 存在；缺失时备份失败且不会淘汰旧备份。
- 应用停止写入后，以 SQLite `immutable=1` 只读方式打开生产库，用 `.backup` 创建副本，并在标记完成前执行 `PRAGMA integrity_check`；这不会在只读数据目录中重建 WAL/SHM 文件。
- 时间线已包含在 SQLite 副本中；若 DATA_DIR 仍有旧 `timeline.json`，也会额外保留。
- 压缩 `photos/`。
- 生成 SHA-256 校验和。
- 默认保留 14 天，且只清理名称符合 UTC 自动时间戳的目录；人工回滚快照不在清理范围内。

`love-story-backup.service` 会在备份期间短暂停止应用写入，并在成功或失败后重新启动应用，使 SQLite 与照片归档属于同一个恢复点。Nginx 在这几秒内仍可提供静态文件，但 API 请求可能短暂返回 502，因此默认安排在低峰时段。

默认输出：

```text
/var/backups/love-story/UTC_TIMESTAMP/
├── database.db
├── timeline.json          # 可选，仅旧版迁移期存在
├── photos.tar.gz
├── metadata.txt
├── SHA256SUMS
└── COMPLETE
```

同盘备份不能抵御云盘损坏、误删账号或主机失陷。至少每天把已完成目录加密同步到另一账户或对象存储，并定期做恢复演练。

### 手工验证

```bash
BACKUP=/var/backups/love-story/REPLACE_TIMESTAMP
cd "$BACKUP"
sha256sum -c SHA256SUMS
sqlite3 database.db "PRAGMA integrity_check;"
```

`PRAGMA integrity_check` 应返回 `ok`。

### 恢复

先停止服务并保留当前数据作为可回滚副本：

```bash
BACKUP=/var/backups/love-story/REPLACE_TIMESTAMP
sudo systemctl stop love-story
cd "$BACKUP"
sha256sum -c SHA256SUMS
sqlite3 database.db "PRAGMA integrity_check;"

sudo mv /var/lib/love-story \
  "/var/lib/love-story.before-restore-$(date -u +%Y%m%dT%H%M%SZ)"
sudo install -d -o love-story -g love-story -m 0750 \
  /var/lib/love-story /var/lib/love-story/photos
sudo sqlite3 "$BACKUP/database.db" \
  ".backup '/var/lib/love-story/database.db'"
if [ -f "$BACKUP/timeline.json" ]; then
  sudo install -o love-story -g love-story -m 0640 \
    "$BACKUP/timeline.json" /var/lib/love-story/timeline.json
fi
if [ -f "$BACKUP/photos.tar.gz" ]; then
  sudo tar -C /var/lib/love-story -xzf "$BACKUP/photos.tar.gz"
fi
sudo chown -R love-story:love-story /var/lib/love-story
sudo systemctl start love-story
curl --fail --silent http://127.0.0.1:8000/api/health
```

随后检查登录、时间线、留言、心愿单和任意一张上传照片。确认恢复成功前不要删除 `before-restore` 目录。

## 测试与安全审计

在开发机或 CI：

```bash
python -m compileall -q main.py init_db.py manage.py tests
ruff check .
pytest -q
pip-audit -r requirements.txt
npm ci
npm run build:css
npm audit
```

现有测试覆盖：

- fresh DB 初始化与旧默认密码迁移。
- 交互式密码重置和会话失效。
- Host/Origin/Cookie 策略。
- 登录、留言和上传限流。
- 非图片、伪造 MIME、超大文件、像素炸弹和 EXIF 清除。
- 时间线并发写入、图片替换和孤儿清理。
- 数据目录权限与迁移。

服务器部署前后：

```bash
sudo systemd-analyze verify /etc/systemd/system/love-story.service
sudo nginx -t
sudo logrotate --debug /etc/logrotate.conf
sudo -u love-story test -r /etc/love-story/love-story.env
sudo -u love-story test -w /var/lib/love-story
curl -i http://127.0.0.1:8000/api/health
curl -I http://SERVER_PUBLIC_IP/
```

取得 TLS 后还应检查证书链、HTTP 到 HTTPS 跳转、HSTS、CSP、`Secure`/`HttpOnly`/`SameSite` Cookie，以及公网无法直连 8000 端口。

## 安全模型

- Nginx 是唯一公网入口，Uvicorn 只监听 loopback。
- 管理员密码使用慢哈希存储；明文只短暂出现在受控输入中。
- 会话服务端只保存令牌哈希，并有过期时间。
- Host 和 Origin 使用显式 allowlist。
- HTTPS 下会话 Cookie 必须为 `Secure`，并使用 `HttpOnly` 和合适的 `SameSite`。
- 登录、留言和总请求在 Nginx 分层限流；应用层仍需二次限制。
- 每个来源同一时刻只允许一个图片上传，请求频率为每分钟 6 次，降低 Pillow 并发解码的内存尖峰。
- CSP 只允许同源脚本，Tailwind 与 vendor 脚本不从第三方 CDN 运行。
- 图片有字节、像素、格式和元数据边界。
- systemd 使用非 root、只读系统目录、最小可写路径及内存/任务上限。
- 依赖固定版本，并通过 `pip-audit` / `npm audit` 持续检查。

Nginx 的 IP 限流只有在它直接面对公网时才可信。若前面增加 CDN，必须只信任 CDN 官方固定出口网段并配置 real IP；不能无条件信任客户端传来的 `X-Forwarded-For`。

## 资源预算

439 MiB 可见内存的初始预算：

| 组件 | 目标 |
| --- | --- |
| Debian、SSH、systemd、journald | 约 100–160 MiB，按实测为准 |
| Nginx | 通常低于 20 MiB |
| 单 Uvicorn/FastAPI worker | 空闲实测约 36 MiB；高峰目标低于 180 MiB |
| 文件缓存、SQLite 和安全余量 | 至少保留约 80–120 MiB |
| systemd 边界 | `MemoryHigh=180M`、`MemoryMax=220M` |

服务器现有 2 GiB swap 已足够作为短时尖峰保险，不要再叠加 swap 文件。Swap 不能修复持续内存泄漏或无限并发；若 `si/so` 长期增长，应降低并发、检查图片处理并扩容。

不要在该主机上：

- 启动多个 Uvicorn worker。
- 运行旧 Streamlit 服务。
- 长期运行 Node/Tailwind watch。
- 把图片编码进 JSON。
- 无限制保留访问日志、上传照片或数据库备份。

常用监控：

```bash
free -h
swapon --show
df -h / /var/lib/love-story /var/backups/love-story
systemctl show love-story -p MemoryCurrent -p MemoryPeak
ps -o pid,rss,%mem,%cpu,cmd -C uvicorn
sudo journalctl -u love-story --since "1 hour ago"
sudo journalctl -k --grep='Out of memory\|oom'
```

建议在磁盘 70% 时告警，85% 时停止非必要上传并清理已验证的旧备份/孤儿文件。

## 隐私提醒

这个站点包含真实姓名、纪念日期和私人照片：

- GitHub 仓库优先设为 private；清除当前文件不等于清除 Git 历史和已有 clone。
- 公开 Nginx `/static/` 与 `/photos/` 意味着知道 URL 的任何人都能访问图片。
- `robots.txt` 或 `noindex` 只能减少索引，不能充当访问控制。
- 上传前移除 GPS/EXIF；服务端仍需重编码，不依赖浏览器。
- 备份包含全部私人数据，必须限制权限、加密异地存储并设置生命周期。
- 若网站只给两个人使用，应在 Nginx 前增加独立访问控制，而不只是隐藏管理员按钮。
- 不在日志中记录密码、Authorization、完整 Cookie、上传内容或私人留言正文。

## 运维与排错

### 服务启动失败

```bash
sudo systemctl status love-story --no-pager
sudo journalctl -u love-story -n 200 --no-pager
sudo systemctl cat love-story
sudo -u love-story /opt/love-story/current/.venv/bin/python --version
```

确认 Python 是 3.12、`current` 指向完整 release、环境文件可读、`DATA_DIR` 可写。

### Nginx 502

```bash
curl -v http://127.0.0.1:8000/api/health
sudo ss -ltnp | grep ':8000'
sudo nginx -t
sudo tail -n 100 /var/log/nginx/love-story-error.log
```

若 loopback 健康而公网失败，检查 Nginx；若 loopback 失败，检查 systemd 和应用日志。

### 400 / Host 被拒绝

把浏览器实际 Host 精确加入 `TRUSTED_HOSTS`。不要用 `*`。使用公网 IP 时加入该 IP；切换域名后移除不再需要的 IP。

### 登录成功后立即失效

检查 `PUBLIC_ORIGIN` 的协议、主机和端口是否与浏览器一致。HTTP IP 必须临时 `COOKIE_SECURE=false`；HTTPS 必须 `true`。修改后重启服务并清除旧站点 Cookie。

### 413 Request Entity Too Large

检查 Nginx `client_max_body_size 6m`。应用仍会拒绝超过 6 MiB 的请求体、超过 5 MiB 的原始图片；生产样例把像素数限制为 16 MP，代码默认上限为 20 MP。不要只放大 Nginx；低内存机器应先压缩图片。

### 429 Too Many Requests

这是限流生效。普通用户持续触发时，检查是否有共享 NAT、CDN real IP 是否配置正确，以及前端是否重复提交。不要直接移除登录限流。

### 照片 404

```bash
namei -l /var/lib/love-story/photos
sudo -u www-data test -r /var/lib/love-story/photos/REPLACE_FILE
sudo nginx -T | grep -A8 'location.*photos'
```

Nginx 用户需要目录执行权限和文件读取权限，但不需要写权限。

### 数据库 locked 或只读

- 确认只有一个 worker。
- 检查 `love-story` 对 `DATA_DIR` 的写权限和磁盘余量。
- 不要运行两个指向同一 DATA_DIR 的 release。
- 不要在服务运行时删除 WAL/SHM。
- 使用 `sqlite3 database.db "PRAGMA quick_check;"` 检查。

### OOM 或频繁 swap

```bash
sudo journalctl -k --grep='Out of memory\|oom'
sudo systemctl show love-story \
  -p MemoryCurrent -p MemoryPeak -p MemoryHigh -p MemoryMax
vmstat 1 10
```

先检查超大/高像素上传、并发请求和 orphan 文件扫描；必要时把 `--limit-concurrency` 从 16 降到 8。不要靠增加 worker 解决。

### 样式或图标丢失

确认 release 包含 `static/site.css`、`static/app.js` 与 `static/vendor/`，并重新执行 `npm ci && npm run build:css`。检查 CSP 报错和 Nginx 静态 alias。

## 日常发布与回滚

每次发布：

1. 运行 Python、前端和安全检查。
2. 创建数据库/时间线/照片备份，并异地复制。
3. 建立新的只读 release 和独立 `.venv`。
4. 用生产环境做导入预检。
5. 原子切换 `current`。
6. `systemctl restart love-story`。
7. 验证健康、首页、登录、留言、心愿单和上传。
8. 观察日志、RSS、swap 和 5xx 至少一个业务周期。

代码回滚：

```bash
sudo ln -sfn /opt/love-story/releases/REPLACE_PREVIOUS_RELEASE \
  /opt/love-story/current
sudo systemctl restart love-story
curl --fail http://127.0.0.1:8000/api/health
```

不要把代码回滚等同于数据回滚。只有确认 schema 兼容或有完整恢复计划时，才恢复旧数据库。

## 与 GitHub 同步（代码 + README 一起入库）

仓库：`Xin-Li-bot/Love-story`。约定：**每次改动都先在服务器部署验证，再同步回 GitHub（代码与 README 一起）**，让仓库反映生产状态。

工作流（在生产工作树 `/opt/love-story/current`）：

1. 改代码 → 部署到生产并验证（health、Xray pid、内存、浏览器冒烟）。
2. 同步更新本 README（功能说明、API 表、`?v=` 缓存约定）。
3. `.gitignore` 排除部署备份：`*.predeploy.*`、`*.bak.*`、`*.pre-*`。
4. 仅暂存真实生产文件：`main.py`、`index.html`、`static/refactor-app.js`、`static/refactor.css`、`README.md`；确认 `git status` 不含任何备份文件或 token。
5. 提交后一次性直推（**不把 PAT 写入 git config**）：`git push https://<PAT>@github.com/Xin-Li-bot/Love-story.git HEAD:production-live`。

安全：PAT 仅在推送命令行临时使用，绝不写入仓库、git config 或日志；`?v=` 资源版本号在前端资源改动时递增（当前 `?v=20260719`）以绕过旧缓存。

## 部署文件索引

| 文件 | 作用 |
| --- | --- |
| [`.env.example`](.env.example) | 环境变量模板 |
| [`deploy/love-story.service`](deploy/love-story.service) | 低内存、非 root systemd unit |
| [`deploy/nginx-love-story-http.conf`](deploy/nginx-love-story-http.conf) | 无域名阶段的临时 HTTP 配置 |
| [`deploy/nginx-love-story.conf`](deploy/nginx-love-story.conf) | 域名 + TLS 正式配置 |
| [`deploy/journald-love-story.conf`](deploy/journald-love-story.conf) | 可选的整机 journal 限额 |
| [`deploy/backup.sh`](deploy/backup.sh) | SQLite、时间线与照片备份 |
| [`deploy/love-story-backup.service`](deploy/love-story-backup.service) | 备份 oneshot unit |
| [`deploy/love-story-backup.timer`](deploy/love-story-backup.timer) | 每日备份 timer |
| [`requirements.txt`](requirements.txt) | 生产 Python 依赖 |
| [`requirements-dev.txt`](requirements-dev.txt) | 测试、lint 与安全审计依赖 |
