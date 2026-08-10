"""
TTSEngine - 独立文本转语音（TTS）引擎
基于 Windows 内置 SAPI（System.Speech），零额外依赖，支持中文朗读
通过回调通知外部朗读状态

特性：
- 抢占式朗读：新的朗读请求立即打断上一条未完成的朗读
- 多音色支持：通过 SAPI 性别/音高/语速调节实现不同音色预设
  （音色参数全部 try/catch 保护，即使系统不支持 Pitch 也不影响正常朗读）
"""
import re
import subprocess
import threading

# 音色预设：通过 SAPI 性别基础 + 音高(Pitch)/语速(Rate)调节实现不同声线
VOICE_PRESETS = {
    "小男孩":   {"gender": "Male",   "pitch": 15, "rate": 2},
    "小女孩":   {"gender": "Female", "pitch": 18, "rate": 1},
    "默认女声": {"gender": "Female", "pitch": 0,  "rate": 0},
    "低沉男声": {"gender": "Male",   "pitch": -8, "rate": 0},
    "欢快女生": {"gender": "Female", "pitch": 6,  "rate": 2},
}


class TTSEngine:
    """独立语音合成引擎 — Windows SAPI，多音色，抢占式朗读"""

    def __init__(self):
        self._speaking = False
        self._proc = None
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()       # 管道读写独占锁（保证 __DONE__ 回报顺序 = 写入顺序）
        self._done_callback = None
        self._generation = 0
        self._voice_name = "小男孩"               # 默认音色
        self._voice_preset = VOICE_PRESETS["小男孩"]

    # ==========================================
    # 对外接口
    # ==========================================

    def speak(self, text: str) -> None:
        """同步朗读文本（阻塞直到朗读完成）"""
        if not text:
            return
        try:
            self._speaking = True
            self._run_sapi(text)
        finally:
            self._speaking = False

    def speak_async(self, text: str, on_done=None) -> None:
        """异步朗读文本，完成后回调 on_done()（抢占式：打断上一条未完成朗读）"""
        if not text:
            if on_done:
                try:
                    on_done()
                except Exception:
                    pass
            return
        with self._lock:
            self._generation += 1
            gen = self._generation
            self._done_callback = on_done
            self._speaking = True
        threading.Thread(target=self._async_speak_worker, args=(text, gen, True), daemon=True).start()

    def speak_stream(self, text: str, on_done=None) -> None:
        """流式朗读（入队式：不打断当前播放，自动排队连续播放）

        用于 AI 边输出边朗读：每个断句排队写入常驻进程，
        SAPI 同步 Speak 天然无缝衔接 → 真正流式连续播放，无每句冷启动停顿。
        """
        if not text:
            if on_done:
                try:
                    on_done()
                except Exception:
                    pass
            return
        with self._lock:
            self._generation += 1
            gen = self._generation
            self._done_callback = on_done
            self._speaking = True
        threading.Thread(target=self._async_speak_worker, args=(text, gen, False), daemon=True).start()

    def stop(self) -> None:
        """立即停止当前朗读（终止常驻进程，清空未播队列）"""
        self._kill_proc()
        with self._lock:
            self._speaking = False
            self._done_callback = None

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def set_voice(self, voice_name: str) -> None:
        """切换音色预设（小男孩/小女孩/默认女声/低沉男声/欢快女生）

        音色参数在常驻进程启动时注入，切换后需重启进程生效。
        """
        if voice_name in VOICE_PRESETS:
            self._voice_name = voice_name
            self._voice_preset = VOICE_PRESETS[voice_name]
            self._kill_proc()  # 音色变更：重启承载 SAPI 的常驻进程
            print(f"[TTS] 🎙️ 音色已切换: {voice_name}")

    @property
    def voice_name(self) -> str:
        return self._voice_name

    @staticmethod
    def list_voice_names() -> list:
        """返回可用音色名称列表"""
        return list(VOICE_PRESETS.keys())

    def list_voices(self) -> list:
        """列出系统 SAPI 可用的语音"""
        try:
            ps = (
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$s.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return [v.strip() for v in result.stdout.strip().splitlines() if v.strip()]
        except Exception as e:
            print(f"[TTS] ❌ 列出语音失败: {e}")
        return []

    # ==========================================
    # 内部实现
    # ==========================================

    def _async_speak_worker(self, text: str, gen: int, interrupt: bool = False):
        try:
            self._run_sapi(text, interrupt=interrupt)
        except Exception as e:
            print(f"[TTS] ❌ 朗读失败: {e}")
        finally:
            with self._lock:
                if gen == self._generation:
                    self._speaking = False
                    cb = self._done_callback
                    self._done_callback = None
                else:
                    cb = None
            if cb:
                try:
                    cb()
                except Exception:
                    pass

    def _sanitize_text(self, text: str) -> str:
        """清洗文本：去除 emoji 图标与 Markdown 符号，只保留可朗读的纯文本"""
        if not text:
            return ""
        text = re.sub(r'```[\w]*\n?', '', text)
        text = text.replace('```', '')
        text = re.sub(r'[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]', '', text)
        text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)
        text = re.sub(r'`([^`]*)`', r'\1', text)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*([-*+]|\d+[.)])\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'^[\s]*---[\s]*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _run_sapi(self, text: str, interrupt: bool = False):
        """向常驻 PowerShell SAPI 进程写入一行文本并等待播完

        - _write_lock 独占：保证多线程排队时 __DONE__ 回报顺序 = 写入顺序
        - interrupt=True（抢占式）：先终止旧进程清空未播队列，再启动新常驻进程
        - interrupt=False（流式入队）：复用现有常驻进程，SAPI 同步 Speak 天然排队连播
        """
        text = self._sanitize_text(text)
        if not text:
            print("[TTS] ⚠️ 清洗后无可朗读文本")
            return
        with self._write_lock:
            try:
                if interrupt:
                    self._kill_proc()  # 抢占：清空旧队列
                self._ensure_proc()
                self._write_line(text)
                self._wait_done()
            except Exception as e:
                print(f"[TTS] ⚠️ 朗读异常: {e}")

    # ------------- 常驻 PowerShell SAPI 进程 -------------

    def _ensure_proc(self):
        """确保常驻 PowerShell 进程存活（首次/被杀后懒启动）"""
        if self._proc is not None and self._proc.poll() is None:
            return
        p = self._voice_preset
        gender = p.get("gender", "Female")
        pitch = p.get("pitch", 0)
        rate = p.get("rate", 0)
        ps = (
            "$ErrorActionPreference = 'Stop'; "
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "try { $s.SelectVoiceByHints([System.Speech.Synthesis.SynthesisVoiceGender]::" + gender + ") } catch {}; "
            "try { $s.Rate = " + str(rate) + " } catch {}; "
            "try { $s.Pitch = " + str(pitch) + " } catch {}; "
            "$in = [Console]::OpenStandardInput(); "
            "$reader = New-Object System.IO.StreamReader($in); "
            "$out = [Console]::OpenStandardOutput(); "
            "$writer = New-Object System.IO.StreamWriter($out); "
            "$writer.AutoFlush = $true; "
            "while ($true) { "
            "  $line = $reader.ReadLine(); "
            "  if ($null -eq $line) { break }; "
            "  if ($line -eq '__KILL__') { exit 0 }; "
            "  try { $s.SpeakAsync($line) | Out-Null } catch { $writer.WriteLine('__DONE__'); continue }; "
            "  $deadline = (Get-Date).AddSeconds(30); "
            "  while ($s.State -ne [System.Speech.Synthesis.SynthesizerState]::Ready) { "
            "    if ((Get-Date) -gt $deadline) { break }; "
            "    Start-Sleep -Milliseconds 20 "
            "  }; "
            "  $writer.WriteLine('__DONE__') "
            "}"
        )
        self._proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-Command", ps],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0,
        )

    def _kill_proc(self):
        """终止常驻进程（清空未播队列）"""
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    def _write_line(self, text: str):
        proc = self._proc
        if proc is None or proc.poll() is not None:
            raise RuntimeError("TTS 常驻进程不可用")
        line = text.replace('\r', ' ').replace('\n', ' ').encode('utf-8') + b'\n'
        proc.stdin.write(line)
        proc.stdin.flush()

    def _wait_done(self, timeout: float = 60.0) -> bool:
        """等待本句播完（收到 __DONE__ 回报）"""
        import time
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return False
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                return False  # EOF（进程被 stop 终止）
            if line.strip() == b'__DONE__':
                return True
        return False

    def cleanup(self):
        """释放资源"""
        self.stop()
        print("[TTS] 🧹 已清理")