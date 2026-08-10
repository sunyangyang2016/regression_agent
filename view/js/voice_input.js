// ============================================
// 语音输入控制 - 使用 Vosk + PyAudio 实现中文语音识别
// 识别文字实时显示到输入框
// ============================================
window.voiceInput = {
    _listening: false,
    _voiceChatMode: false,  // 语音交互模式（连续语音对话）
    _savedInput: "",   // 开始录音前输入框已有内容

    // 初始化：检查桥接与模型可用性
    init: function() {
        var check = setInterval(function() {
            if (window.voice_bridge) {
                clearInterval(check);
                try {
                    var res = window.voice_bridge.checkModel();
                    if (res && typeof res === 'string') {
                        var data = JSON.parse(res);
                        if (data && data.ok) {
                            console.log('[VoiceInput] ✅ 语音模型可用');
                        } else {
                            console.warn('[VoiceInput] ❌ 语音模型不可用:', data);
                        }
                    }
                } catch(e) {
                    console.warn('[VoiceInput] 检查模型失败:', e);
                }
            }
        }, 500);
    },

    // 切换语音输入（点击麦克风按钮）
    toggle: function() {
        if (!window.voice_bridge) {
            if (typeof showToast === 'function') showToast('语音识别的桥接未就绪', 'error');
            return;
        }
        // 如果处于语音交互模式 → 退出
        if (this._voiceChatMode) {
            this._exitVoiceChat();
            return;
        }
        // 如果处于单次录音中 → 停止
        if (this._listening) {
            this._stop();
            return;
        }
        // 否则：进入语音交互模式（连续语音对话）
        this._enterVoiceChat();
    },

    // ===== 语音交互模式（连续语音对话）=====
    _enterVoiceChat: function() {
        this._voiceChatMode = true;
        var btn = document.getElementById('voiceBtn');
        if (btn) btn.classList.add('voice-chat');
        if (typeof showToast === 'function') showToast('🎤 语音对话模式开启（说话自动发送+语音朗读）', 'info');
        try {
            window.voice_bridge.startVoiceChat();
        } catch(e) {
            console.error('[VoiceInput] 进入语音交互模式失败:', e);
            this._voiceChatMode = false;
            if (btn) btn.classList.remove('voice-chat');
        }
    },

    _exitVoiceChat: function() {
        this._voiceChatMode = false;
        var btn = document.getElementById('voiceBtn');
        if (btn) btn.classList.remove('voice-chat');
        if (typeof showToast === 'function') showToast('语音对话模式已退出', 'info');
        try {
            window.voice_bridge.stopVoiceChat();
        } catch(e) {
            console.error('[VoiceInput] 退出语音交互模式失败:', e);
        }
    },

    _start: function() {
        this._listening = true;
        // 保存当前输入框已有内容，识别文字追加在后面
        var input = document.getElementById('messageInput');
        if (input) {
            this._savedInput = input.value;
        } else {
            this._savedInput = '';
        }
        var btn = document.getElementById('voiceBtn');
        if (btn) btn.classList.add('listening');
        try {
            window.voice_bridge.startListening();
        } catch(e) {
            console.error('[VoiceInput] 启动失败:', e);
            this._listening = false;
            if (btn) btn.classList.remove('listening');
            if (typeof showToast === 'function') showToast('启动语音识别失败', 'error');
        }
    },

    _stop: function() {
        var btn = document.getElementById('voiceBtn');
        if (btn) btn.classList.remove('listening');
        try {
            window.voice_bridge.stopListening();
        } catch(e) {
            console.error('[VoiceInput] 停止失败:', e);
        }
        this._listening = false;
    },

    // 更新输入框内容（识别文字 + 已有内容）
    _updateInput: function(spokenText) {
        var input = document.getElementById('messageInput');
        if (!input) return;
        var base = this._savedInput || '';
        if (spokenText) {
            if (base) {
                input.value = base + (base.endsWith('\n') ? '' : ' ') + spokenText;
            } else {
                input.value = spokenText;
            }
        } else if (base) {
            input.value = base;
        }
        if (typeof autoResize === 'function') autoResize(input);
    }
};

// 后端回调：实时部分识别结果（随时更新输入框）
window.onVoicePartial = function(text) {
    var input = document.getElementById('messageInput');
    if (!input) return;
    var base = window.voiceInput._savedInput || '';
    if (text) {
        input.value = base ? (base + (base.endsWith('\n') ? '' : ' ') + text) : text;
    } else {
        input.value = base;
    }
    if (typeof autoResize === 'function') autoResize(input);
};

// 后端回调：最终识别结果（录音结束后调用）
window.onVoiceFinal = function(text) {
    var input = document.getElementById('messageInput');
    if (!input) return;
    var base = window.voiceInput._savedInput || '';
    if (text) {
        input.value = base ? (base + (base.endsWith('\n') ? '' : ' ') + text) : text;
    } else {
        input.value = base;
    }
    if (typeof autoResize === 'function') autoResize(input);
    input.focus();
    window.voiceInput._savedInput = '';
    if (text) {
        if (typeof showToast === 'function') showToast('🎤 识别完成', 'success');
    } else {
        if (typeof showToast === 'function') showToast('未识别到语音内容', 'info');
    }
    var btn = document.getElementById('voiceBtn');
    if (btn) btn.classList.remove('listening');
    window.voiceInput._listening = false;
};

// 后端回调：状态更新
window.onVoiceStatus = function(status) {
    console.log('[VoiceInput] 状态:', status);
    if (typeof showToast === 'function' && status) showToast(status, 'info');
};

// 全局函数：切换语音输入（HTML onclick 调用）
function toggleVoiceInput() {
    window.voiceInput.toggle();
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        window.voiceInput.init();
    }, 1000);
});