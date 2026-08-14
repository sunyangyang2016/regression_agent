"""解码全权 ffmpeg + 渲染 Web <img> + 音频 sounddevice（绕开 Qt 媒体管线/DirectShow）
ffmpeg 解出 JPEG 帧 -> base64 -> 前端 onFrame(<img> 直接显示)
ffmpeg 解出 PCM -> sounddevice 播放（支持 HEVC/AAC/H.264/AV1）
支持：高清(1280/q2)、进度/时长、暂停/续播、快进快退、音量

★ 2026-08 修复：原生 <video> 走 ffmpeg 转码 HTTP 流时
  1) 动态解析 ffmpeg/ffprobe 完整路径（避免 WinError 2）
  2) 自动探测 H.264 编码器（libx264 → h264_amf/h264_qsv/h264_nvenc → mpeg4 兜底）
  3) 在线 URL 携带 Referer/UA 头（修复 B站 CDN 403）
  4) 转码启动后健康检查（进程存活 + stderr 错误回收）
  5) HTTP 流串行响应（threading.Lock 防多线程抢读 stdout 数据错乱）

★ 2026-08 智能播放引擎：
  QWebEngine (PyQt5 5.15.2) 官方构建仅原生支持 VP8/VP9/Opus/MP3/FLAC，
  H.264/AAC/HEVC 因专利授权被编译期禁用。
  → 新增 _probe_codec_compat()：探测源文件编码，
    若是 QWebEngine 原生支持的格式（WebM/VP9/VP8/Opus/MP3/FLAC）→ 直接播放（零转码）；
    否则 → ffmpeg 实时转码为 VP8/Opus WebM（更快的实时流方案）。
"""
import base64
import bisect
import json
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from storage.repositories.video_repo import VideoRepository

# ★ 动态解析 ffmpeg/ffprobe 完整路径（优先 venv/Scripts、PATH）
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
WIDTH = 1280          # ★ 画质：720p 级帧宽（原 480 过糊）
AR = 44100
CH = 2
JPEGQ = 2             # ★ 画质：JPEG 高质量（原 q5 过压缩）

# ★ 完整 .webm 缓存目录（含 Duration → 原生 controls 显示总时长；按 video_id 缓存秒开）
#   2026-08-13 按用户要求改为「与下载视频同目录」：user_config/media/videos/{video_id}/
#   （下载目录结构：user_config/media/videos/{video_id}/xxx.mp4）
#   → 缓存文件路径 = user_config/media/videos/{video_id}/{video_id}.cache.webm
#   ★ 2026-08-13 修复：原实现少两层 dirname → 错误指向 plugins/builtin/user_config/media/videos，
#     与下载/数据库目录（仓库根 user_config/）不同根，缓存永远写错位置。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
))))
MEDIA_VIDEOS_DIR = os.path.join(_PROJECT_ROOT, "user_config", "media", "videos")
os.makedirs(MEDIA_VIDEOS_DIR, exist_ok=True)

# ★ QWebEngine 5.15.2 原生支持的容器/编码（探测验证）
# canPlayType 结果：VP8/VP9/MP3/Opus/FLAC = "probably"；H264/AAC/HEVC/AC3 = ""
_QWE_NATIVE_VIDEO = ("vp8", "vp9")
_QWE_NATIVE_AUDIO = ("opus", "vorbis", "mp3", "flac")
_QWE_NATIVE_CONTAINERS = (".webm", ".ogg", ".mp3", ".flac")

# ★ 编码器探测结果缓存（进程内一次探测；否则每次 play/seek 都重复跑 `ffmpeg -encoders` 两个子进程）
_ENCODER_CACHE = {}


