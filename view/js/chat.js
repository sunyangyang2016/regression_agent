// ============================================
// chatApp - 聊天控制器
// ============================================
window.chatApp = {
    messages: [],
    isProcessing: false,
    _currentAssistantId: null,

    // Token 和上下文统计数据
    tokenStats: {
        totalTokens: 0,
        inputTokens: 0,
        hitTokens: 0,
        missTokens: 0,
        outputTokens: 0,
        contextPercent: 0,
        cost: 0,
        maxContext: 65536
    },

    // AI 通信日志
    aiLogs: [],

    // 更新状态条显示
    updateStatusBar: function(stats) {
        if (stats) {
            this.tokenStats.totalTokens = stats.totalTokens || 0;
            this.tokenStats.inputTokens = stats.inputTokens || 0;
            this.tokenStats.hitTokens = stats.hitTokens || 0;
            this.tokenStats.missTokens = stats.missTokens || 0;
            this.tokenStats.outputTokens = stats.outputTokens || 0;
            this.tokenStats.contextPercent = stats.contextPercent || 0;
            this.tokenStats.cost = stats.cost || 0;
            if (stats.maxContext) this.tokenStats.maxContext = stats.maxContext;
        }
        var s = this.tokenStats;
        var tokenEl = document.getElementById('tokenCount');
        var barEl = document.getElementById('contextBarFill');
        var pctEl = document.getElementById('contextPercent');
        var costEl = document.getElementById('costDisplay');
        // 命中/未命中/输出 分类显示（命中 = hit，未命中 = miss）
        var hitTokenEl = document.getElementById('hitTokenCount');
        var missTokenEl = document.getElementById('missTokenCount');
        var outputTokenEl = document.getElementById('outputTokenCount');
        if (tokenEl) tokenEl.textContent = s.totalTokens >= 1000 ? (s.totalTokens/1000).toFixed(1)+'K' : s.totalTokens;
        if (hitTokenEl) hitTokenEl.textContent = s.hitTokens >= 1000 ? (s.hitTokens/1000).toFixed(1)+'K' : s.hitTokens;
        if (missTokenEl) missTokenEl.textContent = s.missTokens >= 1000 ? (s.missTokens/1000).toFixed(1)+'K' : s.missTokens;
        if (outputTokenEl) outputTokenEl.textContent = s.outputTokens >= 1000 ? (s.outputTokens/1000).toFixed(1)+'K' : s.outputTokens;
        if (barEl) {
            var pct = Math.min(s.contextPercent, 100);
            barEl.style.width = pct + '%';
            barEl.className = 'context-bar-fill' + (pct > 80 ? ' danger' : pct > 60 ? ' warning' : '');
        }
        if (pctEl) pctEl.textContent = Math.round(s.contextPercent) + '%';
        if (costEl) costEl.textContent = '$' + s.cost.toFixed(4);
    },

    // 添加 AI 通信日志条目（默认最多保留 200 条，避免无限增长拖慢渲染）
    addLogEntry: function(entry) {
        this.aiLogs.push(entry);
        // 超过上限时丢弃最旧的日志（先入先出）
        var MAX_LOG_ENTRIES = 200;
        if (this.aiLogs.length > MAX_LOG_ENTRIES) {
            this.aiLogs.splice(0, this.aiLogs.length - MAX_LOG_ENTRIES);
        }
        // 更新日志徽章
        var badge = document.getElementById('logBadge');
        if (badge) {
            badge.textContent = this.aiLogs.length;
            badge.style.display = 'inline-flex';
        }
        // 如果日志面板已打开：无过滤条件时走增量渲染（只 append 新 DOM），
        // 有过滤条件时才全量重渲染（保证过滤结果正确）
        var modal = document.getElementById('logModal');
        if (modal && modal.style.display !== 'none') {
            var hasFilter = (typeof logFilterState !== 'undefined') &&
                (logFilterState.start !== null || logFilterState.end !== null);
            if (hasFilter && typeof renderFilteredLogs === 'function') {
                renderFilteredLogs();
            } else if (typeof appendLogEntry === 'function') {
                appendLogEntry(entry);
            } else if (typeof renderFilteredLogs === 'function') {
                renderFilteredLogs();
            }
        }
    },

    sendMessage: function() {
        var input = document.getElementById('messageInput');
        var content = input.value.trim();
        if (!content) return;
        // 开新一轮对话：重置工具锚点（多轮工具调用时顺序插入用）
        this._lastToolAnchor = null;
        // AI 回复中发送新消息：允许（后端会先中断旧回复再处理新消息）
        if (this.isProcessing) {
            console.log('[chatApp] AI 回复中，先中断旧回复再发送新消息');
            // 新消息接管：不显示「已中断」标记（旧气泡保留原样）
            this._stopRequested = false;
            // 标记旧回复为已中断（防止 _currentAssistantId 被覆盖后丢失引用）
            if (this._currentAssistantId) {
                var oldEl = document.getElementById(this._currentAssistantId);
                if (oldEl && !oldEl.getAttribute('data-interrupted')) {
                    oldEl.setAttribute('data-interrupted', 'true');
                    if (oldEl.textContent.trim() !== '') {
                        oldEl.textContent = oldEl.textContent + '\n\n⏹️ 已中断';
                    } else {
                        oldEl.textContent = '⏹️ 已中断';
                    }
                }
            }
        }
        var welcome = document.getElementById('welcomeScreen');
        if (welcome) welcome.remove();
        this.addMessage('user', content);
        input.value = ''; autoResize(input);
        this.isProcessing = true;
        document.getElementById('sendBtn').disabled = false;
        this._currentAssistantId = this.addMessage('assistant', '');
        this.setSendButtonStopMode(true);
        // 通过桥接调用后端 AI
        if (window.py_bridge && typeof window.py_bridge.sendToAI === 'function') {
            console.log('[chatApp] 通过桥接发送到 AI:', content);
            try { window.py_bridge.sendToAI(content); }
            catch(e) { console.error('[chatApp] sendToAI 失败:', e); this._simulateResponse(); }
        } else {
            console.log('[chatApp] 桥接未就绪，使用模拟响应');
            this._simulateResponse();
        }
    },

    // 切换发送按钮为「停止」模式（AI 回复中）
    setSendButtonStopMode: function(isStop) {
        var btn = document.getElementById('sendBtn');
        if (!btn) return;
        var icon = btn.querySelector('i');
        var text = btn.querySelector('.send-text');
        if (isStop) {
            btn.classList.add('stop-mode');
            btn.disabled = false;
            // 点击行为切换为「停止」（通过 setAttribute 保留 onclick 属性）
            btn.setAttribute('onclick', 'event.preventDefault();event.stopPropagation();stopAI()');
            if (icon) icon.className = 'fas fa-stop';
            if (text) text.textContent = '停止';
        } else {
            btn.classList.remove('stop-mode');
            btn.disabled = false;
            // 恢复为正常发送（恢复 HTML 属性中的 onClick）
            btn.setAttribute('onclick', 'sendMessage()');
            if (icon) icon.className = 'fas fa-paper-plane';
            if (text) text.textContent = '发送';
        }
    },

    // 停止 AI 回复
    stopAI: function() {
        console.log('[chatApp] 用户点击停止按钮');
        this._stopRequested = true;
        if (window.py_bridge && typeof window.py_bridge.stopAI === 'function') {
            try { window.py_bridge.stopAI(); }
            catch(e) { console.error('[chatApp] stopAI 失败:', e); }
        }
    },

    // 压缩当前会话上下文（用户主动触发）
    compressContext: function() {
        console.log('[chatApp] 用户点击压缩上下文按钮');
        if (window.py_bridge && typeof window.py_bridge.compressContext === 'function') {
            try { window.py_bridge.compressContext(); }
            catch(e) { console.error('[chatApp] compressContext 失败:', e); }
        } else {
            if (typeof showToast === 'function') showToast('桥接未就绪，无法压缩上下文', 'error');
        }
    },

    _simulateResponse: function() {
        var self = this;
        var msgId = this._currentAssistantId;
        setTimeout(function() {
            if (document.getElementById(msgId)) {
                document.getElementById(msgId).textContent = '收到！';
                self.completeMessage(msgId);
            }
        }, 500);
    },

    _scrollToBottom: function() {
        var el = document.querySelector('.chat-container');
        if (el) { el.scrollTop = el.scrollHeight; return; }
        var container = document.getElementById('chatMessages');
        if (container) container.scrollTop = container.scrollHeight;
    },

    addMessage: function(role, content) {
        var container = document.getElementById('chatMessages');
        var icons = {user:'fa-user', assistant:'fa-robot', tool:'fa-plug'};
        var names = {user:'user', assistant:appState.currentModel?.name||'AI', tool:'tool'};
        var id = 'msg_'+Date.now()+'_'+Math.random().toString(36).substr(2,4);
        var div = document.createElement('div');
        div.className = 'message ' + role;
        
        if (role === 'tool') {
            div.innerHTML = '<div class="message-avatar tool"><i class="fas fa-plug"></i></div>' +
                '<div class="message-content">' +
                '<div class="message-header"><span class="message-role">tool</span>' +
                '<span class="message-time">'+new Date().toLocaleTimeString()+'</span></div>' +
                '<div class="message-body" id="'+id+'"></div></div>';
            // 工具结果可能含 HTML/CSS 片段（如 get_weather 返回 <link>），
            // 必须用 textContent 防止注入导致页面背景/样式被篡改。
            // 注意：div 尚未插入 document，不能 document.getElementById，须用 div 子树查找
            div.querySelector('.message-body').textContent = content || '';
        } else {
            div.innerHTML = '<div class="message-avatar '+role+'"><i class="fas '+(icons[role]||'fa-user')+'"></i></div>' +
                '<div class="message-content">' +
                '<div class="message-header"><span class="message-role">'+(names[role]||role)+'</span>' +
                '<span class="message-time">'+new Date().toLocaleTimeString()+'</span></div>' +
                '<div class="message-body" id="'+id+'">'+content+'</div></div>';
        }
        container.appendChild(div);
        this._scrollToBottom();
        this.messages.push({id:id,role:role,content:content||''});
        return id;
    },

    // 插入工具调用消息：
    // 1) 若当前 assistant 气泡有中间文本（工具调用前的 AI 输出），封存为独立气泡并断开引用，
    //    后续 AI 最终回答自动新建气泡 → 与会话历史保存的「中间轮 / tool / 最终」分开显示一致
    // 2) 若当前 assistant 气泡为空（第一轮直接调工具），移除空气泡
    // 3) 工具消息插入位置：封存气泡之后 / 上一 tool 之后 / 末尾
    insertToolMessage: function(content) {
        var container = document.getElementById('chatMessages');
        if (!container) return null;
        var id = 'msg_'+Date.now()+'_'+Math.random().toString(36).substr(2,4);
        var div = document.createElement('div');
        div.className = 'message tool';
        div.innerHTML = '<div class="message-avatar tool"><i class="fas fa-plug"></i></div>' +
            '<div class="message-content">' +
            '<div class="message-header"><span class="message-role">tool</span>' +
            '<span class="message-time">'+new Date().toLocaleTimeString()+'</span></div>' +
            '<div class="message-body" id="'+id+'"></div></div>';
        // 工具结果可能含 HTML/CSS 片段，用 textContent 防止注入篡改页面背景/样式。
        // 注意：div 尚未插入 document，不能 document.getElementById，须用 div 子树查找
        div.querySelector('.message-body').textContent = content || '';

        // ===== 封存当前 assistant 气泡 =====
        var anchor = null;
        if (this._currentAssistantId) {
            var bodyEl = document.getElementById(this._currentAssistantId);
            if (bodyEl) {
                var msgEl = bodyEl.closest('.message');
                if (msgEl) {
                    if (!bodyEl.textContent.trim()) {
                        // 气泡为空（第一轮直接调工具，无中间文本）：移除空气泡
                        if (msgEl.parentNode) msgEl.parentNode.removeChild(msgEl);
                    } else {
                        // 有中间文本：封存为独立气泡，tool 插入其后
                        anchor = msgEl;
                    }
                }
            }
            // 断开引用：后续 AI 输出（最终回答）自动新建气泡
            this._currentAssistantId = null;
        }

        // ===== 工具消息插入位置 =====
        if (anchor && anchor.parentNode) {
            // 中间文本气泡之后（最终回答新建气泡会排在 tool 后）
            anchor.parentNode.insertBefore(div, anchor.nextSibling);
        } else if (this._lastToolAnchor && this._lastToolAnchor.parentNode) {
            // 多个工具连续调用：保持顺序，插到上一个 tool 之后
            this._lastToolAnchor.parentNode.insertBefore(div, this._lastToolAnchor.nextSibling);
        } else {
            container.appendChild(div);
        }
        this._lastToolAnchor = div;
        this._scrollToBottom();
        this.messages.push({id:id, role:'tool', content:content||''});
        return id;
    },

    completeMessage: function(messageId) {
        var id = messageId;
        if (!id) {
            var container = document.getElementById('chatMessages');
            if (!container) return;
            var msgs = container.querySelectorAll('.message');
            for (var i = msgs.length - 1; i >= 0; i--) {
                var avatar = msgs[i].querySelector('.message-avatar');
                if (avatar && avatar.classList.contains('assistant')) {
                    var body = msgs[i].querySelector('.message-body');
                    if (body) { id = body.id; break; }
                }
            }
        }
        if (id) {
            var contentDiv = document.getElementById(id)?.closest('.message')?.querySelector('.message-content');
            if (contentDiv && !contentDiv.querySelector('.message-actions')) {
                var actions = document.createElement('div');
                actions.className = 'message-actions';
                actions.innerHTML = '<button onclick="showToast(\'已复制\',\'success\')"><i class="fas fa-copy"></i> 复制</button><button onclick="showToast(\'重新生成中\',\'info\')"><i class="fas fa-redo"></i> 重新生成</button>';
                contentDiv.appendChild(actions);
            }
        }
        this.isProcessing = false;
        this._currentAssistantId = null;
        this._lastToolAnchor = null;
        this.setSendButtonStopMode(false);
        document.getElementById('sendBtn').disabled = false;
        document.getElementById('messageInput').focus();
    },

    newChat: function() {
        this._lastToolAnchor = null;
        document.getElementById('chatTitle').textContent = '新对话';
        var html = '<div class="welcome-screen" id="welcomeScreen">' +
            '<div class="welcome-icon">🤖</div>' +
            '<h1 class="welcome-title">AI 智能助手</h1>' +
            '<p class="welcome-subtitle">基于 <strong>'+(appState.currentModel?.name||'AI')+'</strong> 模型</p>' +
            '<div class="quick-actions">' +
            '<div class="quick-action" onclick="chatApp.quickAction(\'写一个 Python 函数\')"><i class="fas fa-code"></i><span class="label">写代码</span></div>' +
            '<div class="quick-action" onclick="chatApp.quickAction(\'帮我解释这个概念\')"><i class="fas fa-lightbulb"></i><span class="label">解释概念</span></div>' +
            '<div class="quick-action" onclick="chatApp.quickAction(\'分析这段数据\')"><i class="fas fa-chart-bar"></i><span class="label">分析数据</span></div>' +
            '<div class="quick-action" onclick="chatApp.quickAction(\'翻译成中文\')"><i class="fas fa-language"></i><span class="label">翻译</span></div></div></div>';
        document.getElementById('chatMessages').innerHTML = html;
        this.messages = [];
        // 重置 token 统计并刷新 UI（累计费用由 token 推导，同步归零）
        this.tokenStats = {
            totalTokens: 0,
            inputTokens: 0,
            hitTokens: 0,
            missTokens: 0,
            outputTokens: 0,
            contextPercent: 0,
            cost: 0,
            maxContext: 65536
        };
        this.updateStatusBar();
        // 清空日志（新对话无历史日志）
        this.clearLogs();
        document.getElementById('messageInput').focus();
        showToast('新对话已创建', 'success');
    },

    // 清空当前日志及徽章
    clearLogs: function() {
        this.aiLogs = [];
        var badge = document.getElementById('logBadge');
        if (badge) {
            badge.textContent = '0';
            badge.style.display = 'none';
        }
        // 若日志面板已打开，显示空状态（由 chat_log.js 渲染）
        if (typeof renderFilteredLogs === 'function') {
            var modal = document.getElementById('logModal');
            if (modal && modal.style.display !== 'none') {
                renderFilteredLogs();
            }
        }
    },

    quickAction: function(text) {
        document.getElementById('messageInput').value = text;
        this.sendMessage();
    }
};

