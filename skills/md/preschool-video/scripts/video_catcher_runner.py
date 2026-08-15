# -*- coding: utf-8 -*-
"""
yt-dlp 搜索与解析执行器 + video-catcher 下载执行（preschool-video 内部模块）

搜索使用 yt-dlp bilisearch 获取候选 URL，再逐个解析完整元数据（标题/封面/UP主/时长）。
下载逻辑完全由 video-catcher skill 承担。
额外提供：网站认证信息管理（保存到 user_config/user/video_auth.json + 内存缓存，
播放时自动携带 Cookie/Token 等认证信息）。
"""
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

# 项目根目录 / 命令文件统一从 common 取（★ 2026-08-14 修复 off-by-one：
#   此前本模块自己用 4 层 dirname 解析，_PROJECT_ROOT 落在 <root>/skills/，
#   导致认证文件 video_auth.json 被写到 skills/user_config/user/ 而非
#   user_config/user/video_auth.json）
from common import project_root
_PROJECT_ROOT = project_root()

# ==========================================
# 网站认证信息管理
# ==========================================
_AUTH_CACHE = {}          # {'domain': {type, cookies/token, user_agent, ...}}
_AUTH_LOCK = threading.Lock()
_AUTH_LOADED = False

# 认证文件路径：user_config/user/video_auth.json
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

_PROGRESS_PCT_RE = re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
_PROGRESS_BYTES_RE = re.compile(r"\[download\]\s+([\d.]+)\s*([KMGT]?i?B)")
# ★ 2026-08-15 DASH 整体进度："of <大小> <单位>"（当前流总字节数，如 of 128.00MiB）
_STREAM_SIZE_RE = re.compile(r"of\s+([\d.]+)\s*([KMGT]?i?B)")
_SIZE_UNITS = {"B": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "TiB": 1024 ** 4}


def _stream_size_bytes(match):
    """把 `of 128.00MiB` 匹配结果换算成字节；匹配失败返回 0.0"""
    try:
        return float(match.group(1)) * _SIZE_UNITS.get(match.group(2) or "B", 1)
    except (TypeError, ValueError):
        return 0.0


def _stream_video_catcher(cmd, timeout, on_progress):
    """流式运行 video-catcher：逐行解析 yt-dlp 的 `[download]` 进度并回调 on_progress。

    节流：百分比变化 ≥2 或距上次回调 ≥500ms 才回调一次（避免高频写 DB / execute_js）。
    on_progress(percent, text)：percent 为 0-100 整数；总长未知（total_bytes=0）时
    percent=None、text 为已下载字节文本（如 "34.5MiB"）。
    ★ 2026-08-15 DASH 整体进度：B站等分离流 = 纯视频流 + 纯音频流两段各自下载、各自
      0→100%。这里按每段 `of X` 总大小 + 百分比大幅回落（100→0 = 换下一段）换算成
      累计字节，回调【整体】0-100%——视频流 0→100 后音频流从剩余比例继续爬到 100%，
      避免进度条"两次 0→100"让人误以为下载了两遍。单段（合并格式/未知总长）时
      整体进度 = 该段百分比，行为不变。
    返回 (returncode, stdout, stderr)，契约与 subprocess.run(capture_output=True) 一致。
    """
    out_lines = []
    err_lines = []
    last_pct = -10
    last_text = None
    last_time = 0.0
    phase_total = 0.0    # 当前下载段（流）的总字节
    done_bytes = 0.0     # 已完整下载的段累计字节
    had_phase = False
    last_reported = -10  # 已回调给前端的百分比（单调不降：整体进度只升不降）

    def _maybe_report(line):
        nonlocal last_pct, last_text, last_time, phase_total, done_bytes, had_phase, last_reported
        if "[download]" not in line:
            return
        m = _PROGRESS_PCT_RE.search(line)
        now = time.monotonic()
        if m:
            pct = int(round(float(m.group(1))))
            text = None
            tm = _STREAM_SIZE_RE.search(line)
            new_total = _stream_size_bytes(tm) if tm else 0.0
            # 换段判定：百分比从上一段高位（100）大幅回落到低位（0）→ 进入下一段下载
            if had_phase and pct < last_pct - 5:
                if phase_total > 0:
                    done_bytes += phase_total
                phase_total = new_total
            elif new_total > 0:
                phase_total = new_total
            had_phase = True
            # ★ 整体进度 =（已下载段字节 + 当前段已下载）/（已下载段 + 当前段总大小）
            #   单段（合并格式）时 done_bytes=0，整体=该段百分比，行为不变。
            if phase_total > 0 and done_bytes > 0:
                overall = (done_bytes + pct / 100.0 * phase_total) / (done_bytes + phase_total) * 100.0
                pct = int(round(overall))
            # ★ 单调不降：视频段爬到 100% 后切音频段，整体会回落到视频所占比例（如 85%）——
            #   直接上报会造成"100→85→100"倒退观感。钳制为只升不降，音频段在后台完成。
            if pct < last_reported:
                pct = last_reported
            if abs(pct - last_pct) < 2 and now - last_time < 0.5:
                return
            last_pct = pct
            if pct > last_reported:
                last_reported = pct
        else:
            mb = _PROGRESS_BYTES_RE.search(line)
            pct = None
            text = mb.group(0) if mb else line.strip()
            if text == last_text and now - last_time < 0.5:
                return
            last_text = text
        last_time = now
        try:
            on_progress(pct, text)
        except Exception:
            pass

    def _pump(stream, lines, forward):
        try:
            for line in iter(stream.readline, ""):
                lines.append(line)
                if forward:
                    _maybe_report(line)
        except Exception:
            pass
        finally:
            try:
                stream.close()
            except Exception:
                pass

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    t_out = threading.Thread(target=_pump, args=(proc.stdout, out_lines, True), daemon=True)
    t_err = threading.Thread(target=_pump, args=(proc.stderr, err_lines, True), daemon=True)
    t_out.start()
    t_err.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    t_out.join()
    t_err.join()
    return proc.returncode, "".join(out_lines), "".join(err_lines)