class FFmpegDecoder:
    def __init__(self, webview=None):
        self._webview = webview
        self._repo = VideoRepository()
        self._vid = None          # 当前视频 id
        self._proc = None         # 视频 ffmpeg 子进程
        self._aproc = None        # 音频 ffmpeg 子进程
        self._stop = False        # 停止/暂停标志
        self._thread = None
        self._fps = 25.0
        self._duration = 0.0      # 视频总时长（秒）
        self._pos = 0.0           # 当前播放位置（秒）
        self._base_pos = 0.0      # 本次启动的起始位置（-ss）
        self._last_src = None     # 暂停/快进重开用的源
        self._last_vid = None
        self._paused = False
        self._paused_at = 0.0     # 暂停时的位置
        self._vol = 0.8            # 音量 0~1
        self._server = None       # HTTP 流服务器
        self._port = 0
        self._last_audio_src = None
        self._has_separate_audio = False
        self._online_mode = False   # ★ 2026-08-13 在线模式标记（不加 -t、保留数据库时长供 virtual_total 估算）
        # ★ 背压内存缓冲（deque 分块）：ffmpeg stdout → chunks → HTTP 提供数据
        #   缓冲满时暂停读取（ffmpeg 写 pipe 阻塞 → 自然降速），数据永不丢失
        #   ★ 2026-08-13 修复：原环形丢弃方案在 GPU 10-20x 转码下缓冲秒满
        #     → 最老数据被丢弃 → Chromium 按 1x 播放时请求的数据已不在 → 「播几秒就停」
        self._chunks = deque()    # 每块最大 64KB
        self._chunk_sizes = deque()  # 每块实际字节数（与 _chunks 一一对应）
        self._buf_start = 0       # 最老数据在整体流中的绝对偏移
        self._buf_size = 0        # 当前缓冲总字节数（背压）
        self._buf_closed = False  # ffmpeg 已退出、无更多数据
        self._buf_lock = threading.Lock()
        # ★ 2026-08-13 缓冲代际：每次开启新流（reset/seek/回退）递增，
        #   旧写线程的 finally 只能在自己的代际内写 _buf_closed，防止污染新流
        self._buf_gen = 0
        # ★ webm 缓存后台构建去重（同一 video_id 只允许一个构建线程）
        self._cache_building = set()
        self._cache_build_lock = threading.Lock()
        # ★ 背压缓冲上限 64MB：容纳约 3 分钟 1.6Mbps 转码输出（-b:v 1500k + 96k 音频）
        self._MAX_BUF = 64 * 1024 * 1024
        # ★★ 2026-08-13 头部钉住：每代际流的前 _HEAD_PIN 字节独立副本。
        #   滑动窗口会弹出已消费 chunk，而 Chromium 出错重试/元数据探测会从 offset 0
        #   重新拉流（EBML/init segment）→ 若头部已弹出则 rel<0 返回空 → 二次断连
        #   （PIPELINE_ERROR_READ）。此副本永不弹出，仅多占 2MB/流，内存有界不受影响。
        self._HEAD_PIN = 2 * 1024 * 1024
        self._gen_head = b""
        # 保留流锁兼容（旧管道方案已弃用，但字段保留避免破坏引用）
        self._stream_lock = threading.Lock()

    # ============================================
    # ★ webm 缓存路径：与下载视频同目录 user_config/media/videos/{video_id}/
    # ============================================
    def _get_cache_path(self, video_id):
        """按 video_id 返回完整 webm 缓存路径（与下载视频同目录）"""
        if not video_id:
            return ""
        return os.path.join(MEDIA_VIDEOS_DIR, str(video_id), f"{video_id}.cache.webm")

    # ============================================
    # 播放
    # ============================================
    def play(self, src, video_id=None, start_pos=0, audio_src=None):
        self.stop()
        if not src:
            return False
        self._vid = video_id or None
        self._stop = False
        self._paused = False
        self._last_audio_src = audio_src or None
        # ★ 2026-08 修复：每次播放必须重置时长，防止上次播放残留时长污染本次播放
        #   （此前 _duration 未被清除 → 若上次播放过 3 分钟视频，
        #     本次新视频会错误沿用 3 分钟 → 转码 -t 3:00 只输出 3 分钟、
        #     Chromium controls 显示总时长 3 分钟）
        self._duration = 0.0

        print(f"[FFmpegDecoder] play src={str(src)[:80]} ffmpeg={FFMPEG}")
        if not shutil.which(FFMPEG) and not os.path.exists(FFMPEG):
            print("[FFmpegDecoder] ❌ ffmpeg 不在 PATH，无法解码")
            return False
        if not os.path.exists(src) and not str(src).startswith(("http://", "https://")):
            print(f"[FFmpegDecoder] ❌ 源不存在: {src}")
            return False
        # ★ 目录不是可播放文件（如数据库 localPath 指向目录而非具体文件时）
        #   判定为无效源，让调用方尝试解析真实文件路径
        if os.path.isdir(src):
            print(f"[FFmpegDecoder] ⚠️ src 是目录（非文件），尝试从目录解析真实媒体文件: {src}")
            resolved = self._resolve_dir_to_file(src)
            if not resolved:
                print(f"[FFmpegDecoder] ❌ 目录中未找到媒体文件: {src}")
                return False
            print(f"[FFmpegDecoder] ✓ 已解析到媒体文件: {resolved}")
            src = resolved

        # 探测帧率/时长 + 断点续播
        try:
            is_online = str(src).startswith(("http://", "https://"))
            self._online_mode = is_online
            if is_online:
                # ★★ 2026-08-13 修复：在线 URL 保留数据库时长（供 do_GET 计算 virtual_total
                #   → Chromium 认为文件总大小合理 → 播放时长显示正确）
                #   ★ 2026-08-14 修复：转码时用该时长加 -t（_start_stream 统一处理）→
                #     WebM 头预写 Duration → 原生 controls 时长正确（不再 Infinity）。
                self._fps = 25.0
                self._duration = 0.0
                if video_id:
                    try:
                        vid = self._repo.get_by_id(video_id)
                        if vid and vid.get("duration"):
                            db_dur = float(vid["duration"])
                            if db_dur > 0:
                                self._duration = db_dur
                                print(f"[FFmpegDecoder] 🌐 在线时长(数据库) = {self._duration:.1f}s")
                    except Exception:
                        pass
                # ★ 2026-08-14 修复：在线时长缺失（DB 为 0 / _resolve_online_url 的 yt-dlp
                #   补查失败，常见于智慧教育平台/优酷等非 B 站来源）时，用 ffmpeg 探测
                #   已解析 CDN URL 的真实时长（复用与 _start_stream 一致的 Referer/UA 头）。
                #   → _duration > 0 → _start_stream 加 -t 总时长 → WebM 头预写总时长
                #     （原生条显示「当前/总时长」，不再 Infinity）+ getStreamProgress 可估进度
                #     → 在线视频也能自动向后切续播，与本地一致。
                if not self._duration:
                    try:
                        import re as _re
                        probe_cmd = [FFMPEG, "-hide_banner", "-i", src]
                        try:
                            _ref = self._referer_for(src)
                            if _ref:
                                self._insert_headers(probe_cmd, self._http_headers(_ref), which=1)
                        except Exception:
                            pass
                        r2 = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=25)
                        _m = _re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
                                        (r2.stderr or "") + (r2.stdout or ""))
                        if _m:
                            _fmt = int(_m.group(1)) * 3600 + int(_m.group(2)) * 60 + float(_m.group(3))
                            if _fmt > 0:
                                self._duration = _fmt
                                print(f"[FFmpegDecoder] 🌐 在线时长(ffmpeg探测) = {_fmt:.1f}s")
                                if video_id:
                                    try:
                                        self._repo.update(video_id, {"duration": int(_fmt)})
                                    except Exception:
                                        pass
                    except Exception:
                        pass
                print(f"[FFmpegDecoder] 🌐 在线播放（_duration={self._duration:.0f}s，完整时间线：从0转码并加 -t 总时长）")
            else:
                # 仅本地文件可 ffprobe 探测（在线 URL 由 ffmpeg 自行下载解析）
                info = self._probe(src)
                if info:
                    fr = float(info.get("avg_frame_rate") or info.get("r_frame_rate") or 25)
                    if "/" in str(fr):
                        n, d = str(fr).split("/")
                        fr = float(n) / float(d) if d and float(d) else 25.0
                    self._fps = fr
                # ★★ 首选：数据库已存时长 → 直接填充（下载/搜索时已 ffprobe 存库，零额外探测）
                #   列表显示时长正确 → 数据库 duration 可信，优先使用。
                #   （此前逻辑是「仅当 _duration 为空时才查库」，但 _duration
                #     可能被上次播放残留污染 → 永远走不到数据库分支 → 显示错误时长）
                if video_id:
                    try:
                        vid = self._repo.get_by_id(video_id)
                        if vid and vid.get("duration"):
                            db_dur = float(vid["duration"])
                            if db_dur > 0:
                                self._duration = db_dur
                                print(f"[FFmpegDecoder] ⏱ 使用数据库时长 = {self._duration:.1f}s")
                    except Exception:
                        pass
                # 兜底 1：数据库无时长（或非视频库播放）→ ffprobe 探测 stream.duration
                #   （video stream duration 可能缺失（部分 mp4）→ 用容器 format.duration 覆盖）
                if not self._duration and info:
                    dur_from_stream = float(info.get("duration") or 0)
                    if dur_from_stream > 0:
                        self._duration = dur_from_stream
                # 兜底 2：数据库/ffprobe 均无时长 → 用 ffmpeg -i 解析（不依赖 ffprobe）
                if not self._duration and os.path.isfile(src):
                    try:
                        r2 = subprocess.run(
                            [FFMPEG, "-hide_banner", "-i", src],
                            capture_output=True, text=True, timeout=15)
                        import re as _re
                        m = _re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", (r2.stderr or "") + (r2.stdout or ""))
                        if m:
                            hh, mm, ss = int(m.group(1)), int(m.group(2)), float(m.group(3))
                            fmt_dur = hh * 3600 + mm * 60 + ss
                            if fmt_dur > 0:
                                self._duration = fmt_dur
                                print(f"[FFmpegDecoder] ⏱ ffmpeg -i 解析 duration = {fmt_dur:.1f}s")
                    except Exception:
                        pass
            audio = self._repo.get_playback_position(video_id) if video_id else 0
            if not start_pos and audio:
                start_pos = audio
            # ★ 防超范围定位：数据库/前端 lastPos 可能已超过视频实际时长
            #   （视频被删除尾部/时长变化/记录错误）→ 若 start_pos >= duration，
            #   ffmpeg 用 -ss 定位到超范围位置会输出 0 帧并正常退出（启动即退出）。
            #   ★ 2026-08-13 修复：剩余 < 3 秒直接从头播，避免 ffmpeg 几乎无输出
            #     → 缓冲为空 → HTTP 503 → Chromium Format error
            if self._duration and float(start_pos or 0) >= max(1.0, self._duration - 3):
                print(f"[FFmpegDecoder] ⚠️ start_pos {start_pos}s 接近末尾(duration={self._duration:.0f}s)，从 0 开始")
                start_pos = 0
        except Exception:
            # ★ 探测失败静默降级（不打印报错）：ffprobe 对无效路径/目录会报 WinError 2，
            #   不影响后续 ffmpeg 转码播放；帧率/时长保持默认值
            pass

        self._last_src = src
        self._last_vid = video_id or None
        self._base_pos = float(start_pos or 0)
        self._pos = self._base_pos

        return self._start_stream(src, start_pos, video_id or None)

    def _probe(self, src):
        try:
            # ★ 仅对真实文件执行 ffprobe：目录/无效路径直接返回（避免 WinError 2）
            if not os.path.isfile(src):
                return None
            r = subprocess.run(
                [FFPROBE, "-v", "error", "-print_format", "json",
                 "-show_streams", "-select_streams", "v:0", src],
                capture_output=True, text=True, timeout=15)
            if r.returncode == 0:
                return json.loads(r.stdout).get("streams", [{}])[0]
        except Exception:
            pass
        return None

    # ============================================
    # ★ 完整 .webm 缓存构建（含 Duration → 原生 controls 显示总时长）
    #   首播走实时流时后台快速转完整文件，转完前端自动切换获总时长
    # ============================================
    def _wait_stream_idle(self):
        """等待解码器当前/即将启动的实时流完全结束，期间不占用 GPU 编码器。

        后台 webm 缓存构建在 _start_stream 中途被拉起，此刻实时流 ffmpeg（Popen）
        尚未启动。本方法分两段等待：
          阶段1：等实时流真正启动（_proc 出现 / 代际或缓冲状态变化 / 15s 兜底）
          阶段2：等该流完全结束（ffmpeg 退出 / 被 kill → _proc=None 且缓冲已关）
        之后才开始全量转码 → 与实时 vp9_qsv 流错峰，杜绝两个 QSV 会话争用导致的
        「实时流帧饿死 → 服务器 5s 空等截断 → Chromium PIPELINE_ERROR_READ」。
        """
        with self._buf_lock:
            gen0 = self._buf_gen
            closed0 = self._buf_closed
        # 阶段1：等新流启动（Popen 发生在 ensure_webm_cache 之后 ~0.5s）
        for _ in range(150):  # ≤15s
            with self._buf_lock:
                proc = self._proc
                gen = self._buf_gen
                closed = self._buf_closed
            if proc is not None or gen != gen0 or closed != closed0:
                break
            time.sleep(0.1)
        # 阶段2：等活跃流结束（ffmpeg 退出 / 被 kill / 缓冲关闭，代际切换期间的
        #   kill→re-spawn 空隙 _buf_closed 为 False，不会误判为空闲）
        for _ in range(14400):  # ≤2h，超时兜底放行，避免后台线程永久挂起
            with self._buf_lock:
                proc = self._proc
                closed = self._buf_closed
            if (proc is None or proc.poll() is not None) and closed:
                return
            time.sleep(0.5)

    def _build_webm_cache(self, video_id, src, audio_src=None):
        """快速转码完整 .webm（VP8/Opus，含 Duration+Cues）到 WEBM_CACHE_DIR
        3~6 倍实时速度（-deadline good -cpu-used 8 -row-mt 1）"""
        try:
            if not video_id or not src:
                self._cache_done(video_id)
                return None
            out_path = self._get_cache_path(video_id)
            if not out_path:
                self._cache_done(video_id)
                return None
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            tmp_path = out_path + ".part"
            if os.path.exists(out_path):
                self._cache_done(video_id)
                return out_path  # 已缓存
            # ★★ 2026-08-13 修复：等当前实时流结束后再全量转码，
            #   避免与实时 vp9_qsv 流同时占用 GPU（两个 QSV 会话争用 → 流饿死
            #   → 服务器短 body → Chromium PIPELINE_ERROR_READ）。
            #   等待期间 _cache_building 去重标记保持持有，不会重复起构建线程。
            self._wait_stream_idle()
            venc = self._detect_video_encoder()
            aenc = self._detect_audio_encoder()
            if not venc or not aenc:
                self._cache_done(video_id)
                return None
            cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                   "-i", src]
            if audio_src and os.path.exists(audio_src):
                cmd += ["-i", audio_src]
            if str(src).startswith(("http://", "https://")):
                try:
                    referer = self._referer_for(src)
                    if referer:
                        self._insert_headers(cmd, self._http_headers(referer), which=1)
                except Exception:
                    pass
            # ★★ 2026-08-13 修复：按编码器分派参数（此前无论检测到什么都套 libvpx
            #   专属的 -crf/-deadline/-cpu-used/-row-mt，vp9_qsv 会拒绝/行为异常）。
            #   与实时流 _build_video_out_args 同一套参数体系，仅 GOP 加大到 100（整文件）。
            if venc == "vp9_qsv":
                out_args = ["-c:v", "vp9_qsv", "-b:v", "1500k", "-rc", "vbr",
                            "-look_ahead", "0", "-preset", "medium"]
            elif venc == "vp9_nvenc":
                out_args = ["-c:v", "vp9_nvenc", "-b:v", "1500k", "-rc", "vbr",
                            "-preset", "p4"]
            elif venc == "vp9_amf":
                out_args = ["-c:v", "vp9_amf", "-b:v", "1500k", "-quality", "speed"]
            else:
                # CPU libvpx（VP8/VP9）：纯 CRF 高质量
                out_args = ["-c:v", venc, "-b:v", "0", "-crf", "38",
                            "-deadline", "good", "-cpu-used", "8", "-row-mt", "1",
                            "-threads", "0"]
            out_args += ["-g", "100", "-c:a", aenc, "-b:a", "96k", "-vbr", "on"]
            if audio_src and os.path.exists(audio_src):
                out_args = ["-map", "0:v:0", "-map", "1:a:0"] + out_args
            cmd += out_args + ["-f", "webm", tmp_path]
            print(f"[FFmpegDecoder] ⚡ 后台构建完整 webm 缓存: {os.path.basename(out_path)}")
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if r.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                os.replace(tmp_path, out_path)
                print(f"[FFmpegDecoder] ✅ webm 缓存就绪: {out_path}")
                self._cache_done(video_id)
                return out_path
            else:
                print(f"[FFmpegDecoder] ❌ webm 缓存构建失败: {r.stderr[-300:]}")
                if os.path.exists(tmp_path):
                    try: os.remove(tmp_path)
                    except Exception: pass
                self._cache_done(video_id)
                return None
        except Exception as e:
            print(f"[FFmpegDecoder] ⚠️ webm 缓存构建异常: {e}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            self._cache_done(video_id)
            return None

    def _cache_done(self, video_id):
        """后台缓存构建结束（成功/失败）→ 释放去重标记"""
        if not video_id:
            return
        try:
            with self._cache_build_lock:
                self._cache_building.discard(video_id)
        except Exception:
            pass

    def ensure_webm_cache(self, video_id, src, audio_src=None):
        """确保有视频的完整 webm 缓存（后台线程构建，不阻塞播放）
        返回是否已有缓存文件（未构建/正在构建返回 False）
        ★ 2026-08-13 修复：加 _cache_building 去重，避免 seek/重播重复起多个构建线程"""
        try:
            out_path = self._get_cache_path(video_id)
            if not out_path:
                return False
            if os.path.exists(out_path):
                return True
            with self._cache_build_lock:
                if video_id in self._cache_building:
                    return False  # 已在构建，跳过
                self._cache_building.add(video_id)
            # 后台构建（daemon 线程）
            threading.Thread(
                target=self._build_webm_cache,
                args=(video_id, src, audio_src),
                daemon=True
            ).start()
            return False
        except Exception:
            return False

    # ============================================
    # ★ 编码兼容性探测：QWebEngine 原生支持的源直接播，不支持的才转码
    # ============================================
    def _probe_codec_compat(self, src):
        """探测源文件的视频/音频编码是否 QWebEngine 原生支持。
        返回 (native_ok: bool, 原因: str)
        """
        try:
            # ★ 必须是文件（目录/无效路径直接跳过：ffprobe 无法处理目录）
            if not os.path.isfile(src):
                return False, f"非有效文件路径: {str(src)[:80]}"
            r = subprocess.run(
                [FFPROBE, "-v", "error", "-print_format", "json",
                 "-show_streams", src],
                capture_output=True, text=True, timeout=15)
            if r.returncode != 0:
                return False, f"ffprobe 失败: {r.stderr[:120]}"
            streams = json.loads(r.stdout).get("streams", [])
            vcodec = None
            acodec = None
            for st in streams:
                if st.get("codec_type") == "video" and not vcodec:
                    vcodec = (st.get("codec_name") or "").lower()
                elif st.get("codec_type") == "audio" and not acodec:
                    acodec = (st.get("codec_name") or "").lower()
            # ★ 视频编码判断
            if vcodec:
                if vcodec in _QWE_NATIVE_VIDEO:
                    print(f"[FFmpegDecoder] ✓ 视频编码 {vcodec} 是 QWebEngine 原生支持")
                else:
                    return False, f"视频编码 {vcodec} 非 QWebEngine 原生支持"
            # ★ 音频编码判断（无音频则不限制）
            if acodec:
                if acodec in _QWE_NATIVE_AUDIO:
                    print(f"[FFmpegDecoder] ✓ 音频编码 {acodec} 是 QWebEngine 原生支持")
                else:
                    return False, f"音频编码 {acodec} 非 QWebEngine 原生支持"
            return True, "原生支持，直接播放"
        except Exception as e:
            return False, f"探测异常: {e}"

    @staticmethod
    def _is_webm_container(src):
        """本地文件扩展名 .webm/.ogg → WebM/OGG 容器天然兼容"""
        try:
            path = str(src).split("?")[0]
            ext = os.path.splitext(path)[1].lower()
            return ext in _QWE_NATIVE_CONTAINERS
        except Exception:
            return False

    @staticmethod
    def _resolve_dir_to_file(src_dir):
        """当 src 是目录时，在目录中查找真实的媒体文件（.mp4/.mkv/.webm/.mov）
        返回找到的文件路径；无则返回 None。优先取最新修改的文件。
        """
        try:
            if not os.path.isdir(src_dir):
                return None
            candidates = []
            for f in os.listdir(src_dir):
                low = f.lower()
                if (low.endswith((".mp4", ".mkv", ".webm", ".mov", ".flv", ".avi", ".m4v"))
                        and not low.endswith(".bak")):
                    fpath = os.path.join(src_dir, f)
                    candidates.append((fpath, os.path.getmtime(fpath)))
            if not candidates:
                return None
            # 最新修改的媒体文件优先
            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[0][0]
        except Exception:
            return None

    # ============================================
    # ★ 在线 URL 的 Referer / UA 头（B站 CDN 校验主站域名，统一构造，避免 6 处重复）
    # ============================================

    @staticmethod
    def _referer_for(url):
        """根据 URL 推导 Referer（B站/优酷/爱奇艺防盗链校验主站域名，其他站用自身域名）"""
        try:
            host = urlparse(str(url)).netloc
        except Exception:
            return None
        if not host:
            return None
        low = host.lower()
        if ("bilivideo.com" in low or "bilibili.com" in low
                or "bilivideo.cn" in low):
            return "https://www.bilibili.com/"
        if "youku.com" in low:
            return "https://www.youku.com/"
        if "iqiyi.com" in low:
            return "https://www.iqiyi.com/"
        return f"https://{host}/"

    @staticmethod
    def _http_headers(referer):
        """构建 ffmpeg -headers 的 Referer + UA 字符串"""
        return (f"Referer: {referer}\r\n"
                "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36\r\n")

    @staticmethod
    def _insert_headers(cmd, headers, which=1):
        """在 cmd 第 which 个 '-i' 之前插入 ['-headers', headers]（which 从 1 开始）"""
        idx = -1
        for _ in range(which):
            idx = cmd.index("-i", idx + 1)
        cmd[idx:idx] = ["-headers", headers]

    # ============================================
    # ★ 转码 HTTP 流：ffmpeg 转 VP8/Opus → 127.0.0.1 流 → 原生 <video>
    #   QWebEngine 只支持 VP8/VP9/Opus/FLAC（见支持探测），不支持 H.264/AAC/HEVC，
    #   因此必须转码为 WebM（VP8+Opus），否则 Chromium demuxer 永远 no supported streams
    # ============================================
    def _detect_video_encoder(self):
        """检测可用的 WebM 视频编码器
        ★ 2026-08-13 优先 GPU 硬件 VP9 编码器（速度 10-20 倍，避免转码追不上播放）：
          Intel QSV (vp9_qsv) → NVIDIA (vp9_nvenc) → 回退 CPU libvpx (VP8)
        Returns: 编码器名称字符串；无可用返回 None
        """
        if "video" in _ENCODER_CACHE:
            return _ENCODER_CACHE["video"]
        found = None
        try:
            r = subprocess.run([FFMPEG, "-hide_banner", "-encoders"],
                               capture_output=True, text=True, timeout=10)
            out = (r.stdout or "") + "\n" + (r.stderr or "")
            # GPU 硬件 VP9 编码器（QWebEngine 支持 VP9 WebM；GPU 速度远快于 CPU）
            hw_candidates = ["vp9_qsv", "vp9_nvenc"]
            for c in hw_candidates:
                for line in out.splitlines():
                    if c in line and line.strip().startswith("V"):
                        print(f"[FFmpegDecoder] 🎬 使用 GPU 硬件编码器: {c}（转码速度 10-20x）")
                        found = c
                        break
                if found:
                    break
            # 回退 CPU libvpx（VP8 快于 VP9）
            if not found:
                candidates = ["libvpx", "libvpx-vp9", "libvpx-vp8"]
                for c in candidates:
                    for line in out.splitlines():
                        # -encoders 输出格式: " V....D libvpx  ..."（V=视频编码器）
                        if c in line and line.strip().startswith("V"):
                            print(f"[FFmpegDecoder] 🎬 使用 CPU 编码器（无 GPU VP9）: {c}")
                            found = c
                            break
                    if found:
                        break
        except Exception as e:
            print(f"[FFmpegDecoder] 视频编码器检测失败: {e}")
        _ENCODER_CACHE["video"] = found
        return found

    def _detect_audio_encoder(self):
        """检测可用的 WebM 音频编码器（优先 libopus，回退 libvorbis）
        Returns: 编码器名称字符串；无可用返回 None
        """
        if "audio" in _ENCODER_CACHE:
            return _ENCODER_CACHE["audio"]
        found = None
        try:
            r = subprocess.run([FFMPEG, "-hide_banner", "-encoders"],
                               capture_output=True, text=True, timeout=10)
            out = (r.stdout or "") + "\n" + (r.stderr or "")
            candidates = ["libopus", "libvorbis"]
            for c in candidates:
                for line in out.splitlines():
                    # -encoders 输出格式: " A....D libopus  ..."（A=音频编码器）
                    if c in line and line.strip().startswith("A"):
                        print(f"[FFmpegDecoder] 🔉 使用音频编码器: {c}")
                        found = c
                        break
                if found:
                    break
        except Exception as e:
            print(f"[FFmpegDecoder] 音频编码器检测失败: {e}")
        _ENCODER_CACHE["audio"] = found
        return found

    @staticmethod
    def _build_video_out_args(venc, aenc):
        """★ 2026-08-13 根据所选视频编码器构建转码输出参数
        GPU 编码器 (vp9_qsv/vp9_nvenc) 与 CPU (libvpx) 参数完全不同：
          GPU QSV:  -global_quality N（无需 -crf/-deadline）
          GPU NVENC: -cq N -rc vbr -preset p4
          CPU libvpx: -crf N -deadline realtime -cpu-used N
        """
        args = []
        if venc == "vp9_qsv":
            # ★ 2026-08-13 修复：-global_quality 是【全局质量】AVOption，会污染 libopus
            #   → libopus 误入"质量模式"→ "Quality-based encoding not supported"
            #   → 改用纯比特率 -b:v 1500k（GPU 仍 10-20x）
            args += ["-c:v", "vp9_qsv", "-b:v", "1500k", "-rc", "vbr",
                    "-look_ahead", "0", "-preset", "medium"]
        elif venc == "vp9_nvenc":
            # 同样改用纯比特率（-cq 也是质量语义）
            args += ["-c:v", "vp9_nvenc", "-b:v", "1500k", "-rc", "vbr",
                    "-preset", "p4"]
        elif venc == "vp9_amf":
            args += ["-c:v", "vp9_amf", "-b:v", "1500k", "-quality", "speed"]
        else:
            # CPU libvpx（VP8/VP9）
            args += ["-c:v", venc, "-b:v", "0", "-crf", "30",
                    "-deadline", "realtime", "-cpu-used", "8"]
        # ★ 2026-08-13 修复：-g（GOP）/ -error-resilient 是【视频】参数，
        #   必须放在 -c:a 之前！此前放在 -c:a libopus 之后被误应用到音频流
        #   → libopus 不支持这些视频选项 → "Error while opening encoder" 重演
        args += ["-g", "25", "-error-resilient", "1"]
        # 音频统一 libopus（仅音频选项，-b:a + -vbr on 明确 bitrate/VBR）
        args += ["-c:a", aenc, "-b:a", "96k", "-vbr", "on"]
        return args

    def _start_stream(self, src, start_pos, video_id):
        """启动 ffmpeg 实时转码 + 本地 HTTP 流，返回 URL（<video> 直接播放，渲染/控件全原生）

        ★ 智能策略：
          1) 源文件若是 QWebEngine 原生支持的 WebM/VP8/VP9/Opus → 直接透传（零转码、零延迟）
          2) 否则 ffmpeg 实时转码为 VP8/Opus WebM
        """
        # ★★ 智能探测：QWebEngine 原生支持则直接流式播放（不转码）
        is_local = os.path.exists(src) and not str(src).startswith(("http://", "https://"))
        native_path = False
        if is_local and self._is_webm_container(src):
            # 扩展名 .webm → 直接探测编码
            native_ok, reason = self._probe_codec_compat(src)
            if native_ok:
                native_path = True
                print(f"[FFmpegDecoder] ⚡ {reason}，直接播放（零转码）")
        elif is_local:
            # 非 .webm 扩展名 → 探测视频流编码（如 .mkv 内封 VP9+Opus 也可以）
            native_ok, reason = self._probe_codec_compat(src)
            if native_ok:
                native_path = True
                print(f"[FFmpegDecoder] ⚡ {reason}，直接播放（零转码）")

        if native_path:
            return self._start_native_stream(src, start_pos, video_id)

        # ★★ 优化 1（2026-08-13）：已有完整 webm 缓存 → 直接原生播放（零转码秒开）
        #   首播时后台会构建 {video_id}.cache.webm，二次播放命中缓存直接读文件
        #   （缓存含 Duration+Cues → Chromium 原生 controls 秒显总时长）
        #   ★ 2026-08-13 修复：此前 ensure_webm_cache 全仓库无调用 → 缓存永远不构建。
        #   现在首播本地文件即触发后台构建；命中缓存直接原生播放（零转码）。
        if video_id:
            cache_path = self._get_cache_path(video_id)
            if cache_path and os.path.exists(cache_path):
                print(f"[FFmpegDecoder] ⚡ 命中 webm 缓存，直接播放（零转码）: {os.path.basename(cache_path)}")
                return self._start_native_stream(cache_path, start_pos, video_id)
            # 本地文件源 → 后台预热完整 webm 缓存（在线 CDN 流含时效签名，不缓存）
            if src and not str(src).startswith(("http://", "https://")):
                try:
                    self.ensure_webm_cache(video_id, src, getattr(self, "_last_audio_src", None))
                except Exception:
                    pass

        # 起流服务器（随机端口）
        try:
            server = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
            port = server.server_address[1]
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self._server = server
            self._port = port
        except Exception as e:
            print(f"[FFmpegDecoder] ❌ HTTP 流服务启动失败: {e}")
            return ""

        # 检测可用 VP8/Opus 编码器（QWebEngine 支持 VP8/VP9/Opus，不支持 H.264/AAC）
        venc = self._detect_video_encoder()
        if not venc:
            print("[FFmpegDecoder] ❌ 未找到可用的 WebM 视频编码器（libvpx）")
            self._cleanup_server()
            return ""
        # ★ 优化 2：记录当前编码器 → do_GET 动态估算 virtual_total（GPU 1.7Mbps / CPU 0.8Mbps）
        self._current_venc = venc
        aenc = self._detect_audio_encoder()
        if not aenc:
            print("[FFmpegDecoder] ❌ 未找到可用的 WebM 音频编码器（libopus）")
            self._cleanup_server()
            return ""

        # ★★ 2026-08-14 完整时间线模式（内存版）：【所有转码源】统一处理。
        #   原生控制条要显示「真实总时长 + 前后拖拽 + 续播」，流必须是完整时间线 0..TOTAL
        #   且全段可寻址（缓冲永不弹出，见 _read_chunks/_start_buf_writer）。
        #   故转码源强制从 0 转码、-t 用总时长（WebM 头 Duration=总时长 → 原生条显示真实总时长）。
        #   ★ 2026-08-14 修复：此前本地转码用 -ss N -t 剩余 → WebM 头 Duration=剩余时长
        #     → 原生条显示「剩余时长」而非「总时长」（用户反馈"第一条没实现"）。
        #   续播位置改由前端在 URL ?src=native&start=<秒> 上原生 seek（poll-then-seek 等转码追上）。
        #   代价：续播/拖到未转码处需等转码追上（GPU 快、CPU 慢）——用户已确认接受。
        resume_sec = float(start_pos or 0)   # 真实续播秒数 → 进 URL（src=native 路径 seek）
        start_pos = 0.0                       # ffmpeg 从 0 转码（完整时间线）
        self._base_pos = 0.0                  # 数学用全时长（remain = duration - 0）
        self._pos = 0.0

        # ffmpeg 实时转 VP8+Opus WebM（QWebEngine 可解码；WebM 天然流式友好）
        self._start_pos = float(start_pos or 0)
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin",
               "-ss", str(self._start_pos),
               "-i", src]
        # ★ 分离音频（独立 m3a/m4a/mp3 文件 或 在线 DASH 音轨 URL）：
        #   追加第二输入 -i audio_src，最终用 -map 0:v:0 -map 1:a:0 将视频 + 独立音轨合并转码
        #   ★ 2026-08-13 修复：在线 DASH 流（B站 etc）视频和音频是独立 URL，必须合并
        audio_src = getattr(self, "_last_audio_src", None)
        audio_is_online = bool(audio_src and str(audio_src).startswith(("http://", "https://")))
        if audio_src and (os.path.exists(audio_src) or audio_is_online):
            print(f"[FFmpegDecoder] 🔊 使用分离音频: {audio_src[:80]}")
            cmd += ["-ss", str(self._start_pos), "-i", audio_src]
            # 在线音频 URL 也携带 Referer/UA 头
            if audio_is_online:
                try:
                    audio_referer = self._referer_for(audio_src)
                    if audio_referer:
                        self._insert_headers(cmd, self._http_headers(audio_referer), which=2)
                except Exception:
                    pass
            # 标记后续需要 -map（双输入合并）
            self._has_separate_audio = True
        else:
            self._has_separate_audio = False
        # ★ 在线 URL：携带 Referer/UA 头（防 B站等 CDN 403）
        #   ★★ 2026-08-13 修复：B 站 CDN（upos-sz-*.bilivideo.com）校验的 Referer
        #     必须是 https://www.bilibili.com，而不是 CDN 域名本身！
        #     （此前用 CDN 域名做 Referer → 403 Forbidden → ffmpeg 启动即退出
        #       → 缓冲为空 → Chromium Format error）
        #   注意：-headers 必须插在 -i <src> 之前，且不能破坏 -loglevel error
        if str(src).startswith(("http://", "https://")):
            referer = self._referer_for(src)
            if referer:
                # ★ 在 -i 前插入（确保插在 -loglevel error 之后）
                try:
                    self._insert_headers(cmd, self._http_headers(referer), which=1)
                except ValueError:
                    pass
            else:
                print(f"[FFmpegDecoder] ⚠️ 无法确定在线 URL 的 Referer（{str(src)[:60]}）")
        # ★ VP8/Opus WebM：-deadline realtime 实时编码、-cpu-used 5 加速；
        #   -g 25 每 1 秒关键帧；WebM 无需 fragment，流式天然可解析
        #   ★★ 2026-08 实测：加 -t <剩余时长> 让 muxer 在起始头预写 Duration
        #      → Chromium 第一秒解析 → 原生 controls 显示「当前/总时长」（零等待、无缓存文件）
        #   ★ 2026-08 修复：必须用剩余时长（duration - 起始位置）而非总时长！
        #     否则 WebM 头预写 Duration=总时长，但实际输出只有剩余时长 →
        #     Chromium 认为文件不完整 → 「播着播着就停了」
        out_args = []
        # ★ 2026-08-14 修复：在线模式也加 -t（用数据库时长）→ WebM 头预写 Duration
        #   → Chromium 原生 controls 正确显示总时长。
        #   此前在线无 -t → WebM 无 Duration → player.duration=Infinity → 「时长显示不对」。
        #   原 2026-08-13 担忧「DB 时长与实际 CDN 不一致会提前停止」：搜索/下载入库时长来自
        #   ffprobe 元数据、通常准确（B站等），且本地模式早已用同款 -t 逻辑 → 统一处理。
        #   仍以 remain_dur > 0 守卫：DB 无时长时保持无 -t、不截断（时长退回 Infinity）。
        remain_dur = max(0, float(getattr(self, "_duration", 0) or 0) - float(getattr(self, "_base_pos", 0) or 0))
        if remain_dur > 0:
            out_args += ["-t", str(remain_dur)]
        out_args += self._build_video_out_args(venc, aenc)
        # ★ 有分离音频（双输入）时用 -map：视频取输入0，音频取输入1
        if getattr(self, "_has_separate_audio", False):
            out_args = ["-map", "0:v:0", "-map", "1:a:0"] + out_args
        cmd += out_args + ["-f", "webm", "pipe:1"]
        print(f"[FFmpegDecoder] 转码: {' '.join(cmd)}")
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL)
        except Exception as e:
            print(f"[FFmpegDecoder] ❌ 转码启动失败: {e}")
            self._cleanup_server()
            return ""

        def _drain_err():
            collected = b""
            try:
                while self._proc and self._proc.poll() is None:
                    chunk = self._proc.stderr.read(4096)
                    if not chunk:
                        break
                    collected += chunk
                if collected:
                    print(f"[FFmpegDecoder] ❌ 转码stderr:\n"
                          f"{collected.decode('utf-8', errors='replace')[:600]}")
            except Exception:
                pass
        threading.Thread(target=_drain_err, daemon=True).start()

        # ★ 后台读线程：ffmpeg stdout → deque 环形缓冲（无磁盘文件，超限丢最老）
        self._reset_buffer()
        # ★ 2026-08-14 完整时间线模式：_reset_buffer 已复位 _full_timeline，这里重新置位
        #   （转码源一律完整时间线 → 本地转码同样显示总时长），并计算全量背压上限
        #   （数据永不弹出 → 上限必须放大到视频转码后大小，否则写满 64MB 后 ffmpeg 阻塞）。
        self._full_timeline = True
        self._full_timeline_cap = max(
            int(float(getattr(self, "_duration", 0) or 0) * 1_700_000 / 8 * 1.5),
            256 * 1024 * 1024)

        self._start_buf_writer()

        # ★ 健康检查：循环等待缓冲有数据（GPU QSV 首次初始化需几秒）
        #   ★ 2026-08-13 修复：原 1.8 秒后立即判失败太激进
        #     → GPU vp9_qsv 首次加载 QSV 会话慢 → 缓冲为空 → 误判失败 → return ""
        #     → 改为最多等 10 秒，期间 ffmpeg 活着且有数据才算成功
        for _wait in range(100):  # 100 x 0.1s = 10s
            time.sleep(0.1)
            with self._buf_lock:
                if self._buf_size > 0 or self._buf_closed:
                    break
        if self._proc.poll() is not None and float(start_pos or 0) > 0:
            # ★ 最后防线：-ss 定位越界/source 异常导致 0 帧退出时，自动回退从头转码
            #   （正常情况 play() 已用 format.duration clamp，此处仅兜底）
            print(f"[FFmpegDecoder] ⚠️ -ss {start_pos}s 转码立即退出，回退从 0s 重启转码")
            self._kill()
            self._reset_buffer()
            # ★ 2026-08 修复：构建回退命令前【先】重置 _base_pos = 0！
            #   否则下方 cmd0 的 -t 会读取旧 _base_pos（如 245.0）
            #   → 计算出 remain_dur0 = duration - 245 = 0.086 秒 → ffmpeg 立即退出
            self._base_pos = 0.0
            self._pos = 0.0
            # ★ 重新以 -ss 0 启动（复用同 cmd 但 start_pos=0）
            #   注意：_start_buf_writer 必须在【新进程 Popen 之后】调用，
            #   否则写入线程读到已 kill 的旧 proc（None）立即退出 → 新进程无缓冲写入
            cmd0 = [FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin",
                    "-ss", "0", "-i", src]
            audio_src0 = getattr(self, "_last_audio_src", None)
            audio0_is_online = bool(audio_src0 and str(audio_src0).startswith(("http://", "https://")))
            if audio_src0 and (os.path.exists(audio_src0) or audio0_is_online):
                cmd0 += ["-ss", "0", "-i", audio_src0]
                if audio0_is_online:
                    try:
                        audio_ref0 = self._referer_for(audio_src0)
                        if audio_ref0:
                            self._insert_headers(cmd0, self._http_headers(audio_ref0), which=2)
                    except Exception:
                        pass
                self._has_separate_audio = True
            else:
                self._has_separate_audio = False
            if str(src).startswith(("http://", "https://")):
                try:
                    referer0 = self._referer_for(src)
                    if referer0:
                        self._insert_headers(cmd0, self._http_headers(referer0), which=1)
                except Exception:
                    pass
            out_args0 = []
            # ★ 2026-08-14 完整时间线模式回退仍加 -t 总时长（保持 WebM 头真实总时长）
            if (not getattr(self, "_online_mode", False)) or getattr(self, "_full_timeline", False):
                # ★ 2026-08 修复：回退 0s 时剩余时长 = 总时长（_base_pos 已重置为 0）
                remain_dur0 = max(0, float(getattr(self, "_duration", 0) or 0) - float(getattr(self, "_base_pos", 0) or 0))
                if remain_dur0 > 0:
                    out_args0 += ["-t", str(remain_dur0)]
            out_args0 += self._build_video_out_args(venc, aenc)
            if getattr(self, "_has_separate_audio", False):
                out_args0 = ["-map", "0:v:0", "-map", "1:a:0"] + out_args0
            cmd0 += out_args0 + ["-f", "webm", "pipe:1"]
            try:
                self._proc = subprocess.Popen(
                    cmd0, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    stdin=subprocess.DEVNULL)
            except Exception as e:
                print(f"[FFmpegDecoder] ❌ 回退重启失败: {e}")
                self._cleanup_server()
                return ""
            # ★★ 关键：新进程启动后才启动缓冲写入线程（否则无数据）
            self._start_buf_writer()
            def _drain_err0():
                collected = b""
                try:
                    while self._proc and self._proc.poll() is None:
                        chunk = self._proc.stderr.read(4096)
                        if not chunk:
                            break
                        collected += chunk
                    if collected:
                        print(f"[FFmpegDecoder] ❌ 回退stderr:\n"
                              f"{collected.decode('utf-8', errors='replace')[:400]}")
                except Exception:
                    pass
            threading.Thread(target=_drain_err0, daemon=True).start()
            time.sleep(1.8)
            if self._proc.poll() is not None:
                print("[FFmpegDecoder] ❌ 回退后 ffmpeg 仍退出")
                self._cleanup_server()
                return ""
            self._base_pos = 0.0
            self._pos = 0.0
            # ★ 2026-08 修复：回退从 0s 播放后，必须同步重置数据库 last_position。
            #   否则前端 _absolutePosition() 仍按旧 lastPosition + currentTime 计算
            #   → 每次播放位置不断累加 → 最后超过视频时长 → -ss 定位失败 → 再次回退……
            #   （无限恶性循环）
            if self._vid:
                try:
                    self._repo.update_last_position(self._vid, 0)
                    print("[FFmpegDecoder] ⏱ 已重置数据库 last_position = 0（回退从 0 播放）")
                except Exception:
                    pass
        if self._proc.poll() is not None and float(start_pos or 0) <= 0:
            print("[FFmpegDecoder] ❌ ffmpeg 启动即退出（请检查上方 stderr 日志）")
            self._cleanup_server()
            return ""
        with self._buf_lock:
            if self._buf_size <= 0:
                # ★ 2026-08-13 修复：等待期间 ffmpeg 仍活着但缓冲为空
                #   → 再多等 5 秒（GPU 转码输出前有预热期）
                print("[FFmpegDecoder] ⚠️ 缓冲仍为空，再等 5 秒（GPU 预热）...")
                for _w2 in range(50):
                    time.sleep(0.1)
                    with self._buf_lock:
                        if self._buf_size > 0 or self._buf_closed:
                            break
                with self._buf_lock:
                    if self._buf_size <= 0:
                        print("[FFmpegDecoder] ❌ 缓冲无数据（ffmpeg 可能输出异常）")
                        self._cleanup_server()
                        return ""

        self._vid = video_id
        # ★ 2026-08 修复：URL 携带实际起始位置 start=<秒>
        #   使用 self._base_pos（回退 0s 后已重置为 0）而非 start_pos 参数，
        #   确保 URL 反映后端实际播放起点 → 前端正确计算绝对播放位置
        # ★ 2026-08-14 完整时间线模式：转码从 0 开始（_base_pos=0），完整时间线可整段寻址，
        #   URL 统一 src=native → 前端走 isNative 路径（绝对时间线 + _deferSeek 续播），
        #   start=<resume_sec> 即真实续播秒数。
        url = f"http://127.0.0.1:{port}/stream?src=native&start={int(float(resume_sec or 0))}&v={video_id or ''}"
        print(f"[FFmpegDecoder] ▶ 原生<video> 流(转码): {url}")
        return url

    # ============================================
    # ★ 原生直通流：文件本身是 QWebEngine 原生支持的 WebM/VP8/VP9/Opus
    # ============================================
    def _start_native_stream(self, src, start_pos, video_id):
        """源文件已确认 QWebEngine 可解码 → 直接文件流，零转码零延迟"""
        # 起流服务器
        try:
            server = ThreadingHTTPServer(("127.0.0.1", 0), self._make_handler())
            port = server.server_address[1]
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self._server = server
            self._port = port
        except Exception as e:
            print(f"[FFmpegDecoder] ❌ HTTP 流服务启动失败: {e}")
            return ""

        # ★ 2026-08-13 修复：先复位缓冲，再置 native。
        #   play() 每次先 stop() → _buf_closed=True 残留、_buf_gen 不自增、_gen_head 不清；
        #   若不复位，健康检查 `not _buf_closed` 因残留 True 跳过等待 → 读文件慢时误判
        #   "原生流无数据"，且旧 reader 的 finally（gen 相同）会污染新流缓冲。
        #   _reset_buffer() 会把 _native_mode/_src_fsize 清 0 → 必须在复位【之后】再置位。
        self._reset_buffer()
        self._native_mode = True

        # 不启动 ffmpeg 转码进程 → 用 Python 直接读文件 → 环形缓冲
        try:
            fsize = os.path.getsize(src)
            # ★ 2026-08-13 修复：原生直通/缓存【不再按字节跳过 start_pos】。
            #   此前 skip_bytes = start*1.5Mbps/8 直接 seek 到 webm 中部 → 输出流没有
            #   EBML/Info/Tracks 头 → Chromium 无法解析 → SRC_NOT_SUPPORTED
            #   （前端 3s 自动重试 → 「视频一直播放」）。
            #   WebM 的寻址靠 Cues 元素，必须整文件提供、由 Chromium 原生精确 seek；
            #   续播位置改由前端在 currentTime 上设置（URL start=<秒> 已携带）。
            skip_bytes = 0
            self._start_pos = float(start_pos or 0)
            self._src_fsize = fsize

            gen = self._buf_gen  # ★ 捕获代际：seek/回退后旧读线程不再能写 _buf_closed

            def _file_reader():
                """直接读文件 → 背压缓冲（缓冲满时暂停，不丢弃数据）
                ★ 2026-08-13 修复：原生文件流的缓冲上限改为【整个文件大小】而非 64MB。
                  前端续播 seek 会直接请求 seek 目标处的字节（如 231s ≈ 文件 95% 处），
                  若 reader 停在 64MB 无法追上 → Chromium 请求超出缓冲 → 416 → seek 失败。
                  本地文件读取快、数据总量有限（webm 缓存一般几十~几百 MB），整文件缓冲
                  可保证任意位置 seek 都能即时命中；滑动窗口仍在消费后弹出，内存不失控。"""
                try:
                    with open(src, "rb") as f:
                        f.seek(skip_bytes)
                        while not self._stop:
                            # ★ 背压：缓冲满时暂停读取（锁外 sleep）
                            with self._buf_lock:
                                buf_full = self._buf_size >= fsize
                            if buf_full:
                                time.sleep(0.05)
                                continue
                            data = f.read(65536)
                            if not data:
                                break
                            with self._buf_lock:
                                if gen != self._buf_gen:
                                    break  # 已被 reset/seek → 退出
                                # ★ 头部钉住：镜像流前 _HEAD_PIN 字节（永不弹出）
                                if len(self._gen_head) < self._HEAD_PIN:
                                    self._gen_head += data[:self._HEAD_PIN - len(self._gen_head)]
                                self._chunks.append(data)
                                self._chunk_sizes.append(len(data))
                                self._buf_size += len(data)
                except Exception as e:
                    print(f"[FFmpegDecoder] ⚠️ 原生流文件读取异常: {e}")
                finally:
                    with self._buf_lock:
                        # ★ 只有当前代际的读线程才能关闭缓冲
                        if gen == self._buf_gen:
                            self._buf_closed = True

            threading.Thread(target=_file_reader, daemon=True).start()
        except Exception as e:
            print(f"[FFmpegDecoder] ❌ 原生流启动失败: {e}")
            self._cleanup_server()
            return ""

        # 健康检查
        # ★ 2026-08-13 修复：原代码 `with self._buf_lock:` 内再嵌一个 `with self._buf_lock:`
        #   （非重入锁）→ 同一线程二次 acquire 永远阻塞 → _start_native_stream 每次必死锁
        #   （缓存命中路径首次被走到即卡死，视频永远无法播放）。改为单次加锁 + 锁外失败处理。
        time.sleep(0.3)
        with self._buf_lock:
            if self._buf_size <= 0 and not self._buf_closed:
                time.sleep(0.3)
            empty = self._buf_size <= 0
        if empty:
            print("[FFmpegDecoder] ❌ 原生流无数据")
            self._cleanup_server()
            return ""

        self._vid = video_id
        # ★ 2026-08 修复：URL 携带实际起始位置 start=<秒>（与转码流一致）
        #   使用 self._base_pos 确保反映后端实际播放起点 → 避免位置累加
        url = f"http://127.0.0.1:{port}/stream?src=native&start={int(float(self._base_pos or 0))}&v={video_id or ''}"
        print(f"[FFmpegDecoder] ▶ 原生<video> 流(直通): {url}")
        return url

    def _make_handler(self):
        """环形缓冲 HTTP 服务：从 deque chunks 提供数据（支持 Range/Content-Length）
        Chromium 按 file 方式解析，彻底解决 no supported streams；环形防内存暴涨"""
        dec = self

        class H(BaseHTTPRequestHandler):
            def _read_chunks(self, pos, length):
                """从 deque 环形缓冲按绝对偏移 pos 读取 length 字节（锁外调用）"""
                out = bytearray()
                with dec._buf_lock:
                    rel = pos - dec._buf_start
                    if rel < 0:
                        # ★★ 2026-08-13 头部钉住：请求落在滑动窗口已弹出的范围 → 若在
                        #   _gen_head 副本内（流前 _HEAD_PIN 字节，EBML/init segment）则恢复。
                        #   Chromium 出错重试/元数据探测从 offset 0 重新拉流时命中此路径，
                        #   否则返回空 → 二次断连 → PIPELINE_ERROR_READ。
                        head = getattr(dec, "_gen_head", b"") or b""
                        if pos < len(head):
                            take = min(length, len(head) - pos)
                            return bytes(head[pos:pos + take])
                        return b""  # 头部区之外已丢弃，无法恢复
                    # 跳到对应 chunk
                    idx = 0
                    remaining = rel
                    while idx < len(dec._chunks):
                        chunk_sz = dec._chunk_sizes[idx]
                        if remaining < chunk_sz:
                            break
                        remaining -= chunk_sz
                        idx += 1
                    if idx >= len(dec._chunks):
                        return b""
                    # 从该 chunk 的 remaining 偏移开始读
                    chunk = dec._chunks[idx]
                    start_in = remaining
                    take = min(length, chunk_sz - start_in)
                    out += chunk[start_in:start_in + take]
                    # 跨 chunk 继续读
                    idx += 1
                    while len(out) < length and idx < len(dec._chunks):
                        need = length - len(out)
                        out += dec._chunks[idx][:need]
                        idx += 1
                    # ★★ 2026-08-13 滑动窗口：本次读取已覆盖到 end_read，
                    #   把被完整消费的 chunk 弹出缓冲、推进 _buf_start。
                    #   （此前缓冲只增不减 → 转码超过 64MB 后写线程永久阻塞 → 播放冻结；
                    #     长视频/原生大文件必现。裁剪后内存有界、可无限播放。）
                    #   ★ 2026-08-13 修复：原生文件流【不弹出】——整文件一次性缓冲、
                    #     数据有界（=文件大小），保留全部偏移 → Chromium 任意位置 seek
                    #     （含往回拖进度条）都能命中；转码流仍滑动裁剪防内存无限增长。
                    if out and not getattr(dec, "_native_mode", False) and not getattr(dec, "_full_timeline", False):
                        end_read = pos + len(out)
                        while dec._chunks and (dec._buf_start + dec._chunk_sizes[0]) <= end_read:
                            sz = dec._chunk_sizes.popleft()
                            dec._chunks.popleft()
                            dec._buf_start += sz
                            dec._buf_size -= sz
                return bytes(out)

            def do_GET(self):
                # ★ 等缓冲有数据（ffmpeg 转码启动有延迟）
                #   ★ 2026-08-13 修复：在线播放 ffmpeg 需先下载 CDN → 首帧延迟可达 8-10 秒
                #     → 等待时间从 3s 延长到 10s
                with dec._buf_lock:
                    buf_size = dec._buf_size
                    buf_start = dec._buf_start
                    closed = dec._buf_closed
                waited_total = 0
                if buf_size <= 0 and not closed:
                    # 缓冲为空但 ffmpeg 还在写 → 等一会
                    waited = 0
                    while waited < 10000:
                        time.sleep(0.05)
                        waited += 50
                        waited_total = waited
                        with dec._buf_lock:
                            buf_size = dec._buf_size
                            buf_start = dec._buf_start
                            closed = dec._buf_closed
                        if buf_size > 0 or closed:
                            break
                if buf_size <= 0 and not closed:
                    # ★ 2026-08-13 修复：空 200 会让 Chromium demuxer 报 PIPELINE_ERROR_READ
                    #   → 改回 503（Chromium 网络层会重试请求，不会当作数据损坏）
                    print(f"[FFmpegDecoder] ⚠️ HTTP 等待 {waited_total}ms 后缓冲仍为空（ffmpeg 可能下载失败/立即退出）")
                    self.send_response(503)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    return

                # ★ 当前可读范围：绝对偏移 [buf_start, buf_start+buf_size-1]
                abs_end = buf_start + buf_size - 1
                # ★ 内容类型：直通流按扩展名，转码流固定 video/webm
                if getattr(dec, "_native_mode", False):
                    content_type = "video/webm"
                    try:
                        lp = str(getattr(dec, "_last_src", "") or "").lower()
                        if lp.endswith(".ogg"):
                            content_type = "video/ogg"
                        elif lp.endswith(".mp3"):
                            content_type = "audio/mpeg"
                        elif lp.endswith(".flac"):
                            content_type = "audio/flac"
                    except Exception:
                        pass
                else:
                    content_type = "video/webm"
                # ★ 虚拟总大小：基于真实时长估算转码后字节数（固定值，避免 Chromium 的
                #   duration 随背压缓冲大小变化导致"实际播放时长与总时长不匹配"）
                #   ★★ 2026-08-13 修复：转码实际输出 = -b:v 1500k + -b:a 96k ≈ 1.6Mbps，
                #     原 0.8Mbps 估算过低 → 虚拟大小 < 实际输出 → Chromium 读到超过
                #     虚拟总大小的数据 → 认为文件损坏/不完整 → 「播几秒就停」。
                #     改用 1.7Mbps（略高于实际，Chromium 按 Content-Length 计算总时长更稳）。
                virtual_total = 0
                remain_http = 0
                if not getattr(dec, "_native_mode", False):
                    remain_http = max(0, float(getattr(dec, "_duration", 0) or 0) - float(getattr(dec, "_base_pos", 0) or 0))
                if remain_http > 0:
                    # ★ 优化 2：按编码器分档估算（GPU 1.7Mbps / CPU 0.8Mbps）
                    cur_venc = getattr(dec, "_current_venc", "") or ""
                    if cur_venc in ("vp9_qsv", "vp9_nvenc", "vp9_amf"):
                        virtual_total = int(remain_http * 1_700_000 / 8)
                    else:
                        # CPU libvpx / libvpx-vp9 / libvpx-vp8（crf VBR ≈0.3~1Mbps）
                        virtual_total = int(remain_http * 800_000 / 8)
                # 原生直通流：虚拟总大小 = 实际文件大小
                if getattr(dec, "_native_mode", False) and getattr(dec, "_src_fsize", 0) > 0:
                    virtual_total = dec._src_fsize
                # ★★ 2026-08-13 修复：ffmpeg 已结束 → virtual_total 用实际已缓冲总字节数
                #   （真实输出大小，Chromium 读到 EOF 时知道文件结束 → 不会卡住/停止）
                if getattr(dec, "_buf_closed", False):
                    virtual_total = dec._buf_start + dec._buf_size
                # 保证不小于当前已缓冲字节（避免 416）
                # ★★ 2026-08-13 修复：原生模式 virtual_total 必须【严格等于文件大小】。
                #   原逻辑 `<=` 且 `+1`：文件全缓冲后 virtual_total = fsize+1 →
                #   Content-Range 声明比实际文件多 1 字节 → Chromium 按此请求
                #   `bytes=fsize-`（最后一个“不存在的字节”）→ 服务器永远无法提供
                #   → demuxer STALLED → 超时后报 PIPELINE_ERROR_READ（在线视频续播必现）。
                #   原生模式跳过该调整（fsize 即精确总大小），转码流估计仍保留兜底。
                if not getattr(dec, "_native_mode", False) and virtual_total <= buf_start + buf_size:
                    virtual_total = buf_start + buf_size + 1

                # ★ 解析 Range 头（Chromium 播放请求可能带 Range: bytes=N-）
                range_header = self.headers.get("Range")
                start = buf_start  # 默认从缓冲最老开始
                end = abs_end
                if range_header:
                    try:
                        rng = range_header.replace("bytes=", "").strip()
                        if rng and "-" in rng:
                            parts = rng.split("-", 1)
                            if parts[0] == "":      # bytes=-N suffix range
                                suffix = int(parts[1]) if parts[1] else 0
                                start = max(buf_start, abs_end - suffix + 1)
                            else:
                                # 绝对偏移（Chromium 基于整体流绝对位置请求）
                                start = int(parts[0])
                                if parts[1]:
                                    end = int(parts[1])
                    except Exception:
                        pass

                # 防止越界
                if start < buf_start:
                    start = buf_start
                if end > abs_end:
                    end = abs_end
                if start > end:
                    # 请求起点超出当前缓冲（通常是前端续播 seek 到 reader 尚未读取的偏移）
                    if getattr(dec, "_buf_closed", False):
                        # ★★ 2026-08-13 修复：ffmpeg 已结束 → 返回 206 + 实际总大小
                        #   Chromium 据此知道文件已到末尾 → 正常停止而非卡住
                        actual_end = dec._buf_start + dec._buf_size - 1
                        self.send_response(206)
                        self.send_header("Content-Type", content_type)
                        self.send_header("Accept-Ranges", "bytes")
                        self.send_header("Content-Range", f"bytes {buf_start}-{actual_end}/{virtual_total}")
                        self.send_header("Content-Length", "0")
                        self.send_header("Connection", "close")
                        self.end_headers()
                        return
                    # ★★ 2026-08-13 修复：流仍在写入 → 等待 reader 读到该偏移再提供，
                    #   而不是立即 416。此前续播 seek 超出缓冲 → 416 → Chromium 判定
                    #   范围不可满足 → 播放失败（「视频一直播放」）。原生文件整文件缓冲
                    #   后 reader 会追到 seek 偏移（本地磁盘读取快，一般 <1s）。
                    waited = 0
                    # ★ 2026-08-14 在线完整模式：续播/拖到未转码处需等转码追上，预算放大到 10 分钟
                    _wait_budget = 600000 if getattr(dec, "_full_timeline", False) else 60000
                    while waited < _wait_budget:
                        time.sleep(0.05)
                        waited += 50
                        with dec._buf_lock:
                            buf_start = dec._buf_start
                            buf_size = dec._buf_size
                            closed = dec._buf_closed
                        abs_end = buf_start + buf_size - 1
                        if start < buf_start:
                            start = buf_start
                        if end > abs_end:
                            end = abs_end
                        if start <= end or closed:
                            break
                    if start > end:
                        if closed:
                            actual_end = dec._buf_start + dec._buf_size - 1
                            self.send_response(206)
                            self.send_header("Content-Type", content_type)
                            self.send_header("Accept-Ranges", "bytes")
                            self.send_header("Content-Range", f"bytes {buf_start}-{actual_end}/{virtual_total}")
                            self.send_header("Content-Length", "0")
                            self.send_header("Connection", "close")
                            self.end_headers()
                            return
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{virtual_total}")
                        self.end_headers()
                        return

                length = end - start + 1

                # ★ 典型响应：206 + Content-Range + Content-Length（Chromium 依赖）
                self.send_response(206 if range_header else 200)
                self.send_header("Content-Type", content_type)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{virtual_total}")
                self.send_header("Content-Length", str(length))
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()

                # ★ 从环形缓冲读取指定范围发送
                try:
                    remaining = length
                    read_size = 64 * 1024
                    empty_wait = 0  # ★ 2026-08-13 空数据等待毫秒计数
                    while remaining > 0:
                        to_read = min(read_size, remaining)
                        data = self._read_chunks(start, to_read)
                        if data:
                            self.wfile.write(data)
                            self.wfile.flush()
                            start += len(data)
                            remaining -= len(data)
                            empty_wait = 0
                        else:
                            # 无可读数据：若 ffmpeg 已关闭且仍在等则退；否则等新数据
                            with dec._buf_lock:
                                closed_now = dec._buf_closed
                            if closed_now:
                                break
                            empty_wait += 50
                            # ★★ 2026-08-13 修复：原 5s 空等即断开 → 在 GPU 争用/写速慢于
                            #   播放时 body 短于已声明 Content-Length → Chromium 报
                            #   PIPELINE_ERROR_READ。_buf_closed 已在 ffmpeg 退出时可靠置位，
                            #   这里只需等数据即可，护栏放宽到 60s 防真卡死时线程长期挂起。
                            if empty_wait > 60000:
                                print(f"[FFmpegDecoder] ⚠️ 读取等待 {empty_wait}ms 无新数据，断开连接（Chromium 将重试）")
                                break
                            time.sleep(0.05)
                except (BrokenPipeError, ConnectionResetError):
                    # 客户端断开（正常停止/切歌）→ 提前退出
                    pass
                except Exception:
                    pass
                try:
                    self.wfile.flush()
                except Exception:
                    pass

            def log_message(self, *a):
                pass

        return H

    # ============================================
    # ★ 解码直渲：ffmpeg 解码 → JPEG 帧 → runJavaScript → 前端 <img>/Canvas 渲染
    #   不依赖 QWebEngine 解码能力；支持 H.264/HEVC/AAC/AV1 等任意 ffmpeg 可解码格式
    #   配合前端 _ensureFrameUI() 自绘控制条（播放/暂停/进度/音量/快进快退）
    # ============================================
    def _start_video(self, src, start_pos):
        """启动 ffmpeg 解码 → JPEG 帧 → 前端 <img> 直渲（无中间转码 WebM）
        ★ 修复：resume()/seek() 曾调用不存在的 _start_video() 导致崩溃
        解码帧通过 runJavaScript 推送到前端 window.videoApp.onFrame()
        """
        try:
            if not src:
                return False
            # ★ 终止旧的视频进程（避免多实例冲突）
            self._kill()
            self._paused = False
            # ★ 2026-08 修复：每次播放必须重置时长，防止上次播放残留时长污染本次播放
            self._duration = 0.0

            # ★ 探测帧率/时长（直渲推帧需要准确 fps；进度条需要 duration）
            try:
                info = self._probe(src)
                if info:
                    fr = float(info.get("avg_frame_rate") or info.get("r_frame_rate") or 25)
                    if "/" in str(fr):
                        n, d = str(fr).split("/")
                        fr = float(n) / float(d) if d and float(d) else 25.0
                    self._fps = fr
                # ★ 优先：数据库已存时长（列表显示正确 → 数据库可信）
                if self._vid:
                    try:
                        vid = self._repo.get_by_id(self._vid)
                        if vid and vid.get("duration"):
                            db_dur = float(vid["duration"])
                            if db_dur > 0:
                                self._duration = db_dur
                    except Exception:
                        pass
                # 兜底 1：数据库无时长 → ffprobe 探测 stream.duration
                if not self._duration and info:
                    self._duration = float(info.get("duration") or 0)
                # 兜底 2：本机无 ffprobe → 用 ffmpeg -i 解析兜底
                if not self._duration and os.path.isfile(src):
                    try:
                        r2 = subprocess.run(
                            [FFMPEG, "-hide_banner", "-i", src],
                            capture_output=True, text=True, timeout=15)
                        import re as _re
                        m = _re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
                                       (r2.stderr or "") + (r2.stdout or ""))
                        if m:
                            hh, mm, ss = int(m.group(1)), int(m.group(2)), float(m.group(3))
                            self._duration = hh * 3600 + mm * 60 + ss
                    except Exception:
                        pass
            except Exception:
                pass

            # ffmpeg 解码为 JPEG 帧（-f image2pipe -c:v mjpeg，画质优先 q2）
            cmd = [
                FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin",
                "-ss", str(float(start_pos or 0)),
                "-i", src,
                # ★ 缩放至最大宽度 1280（保持宽高比），控制带宽
                "-vf", f"scale='min(1280,iw)':-2",
                # 输出 JPEG 帧流（最高画质）
                "-f", "image2pipe", "-c:v", "mjpeg", "-q:v", str(JPEGQ), "-"
            ]
            # 在线 URL 加 Referer/UA
            if str(src).startswith(("http://", "https://")):
                try:
                    referer = self._referer_for(src)
                    if referer:
                        self._insert_headers(cmd, self._http_headers(referer), which=1)
                except Exception:
                    pass

            print(f"[FFmpegDecoder] 🎬 解码直渲: {' '.join(str(x)[:80] for x in cmd)}")
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL)

            def _drain_err():
                collected = b""
                try:
                    while self._proc and self._proc.poll() is None:
                        chunk = self._proc.stderr.read(4096)
                        if not chunk:
                            break
                        collected += chunk
                    if collected:
                        print(f"[FFmpegDecoder] ❌ 直渲stderr:\n"
                              f"{collected.decode('utf-8', errors='replace')[:400]}")
                except Exception:
                    pass
            threading.Thread(target=_drain_err, daemon=True).start()

            # 启动推帧线程（复用 _video_loop 逻辑）
            # _video_loop 将帧通过 onFrame() push 给前端 <img> 渲染
            self._stop = False
            self._thread = threading.Thread(target=self._video_loop, daemon=True)
            self._thread.start()

            # 健康检查
            time.sleep(1.2)
            if self._proc.poll() is not None:
                print("[FFmpegDecoder] ❌ 直渲 ffmpeg 启动即退出")
                return False
            print(f"[FFmpegDecoder] ▶ 解码直渲启动 @ {float(start_pos or 0):.1f}s")
            return True
        except Exception as e:
            print(f"[FFmpegDecoder] ❌ 解码直渲启动失败: {e}")
            return False

    def _video_loop(self):
        buf = bytearray()
        frames = 0
        print(f"[FFmpegDecoder] _video_loop 启动, fps={self._fps:.2f}")
        try:
            while not self._stop and self._proc and self._proc.poll() is None:
                chunk = self._proc.stdout.read(65536)
                if not chunk:
                    print(f"[FFmpegDecoder] _video_loop: stdout 关闭(共{frames}帧)")
                    break
                buf += chunk
                idx = buf.find(b"\xff\xd9")
                while idx != -1:
                    start = buf.find(b"\xff\xd8")
                    if start == -1:
                        buf = bytearray()
                        break
                    frame = bytes(buf[start:idx + 2])
                    del buf[:idx + 2]
                    frames += 1
                    # ★ 进度 = 起始位置 + 已解帧数/帧率
                    self._pos = self._base_pos + frames / max(1.0, self._fps)
                    try:
                        b64 = base64.b64encode(frame).decode()
                        if self._webview:
                            # ★ 2026-08 用户反馈：QWebEngineView 删除后仍在推帧
                            #   （wrapped C/C++ object has been deleted）
                            #   推帧前检查底层 C++ 对象是否已被销毁；销毁则立即终止推帧
                            if not self._webview_alive():
                                print("[FFmpegDecoder] ⚠️ QWebEngineView 已销毁，停止推帧")
                                self._stop = True
                                self._kill()
                                return
                            self._webview.page().runJavaScript(
                                "window.videoApp&&window.videoApp.onFrame&&"
                                f"window.videoApp.onFrame('{b64}')")
                            # ★ 优化 4：日志降噪（原每 60 帧打印 → 每 300 帧）
                            if frames <= 3 or frames % 300 == 0:
                                print(f"[FFmpegDecoder] 已推帧 #{frames} ({len(frame)}B)")
                    except Exception as e:
                        # ★ C/C++ 对象被删除时 PyQt 抛 RuntimeError，
                        #   视作 webview 已销毁 → 停止后续所有推帧
                        msg = str(e)
                        if "deleted" in msg.lower() or "wrapper" in msg.lower():
                            print("[FFmpegDecoder] ⚠️ QWebEngineView 已删除，终止推帧")
                            self._stop = True
                            self._kill()
                            return
                        print(f"[FFmpegDecoder] ⚠️ 推帧失败: {e}")
                    time.sleep(1.0 / max(1.0, self._fps))
                    if self._stop:
                        print(f"[FFmpegDecoder] _video_loop 停止(共{frames}帧)")
                        return
                    idx = buf.find(b"\xff\xd9")
        except Exception as e:
            print(f"[FFmpegDecoder] _video_loop 异常: {e}")
        print(f"[FFmpegDecoder] _video_loop 退出(共{frames}帧)")

    def _webview_alive(self):
        """检查 QWebEngineView 底层 C++ 对象是否仍存活（避免推帧到已删除对象）"""
        try:
            if self._webview is None:
                return False
            # 访问 shiboken 有效性检查（PyQt5 用 sip 判断 C++ 对象是否被删除）
            try:
                import sip
                if sip.isdeleted(self._webview):
                    return False
            except ImportError:
                pass
            # 兜底：尝试访问无害属性，捕获 RuntimeError
            try:
                # noinspection PyUnresolvedReferences
                self._webview.page()
            except RuntimeError:
                return False
            return True
        except Exception:
            return False

    # ============================================
    # 缓冲工具
    # ============================================
    def _reset_buffer(self):
        with self._buf_lock:
            self._buf_gen += 1  # ★ 新代际：旧写线程 finally 不再能污染新流
            self._chunks.clear()
            self._chunk_sizes.clear()
            self._buf_start = 0
            self._buf_size = 0
            self._buf_closed = False
            self._gen_head = b""  # 新代际 → 头部副本重新开始
        self._native_mode = False
        self._src_fsize = 0
        self._full_timeline = False

    def _start_buf_writer(self):
        """ffmpeg stdout → deque 背压缓冲（缓冲满时暂停读取 → ffmpeg 写 pipe 阻塞自然限速）
        ★ 2026-08-13 修复：原环形丢弃方案在 GPU 10-20x 转码下缓冲秒满 → 最老数据被丢弃
          → Chromium 按 1x 播放时请求的数据已不在 → 「播几秒就停」
          背压方案：数据永不丢弃；缓冲满时暂停读 stdout（ffmpeg 写满 OS pipe 后阻塞降速）"""
        gen = self._buf_gen  # ★ 捕获当前代际：旧线程在 seek/回退后不再能写 _buf_closed
        proc = self._proc     # ★ 捕获进程引用：避免旧线程读到被替换的新进程

        def _buf_writer():
            try:
                while proc and proc.poll() is None:
                    # ★ 背压：缓冲满时暂停读取（锁外 sleep，避免阻塞 HTTP 读取线程）
                    with self._buf_lock:
                        # ★ 2026-08-14 在线完整模式：数据永不弹出 → 上限放大到视频转码后大小
                        cap = getattr(self, "_full_timeline_cap", 0) if getattr(self, "_full_timeline", False) else self._MAX_BUF
                        buf_full = self._buf_size >= cap
                    if buf_full:
                        time.sleep(0.05)
                        continue
                    data = proc.stdout.read(65536)
                    if not data:
                        break
                    with self._buf_lock:
                        # 代际变化说明已被 reset/seek → 本线程应退出
                        if gen != self._buf_gen:
                            break
                        # ★ 头部钉住：镜像流前 _HEAD_PIN 字节（永不弹出）
                        if len(self._gen_head) < self._HEAD_PIN:
                            self._gen_head += data[:self._HEAD_PIN - len(self._gen_head)]
                        self._chunks.append(data)
                        self._chunk_sizes.append(len(data))
                        self._buf_size += len(data)
            except Exception as e:
                print(f"[FFmpegDecoder] ⚠️ 背压缓冲写入异常: {e}")
            finally:
                with self._buf_lock:
                    # ★ 只有当前代际的写线程才能关闭缓冲（防止旧线程污染新流）
                    if gen == self._buf_gen:
                        self._buf_closed = True

        threading.Thread(target=_buf_writer, daemon=True).start()

    # ============================================
    # 音频
    # ============================================
    def _start_audio(self, src, start_pos):
        try:
            import sounddevice as sd
            cmd = [FFMPEG, "-hide_banner", "-loglevel", "error",
                   "-ss", str(float(start_pos)),
                   "-i", src,
                   "-vn", "-f", "s16le", "-ac", str(CH), "-ar", str(AR), "-"]
            self._aproc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            frame = AR * CH * 2

            def _audio_loop():
                import numpy as np
                with sd.OutputStream(samplerate=AR, channels=CH,
                                     dtype="int16", blocksize=4096) as stream:
                    while not self._stop and self._aproc and self._aproc.poll() is None:
                        data = self._aproc.stdout.read(frame)
                        if not data:
                            break
                        arr = np.frombuffer(data, dtype=np.int16)
                        usable = len(arr) - (len(arr) % CH)
                        if usable:
                            arr = arr[:usable].reshape(-1, CH)
                            # ★ 音量
                            if self._vol < 0.999:
                                arr = (arr.astype(np.float32) * self._vol).astype(np.int16)
                            stream.write(arr)
            threading.Thread(target=_audio_loop, daemon=True).start()
        except Exception as e:
            print(f"[FFmpegDecoder] 音频启动失败: {e}")

    # ============================================
    # 控制：暂停/续播/快进/音量/停止
    # ============================================
    def _kill(self):
        for p in (self._proc, self._aproc):
            if p and p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass
        self._proc = self._aproc = None

    def _cleanup_server(self):
        """关闭当前 HTTP 流 server（启动失败/中断时释放端口与线程，避免泄漏）"""
        srv = getattr(self, "_server", None)
        if srv:
            try:
                srv.shutdown()
            except Exception:
                pass
            try:
                srv.server_close()
            except Exception:
                pass
            self._server = None

    def pause(self):
        """暂停：终止 ffmpeg 子进程并记录当前位置"""
        if self._paused:
            return
        self._paused = True
        self._paused_at = float(self._pos)
        self._stop = True
        self._kill()
        try:
            import sounddevice
            sounddevice.stop()
        except Exception:
            pass
        print(f"[FFmpegDecoder] ⏸ 已暂停 @ {self._paused_at:.1f}s")

    def resume(self):
        """续播：从暂停位置重新启动（-ss 定位）"""
        if not self._paused or not self._last_src:
            return
        self._paused = False
        self._stop = False
        pos = self._paused_at or float(self._pos)
        self._base_pos = pos
        self._vid = self._last_vid
        self._start_audio(self._last_src, pos)
        self._start_video(self._last_src, pos)
        print(f"[FFmpegDecoder] ▶ 续播 @ {pos:.1f}s")

    def seek(self, sec):
        """快进/快退到指定秒（绝对值）。终止后从新位置重开"""
        if not self._last_src:
            return
        try:
            target = max(0.0, float(sec))
            if self._duration and target > self._duration:
                target = self._duration
        except Exception:
            target = 0.0
        self._stop = True
        self._kill()
        self._paused = False
        self._base_pos = target
        self._pos = target
        self._stop = False
        self._vid = self._last_vid
        self._start_audio(self._last_src, target)
        self._start_video(self._last_src, target)
        print(f"[FFmpegDecoder] ⏩ seek → {target:.1f}s")

    def seek_stream(self, sec):
        """★ 前端进度条拖放：重启 ffmpeg 从新位置转码，返回新流 URL（含 ?seek=秒，强制 Chromium 重新解析）
        复用同一 HTTP server；清空环形缓冲并把新位置作为新的 0 偏移。
        Returns: 新 URL 字符串；失败返回 ""（前端保持原播放）
        """
        if not self._last_src:
            return ""
        try:
            target = max(0.0, float(sec))
            if self._duration and target > self._duration:
                target = self._duration
        except Exception:
            target = 0.0

        # 终止当前转码，保留 HTTP server 与端口
        self._stop = True
        self._kill()
        self._paused = False
        self._base_pos = target
        self._pos = target
        self._stop = False

        # 清空环形缓冲：新位置作为新流的 0 偏移
        with self._buf_lock:
            self._buf_gen += 1  # ★ 新代际：旧写/读线程 finally 不再能污染新流
            self._chunks.clear()
            self._chunk_sizes.clear()
            self._buf_start = 0
            self._buf_size = 0
            self._buf_closed = False
            self._gen_head = b""  # 新代际 → 头部副本重新开始

        # ★★ 若是原生直通模式 → 重启文件读取
        if getattr(self, "_native_mode", False):
            src = self._last_src
            fsize = os.path.getsize(src)
            # ★ 2026-08-13 修复：与 _start_native_stream 一致 —— 原生文件流不再按字节跳过
            #   （webm 无 EBML 头无法解析 → SRC_NOT_SUPPORTED），整文件从头读、缓冲上限=文件大小，
            #   Chromium 原生按 Cues seek；此处 URL ?seek=<秒> 供前端定位，不裁剪文件。
            skip_bytes = 0
            gen = self._buf_gen  # ★ 捕获代际

            def _reader():
                try:
                    with open(src, "rb") as f:
                        f.seek(skip_bytes)
                        while not self._stop:
                            # ★ 背压：缓冲满时暂停读取（锁外 sleep）
                            with self._buf_lock:
                                buf_full = self._buf_size >= fsize
                            if buf_full:
                                time.sleep(0.05)
                                continue
                            data = f.read(65536)
                            if not data:
                                break
                            with self._buf_lock:
                                if gen != self._buf_gen:
                                    break  # 已被再次 reset/seek → 退出
                                # ★ 头部钉住：镜像流前 _HEAD_PIN 字节（永不弹出）
                                if len(self._gen_head) < self._HEAD_PIN:
                                    self._gen_head += data[:self._HEAD_PIN - len(self._gen_head)]
                                self._chunks.append(data)
                                self._chunk_sizes.append(len(data))
                                self._buf_size += len(data)
                except Exception as e:
                    print(f"[FFmpegDecoder] seek_stream 原生读取异常: {e}")
                finally:
                    with self._buf_lock:
                        # ★ 只有当前代际的读线程才能关闭缓冲
                        if gen == self._buf_gen:
                            self._buf_closed = True

            threading.Thread(target=_reader, daemon=True).start()
            time.sleep(0.3)
            port = getattr(self, "_port", 0)
            return f"http://127.0.0.1:{port}/stream?seek={int(target)}&src=native"

        # 重启 ffmpeg 从 target 开始转码（复用同一 server 与 handler）
        venc = self._detect_video_encoder()
        aenc = self._detect_audio_encoder()
        if not venc or not aenc:
            return ""
        src = self._last_src
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin",
               "-ss", str(target), "-i", src]
        audio_src = getattr(self, "_last_audio_src", None)
        audio_is_online = bool(audio_src and str(audio_src).startswith(("http://", "https://")))
        if audio_src and (os.path.exists(audio_src) or audio_is_online):
            cmd += ["-ss", str(target), "-i", audio_src]
            if audio_is_online:
                try:
                    audio_ref = self._referer_for(audio_src)
                    if audio_ref:
                        self._insert_headers(cmd, self._http_headers(audio_ref), which=2)
                except Exception:
                    pass
            self._has_separate_audio = True
        else:
            self._has_separate_audio = False
        # 在线 URL 加 headers
        if str(src).startswith(("http://", "https://")):
            try:
                referer = self._referer_for(src)
                if referer:
                    self._insert_headers(cmd, self._http_headers(referer), which=1)
            except Exception:
                pass
        out_args = []
        # ★ 2026-08-14 修复：在线模式 seek 也加 -t（与 _start_stream 对在线一致）
        #   → WebM 头预写剩余时长，避免 Chromium 时长未知（Infinity）
        remain_dur2 = max(0, float(getattr(self, "_duration", 0) or 0) - float(target or 0))
        if remain_dur2 > 0:
            out_args += ["-t", str(remain_dur2)]
        out_args += self._build_video_out_args(venc, aenc)
        if getattr(self, "_has_separate_audio", False):
            out_args = ["-map", "0:v:0", "-map", "1:a:0"] + out_args
        cmd += out_args + ["-f", "webm", "pipe:1"]
        print(f"[FFmpegDecoder] seek_stream 转码: {' '.join(cmd)}")
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL)
        except Exception as e:
            print(f"[FFmpegDecoder] seek_stream 启动失败: {e}")
            return ""

        self._start_buf_writer()

        # 健康检查
        time.sleep(1.2)
        if self._proc.poll() is not None:
            print("[FFmpegDecoder] seek_stream ffmpeg 启动即退出")
            return ""

        # ★ 新 URL 带 ?seek= 参数 → 强制 Chromium 视为全新资源重新解析
        port = getattr(self, "_port", 0)
        return f"http://127.0.0.1:{port}/stream?seek={int(target)}&src=transcode"

    def stop(self):
        self._stop = True
        self._kill()
        if getattr(self, "_server", None):
            try:
                self._server .shutdown()
            except Exception:
                pass
            try:
                self._server.server_close()
            except Exception:
                pass
            self._server = None
        # ★ 清空环形缓冲，标记关闭
        with self._buf_lock:
            self._chunks.clear()
            self._chunk_sizes.clear()
            self._buf_size = 0
            self._buf_start = 0
            self._buf_closed = True
        self._native_mode = False
        self._src_fsize = 0
        self._full_timeline = False
        try:
            import sounddevice
            sounddevice.stop()
        except Exception:
            pass

    def set_volume(self, v):
        try:
            self._vol = max(0.0, min(1.0, float(v)))
        except Exception:
            self._vol = 0.8
        print(f"[FFmpegDecoder] 🔊 音量 {self._vol:.2f}")

    def is_playing(self):
        return bool(self._proc and self._proc.poll() is None and not self._stop)

    def current_position(self):
        return int(self._pos)

    def get_duration(self):
        return int(self._duration or 0)

    def close_player(self):
        self._save()
        self.stop()

    # ============================================
    # 断点续播保存（5s 定时）
    # ============================================
    def _start_save_timer(self):
        threading.Thread(target=self._save_timer_loop, daemon=True).start()

    def _save_timer_loop(self):
        while not self._stop:
            time.sleep(5)
            self._save()

    def _save(self):
        if self._vid:
            try:
                self._repo.update_last_position(self._vid, self.current_position())
            except Exception:
                pass