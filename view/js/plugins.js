// ============================================
// Plugins - 插件管理面板（三卡片 + 开关 + 显示按钮）
// 插件显示改为 Chat 区域 Tab 形式：聊天区 + 插件共存在 Tab 栏中
// ============================================

const PLUGIN_ICONS = {
    security_plugin: 'fa-shield-alt',
    monitor_plugin: 'fa-chart-line',
    git_plugin: 'fa-code-branch'
};
const PLUGIN_ICON_COLORS = {
    security_plugin: 'rgba(247,120,186,0.15)',
    monitor_plugin: 'rgba(76,175,80,0.15)',
    git_plugin: 'rgba(255,152,0,0.15)'
};
const PLUGIN_ICON_COLOR_FG = {
    security_plugin: 'var(--accent-pink)',
    monitor_plugin: '#4caf50',
    git_plugin: '#ff9800'
};

function renderPlugins() {
    var c = document.getElementById('pluginList');
    if (!c) return;
    var plugins = (appState && appState.plugins) || [];
    if (plugins.length === 0) {
        c.innerHTML = '<div style="text-align:center;padding:30px 20px;color:var(--text-muted);">暂无插件</div>';
        return;
    }
    c.innerHTML = plugins.map(function(p) {
        var enabled = !!p.enabled;
        var icon = PLUGIN_ICONS[p.name] || 'fa-puzzle-piece';
        var bg = PLUGIN_ICON_COLORS[p.name] || 'rgba(100,100,255,0.15)';
        var fg = PLUGIN_ICON_COLOR_FG[p.name] || 'var(--accent-primary)';
        var desc = p.description || '';
        var hooksHtml = '';
        if (p.hook_handlers && p.hook_handlers.length > 0) {
            hooksHtml = '<div class="tags" style="margin-top:4px;">' +
                p.hook_handlers.map(function(h) {
                    return '<span class="tag" style="font-size:10px;opacity:0.7;">' + h + '</span>';
                }).join('') + '</div>';
        }
        return '<div class="item-row">' +
            '<div class="icon" style="background:' + bg + ';color:' + fg + ';">' +
                '<i class="fas ' + icon + '"></i>' +
            '</div>' +
            '<div class="info">' +
                '<div class="name">' + (p.name || '') + '</div>' +
                '<div class="desc">' + desc + '</div>' +
                '<div class="tags"><span class="tag active">v' + (p.version || '1.0.0') + '</span></div>' +
                hooksHtml +
            '</div>' +
            '<div style="display:flex;flex-direction:column;align-items:flex-end;gap:8px;justify-content:center;">' +
                '<label class="switch">' +
                    '<input type="checkbox"' + (enabled ? ' checked' : '') +
                        ' onchange="togglePlugin(this, \'' + String(p.name).replace(/'/g, "\\'") + '\')">' +
                    '<span class="slider"></span>' +
                '</label>' +
                '<button class="plugin-show-btn" onclick="showPlugin(\'' + String(p.name).replace(/'/g, "\\'") + '\')" title="在聊天区域打开插件">' +
                    '<i class="fas fa-external-link-alt"></i> 显示' +
                '</button>' +
            '</div>' +
        '</div>';
    }).join('');
}

function togglePlugin(checkbox, name) {
    if (!window.plugin_bridge) {
        checkbox.checked = !checkbox.checked;
        showToast('❌ 插件桥接不可用', 'error');
        return;
    }
    var enable = checkbox.checked ? 'true' : 'false';
    try {
        var p = window.plugin_bridge.togglePlugin(name, enable);
        if (p && typeof p.then === 'function') {
            p.then(function(result) {
                try {
                    var r = typeof result === 'string' ? JSON.parse(result) : result;
                    if (r && r.ok) {
                        showToast((enable === 'true' ? '✅ 已启用 ' : '🛑 已禁用 ') + name, 'success');
                    } else {
                        checkbox.checked = !checkbox.checked;
                        showToast('❌ ' + ((r && r.message) || '切换失败'), 'error');
                    }
                } catch(e) {
                    checkbox.checked = !checkbox.checked;
                    console.warn('[Plugins] 切换响应解析失败:', e);
                }
            }).catch(function(e) {
                checkbox.checked = !checkbox.checked;
                console.warn('[Plugins] 切换失败:', e);
            });
        } else {
            var r = typeof p === 'string' ? JSON.parse(p) : p;
            if (r && r.ok) {
                showToast((enable === 'true' ? '✅ 已启用 ' : '🛑 已禁用 ') + name, 'success');
            } else {
                checkbox.checked = !checkbox.checked;
                showToast('❌ ' + ((r && r.message) || '切换失败'), 'error');
            }
        }
    } catch(e) {
        checkbox.checked = !checkbox.checked;
        console.warn('[Plugins] 切换异常:', e);
    }
}

// ============================================
// 插件 Tab 面板 - 聊天区 + 插件共存于 Tab 栏
// Tab 栏始终显示，第一个 Tab 固定为「聊天」
// ============================================

// 当前激活的 Tab 名（'chat' = 聊天区，其余为插件名）
var _activePluginTab = 'chat';

function _getPluginTabBar() {
    var bar = document.getElementById('pluginTabBar');
    if (!bar) {
        bar = document.createElement('div');
        bar.id = 'pluginTabBar';
        bar.className = 'plugin-tab-bar';
        var container = document.getElementById('chatContainer');
        if (container) {
            container.insertBefore(bar, document.getElementById('pluginTabContent') || container.firstChild);
        }
    }
    return bar;
}

function _getPluginTabContent() {
    var content = document.getElementById('pluginTabContent');
    if (!content) {
        content = document.createElement('div');
        content.id = 'pluginTabContent';
        content.className = 'plugin-tab-content';
        var container = document.getElementById('chatContainer');
        if (container) {
            container.insertBefore(content, document.getElementById('chatMessages') || null);
        }
    }
    return content;
}

// 初始化 Tab 栏：创建固定的「聊天」Tab
function initPluginTabs() {
    var bar = _getPluginTabBar();
    if (bar.querySelector('.plugin-tab[data-plugin="chat"]')) return;

    // 创建「聊天」Tab（第一个，固定存在，不可关闭）
    // 标题显示当前会话标题，默认「新对话」
    var chatTab = document.createElement('div');
    chatTab.id = 'pluginTab_chat';
    chatTab.className = 'plugin-tab active';
    chatTab.setAttribute('data-plugin', 'chat');
    chatTab.innerHTML = '<span class="plugin-tab-icon"><i class="fas fa-comments"></i></span>' +
        '<span class="plugin-tab-title" id="pluginChatTitle">新对话</span>';
    chatTab.onclick = function() { activatePluginTab('chat'); };
    bar.appendChild(chatTab);

    // Tab 栏始终显示
    bar.style.display = '';
    var content = document.getElementById('pluginTabContent');
    if (content) content.style.display = 'none';
}

// 更新聊天 Tab 标题（会话标题显示在「聊天」Tab 上）
function updateChatTabTitle(title) {
    var el = document.getElementById('pluginChatTitle');
    if (el) el.textContent = title || '新对话';
}

// 显示插件：在 Tab 栏创建/激活对应插件 Tab
function showPlugin(name) {
    initPluginTabs();
    var bar = _getPluginTabBar();
    var content = _getPluginTabContent();

    // 若 Tab 已存在，直接激活
    if (document.getElementById('pluginTab_' + name)) {
        activatePluginTab(name);
        return;
    }

    // 从后端 metadata 找该插件的 config_ui
    var p = (appState && appState.plugins || []).find(function(x) { return x.name === name; });
    var ui = (p && p.config_ui) || {};
    var html = ui.html || '';
    var css = ui.css || '';
    var js = ui.js || '';

    var icon = PLUGIN_ICONS[name] || 'fa-puzzle-piece';
    var fg = PLUGIN_ICON_COLOR_FG[name] || 'var(--accent-primary)';
    var title = name === 'security_plugin' ? '安全插件配置' :
                name === 'monitor_plugin' ? '系统监控' :
                name === 'git_plugin' ? 'Git 集成' : '插件配置';

    // ===== 创建 Tab 标签按钮 =====
    var tabBtn = document.createElement('div');
    tabBtn.id = 'pluginTab_' + name;
    tabBtn.className = 'plugin-tab';
    tabBtn.setAttribute('data-plugin', name);
    tabBtn.innerHTML = '<span class="plugin-tab-icon"><i class="fas ' + icon + '" style="color:' + fg + ';"></i></span>' +
        '<span class="plugin-tab-title">' + title + '</span>' +
        '<button class="plugin-tab-close" onclick="event.stopPropagation();closePlugin(\'' + String(name).replace(/'/g, "\\'") + '\')" title="关闭">✕</button>';
    tabBtn.onclick = function() { activatePluginTab(name); };
    bar.appendChild(tabBtn);

    // ===== 创建内容面板 =====
    var panel = document.createElement('div');
    panel.id = 'pluginTabPanel_' + name;
    panel.className = 'plugin-tab-panel';
    panel.style.display = 'none';

    var styleTag = css ? '<style>' + css + '</style>' : '';
    var bodyDiv = '<div class="plugin-tab-body">' + html + '</div>';
    panel.innerHTML = styleTag + bodyDiv;
    content.appendChild(panel);

    // ===== 激活此 Tab =====
    activatePluginTab(name);

    // ===== 执行插件自身 js（依赖 window.security_bridge 等，由 app.js 全局注入）=====
    if (js) {
        try {
            // eslint-disable-next-line no-new-func
            (new Function('window', 'document', js))(window, document);
        } catch(e) {
            console.warn('[Plugins] 执行插件 js 失败:', name, e);
        }
    }
}

// 激活指定 Tab：'chat' 显示聊天区，插件名显示对应插件面板
function activatePluginTab(name) {
    _activePluginTab = name;
    var bar = document.getElementById('pluginTabBar');
    var content = document.getElementById('pluginTabContent');
    if (!bar) return;

    // Tab 标签高亮
    bar.querySelectorAll('.plugin-tab').forEach(function(t) {
        t.classList.toggle('active', t.getAttribute('data-plugin') === name);
    });

    var chatMessages = document.getElementById('chatMessages');

    if (name === 'chat') {
        // 聊天 Tab：显示聊天消息区，隐藏插件内容容器
        if (chatMessages) chatMessages.style.display = '';
        if (content) content.style.display = 'none';
    } else {
        // 插件 Tab：隐藏聊天消息区，显示插件内容容器
        if (chatMessages) chatMessages.style.display = 'none';
        if (content) content.style.display = '';
        if (content) {
            content.querySelectorAll('.plugin-tab-panel').forEach(function(p) {
                p.style.display = p.id === 'pluginTabPanel_' + name ? 'block' : 'none';
            });
        }
    }
}

// 关闭插件 Tab（聊天 Tab 不可关闭）
function closePlugin(name) {
    if (name === 'chat') return;
    var tab = document.getElementById('pluginTab_' + name);
    var panel = document.getElementById('pluginTabPanel_' + name);
    if (tab) tab.remove();
    if (panel) panel.remove();

    // 如果关闭的是当前激活的插件，切回聊天
    if (_activePluginTab === name) {
        activatePluginTab('chat');
    }
}

// 关闭所有插件 Tab，切回聊天
function closeAllPlugins() {
    var bar = document.getElementById('pluginTabBar');
    var content = document.getElementById('pluginTabContent');
    if (bar) {
        bar.querySelectorAll('.plugin-tab[data-plugin!="chat"]').forEach(function(t) { t.remove(); });
    }
    if (content) content.innerHTML = '';
    activatePluginTab('chat');
}

// 新对话 / 需要聚焦聊天时调用：切换到聊天 Tab
function focusChatTab() {
    initPluginTabs();
    activatePluginTab('chat');
}