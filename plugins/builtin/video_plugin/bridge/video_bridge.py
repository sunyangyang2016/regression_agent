"""视频插件桥接层 - JS <-> Python 通信"""
import json
import os
import sys
import threading
from urllib.parse import urlparse
from PyQt5.QtCore import QObject, pyqtSlot, pyqtSignal

from storage.repositories.video_repo import VideoRepository
from ..player import FFmpegDecoder

# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
))))
# 下载目录（用户配置目录下）
VIDEO_DIR = os.path.join(_PROJECT_ROOT, "user_config", "media", "videos")

# → preschool-video 内部脚本目录（搜索/解析执行器，使 Skill 自包含）
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "skills", "md", "preschool-video", "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from video_catcher_runner import search_videos, ytdlp_get_url, run_video_catcher, save_auth

_bridge_instance = None


def get_bridge_instance():
    """供插件内部（observer 等）获取 VideoBridge 单例"""
    return _bridge_instance


class VideoBridge(QObject):
    """供前端 video.js 调用的 QWebChannel 桥"""

    # ★ 2026-08-13 后台线程 → GUI 线程的 JS 执行通道：
    #   QWebEngine 的 page().runJavaScript() 只能在 GUI 主线程调用。
    #   后台线程（下载/搜索/解析/播放 worker）不能直接调 runJavaScript，
    #   统一 emit 本信号 → Qt 自动 marshal 回 GUI 线程执行（跨线程 QueuedConnection）。
    _jsRequested = pyqtSignal(str)

    def __init__(self, parent=None, webview=None):
        super().__init__(parent)
        global _bridge_instance
        _bridge_instance = self
        self._webview = webview
        self._repo = VideoRepository()
        # ★ 内嵌播放器（QMediaPlayer + HWND 嵌入 webview，不弹窗）
        self._external_player = FFmpegDecoder(self._webview)
        self._jsRequested.connect(self._exec_js_on_gui)
        # ★ 2026-08-13 播放器互斥锁：所有 FFmpegDecoder 变更操作（play/seek/stop/close）
        #   在后台线程异步执行，用此锁串行化，避免 GUI 线程与播放 worker 并发访问内部状态
        self._player_lock = threading.RLock()

    # ==========================================
    # 工具方法
    # ==========================================

    def execute_js(self, js_code: str):
        """★ 线程安全地执行前端 JS：后台线程 emit 信号 → GUI 线程执行 runJavaScript"""
        try:
            if self._webview:
                self._jsRequested.emit(js_code)
        except Exception as e:
            print(f"[VideoBridge] JS 执行失败: {e}")

    def _exec_js_on_gui(self, js_code: str):
        """仅在 GUI 主线程执行（信号跨线程 QueuedConnection 自动 marshal）"""
        try:
            if self._webview:
                self._webview.page().runJavaScript(js_code)
        except Exception as e:
            print(f"[VideoBridge] JS 执行失败: {e}")

    # ==========================================
    # ★ 后台播放完成通知（worker 线程 → execute_js → GUI 线程执行 JS 回调）
    # ==========================================
    def _notify_play_ready(self, video_id, data):
        """通知前端 playReady(video_id, data)：播放流已就绪（mode: native/transcode/stream）"""
        try:
            payload = json.dumps(data, ensure_ascii=False)
            self.execute_js("window.videoApp && window.videoApp.playReady(%s, %s);" % (
                json.dumps(video_id or "", ensure_ascii=False), payload))
        except Exception as e:
            print(f"[VideoBridge] playReady 通知失败: {e}")

    def _notify_seek_ready(self, video_id, data):
        """通知前端 seekReady(video_id, data)：seek 新流 URL 已就绪"""
        try:
            payload = json.dumps(data, ensure_ascii=False)
            self.execute_js("window.videoApp && window.videoApp.seekReady(%s, %s);" % (
                json.dumps(video_id or "", ensure_ascii=False), payload))
        except Exception as e:
            print(f"[VideoBridge] seekReady 通知失败: {e}")

    # ==========================================
    # 前端调用（前端 -> Python）
    # ==========================================

    @pyqtSlot(str, result=str)
    def getVideos(self, filter_json):
        """获取视频列表（按科目/年级/来源/关键词筛选）"""
        try:
            f = json.loads(filter_json or "{}")
            videos = self._repo.get_all(
                subject=f.get("subject"),
                grade=f.get("grade"),
                source=f.get("source"),
                status=f.get("status"),
                keyword=f.get("keyword"),
                limit=f.get("limit", 100),
                offset=f.get("offset", 0),
            )
            # ★ 自动补录：旧版本 downloaded 记录 localPath 为空时，扫描固定目录回写
            for v in videos:
                if v.get("status") == "downloaded" and not v.get("localPath"):
                    local_file, audio_file = self._scan_local_files(v.get("id"))
                    if local_file:
                        self._repo.mark_downloaded(
                            v["id"], local_file,
                            os.path.getsize(local_file),
                            os.path.splitext(local_file)[1][1:],
                            audio_path=audio_file,
                        )
                        v["localPath"] = local_file
                        v["audioPath"] = audio_file
            return json.dumps(videos, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @pyqtSlot(str, result=str)
    def searchOnline(self, keyword):
        """★ 前端搜索按钮 → yt-dlp 搜索 B站 → 写入视频库 → 返回结果
        ★ 2026-08-13 异步化：搜索（bilisearch + 逐个解析元数据）耗时可能数十秒，
          改后台线程执行，完成后 JS 回调 window.videoApp.searchDone()，不再阻塞 GUI 线程。
        """
        try:
            keyword = (keyword or "").strip()
            if not keyword:
                return json.dumps({"ok": False, "message": "请输入搜索关键词"}, ensure_ascii=False)

            def _worker():
                try:
                    videos = search_videos(keyword, limit=10)
                    for v in videos:
                        if not v.get("subject"):
                            v["subject"] = self._guess_subject(keyword)
                        if not v.get("grade"):
                            v["grade"] = self._guess_grade(keyword)
                        v["source"] = v.get("source") or "bilibili"

                    if not videos:
                        self._notify_search_done({
                            "ok": False, "message": f"未搜索到相关视频（关键词: {keyword}）"
                        })
                        return

                    added = self._repo.add_many(videos)
                    self.refresh_frontend({"added": added, "total": len(videos), "keyword": keyword})
                    self._notify_search_done({"ok": True, "added": added, "total": len(videos)})
                except Exception as e:
                    self._notify_search_done({"ok": False, "message": str(e)[:200]})

            threading.Thread(target=_worker, daemon=True).start()
            return json.dumps({
                "ok": True, "started": True,
                "message": f"正在搜索：{keyword}..."
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "message": str(e)[:200]}, ensure_ascii=False)

    def _notify_search_done(self, payload):
        """后台线程完成搜索 → 前端 searchDone 回调（toast + 刷新列表）"""
        try:
            self.execute_js(
                "window.videoApp&&window.videoApp.searchDone&&"
                f"window.videoApp.searchDone({json.dumps(payload, ensure_ascii=False)});"
            )
        except Exception:
            pass

    @staticmethod
    def _guess_subject(keyword: str) -> str:
        subjects = {
            "数学": "数学", "算术": "数学", "数字": "数学", "计算": "数学",
            "语文": "语文", "拼音": "语文", "识字": "语文", "汉字": "语文",
            "英语": "英语", "字母": "英语", "abc": "英语",
            "科学": "科学", "实验": "科学", "自然": "科学",
            "艺术": "艺术", "画画": "艺术", "美术": "艺术", "音乐": "艺术",
            "健康": "健康", "体育": "健康", "安全": "健康",
        }
        kw = keyword.lower()
        for k, v in subjects.items():
            if k in kw:
                return v
        return None

    @staticmethod
    def _guess_grade(keyword: str) -> str:
        grades = {
            "学前班": "学前班", "幼小衔接": "学前班", "幼儿园": "学前班",
            "大班": "大班", "中班": "中班", "小班": "小班",
        }
        for k, v in grades.items():
            if k in keyword:
                return v
        return None

    @pyqtSlot(str, result=int)
    def getLastPosition(self, video_id):
        try:
            return self._repo.get_playback_position(video_id)
        except Exception:
            return 0

    @pyqtSlot(str, result=str)
    def getPlayableUrl(self, video_id):
        """★ 获取可播放的视频地址（前端在线播放前调用）
        ★ 2026-08-13 异步化：本地文件扫描秒回；在线 URL 解析（yt-dlp 最长 60s）
          放后台线程执行，完成后 JS 回调 window.videoApp.playUrlReady() 继续播放流程，
          不再阻塞 GUI 线程。"""
        try:
            video = self._repo.get_by_id(video_id)
            if not video:
                return json.dumps({"ok": False, "message": "视频不存在"}, ensure_ascii=False)

            # ★ 本地兜底：即使数据库 localPath 为空，也探测固定目录，
            # 已下载的视频一律播本地（绝不回退在线裸 m4s）
            if not (video.get("localPath") and os.path.exists(video.get("localPath"))):
                local_file, audio_file = self._scan_local_files(video_id)
                if local_file:
                    self._repo.mark_downloaded(
                        video_id, local_file,
                        os.path.getsize(local_file),
                        os.path.splitext(local_file)[1][1:],
                        audio_path=audio_file,
                    )
                    print(f"[VideoBridge] ▶ 本地文件播放: {local_file}")
                    result = {"ok": True, "url": local_file, "local": True}
                    if audio_file:
                        result["audio_url"] = audio_file
                    return json.dumps(result, ensure_ascii=False)

            if video.get("localPath") and os.path.exists(video.get("localPath")):
                print(f"[VideoBridge] ▶ 本地文件播放: {video['localPath']}")
                result = {"ok": True, "url": video["localPath"], "local": True}
                if video.get("audioPath") and os.path.exists(video.get("audioPath")):
                    result["audio_url"] = video["audioPath"]
                return json.dumps(result, ensure_ascii=False)

            page_url = video.get("pageUrl") or video.get("playUrl")
            if not page_url:
                return json.dumps({"ok": False, "message": "该视频没有可用的播放地址"},
                                  ensure_ascii=False)

            # ★ 在线：后台线程解析真实播放地址 → JS 回调 playUrlReady
            print(f"[VideoBridge] 🔍 在线解析: {str(page_url)[:60]}")
            threading.Thread(
                target=self._resolve_online_url, args=(video_id, page_url), daemon=True
            ).start()
            return json.dumps({"ok": True, "started": True,
                               "message": "正在解析视频地址..."}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "message": str(e)[:200]}, ensure_ascii=False)

    def _resolve_online_url(self, video_id, page_url):
        """后台线程：yt-dlp 解析在线真实播放地址 → JS 回调 playUrlReady"""
        try:
            print(f"[VideoBridge] 🔍 开始解析在线地址: {str(page_url)[:60]} ...")
            real_urls = ytdlp_get_url(page_url, timeout=60)
            if not real_urls:
                site = urlparse(page_url).netloc or "unknown"
                try:
                    from video_catcher_runner import get_auth_for_url
                    has_auth = bool(get_auth_for_url(page_url))
                except Exception:
                    has_auth = False
                print(f"[VideoBridge] ⚠️ 解析失败，需要认证: {site} (has_auth={has_auth})")
                if not has_auth:
                    payload = {"ok": False, "need_auth": True, "site": site,
                               "message": f"该网站（{site}）需要认证才能播放，请提供 Cookie/Token"}
                else:
                    payload = {"ok": False, "need_auth": True, "site": site,
                               "auth_expired": True,
                               "message": f"认证信息可能已过期，请更新{site}的认证信息"}
                self._notify_play_url_ready(video_id, payload)
                return

            print(f"[VideoBridge] ✅ yt-dlp 返回 {len(real_urls)} 个地址")
            if len(real_urls) == 1:
                real_url = real_urls[0]
                self._repo.update(video_id, {"play_url": real_url})
                self._notify_play_url_ready(video_id,
                                            {"ok": True, "url": real_url, "local": False})
                return

            video_url = real_urls[0]
            audio_url = real_urls[1] if len(real_urls) > 1 else None
            self._repo.update(video_id, {"play_url": video_url})
            self._notify_play_url_ready(video_id, {
                "ok": True, "url": video_url,
                "audio_url": audio_url, "local": False
            })
        except Exception as e:
            print(f"[VideoBridge] ❌ 在线解析失败: {e}")
            self._notify_play_url_ready(video_id, {"ok": False, "message": str(e)[:200]})

    def _notify_play_url_ready(self, video_id, payload):
        """后台线程完成 URL 解析 → 前端 playUrlReady(video_id, data) 回调（继续播放流程）
        ★ 2026-08-14 修复：此前只传 payload 单参数，JS playUrlReady(video_id, data)
          收到 video_id=对象、data=undefined → `video.id !== video_id` 恒真 → 在线回调被
          当过期丢弃 → 在线播放静默卡死。改为与 _notify_play_ready 一致的双参调用。"""
        try:
            payload_json = json.dumps(payload, ensure_ascii=False)
            self.execute_js(
                "window.videoApp && window.videoApp.playUrlReady && "
                "window.videoApp.playUrlReady(%s, %s);" % (
                    json.dumps(video_id or "", ensure_ascii=False), payload_json))
        except Exception as e:
            print(f"[VideoBridge] playUrlReady 通知失败: {e}")

    @pyqtSlot(str, str, result=str)
    def saveSiteAuth(self, site, auth_json):
        try:
            auth = json.loads(auth_json or "{}")
            if not auth:
                return json.dumps({"ok": False, "message": "认证信息不能为空"},
                                  ensure_ascii=False)
            save_auth(site.strip(), auth)
            return json.dumps({"ok": True, "site": site, "message": "认证信息已保存"},
                              ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "message": f"保存认证失败: {str(e)[:200]}"},
                              ensure_ascii=False)

    @pyqtSlot(str, int)
    def updateLastPosition(self, video_id, position):
        try:
            self._repo.update_last_position(video_id, int(position or 0))
        except Exception as e:
            print(f"[VideoBridge] 保存播放位置失败: {e}")

    @pyqtSlot(str)
    def incrementPlayCount(self, video_id):
        try:
            self._repo.increment_play_count(video_id)
        except Exception:
            pass

    @pyqtSlot(str)
    def downloadVideo(self, video_id):
        """启动下载（后台线程）— 委托 video-catcher 完成多平台下载

        使用固定目录 user_config/media/videos/<video_id>/ 保存，避免每次下载路径变化；
        下载前备份旧文件（*.bak），下载成功后再删除，失败时从 *.bak 恢复。
        """
        try:
            video = self._repo.get_by_id(video_id)
            if not video:
                return

            url = video.get("pageUrl") or video.get("playUrl")
            if not url:
                return

            vc_script = os.path.join(
                _PROJECT_ROOT, "skills", "md", "video-catcher",
                "scripts", "video_catcher.py"
            )
            if not os.path.exists(vc_script):
                print(f"[VideoBridge] video-catcher 脚本不存在: {vc_script}")
                self._repo.set_status(video_id, "failed")
                self.refresh_frontend({"video_id": video_id, "status": "failed"})
                return

            # ★ 固定下载子目录（同一视频固定路径，不随日期变化）
            video_dir = os.path.join(VIDEO_DIR, video_id)
            os.makedirs(video_dir, exist_ok=True)

            # 下载前备份旧文件（*.bak）
            self._backup_existing_media(video_dir)

            self._repo.set_status(video_id, "downloading", download_progress=0)
            self.refresh_frontend({"video_id": video_id, "status": "downloading", "progress": 0})

            def _do():
                try:
                    self._find_downloaded_later(video_id, vc_script, url, video_dir)
                except Exception as e:
                    print(f"[VideoBridge] 下载异常: {e}")
                    self._restore_backup(video_dir)
                    self._repo.set_status(video_id, "failed")
                    self.refresh_frontend({"video_id": video_id, "status": "failed"})

            threading.Thread(target=_do, daemon=True).start()
        except Exception as e:
            print(f"[VideoBridge] 启动下载失败: {e}")

    def _backup_existing_media(self, video_dir):
        """下载前备份目录中已有的媒体文件（重命名为 *.bak）"""
        try:
            if not os.path.isdir(video_dir):
                return
            for f in os.listdir(video_dir):
                if f.lower().endswith((".mp4", ".mkv", ".webm", ".mov")) and not f.endswith(".bak"):
                    src = os.path.join(video_dir, f)
                    dst = os.path.join(video_dir, f + ".bak")
                    try:
                        if os.path.exists(dst):
                            os.remove(dst)
                        os.rename(src, dst)
                    except OSError:
                        pass
        except Exception as e:
            print(f"[VideoBridge] 备份旧文件失败: {e}")

    def _restore_backup(self, video_dir):
        """下载失败时恢复备份的旧文件"""
        try:
            if not os.path.isdir(video_dir):
                return
            for f in os.listdir(video_dir):
                if f.endswith(".bak"):
                    src = os.path.join(video_dir, f)
                    dst = os.path.join(video_dir, f[:-4])
                    try:
                        if os.path.exists(dst):
                            os.remove(dst)
                        os.rename(src, dst)
                    except OSError:
                        pass
        except Exception as e:
            print(f"[VideoBridge] 恢复备份失败: {e}")

    def _cleanup_backup(self, video_dir):
        """下载成功后清理 *.bak 备份文件"""
        try:
            if not os.path.isdir(video_dir):
                return
            for f in os.listdir(video_dir):
                if f.endswith(".bak"):
                    try:
                        os.remove(os.path.join(video_dir, f))
                    except OSError:
                        pass
        except Exception as e:
            print(f"[VideoBridge] 清理备份失败: {e}")

    def _find_downloaded_later(self, video_id, vc_script, url, video_dir):
        """执行 video-catcher 下载并在结束后从固定目录扫描产物更新状态"""
        try:
            # ★ 使用 --run-dir 让 video-catcher 直接输出到固定子目录（不再创建日期子目录）
            returncode, stdout, stderr = run_video_catcher(
                vc_script, url, video_dir, run_dir=video_dir
            )
            # 扫描固定目录中的媒体文件（排除 .bak）
            media_files = []
            if os.path.isdir(video_dir):
                for f in os.listdir(video_dir):
                    if (f.lower().endswith((".mp4", ".mkv", ".webm", ".mov"))
                            and not f.endswith(".bak")):
                        fpath = os.path.join(video_dir, f)
                        media_files.append((fpath, os.path.getmtime(fpath)))
            if media_files:
                # 取最新的一个作为下载产物
                media_files.sort(key=lambda x: x[1], reverse=True)
                latest = media_files[0][0]
                size = os.path.getsize(latest)
                fmt = os.path.splitext(latest)[1][1:]
                # ★ 识别同目录配套音频文件（分离 DASH：video.mp4 + audio.m4a），
                # 写库 audio_path → 前端可同步播放，无需合并
                audio_path = self._find_paired_audio(video_dir, latest)
                self._repo.mark_downloaded(
                    video_id, latest, size, fmt, audio_path=audio_path
                )
                self._cleanup_backup(video_dir)
                self.refresh_frontend({
                    "video_id": video_id,
                    "status": "downloaded",
                    "local_path": latest,
                    "audio_path": audio_path,
                })
                return
            elif returncode != 0:
                # 增强错误详情：即使 stderr 为空也从 stdout / 退出码提取信息
                err_detail = (stderr or "").strip() or (stdout or "").strip() or "（无输出）"
                raise RuntimeError(f"video-catcher 退出码 {returncode}: {err_detail[:500]}")
            else:
                # 固定目录未找到媒体，可能输出到默认目录，递归查找
                self._search_nested_output(video_id)
        except Exception as e:
            print(f"[VideoBridge] 下载完成后处理失败: {e}")
            self._repo.set_status(video_id, "failed")
            self.refresh_frontend({"video_id": video_id, "status": "failed"})

    def _find_paired_audio(self, video_dir, video_path):
        """在视频文件同目录查找配对的音频文件（.m4a/.m4s/.mp3/.aac/.opus）

        返回匹配到的音频路径；无则返回 None。
        """
        try:
            stem = os.path.splitext(os.path.basename(video_path))[0]
            candidates = []
            for f in os.listdir(video_dir):
                if f.endswith(".bak"):
                    continue
                low = f.lower()
                if not low.endswith((".m4a", ".m4s", ".mp3", ".aac", ".opus")):
                    continue
                cand = os.path.join(video_dir, f)
                # 优先同 basename（如 video.mp4 ↔ video.m4a）
                if os.path.splitext(f)[0] == stem:
                    return cand
                candidates.append((cand, os.path.getmtime(cand)))
            if candidates:
                candidates.sort(key=lambda x: x[1], reverse=True)
                return candidates[0][0]
            return None
        except Exception as e:
            print(f"[VideoBridge] 查找配对音频失败: {e}")
            return None

    def _scan_local_files(self, video_id):
        """扫描固定目录 user_config/media/videos/<video_id>/ 找本地视频 + 配对音频（兜底用）

        返回 (video_file, audio_file)；无本地视频返回 (None, None)。
        """
        try:
            video_dir = os.path.join(VIDEO_DIR, video_id)
            if not os.path.isdir(video_dir):
                return None, None
            media_files = []
            for f in os.listdir(video_dir):
                if (f.lower().endswith((".mp4", ".mkv", ".webm", ".mov"))
                        and not f.endswith(".bak")):
                    fpath = os.path.join(video_dir, f)
                    media_files.append((fpath, os.path.getmtime(fpath)))
            if not media_files:
                return None, None
            media_files.sort(key=lambda x: x[1], reverse=True)
            video_file = media_files[0][0]
            audio_file = self._find_paired_audio(video_dir, video_file)
            return video_file, audio_file
        except Exception as e:
            print(f"[VideoBridge] 扫描本地文件失败: {e}")
            return None, None

    def _search_nested_output(self, video_id):
        """video-catcher 可能输出到默认目录，递归查找新文件并复制到固定目录"""
        try:
            download_root = VIDEO_DIR
            if not os.path.isdir(download_root):
                self._repo.set_status(video_id, "failed")
                self.refresh_frontend({"video_id": video_id, "status": "failed"})
                return
            video_dir = os.path.join(VIDEO_DIR, video_id)
            os.makedirs(video_dir, exist_ok=True)

            latest_media = None
            latest_mtime = 0
            for root, dirs, files in os.walk(download_root):
                for f in files:
                    if f.lower().endswith((".mp4", ".mkv", ".webm", ".mov")) and not f.endswith(".bak"):
                        if video_id in root:
                            continue
                        fpath = os.path.join(root, f)
                        mtime = os.path.getmtime(fpath)
                        if mtime > latest_mtime:
                            latest_mtime = mtime
                            latest_media = fpath
            if latest_media:
                import shutil
                target = os.path.join(video_dir, os.path.basename(latest_media))
                shutil.copy2(latest_media, target)
                size = os.path.getsize(target)
                fmt = os.path.splitext(target)[1][1:]
                audio_path = self._find_paired_audio(
                    os.path.dirname(latest_media), latest_media)
                self._repo.mark_downloaded(
                    video_id, target, size, fmt, audio_path=audio_path
                )
                self._cleanup_backup(video_dir)
                self.refresh_frontend({
                    "video_id": video_id,
                    "status": "downloaded",
                    "local_path": target,
                    "audio_path": audio_path,
                })
            else:
                self._repo.set_status(video_id, "failed")
                self.refresh_frontend({"video_id": video_id, "status": "failed"})
        except Exception as e:
            print(f"[VideoBridge] 递归查找产物失败: {e}")
            self._repo.set_status(video_id, "failed")
            self.refresh_frontend({"video_id": video_id, "status": "failed"})

    @pyqtSlot(str)
    def deleteVideo(self, video_id):
        """删除视频（本地文件 + 数据库记录）
        ★ 2026-08-13 修复：文件/目录删除（可能含大文件 rmtree）移后台线程，避免卡 GUI"""
        try:
            video = self._repo.get_by_id(video_id)
            # 数据库记录立即删（快）；本地文件后台清理
            self._repo.delete(video_id)
            self.refresh_frontend({"deleted": video_id})

            def _cleanup():
                try:
                    if video and video.get("localPath"):
                        local = video["localPath"]
                        if os.path.exists(local):
                            try:
                                os.remove(local)
                            except OSError:
                                pass
                    vdir = os.path.join(VIDEO_DIR, video_id)
                    if os.path.isdir(vdir):
                        import shutil
                        shutil.rmtree(vdir, ignore_errors=True)
                except Exception as e:
                    print(f"[VideoBridge] 删除文件清理失败: {e}")

            threading.Thread(target=_cleanup, daemon=True).start()
        except Exception as e:
            print(f"[VideoBridge] 删除失败: {e}")

    @pyqtSlot()
    def openVideoFolder(self):
        try:
            os.makedirs(VIDEO_DIR, exist_ok=True)
            os.startfile(VIDEO_DIR)
        except Exception as e:
            print(f"[VideoBridge] 打开目录失败: {e}")

    # ==========================================
    # ★ 外部播放器（QMediaPlayer，走系统解码器）
    # ==========================================

    @pyqtSlot(str, str, int, str, result=str)
    def playLocalVideo(self, file_path, video_id, start_pos, audio_path=""):
        """★ 本地转码播放（异步）：后台线程启动 ffmpeg 实时转码流（-t 预写 WebM 头
           Duration → 原生 controls 显示总时长）。完成后回调 playReady(video_id, data)。
           返回 {"started": true} 立即释放 GUI 线程；同步校验失败返回 {"ok": false}。
           audio_path: 可选分离音频文件。"""
        try:
            if not file_path or not os.path.exists(file_path):
                return json.dumps({"ok": False, "message": "文件不存在"}, ensure_ascii=False)
            # 目录 → 解析真实文件
            if os.path.isdir(file_path):
                resolved = self._external_player._resolve_dir_to_file(file_path)
                if not resolved:
                    return json.dumps({"ok": False, "message": "目录中未找到媒体文件"}, ensure_ascii=False)
                file_path = resolved
            audio_src = audio_path or None
            if audio_src and not os.path.exists(audio_src):
                audio_src = None

            def _worker():
                url = None
                err = None
                try:
                    with self._player_lock:
                        url = self._external_player.play(
                            file_path, video_id or None, int(start_pos or 0), audio_src=audio_src) or ""
                except Exception as e:
                    err = str(e)[:120]
                if err:
                    self._notify_play_ready(video_id, {"ok": False, "message": err})
                elif url:
                    self._notify_play_ready(video_id, {"mode": "transcode", "ok": True, "url": url})
                else:
                    self._notify_play_ready(video_id, {"ok": False, "message": "转码播放启动失败"})

            threading.Thread(target=_worker, daemon=True).start()
            return json.dumps({"started": True}, ensure_ascii=False)
        except Exception as e:
            print(f"[VideoBridge] 本地播放失败: {e}")
            return json.dumps({"ok": False, "message": str(e)[:120]}, ensure_ascii=False)

    @pyqtSlot(str, result=str)
    def probeNativePlayable(self, url):
        """★ 探测源文件是否 QWebEngine 原生可解码（VP8/VP9/Opus/MP3/FLAC）
        返回 JSON: {"ok": true, "native": true, "reason": "..."}
        若 native=true → 前端直接用原始 URL（file:///）播放，零转码
        若 native=false → 前端走 ffmpeg 转码流
        """
        try:
            if not url:
                return json.dumps({"ok": False, "native": False, "reason": "空 URL"},
                                  ensure_ascii=False)
            # 仅本地文件可判断（在线 URL 无法直接确定 → 一律转码）
            if str(url).startswith(("http://", "https://")):
                return json.dumps({"ok": True, "native": False,
                                   "reason": "在线 URL 一律走 ffmpeg 转码（含 Referer）"},
                                  ensure_ascii=False)
            if not os.path.exists(url):
                return json.dumps({"ok": False, "native": False, "reason": "文件不存在"},
                                  ensure_ascii=False)

            native_ok, reason = self._external_player._probe_codec_compat(url)
            return json.dumps({
                "ok": True,
                "native": bool(native_ok),
                "reason": reason or "",
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "native": False, "reason": str(e)[:200]},
                              ensure_ascii=False)

    @pyqtSlot(str, result=str)
    def getWebmCacheStatus(self, video_id):
        """★ 查询 video_id 的完整 webm 缓存是否已就绪（原生可显示总时长）
        返回 JSON: {"ready": true, "url": "file:///..."} 或 {"ready": false}
        ★ 2026-08-13 修复：原实现 import 不存在的 WEBM_CACHE_DIR → 必然 ImportError 被吞，
          且 glob 模式与真实路径 {video_id}/{video_id}.cache.webm 不匹配 → 永远返回 false。
        """
        try:
            from ..player import MEDIA_VIDEOS_DIR
            if not video_id:
                return json.dumps({"ready": False}, ensure_ascii=False)
            cache_file = os.path.join(MEDIA_VIDEOS_DIR, video_id, video_id + ".cache.webm")
            if os.path.isfile(cache_file) and os.path.getsize(cache_file) > 0:
                return json.dumps({
                    "ready": True,
                    "url": "file:///" + cache_file.replace("\\", "/"),
                    "duration_hint": self._external_player.get_duration()
                }, ensure_ascii=False)
            return json.dumps({"ready": False}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ready": False, "error": str(e)[:100]}, ensure_ascii=False)

    @pyqtSlot(str, str, int, str, result=str)
    def playOnlineVideo(self, url, video_id, start_pos, audio_url=""):
        """★ 在线播放（异步）：后台线程启动 ffmpeg 转码流（防 B站 m4s/HEVC 无法解码）。
           完成后回调 playReady(video_id, data)。返回 {"started": true} 立即释放 GUI 线程。
           audio_url: B站等 DASH 分离流的音频 URL（默认为空 = 视频自身带音轨）"""
        try:
            if not url or not str(url).startswith(("http://", "https://")):
                return json.dumps({"ok": False, "message": "无效的在线地址"}, ensure_ascii=False)
            # 分离音频（DASH 流）：有音频 URL 且也是 HTTP(S) 时才传给播放器合并
            audio_src = str(audio_url) if audio_url and str(audio_url).startswith(("http://", "https://")) else None

            def _worker():
                print(f"[VideoBridge] ▶ 在线播放 worker 启动: {str(url)[:60]} "
                      f"(video_id={video_id}, start={start_pos})")
                stream_url = None
                err = None
                try:
                    with self._player_lock:
                        # 自定义音频 URL 标记（_start_stream 内部检查 _last_audio_src 是文件或 URL）
                        self._external_player._last_audio_src = audio_src
                        stream_url = self._external_player.play(
                            url, video_id or None, int(start_pos or 0), audio_src=audio_src) or ""
                except Exception as e:
                    err = str(e)[:120]
                if err:
                    print(f"[VideoBridge] ❌ 在线播放失败: {err}")
                    self._notify_play_ready(video_id, {"ok": False, "message": err})
                elif stream_url:
                    print(f"[VideoBridge] ✅ 在线流就绪: {str(stream_url)[:60]}")
                    self._notify_play_ready(video_id, {"mode": "stream", "ok": True, "url": stream_url})
                else:
                    print("[VideoBridge] ❌ 在线播放启动失败（play() 返回空流地址）")
                    self._notify_play_ready(video_id, {"ok": False, "message": "在线转码启动失败"})

            threading.Thread(target=_worker, daemon=True).start()
            return json.dumps({"started": True}, ensure_ascii=False)
        except Exception as e:
            print(f"[VideoBridge] 在线播放失败: {e}")
            return json.dumps({"ok": False, "message": str(e)[:120]}, ensure_ascii=False)

    @pyqtSlot(str, str, int, str, result=str)
    def playLocalVideoNative(self, file_path, video_id, start_pos, audio_path=""):
        """★ 本地播放统一异步入口：后台线程一次性完成
           ①探测 QWebEngine 原生解码 → 原生支持直接 file:// 播放
           ②否则启动 ffmpeg 转码流
           完成后回调 playReady(video_id, {"mode":"native"/"transcode", "ok", "url"})。
           返回 {"started": true} 立即释放 GUI 线程（此前 ffprobe 探测最坏阻塞 ~15s）。"""
        try:
            if not file_path or not os.path.exists(file_path):
                return json.dumps({"ok": False, "message": "文件不存在"}, ensure_ascii=False)
            # 目录 → 解析真实媒体文件（与 play() 一致）
            if os.path.isdir(file_path):
                resolved = self._external_player._resolve_dir_to_file(file_path)
                if not resolved:
                    return json.dumps({"ok": False, "message": "目录中未找到媒体文件"}, ensure_ascii=False)
                print(f"[VideoBridge] ✓ 已解析媒体文件: {resolved}")
                file_path = resolved
            audio_src = audio_path or None
            if audio_src and not os.path.exists(audio_src):
                audio_src = None

            def _worker():
                print(f"[VideoBridge] ▶ 本地播放 worker 启动: {str(file_path)[:60]} "
                      f"(video_id={video_id}, start={start_pos})")
                mode = None
                url = None
                err = None
                try:
                    with self._player_lock:
                        native_ok, reason = self._external_player._probe_codec_compat(file_path)
                        if native_ok:
                            print(f"[VideoBridge] ⚡ 本地原生直通: {file_path[:80]} ({reason})")
                            mode, url = "native", file_path
                        else:
                            url = self._external_player.play(
                                file_path, video_id or None, int(start_pos or 0), audio_src=audio_src) or ""
                            if url:
                                mode = "transcode"
                except Exception as e:
                    err = str(e)[:120]
                if err:
                    print(f"[VideoBridge] ❌ 本地播放失败: {err}")
                    self._notify_play_ready(video_id, {"ok": False, "message": err})
                elif url:
                    print(f"[VideoBridge] ✅ 本地播放就绪: mode={mode} url={str(url)[:60]}")
                    self._notify_play_ready(video_id, {"mode": mode, "ok": True, "url": url})
                else:
                    print("[VideoBridge] ❌ 本地播放启动失败（未拿到流地址）")
                    self._notify_play_ready(video_id, {"ok": False, "message": "本地播放启动失败"})

            threading.Thread(target=_worker, daemon=True).start()
            return json.dumps({"started": True}, ensure_ascii=False)
        except Exception as e:
            print(f"[VideoBridge] 本地播放启动失败: {e}")
            return json.dumps({"ok": False, "message": str(e)[:120]}, ensure_ascii=False)

    @pyqtSlot(str, str, int, str, result=str)
    def playDirect(self, file_path, video_id, start_pos, audio_path=""):
        """★ 解码直渲：ffmpeg 解码帧直接渲染到 QWebEngine（不转码、不依赖 QWebEngine 解码能力）
        返回 "ok" 表示直渲启动成功；返回 "" 表示失败（前端可回退转码/转码流）
        audio_path: 可选分离音频文件
        """
        try:
            if not file_path or not os.path.exists(file_path):
                return ""
            # ★ 目录 → 解析真实媒体文件（与 play() 一致）
            if os.path.isdir(file_path):
                resolved = self._external_player._resolve_dir_to_file(file_path)
                if not resolved:
                    print(f"[VideoBridge] 直渲目录中未找到媒体文件: {file_path}")
                    return ""
                print(f"[VideoBridge] ✓ 直渲已解析媒体文件: {resolved}")
                file_path = resolved
            # ★ 启动解码直渲 + 音频 sounddevice
            #   2026-08 修复：必须先设置 _vid，_start_video() 内部会用
            #   self._vid 查询数据库时长（列表显示正确 → 数据库时长可信）
            self._external_player._vid = video_id or None
            self._external_player._last_vid = video_id or None
            self._external_player._last_audio_src = audio_path or None
            ok = self._external_player._start_video(file_path, int(start_pos or 0))
            if not ok:
                return ""
            # 启动音频（若存在音频路径则用分离音轨，否则用视频文件自身的音轨）
            audio_src = audio_path or file_path
            if os.path.exists(audio_src):
                self._external_player._start_audio(audio_src, int(start_pos or 0))
            # 更新元数据
            try:
                self._external_player._last_src = file_path
                self._external_player._base_pos = float(start_pos or 0)
                self._external_player._pos = float(start_pos or 0)
            except Exception:
                pass
            print(f"[VideoBridge] ⚡ 解码直渲启动: {file_path[:80]}")
            return "ok"
        except Exception as e:
            print(f"[VideoBridge] 解码直渲启动失败: {e}")
            return ""

    @pyqtSlot(int, str, result=str)
    def seekVideo(self, seconds, video_id=""):
        """★ 进度条拖放（异步）：后台线程重启 ffmpeg 从新位置转码。
           完成后回调 seekReady(video_id, data)，data.url 为新流 URL（?seek=秒）。
           返回 {"started": true} 立即释放 GUI 线程（seek_stream 会 sleep 等待重启，
           同步调用此前阻塞 GUI ~1-3s）。"""
        try:
            def _worker():
                new_url = None
                err = None
                try:
                    with self._player_lock:
                        new_url = self._external_player.seek_stream(int(seconds or 0)) or ""
                except Exception as e:
                    err = str(e)[:120]
                if err:
                    self._notify_seek_ready(video_id, {"ok": False, "message": err})
                elif new_url:
                    self._notify_seek_ready(video_id, {"ok": True, "url": new_url})
                else:
                    self._notify_seek_ready(video_id, {"ok": False, "message": "定位失败"})

            threading.Thread(target=_worker, daemon=True).start()
            return json.dumps({"started": True}, ensure_ascii=False)
        except Exception as e:
            print(f"[VideoBridge] seekVideo 失败: {e}")
            return json.dumps({"ok": False, "message": str(e)[:120]}, ensure_ascii=False)

    @pyqtSlot()
    def closeLocalVideo(self):
        """前端调用关闭内嵌播放器（与后台播放 worker 串行化）"""
        try:
            with self._player_lock:
                self._external_player.close_player()
        except Exception as e:
            print(f"[VideoBridge] 关闭播放器失败: {e}")

    @pyqtSlot(str, str)
    def controlExternalPlayer(self, action, value=""):
        """前端/AI 控制外部播放器
        Args:
            action: pause/resume/stop/seek/volume
            value: seek 秒数 或 volume 0-1
        （与后台播放 worker 串行化，避免并发操作 FFmpegDecoder）"""
        try:
            with self._player_lock:
                p = self._external_player
                if action == "pause":
                    p.pause()
                elif action == "resume":
                    p.resume()
                elif action == "stop":
                    p.stop()
                elif action == "seek":
                    p.seek(int(value or 0))
                elif action == "volume":
                    p.set_volume(float(value or 0.8))
        except Exception as e:
            print(f"[VideoBridge] 外部播放控制失败: {e}")

    @pyqtSlot(result=int)
    def getExternalPosition(self):
        """查询外部播放器当前播放位置（秒）"""
        try:
            return self._external_player.current_position()
        except Exception:
            return 0

    @pyqtSlot(result=int)
    def getExternalDuration(self):
        """查询当前视频总时长（秒）"""
        try:
            return self._external_player.get_duration()
        except Exception:
            return 0

    @pyqtSlot(result=bool)
    def isExternalPlaying(self):
        try:
            return self._external_player.is_playing()
        except Exception:
            return False

    # ==========================================
    # AI 事件执行（observer 调用 -> 前端播放器）
    # ==========================================

    def execute_control(self, payload: dict):
        payload_json = json.dumps(payload, ensure_ascii=False)
        self.execute_js(
            "if (window.videoApp && typeof window.videoApp.control === 'function') "
            f"window.videoApp.control({payload_json});"
        )

    def refresh_frontend(self, payload: dict = None):
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        self.execute_js(
            "if (window.videoApp && typeof window.videoApp.refreshList === 'function') "
            f"window.videoApp.refreshList({payload_json});"
        )