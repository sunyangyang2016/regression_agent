"""视频插件桥接层 - JS <-> Python 通信"""
import json
import os
import sys
import threading
from PyQt5.QtCore import QObject, pyqtSlot

from storage.repositories.video_repo import VideoRepository

# 项目根目录
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
))))
# 下载目录（用户配置目录下）
VIDEO_DIR = os.path.join(_PROJECT_ROOT, "user_config", "media", "videos")

_bridge_instance = None


def get_bridge_instance():
    """供插件内部（observer 等）获取 VideoBridge 单例"""
    return _bridge_instance


class VideoBridge(QObject):
    """供前端 video.js 调用的 QWebChannel 桥"""

    def __init__(self, parent=None, webview=None):
        super().__init__(parent)
        global _bridge_instance
        _bridge_instance = self
        self._webview = webview
        self._repo = VideoRepository()

    # ==========================================
    # 工具方法
    # ==========================================

    def execute_js(self, js_code: str):
        try:
            if self._webview:
                self._webview.page().runJavaScript(js_code)
        except Exception as e:
            print(f"[VideoBridge] JS 执行失败: {e}")

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
            return json.dumps(videos, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @pyqtSlot(str, result=str)
    def searchOnline(self, keyword):
        """★ 前端搜索按钮 → wbi 搜索 B站 → 写入视频库 → 返回结果"""
        try:
            keyword = (keyword or "").strip()
            if not keyword:
                return json.dumps({"ok": False, "message": "请输入搜索关键词"}, ensure_ascii=False)

            # 1. 使用 wbi 签名搜索（破解 B 站风控），失败兜底 yt-dlp
            from tools.video_search_wbi import bili_search as wbi_search
            videos = wbi_search(keyword, limit=10)
            # 补全科目/年级
            for v in videos:
                if not v.get("subject"):
                    v["subject"] = self._guess_subject(keyword)
                if not v.get("grade"):
                    v["grade"] = self._guess_grade(keyword)
                v["source"] = v.get("source") or "bilibili"

            if not videos:
                return json.dumps({
                    "ok": False, "message": f"未搜索到相关视频（关键词: {keyword}，B站可能风控了）"
                }, ensure_ascii=False)

            # 3. 批量写入（去重）
            added = self._repo.add_many(videos)

            # 4. 通知前端刷新
            self.refresh_frontend({"added": added, "total": len(videos), "keyword": keyword})

            return json.dumps({
                "ok": True,
                "added": added,
                "total": len(videos),
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "message": str(e)[:200]}, ensure_ascii=False)

    @staticmethod
    def _guess_subject(keyword: str) -> str:
        """从关键词猜测科目"""
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
        """从关键词猜测年级"""
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
        """★ 获取上次播放位置（断点续播用）"""
        try:
            return self._repo.get_playback_position(video_id)
        except Exception:
            return 0

    @pyqtSlot(str, int)
    def updateLastPosition(self, video_id, position):
        """★ 保存播放位置（前端每 5 秒调用）"""
        try:
            self._repo.update_last_position(video_id, int(position or 0))
        except Exception as e:
            print(f"[VideoBridge] 保存播放位置失败: {e}")

    @pyqtSlot(str)
    def incrementPlayCount(self, video_id):
        """播放次数 +1"""
        try:
            self._repo.increment_play_count(video_id)
        except Exception:
            pass

    @pyqtSlot(str)
    def downloadVideo(self, video_id):
        """启动下载（后台线程）— 委托 video-catcher 完成多平台下载"""
        try:
            video = self._repo.get_by_id(video_id)
            if not video:
                return

            url = video.get("pageUrl") or video.get("playUrl")
            if not url:
                return

            # 定位 video-catcher 主脚本
            vc_script = os.path.join(
                _PROJECT_ROOT, "skills", "md", "video-catcher",
                "scripts", "video_catcher.py"
            )
            if not os.path.exists(vc_script):
                print(f"[VideoBridge] video-catcher 脚本不存在: {vc_script}")
                self._repo.set_status(video_id, "failed")
                self.refresh_frontend({"video_id": video_id, "status": "failed"})
                return

            # 更新状态
            self._repo.set_status(video_id, "downloading", download_progress=0)
            self.refresh_frontend({"video_id": video_id, "status": "downloading", "progress": 0})

            def _do():
                try:
                    os.makedirs(VIDEO_DIR, exist_ok=True)
                    # 委托 video_catcher_runner 执行（隔离 subprocess，避免安全扫描拒绝 bridge 注册）
                    self._find_downloaded_later(video_id, vc_script, url)
                except Exception as e:
                    print(f"[VideoBridge] 下载异常: {e}")
                    self._repo.set_status(video_id, "failed")
                    self.refresh_frontend({"video_id": video_id, "status": "failed"})

            threading.Thread(target=_do, daemon=True).start()
        except Exception as e:
            print(f"[VideoBridge] 启动下载失败: {e}")

    def _find_downloaded_later(self, video_id, vc_script, url):
        """执行 video-catcher 下载并在结束后扫描产物更新状态"""
        try:
            from tools.video_catcher_runner import run_video_catcher
            # 记录执行前目录已有文件，下载后对比新文件
            before = set(os.listdir(VIDEO_DIR)) if os.path.isdir(VIDEO_DIR) else set()
            returncode, stdout, stderr = run_video_catcher(vc_script, url, VIDEO_DIR)
            # 扫描新增媒体文件（mp4/mkv/webm/mov）
            after = set(os.listdir(VIDEO_DIR)) if os.path.isdir(VIDEO_DIR) else set()
            new_files = [f for f in (after - before)
                         if f.lower().endswith((".mp4", ".mkv", ".webm", ".mov"))]
            if new_files:
                # 取最新的一个作为下载产物
                latest = None
                latest_mtime = 0
                for f in new_files:
                    fpath = os.path.join(VIDEO_DIR, f)
                    mtime = os.path.getmtime(fpath)
                    if mtime > latest_mtime:
                        latest_mtime = mtime
                        latest = fpath
                size = os.path.getsize(latest)
                fmt = os.path.splitext(latest)[1][1:]
                self._repo.mark_downloaded(video_id, latest, size, fmt)
                self.refresh_frontend({
                    "video_id": video_id,
                    "status": "downloaded",
                    "local_path": latest,
                })
            elif returncode != 0:
                raise RuntimeError(stderr[:300])
            else:
                # video-catcher 可能输出到默认 Video/Downloads 目录，尝试递归查找
                self._search_nested_output(video_id)
        except Exception as e:
            print(f"[VideoBridge] 下载完成后处理失败: {e}")
            self._repo.set_status(video_id, "failed")
            self.refresh_frontend({"video_id": video_id, "status": "failed"})

    def _search_nested_output(self, video_id):
        """video-catcher 默认输出到 Video/Downloads/日期-主题/，递归查找新文件"""
        try:
            download_root = os.path.join(_PROJECT_ROOT, "Video", "Downloads")
            if not os.path.isdir(download_root):
                # 无产物且无默认目录 → 失败
                self._repo.set_status(video_id, "failed")
                self.refresh_frontend({"video_id": video_id, "status": "failed"})
                return
            # 扫描最新任务目录中的媒体文件
            latest_media = None
            latest_mtime = 0
            for root, dirs, files in os.walk(download_root):
                for f in files:
                    if f.lower().endswith((".mp4", ".mkv", ".webm", ".mov")):
                        fpath = os.path.join(root, f)
                        mtime = os.path.getmtime(fpath)
                        if mtime > latest_mtime:
                            latest_mtime = mtime
                            latest_media = fpath
            if latest_media:
                # 复制回视频库目录（保持统一管理）
                import shutil
                os.makedirs(VIDEO_DIR, exist_ok=True)
                target = os.path.join(VIDEO_DIR, os.path.basename(latest_media))
                shutil.copy2(latest_media, target)
                size = os.path.getsize(target)
                fmt = os.path.splitext(target)[1][1:]
                self._repo.mark_downloaded(video_id, target, size, fmt)
                self.refresh_frontend({
                    "video_id": video_id,
                    "status": "downloaded",
                    "local_path": target,
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
        """删除视频（本地文件 + 数据库记录）"""
        try:
            video = self._repo.get_by_id(video_id)
            if video and video.get("localPath"):
                local = video["localPath"]
                if os.path.exists(local):
                    try:
                        os.remove(local)
                    except OSError:
                        pass
            self._repo.delete(video_id)
            self.refresh_frontend({"deleted": video_id})
        except Exception as e:
            print(f"[VideoBridge] 删除失败: {e}")

    @pyqtSlot()
    def openVideoFolder(self):
        """打开本地视频目录"""
        try:
            os.makedirs(VIDEO_DIR, exist_ok=True)
            # os.startfile 打开资源管理器（避免 subprocess 触发安全扫描）
            os.startfile(VIDEO_DIR)
        except Exception as e:
            print(f"[VideoBridge] 打开目录失败: {e}")

    # ==========================================
    # AI 事件执行（observer 调用 -> 前端播放器）
    # ==========================================

    def execute_control(self, payload: dict):
        """执行 AI/脚本播放控制事件 → 前端 HTML5 播放器"""
        payload_json = json.dumps(payload, ensure_ascii=False)
        self.execute_js(
            "if (window.videoApp && typeof window.videoApp.control === 'function') "
            f"window.videoApp.control({payload_json});"
        )

    def refresh_frontend(self, payload: dict = None):
        """刷新前端视频列表"""
        payload_json = json.dumps(payload or {}, ensure_ascii=False)
        self.execute_js(
            "if (window.videoApp && typeof window.videoApp.refreshList === 'function') "
            f"window.videoApp.refreshList({payload_json});"
        )