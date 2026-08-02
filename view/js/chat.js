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
        outputTokens: 0,
        contextPercent: 0,
        cost: 0,
        maxContext: 8192
    },

    // AI 通信日志
    aiLogs: [],

    // 更新状态条显示
    updateStatusBar: function(stats) {
        if (stats) {
            this.tokenStats.totalTokens = stats.totalTokens || 0;
            this.tokenStats.inputTokens = stats.inputTokens || 0;
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
        if (tokenEl) tokenEl.textContent = s.totalTokens >= 1000 ? (s.totalTokens/1000).toFixed(1)+'K' : s.totalTokens;
        if (barEl) {
            var pct = Math.min(s.contextPercent, 100);
            barEl.style.width = pct + '%';
            barEl.className = 'context-bar-fill' + (pct > 80 ? ' danger' : pct > 60 ? ' warning' : '');
        }
        if (pctEl) pctEl.textContent = Math.round(s.contextPercent) + '%';
        if (costEl) costEl.textContent = '$' + s.cost.toFixed(4);
    },

    // 添加 AI 通信日志条目
    addLogEntry: function(entry) {
        this.aiLogs.push(entry);
        // 更新日志徽章
        var badge = document.getElementById('logBadge');
        if (badge) {
            badge.textContent = this.aiLogs.length;
            badge.style.display = 'inline-flex';
        }
        // 如果日志面板已打开，交由 chat_log.js 渲染（应用时间过滤）
        if (typeof renderFilteredLogs === 'function') {
            var modal = document.getElementById('logModal');
            if (modal && modal.style.display !== 'none') {
                renderFilteredLogs();
            }
        }
    },

    sendMessage: function() {
        var input = document.getElementById('messageInput');
        var content = input.value.trim();
        if (!content || this.isProcessing) return;
        var welcome = document.getElementById('welcomeScreen');
        if (welcome) welcome.remove();
        this.addMessage('user', content);
        input.value = ''; autoResize(input);
        this.isProcessing = true;
        document.getElementById('sendBtn').disabled = true;
        this._currentAssistantId = this.addMessage('assistant', '');
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
        var names = {user:'你', assistant:appState.currentModel?.name||'AI', tool:'工具调用'};
        var id = 'msg_'+Date.now()+'_'+Math.random().toString(36).substr(2,4);
        var div = document.createElement('div');
        div.className = 'message ' + role;
        
        if (role === 'tool') {
            div.innerHTML = '<div class="message-avatar tool"><i class="fas fa-plug"></i></div>' +
                '<div class="message-content">' +
                '<div class="message-header"><span class="message-role">🔧 工具</span>' +
                '<span class="message-time">'+new Date().toLocaleTimeString()+'</span></div>' +
                '<div class="message-body" id="'+id+'" style="font-family:monospace;font-size:12px;background:var(--bg-tertiary);padding:8px 12px;border-radius:var(--radius-sm);white-space:pre-wrap;word-break:break-all;">'+content+'</div></div>';
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
        document.getElementById('sendBtn').disabled = false;
        document.getElementById('messageInput').focus();
    },

    newChat: function() {
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
            outputTokens: 0,
            contextPercent: 0,
            cost: 0,
            maxContext: 8192
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
    document.getElementById('sendBtn').disabled = processing;
};
window.onShowError = function(errorMsg) {
    if (window.chatApp._currentAssistantId) {
        var el = document.getElementById(window.chatApp._currentAssistantId);
        if (el) el.textContent = '❌ ' + errorMsg;
    }
    window.chatApp.completeMessage();
};
window.onAddToolCall = function(toolName, argsJson, result) {
    var container = document.getElementById('chatMessages');
    if (!container) return;
    
    // argsJson 可能是对象也可能是字符串，统一转成字符串处理
    var argsStr = typeof argsJson === 'string' ? argsJson : JSON.stringify(argsJson);
    
    // ====== 过滤空参数或无意义的调用 ======
    if ((!argsStr || argsStr === '{}') && (!result || result.length < 5)) return;
    
    var div = document.createElement('div');
    div.style.cssText = 'background:var(--bg-tertiary);border:1px solid var(--border-color);border-radius:var(--radius-md);padding:12px 16px;margin:8px 0;font-size:13px;';
    
    var html = '<div style="display:flex;align-items:center;gap:8px;color:var(--text-secondary);margin-bottom:6px;">';
    html += '<i class="fas fa-plug" style="color:var(--accent-purple);"></i> <strong>工具调用:</strong> ' + toolName + '</div>';
    if (argsJson) {
        html += '<div style="font-family:monospace;background:var(--bg-secondary);padding:8px 12px;border-radius:var(--radius-sm);overflow-x:auto;margin-bottom:4px;color:var(--text-muted);font-size:12px;">参数: ' + argsJson + '</div>';
    }
    if (result && result.length >= 5) {
        var displayResult = result.length > 500 ? result.substring(0, 500) + '...' : result;
        html += '<div style="font-family:monospace;background:var(--bg-secondary);padding:8px 12px;border-radius:var(--radius-sm);overflow-x:auto;color:var(--text-primary);font-size:12px;white-space:pre-wrap;word-break:break-all;">📥 结果: ' + displayResult + '</div>';
    }
    div.innerHTML = html;
    container.appendChild(div);
    var scrollEl = document.querySelector('.chat-container');
    if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight;
    
    window.chatApp._currentAssistantId = null;
};

// ============================================
// 后端回调 — Token 更新
// ============================================

// 由后端推送 token 统计数据
window.onTokenUpdate = function(stats) {
    // stats: { totalTokens, inputTokens, outputTokens, contextPercent, cost, maxContext }
    if (typeof stats === 'string') {
        try { stats = JSON.parse(stats); } catch(e) { return; }
    }
    window.chatApp.updateStatusBar(stats);
};

function handleInputKeydown(e) { if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();window.chatApp.sendMessage();} }
function sendMessage() { window.chatApp.sendMessage(); }
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
