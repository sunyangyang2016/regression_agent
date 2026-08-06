// ============================================
// UI - 面板切换、主题、渲染函数
// ============================================

var tabTitles={mcp:'<i class="fas fa-plug"></i> MCP 配置',models:'<i class="fas fa-brain"></i> 模型',tools:'<i class="fas fa-tools"></i> 工具',skills:'<i class="fas fa-star"></i> 技能',plugins:'<i class="fas fa-puzzle-piece"></i> 插件',settings:'<i class="fas fa-sliders-h"></i> 设置',about:'<i class="fas fa-info-circle"></i> 关于'};
var tabList=['mcp','models','tools','skills','plugins','settings','about'];

function switchPanelTab(tab) {
    document.getElementById('rightPanel').classList.add('open');
    document.querySelectorAll('.panel-tab').forEach(function(t){t.classList.toggle('active',t.dataset.tab===tab);});
    var idMap={mcp:'tabMCP',models:'tabModels',tools:'tabTools',skills:'tabSkills',plugins:'tabPlugins',settings:'tabSettings',about:'tabAbout'};
    Object.keys(idMap).forEach(function(k){var el=document.getElementById(idMap[k]);if(el)el.style.display=k===tab?'block':'none';});
    document.getElementById('panelTitle').innerHTML=tabTitles[tab]||'配置';
    document.querySelectorAll('.header-btn').forEach(function(b,i){b.classList.toggle('active',['mcp','models','tools','skills','plugins','settings','about'][i]===tab);});
    appState.currentTab=tab;
    console.log('[UI] switchPanelTab to:', tab);
    // 懒加载面板 HTML + 渲染数据
    switch(tab) {
        case 'mcp':
            try { renderMCPServers(); } catch(e) { console.warn('[UI] renderMCPServers error:', e); }
            try { renderMCPMarket(); } catch(e) { console.warn('[UI] renderMCPMarket error:', e); }
            try { updateMCPBadge(); } catch(e) { console.warn('[UI] updateMCPBadge error:', e); }
            break;
        case 'models':
            try { renderModelList(); updateModelCount(); } catch(e) { console.warn('[UI] renderModelList error:', e); }
            break;
        case 'tools':
            try { renderTools(); } catch(e) { console.warn('[UI] renderTools error:', e); }
            break;
        case 'skills':
            // 切换到技能面板时，从后端拉取最新技能数据（QWebChannel 返回 Promise）
            try {
                if (window.skill_bridge) {
                    var p = window.skill_bridge.getSkills();
                    if (p && typeof p.then === 'function') {
                        p.then(function(raw) {
                            if (raw && typeof raw === 'string') {
                                try {
                                    var skills = JSON.parse(raw);
                                    if (skills && skills.length > 0) {
                                        appState.skills = skills;
                                        renderSkills();
                                        console.log('[Skills] 面板拉取 ' + skills.length + ' 个技能');
                                    }
                                } catch(e2) { console.warn('[Skills] 解析失败:', e2); }
                            }
                        });
                    }
                }
            } catch(e) { console.warn('[UI] skills bridge error:', e); }
            // 先用已有数据渲染
            try { renderSkills(); } catch(e) { console.warn('[UI] renderSkills error:', e); }
            break;
        case 'plugins':
            try { renderPlugins(); } catch(e) { console.warn('[UI] renderPlugins error:', e); }
            break;
        case 'settings':
            try { renderSettings(); } catch(e) { console.warn('[UI] renderSettings error:', e); }
            break;
        case 'about':
            try { renderAbout(); } catch(e) { console.warn('[UI] renderAbout error:', e); }
            break;
        default:
            try { renderMCPServers(); } catch(e) { console.warn('[UI] renderMCPServers error:', e); }
            try { renderMCPMarket(); } catch(e) { console.warn('[UI] renderMCPMarket error:', e); }
            try { renderModelList(); } catch(e) { console.warn('[UI] renderModelList error:', e); }
            try { renderTools(); } catch(e) { console.warn('[UI] renderTools error:', e); }
            try { renderSkills(); } catch(e) { console.warn('[UI] renderSkills error:', e); }
            try { renderPlugins(); } catch(e) { console.warn('[UI] renderPlugins error:', e); }
            try { updateMCPBadge(); } catch(e) { console.warn('[UI] updateMCPBadge error:', e); }
    }
}
function closePanel(){document.getElementById('rightPanel').classList.remove('open');document.querySelectorAll('.header-btn').forEach(b=>b.classList.remove('active'));}
function toggleSidebar(){
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebarOverlay');
    if (!sidebar) return;
    if (window.innerWidth <= 768) {
        sidebar.classList.toggle('open');
        if (overlay) overlay.classList.toggle('active');
    } else {
        var isCollapsed = sidebar.classList.toggle('collapsed');
        var headerMenuBtn = document.querySelector('.header-menu-btn');
        if (headerMenuBtn) headerMenuBtn.style.display = isCollapsed ? 'block' : 'none';
    }
}
function switchMCPSubTab(tab){
    console.log('[UI] switchMCPSubTab:', tab);
    document.querySelectorAll('.mcp-sub-tab').forEach(t=>t.classList.remove('active'));
    document.querySelector('.mcp-sub-tab[data-subtab="'+tab+'"]')?.classList.add('active');
    ['mcpSubMarket','mcpSubLocal','mcpSubRemote','mcpSubConfig'].forEach(id=>{
        const el=document.getElementById(id);
        if(el)el.style.display='none';
    });
    const map={market:'mcpSubMarket',local:'mcpSubLocal',remote:'mcpSubRemote',config:'mcpSubConfig'};
    const el=document.getElementById(map[tab]);
    if(el)el.style.display='block';
    // 切换到本地/远程时，加载服务器列表和扫描目录
    if(tab==='local'||tab==='remote'){
        if(typeof loadMCPServers==='function'){
            loadMCPServers();
        }
    }
    if(tab==='local'){
        if(typeof scanLocalServerDirs==='function'){
            scanLocalServerDirs();
        }
    }
    if(tab==='market'&&typeof loadMCPMarket==='function'){
        loadMCPMarket();
    }
    if(tab==='config'&&typeof loadMCPConfigToEditor==='function'){
        loadMCPConfigToEditor();
    }
}

