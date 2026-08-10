"""
VoiceBridge - 语音桥接层
组合独立 ASR（SpeechRecognizer）和 TTS（TTSEngine）引擎，
负责前后端通信与语音交互模式编排
"""
import json
import os

from PyQt5.QtCore import pyqtSlot

from .base import BridgeBase
from media.voice.asr import SpeechRecognizer
from media.voice.tts import TTSEngine, VOICE_PRESETS

# 模型路径
MODEL_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "resources", "models", "vosk-model-small-cn-0.22"
)


class VoiceBridge(BridgeBase):
    """语音桥接层 — 协调 ASR/TTS 引擎 + 语音交互模式"""

    def __init__(self, app_controller):
        super().__init__(app_controller)
        # 独立引擎实例
        self._asr = SpeechRecognizer(MODEL_PATH)
        self._tts = TTSEngine()

        # 语音交互模式状态
        self._voice_chat_active = False
        self._voice_chat_thinking = False  # 等待 AI 回复中
        self._ai_reply_done = False        # AI 流式回复是否已完成（流式朗读完成后据此重新聆听）

        # 设置 ASR 回调
        self._asr.on_partial = self._on_asr_partial
        self._asr.on_final = self._on_asr_final
        self._asr.on_vad_done = self._on_asr_vad_done
        self._asr.on_status = self._on_asr_status

        # 启动时从 agent_config.json 读取并应用音色配置
        self._apply_voice_from_config()

    # ==========================================
    # 前端 → 后端（通过 @pyqtSlot 暴露给 JS）
    # ==========================================

    @pyqtSlot()
    def startListening(self):
        """开始语音识别（前端点击麦克风按钮调用）"""
        print("[VoiceBridge] 🎤 开始语音识别...")
        self._asr.start()

    @pyqtSlot()
    def stopListening(self):
        """停止语音识别并返回结果（前端再次点击麦克风按钮调用）"""
        print("[VoiceBridge] ⏹ 停止语音识别...")
        text = self._asr.stop()
        print(f"[VoiceBridge] ✅ 识别结果: {text}")
        self._emit_final(text)

    @pyqtSlot(str)
    def speakText(self, text):
        """朗读文本（TTS）"""
        self._tts.speak_async(text)

    def speak_stream(self, text: str):
        """流式朗读：AI 边输出边播放（ChatBridge 断句后调用）

        入队式（speak_stream）：不打断正在播放的句子，
        排队写入常驻 SAPI 进程连续播放（无每句冷启动停顿）；
        每句完成后回调 _on_stream_tts_done，最后一句播完重新聆听。
        """
        if not text:
            return
        self._tts.speak_stream(text, on_done=self._on_stream_tts_done)

    @pyqtSlot(str, result=bool)
    def setVoice(self, voice_name):
        """切换 TTS 音色（由设置面板调用并实时生效）"""
        if voice_name in VOICE_PRESETS:
            self._tts.set_voice(voice_name)
            return True
        return False

    @pyqtSlot(result=str)
    def getVoice(self):
        """获取当前 TTS 音色名称"""
        return self._tts.voice_name

    @pyqtSlot()
    def startVoiceChat(self):
        """开启语音交互模式（连续语音对话）"""
        if self._voice_chat_active:
            return
        print("[VoiceBridge] 🎤 开启语音交互模式...")
        self._voice_chat_active = True
        self._voice_chat_thinking = False
        self._ai_reply_done = False
        # 启用 VAD 静音检测
        self._asr.set_vad_enabled(True)
        self._asr.set_vad_silence(1.5)
        self._asr.start()

    @pyqtSlot()
    def stopVoiceChat(self):
        """退出语音交互模式"""
        if not self._voice_chat_active:
            return
        print("[VoiceBridge] ⏹ 退出语音交互模式...")
        self._voice_chat_active = False
        self._voice_chat_thinking = False
        self._asr.cancel()
        self._tts.stop()

    @pyqtSlot(result=str)
    def checkModel(self):
        """检查语音模型是否可用（前端初始化时调用）"""
        try:
            ok = self._asr.check_model()
            return json.dumps({"ok": ok, "path": MODEL_PATH}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

    # ==========================================
    # ASR 回调处理
    # ==========================================

    def _on_asr_partial(self, text: str):
        """实时部分识别结果 → 推送到前端显示"""
        self._emit_partial(text)

    def _on_asr_final(self, text: str):
        """一句话确定 → 推送到前端（非交互模式）"""
        if not self._voice_chat_active:
            self._emit_final(text)

    def _on_asr_vad_done(self, text: str):
        """静音检测触发（语音交互模式）：自动发送给 AI

        通过与手动发送完全一致的流程：
        1. 识别文字填入输入框
        2. 调用前端 sendMessage() → 显示用户气泡 + 流式 AI 回复
        """
        if not self._voice_chat_active or self._voice_chat_thinking:
            return
        if not text:
            return
        print(f"[VoiceBridge] 🗣️ VAD 自动发送: {text}")
        self._voice_chat_thinking = True
        self._ai_reply_done = False  # 新一轮回复开始
        # 让前端走与手动发送完全一致的流程
        js = (
            "var input = document.getElementById('messageInput');"
            "if (input) input.value = " + json.dumps(text, ensure_ascii=False) + ";"
            "if (typeof sendMessage === 'function') sendMessage();"
        )
        self.execute_js(js)

    def _on_asr_status(self, status: str):
        self._emit_status(status)

    # ==========================================
    # TTS 联动（由 ChatBridge 在 AI 回复完成时调用）
    # ==========================================

    def on_ai_reply_complete(self, reply_text: str):
        """AI 回复完成回调（ChatBridge 调用）：
        语音交互模式 → AI 回复已边输出边流式朗读（chat_bridge._feed_tts_stream 断句播放），
        此处仅标记回复完成；若当前无播放则立即重新聆听，
        否则等最后一句流式朗读完成（_on_stream_tts_done）后重新聆听。
        """
        if not self._voice_chat_active:
            return
        self._voice_chat_thinking = False
        self._ai_reply_done = True
        if not self._tts.is_speaking:
            self._restart_listening()

    def _on_stream_tts_done(self):
        """流式朗读完成回调：AI 回复已结束时，重新开始聆听"""
        if self._voice_chat_active and self._ai_reply_done:
            self._ai_reply_done = False
            self._restart_listening()

    def _restart_listening(self):
        """重新开始聆听"""
        self._emit_status("🎤 聆听中...（继续说）")
        self._asr.start()

    # ==========================================
    # 配置读取
    # ==========================================

    def _apply_voice_from_config(self):
        """从 agent_config.json 读取音色配置并应用到 TTS（默认小男孩）"""
        try:
            from config.user_config import resolve_config_path
            path = resolve_config_path("agent_config.json")
            voice = "小男孩"
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                voice = cfg.get("voice", "小男孩")
            self._tts.set_voice(voice)
            print(f"[VoiceBridge] 🎙️ 已应用音色: {voice}")
        except Exception as e:
            print(f"[VoiceBridge] ⚠️ 读取音色配置失败: {e}，使用默认音色")
            self._tts.set_voice("小男孩")

    # ==========================================
    # 前端回调推送
    # ==========================================

    def _emit_partial(self, text: str):
        self.execute_js(f"window.onVoicePartial({json.dumps(text, ensure_ascii=False)});")

    def _emit_final(self, text: str):
        self.execute_js(f"window.onVoiceFinal({json.dumps(text, ensure_ascii=False)});")

    def _emit_status(self, status: str):
        s = json.dumps(status, ensure_ascii=False)
        self.execute_js(f"window.onVoiceStatus({s});")

    # ==========================================
    # 清理
    # ==========================================

    def cleanup(self):
        """应用退出时清理资源"""
        self._voice_chat_active = False
        self._asr.cleanup()
        self._tts.cleanup()
        print("[VoiceBridge] 🧹 已清理")