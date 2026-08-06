// ============================================
// Sidebar - 左侧会话导航栏
// ============================================

// 侧边栏控制
function toggleSidebar() {
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebarOverlay');
    if (!sidebar) return;
    if (window.innerWidth <= 768) {
        // 移动端：切换 open class（通过 left 定位显示）
        sidebar.classList.toggle('open');
        if (overlay) overlay.classList.toggle('active');
    } else {
        // 桌面端：切换 collapsed class（通过 margin-left 收起）
        var isCollapsed = sidebar.classList.toggle('collapsed');
        // 折叠后显示 header 中的展开按钮（☰），展开后隐藏
        var headerMenuBtn = document.querySelector('.header-menu-btn');
        if (headerMenuBtn) headerMenuBtn.style.display = isCollapsed ? 'block' : 'none';
    }
}
function closeSidebar() {
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebarOverlay');
    if (sidebar) {
        sidebar.classList.remove('open');
        sidebar.classList.remove('collapsed');
    }
    if (overlay) overlay.classList.remove('active');
    var headerMenuBtn = document.querySelector('.header-menu-btn');
    if (headerMenuBtn && window.innerWidth > 768) headerMenuBtn.style.display = 'none';
}

// 渲染对话列表
function renderChatList(conversations) {
    var list = document.getElementById('chatList');
    if (!list) return;
    if (!conversations || conversations.length === 0) {
        list.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-muted);font-size:13px;">暂无对话</div>';
        return;
    }
    var now = new Date();
    var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var yesterday = new Date(today.getTime() - 86400000);
    var weekAgo = new Date(today.getTime() - 7 * 86400000);
    var monthAgo = new Date(today.getTime() - 30 * 86400000);
    
    var groups = {
        'today': {label:'今天', items:[]},
        'yesterday': {label:'昨天', items:[]},
        'week': {label:'七天内', items:[]},
        'month': {label:'30天内', items:[]},
        'older': {label:'更早', items:[]}
    };
    
    conversations.forEach(function(c) {
        var created = c.created_at ? new Date(c.created_at) : now;
        var title = c.title || '新对话';
        var dateStr = '';
        try {
            if (created >= today) {
                var h = created.getHours().toString().padStart(2,'0');
                var m = created.getMinutes().toString().padStart(2,'0');
                var s = created.getSeconds().toString().padStart(2,'0');
                dateStr = h + ':' + m + ':' + s;
            } else if (created >= yesterday) {
                var h = created.getHours().toString().padStart(2,'0');
                var m = created.getMinutes().toString().padStart(2,'0');
                var s = created.getSeconds().toString().padStart(2,'0');
                dateStr = h + ':' + m + ':' + s;
            } else {
                dateStr = created.toLocaleDateString();
            }
        } catch(e) { dateStr = ''; }
        var item = '<div class="chat-item" onclick="selectChat(this,\'' + c.id + '\',\'' + title.replace(/'/g,"\\'") + '\')">' +
            '<i class="fas fa-comment"></i>' +
            '<span class="chat-title">' + title + '</span>' +
            '<span class="chat-date">' + dateStr + '</span>' +
            '<button class="chat-delete" onclick="deleteChat(event,this)"><i class="fas fa-times"></i></button></div>';
        
        if (created >= today) groups.today.items.push(item);
        else if (created >= yesterday) groups.yesterday.items.push(item);
        else if (created >= weekAgo) groups.week.items.push(item);
        else if (created >= monthAgo) groups.month.items.push(item);
        else groups.older.items.push(item);
    });
    
    var html = '';
    var keys = ['today','yesterday','week','month','older'];
    keys.forEach(function(k) {
        if (groups[k].items.length > 0) {
            html += '<div class="chat-list-label">' + groups[k].label + '</div>';
            html += groups[k].items.join('');
        }
    });
    list.innerHTML = html;
}

function selectChat(el, id, title) {
    document.querySelectorAll('.chat-item').forEach(function(i){i.classList.remove('active');});
    el.classList.add('active');
    if (title) {
        document.getElementById('chatTitle').textContent = title;
    }
    if (window.py_bridge) {
        try { window.py_bridge.loadConversation(id); } catch(e) { console.warn('[Sidebar] loadConversation:', e); }
    }
}

function deleteChat(event, el) {
    event.stopPropagation();
    var item = el.closest('.chat-item');
    if (!item) return;
    var onclick = item.getAttribute('onclick') || '';
    var match = onclick.match(/selectChat\(this,'([^']+)'/);
    var id = match ? match[1] : '';
    if (!id) return;
    var isActive = item.classList.contains('active');
    if (window.py_bridge) {
        try {
            window.py_bridge.deleteConversationAndNew(id);
            item.remove();
            if (isActive) {
                document.getElementById('chatTitle').textContent = '新对话';
                var html = '<div class="welcome-screen" id="welcomeScreen">' +
                    '<div class="welcome-icon">🤖</div>' +
                    '<h1 class="welcome-title">AI 智能助手</h1>' +
                    '<p class="welcome-subtitle">基于 <strong>'+(appState.currentModel?.name||'AI')+'</strong> 模型</p></div>';
                document.getElementById('chatMessages').innerHTML = html;
                window.chatApp.messages = [];
            }
        } catch(e) { console.warn('[Sidebar] deleteChat:', e); }
    }
}

function newChat() {
    closeSidebar();
    document.getElementById('chatTitle').textContent = '新对话';
    document.getElementById('chatMessages').innerHTML = 
        '<div class="welcome-screen" id="welcomeScreen">' +
        '<div class="welcome-icon">🤖</div>' +
        '<h1 class="welcome-title">AI 智能助手</h1>' +
        '<p class="welcome-subtitle">基于 <strong>'+(appState.currentModel?.name||'AI')+'</strong> 模型，支持 MCP 工具调用。</p>' +
        '<div class="quick-actions">' +
            '<div class="quick-action" onclick="quickAction(\'写一个 Python 函数\')"><i class="fas fa-code"></i><span class="label">写代码</span></div>' +
            '<div class="quick-action" onclick="quickAction(\'帮我解释这个概念\')"><i class="fas fa-lightbulb"></i><span class="label">解释概念</span></div>' +
            '<div class="quick-action" onclick="quickAction(\'分析这段数据\')"><i class="fas fa-chart-bar"></i><span class="label">分析数据</span></div>' +
            '<div class="quick-action" onclick="quickAction(\'翻译成中文\')"><i class="fas fa-language"></i><span class="label">翻译</span></div>' +
        '</div></div>';
    appState.messages = [];
    document.getElementById('messageInput').focus();
    if (typeof showToast === 'function') showToast('新对话已创建', 'success');
}

// sidebar-overlay 点击关闭
document.addEventListener('DOMContentLoaded', function() {
    var overlay = document.getElementById('sidebarOverlay');
    if (overlay) overlay.addEventListener('click', closeSidebar);
});