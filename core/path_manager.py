"""
跨平台路径管理
"""
import os
import sys
from pathlib import Path
from typing import Optional


class PathManager:
    """跨平台路径管理器"""

    def __init__(self, app_name: str = "agent"):
        self.app_name = app_name
        self._root: Optional[Path] = None
        self._data_dir: Optional[Path] = None
        self._config_dir: Optional[Path] = None
        self._log_dir: Optional[Path] = None
        self._cache_dir: Optional[Path] = None

    @property
    def root(self) -> Path:
        """项目根目录"""
        if self._root is None:
            self._root = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return self._root

    @property
    def data_dir(self) -> Path:
        """数据目录"""
        if self._data_dir is None:
            self._data_dir = self.root / "data"
            self._data_dir.mkdir(parents=True, exist_ok=True)
        return self._data_dir

    @property
    def config_dir(self) -> Path:
        """配置目录"""
        if self._config_dir is None:
            self._config_dir = self.root / "config"
            self._config_dir.mkdir(parents=True, exist_ok=True)
        return self._config_dir

    @property
    def log_dir(self) -> Path:
        """日志目录"""
        if self._log_dir is None:
            self._log_dir = self.root / "logs"
            self._log_dir.mkdir(parents=True, exist_ok=True)
        return self._log_dir

    @property
    def cache_dir(self) -> Path:
        """缓存目录"""
        if self._cache_dir is None:
            self._cache_dir = self.data_dir / "cache"
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        return self._cache_dir

    def ensure_dir(self, *parts: str) -> Path:
        """确保目录存在并返回路径"""
        path = self.root.joinpath(*parts)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_path(self, *parts: str) -> Path:
        """获取项目内路径"""
        return self.root.joinpath(*parts)

    def get_user_data_dir(self) -> Path:
        """获取用户数据目录（平台特定）"""
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        path = base / self.app_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_user_config_dir(self) -> Path:
        """获取用户配置目录（平台特定）"""
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Preferences"
        else:
            base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        path = base / self.app_name
        path.mkdir(parents=True, exist_ok=True)
        return path


_path_manager = PathManager()


def get_path_manager() -> PathManager:
    """获取全局路径管理器实例"""
    return _path_manager