// ============================================
// 后端回调 — 由 Python MainBridge 调用
// ============================================
window.onStreamUpdate = function(content) {
    var id = window.chatApp._currentAssistantId;
    if (!id) {
        // 没有当前 AI 消息时（如多轮工具调用后），创建一个新的
        id = window.chatApp.addMessage('assistant', '');
        window.chatApp._currentAssistantId = id;
    }
    if (id) {
        var el = document.getElementById(id);
        if (el && typeof formatMessage === 'function') {
            el.innerHTML = formatMessage(content);
        } else if (el) {
            el.textContent = content;
        }
        // 每次更新内容后自动向下滚动（使用 .chat-container 因为它是 overflow-y:auto 的容器）
        var scrollEl = document.querySelector('.chat-container');
        if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight;
    }
};
window.onStreamComplete = function() {
    window.chatApp.completeMessage();
};
window.onSetProcessing = function(processing) {
    window.chatApp.isProcessing = processing;
    if (processing) {
        window.chatApp.setSendButtonStopMode(true);
    } else {
        window.chatApp.setSendButtonStopMode(false);
    }
};
// AI 流被中断（用户点击停止按钮时触发）
window.onAIStopped = function() {
    // 只有用户点击停止时才标记「已中断」；发送新消息接管时 _stopRequested 为 false 不标记
    if (window.chatApp._stopRequested && window.chatApp._currentAssistantId) {
        var el = document.getElementById(window.chatApp._currentAssistantId);
        if (el && !el.getAttribute('data-interrupted')) {
            el.setAttribute('data-interrupted', 'true');
            if (el.textContent.trim() !== '') {
                el.textContent = el.textContent + '\n\n⏹️ 已中断';
            } else {
                el.textContent = '⏹️ 已中断';
            }
        }
    }
    window.chatApp._stopRequested = false;
    window.chatApp.completeMessage();
};
window.onShowError = function(errorMsg) {
    if (window.chatApp._currentAssistantId) {
        var el = document.getElementById(window.chatApp._currentAssistantId);
        if (el) el.textContent = '❌ ' + errorMsg;
    }
    window.chatApp.completeMessage();
};
// ============================================
// 后端回调 — Token 更新
// ============================================

