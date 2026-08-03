"""
安全插件 - 内容过滤和权限管理
通过 hook 机制订阅消息与工具执行事件：
- message:before_send       入站内容过滤（用户输入）
- message:before_complete   出站内容过滤（AI 回复）
- tool:before_execute       工具权限校验（内建 + MCP 工具统一拦截）
"""
import asyncio
import json
import re
from typing import Any, Dict

from plugins.base import BasePlugin


class SecurityPlugin(BasePlugin):
    """安全插件：内容过滤 + 权限管理"""

    name = "security_plugin"
    version = "1.0.0"
    description = "内容过滤和权限管理"
    author = "孙洋洋"

    # 声明本插件需要 hook 的事件 → 处理方法
    hook_handlers = {
        "message:before_send": "on_before_send",
        "message:before_complete": "on_before_complete",
        "tool:before_execute": "on_before_tool",
    }

    CONFIG_NAME = "security_config.json"

    def __init__(self):
        super().__init__()
        self._cfg: Dict[str, Any] = {}
        self._running = False

    def on_load(self):
        """加载配置（配置文件位于插件目录 security_config.json）"""
        try:
            import json as _json
            import os as _os
            config_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "config", self.CONFIG_NAME)
            if _os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    self._cfg = _json.load(f) or {}
            else:
                self._cfg = {}
        except Exception as e:
            print(f"[SecurityPlugin] [WARN] 加载配置失败: {e}")
            self._cfg = {}

    async def run(self, context=None):
        """插件异步入口 - 加载完成后由 PluginManager 自动异步启动。
        安全插件 run 为轻量常驻循环（可扩展为配置热更新监听）。
        """
        self._running = True
        print("[SecurityPlugin] [START] run() 已启动（内容过滤 + 权限管理）")
        try:
            while self._running and self._enabled:
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            pass
        finally:
            print("[SecurityPlugin] [STOP] run() 已停止")

    def exit(self):
        """插件退出 - 禁用/卸载时调用，清理资源"""
        self._running = False
        self._cfg = {}
        print("[SecurityPlugin] [EXIT] exit() 已调用（资源已清理）")

    # ==========================================
    # Hook 处理方法（统一 JSON 入参 / 返回）
    # ==========================================

    def on_before_send(self, payload_json: str) -> str:
        """入站内容过滤（用户输入）"""
        data = self._parse_payload(payload_json)
        result = self.filter_content(data.get("text", ""), direction="in")
        return json.dumps(result, ensure_ascii=False)

    def on_before_complete(self, payload_json: str) -> str:
        """出站内容过滤（AI 回复）"""
        data = self._parse_payload(payload_json)
        result = self.filter_content(data.get("content", ""), direction="out")
        return json.dumps(result, ensure_ascii=False)

    def on_before_tool(self, payload_json: str) -> str:
        """工具权限校验（内建 + MCP 工具统一拦截）"""
        data = self._parse_payload(payload_json)
        result = self.check_tool_permission(
            data.get("tool_name", ""),
            source=data.get("source", ""),
        )
        return json.dumps(result, ensure_ascii=False)

    # ==========================================
    # 核心业务能力
    # ==========================================

    def filter_content(self, text: str, direction: str = "in") -> Dict[str, Any]:
        """内容过滤（block/mask/warn 三种策略）"""
        if not text:
            return {"blocked": False, "message": "", "masked_text": text}
        cf = self._cfg.get("content_filter", {})
        mode = cf.get("mode", "mask")
        mask_char = cf.get("mask_char", "*")
        patterns = list(cf.get("danger_patterns", []))
        sensitive = cf.get("sensitive_words", [])
        all_words = list(patterns) + list(sensitive)
        hit_word = None
        for word in all_words:
            if word and word in text:
                hit_word = word
                break
        if not hit_word:
            return {"blocked": False, "message": "", "masked_text": text}
        if mode == "block":
            return {
                "blocked": True,
                "message": f"内容包含敏感词/危险指令「{hit_word}」，已阻止发送",
                "masked_text": text,
            }
        if mode == "mask":
            masked = re.sub(re.escape(hit_word), mask_char * len(hit_word), text)
            return {
                "blocked": False,
                "message": f"内容包含敏感词/危险指令「{hit_word}」，已自动打码",
                "masked_text": masked,
            }
        return {
            "blocked": False,
            "message": f"[WARN] 内容包含敏感词/危险指令「{hit_word}」",
            "masked_text": text,
        }

    def check_tool_permission(self, tool_name: str, source: str = "") -> Dict[str, Any]:
        """工具权限校验（黑名单/白名单模式）"""
        if not tool_name:
            return {"allowed": True, "deny_message": ""}
        pm = self._cfg.get("permission", {})
        mode = pm.get("mode", "blacklist")
        blocked = list(pm.get("blocked_tools", []))
        allowed = list(pm.get("allowed_tools", []))
        if mode == "whitelist":
            if tool_name in allowed:
                return {"allowed": True, "deny_message": ""}
            return {
                "allowed": False,
                "deny_message": f"[ERROR] 工具 '{tool_name}' 不在白名单内，已被安全策略禁止"
            }
        if tool_name in blocked:
            return {
                "allowed": False,
                "deny_message": f"[ERROR] 工具 '{tool_name}' 已被安全策略禁止"
            }
        return {"allowed": True, "deny_message": ""}

    # ==========================================
    # 辅助
    # ==========================================

    @staticmethod
    def _parse_payload(payload_json: str) -> dict:
        try:
            return json.loads(payload_json) if payload_json else {}
        except json.JSONDecodeError:
            return {}

    def get_config(self) -> Dict[str, Any]:
        """返回当前生效配置（供前端/调试）"""
        return dict(self._cfg)

    def set_config(self, cfg: Dict[str, Any]) -> bool:
        """更新并保存配置（保存到插件目录 security_config.json）"""
        try:
            import os as _os
            self._cfg = cfg or {}
            config_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "config", self.CONFIG_NAME)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(self._cfg, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"[SecurityPlugin] [ERROR] 保存配置失败: {e}")
            return False
