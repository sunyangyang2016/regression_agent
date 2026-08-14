# 学前班教学视频 — 详细设计文档

> ⚠️ **与当前实现不符（2026-08-14）**：本文档为早期设计稿，文中描述的部分架构（第 4 节
> Python Skill 类 `skill_video_search/download/control`、`skills/builtin/video_skill.py`）**从未实现**。
> 实际实现为：MD Skill（`skills/md/preschool-video/SKILL.md` 提示词）+ 独立 CLI 脚本
> （`scripts/video_search.py` / `video_control.py` / `video_catcher_runner.py`）。
> 命令传送走**事件通道**：脚本进程 HTTP POST `/video_command`（127.0.0.1 端口发现于
> `storage/video_plugin.json`）→ 主进程 `PluginBus.publish("video_control"/"video_updated")`
> → video_plugin observer 订阅执行。
> 数据库设计、VideoRepository、video_plugin、断点续播等章节仍与实际一致，可作参考。

> 本文档基于项目现有架构（PluginBus 事件总线、Python Skill 类、video_plugin 插件、VideoRepository 数据层）的完整设计，覆盖**视频搜索、播放控制、断点续播、视频下载、AI 对话驱动**等核心业务流程。

---

## 目录

- [1. 总体架构](#1-总体架构)
- [2. 数据库设计](#2-数据库设计)
- [3. VideoRepository 数据操作层](#3-videorepository-数据操作层)
- [4. Python Skill 类设计](#4-python-skill-类设计)
- [5. video_plugin 插件设计](#5-video_plugin-插件设计)
- [6. 前端 UI 设计](#6-前端-ui-设计)
- [7. MD Skill（AI 知识库）](#7-md-skillai-知识库)
- [8. 事件流时序](#8-事件流时序)
- [9. 文件清单](#9-文件清单)
- [10. 实施步骤](#10-实施步骤)
- [11. 验证场景](#11-验证场景)

---

## 1. 总体架构

```
┌───────────────────────── AI 对话层 ──────────────────────────┐
│  用户："帮我找幼儿园大班的数学视频" / "播放第一个" / "快进30秒" │
│    │                                                       │
│    ▼                                                       │
│  AI 读取「preschool-video SKILL」提示词 → 识别意图             │
│    │                                                       │
│    ▼                                                       │
│  AI 调用 skill_video_search / skill_video_download          │
│       / skill_video_control（Python Skill 类）               │
└────────────────────────┬────────────────────────────────────┘
                         ▼ 主进程内执行
┌─────────────────────────────────────────────────────────────┐
│              skills/builtin/video_skill.py                   │
│  VideoSearchSkill / VideoDownloadSkill / VideoControlSkill   │
│    │                                                        │
│    ├── VideoRepository（数据库操作）                          │
│    └── PluginBus.publish("video_control"/"video_updated")    │
└─────────┬───────────────────────────────────┬────────────────┘
          │                                   │
          ▼ 事件订阅（同进程）                  ▼
┌─────────────────────────────────────────────────────────────┐
│          plugins/builtin/video_plugin/                       │
│  VideoObserver ── 订阅 PluginBus 事件                        │
│    │                                                       │
│    ▼                                                       │
│  VideoBridge ── execute_js ──► 前端视频中心 UI              │
│    │                                                       │
│    └── VideoRepository（同一数据操作层）                      │
└─────────────────────────────────────────────────────────────┘
```

**核心设计原则**：

| 原则 | 说明 |
|------|------|
| **全部主进程内** | Skill 类是 Python 内建类，在 Qt 主进程内执行，直接访问 PluginBus 和 VideoRepository |
| **事件驱动** | 与系统监控 monitor_plugin 完全相同的 PluginBus 订阅/发布模式 |
| **统一数据层** | Skill 和插件都通过 `VideoRepository` 访问数据库，数据操作完全一致 |
| **解耦** | Skill 不依赖插件存在，插件不依赖 Skill，通过 PluginBus 事件通信 |

---

## 2. 数据库设计

### 2.1 表结构（`storage/database.py` 修改）

在 `Database.TABLES` 中追加第 5 张表：

```python
TABLES = [
    "history_sessions_index",
    "history_sessions_messages",
    "mcp_market_index",
    "mcp_server_logs",
    "video_library",          # ★ 新增
]
```

```python
TABLE_DDL += [
    """
    CREATE TABLE IF NOT EXISTS video_library (
        id            TEXT PRIMARY KEY,          -- UUID
        title         TEXT NOT NULL,             -- 视频名称
        subject       TEXT,                      -- 科目（数学/语文/英语/科学/艺术/健康）
        grade         TEXT,                      -- 年级（学前班/大班/中班/小班）
        source        TEXT,                      -- 来源（智慧教育平台/bilibili/优酷/本地）
        description   TEXT,                      -- 视频简介
        page_url      TEXT,                      -- 原始页面链接
        play_url      TEXT,                      -- 播放直链（在线播放）
        local_path    TEXT,                      -- 本地文件路径（下载后）
        thumbnail     TEXT,                      -- 封面图/图标
        duration      INTEGER,                   -- 播放时长（秒）
        resolution    TEXT,                      -- 分辨率（1920x1080）
        width         INTEGER,                   -- 宽（像素）
        height        INTEGER,                   -- 高（像素）
        quality       TEXT,                      -- 画质（1080p/720p/480p）
        file_size     INTEGER,                   -- 文件大小（字节）
        file_format   TEXT,                      -- 格式（mp4/webm/flv）
        fps           REAL,                      -- 帧率
        status        TEXT DEFAULT 'online',     -- online/downloading/downloaded/failed
        download_progress INTEGER DEFAULT 0,     -- 下载进度（0-100）
        play_count    INTEGER DEFAULT 0,         -- 播放次数
        last_played_at TEXT,                     -- 最近播放时间
        is_favorite   INTEGER DEFAULT 0,         -- 收藏（0/1）
        last_position INTEGER DEFAULT 0,         -- ★ 上次播放位置（秒），0=从头
        created_at    TEXT,                      -- 入库时间
        updated_at    TEXT                       -- 更新时间
    )
    """,
]
```

```python
INDEX_DDL += [
    "CREATE INDEX IF NOT EXISTS idx_vlib_subject ON video_library (subject)",
    "CREATE INDEX IF NOT EXISTS idx_vlib_grade   ON video_library (grade)",
    "CREATE INDEX IF NOT EXISTS idx_vlib_status  ON video_library (status)",
    "CREATE INDEX IF NOT EXISTS idx_vlib_source  ON video_library (source)",
    "CREATE INDEX IF NOT EXISTS idx_vlib_created ON video_library (created_at)",
]
```

### 2.2 字段分类说明

| 分组 | 字段 | 说明 |
|------|------|------|
| **基本信息** | id / title / subject / grade / source / description | 视频基础元数据 |
| **链接信息** | page_url / play_url / local_path / thumbnail | 在线/本地/封面 |
| **媒体信息** | duration / resolution / width / height / quality / file_size / file_format / fps | 视频技术参数 |
| **状态管理** | status / download_progress / play_count / last_played_at / is_favorite | 播放与下载状态 |
| **★ 播放进度** | last_position | 断点续播支持 |
| **时间戳** | created_at / updated_at | 数据生命周期 |

---

## 3. VideoRepository 数据操作层

创建 `storage/repositories/video_repo.py`，参照 `MCPMarketRepository` 经典 Repository 模式。

### 3.1 查询方法

| 方法 | 说明 |
|------|------|
| `get_all(subject, grade, source, status, keyword, limit, offset)` | 视频列表（筛选 + 搜索 + 分页） |
| `get_by_id(video_id)` | 按 ID 获取单个视频 |
| `count(**filters)` | 数量统计（支持筛选） |
| `get_stats()` | 视频库统计（总数/在线/下载中/已下载/失败） |
| `get_playback_position(video_id)` | ★ 获取上次播放位置（秒） |
| `get_playback_state(video_id)` | ★ 完整播放状态（AI get_state 查询用） |

### 3.2 写入方法

| 方法 | 说明 |
|------|------|
| `add(video)` | 新增视频，返回 ID |
| `add_many(videos)` | 批量新增（同 title+source 去重），返回新增数 |
| `update(video_id, fields)` | 更新指定字段 |
| `upsert(video)` | 插入或更新（同 id 则更新，否则新增） |

### 3.3 状态管理方法

| 方法 | 说明 |
|------|------|
| `set_status(video_id, status)` | 设置状态（online/downloading/downloaded/failed） |
| `set_download_progress(video_id, progress)` | 更新下载进度（0-100） |
| `mark_downloaded(video_id, local_path, file_size, file_format)` | 标记已下载 |
| `increment_play_count(video_id)` | 播放次数 +1，更新最近播放时间 |
| `toggle_favorite(video_id)` | 切换收藏状态 |
| **`update_last_position(video_id, position)`** | **★ 每 5 秒保存播放位置** |

### 3.4 删除方法

| 方法 | 说明 |
|------|------|
| `delete(video_id)` | 删除视频记录 |
| `clear()` | 清空所有视频记录 |

### 3.5 字段映射

| 前端字段（camelCase） | 数据库字段（snake_case） |
|----------------------|------------------------|
| `pageUrl` | `page_url` |
| `playUrl` | `play_url` |
| `localPath` | `local_path` |
| `fileSize` | `file_size` |
| `fileFormat` | `file_format` |
| `downloadProgress` | `download_progress` |
| `playCount` | `play_count` |
| `lastPlayedAt` | `last_played_at` |
| `isFavorite` | `is_favorite` |
| `lastPosition` | `last_position` |
| `createdAt` | `created_at` |
| `updatedAt` | `updated_at` |

---

## 4. Python Skill 类设计

> **架构说明**：Skill 脚本位于 `skills/md/preschool-video/scripts/`，为自包含的独立脚本集。
> 搜索/解析逻辑（搜狗搜索/yt-dlp）位于本目录内，**下载职责完全由 video-catcher skill 承担**。
>
> 脚本清单：
> | 脚本 | 作用 |
> |------|------|
> | `video_catcher_runner.py` | 搜索/解析执行器（搜狗搜索/yt-dlp 解析）+ video-catcher 下载 subprocess 隔离封装 |
> | `video_search.py` | 搜索学前教学视频并写入 video_library 表 |
> | `video_control.py` | 控制播放器（播放/暂停/快进/音量等） |
>
> 下载操作请使用 `skills/md/video-catcher/SKILL.md`（支持 B站/YouTube/抖音等，自动嗅探/断点续传）。
>

### 4.1 VideoSearchSkill（`skill_video_search`）

| 属性 | 值 |
|------|------|
| name | `video_search` |
| description | 搜索学前教学视频并加入视频库，结果显示在视频中心 |
| category | `tool` |

**input_schema**：

```json
{
  "type": "object",
  "properties": {
    "keyword": {"type": "string", "description": "搜索关键词，如：幼儿园大班 数学 教学视频"},
    "source": {"type": "string", "enum": ["自动", "智慧教育平台", "bilibili", "优酷"]},
    "limit": {"type": "integer", "description": "返回数量，默认 10"}
  },
  "required": ["keyword"]
}
```

**执行流程**：

```
1. 解析关键词 → 猜测 subject（数学/语文/...）和 grade（学前班/大班/...）
2. 调用 yt-dlp 搜索指定来源（ytsearch{limit}:{keyword}）
3. 提取视频信息：title / page_url / play_url / thumbnail / duration / width / height / resolution
4. VideoRepository.add_many() 批量写入（同 title+source 去重）
5. ★ PluginBus.publish("video_updated", {"added": N, "total": M})
   → video_plugin observer → 前端自动刷新列表
6. 返回：搜索到 N 个视频，新增 M 个
```

### 4.2 VideoDownloadSkill（`skill_video_download`）

| 属性 | 值 |
|------|------|
| name | `video_download` |
| description | 下载教学视频到本地（默认 720p） |
| category | `tool` |

**input_schema**：

```json
{
  "type": "object",
  "properties": {
    "video_id": {"type": "string", "description": "视频 ID（video_library 中的 id）"},
    "quality": {"type": "string", "enum": ["480p", "720p", "1080p"], "description": "下载画质，默认 720p"}
  },
  "required": ["video_id"]
}
```

**执行流程**：

```
1. VideoRepository.get_by_id(video_id) → 获取视频信息
2. set_status("downloading", download_progress=0)
3. PluginBus.publish("video_updated", {status: "downloading"})
4. 后台线程启动 yt-dlp 下载（避免阻塞 AI 回复）：
   yt-dlp -f "bestvideo[height<={quality}]+bestaudio/best" --merge-output-format mp4 -o media/videos/%(title)s.%(ext)s <url>
5. 下载完成 → mark_downloaded(video_id, local_path, file_size, file_format)
6. PluginBus.publish("video_updated", {status: "downloaded"})
7. 失败 → set_status("failed") + 发布事件
8. 返回：⏳ 开始下载《xxx》（720p）...
```

### 4.3 VideoControlSkill（`skill_video_control`）

| 属性 | 值 |
|------|------|
| name | `video_control` |
| description | 控制视频播放器：播放/暂停/停止/快进/快退/音量/全屏/查询状态 |
| category | `tool` |

**input_schema**：

```json
{
  "type": "object",
  "properties": {
    "action": {
      "type": "string",
      "enum": ["play", "pause", "stop", "seek", "volume", "fullscreen", "get_state"],
      "description": "控制动作"
    },
    "video_id": {"type": "string", "description": "视频 ID（action=play 时必填）"},
    "seconds": {"type": "integer", "description": "快进/快退秒数（action=seek 时必填，正=快进 负=快退）"},
    "volume": {"type": "number", "description": "音量 0-1（action=volume 时必填）"}
  },
  "required": ["action"]
}
```

**执行流程**：

```
action = play:
  1. VideoRepository.get_by_id(video_id) → 获取视频
  2. 附加 title / url（localPath 优先 / playUrl 兜底）/ lastPosition
  3. PluginBus.publish("video_control", payload)

action = get_state:
  1. VideoRepository.get_playback_state(video_id)
  2. 返回 {title, position, duration, play_count, last_played_at}
     （不依赖前端，直接查库）

其他 action（pause/stop/seek/volume/fullscreen）:
  直接 PluginBus.publish("video_control", payload)
```

---

## 5. video_plugin 插件设计

### 5.1 目录结构

```
plugins/builtin/video_plugin/
├── __init__.py
├── main.py                          # BasePlugin 生命周期
├── bridge/
│   ├── __init__.py
│   └── video_bridge.py              # VideoBridge(QObject)：JS 通信
├── config/
│   └── video_config.json            # 默认配置
├── index.html                       # 视频中心 UI
├── model/
│   ├── __init__.py
│   └── video_observer.py            # ★ PluginBus 直接订阅
└── view/
    ├── css/video.css                # 样式
    └── js/video.js                  # 前端逻辑
```

### 5.2 `main.py`（插件生命周期）

```python
class VideoPlugin(BasePlugin):
    name = "video_plugin"
    version = "1.0.0"
    description = "学前教学视频中心：播放、下载、断点续播"
    initial_size = {"width": 1200}

    def on_load(self):
        # 加载配置 + 确保 media/videos/ 目录存在
        # 创建 VideoObserver（订阅 PluginBus 事件）
        self._observer = VideoObserver(bridge)

    async def run(self, context=None):
        # 轻量常驻循环
        while True:
            await asyncio.sleep(30)

    def exit(self):
        # 停止 observer 订阅
        if self._observer:
            self._observer.stop()
```

### 5.3 `video_observer.py`（★ 核心：HTTP 命令服务器 + 事件订阅）

> 实际实现（2026-08-14）：CLI 脚本为独立进程，无法直接调用进程内 PluginBus，
> 故由 observer 起一个 127.0.0.1 随机端口 HTTP 命令服务器承接脚本命令，
> 再以 PluginBus **事件**分发（命令传送统一走事件通道，无命令文件）。

```python
class VideoObserver:
    """HTTP 命令服务器 + PluginBus 事件订阅（与系统监控同模式）"""

    def __init__(self, bridge):
        self.bridge = bridge
        # ★ 订阅事件（命令最终都汇入事件总线）
        PluginBus.subscribe("video_control", self.on_control)
        PluginBus.subscribe("video_updated", self.on_updated)
        # ★ 启动 HTTP 命令服务器（独立进程脚本通道）
        #  ThreadingHTTPServer(("127.0.0.1", 0)) → POST /video_command
        #  收到 payload → PluginBus.publish(payload["type"], payload)
        #  端口写入 storage/video_plugin.json 供脚本发现
        self._start_command_server()

    def on_control(self, payload):
        """播放控制事件 → 直接控制前端播放器"""
        self.bridge.execute_control(payload)  # execute_js

    def on_updated(self, payload):
        """视频库更新 → 前端自动刷新列表"""
        self.bridge.execute_js("window.videoApp.refreshList()")

    def stop(self):
        # 关闭 HTTP 服务器 + 取消事件订阅
        PluginBus.unsubscribe("video_control", self.on_control)
        PluginBus.unsubscribe("video_updated", self.on_updated)
```

### 5.4 `video_bridge.py`（JS 通信）

| 方法 | 说明 |
|------|------|
| `getVideos(filter_json)` | 获取视频列表（按科目/年级/来源/关键词筛选） |
| `getLastPosition(video_id)` | ★ 获取上次播放位置（断点续播用） |
| `updateLastPosition(video_id, position)` | ★ 保存播放位置（前端每 5 秒调用） |
| `incrementPlayCount(video_id)` | 播放次数 +1 |
| `downloadVideo(video_id)` | 启动下载（后台线程） |
| `deleteVideo(video_id)` | 删除视频（本地文件 + 数据库记录） |
| `openVideoFolder()` | 打开本地视频目录 |
| `execute_control(payload)` | AI 控制事件 → 前端播放器 |

### 5.5 `video_config.json`

```json
{
  "default_quality": "720p",
  "download_dir": "media/videos",
  "refresh_interval": 5,
  "position_save_interval": 5,
  "max_results": 50
}
```

---

## 6. 前端 UI 设计

### 6.1 布局（播放器左 + 播放列表右）

```
┌──────────────────────────────────────────────────────────────────────────┐
│  视频中心  [搜索框...] [🔍] [科目▼] [年级▼] [来源▼] [🔄] [📂]             │
├───────────────────────────────┬──────────────────────────────────────────┤
│  ▶️ 播放器（左侧·主区域）      │  📺 播放列表（右侧·侧栏）                   │
│  ┌─────────────────────────┐  │  ┌────────────────────────────────────┐  │
│  │                         │  │  │ [▶][封面] 幼儿园大班数学①           │  │
│  │    🎬 HTML5 <video>     │  │  │   📘 数学·大班 ⏱15:30 1080p       │  │
│  │    （断点续播）          │  │  │   ⏺ 上次播到 2:05                 │  │
│  └─────────────────────────┘  │  │   [▶播放] [⬇下载]                 │  │
│  ┌─────────────────────────┐  │  ├────────────────────────────────────┤  │
│  │ 📌 当前播放信息          │  │  │ [✓] 拼音启蒙教学                   │  │
│  │ 进度：12:30 / 15:30     │  │  │   📕 语文·学前班 ⏱20:00 720p      │  │
│  │ [🔗 打开源链接]          │  │  │   [▶播放] [✓已下载]               │  │
│  └─────────────────────────┘  │  ├────────────────────────────────────┤  │
│  💾 本地目录: media/videos/   │  │  [共 4 个视频] 🔽 加载更多           │  │
└───────────────────────────────┴──────────────────────────────────────────┘
```

### 6.2 `video.js` 关键逻辑

```javascript
// ===== 断点续播 =====
function play(video_id) {
    var video = getVideoById(video_id);
    player.src = video.localPath || video.playUrl;
    
    // ★ 断点续播
    var lastPos = window.video_bridge.getLastPosition(video_id);
    player.currentTime = lastPos || 0;
    player.play();
    
    incrementPlayCount(video_id);
    startPositionSave(video_id);
}

// ===== ★ 每 5 秒自动保存 =====
function startPositionSave(video_id) {
    if (_timer) clearInterval(_timer);
    _timer = setInterval(function() {
        if (!player.paused && !player.ended) {
            window.video_bridge.updateLastPosition(
                video_id, Math.floor(player.currentTime)
            );
        }
    }, 5000);
}

// ===== 暂停/结束时立即保存 =====
player.addEventListener('pause', savePosition);
player.addEventListener('ended', savePosition);

// ===== AI 控制入口 =====
function control(payload) {
    switch (payload.action) {
        case 'play':    if (payload.video_id) play(payload.video_id); else player.play(); break;
        case 'pause':   player.pause(); break;
        case 'stop':    player.pause(); player.currentTime = 0; break;
        case 'seek':    player.currentTime += parseInt(payload.seconds) || 0; break;
        case 'volume':  player.volume = Math.max(0, Math.min(1, parseFloat(payload.volume) || 0)); break;
        case 'fullscreen': if (player.requestFullscreen) player.requestFullscreen(); break;
    }
}
```

---

## 7. MD Skill（AI 知识库）

创建 `skills/md/preschool-video/SKILL.md`：

```markdown
---
name: preschool-video
enabled: true
description: 学前班教学视频 - AI 负责搜索教学视频、控制播放、下载、查询播放进度
---

# Preschool Video Skill

当用户需要学前班/幼儿园教学视频时，按本技能执行。

## 解析用户意图
提取科目（数学/语文/英语/科学/艺术/健康）+ 年级（学前班/大班/中班/小班）

## 搜索视频
用户说"帮我找xxx视频" → 调用 skill_video_search：
{"keyword": "幼儿园大班 数学 教学视频", "source": "自动", "limit": 10}

## 播放控制
| 用户指令 | 工具调用 |
|---------|---------|
| "播放xxx" | skill_video_control {"action":"play","video_id":"<ID>"} |
| "暂停" | {"action":"pause"} |
| "停止" | {"action":"stop"} |
| "快进 30 秒" | {"action":"seek","seconds":30} |
| "后退 10 秒" | {"action":"seek","seconds":-10} |
| "音量调到 80%" | {"action":"volume","volume":0.8} |
| "全屏" | {"action":"fullscreen"} |
| "播放到哪了" | {"action":"get_state","video_id":"<ID>"} |

## 下载视频
用户说"下载xxx" → skill_video_download：{"video_id": "<ID>", "quality": "720p"}

## 内容源优先级
1. 国家智慧教育平台（basic.smartedu.cn）— 首选（内容权威合规）
2. B站
3. 其他公开免费源

## 合规要求
仅搜索公开免费、有访问权限的视频，不绕过 DRM/付费墙/会员权限。
```

---

## 8. 事件流时序

### 8.1 视频搜索链路

```
用户："帮我找幼儿园大班数学视频"
    │
    ▼
AI 读取 SKILL → 提取意图
    │
    ▼
AI 运行 python scripts/video_search.py --keyword "幼儿园大班 数学"
    │
    ▼
脚本进程（独立进程）：yt-dlp 多源搜索 → 提取视频信息
    │
    ├─ VideoRepository.add_many() → 批量写入 video_library 表
    │
    └─ ★ HTTP POST /video_command {"type":"video_updated", added, total}
         │
         ▼
主进程 video_plugin 命令服务器 → PluginBus.publish("video_updated", {...})
         │
         ▼
    VideoObserver.on_updated()
         │
         ▼
    VideoBridge.execute_js("window.videoApp.refreshList()")
         │
         ▼
    前端视频列表自动刷新 ✅
```

### 8.2 视频播放链路（含断点续播）

```
用户："播放第一个"
    │
    ▼
AI 读取 SKILL → 提取意图
    │
    ▼
AI 运行 python scripts/video_control.py --action play --video-id "xxx"
    │
    ▼
脚本进程（独立进程）
    ├─ VideoRepository.get_by_id() → 获取 url + lastPosition
    │
    └─ ★ HTTP POST /video_command {"type":"video_control", action:"play", ...}
         │
         ▼
主进程 video_plugin 命令服务器 → PluginBus.publish("video_control", {...})
         │
         ▼
    VideoObserver.on_control()
         │
         ▼
    VideoBridge.execute_control() → execute_js
         │
         ▼
    前端 videoApp.control({action:'play', url, lastPosition})
         │
         ├─ player.src = url
         ├─ player.currentTime = lastPosition  ← ★ 断点续播
         ├─ player.play()
         ├─ incrementPlayCount()
         └─ 启动 5 秒定时器 → updateLastPosition() → 数据库
```

### 8.3 播放控制链路

```
用户："快进 30 秒"
    │
    ▼
AI 运行 python scripts/video_control.py --action seek --seconds 30
    │
    ▼
脚本 HTTP POST /video_command → 主进程 PluginBus.publish("video_control", {...})
    │
    ▼
VideoObserver.on_control → VideoBridge.execute_control()
    │
    ▼
execute_js → 前端 player.currentTime += 30 ✅
```

### 8.4 播放状态查询链路

```
用户："播放到哪了"
    │
    ▼
AI 运行 python scripts/video_control.py --action get_state --video-id "xxx"
    │
    ▼
脚本进程（独立进程）→ VideoRepository.get_playback_state()（直接查库，不依赖前端/事件）
    │
    ▼
脚本打印 {title, position:125, duration:930, play_count:3}
    │
    ▼
AI 回答："《幼儿园大班数学①》已播放到 2 分 05 秒" ✅
```

---

## 9. 文件清单

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `storage/database.py` | 修改 | 新增 `video_library` 表 + 5 个索引 |
| 2 | `storage/repositories/video_repo.py` | 新建 | `VideoRepository` 数据操作层 |
| 3 | `skills/builtin/video_skill.py` | 新建 | 3 个 Python Skill 类 |
| 4 | `user_config/defaults/skills_config.json` | 修改 | 启用视频 Skill |
| 5 | `skills/md/preschool-video/SKILL.md` | 新建 | AI 知识库 |
| 6 | `plugins/builtin/video_plugin/__init__.py` | 新建 | 插件包 |
| 7 | `plugins/builtin/video_plugin/main.py` | 新建 | 插件生命周期 |
| 8 | `plugins/builtin/video_plugin/bridge/__init__.py` | 新建 | |
| 9 | `plugins/builtin/video_plugin/bridge/video_bridge.py` | 新建 | JS 通信 |
| 10 | `plugins/builtin/video_plugin/model/__init__.py` | 新建 | |
| 11 | `plugins/builtin/video_plugin/model/video_observer.py` | 新建 | PluginBus 订阅 |
| 12 | `plugins/builtin/video_plugin/config/video_config.json` | 新建 | 配置 |
| 13 | `plugins/builtin/video_plugin/index.html` | 新建 | 视频中心 UI |
| 14 | `plugins/builtin/video_plugin/view/css/video.css` | 新建 | 样式 |
| 15 | `plugins/builtin/video_plugin/view/js/video.js` | 新建 | 前端逻辑 |
| 16 | `view/js/plugins.js` | 修改 | 注册视频插件图标 |
| 17 | `pyproject.toml` | 修改 | 添加 `yt-dlp` 依赖 |

---

## 10. 实施步骤

| 步骤 | 内容 | 说明 |
|------|------|------|
| ① | `storage/database.py` 添加 `video_library` 表 + 索引 | 修改现有文件 |
| ② | 创建 `storage/repositories/video_repo.py` | 新建 |
| ③ | 创建 `skills/builtin/video_skill.py`（3 个 Skill 类） | 新建 |
| ④ | 启用视频 Skill 配置（`skills_config.json`） | 修改 |
| ⑤ | 创建 `plugins/builtin/video_plugin/` 后端（main/bridge/observer/config） | 新建 |
| ⑥ | 创建 `plugins/builtin/video_plugin/` 前端（index.html/css/js） | 新建 |
| ⑦ | 注册插件图标 + 添加依赖 + 验证全链路 | 修改 + 测试 |

---

## 11. 验证场景

| # | 场景 | 预期结果 |
|---|------|---------|
| 1 | "帮我找幼儿园大班数学视频" | Skill 搜索 → 视频库新增多条 → 前端列表自动刷新 |
| 2 | "播放第一个" | 播放器切换 → 从上次位置续播 → 开始播放 |
| 3 | "快进 30 秒" | 播放器进度 +30 秒 |
| 4 | 播放 10 秒后关闭插件 | 数据库 `last_position` ≈ 10（5 秒定时器已保存） |
| 5 | 再次打开点击播放 | 从上次位置继续播放（断点续播）✅ |
| 6 | "暂停" | 播放器暂停 → 位置立即保存 |
| 7 | "播放到哪了" | AI 返回当前播放位置和时长 |
| 8 | "下载这个" | yt-dlp 下载 → 状态变"已下载" → 下次播放用本地文件 |
| 9 | 手动点击列表视频 | 左侧播放器播放 + 断点续播 |
| 10 | 列表筛选（科目/年级） | 只显示符合条件的视频 |

---

## 附录：事件总线说明（PluginBus）

| 事件名 | 发布者 | 订阅者 | 载荷 |
|--------|--------|--------|------|
| `video_control` | VideoControlSkill | VideoObserver | `{action, video_id, seconds, volume, url, localPath, lastPosition}` |
| `video_updated` | VideoSearchSkill / VideoDownloadSkill / VideoBridge | VideoObserver | `{added, total, video_id, status, progress}` |

> 与系统监控 `ai_reply` 事件完全同模式：Skill 在主进程内 `PluginBus.publish()`，插件 observer 直接 `PluginBus.subscribe()`。