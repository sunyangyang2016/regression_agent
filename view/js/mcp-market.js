// ============================================
// MCP 市场 - 搜索、筛选、渲染、安装
// ============================================

// HTML 模板
var MCP_MARKET_HTML = '<div class="config-section"><div class="config-section-title"><i class="fas fa-store"></i> MCP 市场</div><div id="mcpMarketList"></div></div>';

// 注入 HTML
(function(){
    var el = document.getElementById('mcpSubMarket');
    if (el && !el.getAttribute('data-html-loaded')) {
        el.innerHTML = MCP_MARKET_HTML;
        el.setAttribute('data-html-loaded', 'true');
    }
})();

var _mcpFilterText = '';
var _mcpFilterCat = 'all';

function _filterMarket() {
    var inp = document.getElementById('mcpMarketSearch');
    var t = inp ? inp.value.toLowerCase().trim() : '';
    if (t === _mcpFilterText) return;
    _mcpFilterText = t;
    renderMCPMarket();
}

function initMarketSearch() {
    if (window._marketSearchInited) return;
    window._marketSearchInited = true;
    
    var inp = document.getElementById('mcpMarketSearch');
    if (!inp) { setTimeout(initMarketSearch, 100); return; }
    
    inp.addEventListener('input', function() { _filterMarket(); }, false);
    inp.addEventListener('change', function() { _filterMarket(); }, false);
    
    // 分类按钮事件绑定
    var btns = document.querySelectorAll('#mcpCategoryFilters .mcp-filter-btn');
    for (var i = 0; i < btns.length; i++) {
        btns[i].addEventListener('click', function(e) {
            var cat = this.getAttribute('data-cat');
            _filterMarketByCat(cat);
        }, false);
    }
}

function renderMCPSearchBar() {
    var container = document.getElementById('mcpSubMarket');
    if (!container) return;
    if (document.getElementById('mcpMarketSearchBar')) { return; }
    
    var bar = document.createElement('div');
    bar.id = 'mcpMarketSearchBar';
    bar.innerHTML =
        '<div style="display:flex;gap:8px;margin-bottom:8px;flex-direction:column;">'
        + '<div style="position:relative;">'
        + '<i class="fas fa-search" style="position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--text-muted);font-size:13px;"></i>'
        + '<input type="text" id="mcpMarketSearch" placeholder="搜索服务器名称、描述..."'
        + 'style="width:100%;padding:7px 10px 7px 30px;border:1px solid var(--border-color);border-radius:var(--radius-md);background:var(--bg-primary);color:var(--text-primary);font-size:13px;outline:none;box-sizing:border-box;">'
        + '</div>'
        + '<div style="display:flex;gap:4px;flex-wrap:wrap;align-items:center;" id="mcpCategoryFilters">'
        + '<button class="mcp-filter-btn active" data-cat="all">全部</button>'
        + '<button class="mcp-filter-btn" data-cat="local">📦 本地</button>'
        + '<button class="mcp-filter-btn" data-cat="remote">🌐 网络</button>'
        + '<button class="mcp-filter-btn" data-cat="tested">已验证</button>'
        + '<button class="mcp-filter-btn" data-cat="pending">待审核</button>'
        + '<button onclick="loadMCPMarketRefresh()" style="margin-left:auto;padding:5px 14px;border:1px solid var(--border-color);border-radius:var(--radius-md);background:var(--bg-secondary);color:var(--text-primary);cursor:pointer;font-size:12px;white-space:nowrap;"><i class="fas fa-sync-alt"></i> 刷新</button>'
        + '</div></div>'
        + '<div id="mcpMarketStats" style="font-size:12px;color:var(--text-muted);margin-bottom:8px;"></div>';
    container.insertBefore(bar, container.firstChild);
    
    // 绑定事件（用 setTimeout 确保 DOM 已渲染）
    setTimeout(initMarketSearch, 0);
}

function _filterMarketByCat(cat) {
    if (cat === _mcpFilterCat) return;
    _mcpFilterCat = cat;
    var btns = document.querySelectorAll('#mcpCategoryFilters .mcp-filter-btn');
    for (var i = 0; i < btns.length; i++) {
        btns[i].classList.toggle('active', btns[i].getAttribute('data-cat') === cat);
    }
    renderMCPMarket();
}

// 兼容旧函数名
function filterMCPMarket() { _filterMarket(); }
function filterMCPMarketByCat(cat) { _filterMarketByCat(cat); }

