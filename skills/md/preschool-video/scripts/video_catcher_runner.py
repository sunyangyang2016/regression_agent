# -*- coding: utf-8 -*-
"""
yt-dlp 搜索与解析执行器 + video-catcher 下载执行（preschool-video 内部模块）

搜索使用 yt-dlp bilisearch 获取候选 URL，再逐个解析完整元数据（标题/封面/UP主/时长）。
下载逻辑完全由 video-catcher skill 承担。
额外提供：网站认证信息管理（保存到 user_config/user/video_auth.json + 内存缓存，
播放时自动携带 Cookie/Token 等认证信息）。
"""
import json
import os
import subprocess
import sys
import threading
from urllib.parse import urlparse

# ==========================================
# 网站认证信息管理
# ==========================================
_AUTH_CACHE = {}          # {'domain': {type, cookies/token, user_agent, ...}}
_AUTH_LOCK = threading.Lock()
_AUTH_LOADED = False

# 认证文件路径：user_config/user/video_auth.json
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))
_AUTH_FILE = os.path.join(_PROJECT_ROOT, "user_config", "user", "video_auth.json")


def load_auths():
    """读取认证文件到内存（进程生命周期内只加载一次）"""
    global _AUTH_CACHE, _AUTH_LOADED
    if _AUTH_LOADED:
        return
    with _AUTH_LOCK:
        if _AUTH_LOADED:
            return
        try:
            with open(_AUTH_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _AUTH_CACHE.update(data.get("sites", {}))
        except (OSError, ValueError):
            pass
        _AUTH_LOADED = True


def save_auth(site, auth_info):
    """保存网站认证信息到文件 + 内存缓存

    site: 域名，如 'www.bilibili.com'
    auth_info: {'type': 'cookies'|'token'|'headers', 'cookies': '...', 'token': '...',
                'user_agent': '...', ...}
    """
    global _AUTH_CACHE
    load_auths()
    auth_info["saved_at"] = __import__("datetime").datetime.now().isoformat()
    with _AUTH_LOCK:
        _AUTH_CACHE[site] = auth_info
        data = {"sites": _AUTH_CACHE}
        try:
            os.makedirs(os.path.dirname(_AUTH_FILE), exist_ok=True)
            with open(_AUTH_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            print(f"[Auth] ⚠️ 保存认证文件失败: {e}")


def get_auth_for_url(url):
    """根据 URL 域名从内存缓存中查找认证信息（无则返回 None）

    依次尝试：完整域名 → 顶级域名（如 www.bilibili.com → bilibili.com）
    """
    load_auths()
    host = urlparse(url).netloc.lower()
    if not host:
        return None
    # 直接域名匹配
    if host in _AUTH_CACHE:
        return _AUTH_CACHE[host]
    # 尝试去掉子域名（如 www.）
    parts = host.split(".")
    if len(parts) >= 2:
        root = ".".join(parts[-2:])
        if root in _AUTH_CACHE:
            return _AUTH_CACHE[root]
    # 子域名前缀匹配（如 www.bilibili.com → bilibili.com）
    for domain, auth in _AUTH_CACHE.items():
        if host.endswith("." + domain) or host == domain:
            return auth
    return None


def build_auth_args(auth):
    """将认证信息转换为 yt-dlp 命令行参数列表

    返回 [arg1, val1, arg2, val2, ...]；无认证信息返回 []。
    """
    args = []
    if not auth:
        return args
    # Cookie 认证
    cookies = auth.get("cookies") or auth.get("cookie")
    if cookies:
        args += ["--add-header", f"Cookie: {cookies}"]
    # Token / Authorization 头
    token = auth.get("token") or auth.get("authorization")
    if token:
        args += ["--add-header", f"Authorization: Bearer {token}"]
    # 自定义请求头
    headers = auth.get("headers")
    if isinstance(headers, dict):
        for k, v in headers.items():
            args += ["--add-header", f"{k}: {v}"]
    # User-Agent
    ua = auth.get("user_agent")
    if ua:
        args += ["--user-agent", ua]
    return args


# ==========================================
# 下载执行（video-catcher 子进程隔离）
# ==========================================

def run_video_catcher(vc_script, url, out_root, quality=None, timeout=1800, run_dir=None):
    """调用 video-catcher 下载视频（subprocess 隔离封装）。

    quality: 可选画质（auto/480p/720p/1080p/2K/4K），默认不指定。
    run_dir: 若指定，则输出到该固定目录（video-catcher 使用 --run-dir，
             不会再创建 <日期>-<标题>/ 子目录，路径固定不变）。
    返回 (returncode, stdout, stderr)。
    """
    cmd = [sys.executable, vc_script, "download", url]
    if run_dir:
        # --run-dir 直接指定输出目录，不额外创建日期子目录
        cmd += ["--run-dir", str(run_dir)]
    else:
        cmd += ["--out-root", str(out_root)]
    if quality and quality != "auto":
        cmd += ["--quality", quality, "--quality-mode", "at-most"]
    # 注意：不向 video-catcher 传递 yt-dlp 专属认证参数（--add-header/--user-agent 等），
    # 否则 video-catcher CLI 会因无法识别参数而直接退出。认证由 video-catcher 自身处理。
    result = subprocess.run(
        cmd, capture_output=True, timeout=timeout,
        encoding="utf-8", errors="replace"
    )
    return result.returncode, result.stdout, result.stderr


def _fetch_meta(page_url, timeout=40):
    """解析单个 B 站视频的完整元数据（标题/封面/UP主/时长/描述等）。

    返回 dict（含 title/page_url/play_url/thumbnail/duration/...），失败返回 None。
    """
    try:
        cmd = [
            "yt-dlp", page_url,
            "--dump-single-json", "--skip-download",
            "--no-warnings", "--no-playlist",
        ]
        # 自动携带该网站已保存的认证信息
        auth = get_auth_for_url(page_url)
        if auth:
            # 注入到 yt-dlp 命令中间位置（page_url 之前）
            insert_at = 2  # 在 "yt-dlp" 和 page_url 之间插入认证参数
            cmd = cmd[:insert_at] + build_auth_args(auth) + cmd[insert_at:]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            return None
        info = json.loads(result.stdout)
        width = info.get("width")
        height = info.get("height")
        return {
            "title": info.get("title", ""),
            "page_url": info.get("webpage_url") or page_url,
            "play_url": info.get("url", ""),
            "thumbnail": info.get("thumbnail", ""),
            "duration": info.get("duration") or 0,
            "width": width,
            "height": height,
            "resolution": f"{width}x{height}" if width and height else None,
            "fps": info.get("fps"),
            "uploader": info.get("uploader", ""),
            "view_count": info.get("view_count") or 0,
            "description": (info.get("description") or "")[:500],
        }
    except (subprocess.TimeoutExpired, ValueError, KeyError, json.JSONDecodeError):
        return None


def ytdlp_search(keyword, limit=10, timeout=120):
    """使用 yt-dlp 搜索 B站视频并补全元数据。

    流程：bilisearch(flat) 获取候选 URL → 逐个解析完整信息。
    返回 [{"title", "page_url", "play_url", "thumbnail", "duration", ...}]
    失败/无结果返回 []。
    """
    try:
        cmd = [
            "yt-dlp",
            f"bilisearch{int(limit)}:{keyword}",
            "--flat-playlist", "--dump-json",
            "--no-warnings", "--no-playlist",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            print(f"[ytdlp_search] ⚠️ yt-dlp 搜索失败: {result.stderr[:200]}")
            return []
        # 1) 收集候选 URL
        candidates = []
        for line in result.stdout.strip().splitlines():
            try:
                info = json.loads(line)
                url = info.get("webpage_url") or info.get("url")
                if url:
                    candidates.append(url)
            except (ValueError, KeyError):
                continue
        candidates = candidates[:int(limit)]
        if not candidates:
            return []

        # 2) 逐个解析完整元数据
        videos = []
        for url in candidates:
            meta = _fetch_meta(url)
            if meta and meta.get("title"):
                videos.append(meta)
            elif meta:
                # 至少保留 URL 占位
                videos.append(meta)
        return videos[:int(limit)]
    except subprocess.TimeoutExpired:
        print("⏱️ yt-dlp 搜索超时")
        return []
    except Exception as e:
        print(f"❌ yt-dlp 搜索异常: {e}")
        return []


_YTDLP_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0")


def _ytdlp_fetch_urls(url, format_spec, auth, timeout):
    """执行 yt-dlp -g 并返回所有输出 URL 行（最多 2 行：视频流 + 音频流）。
    ★ 2026-08-13 修复：subprocess.run 包 try/except——yt-dlp 缺失/超时/崩溃时打印终端日志
      并返回错误信息，而非抛异常静默冒泡到 _resolve_online_url（终端零日志，用户无从排查）。"""
    cmd = [
        "yt-dlp", "-g",
        "--format", format_spec,
        "--user-agent", _YTDLP_UA,
        "--no-warnings", "--no-playlist",
    ]
    # 根据 URL 域名自动添加 Referer，帮助通过防盗链检查
    host = urlparse(url).netloc
    if host:
        cmd += ["--referer", f"https://{host}/"]
    cmd += ["--add-header", "Accept-Language: zh-CN,zh;q=0.9"]
    if auth:
        cmd += build_auth_args(auth)
    cmd.append(url)
    print(f"[ytdlp_get_url] 尝试 <{format_spec}> ...")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace"
        )
    except FileNotFoundError:
        msg = "yt-dlp 未安装，请安装后重试"
        print(f"[ytdlp_get_url] ❌ {msg}")
        return None, msg
    except subprocess.TimeoutExpired:
        msg = f"yt-dlp 解析超时（{timeout}s）"
        print(f"[ytdlp_get_url] ❌ {msg}")
        return None, msg
    except Exception as e:
        msg = str(e)[:200]
        print(f"[ytdlp_get_url] ❌ 解析异常: {msg}")
        return None, msg
    if result.returncode != 0:
        print(f"[ytdlp_get_url] ❌ 方案 <{format_spec}> 失败: {result.stderr[:200]}")
        return None, result.stderr[:200]
    urls = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    if urls:
        print(f"[ytdlp_get_url] ✅ 方案 <{format_spec}> 返回 {len(urls)} 个地址")
    return urls, None


def ytdlp_get_url(url, timeout=60):
    """使用 yt-dlp 解析视频真实可播放地址，返回流 URL 列表。

    自动携带该网站已保存的认证信息（Cookie/Token/UA 等）。
    返回语义：
      - [video_url, audio_url]  → DASH 分离流（视频流 + 音频流，前端需同步双播放）
      - [single_url]            → 完整流（含音视频，直接播放）
      - []                      → 解析失败（空列表）
    """
    if not url:
        print("[ytdlp_get_url] ⚠️ URL 为空")
        return []
    auth = get_auth_for_url(url)

    # 1) ★ 方案 A：优先单文件 mp4 完整流（含音视频，QMediaPlayer 单源可播）
    urls, err = _ytdlp_fetch_urls(url, "best[ext=mp4]", auth, timeout)
    if urls and len(urls) == 1:
        return urls

    # 2) 通用完整流（mp4/m4a/webm 等单文件含音视频）
    urls2, err2 = _ytdlp_fetch_urls(
        url, "best[ext=mp4]/best[ext=m4a]/best", auth, timeout)
    if urls2 and len(urls2) == 1:
        return urls2

    # 3) 完整流失败/仅分离 → 尝试 DASH 分离流（视频流 + 音频流两行输出）
    urls3, err3 = _ytdlp_fetch_urls(
        url, "bestvideo+bestaudio/bestvideo/best", auth, timeout)
    if urls3:
        return urls3

    # 4) 全部失败
    print(f"[ytdlp_get_url] ⚠️ 解析失败: {err or err2 or err3}")
    return []


def search_videos(keyword, limit=10):
    """搜索入口：直接使用 yt-dlp bilisearch 搜索 B站视频并补全元数据。

    返回与 ytdlp_search 一致结构的视频列表。
    """
    return ytdlp_search((keyword or "").strip(), limit=int(limit or 10))