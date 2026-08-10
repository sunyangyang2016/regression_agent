"""
SpeechRecognizer - 独立语音识别（ASR）引擎
使用 Vosk + PyAudio 实现中文语音识别
通过回调将识别结果通知外部（桥接层/调用方）
"""
import json
import os
import threading
import time


class SpeechRecognizer:
    """独立语音识别引擎 — Vosk + PyAudio 实时识别

    职责：仅负责语音识别功能。
    通过回调接口将识别状态/结果通知外部，不依赖 Qt/前端。
    """

    def __init__(self, model_path: str):
        self._model_path = model_path
        self._model = None
        self._rec = None

        # 音频资源（延迟加载）
        self._audio = None
        self._stream = None

        # 状态
        self._listening = False
        self._thread = None
        self._stop_event = threading.Event()

        # 识别文本状态
        self._current_text = ""   # 已确定的完整文本
        self._partial_text = ""   # 当前正在识别的部分文本

        # 静音检测配置（VAD）
        self.vad_enabled = False
        self.vad_silence_seconds = 1.5   # 静音超过该时长自动结束当前句

        # 回调接口（由外部设置）
        self.on_partial = None   # callback(text)  实时部分结果
        self.on_final = None     # callback(text)  一句话确定
        self.on_vad_done = None  # callback(text)  静音检测自动结束
        self.on_status = None    # callback(status) 状态变更

    # ==========================================
    # 对外接口
    # ==========================================

    def start(self):
        """开始聆听（后台线程）"""
        if self._listening:
            return
        self._current_text = ""
        self._partial_text = ""
        self._stop_event.clear()
        self._listening = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop(self) -> str:
        """停止聆听，返回已识别完整文本"""
        if not self._listening:
            return self._current_text.strip()
        self._stop_event.set()
        if self._thread:
            try:
                self._thread.join(timeout=3.0)
            except Exception:
                pass
        self._thread = None
        self._listening = False
        return self._get_full_text()

    def cancel(self):
        """取消聆听，丢弃结果"""
        self._stop_event.set()
        if self._thread:
            try:
                self._thread.join(timeout=2.0)
            except Exception:
                pass
        self._thread = None
        self._listening = False
        self._current_text = ""
        self._partial_text = ""

    def set_vad_enabled(self, enabled: bool):
        """启用/禁用静音检测"""
        self.vad_enabled = enabled

    def set_vad_silence(self, seconds: float):
        """设置静音多少秒后自动结束"""
        self.vad_silence_seconds = seconds

    @property
    def is_listening(self) -> bool:
        return self._listening

    def check_model(self) -> bool:
        """检查模型是否可用"""
        return os.path.isdir(self._model_path)

    # ==========================================
    # 内部实现
    # ==========================================

    def _get_full_text(self) -> str:
        if self._partial_text.strip():
            return (self._current_text.strip() + (" " if self._current_text.strip() else "") + self._partial_text.strip())
        return self._current_text.strip()

    def _emit_status(self, status: str):
        if self.on_status:
            try:
                self.on_status(status)
            except Exception:
                pass

    def _emit_partial(self, text: str):
        if self.on_partial:
            try:
                self.on_partial(text)
            except Exception:
                pass

    def _emit_final(self, text: str):
        if self.on_final:
            try:
                self.on_final(text)
            except Exception:
                pass

    def _load_model(self) -> bool:
        try:
            from vosk import Model, KaldiRecognizer
            if not os.path.isdir(self._model_path):
                return False
            if self._model is None:
                self._emit_status("正在加载语音模型...")
                self._model = Model(self._model_path)
            if self._rec is None:
                self._rec = KaldiRecognizer(self._model, 16000)
            return True
        except Exception as e:
            print(f"[ASR] ❌ 加载模型失败: {e}")
            return False

    def _listen_loop(self):
        """后台线程：采集麦克风音频并通过 Vosk 实时识别"""
        try:
            import pyaudio
        except ImportError:
            self._emit_status("未安装 pyaudio")
            self._listening = False
            return

        if not self._load_model():
            self._listening = False
            return

        # 静音检测状态
        silence_start_time = None
        last_partial = ""

        try:
            self._audio = pyaudio.PyAudio()
            self._stream = self._audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=4000,
            )
            self._emit_status("🎤 正在聆听...")

            while not self._stop_event.is_set():
                try:
                    data = self._stream.read(4000, exception_on_overflow=False)
                except Exception:
                    break

                if self._rec.AcceptWaveform(data):
                    # 确定了一整句话
                    try:
                        res = json.loads(self._rec.Result())
                        text = res.get("text", "").strip()
                        if text:
                            if self._current_text.strip():
                                self._current_text = self._current_text.strip() + " " + text
                            else:
                                self._current_text = text
                            self._partial_text = ""
                            # 通知一句话确定
                            self._emit_partial(self._current_text)
                            self._emit_final(self._current_text)
                            # 重置静音计时
                            silence_start_time = None
                    except Exception:
                        pass
                else:
                    # 部分识别（实时更新）
                    try:
                        partial = json.loads(self._rec.PartialResult())
                        ptext = partial.get("partial", "").strip()
                        if ptext and ptext != last_partial:
                            self._partial_text = ptext
                            combined = self._current_text.strip() + (" " if self._current_text.strip() else "") + ptext
                            self._emit_partial(combined)
                            last_partial = ptext

                        # 静音检测：没有语音输入时，追踪静音时长
                        current_partial = partial.get("partial", "").strip()
                        if current_partial:
                            silence_start_time = None
                        else:
                            if silence_start_time is None:
                                silence_start_time = time.time()
                            elif time.time() - silence_start_time > self.vad_silence_seconds:
                                # 静音达到阈值，自动结束当前句
                                full = self._get_full_text()
                                if full:
                                    self._emit_vad_done(full)
                                # 重置，准备下一句
                                self._current_text = ""
                                self._partial_text = ""
                                last_partial = ""
                                silence_start_time = None
                    except Exception:
                        pass
        except Exception as e:
            import traceback
            print(f"[ASR] ❌ 录音失败: {e}")
            traceback.print_exc()
            self._emit_status(f"录音失败: {e}")
        finally:
            self._close_stream()

    def _emit_vad_done(self, text: str):
        if self.on_vad_done:
            try:
                self.on_vad_done(text)
            except Exception:
                pass

    def _close_stream(self):
        """关闭音频流和资源"""
        try:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
        except Exception:
            pass
        try:
            if self._audio:
                self._audio.terminate()
        except Exception:
            pass
        self._stream = None
        self._audio = None

    def cleanup(self):
        """释放资源"""
        if self._listening:
            self._stop_event.set()
            if self._thread:
                try:
                    self._thread.join(timeout=2.0)
                except Exception:
                    pass
        self._close_stream()
        print("[ASR] 🧹 已清理")