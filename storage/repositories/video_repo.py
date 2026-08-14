"""
Video Repository — 经典 Repository 模式
持有 db（Database 连接池），使用原生 SQL 访问 video_library 表
供 Python Skill（主进程）与 video_plugin（主进程）共同访问
"""
import sqlite3
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from storage.database import Database


class VideoRepository:
    """视频数据仓库（持有 db + 原生 SQL）"""

    TABLE = "video_library"  # 表名

    def __init__(self):
        self.db = Database()  # 直接持有数据库（连接池）
        self._ensure_audio_path_column()
        self._ensure_new_columns()

    def _ensure_audio_path_column(self):
        """确保 video_library 有 audio_path 列（旧库自动 ALTER 补列）"""
        try:
            cols = self.db.query("PRAGMA table_info(video_library)")
            exists = any(c.get("name") == "audio_path" for c in cols)
            if not exists:
                self.db.execute("ALTER TABLE video_library ADD COLUMN audio_path TEXT")
                print("[VideoRepository] 已补充 video_library.audio_path 列")
        except Exception as e:
            print(f"[VideoRepository] 检查/补充 audio_path 列失败: {e}")

    def _ensure_new_columns(self):
        """确保 video_library 有整套搜索相关列 + video_id 唯一索引（旧库自动 ALTER 补列）"""
        try:
            cols = self.db.query("PRAGMA table_info(video_library)")
            names = {c.get("name") for c in cols}
            for col, ddl in (("video_id", "TEXT"), ("episode_index", "INTEGER"),
                             ("series_id", "TEXT"), ("series_title", "TEXT")):
                if col not in names:
                    self.db.execute(f"ALTER TABLE video_library ADD COLUMN {col} {ddl}")
                    print(f"[VideoRepository] 已补充 video_library.{col} 列")
            # 入库判重兜底：B站 BV号 唯一（老行 video_id 为 NULL，SQLite UNIQUE 允许多个 NULL）
            self.db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_vlib_video_id "
                "ON video_library (video_id)"
            )
        except Exception as e:
            print(f"[VideoRepository] 检查/补充整套搜索列失败: {e}")

    # ==========================================
    # 查询
    # ==========================================

    def get_all(self, subject=None, grade=None, source=None, status=None,
                keyword=None, limit=100, offset=0) -> list:
        """获取视频列表（支持筛选 + 关键词搜索 + 分页）"""
        sql = f"SELECT * FROM {self.TABLE}"
        where, params = [], []
        if subject:
            where.append("subject = ?")
            params.append(subject)
        if grade:
            where.append("grade = ?")
            params.append(grade)
        if source:
            where.append("source = ?")
            params.append(source)
        if status:
            where.append("status = ?")
            params.append(status)
        if keyword:
            where.append("(title LIKE ? OR description LIKE ?)")
            params += [f"%{keyword}%", f"%{keyword}%"]
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        rows = self.db.query(sql, params)
        return [self._row_to_dict(r) for r in rows]

    def get_by_id(self, video_id: str) -> dict:
        """根据 ID 获取视频"""
        row = self.db.query_one(
            f"SELECT * FROM {self.TABLE} WHERE id = ?", (video_id,)
        )
        return self._row_to_dict(row) if row else {}

    def count(self, **filters) -> int:
        """获取视频数量（支持筛选）"""
        where, params = [], []
        for k, v in filters.items():
            if v is not None and v != "":
                where.append(f"{k} = ?")
                params.append(v)
        sql = f"SELECT COUNT(*) FROM {self.TABLE}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        return self.db.query_value(sql, params) or 0

    def get_stats(self) -> dict:
        """获取视频库统计信息"""
        return {
            "total": self.count(),
            "online": self.count(status="online"),
            "downloading": self.count(status="downloading"),
            "downloaded": self.count(status="downloaded"),
            "failed": self.count(status="failed"),
        }

    # ==========================================
    # 写入
    # ==========================================

    def add(self, video: dict) -> str:
        """新增视频，返回生成的 ID。

        ★ 2026-08 幂等去重：若 video_id（平台ID，如 B站 BV号）已存在则直接返回已有行 ID，
        不重复插入。video_id/series_id 归一化为 None（不存空串，否则 UNIQUE 索引把 '' 当真值冲突）。
        """
        video_id = video.get("id") or str(uuid.uuid4())
        now = datetime.now().isoformat()
        bvid = (video.get("video_id") or "").strip() or None
        if bvid:
            existing = self.db.query_one(
                f"SELECT id FROM {self.TABLE} WHERE video_id = ?", (bvid,)
            )
            if existing:
                return existing["id"]
        try:
            self.db.execute(
                f"INSERT INTO {self.TABLE} (id, title, subject, grade, source, "
                f"description, page_url, play_url, local_path, thumbnail, "
                f"duration, resolution, width, height, quality, file_size, "
                f"file_format, fps, status, download_progress, play_count, "
                f"last_played_at, is_favorite, last_position, video_id, "
                f"episode_index, series_id, series_title, created_at, updated_at) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                f"?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (video_id, video.get("title"), video.get("subject"),
                 video.get("grade"), video.get("source"), video.get("description"),
                 video.get("page_url"), video.get("play_url"), video.get("local_path"),
                 video.get("thumbnail"), video.get("duration"),
                 video.get("resolution"), video.get("width"), video.get("height"),
                 video.get("quality"), video.get("file_size"),
                 video.get("file_format"), video.get("fps"),
                 video.get("status") or "online", video.get("download_progress") or 0,
                 video.get("play_count") or 0, video.get("last_played_at"),
                 video.get("is_favorite") or 0, video.get("last_position") or 0,
                 bvid, video.get("episode_index"),
                 (video.get("series_id") or "").strip() or None,
                 video.get("series_title"),
                 now, now),
            )
        except sqlite3.IntegrityError:
            # 并发/批量内重复 video_id 触发唯一索引 → 回查返回已有 ID，幂等不抛
            if bvid:
                existing = self.db.query_one(
                    f"SELECT id FROM {self.TABLE} WHERE video_id = ?", (bvid,)
                )
                if existing:
                    return existing["id"]
            raise
        return video_id

    def add_many(self, videos: list) -> dict:
        """批量新增视频（★ 2026-08 判重优先级：video_id → page_url → title+source）

        返回 {"added": 新增条数, "skipped": 已存在被跳过的条数}。
        ★ 采纳旧行：命中重复但旧行 video_id 为空（迁移前遗留行）时，
          用新数据补全 video_id/episode_index/series_id/series_title ——
          重搜即自动修复，无需回填迁移。
        """
        added = 0
        skipped = 0
        for v in videos:
            if not v.get("title"):
                continue
            bvid = (v.get("video_id") or "").strip()
            purl = (v.get("page_url") or "").strip()
            title = (v.get("title") or "").strip()
            src = (v.get("source") or "").strip()
            existing = None
            if bvid:
                existing = self.db.query_one(
                    f"SELECT id, video_id FROM {self.TABLE} WHERE video_id = ?", (bvid,))
            if not existing and purl:
                existing = self.db.query_one(
                    f"SELECT id, video_id FROM {self.TABLE} WHERE page_url = ?", (purl,))
            if not existing and title and src:
                existing = self.db.query_one(
                    f"SELECT id, video_id FROM {self.TABLE} WHERE title = ? AND source = ?",
                    (title, src))
            if existing:
                # 采纳旧行：旧行无 video_id → 用新数据补全系列元数据
                if not existing.get("video_id"):
                    enrich = {}
                    if bvid:
                        enrich["video_id"] = bvid
                    if v.get("episode_index") is not None:
                        enrich["episode_index"] = v.get("episode_index")
                    sid = (v.get("series_id") or "").strip() or None
                    if sid:
                        enrich["series_id"] = sid
                    if v.get("series_title"):
                        enrich["series_title"] = v.get("series_title")
                    if enrich:
                        self.update(existing["id"], enrich)
                skipped += 1
                continue
            self.add(v)
            added += 1
        return {"added": added, "skipped": skipped}

    def update(self, video_id: str, fields: dict):
        """更新视频字段（只更新传入的字段）"""
        if not fields:
            return
        fields["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join([f"{k} = ?" for k in fields.keys()])
        params = list(fields.values()) + [video_id]
        self.db.execute(
            f"UPDATE {self.TABLE} SET {set_clause} WHERE id = ?", params
        )

    def upsert(self, video: dict) -> str:
        """插入或更新（同 id 则更新，否则新增），返回 ID"""
        video_id = video.get("id")
        if video_id and self.get_by_id(video_id):
            self.update(video_id, video)
            return video_id
        return self.add(video)

    # ==========================================
    # 状态管理
    # ==========================================

    def set_status(self, video_id: str, status: str, **extra):
        """设置视频状态（online/downloading/downloaded/failed）"""
        fields = {"status": status}
        fields.update(extra)
        self.update(video_id, fields)

    def set_download_progress(self, video_id: str, progress: int):
        """更新下载进度（0-100）"""
        self.update(video_id, {"download_progress": progress})

    def mark_downloaded(self, video_id: str, local_path: str,
                        file_size: int, file_format: str = None,
                        audio_path: str = None):
        """标记视频已下载（audio_path 为分离的音频文件路径，可选）"""
        fields = {
            "status": "downloaded",
            "local_path": local_path,
            "file_size": file_size,
            "file_format": file_format,
            "download_progress": 100,
        }
        if audio_path:
            fields["audio_path"] = audio_path
        self.update(video_id, fields)

    def increment_play_count(self, video_id: str):
        """播放次数 +1，更新最近播放时间"""
        self.db.execute(
            f"UPDATE {self.TABLE} SET play_count = play_count + 1, "
            f"last_played_at = ? WHERE id = ?",
            (datetime.now().isoformat(), video_id),
        )

    def toggle_favorite(self, video_id: str) -> bool:
        """切换收藏状态，返回新状态"""
        video = self.get_by_id(video_id)
        if not video:
            return False
        new_val = 0 if video.get("is_favorite") else 1
        self.update(video_id, {"is_favorite": new_val})
        return bool(new_val)

    # ==========================================
    # 播放进度（断点续播）
    # ==========================================

    def update_last_position(self, video_id: str, position: int):
        """★ 更新播放位置（每 5 秒保存一次）"""
        self.update(video_id, {
            "last_position": int(position or 0),
            "last_played_at": datetime.now().isoformat(),
        })

    def get_playback_position(self, video_id: str) -> int:
        """★ 获取上次播放位置（秒），前端续播用"""
        video = self.get_by_id(video_id)
        return video.get("last_position") or 0

    def get_playback_state(self, video_id: str) -> dict:
        """★ 获取完整播放状态（AI get_state 用）"""
        video = self.get_by_id(video_id)
        if not video:
            return {}
        return {
            "video_id": video_id,
            "title": video.get("title"),
            "position": video.get("last_position") or 0,
            "duration": video.get("duration") or 0,
            "play_count": video.get("play_count") or 0,
            "last_played_at": video.get("last_played_at"),
        }

    # ==========================================
    # 删除
    # ==========================================

    def delete(self, video_id: str):
        """删除视频记录"""
        self.db.execute(f"DELETE FROM {self.TABLE} WHERE id = ?", (video_id,))

    def clear(self):
        """清空所有视频记录"""
        self.db.execute(f"DELETE FROM {self.TABLE}")

    # ==========================================
    # 工具方法
    # ==========================================

    def _normalize(self, video: dict) -> Dict[str, Any]:
        """将前端字段名（camelCase）转为数据库字段名（snake_case）"""
        mapping = {
            "pageUrl": "page_url",
            "playUrl": "play_url",
            "localPath": "local_path",
            "audioPath": "audio_path",
            "fileSize": "file_size",
            "fileFormat": "file_format",
            "downloadProgress": "download_progress",
            "playCount": "play_count",
            "lastPlayedAt": "last_played_at",
            "isFavorite": "is_favorite",
            "lastPosition": "last_position",
            "videoId": "video_id",
            "episodeIndex": "episode_index",
            "seriesId": "series_id",
            "seriesTitle": "series_title",
            "createdAt": "created_at",
            "updatedAt": "updated_at",
        }
        table_fields = {
            "id", "title", "subject", "grade", "source", "description",
            "page_url", "play_url", "local_path", "audio_path", "thumbnail",
            "duration", "resolution", "width", "height", "quality", "file_size",
            "file_format", "fps", "status", "download_progress", "play_count",
            "last_played_at", "is_favorite", "last_position",
            "video_id", "episode_index", "series_id", "series_title",
            "created_at", "updated_at",
        }
        data = {}
        for k, v in video.items():
            db_key = mapping.get(k, k)
            if db_key in table_fields:
                data[db_key] = v
        return data

    def _row_to_dict(self, row: dict) -> dict:
        """将数据库行转为前端字段名格式（camelCase）"""
        return {
            "id": row.get("id"),
            "title": row.get("title"),
            "subject": row.get("subject"),
            "grade": row.get("grade"),
            "source": row.get("source"),
            "description": row.get("description"),
            "pageUrl": row.get("page_url"),
            "playUrl": row.get("play_url"),
            "localPath": row.get("local_path"),
            "audioPath": row.get("audio_path"),
            "thumbnail": row.get("thumbnail"),
            "duration": row.get("duration"),
            "resolution": row.get("resolution"),
            "width": row.get("width"),
            "height": row.get("height"),
            "quality": row.get("quality"),
            "fileSize": row.get("file_size"),
            "fileFormat": row.get("file_format"),
            "fps": row.get("fps"),
            "status": row.get("status"),
            "downloadProgress": row.get("download_progress"),
            "playCount": row.get("play_count"),
            "lastPlayedAt": row.get("last_played_at"),
            "isFavorite": bool(row.get("is_favorite")),
            "lastPosition": row.get("last_position") or 0,
            "videoId": row.get("video_id"),
            "episodeIndex": row.get("episode_index"),
            "seriesId": row.get("series_id"),
            "seriesTitle": row.get("series_title"),
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        }