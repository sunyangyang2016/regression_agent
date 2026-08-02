// ============================================
// chat_log.js - AI 通信日志模块（独立逻辑）
// 负责日志悬浮窗渲染、拖动缩放、时间戳过滤
// ============================================

// ============================================
// 渲染单条日志条目
// - type: "raw" → 底层 AI 通信原始完整 JSON（request/response）
// ============================================
function renderLogEntry(entry) {
    var list = document.getElementById('logList');
    if (!list) return;
    var empty = list.querySelector('.log-empty');
    if (empty) empty.remove();

    var div = document.createElement('div');
    div.className = 'log-entry';
    div.style.marginBottom = '10px';

    // ====== 底层 AI 通信原始 JSON 日志（type: "raw"）======
    var isReq = entry.direction === 'request';
    var directionLabel = isReq ? '⬆️ 请求 (Request)' : '⬇️ 响应 (Response)';
    var accentColor = isReq ? 'var(--accent-primary)' : 'var(--accent-success)';

    var headerHtml = '<div class="log-entry-header" style="cursor:default;">' +
        '<div style="display:flex;align-items:center;gap:8px;">' +
        '<span style="font-weight:600;color:' + accentColor + ';">' + directionLabel + '</span>' +
        '<span class="log-model">' + escapeHtml(entry.model || 'AI') + '</span></div>' +
        '<span class="log-time">' + new Date((entry.timestamp || Date.now()) * 1000).toLocaleString() + '</span></div>';

    var rawJson = JSON.stringify(entry.data || {}, null, 2);
    var bodyHtml = '<div class="log-entry-body">' +
        '<pre style="margin:0;padding:10px 12px;font-size:11px;line-height:1.6;white-space:pre-wrap;word-break:break-all;background:var(--bg-primary);border:1px solid var(--border-color);border-left:3px solid ' + accentColor + ';border-radius:var(--radius-sm);max-height:400px;overflow-y:auto;color:var(--text-secondary);">' +
        escapeHtml(rawJson) + '</pre></div>';

    div.innerHTML = headerHtml + bodyHtml;
    list.appendChild(div);
    list.scrollTop = list.scrollHeight;
}

// ============================================
// 时间戳过滤
// ============================================

// 当前过滤条件（空表示不过滤）
var logFilterState = { start: null, end: null };

// 将 datetime-local 输入值转换为秒级时间戳（本地时区）；空值返回 null
function parseFilterTime(value, isEnd) {
    if (!value) return null;
    // datetime-local 格式: "YYYY-MM-DDTHH:mm[:ss]"（本地时间，无时区）
    var m = value.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/);
    if (!m) return null;
    var sec = m[6] !== undefined ? parseInt(m[6], 10) : (isEnd ? 59 : 0);
    // 结束时间缺省秒时补到 59，保证选中整分钟不会漏掉该分钟内的日志
    var ms = new Date(
        parseInt(m[1], 10),
        parseInt(m[2], 10) - 1,
        parseInt(m[3], 10),
        parseInt(m[4], 10),
        parseInt(m[5], 10),
        sec
    ).getTime();
    if (isNaN(ms)) return null;
    return Math.floor(ms / 1000);
}

// 判断日志条目是否匹配当前过滤条件
function logMatchesFilter(entry) {
    var ts = entry.timestamp || 0;
    if (logFilterState.start !== null && ts < logFilterState.start) return false;
    if (logFilterState.end !== null && ts > logFilterState.end) return false;
    return true;
}

// 重新渲染日志列表（应用当前过滤条件）
function renderFilteredLogs() {
    var modal = document.getElementById('logModal');
    if (!modal || modal.style.display === 'none') return;
    var list = document.getElementById('logList');
    if (!list) return;

    var all = (window.chatApp && window.chatApp.aiLogs) || [];
    var filtered = all.filter(logMatchesFilter);

    list.innerHTML = '';
    if (filtered.length === 0) {
        list.innerHTML = '<div class="log-empty">' +
            (all.length === 0 ? '暂无日志记录' : '没有匹配时间范围的日志') +
            '</div>';
    } else {
        filtered.forEach(function(entry) { renderLogEntry(entry); });
        list.scrollTop = list.scrollHeight;
    }

    // 更新过滤计数
    var countEl = document.getElementById('logFilterCount');
    if (countEl) {
        countEl.textContent = all.length === 0 ? '' : (filtered.length + ' / ' + all.length);
    }
}

