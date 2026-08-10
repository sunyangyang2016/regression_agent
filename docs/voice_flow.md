# 语音系统 — 业务逻辑说明文档

> 本文档基于 `bridge/voice_bridge.py`、`bridge/chat_bridge.py`、`media/voice/asr.py`、`media/voice/tts.py`、`view/js/voice_input.js` 的实际实现编写，覆盖语音系统的**语音识别（ASR）、语音合成（TTS）、语音交互模式（连续语音对话）、前后端通信**等核心业务流程。

---

## 目录

- [1. 系统整体架构](#1-系统整体架构)
- [2. 核心组件清单](#2-核心组件清单)
- [3. 语音识别（ASR）引擎](#3-语音识别asr引擎)
- [4. 语音合成（TTS）引擎](#4-语音合成tts引擎)
- [5. 语音桥接层（VoiceBridge）](#5-语音桥接层voicebridge)
- [6. 单次语音输入流程](#6-单次语音输入流程)
- [7. 语音交互模式（连续语音对话）](#7-语音交互模式连续语音对话)
- [8. AI 回复流式朗读（TTS 联动）](#8-ai-回复流式朗读tts-联动)
- [9. 音色配置与管理](#9-音色配置与管理)
- [10. 前端交互与回调](#10-前端交互与回调)
- [11. 资源清理与异常处理](#11-资源清理与异常处理)

---

## 1. 系统整体架构

语音系统采用**前端（JS）+ 桥接层（PyQt5 Slot）+ 独立引擎（ASR/TTS）**的三层架构，通过 `execute_js` 实现双向通信。

```
┌────────────────────────── 前端（QWebEngineView）──────────────────────────┐
│  view/index.html ── voiceBtn 麦克风按钮                                    │
│  view/js/voice_input.js ── 语音输入控制 + 后端回调接收                      │
└────────────────────────────────┬───────────────────────────────────────────┘
                                 │  pyqtSlot 调用 / execute_js 回调
┌────────────────────────────────▼───────────────────────────────────────────┐
│                        bridge/voice_bridge.py                               │
│                     VoiceBridge（语音桥接层）                                 │
│  - 组合 ASR / TTS 引擎实例                                                   │
│  - 语音交互模式状态机（_voice_chat_active / _voice_chat_thinking）            │
│  - 前后端通信 + 回调分发                                                     │
└───────────────┬────────────────────────────────┬───────────────────────────┘
                │                                │
    ┌───────────▼──────────┐          ┌───────────▼──────────┐
    │  media/voice/asr.py  │          │  media/voice/tts.py  │
    │  SpeechRecognizer    │          │  TTSEngine           │
    │  Vosk + PyAudio      │          │  Windows SAPI        │
    │  语音识别（输入）      │          │  语音合成（输出）      │
    └──────────────────────┘          └──────────────────────┘

┌────────────────────────────────────────────────────────────────────────────┐
│                     bridge/chat_bridge.py（TTS 联动）                        │
│  - on_stream_update：接收 AI 流式内容 → 增量提取 → 断句朗读                   │
│  - on_stream_complete：AI 回复完成 → 刷新剩余缓冲 → 通知 VoiceBridge         │
└────────────────────────────────────────────────────────────────────────────┘
```

**关键设计**：

- **双引擎独立**：ASR（输入）和 TTS（输出）完全解耦，通过 `VoiceBridge` 统一编排。
- **流式朗读**：AI 边输出边断句播放，实现自然的「边说边听」体验。
- **VAD 静音检测**：语音交互模式下自动识别一句话结束并自动发送。

---

## 2. 核心组件清单

| 组件 | 文件 | 职责 |
|------|------|------|
| `SpeechRecognizer` | `media/voice/asr.py` | 语音识别引擎（Vosk + PyAudio），实时采集麦克风音频并输出文本 |
| `TTSEngine` | `media/voice/tts.py` | 语音合成引擎（Windows SAPI），支持多音色、抢占式/流式朗读 |
| `VoiceBridge` | `bridge/voice_bridge.py` | 语音桥接层，组合 ASR/TTS，负责前后端通信与语音交互模式编排 |
| `ChatBridge`（联动部分） | `bridge/chat_bridge.py` | AI 回复流式朗读联动（断句触发 TTS） |
| `voiceInput` | `view/js/voice_input.js` | 前端语音控制（麦克风按钮、模式切换、回调处理） |
| `voiceBtn` | `view/index.html` | 麦克风按钮（点击进入/退出语音交互模式） |

---

## 3. 语音识别（ASR）引擎

### 3.1 技术方案

- **模型**：Vosk 中文小模型（`vosk-model-small-cn-0.22`，位于 `resources/models/`）
- **音频采集**：PyAudio（16kHz 单声道 PCM 16bit）
- **识别方式**：`KaldiRecognizer.AcceptWaveform()` 实时流式识别

### 3.2 回调接口

| 回调 | 触发时机 | 说明 |
|------|---------|------|
| `on_partial(text)` | 实时识别中 | 部分识别结果，随时更新前端输入框 |
| `on_final(text)` | 一句话确定 | 完整句子确定时触发 |
| `on_vad_done(text)` | VAD 静音检测 | 静音超过阈值自动结束当前句（语音交互模式使用） |
| `on_status(status)` | 状态变更 | "正在加载语音模型…" / "🎤 正在聆听…" 等 |

### 3.3 核心状态

```python
self._listening = False        # 是否正在聆听
self._current_text = ""        # 已确定的完整文本
self._partial_text = ""        # 当前正在识别的部分文本
self.vad_enabled = False       # VAD 静音检测开关
self.vad_silence_seconds = 1.5 # 静音阈值（秒）
```

### 3.4 VAD 静音检测

```
用户说话 ──► 实时识别（partial 持续更新）
                │
                ├─ 检测到静音（无 partial 输出）
                │     └── 持续超过 vad_silence_seconds (1.5s)
                │           └──► 触发 _emit_vad_done(完整文本)
                │                 └──► VoiceBridge._on_asr_vad_done
                │                       └──► 自动发送给 AI
                │
                └─ 检测到完整句子（AcceptWaveform=True）
                      └──► _emit_final(当前文本)
                            └──► VoiceBridge._on_asr_final（非交互模式推送前端）
```

---

## 4. 语音合成（TTS）引擎

### 4.1 技术方案

- **合成方式**：Windows 内置 SAPI（`System.Speech`），零额外依赖
- **进程模型**：常驻 PowerShell 进程，通过标准输入/输出管道通信
- **文本清洗**：`_sanitize_text()` 去除 emoji、Markdown 标记，保留可朗读纯文本

### 4.2 音色预设（VOICE_PRESETS）

| 音色名称 | 性别 | 音高 (Pitch) | 语速 (Rate) |
|---------|------|-------------|------------|
| 小男孩 | Male | +15 | +2 |
| 小女孩 | Female | +18 | +1 |
| 默认女声 | Female | 0 | 0 |
| 低沉男声 | Male | -8 | 0 |
| 欢快女生 | Female | +6 | +2 |

### 4.3 两种朗读模式

| 模式 | 方法 | 行为 | 适用场景 |
|------|------|------|---------|
| 抢占式 | `speak_async(text)` | 打断当前朗读，立即播放新内容 | 手动朗读（如 `speakText`） |
| 流式入队 | `speak_stream(text)` | 不打断当前播放，排队连续播放 | AI 回复边输出边朗读 |

### 4.4 流式朗读实现原理

```
speak_stream(sentence)
    │
    ├─ 累积到 _tts_buffer
    │
    └─ 按断句符（。？！；换行）切出完整句子 [s1, s2, ..., last]
         │
         ├─ 完整句子 → 队列写入常驻 SAPI 进程
         │     └── SAPI 同步 Speak 天然无缝衔接 → 连续播放
         │
         └─ 最后残句 → 保留到 _tts_buffer（等待下一轮累积）
```

**关键机制**：
- `_write_lock` 独占锁保证多线程排队时 `__DONE__` 回报顺序 = 写入顺序
- 常驻进程内 `SpeakAsync` + 轮询 `State == Ready` → 保证句子串行播放
- 每句完成后向 stdout 写入 `__DONE__`，Python 侧 `_wait_done()` 同步等待

---

## 5. 语音桥接层（VoiceBridge）

### 5.1 职责

- **组合引擎**：实例化 `SpeechRecognizer` 和 `TTSEngine`
- **注册回调**：将 ASR 的回调绑定到内部处理方法
- **前后端桥接**：通过 `@pyqtSlot` 暴露方法给 JS，通过 `execute_js` 推送回调到前端
- **语音交互模式**：管理连续语音对话的状态机

### 5.2 初始化流程

```python
def __init__(self, app_controller):
    # 1. 创建独立引擎实例
    self._asr = SpeechRecognizer(MODEL_PATH)   # Vosk 模型路径
    self._tts = TTSEngine()                     # SAPI 合成引擎

    # 2. 语音交互模式状态
    self._voice_chat_active = False    # 是否处于语音交互模式
    self._voice_chat_thinking = False  # 是否等待 AI 回复中
    self._ai_reply_done = False        # AI 流式回复是否已完成

    # 3. 绑定 ASR 回调
    self._asr.on_partial = self._on_asr_partial
    self._asr.on_final = self._on_asr_final
    self._asr.on_vad_done = self._on_asr_vad_done
    self._asr.on_status = self._on_asr_status

    # 4. 启动时读取音色配置（agent_config.json → "voice" 字段）
    self._apply_voice_from_config()
```

### 5.3 对前端暴露的槽方法

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `startListening()` | 无 | 无 | 开始语音识别（单次录音） |
| `stopListening()` | 无 | 无 | 停止语音识别并返回结果 |
| `speakText(text)` | str | 无 | 朗读指定文本（TTS） |
| `speak_stream(text)` | str | 无 | 流式朗读（排队播放） |
| `setVoice(voice_name)` | str | bool | 切换 TTS 音色 |
| `getVoice()` | 无 | str | 获取当前音色名称 |
| `startVoiceChat()` | 无 | 无 | 开启语音交互模式 |
| `stopVoiceChat()` | 无 | 无 | 退出语音交互模式 |
| `checkModel()` | 无 | str(JSON) | 检查语音模型是否可用 |

---

## 6. 单次语音输入流程

> 通过点击麦克风按钮**第一次**进入语音交互模式；如果在语音交互模式中，点击则立即退出。单次录音的 `startListening/stopListening` 方法仍被保留，但当前按钮点击已直接映射到语音交互模式。

```
用户点击麦克风按钮（voiceBtn）
    │
    ▼
voiceInput.toggle()
    │
    ├─ 处于语音交互模式？──是──► _exitVoiceChat() → stopVoiceChat()
    │
    ├─ 处于单次录音中？────是──► _stop() → stopListening()
    │
    └─ 否则 ──────────────► _enterVoiceChat() → startVoiceChat()
```

---

## 7. 语音交互模式（连续语音对话）

### 7.1 模式状态机

```
                    startVoiceChat()                     
  ┌────────────────────────► 语音交互模式 ──────────────────────────┐
  │                              │                                 │
  │                           VAD 检测                             │
  │                              │                                 │
  │                    ┌─────────▼─────────┐                       │
  │                    │  _voice_chat_     │                       │
  │                    │   thinking=false  │                       │
  │                    └─────────┬─────────┘                       │
  │                              │                                 │
  │                    用户说话 + 静音 1.5s                          │
  │                              │                                 │
  │                    ┌─────────▼─────────┐                       │
  │                    │  _on_asr_vad_done │                       │
  │                    │  (自动发送)        │                       │
  │                    └─────────┬─────────┘                       │
  │                              │                                 │
  │              _voice_chat_thinking = true                       │
  │                              │                                 │
  │                前端 sendMessage() ──► AI 回复                   │
  │                              │                                 │
  │                 ChatBridge 流式朗读（边输出边播放）               │
  │                              │                                 │
  │                    ┌─────────▼─────────┐                       │
  │                    │ on_stream_        │                       │
  │                    │  complete()       │                       │
  │                    └─────────┬─────────┘                       │
  │                              │                                 │
  │              _voice_chat_thinking = false                      │
  │              _ai_reply_done = true                             │
  │                              │                                 │
  │              ┌─── TTS 正在播放？ ───┐                           │
  │              │否                    │是                         │
  │              ▼                      ▼                           │
  │        _restart_listening()   等待 _on_stream_tts_done         │
  │        （立即重新聆听）          └──► _restart_listening()       │
  └───────────────────────────────────────────────────────────────┘

                  stopVoiceChat() ────► 退出模式，清理资源
```

### 7.2 开启流程（startVoiceChat）

```python
def startVoiceChat(self):
    # 1. 标记模式激活
    self._voice_chat_active = True
    self._voice_chat_thinking = False
    self._ai_reply_done = False
    # 2. 启用 VAD 静音检测（1.5 秒静音自动结束）
    self._asr.set_vad_enabled(True)
    self._asr.set_vad_silence(1.5)
    # 3. 开始聆听
    self._asr.start()
```

### 7.3 VAD 自动发送流程（_on_asr_vad_done）

```
VAD 检测到一句话结束
    │
    ├─ 检查：_voice_chat_active && !_voice_chat_thinking
    │
    ├─ 设置 _voice_chat_thinking = True（防止重复发送）
    │
    └─ 通过 execute_js 执行前端代码：
        1. 识别文字填入输入框（messageInput.value = text）
        2. 调用 sendMessage() → 走与手动发送完全一致的流程
           └── 显示用户气泡 + 流式 AI 回复
```

**关键设计**：VAD 自动发送完全复用前端 `sendMessage()` 流程，确保 UI 行为与手动发送一致（用户气泡、AI 流式回复、TTS 朗读联动全部生效）。

### 7.4 退出流程（stopVoiceChat）

```python
def stopVoiceChat(self):
    self._voice_chat_active = False
    self._voice_chat_thinking = False
    self._asr.cancel()   # 取消聆听，丢弃未完成结果
    self._tts.stop()     # 停止当前朗读，清空未播队列
```

---

## 8. AI 回复流式朗读（TTS 联动）

### 8.1 完整链路

```
AI 客户端流式返回
    │
    ▼
ChatBridge.on_stream_update(content)    // content 是累积全文
    │
    ├─ 推送全文到前端 UI（onStreamUpdate 全量渲染）
    │
    ├─ 缓存 _last_ai_reply = content    // 供回复完成时使用
    │
    └─ 增量提取：delta = content[_tts_last_len:]
        └─ _tts_last_len = len(content)
            └─ _feed_tts_stream(delta)
                │
                ├─ _tts_buffer += delta  // 累积
                │
                └─ 按断句符切分（。？！；换行）
                    ├─ 完整句子 → _speak_sentence(句子)
                    │     └─ VoiceBridge.speak_stream(句子)
                    │           └─ TTSEngine 入队播放（不打断）
                    └─ 残句 → 保留在缓冲区


AI 回复完成
    │
    ▼
ChatBridge.on_stream_complete()
    │
    ├─ 前端 onStreamComplete()
    │
    ├─ _flush_tts_stream()  // 播放剩余无标点缓冲
    │     └─ vb.speak_stream(缓冲内容)
    │
    ├─ vb.on_ai_reply_complete(reply_text)
    │     ├─ _voice_chat_thinking = false
    │     ├─ _ai_reply_done = true
    │     └─ TTS 未在播放？ ──是──► _restart_listening()
    │                              └─（否则等 _on_stream_tts_done）
    │
    └─ _tts_last_len = 0  // 重置增量游标
```

### 8.2 增量提取机制

**为什么需要增量？**

AIController 推送的 `content` 是**累积全文**（例如 `"你好" → "你好世界" → "你好世界！"`），而非增量片段。如果每次都把全文送入 TTS，会导致已播内容重复播放。

**解决方案**：

```python
if len(content) > self._tts_last_len:
    delta = content[self._tts_last_len:]  # 只取新增部分
    self._tts_last_len = len(content)      # 更新游标
    self._feed_tts_stream(delta)
```

### 8.3 断句播放

```python
def _feed_tts_stream(self, delta):
    self._tts_buffer += delta
    # 按断句符（。？！；换行）切出完整句子
    sentences = re.split(r'(?<=[。？！；\n])', self._tts_buffer)
    if len(sentences) > 1:
        complete = ''.join(sentences[:-1]).strip()
        if complete:
            self._speak_sentence(complete)  # 播放完整句子
        self._tts_buffer = sentences[-1]    # 保留残句
```

**示例**：AI 输出 `"你好！今天天气很好。继续..."`

```
第 1 次流式：delta="你好！今"
    buffer = "你好！今"
    sentences = ["你好！", "今"]
    → 播放 "你好！"，保留 "今"

第 2 次流式：delta="天天气很好。继续说"
    buffer = "今天天气很好。继续说"
    sentences = ["今天天气很好。", "继续说"]
    → 播放 "今天天气很好。"，保留 "继续说"

回复完成：_flush_tts_stream() → 播放 "继续说"
```

### 8.4 播放完成后的重新聆听

```
最后一句流式朗读完成
    │
    ▼
TTSEngine._async_speak_worker → callback
    │
    ▼
VoiceBridge._on_stream_tts_done()
    │
    ├─ 检查：_voice_chat_active && _ai_reply_done
    │
    ├─ _ai_reply_done = false  // 标记已处理
    │
    └─ _restart_listening()
          ├─ 前端提示 "🎤 聆听中...（继续说）"
          └─ _asr.start()  // 重新开始聆听
```

### 8.5 关键时序图

```
用户发送 ─► VAD ─► 前端 sendMessage ─► ChatController ─► AI 客户端
                │                          │                 │
                │                    流式内容回调              │
                │                          │◄────────────────┘
                │                          ▼
                │              on_stream_update (累积全文)
                │                          │
                │                    增量提取 + 断句
                │                          │
                │                   speak_stream(句子) ──► SAPI 播放
                │                          │
                │                   ... 多轮 ...
                │                          │
                │              on_stream_complete
                │                          │
                │                   flush + on_ai_reply_complete
                │                          │
                │              最后一句播完 → _restart_listening ◄──┐
                │                          │                          │
                └───────（等待用户继续说）────────────────────────────┘
```

---

## 9. 音色配置与管理

### 9.1 配置来源

音色存储在 `user_config/defaults/agent_config.json`（及用户自定义覆盖）：

```json
{
  "voice": "小男孩"
}
```

### 9.2 启动时应用（_apply_voice_from_config）

```
VoiceBridge.__init__
    │
    └─ _apply_voice_from_config()
         │
         ├─ 读取 agent_config.json 的 "voice" 字段
         │     ├─ 存在 → 使用配置的音色名
         │     └─ 不存在/读失败 → 默认 "小男孩"
         │
         └─ self._tts.set_voice(voice)
               └─ 更新音色预设 + 重启常驻 SAPI 进程
```

### 9.3 运行时切换（setVoice）

```
前端设置面板 → setVoice(voice_name)
    │
    ├─ 校验 voice_name 在 VOICE_PRESETS 中？──否──► 返回 false
    │是
    ├─ _tts.set_voice(voice_name)
    │     └─ 更新预设 + _kill_proc() 重启常驻进程
    │
    └─ 返回 true（实时生效）
```

---

## 10. 前端交互与回调

### 10.1 前端 → 后端

```
voiceInput.toggle()          → voice_bridge.startVoiceChat() / stopVoiceChat()
voiceInput._start()          → voice_bridge.startListening()
voiceInput._stop()           → voice_bridge.stopListening()
voiceInput.init()            → voice_bridge.checkModel()
```

### 10.2 后端 → 前端（execute_js 推送）

| 前端回调 | 触发场景 | 示例 |
|---------|---------|------|
| `onVoicePartial(text)` | ASR 部分识别结果 | 实时更新输入框 |
| `onVoiceFinal(text)` | ASR 一句话确定（非交互模式） | 录音结束显示结果 |
| `onVoiceStatus(status)` | 状态变更 | "🎤 正在聆听..." / "🎤 聆听中...（继续说）" |

### 10.3 输入框内容合并逻辑

```
识别的文字 = _savedInput + (分隔符) + 识别文本
```

- `_savedInput`：开始录音前输入框已有内容（按下麦克风时保存）
- 分隔符：若 `_savedInput` 以 `\n` 结尾则不添加分隔符，否则添加空格

---

## 11. 资源清理与异常处理

### 11.1 清理流程

| 场景 | 调用 | 清理内容 |
|------|------|---------|
| 退出语音交互模式 | `VoiceBridge.stopVoiceChat()` | ASR `cancel()` + TTS `stop()` |
| 应用退出 | `VoiceBridge.cleanup()` | ASR `cleanup()` + TTS `cleanup()` + 重置状态 |
| 切换音色 | `TTSEngine.set_voice()` | 重启常驻 SAPI 进程（`_kill_proc()`） |

### 11.2 异常处理策略

| 异常场景 | 处理方式 |
|---------|---------|
| 未安装 pyaudio | ASR 发送 "未安装 pyaudio" 状态，停止聆听 |
| 模型不存在 | `check_model()` 返回 `{ok: false}`，前端警告 |
| SAPI 朗读失败 | 捕获异常打印日志，不阻塞主流程 |
| 音色配置读取失败 | 回退默认音色 "小男孩" |
| execute_js 执行失败 | 各 emit 方法捕获异常，不抛到上层 |

### 11.3 线程安全

- **TTS 管道**：`_write_lock` 保证写入顺序与 `__DONE__` 回报顺序一致
- **ASR 线程**：`_stop_event`（threading.Event）控制聆听循环退出
- **TTS 代际**：`_generation` 递增 + 比对，避免旧朗读线程的回调串扰新朗读

---

## 附录：方法速查表

### VoiceBridge 对外接口

| 方法 | 类型 | 说明 |
|------|------|------|
| `startListening()` | @pyqtSlot() | 开始单次语音识别 |
| `stopListening()` | @pyqtSlot() | 停止识别并返回结果 |
| `speakText(text)` | @pyqtSlot(str) | 朗读指定文本 |
| `speak_stream(text)` | 内部方法 | 流式朗读（ChatBridge 调用） |
| `setVoice(name)` | @pyqtSlot(str) | 切换音色 |
| `getVoice()` | @pyqtSlot(result=str) | 获取当前音色 |
| `startVoiceChat()` | @pyqtSlot() | 开启语音交互模式 |
| `stopVoiceChat()` | @pyqtSlot() | 退出语音交互模式 |
| `checkModel()` | @pyqtSlot(result=str) | 检查模型可用性 |
| `on_ai_reply_complete(reply)` | 内部方法 | AI 回复完成回调（ChatBridge 调用） |
| `cleanup()` | 内部方法 | 清理资源 |

### TTSEngine 对外接口

| 方法 | 说明 |
|------|------|
| `speak(text)` | 同步朗读（阻塞） |
| `speak_async(text, on_done)` | 异步抢占式朗读 |
| `speak_stream(text, on_done)` | 流式入队朗读 |
| `stop()` | 停止并清空队列 |
| `set_voice(name)` | 切换音色 |
| `is_speaking` | 是否正在播放 |
| `list_voice_names()` | 列出可用音色 |

### SpeechRecognizer 对外接口

| 方法 | 说明 |
|------|------|
| `start()` | 开始聆听（后台线程） |
| `stop()` | 停止并返回已识别文本 |
| `cancel()` | 取消并丢弃结果 |
| `set_vad_enabled(bool)` | 开关 VAD 静音检测 |
| `set_vad_silence(sec)` | 设置静音阈值 |
| `check_model()` | 检查模型是否可用 |
| `cleanup()` | 释放资源 |