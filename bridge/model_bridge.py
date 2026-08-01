"""
ModelBridge - 模型配置桥接
处理模型配置、AI 重连等配置相关的前后端交互
"""
import json
import os
from PyQt5.QtCore import pyqtSlot

from .base import BridgeBase


class ModelBridge(BridgeBase):
    """模型配置桥接 — 模型/系统配置管理"""

    def _get_model_config(self):
        if self.app_controller and hasattr(self.app_controller, 'model_config'):
            return self.app_controller.model_config
        return None

    def _get_user_config_dir(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "user_config", "defaults")

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
        """从 user_config/defaults/models.json 读取模型列表"""
        try:
            path = os.path.join(self._get_user_config_dir(), "models.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                models = data.get("models", [])
                print(f"[ModelBridge] ✅ 已加载 {len(models)} 个模型")
                return json.dumps(models, ensure_ascii=False)
            else:
                print(f"[ModelBridge] ⚠️ models.json 未找到: {path}")
        except Exception as e:
            print(f"[ModelBridge] ❌ 读取 models.json 失败: {e}")
        return json.dumps([])

    @pyqtSlot(str)
    def saveModels(self, models_json):
        """保存模型列表到 user_config/defaults/models.json"""
        try:
            models = json.loads(models_json)
            if not isinstance(models, list):
                raise ValueError("数据必须是数组格式")
            path = os.path.join(self._get_user_config_dir(), "models.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"models": models}, f, ensure_ascii=False, indent=4)
            print(f"[ModelBridge] ✅ 已保存 {len(models)} 个模型")
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
        """通用方法：从 user_config/defaults/ 读取 JSON 文件"""
        try:
            path = os.path.join(self._get_user_config_dir(), filename)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            return "{}"
        except Exception as e:
            print(f"[ModelBridge] ❌ 读取 {filename} 失败: {e}")
            return "{}"