// 应用时间戳范围过滤
function filterLogs() {
    var startEl = document.getElementById('logFilterStart');
    var endEl = document.getElementById('logFilterEnd');
    logFilterState.start = parseFilterTime(startEl ? startEl.value : '', false);
    logFilterState.end = parseFilterTime(endEl ? endEl.value : '', true);
    renderFilteredLogs();
}

// 清除时间过滤条件
function clearLogFilter() {
    var startEl = document.getElementById('logFilterStart');
    var endEl = document.getElementById('logFilterEnd');
    if (startEl) startEl.value = '';
    if (endEl) endEl.value = '';
    logFilterState.start = null;
    logFilterState.end = null;
    renderFilteredLogs();
}

// ============================================
// 悬浮窗控制
// ============================================

// 切换日志条目展开/收起
function toggleLogBody(headerEl) {
    var body = headerEl.nextElementSibling;
    var expand = headerEl.querySelector('.log-expand');
    if (body) {
        body.style.display = body.style.display === 'none' ? 'block' : 'none';
    }
    if (expand) {
        expand.classList.toggle('expanded');
    }
}

// 打开/关闭日志悬浮窗（非模态）
function toggleAILog(event) {
    if (event) event.stopPropagation();
    var modal = document.getElementById('logModal');
    if (!modal) return;
    if (modal.style.display === 'none') {
        openAILogWindow();
    } else {
        modal.style.display = 'none';
    }
}

// 打开日志悬浮窗并渲染内容
function openAILogWindow() {
    var modal = document.getElementById('logModal');
    if (!modal) return;
    modal.style.display = 'flex';
    renderFilteredLogs();
}

// 关闭日志悬浮窗
function closeAILog(event) {
    var modal = document.getElementById('logModal');
    if (modal) modal.style.display = 'none';
}

// 放大/缩小悬浮窗（切换预设尺寸）
function toggleLogSize() {
    var modal = document.getElementById('logModal');
    if (!modal) return;
    var icon = document.getElementById('logSizeIcon');
    var isLarge = modal.dataset.size === 'large';
    if (isLarge) {
        modal.style.width = '520px';
        modal.style.height = '400px';
        modal.dataset.size = 'default';
        if (icon) icon.className = 'fas fa-expand';
    } else {
        // 放大：按 1080p（1920×1080）比例计算，取视口 80%×88%（约 1536×950）
        modal.style.width = Math.min(Math.floor(window.innerWidth * 0.8), 1680) + 'px';
        modal.style.height = Math.min(Math.floor(window.innerHeight * 0.88), 950) + 'px';
        modal.dataset.size = 'large';
        if (icon) icon.className = 'fas fa-compress';
    }
}

// 拖动：按住标题栏拖动悬浮窗
function setupLogDrag() {
    var modal = document.getElementById('logModal');
    var header = document.getElementById('logModalHeader');
    if (!modal || !header) return;
    var dragging = false, offsetX = 0, offsetY = 0;

    header.addEventListener('mousedown', function(e) {
        if (e.target.closest('button')) return;
        dragging = true;
        var rect = modal.getBoundingClientRect();
        offsetX = e.clientX - rect.left;
        offsetY = e.clientY - rect.top;
        e.preventDefault();
    });
    document.addEventListener('mousemove', function(e) {
        if (!dragging) return;
        var x = Math.max(0, Math.min(e.clientX - offsetX, window.innerWidth - 60));
        var y = Math.max(0, Math.min(e.clientY - offsetY, window.innerHeight - 40));
        modal.style.left = x + 'px';
        modal.style.top = y + 'px';
        modal.style.right = 'auto';
        modal.style.bottom = 'auto';
    });
    document.addEventListener('mouseup', function() { dragging = false; });
}