function updateModelCount(){var e=document.getElementById('modelCount');if(e)e.textContent=appState.models.length;}
// 后端 ChatController 可能调用的函数
function formatMessage(text) {
    if (!text) return '';
    // 转义HTML特殊字符
    text = text.replace(/&/g,'&').replace(/</g,'<').replace(/>/g,'>');
    // **bold** → <strong>
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // *text* → <em>（只处理单星号，但排除可能被**误匹配的情况）
    text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');
    // 换行 → <br>
    text = text.replace(/\n/g, '<br>');
    // 数字序号如 "1. " → 加缩进
    text = text.replace(/(\d+\.\s)/g, '<span style="margin-left:2px;">$1</span>');
    return text;
}
// 分页加载状态（UI 顶部滚动加载更早历史用）
var loadMoreState = { offset: 0, hasMore: true, loading: false };

function renderMessageInto(container, msg) {
    var role = msg.role || 'user';
    var content = msg.content || '';
    var time = msg.time || '';
    var icons = {user:'fa-user', assistant:'fa-robot', tool:'fa-plug'};
    var names = {user:'user', assistant: appState.currentModel?.name || 'AI', tool:'tool'};
    var div = document.createElement('div');
    div.className = 'message ' + role;
    div.innerHTML = '<div class="message-avatar '+role+'"><i class="fas '+(icons[role]||'fa-user')+'"></i></div>' +
        '<div class="message-content">' +
        '<div class="message-header"><span class="message-role">'+(names[role]||role)+'</span>' +
        '<span class="message-time">'+time+'</span></div>' +
        '<div class="message-body">'+formatMessage(content)+'</div></div>';
    container.appendChild(div);
}

function loadConversationMessages(data) {
    var container = document.getElementById('chatMessages');
    if (!container) return;
    var welcome = document.getElementById('welcomeScreen');
    if (welcome) welcome.remove();
    container.innerHTML = '';
    data = data || [];
    data.forEach(function(msg) { renderMessageInto(container, msg); });
    // 记录分页状态：offset = 已加载条数（下次加载更早的 50 条）
    loadMoreState.offset = data.length;
    loadMoreState.hasMore = true;
    loadMoreState.loading = false;
    container.scrollTop = container.scrollHeight;
}

// 滚动加载更多历史：将更早的消息插入到聊天顶部，并保持滚动位置
function prependHistoryMessages(olderData) {
    var container = document.getElementById('chatMessages');
    if (!container || !olderData || olderData.length === 0) return;
    var scrollHeightBefore = container.scrollHeight;
    var scrollTopBefore = container.scrollTop;
    var frag = document.createDocumentFragment();
    olderData.forEach(function(msg) { renderMessageInto(frag, msg); });
    container.insertBefore(frag, container.firstChild);
    loadMoreState.offset += olderData.length;
    loadMoreState.loading = false;
    // 保持用户当前位置（滚动的历史消息不跳动）
    container.scrollTop = container.scrollHeight - scrollHeightBefore + scrollTopBefore;
}

// 没有更多历史时触发（后端调用）
function onNoMoreHistory() {
    loadMoreState.hasMore = false;
    loadMoreState.loading = false;
}

// 聊天容器滚动处理：滚动到顶部时加载更早的历史（分页）
function handleChatScroll(el) {
    if (!el) return;
    // 仅当接近顶部时才触发加载（scrollTop <= 30 容差）
    if (el.scrollTop > 30) return;
    if (!loadMoreState.hasMore || loadMoreState.loading) return;
    loadMoreState.loading = true;
    if (window.py_bridge && typeof window.py_bridge.loadMoreMessages === 'function') {
        try {
            var cid = window.currentChatId || '';
            if (cid) {
                console.log('[UI] 滚动到顶部，加载更早历史 offset=', loadMoreState.offset);
                window.py_bridge.loadMoreMessages(cid, loadMoreState.offset);
            } else {
                loadMoreState.loading = false;
            }
        } catch(e) {
            console.error('[UI] 加载更多历史失败:', e);
            loadMoreState.loading = false;
        }
    } else {
        loadMoreState.loading = false;
    }
}
function syncConfig() {}