def run_video_catcher(vc_script, url, out_root, quality=None, timeout=1800, run_dir=None, on_progress=None):
    """调用 video-catcher 下载视频（subprocess 隔离封装）。

    quality: 可选画质（auto/480p/720p/1080p/2K/4K），默认不指定。
    run_dir: 若指定，则输出到该固定目录（video-catcher 使用 --run-dir，
             不会再创建 <日期>-<标题>/ 子目录，路径固定不变）。
    on_progress: 可选回调 on_progress(percent, text)——yt-dlp [download] 进度逐行解析后
                 调用（percent 为 0-100 整数；总长未知时 percent=None、text 为字节文本）。
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
    if on_progress is not None:
        # ★ 2026-08-15 流式：实时解析下载进度（[download] 行由 ytdlp_downloader 转发）
        return _stream_video_catcher(cmd, timeout, on_progress)
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


# ==========================================
# ★ 2026-08 多P整套搜索：单次 yt-dlp 调用取回多P视频全部集元数据
# ==========================================

# 搜索一次最多入库的视频总数上限（对应 plugins/builtin/video_plugin/config/video_config.json 的 max_results）
MAX_SEARCH_TOTAL = 100
# 单个系列（多P视频）最多展开的集数上限（防御异常大系列）
_MAX_SERIES_ENTRIES = 200
# ★ 2026-08-14 候选解析并行度：每批并发解析的候选数（3 worker，提升吞吐；B站反爬敏感可回调为 2）
_PARALLEL = 3


def _entry_to_video(entry, series_id=None, series_title=None,
                    default_uploader="", default_view_count=0, default_description=""):
    """将 yt-dlp 单条 entry（多P的一集）或顶层 info（单集视频）规范化为视频 dict。

    新增字段（入库去重用）：
      video_id      平台唯一ID（多P某集 = BVxxx_pN；单集 = BV id）
      episode_index 集序号（playlist_index；单集为 None）
      series_id    系列顶层 BV id（单集为 None）
      series_title  系列顶层标题（单集为 None）
    source 固定 'bilibili'，修复此前 B站 结果被标成"未知"的问题。
    缺 webpage_url / 空标题 的条目返回 None。
    """
    page_url = entry.get("webpage_url") or entry.get("url") or ""
    if not page_url:
        return None
    title = (entry.get("title") or "").strip()
    episode_index = entry.get("playlist_index")
    if not title and series_title and episode_index:
        title = f"{series_title} 第{episode_index}集"
    if not title:
        return None
    width = entry.get("width")
    height = entry.get("height")
    return {
        "title": title,
        "page_url": page_url,
        "play_url": entry.get("url") or page_url,
        "thumbnail": entry.get("thumbnail") or "",
        "duration": entry.get("duration") or 0,
        "width": width,
        "height": height,
        "resolution": f"{width}x{height}" if width and height else None,
        "fps": entry.get("fps"),
        "uploader": entry.get("uploader") or default_uploader,
        "view_count": entry.get("view_count") or default_view_count,
        "description": (entry.get("description") or default_description or "")[:500],
        "source": "bilibili",
        "video_id": entry.get("id"),
        "episode_index": episode_index,
        "series_id": series_id,
        "series_title": series_title,
    }


def fetch_series_and_meta(page_url, timeout=60):
    """解析单个 B站视频并判断是否多P：返回 (is_series, episode_count, videos)。

    与 _fetch_meta 的关键区别：不带 --no-playlist，多P视频一次取回全部集的完整元数据。
      - 多P:  (True,  N, [每集 dict ...])
      - 单集: (False, 1, [单个 dict])
      - 失败: (False, 0, [])
    """
    try:
        cmd = [
            "yt-dlp", page_url,
            "--dump-single-json", "--skip-download",
            "--no-warnings",
        ]
        # 自动携带该网站已保存的认证信息（与 _fetch_meta 一致，插在 yt-dlp 与 page_url 之间）
        auth = get_auth_for_url(page_url)
        if auth:
            cmd = cmd[:2] + build_auth_args(auth) + cmd[2:]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace"
        )
        if result.returncode != 0:
            print(f"[fetch_series_and_meta] ⚠️ 解析失败: {result.stderr[:200]}")
            return False, 0, []
        info = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, ValueError, json.JSONDecodeError) as e:
        print(f"[fetch_series_and_meta] ⚠️ 解析异常: {e}")
        return False, 0, []

    return _expand_series(info)


def _expand_series(info):
    """从 yt-dlp --dump-single-json 的 info dict 展开视频列表（纯逻辑，无子进程，可单测）。

    返回 (is_series, episode_count, videos)：
      - 多P:  (True,  N, [每集 dict ...])
      - 单集: (False, 1, [单个 dict])
      - 无效: (False, 0, [])
    """
    series_id = info.get("id")             # 顶层 BV id
    series_title = (info.get("title") or "").strip()
    entries = info.get("entries")
    if entries:
        videos = []
        for idx, e in enumerate(entries):
            if idx >= _MAX_SERIES_ENTRIES:
                print(f"[fetch_series_and_meta] ⚠️ 系列超过 {_MAX_SERIES_ENTRIES} 集，截断")
                break
            v = _entry_to_video(
                e,
                series_id=series_id,
                series_title=series_title,
                default_uploader=info.get("uploader", ""),
                default_view_count=info.get("view_count") or 0,
                default_description=info.get("description", ""),
            )
            if v:
                videos.append(v)
        if videos:
            return True, len(entries), videos
        return False, 0, []

    # 单集视频：顶层 info 即为该视频元数据
    v = _entry_to_video(info)
    if not v:
        return False, 0, []
    return False, 1, [v]


def ytdlp_search(keyword, limit=50, timeout=300, max_total=None):
    """使用 yt-dlp 搜索 B站视频并补全元数据（★ 多P整套：自动展开为全部集）。

    流程：bilisearch(flat) 获取候选 URL → 分批并发 fetch_series_and_meta
         （多P视频一次取回全部集，返回列表为整套展开后的全部视频）。
    返回 [{"title", "page_url", "play_url", "thumbnail", "duration", ...}]
    失败/无结果返回 []。总数受 max_total 上限约束（默认 MAX_SEARCH_TOTAL=100，
    达到上限时保留当前完整系列，不截半），并带墙钟截止时间防后台卡死
    （deadline = max(60, timeout)，与 execute_system_command 最大 300s 对齐）。
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

        # 2) 分批并发解析（多P自动展开整套）：每批 _PARALLEL 个，批间检查 deadline / max_total
        max_total = int(max_total or MAX_SEARCH_TOTAL)
        videos = []
        seen = set()
        deadline = time.monotonic() + max(60, timeout)
        for i in range(0, len(candidates), _PARALLEL):
            if time.monotonic() > deadline:
                print("[ytdlp_search] ⏱️ 达到搜索时限，提前收尾")
                break
            batch = candidates[i:i + _PARALLEL]
            with concurrent.futures.ThreadPoolExecutor(max_workers=_PARALLEL) as ex:
                future_to_url = {ex.submit(fetch_series_and_meta, url, timeout=45): url
                                 for url in batch}
                for fut in concurrent.futures.as_completed(future_to_url):
                    url = future_to_url[fut]
                    try:
                        _is_series, _count, metas = fut.result()
                    except Exception as e:
                        print(f"[ytdlp_search] ⚠️ 解析 {url[:60]} 失败: {e}")
                        continue
                    for m in metas:
                        if not m.get("title"):
                            continue
                        # 并行结果去重（候选可能重叠/同一系列出现多次）
                        key = (m.get("page_url") or m.get("video_id") or m.get("title")).strip()
                        if key in seen:
                            continue
                        seen.add(key)
                        videos.append(m)
                    if len(videos) >= max_total:
                        print(f"[ytdlp_search] 已达结果上限 {max_total}，停止展开")
                        break
            if len(videos) >= max_total:
                break
        return videos
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
        err_txt = result.stderr[:200]
        # ★ 2026-08-15 优化："Requested format is not available" 表示该站没有对应格式
        #   （DASH 分离站没有"音视频合并"单文件），是正常的格式降级信号而非故障。
        #   用 ⏩ 弱提示，避免每次播放 B站 都刷一排 ❌ 让用户误以为解析坏了。
        if "Requested format is not available" in err_txt:
            print(f"[ytdlp_get_url] ⏩ 方案 <{format_spec}> 跳过: {err_txt}")
        else:
            print(f"[ytdlp_get_url] ❌ 方案 <{format_spec}> 失败: {err_txt}")
        return None, err_txt
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

    # ★ 2026-08-15 优化：B站（含 b23.tv 短链）为纯 DASH 分离流——视频格式全部
    #   "video only"（mp4/m4s 容器但无音轨），音频单独 m4a，不存在"音视频合并"的
    #   单文件，best[ext=mp4]/best[ext=m4a]/best 对该站必然匹配 0 个格式、每次白白
    #   启动 2 次注定失败的 yt-dlp 子进程。B站直接走 DASH 分离方案（一条命令出
    #   视频流+音频流两行），既省两次解析时间又不刷 ❌ 日志。
    host = (urlparse(url).netloc or "").lower()
    if "bilibili.com" in host or "b23.tv" in host:
        urls_b, err_b = _ytdlp_fetch_urls(
            url, "bestvideo+bestaudio/bestvideo/best", auth, timeout)
        if urls_b:
            return urls_b
        print(f"[ytdlp_get_url] ⚠️ B站解析失败: {err_b}")
        return []

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