// 由后端推送 token 统计数据
window.onTokenUpdate = function(stats) {
    // stats: { totalTokens, inputTokens, hitTokens, missTokens, outputTokens, contextPercent, cost, maxContext }
    if (typeof stats === 'string') {
        try { stats = JSON.parse(stats); } catch(e) { return; }
    }
    window.chatApp.updateStatusBar(stats);
};

function handleInputKeydown(e) {
    if(e.key==='Enter'&&!e.shiftKey){
        e.preventDefault();
        // AI 回复中按 Enter：如果输入框有内容则发送新消息（会中断旧回复）
        window.chatApp.sendMessage();
    }
}
function sendMessage() { window.chatApp.sendMessage(); }
function stopAI() { window.chatApp.stopAI(); }
function compressContext() { window.chatApp.compressContext(); }
function newChat() {
    window.chatApp.newChat();
    // 通知后端创建新会话并刷新侧边栏
    if (window.py_bridge) {
        try {
            window.py_bridge.newConversation();
        } catch(e) { console.warn('[Chat] newConversation:', e); }
    }
    if (typeof closeSidebar==='function') closeSidebar();
}
function quickAction(text) { window.chatApp.quickAction(text); }
function autoResize(t){t.style.height='auto';t.style.height=Math.min(t.scrollHeight,150)+'px';}
