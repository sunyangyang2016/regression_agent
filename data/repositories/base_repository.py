"""
Repository 基类 — 使用 SQLite（agent.db）持久化
"""
import sqlite3
import json
from typing import Dict, List, Optional, TypeVar, Generic, Type
from datetime import datetime
from model.entities.base import BaseModel
from data.database import Database

T = TypeVar("T", bound=BaseModel)


class BaseRepository(Generic[T]):
    """泛型仓库基类（SQLite 持久化）"""

    def __init__(self, model_class: Type[T]):
        self._model_class = model_class
        self._table_name = model_class.__name__.lower()
        self._db = Database()
        self._ensure_table()

    # ==========================================
    # 表管理
    # ==========================================

    def _ensure_table(self):
        """自动创建表（如果不存在）"""
        conn = self._db.connection
        # 用 JSON 列存储所有字段，避免动态建列
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self._table_name} (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        conn.commit()

    def _to_dict(self, item: T) -> dict:
        """将实体转为可序列化的字典"""
        d = {}
        for key, value in item.__dict__.items():
            if isinstance(value, datetime):
                d[key] = value.isoformat()
            else:
                d[key] = value
        return d

    def _from_dict(self, data: dict) -> T:
        """从字典还原实体"""
        for key, value in data.items():
            if isinstance(value, str) and key in ('created_at', 'updated_at'):
                try:
                    data[key] = datetime.fromisoformat(value)
                except (ValueError, TypeError):
                    pass
        return self._model_class(**data)

    # ==========================================
    # CRUD
    # ==========================================

    def save(self, item: T) -> bool:
        """保存实体到 SQLite"""
        conn = self._db.connection
        data = json.dumps(self._to_dict(item), ensure_ascii=False)
        conn.execute(f"""
            INSERT OR REPLACE INTO {self._table_name} (id, data, created_at, updated_at)
            VALUES (?, ?, ?, ?)
        """, (item.id, data, str(item.created_at) if hasattr(item, 'created_at') else None,
              str(item.updated_at) if hasattr(item, 'updated_at') else None))
        conn.commit()
        return True

    def get(self, item_id: str) -> Optional[T]:
        """根据 ID 获取实体"""
        conn = self._db.connection
        row = conn.execute(
            f"SELECT data FROM {self._table_name} WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None:
            return None
        return self._from_dict(json.loads(row[0]))

    def get_all(self) -> List[T]:
        """获取所有实体"""
        conn = self._db.connection
        rows = conn.execute(f"SELECT data FROM {self._table_name}").fetchall()
        return [self._from_dict(json.loads(row[0])) for row in rows]

    def delete(self, item_id: str) -> bool:
        """删除实体"""
        conn = self._db.connection
        conn.execute(f"DELETE FROM {self._table_name} WHERE id = ?", (item_id,))
        conn.commit()
        return True

    def count(self) -> int:
        """实体数量"""
        conn = self._db.connection
        row = conn.execute(f"SELECT COUNT(*) FROM {self._table_name}").fetchone()
        return row[0] if row else 0

    def clear(self):
        """清空表"""
        conn = self._db.connection
        conn.execute(f"DELETE FROM {self._table_name}")
        conn.commit()

    def find(self, **filters) -> List[T]:
        """按条件查找（遍历匹配，适用于小数据集）"""
        all_items = self.get_all()
        results = []
        for item in all_items:
            match = True
            for key, value in filters.items():
                if getattr(item, key, None) != value:
                    match = False
                    break
            if match:
                results.append(item)
        return results