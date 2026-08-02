"""
ModelBridge - 模型配置桥接
处理模型配置、AI 重连等配置相关的前后端交互
"""
import json
import os
from PyQt5.QtCore import pyqtSlot, pyqtSignal

from .base import BridgeBase
from config.user_config import USER_DIR, resolve_config_path, load_agent_info


class ModelBridge(BridgeBase):
    """模型配置桥接 — 模型/系统配置管理"""

    # 连通性测试结果信号（跨线程 emit 安全，自动切回 GUI 线程）
    test_result = pyqtSignal(bool, str)

    def __init__(self, app_controller):
        super().__init__(app_controller)
        self.test_result.connect(self._emit_test_result)
        print("[ModelBridge] ✅ test_result 信号已就绪")

    def _get_model_config(self):
        if self.app_controller and hasattr(self.app_controller, 'model_config'):
            return self.app_controller.model_config
        return None

    def _get_user_config_dir(self):
        # 用户配置写入目录：user_config/user/（默认配置在 defaults/ 下，只读不修改）
        return USER_DIR

    def _get_fallback(self, key, default=""):
        """从 defaults/models.json 激活模型读取兜底值（不再硬编码提供商/模型）"""
        try:
            from config.user_config import load_default_active_model
            m = load_default_active_model()
            if m and m.get(key) is not None:
                return m.get(key)
        except Exception:
            pass
        return default

    @pyqtSlot(str)
    def saveConfig(self, config_json):
        """保存模型配置到后端 ConfigManager 内存（供 AI 客户端重连使用）

        注意：这里不调用 mgr.save_config() 写回 models.json。
        原因：save_config() 会按"active=true"找到激活模型并用当前配置覆盖它，
        在多模型场景下会把 config 覆盖到错误的模型记录（如添加智谱模型时
        覆盖了 deepseek）。模型列表的持久化完全由 saveModels() 负责。
        """
        try:
            cfg = json.loads(config_json)
            mgr = self._get_model_config()
            if mgr:
                mgr.set("api", "provider", cfg.get("provider") or self._get_fallback("provider", "DeepSeek"))
                mgr.set("api", "model", cfg.get("model") or self._get_fallback("model", "deepseek-v4-flash"))
                mgr.set("chat", "temperature", cfg.get("temperature", self._get_fallback("temperature", 0.7)))
                mgr.set("chat", "max_tokens", cfg.get("maxTokens", self._get_fallback("maxTokens", 2000)))
                mgr.set("api", "api_key", cfg.get("apiKey", ""))
                mgr.set("api", "base_url", cfg.get("baseUrl", self._get_fallback("baseUrl", "")))
                mgr.set("api", "max_context", cfg.get("maxContext", self._get_fallback("maxContext", 65536)))
                mgr.set("api", "price_per_million_hit_tokens", cfg.get("pricePerMillionHitTokens", self._get_fallback("pricePerMillionHitTokens", 0.07)))
                mgr.set("api", "price_per_million_miss_tokens", cfg.get("pricePerMillionMissTokens", self._get_fallback("pricePerMillionMissTokens", 1.0)))
                mgr.set("api", "price_per_million_output_tokens", cfg.get("pricePerMillionOutputTokens", self._get_fallback("pricePerMillionOutputTokens", 2.0)))
                print(f"[ModelBridge] ✅ 运行时配置已更新: {cfg.get('provider')}/{cfg.get('model')}")
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
                "provider": self._get_fallback("provider", "DeepSeek"),
                "model": self._get_fallback("model", "deepseek-v4-flash"),
                "temperature": self._get_fallback("temperature", 0.7),
                "maxTokens": self._get_fallback("maxTokens", 2000)
            })
        cfg = {
            "provider": mgr.get("api", "provider") or self._get_fallback("provider", "DeepSeek"),
            "model": mgr.get("api", "model") or self._get_fallback("model", "deepseek-v4-flash"),
            "temperature": mgr.get("chat", "temperature") or self._get_fallback("temperature", 0.7),
            "maxTokens": mgr.get("chat", "max_tokens") or self._get_fallback("maxTokens", 2000),
            "maxContext": mgr.get("api", "max_context") or self._get_fallback("maxContext", 65536),
            "pricePerMillionHitTokens": mgr.get("api", "price_per_million_hit_tokens") or self._get_fallback("pricePerMillionHitTokens", 0.07),
            "pricePerMillionMissTokens": mgr.get("api", "price_per_million_miss_tokens") or self._get_fallback("pricePerMillionMissTokens", 1.0),
            "pricePerMillionOutputTokens": mgr.get("api", "price_per_million_output_tokens") or self._get_fallback("pricePerMillionOutputTokens", 2.0)
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

            if hasattr(self.app_controller, '_bridge') and self.app_controller._bridge:
                bridge = self.app_controller._bridge
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

            if hasattr(self.app_controller, '_bridge') and self.app_controller._bridge:
                bridge = self.app_controller._bridge
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

    @pyqtSlot(str)
    def testConnection(self, config_json):
        """真实连通性测试：后台线程发起最小 API 请求验证配置，结果回调前端 JS

        与 reconnectAI 不同：
        - reconnectAI 仅重建客户端对象（不发真实请求），Key 错误也会"成功"
        - testConnection 实际调用 chat.completions 最小请求，确认 Key 真实有效

        前端通过 window.onModelTestResult(success, msg) 接收结果
        """
        import threading
        try:
            cfg = json.loads(config_json)
        except Exception:
            cfg = {}
        print(f"[ModelBridge][测试] ① 收到测试请求: provider={cfg.get('provider')} model={cfg.get('model')} "
              f"key={'***' if cfg.get('apiKey') else '空'} baseUrl={cfg.get('baseUrl')}")

        def _run():
            try:
                from ai.protocol import ModelConfig as MC
                from ai.stream_handler import StreamHandler
                mcfg = MC(
                    base_url=cfg.get("baseUrl", ""),
                    api_key=cfg.get("apiKey", ""),
                    model=cfg.get("model", ""),
                    temperature=0.7,
                    max_tokens=16,
                    stream=False,
                )
                sh = StreamHandler(mcfg, None, None)
                print("[ModelBridge][测试] ② 后台线程开始真实请求...")
                success, msg = sh.test_connection(timeout=15.0)
                print(f"[ModelBridge][测试] ③ 后台测试完成: success={success} msg={msg}")
            except Exception as e:
                success, msg = False, f"连接失败: {e}"
                print(f"[ModelBridge][测试] ⚠️ 后台测试异常: {e}")
            try:
                # 用信号跨线程回传（线程安全，自动切回 GUI 线程）
                self.test_result.emit(success, msg)
                print(f"[ModelBridge][测试] ④ 已 emit test_result 信号: success={success} msg={msg}")
            except Exception as e:
                print(f"[ModelBridge][测试] ❌ emit 信号失败: {e}")

        threading.Thread(target=_run, daemon=True).start()

    def _emit_test_result(self, success, msg):
        """把连通测试结果回传给前端 JS（由 test_result 信号触发，GUI 线程）"""
        try:
            # 注意：AppController 保存的是 self._bridge（ChatBridge 实例），不是 main_bridge 属性
            has_main = bool(self.app_controller and hasattr(self.app_controller, '_bridge') and self.app_controller._bridge)
            print(f"[ModelBridge][测试] ⑤ 回调前端: _bridge={'有' if has_main else '无'} success={success} msg={msg}")
            if has_main:
                bridge = self.app_controller._bridge
                js = "window.onModelTestResult && window.onModelTestResult(%s, %s);" % (
                    "true" if success else "false",
                    json.dumps(msg, ensure_ascii=False),
                )
                bridge.execute_js(js)
                print(f"[ModelBridge][测试] ⑥ JS 已注入: {js[:80]}...")
        except Exception as e:
            print(f"[ModelBridge][测试] ❌ 测试结果回调失败: {e}")

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