// 缩放：拖拽右下角控制柄调整尺寸
function setupLogResize() {
    var modal = document.getElementById('logModal');
    var handle = document.getElementById('logResizeHandle');
    if (!modal || !handle) return;
    var resizing = false, startX = 0, startY = 0, startW = 0, startH = 0;

    handle.addEventListener('mousedown', function(e) {
        resizing = true;
        startX = e.clientX;
        startY = e.clientY;
        var rect = modal.getBoundingClientRect();
        startW = rect.width;
        startH = rect.height;
        e.preventDefault();
        e.stopPropagation();
    });
    document.addEventListener('mousemove', function(e) {
        if (!resizing) return;
        modal.style.width = Math.max(320, startW + (e.clientX - startX)) + 'px';
        modal.style.height = Math.max(240, startH + (e.clientY - startY)) + 'px';
        modal.style.resize = 'none';
        modal.dataset.size = 'custom';
    });
    document.addEventListener('mouseup', function() { resizing = false; });
}

// 初始化悬浮窗事件（页面加载完成后调用）
function initLogFloatWindow() {
    // 等待 #logModal 注入到主页面后再绑定事件
    if (!document.getElementById('logModal')) return;
    setupLogDrag();
    setupLogResize();
}

// 清空日志
function clearAILog() {
    if (!window.chatApp) return;
    window.chatApp.aiLogs = [];
    var badge = document.getElementById('logBadge');
    if (badge) {
        badge.style.display = 'none';
        badge.textContent = '0';
    }
    var list = document.getElementById('logList');
    if (list) list.innerHTML = '<div class="log-empty">暂无日志记录</div>';
    var countEl = document.getElementById('logFilterCount');
    if (countEl) countEl.textContent = '';
    showToast('日志已清空', 'success');
}

// HTML 转义工具函数
function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&' + 'amp;')
        .replace(/</g, '&' + 'lt;')
        .replace(/>/g, '&' + 'gt;')
        .replace(/"/g, '&' + 'quot;');
}

// ============================================
// 后端回调 — 日志推送 / 历史加载
// ============================================

// 由后端推送 AI 通信日志条目
window.onLogEntry = function(entry) {
    // entry: { timestamp, type, direction, model, data }
    if (typeof entry === 'string') {
        try { entry = JSON.parse(entry); } catch(e) { return; }
    }
    if (!window.chatApp) return;
    window.chatApp.addLogEntry(entry);
    // 若面板已打开且当前有过滤条件，重新渲染以应用过滤
    var modal = document.getElementById('logModal');
    if (modal && modal.style.display !== 'none' && (logFilterState.start !== null || logFilterState.end !== null)) {
        renderFilteredLogs();
    }
};

// 由后端加载历史会话的 AI 通信日志（切换历史会话时调用）
window.loadConversationLogs = function(logsJson) {
    // logsJson: JSON 字符串，是日志数组的序列化
    if (typeof logsJson === 'string') {
        try { logsJson = JSON.parse(logsJson); } catch(e) { logsJson = []; }
    }
    var logs = Array.isArray(logsJson) ? logsJson : [];
    if (!window.chatApp) return;
    window.chatApp.aiLogs = logs;
    // 更新日志徽章
    var badge = document.getElementById('logBadge');
    if (badge) {
        badge.textContent = String(logs.length);
        badge.style.display = logs.length > 0 ? 'inline-flex' : 'none';
    }
    // 若面板已打开，重新渲染（应用过滤）
    renderFilteredLogs();
    // 清空过滤条件，避免跨会话残留
    clearLogFilter();
};

// ============================================
// 日志模块初始化（绑定悬浮窗拖动/缩放事件）
// 悬浮窗 HTML 结构由 BridgeLoader 在加载页面时从
// view/html/chat_log.html 合并注入到 index.html
// ============================================
(function initChatLogModule() {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initLogFloatWindow);
    } else {
        initLogFloatWindow();
    }
})();
