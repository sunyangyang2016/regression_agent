"""
ModelBridge - 模型配置桥接
处理模型配置、AI 重连等配置相关的前后端交互
"""
import json
import os
from PyQt5.QtCore import pyqtSlot

from .base import BridgeBase
from config.user_config import USER_DIR, resolve_config_path, load_agent_info


class ModelBridge(BridgeBase):
    """模型配置桥接 — 模型/系统配置管理"""

    def _get_model_config(self):
        if self.app_controller and hasattr(self.app_controller, 'model_config'):
            return self.app_controller.model_config
        return None

    def _get_user_config_dir(self):
        # 用户配置写入目录：user_config/user/（默认配置在 defaults/ 下，只读不修改）
        return USER_DIR

    @pyqtSlot(str)
    def saveConfig(self, config_json):
        """保存模型配置到后端 ConfigManager 并持久化到 config.yaml"""
        try:
            cfg = json.loads(config_json)
            mgr = self._get_model_config()
            if mgr:
                mgr.set("api", "provider", cfg.get("provider", "deepseek"))
                mgr.set("api", "model", cfg.get("model", "deepseek-chat"))
                mgr.set("chat", "temperature", cfg.get("temperature", 0.7))
                mgr.set("chat", "max_tokens", cfg.get("maxTokens", 2000))
                mgr.set("api", "api_key", cfg.get("apiKey", ""))
                mgr.set("api", "base_url", cfg.get("baseUrl", ""))
                mgr.save_config()
                print(f"[ModelBridge] ✅ 配置已保存: {cfg.get('provider')}/{cfg.get('model')}")
                return True
        except Exception as e:
            print(f"[ModelBridge] ❌ 保存失败: {e}")
        return False

    @pyqtSlot(result=str)
    def getConfig(self):
        """从后端 ConfigManager 读取配置"""
        mgr = self._get_model_config()
        if not mgr:
            return json.dumps({
                "provider": "deepseek",
                "model": "deepseek-chat",
                "temperature": 0.7,
                "maxTokens": 2000
            })
        cfg = {
            "provider": mgr.get("api", "provider") or "deepseek",
            "model": mgr.get("api", "model") or "deepseek-chat",
            "temperature": mgr.get("chat", "temperature") or 0.7,
            "maxTokens": mgr.get("chat", "max_tokens") or 2000
        }
        return json.dumps(cfg)

    @pyqtSlot(result=str)
    def getModels(self):
        """读取模型列表：优先 user_config/user/models.json，回退 defaults/models.json"""
        try:
            path = resolve_config_path("models.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                models = data.get("models", [])
                source = "user" if path.startswith(USER_DIR) else "defaults"
                print(f"[ModelBridge] ✅ 已加载 {len(models)} 个模型（来源: {source}）")
                return json.dumps(models, ensure_ascii=False)
            else:
                print(f"[ModelBridge] ⚠️ models.json 未找到: {path}")
        except Exception as e:
            print(f"[ModelBridge] ❌ 读取 models.json 失败: {e}")
        return json.dumps([])

    @pyqtSlot(str)
    def saveModels(self, models_json):
        """保存模型列表到 user_config/user/models.json（defaults 目录不被修改）"""
        try:
            models = json.loads(models_json)
            if not isinstance(models, list):
                raise ValueError("数据必须是数组格式")
            path = os.path.join(self._get_user_config_dir(), "models.json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"models": models}, f, ensure_ascii=False, indent=4)
            print(f"[ModelBridge] ✅ 已保存 {len(models)} 个模型 → {path}")
            return True
        except Exception as e:
            print(f"[ModelBridge] ❌ 保存 models.json 失败: {e}")
            return False

    def _reconnect_ai(self):
        """热切换 AI 配置"""
        try:
            if not (self.app_controller and hasattr(self.app_controller, 'ai_controller')):
                return
            ai_model = self.app_controller.ai_controller

            if hasattr(self.app_controller, 'main_bridge') and self.app_controller.main_bridge:
                bridge = self.app_controller.main_bridge
                bridge.execute_js("showToast('🔄 切换模型配置...', 'info');")
                bridge.execute_js("""
                    if(window.chatApp){
                        window.chatApp.isProcessing=false;
                        window.chatApp._currentAssistantId=null;
                        var btn=document.getElementById('sendBtn');
                        if(btn)btn.disabled=false;
                    }
                """)

            if hasattr(self.app_controller, 'chat_controller'):
                cc = self.app_controller.chat_controller
                cc.set_processing.emit(False)
                cc.complete_message.emit("")

            success, msg = ai_model.reconnect()
            print(f"[ModelBridge] 🔄 AI 重连: {'✅ ' + msg if success else '❌ ' + msg}")

            if hasattr(self.app_controller, 'main_bridge') and self.app_controller.main_bridge:
                bridge = self.app_controller.main_bridge
                if success:
                    bridge.execute_js("showToast('✅ AI 客户端已连接', 'success');")
                else:
                    bridge.execute_js(f"showToast('❌ {msg}', 'error');")
        except Exception as e:
            print(f"[ModelBridge] ❌ AI 重连失败: {e}")

    @pyqtSlot()
    def reconnectAI(self):
        """前端手动触发的 AI 重连"""
        self._reconnect_ai()

    @pyqtSlot(str, result=str)
    def getUserConfig(self, filename):
        """通用方法：读取 JSON 文件，优先 user_config/user/，回退 defaults/"""
        try:
            path = resolve_config_path(filename)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            return "{}"
        except Exception as e:
            print(f"[ModelBridge] ❌ 读取 {filename} 失败: {e}")
            return "{}"

    @pyqtSlot(str, str, result=bool)
    def saveUserConfig(self, filename, config_json):
        """通用方法：保存配置到 user_config/user/ 目录（defaults/ 不被修改）"""
        try:
            from config.user_config import save_config
            parsed = json.loads(config_json) if isinstance(config_json, str) else config_json
            path = save_config(filename, parsed)
            print(f"[ModelBridge] ✅ 已保存 {filename} → {path}")
            return True
        except Exception as e:
            print(f"[ModelBridge] ❌ 保存 {filename} 失败: {e}")
            return False

    @pyqtSlot(result=str)
    def getAgentInfo(self):
        """获取 Agent 信息（关于界面详情，读取 defaults/agent_info.json）"""
        try:
            return json.dumps(load_agent_info(), ensure_ascii=False)
        except Exception as e:
            print(f"[ModelBridge] ❌ 读取 agent_info.json 失败: {e}")
            return "{}"
