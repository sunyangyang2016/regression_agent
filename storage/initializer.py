"""
初始化器 — 数据库初始化与状态检查

负责:
- 应用启动时的数据库全局初始化（创建连接、确保建表）
- 检查数据库 schema 版本（PRAGMA user_version）
- 检查数据表是否存在
- 提供数据库路径

注意: 数据迁移不在此类中执行，统一由 scripts/migrate_db.py 手动运行。
"""
import os


class DatabaseInitializer:
    """数据库初始化管理器"""

    # 当前数据库 Schema 版本（与软件版本对应，见 scripts/migrate_db.py）
    SCHEMA_VERSION = 1

    @staticmethod
    def initialize() -> dict:
        """数据库全局初始化（应用启动时调用）

        集中封装初始化流程：
        1. 创建数据库连接（sqlite3.connect 自动创建 agent.db 文件）
        2. 确保 4 张数据表存在（ensure_tables，幂等建表，不迁移数据）
        3. 返回初始化报告

        返回:
            {"database_path", "tables", "schema_version", "success"}
        """
        from storage.database import Database

        # 创建 Database 单例（内部完成：连接 + ensure_tables）
        db = Database()

        report = {
            "database_path": db.db_path,
            "tables": [],
            "schema_version": 0,
            "success": False,
        }

        try:
            # 收集已存在的表（期望的 4 张表）
            for table_name in Database.TABLES:
                if db.table_exists(table_name):
                    report["tables"].append(table_name)

            report["schema_version"] = db.query_value("PRAGMA user_version") or 0
            report["success"] = len(report["tables"]) == len(Database.TABLES)
            return report
        except Exception as e:
            print(f"[DatabaseInitializer] 数据库初始化失败: {e}")
            report["error"] = str(e)
            return report

    @staticmethod
    def check_database() -> dict:
        """检查数据库状态，返回报告（不修改数据库）"""
        from storage.database import Database

        report = {"tables": [], "schema_version": 0, "success": False, "exists": False}

        try:
            db = Database()
            report["exists"] = os.path.exists(db.db_path)

            # 检查所有期望的表是否存在
            for table_name in Database.TABLES:
                if db.table_exists(table_name):
                    report["tables"].append(table_name)

            # 读取 schema 版本
            report["schema_version"] = DatabaseInitializer.get_schema_version()

            report["success"] = len(report["tables"]) == len(Database.TABLES)
            report["needs_migration"] = report["schema_version"] < DatabaseInitializer.SCHEMA_VERSION
            return report

        except Exception as e:
            print(f"[DatabaseInitializer] 数据库检查失败: {e}")
            report["error"] = str(e)
            return report

    @staticmethod
    def get_schema_version() -> int:
        """获取当前数据库的 schema 版本号"""
        from storage.database import Database
        return Database().query_value("PRAGMA user_version") or 0

    @staticmethod
    def get_database_path() -> str:
        """获取数据库文件完整路径"""
        from storage.database import Database
        return Database().db_path