def search_videos(keyword, limit=50, source=None):
    """搜索入口：多源搜索，目标源取不到数据时自动回退 B站（绝不无结果/崩）。

    source: None/'自动' → B站（默认稳定源）；
            'bilibili'/'B站' → B站；'智慧教育平台'/'smartedu' → 智慧教育平台；
            '优酷'/'youku' → 优酷。
    返回与 ytdlp_search 一致结构的视频列表。
    """
    keyword = (keyword or "").strip()
    limit = int(limit or 50)
    src_key = _SOURCE_MAP.get((source or "").strip().lower())
    if src_key == "smartedu":
        videos = _search_smartedu(keyword, limit)
        if videos:
            return videos
        print("⚠️ 智慧教育平台搜索未取到结果，自动回退 B站")
    elif src_key == "youku":
        videos = _search_youku(keyword, limit)
        if videos:
            return videos
        print("⚠️ 优酷搜索未取到结果，自动回退 B站")
    # 默认 / 回退 → B站
    return ytdlp_search(keyword, limit)


# ==========================================
# 多源搜索：智慧教育平台 / 优酷（尽力而为）
# ★ 2026-08-14 实测：两源搜索接口均靠 JS 渲染 / 需签名，简单 GET 常拿不到数据，
#   因此实现为 best-effort —— 抓得到则返回结果，抓不到返回 [] 由 search_videos 回退 B站。
# ==========================================

