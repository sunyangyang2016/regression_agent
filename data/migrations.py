"""
数据库迁移管理
"""
from typing import List


class Migration:
    """单个迁移"""
    def __init__(self, version: int, description: str, sql: str):
        self.version = version
        self.description = description
        self.sql = sql


class Migrator:
    """迁移执行器"""
    def __init__(self, db):
        self.db = db
    
    def migrate(self):
        """执行所有待执行的迁移"""
        pass