// ============================================
// UI - 面板切换、主题、渲染函数
// ============================================

var tabTitles={mcp:'<i class="fas fa-plug"></i> MCP 配置',models:'<i class="fas fa-brain"></i> 模型',tools:'<i class="fas fa-tools"></i> 工具',skills:'<i class="fas fa-star"></i> 技能',plugins:'<i class="fas fa-puzzle-piece"></i> 插件',settings:'<i class="fas fa-sliders-h"></i> 设置',about:'<i class="fas fa-info-circle"></i> 关于'};
var tabList=['mcp','models','tools','skills','plugins','settings','about'];

// ============================================
// UI 状态持久化：面板/侧边栏/插件 Tab 状态保存到 user_config/user/ui_state.json
// ============================================

// 采集当前 UI 状态（打开/隐藏状态：右侧面板、工具栏 Tab、侧边栏、插件 Tab）
function collectUIState() {
    var sidebar = document.getElementById('sidebar');
    var panel = document.getElementById('rightPanel');
    var state = {
        sidebarCollapsed: !!(sidebar && sidebar.classList.contains('collapsed')),
        panelOpen: !!(panel && panel.classList.contains('open')),
        currentTab: (appState && appState.currentTab) || 'mcp',
        mcpSubTab: 'market',
        openPlugins: [],
        activePluginTab: 'chat'
    };
    // MCP 子 Tab
    var mcpTab = document.querySelector('.mcp-sub-tab.active');
    if (mcpTab) state.mcpSubTab = mcpTab.getAttribute('data-subtab') || 'market';
    // 插件 Tab 栏中已打开的插件（排除固定「聊天」Tab）
    var bar = document.getElementById('pluginTabBar');
    if (bar) {
        bar.querySelectorAll('.plugin-tab[data-plugin]').forEach(function(t) {
            var name = t.getAttribute('data-plugin');
            if (name && name !== 'chat') state.openPlugins.push(name);
        });
    }
    // 当前激活的插件 Tab
    if (typeof _activePluginTab !== 'undefined' && _activePluginTab) {
        state.activePluginTab = _activePluginTab;
    }
    return state;
}

// 保存 UI 状态到后端（user_config/user/ui_state.json）
function saveUIState() {
    if (!window.ui_state_bridge || typeof window.ui_state_bridge.saveState !== 'function') return;
    try {
        window.ui_state_bridge.saveState(JSON.stringify(collectUIState()));
    } catch(e) { console.warn('[UI] 保存界面状态失败:', e); }
}

// 启动时读取已保存的 UI 状态并恢复
function restoreUIState() {
    if (!window.ui_state_bridge || typeof window.ui_state_bridge.getState !== 'function') return;
    try {
        var p = window.ui_state_bridge.getState();
        if (p && typeof p.then === 'function') {
            p.then(function(raw) {
                if (raw && typeof raw === 'string') {
                    var state = JSON.parse(raw);
                    applyUIState(state);
                }
            }).catch(function(e) { console.warn('[UI] 读取界面状态失败:', e); });
        }
    } catch(e) { console.warn('[UI] 恢复界面状态失败:', e); }
}

// 按保存的状态恢复 UI
function applyUIState(state) {
    if (!state) return;
    // 1. 侧边栏折叠
    if (state.sidebarCollapsed) {
        var sidebar = document.getElementById('sidebar');
        if (sidebar) sidebar.classList.add('collapsed');
        var headerMenuBtn = document.querySelector('.header-menu-btn');
        if (headerMenuBtn) headerMenuBtn.style.display = 'block';
    }
    // 2. 右侧面板 + 当前工具栏 Tab
    if (state.panelOpen && state.currentTab) {
        var validTabs = ['mcp','models','tools','skills','plugins','settings','about'];
        if (validTabs.indexOf(state.currentTab) !== -1) {
            switchPanelTab(state.currentTab);
            if (state.currentTab === 'mcp' && state.mcpSubTab) {
                setTimeout(function() { switchMCPSubTab(state.mcpSubTab); }, 120);
            }
        }
    }
    // 3. 插件 Tab 恢复（showPlugin 依赖 appState.plugins 异步加载，轮询等待）
    var pluginsToOpen = (state.openPlugins && state.openPlugins.length > 0) ? state.openPlugins : [];
    if (pluginsToOpen.length > 0) {
        var tries = 0;
        (function tryOpenPlugins() {
            if (!(appState && appState.plugins && appState.plugins.length > 0)) {
                tries++;
                if (tries < 12) { setTimeout(tryOpenPlugins, 500); return; }
                return;
            }
            pluginsToOpen.forEach(function(name) {
                try {
                    if (typeof showPlugin === 'function') showPlugin(name);
                } catch(e) { console.warn('[UI] 恢复插件 Tab 失败:', name, e); }
            });
            var active = state.activePluginTab || 'chat';
            if (active !== 'chat' && pluginsToOpen.indexOf(active) === -1) active = 'chat';
            setTimeout(function() {
                if (typeof activatePluginTab === 'function') activatePluginTab(active);
            }, 100);
        })();
    }
}

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
    saveUIState();
}
function closePanel(){document.getElementById('rightPanel').classList.remove('open');document.querySelectorAll('.header-btn').forEach(b=>b.classList.remove('active'));saveUIState();}
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
    saveUIState();
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
    saveUIState();
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
    // ====== 重置实时聊天状态（修复：历史会话加载后残留的流式引用导致消息重复显示）======
    // 之前只清空 DOM，未重置 chatApp 的 _currentAssistantId / _lastToolAnchor / isProcessing /
    // messages。若加载发生在 AI 仍活跃或刚结束时，残留的实时状态会让后续 live 渲染
    // （insertToolMessage / onStreamUpdate / addMessage）把新气泡追加到历史气泡之后，
    // 形成「同一段对话显示两遍」（历史用 ISO 时间、实时用本地时间）的错乱显示。
    if (window.chatApp) {
        window.chatApp._currentAssistantId = null;
        window.chatApp._lastToolAnchor = null;
        window.chatApp.isProcessing = false;
        window.chatApp._stopRequested = false;
        // 重建内部消息列表，使其与刚渲染的 DOM 一致（历史消息的 id 为合成 id，
        // 仅供内部索引，不会被 completeMessage 等实时逻辑再次引用）
        window.chatApp.messages = (data || []).map(function(m) {
            return { id: 'msg_hist_' + Math.random().toString(36).substr(2, 8),
                     role: m.role || 'user', content: m.content || '' };
        });
        if (typeof window.chatApp.setSendButtonStopMode === 'function') {
            window.chatApp.setSendButtonStopMode(false);
        }
    }
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
    // 防止「全新会话」误触分页：offset 只在 loadConversationMessages / prependHistoryMessages
    // 中初始化。若 offset=0（本次会话从未从历史加载过，全是实时渲染），滚动到顶部时若继续
    // 分页，后端会以 offset=0 返回全部消息并 prepend 到顶部 → 同一段对话显示两遍
    // （历史用 ISO 时间、实时用本地时间，与用户看到的重复现象完全一致）。
    if (loadMoreState.offset <= 0) return;
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