_SOURCE_MAP = {
    "bilibili": "bilibili", "b站": "bilibili",
    "智慧教育平台": "smartedu", "smartedu": "smartedu", "智慧": "smartedu",
    "优酷": "youku", "youku": "youku",
}
# 视频条目里常见的 URL 字段名（泛化识别用）
_URL_KEYS = ("url", "pageUrl", "page_url", "playUrl", "videoUrl", "href", "resourceUrl")
# 常见缩略图字段名
_THUMB_KEYS = ("thumbnail", "coverUrl", "cover_url", "imageUrl", "pic", "thumbUrl")


def _http_get(url, timeout=15, referer=None):
    """通用 GET 请求（带 UA/Referer），返回解码文本或 None"""
    import urllib.request
    headers = {
        "User-Agent": _YTDLP_UA,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[search] ⚠️ 请求失败: {url[:70]}… ({type(e).__name__})")
        return None


def _extract_embedded_json(html, patterns):
    """从 HTML 中提取内嵌 JSON（如 window.__INITIAL_DATA__ = {...}），失败返回 None"""
    import re
    for pat in patterns:
        m = re.search(pat, html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except (ValueError, json.JSONDecodeError):
                continue
    return None


def _collect_video_items(data):
    """递归收集疑似视频条目：dict 同时含标题字段与 URL 字段才视为一条"""
    items = []

    def walk(obj):
        if isinstance(obj, dict):
            has_title = isinstance(obj.get("title"), str) or isinstance(obj.get("name"), str)
            has_url = any(k in obj for k in _URL_KEYS)
            if has_title and has_url:
                items.append(obj)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(data)
    # 按 title+url 去重
    seen = set()
    uniq = []
    for it in items:
        key = (str(it.get("title") or it.get("name") or ""), str(it.get("pageUrl") or it.get("url") or ""))
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)
    return uniq


def _normalize_search_items(items, source):
    """把泛化收集的条目规范化为视频 dict（多源共用）"""
    out = []
    for it in items:
        title = str(it.get("title") or it.get("name") or "").strip()
        if not title:
            continue
        url = next((str(it[k]) for k in _URL_KEYS if it.get(k)), "")
        if not url:
            continue
        if url.startswith("//"):
            url = "https:" + url
        dur = it.get("duration") or it.get("timeLength") or it.get("totalTime") or 0
        try:
            dur = int(float(dur))
        except (TypeError, ValueError):
            dur = 0
        out.append({
            "title": title,
            "page_url": url,
            "play_url": url,
            "thumbnail": next((str(it[k]) for k in _THUMB_KEYS if it.get(k)), ""),
            "duration": dur,
            "source": source,
        })
    return out


def _search_smartedu(keyword, limit=10):
    """智慧教育平台搜索（尽力而为）：GET so.smartedu.cn/sousou/searchList"""
    import urllib.parse
    kw = urllib.parse.quote(keyword)
    candidates = [
        f"https://so.smartedu.cn/sousou/searchList?keyword={kw}&type=video&pageNo=1&pageSize={limit}",
        f"https://so.smartedu.cn/sousou/searchList?keyword={kw}&type=video",
    ]
    for url in candidates:
        text = _http_get(url, referer="https://basic.smartedu.cn/")
        if not text:
            continue
        try:
            data = json.loads(text)
        except (ValueError, json.JSONDecodeError):
            continue
        items = _collect_video_items(data)
        if items:
            return _normalize_search_items(items, "智慧教育平台")[:limit]
    return []


def _search_youku(keyword, limit=10):
    """优酷搜索（尽力而为）：抓 so.youku.com/search/q_ 页解析内嵌 JSON"""
    import urllib.parse
    kw = urllib.parse.quote(keyword)
    url = f"https://so.youku.com/search/q_{kw}"
    html = _http_get(url, referer="https://www.youku.com/")
    if not html:
        return []
    patterns = [
        r"window\.__INITIAL_DATA__\s*=\s*(\{.*?\})\s*;",
        r"window\.__PRELOADED_STATE__\s*=\s*(\{.*?\})\s*;",
        r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;",
    ]
    data = _extract_embedded_json(html, patterns)
    if not data:
        return []
    items = _collect_video_items(data)
    return _normalize_search_items(items, "优酷")[:limit]


# ==========================================
# 科目/年级/来源推断（video_search.py 与 video_bridge.py 共用，消除双份实现）
# ==========================================

def classify_source(source):
    """来源规范化（兼容各来源文案）"""
    if not source:
        return "未知"
    s = str(source)
    if "智慧" in s:
        return "智慧教育平台"
    if "bili" in s.lower() or "b站" in s:
        return "bilibili"
    if "优酷" in s or "youku" in s.lower():
        return "优酷"
    return s


def guess_subject(keyword):
    """从关键词猜测科目
    ★ 2026-08-15 古诗 → 语文；儿歌 → 艺术。
    """
    subjects = {
        "数学": "数学", "算术": "数学", "数字": "数学", "计算": "数学",
        "语文": "语文", "拼音": "语文", "识字": "语文", "汉字": "语文", "古诗": "语文",
        "英语": "英语", "字母": "英语", "abc": "英语",
        "科学": "科学", "实验": "科学", "自然": "科学",
        "艺术": "艺术", "画画": "艺术", "美术": "艺术", "音乐": "艺术", "儿歌": "艺术",
        "健康": "健康", "体育": "健康", "安全": "健康",
    }
    kw = (keyword or "").lower()
    for k, v in subjects.items():
        if k in kw:
            return v
    return None


# 科目别名 → 规范值（★ 2026-08-15 用户需求：拼音/识字/古诗 归属 语文；儿歌 归属 艺术）
_SUBJECT_ALIASES = {
    "拼音": "语文", "识字": "语文", "汉字": "语文", "古诗": "语文", "诗词": "语文",
    "儿歌": "艺术",
}


def normalize_subject(subject):
    """规范化科目：拼音/识字/汉字/古诗/诗词 → 语文，儿歌 → 艺术；其余原样返回。

    用「包含」匹配（科目标签可能是『古诗词』『拼音识字』等复合词），非空值兜底原样返回。
    """
    if not subject:
        return None
    s = str(subject).strip()
    if not s:
        return None
    for k, v in _SUBJECT_ALIASES.items():
        if k in s:
            return v
    return s


# 年级别名 → 规范值（★ 2026-08-15 用户需求：幼儿/幼小 归属 小班；幼儿园泛称 → 学前班）
_GRADE_ALIASES = {
    "幼儿": "小班", "幼小": "小班", "幼小衔接": "小班",
    "幼儿园": "学前班",
}


def normalize_grade(grade):
    """规范化年级：幼儿/幼小/幼小衔接 → 小班，幼儿园 → 学前班；其余原样返回"""
    if not grade:
        return None
    g = str(grade).strip()
    if not g:
        return None
    return _GRADE_ALIASES.get(g, g)


def guess_grade(keyword):
    """从关键词猜测年级
    ★ 2026-08-14 大班/中班/小班优先于「幼儿园」泛称（dict 顺序即优先级），
      避免「幼儿园大班 数学」被误判为学前班；仅含「幼儿园」时默认学前班。
    ★ 2026-08-15 新增「一年级」；幼儿/幼小（含幼小衔接）归属 小班。
    """
    grades = {
        "二年级": "二年级",
        "一年级": "一年级",
        "大班": "大班", "中班": "中班", "小班": "小班",
        "学前班": "学前班",
        # 注意顺序：幼小衔接 / 幼儿园 需先于 幼小 / 幼儿 命中（后者是前者子串），
        #   统一经 normalize_grade 收敛到规范值。
        "幼小衔接": "幼小", "幼儿园": "幼儿园",
        "幼小": "幼小", "幼儿": "幼儿",
    }
    for k, v in grades.items():
        if k in (keyword or ""):
            return normalize_grade(v)
    return None


def guess_metadata(video, keyword, source=None):
    """为视频补全 subject/grade/source 推断（各源 searcher 已填 source 则不覆盖）"""
    if not video.get("subject"):
        video["subject"] = guess_subject(keyword)
    if not video.get("grade"):
        video["grade"] = guess_grade(keyword)
    if not video.get("source"):
        video["source"] = classify_source(source)
    # ★ 2026-08-15 年级/科目统一规范化：新推断与各源元数据同口径
    #   （幼儿/幼小 → 小班；拼音/识字/古诗 → 语文，儿歌 → 艺术）
    video["grade"] = normalize_grade(video.get("grade"))
    video["subject"] = normalize_subject(video.get("subject"))
    return video