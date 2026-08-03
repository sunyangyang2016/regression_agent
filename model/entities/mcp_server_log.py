"""
MCP 服务器日志实体 — MCPServerLog
对应数据库表 mcp_server_logs 的业务对象
"""
from model.entities.base import BaseEntity


class MCPServerLog(BaseEntity):
    """MCP 服务器操作日志实体"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.server_id: str = kwargs.get("server_id", "")
        self.action: str = kwargs.get("action", "")          # install/uninstall/start/stop/restart/config
        self.status: str = kwargs.get("status", "start")      # start/success/failed
        self.log_content: str = kwargs.get("log_content", "")
        self.log_file: str = kwargs.get("log_file", "")
        self.duration: float = kwargs.get("duration")
        self.server_name: str = kwargs.get("server_name", "")
        self.repo_url: str = kwargs.get("repo_url", "")
        self.market_id: str = kwargs.get("market_id", "")     # 市场项 ID（mcp-{issue_number}），非市场安装为空

    def to_dict(self, for_db: bool = False) -> dict:
        """转 dict（可选：仅含数据库字段）"""
        data = super().to_dict()
        if for_db:
            # 仅保留 mcp_server_logs 表字段
            return {
                "id": data.get("id"),
                "server_id": data.get("server_id"),
                "action": data.get("action"),
                "status": data.get("status"),
                "log_content": data.get("log_content"),
                "log_file": data.get("log_file"),
                "duration": data.get("duration"),
                "server_name": data.get("server_name"),
                "repo_url": data.get("repo_url"),
                "market_id": data.get("market_id"),
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
            }
        return data