function renderMCPMarket() {
    var c = document.getElementById('mcpMarketList');
    if (!c) return;
    var statsEl = document.getElementById('mcpMarketStats');
    // 保存当前日志内容（避免重渲染时丢失安装日志）
    var savedLogs = {};
    if (c) {
        var logDivs = c.querySelectorAll('[id^="mcpLog_"]');
        for (var i = 0; i < logDivs.length; i++) {
            var id = logDivs[i].id.replace('mcpLog_', '');
            var content = logDivs[i].querySelector('.mcp-log-content');
            if (content) {
                savedLogs[id] = {
                    html: content.innerHTML,
                    display: logDivs[i].style.display
                };
            }
        }
    }
    renderMCPSearchBar();
    if (appState.mcpMarket.length === 0) {
        c.innerHTML = '<div style="text-align:center;padding:30px 20px;color:var(--text-muted);">'
            + '<div style="font-size:36px;margin-bottom:10px;">📦</div>'
            + '<div style="font-size:14px;color:var(--text-secondary);">暂无市场数据，点击"刷新市场"从 GitHub 加载</div></div>';
        if (statsEl) statsEl.textContent = '';
        return;
    }
    var filtered = appState.mcpMarket.filter(function(i) {
        if (_mcpFilterText) {
            var searchText = (i.title || i.name || '') + ' ' + (i.description || '') + ' ' + (i.author || '');
            if (searchText.toLowerCase().indexOf(_mcpFilterText) === -1) return false;
        }
        if (_mcpFilterCat === 'local') { if (i.serverType !== 'local') return false; }
        else if (_mcpFilterCat === 'remote') { if (i.serverType !== 'remote') return false; }
        else if (_mcpFilterCat === 'approved') { if (!i.labels || i.labels.indexOf('approved') === -1) return false; }
        else if (_mcpFilterCat === 'tested') { if (!i.tested) return false; }
        else if (_mcpFilterCat === 'pending') { if (i.tested || (i.labels && i.labels.indexOf('approved') !== -1)) return false; }
        return true;
    });
    if (statsEl) statsEl.textContent = '共 ' + filtered.length + ' / ' + appState.mcpMarket.length + ' 个服务器';
    if (filtered.length === 0) {
        c.innerHTML = '<div style="text-align:center;padding:30px 20px;color:var(--text-muted);">'
            + '<div style="font-size:36px;margin-bottom:10px;">🔍</div>'
            + '<div style="font-size:14px;color:var(--text-secondary);">没有匹配的服务器</div></div>';
        return;
    }
    c.innerHTML = filtered.map(function(i) {
        var raw = i.raw_issue || {};
        var title = i.title || i.name || raw.title || i.id;
        var author = i.author || (raw.user ? raw.user.login : 'unknown');
        var githubUrl = i.githubRepoUrl || '';
        var issueNumber = i.issueNumber || raw.number || '';
        var state = raw.state || 'open';
        var body = raw.body || '';
        var createdAt = raw.created_at || i.createdAt || '';
        var comments = raw.comments || 0;
        var rawLabels = raw.labels || [];
        var description = i.description || '';
        var logo = i.logo || '';
        var btnClass = i.installed ? 'installed' : '';
        var btnText = i.installed ? '🗑️ 卸载' : '📦 安装';
        var installBtn = '<button class="' + btnClass + '" onclick="event.stopPropagation();toggleMCPInstall(\'' + i.id + '\')">' + btnText + '</button>';
        // 匹配服务器：优先按 serverId（市场表新增字段），回退按 githubRepoUrl 规范化后比较
        var server = null;
        if (i.serverId) {
            server = appState.mcpServers.find(function(s) { return s.id === i.serverId; });
        }
        if (!server && i.githubRepoUrl) {
            var normUrl = function(u) { return (u || '').replace(/\/+$/, '').replace(/\.git$/, '').toLowerCase(); };
            var targetUrl = normUrl(i.githubRepoUrl);
            server = appState.mcpServers.find(function(s) {
                return s.githubRepoUrl && normUrl(s.githubRepoUrl) === targetUrl;
            });
        }
        var statusHtml = ''; var controlBtns = ''; var toolListHtml = '';
        if (server) {
            var serverId = server.id;  // 服务器真实 ID（配置 key）
            var statusClass = server.online ? 'online' : 'offline';
            var statusText = server.online ? '● 在线' : '● 离线';
            statusHtml = '<span class="server-status ' + statusClass + '" style="margin-left:8px;font-size:12px;">' + statusText + '</span>';
            if (server.online) controlBtns += '<button class="btn-action btn-stop" onclick="event.stopPropagation();stopMCPServer(\'' + serverId + '\')" title="停止" style="font-size:10px;padding:2px 6px;">⏹ 停止</button>';
            else controlBtns += '<button class="btn-action btn-start" onclick="event.stopPropagation();startMCPServer(\'' + serverId + '\')" title="启动" style="font-size:10px;padding:2px 6px;">▶ 启动</button>';
            controlBtns += '<button class="btn-action btn-restart" onclick="event.stopPropagation();restartMCPServer(\'' + serverId + '\')" title="重启" style="font-size:10px;padding:2px 6px;">🔄 重启</button>';
            if (server.tools && server.tools.length > 0) toolListHtml = '<div style="font-size:9px;color:var(--text-muted);margin-top:2px;">🔧 ' + server.tools.map(function(t){return t.name;}).join(', ') + '</div>';
            else if (server.toolCount > 0) toolListHtml = '<div style="font-size:9px;color:var(--text-muted);margin-top:2px;">🔧 ' + server.toolCount + ' 个工具</div>';
        }
        var logoHtml = logo ? '<img src="' + logo + '" style="width:36px;height:36px;border-radius:6px;object-fit:contain;margin-right:8px;" onerror="this.style.display=\'none\'" />'
            : (raw.user && raw.user.avatar_url ? '<img src="' + raw.user.avatar_url + '" style="width:36px;height:36px;border-radius:50%;margin-right:8px;" />'
            : '<div style="width:36px;height:36px;border-radius:6px;background:var(--bg-tertiary);display:flex;align-items:center;justify-content:center;margin-right:8px;font-size:18px;">📦</div>');
        var labelsHtml = '';
        rawLabels.concat(i.labels || []).forEach(function(l) {
            var name = typeof l === 'string' ? l : l.name;
            var color = l.color || '';
            if (name) labelsHtml += '<span style="font-size:9px;background:#' + color + '22;color:#' + (color || '666') + ';padding:1px 5px;border-radius:3px;margin-right:3px;">' + name + '</span>';
        });
        var sourceLabel = '<span class="market-badge" style="font-size:10px;background:#f3e8ff;color:#7c3aed;padding:1px 6px;border-radius:4px;margin-left:4px;">#' + issueNumber + '</span>';
        var stateBadge = state === 'open' ? '<span style="font-size:10px;background:#dcfce7;color:#166534;padding:1px 6px;border-radius:4px;margin-left:4px;">🟢 open</span>'
            : '<span style="font-size:10px;background:#f3e8ff;color:#7c3aed;padding:1px 6px;border-radius:4px;margin-left:4px;">✅ closed</span>';
        var parsedInfo = description ? '<span style="font-size:10px;color:#059669;margin-left:4px;">✓ 已解析</span>' : '';
        var bodySummary = body ? body.substring(0, 200).replace(/[#\*\[\]]/g, '') + (body.length > 200 ? '...' : '') : '';
        return '<div class="market-item" onclick="toggleMCPLog(\'' + i.id + '\')" style="cursor:pointer;">'
            + '<div class="market-header">'
            + '<div style="display:flex;align-items:center;flex:1;min-width:0;">' + logoHtml
            + '<div style="min-width:0;"><div style="display:flex;align-items:center;flex-wrap:wrap;">'
            + '<span class="market-name">' + title + '</span>' + sourceLabel + stateBadge + '</div>'
            + '<div style="font-size:11px;color:var(--text-muted);margin-top:2px;">by ' + author + statusHtml + parsedInfo + '</div></div></div>'
            + '<div class="market-actions">' + installBtn + '</div></div>'
            + '<div class="market-desc" style="font-size:12px;">' + (description || '') + '</div>'
            + '<div style="font-size:11px;color:var(--text-secondary);margin-top:2px;line-height:1.5;">' + labelsHtml + '</div>'
            + '<div style="font-size:11px;color:var(--text-muted);margin-top:2px;white-space:pre-line;max-height:60px;overflow:hidden;">' + (bodySummary || '') + '</div>'
            + '<div style="font-size:10px;color:var(--text-muted);margin-top:4px;display:flex;gap:8px;flex-wrap:wrap;">'
            + (githubUrl ? '<span>🔗 <a href="' + githubUrl + '" target="_blank" style="color:var(--accent-color);">' + githubUrl.replace('https://github.com/', '') + '</a></span>' : '')
            + (createdAt ? '<span>📅 ' + createdAt.substring(0, 10) + '</span>' : '')
            + (comments ? '<span>💬 ' + comments + '</span>' : '') + '</div>'
            + (controlBtns ? '<div style="display:flex;gap:4px;margin-top:6px;">' + controlBtns + '</div>' : '')
            + (toolListHtml || '')
            + '<div class="mcp-install-log" id="mcpLog_' + i.id + '" style="display:none;margin-top:10px;padding-top:10px;border-top:1px solid var(--border-color);" onclick="event.stopPropagation();">'
            + '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;">'
            + '<div style="font-size:12px;font-weight:600;color:var(--text-muted);">📋 日志 <span style="font-weight:400;color:var(--text-secondary);font-size:11px;" id="mcpLogCount_' + i.id + '"></span></div>'
            + '<button onclick="document.getElementById(\'mcpLog_' + i.id + '\').style.display=\'none\'" style="background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:11px;padding:0 4px;"><i class="fas fa-times"></i></button></div>'
            + '<div style="background:var(--bg-secondary);border:1px solid var(--border-color);border-radius:var(--radius-md);padding:10px;max-height:200px;overflow-y:auto;overflow-x:hidden;font-family:Courier New,monospace;font-size:11px;line-height:1.6;color:var(--text-primary);word-break:break-all;" class="mcp-log-content"></div></div></div>';
    }).join('');
    // 恢复之前保存的日志内容
    for (var id in savedLogs) {
        if (savedLogs.hasOwnProperty(id)) {
            var logDiv = document.getElementById('mcpLog_' + id);
            if (logDiv) {
                var content = logDiv.querySelector('.mcp-log-content');
                if (content) content.innerHTML = savedLogs[id].html;
                logDiv.style.display = savedLogs[id].display;
            }
        }
    }
}

function toggleMCPLog(id) {
    var logDiv = document.getElementById('mcpLog_' + id);
    if (!logDiv) return;
    logDiv.style.display = logDiv.style.display === 'none' ? 'block' : 'none';
}

function toggleMCPInstall(id) {
    var item = appState.mcpMarket.find(function(m) { return m.id === id; });
    if (!item) return;
    var name = item.title || item.name || id;
    if (item.installed) {
        showMCPLog(id, '🔄 正在卸载: ' + name);
        // 标记为卸载中，用于 mcpFinishInstall 回调时区分操作类型
        if (window._pendingUninstallIds) window._pendingUninstallIds[id] = true;
        if (window.mcp_bridge && window._bridgeReady) window.mcp_bridge.uninstallMCPFromMarket(id, '');
        item.installed = false;
        // 按真实 server_id 移除服务器列表中的对应项（不匹配则稍后 loadMCPServers 刷新）
        var uninstallServerId = item.serverId || '';
        item.serverId = '';   // ★ 取完 serverId 后再清残留，避免后续 loadMCPMarket merge 误判为已安装
        if (uninstallServerId) {
            appState.mcpServers = appState.mcpServers.filter(function(s) { return s.id !== uninstallServerId; });
        } else if (item.githubRepoUrl) {
            var normUrl = function(u) { return (u || '').replace(/\/+$/, '').replace(/\.git$/, '').toLowerCase(); };
            var targetUrl = normUrl(item.githubRepoUrl);
            appState.mcpServers = appState.mcpServers.filter(function(s) {
                return !(s.githubRepoUrl && normUrl(s.githubRepoUrl) === targetUrl);
            });
        }
        renderMCPMarket();
        if (typeof renderMCPServers === 'function') renderMCPServers();
        if (typeof renderMCPLocalServers === 'function') renderMCPLocalServers();
        updateMCPBadge();
        showToast('🗑️ 已卸载: ' + name, 'warning');
    } else {
        showMCPLog(id, '📦 正在安装: ' + name);
        showMCPLog(id, '🔗 仓库: ' + (item.githubRepoUrl || ''));
        if (window.mcp_bridge && window._bridgeReady) window.mcp_bridge.installMCPFromMarket(id, item.githubRepoUrl || '');
        showToast('📦 安装中: ' + name + '（查看日志）', 'info');
    }
}