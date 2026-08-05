// ============================================
// MCP 远程服务器 - 渲染、添加、管理
// ============================================

var MCP_REMOTE_HTML = '<div class="config-section"><div class="config-section-title"><i class="fas fa-server"></i> 远程服务器</div><div style="margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid var(--border-color);"><div class="config-section-title" style="margin-bottom:12px;"><i class="fas fa-plus-circle"></i> 添加远程服务器</div><div class="config-group"><label>服务器名称</label><input type="text" id="mcpServerName" placeholder="例如: filesystem" style="width:100%;padding:7px 10px;border:1px solid var(--border-color);border-radius:var(--radius-md);background:var(--bg-primary);color:var(--text-primary);font-size:13px;box-sizing:border-box;"></div><div class="config-group" style="margin-top:10px;"><label>服务器 URL</label><input type="text" id="mcpServerUrl" placeholder="http://localhost:8000" style="width:100%;padding:7px 10px;border:1px solid var(--border-color);border-radius:var(--radius-md);background:var(--bg-primary);color:var(--text-primary);font-size:13px;box-sizing:border-box;"></div><div class="config-group" style="margin-top:10px;"><label>API Key <span style="color:var(--text-muted);font-size:11px;">(可选，需要认证时填写)</span></label><input type="password" id="mcpServerApiKey" placeholder="sk-..." style="width:100%;padding:7px 10px;border:1px solid var(--border-color);border-radius:var(--radius-md);background:var(--bg-primary);color:var(--text-primary);font-size:13px;box-sizing:border-box;"></div><div class="config-group" style="margin-top:10px;"><label>描述 (可选)</label><input type="text" id="mcpServerDesc" placeholder="文件系统操作服务器" style="width:100%;padding:7px 10px;border:1px solid var(--border-color);border-radius:var(--radius-md);background:var(--bg-primary);color:var(--text-primary);font-size:13px;box-sizing:border-box;"></div><div style="display:flex;gap:10px;margin-top:12px;"><button class="btn-primary" onclick="addRemoteMCPServer()" style="padding:8px 20px;background:var(--accent-primary);color:white;border:none;border-radius:var(--radius-md);cursor:pointer;font-size:14px;"><i class="fas fa-plus"></i> 添加服务器</button><button id="mcpRemoteCancelEditBtn" class="btn-primary" onclick="cancelRemoteEdit()" style="display:none;padding:8px 20px;background:var(--accent-danger,#dc3545);color:white;border:none;border-radius:var(--radius-md);cursor:pointer;font-size:14px;"><i class="fas fa-times"></i> 取消编辑</button></div></div><div class="config-section-title" style="margin-top:0;"><i class="fas fa-list"></i> 已安装的远程服务器</div><div id="mcpServerList"></div></div>';

(function(){
    var el = document.getElementById('mcpSubRemote');
    if (el && !el.getAttribute('data-html-loaded')) {
        el.innerHTML = MCP_REMOTE_HTML;
        el.setAttribute('data-html-loaded', 'true');
    }
})();

function renderMCPServers() {
    var c = document.getElementById('mcpServerList');
    if (!c) return;
    var filtered = appState.mcpServers.filter(function(s) { return s.transport !== 'stdio'; });
    if (filtered.length === 0) {
        c.innerHTML = '<div style="text-align:center;padding:30px 20px;color:var(--text-muted);">'
            + '<div style="font-size:36px;margin-bottom:10px;">🌐</div>'
            + '<div style="font-size:14px;color:var(--text-secondary);">暂无已安装的远程服务器</div></div>';
        return;
    }
    c.innerHTML = filtered.map(function(s) {
        var online = s.online; var toolCount = s.toolCount || 0; var tools = s.tools || [];
        var statusClass = online ? 'online' : 'offline'; var statusText = online ? '● 在线' : '● 离线';
        var actionBtns = '';
        if (online) actionBtns += '<button class="btn-action btn-stop" onclick="event.stopPropagation();stopMCPServer(\'' + s.id + '\')" title="停止服务器">⏹ 停止</button>';
        else actionBtns += '<button class="btn-action btn-start" onclick="event.stopPropagation();startMCPServer(\'' + s.id + '\')" title="启动服务器">▶ 启动</button>';
        actionBtns += '<button class="btn-action btn-restart" onclick="event.stopPropagation();restartMCPServer(\'' + s.id + '\')" title="重启服务器">🔄 重启</button>';
        var toolsHtml = '';
        if (tools.length > 0) {
            toolsHtml = '<div style="font-size:10px;color:var(--text-muted);margin-top:4px;display:flex;flex-wrap:wrap;gap:3px;">';
            tools.forEach(function(t) { toolsHtml += '<span style="background:var(--bg-tertiary);padding:1px 5px;border-radius:3px;">' + t.name + '</span>'; });
            toolsHtml += '</div>';
        }
        return '<div class="mcp-server-card" style="cursor:pointer;" onclick="editRemoteMCPServer(\'' + s.id + '\')" title="点击将配置回填到表单进行编辑">'
            + '<div class="server-header"><div style="flex:1;min-width:0;">'
            + '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;">'
            + '<span class="server-name">' + (s.name || s.id) + '</span>'
            + '<span class="server-status ' + statusClass + '" style="font-size:11px;">' + statusText + '</span>'
            + '<span style="font-size:10px;background:var(--bg-tertiary);padding:1px 5px;border-radius:3px;color:var(--text-muted);">远程</span>'
            + (online ? '<span style="font-size:10px;color:var(--accent-color);">🔧 ' + toolCount + ' 工具</span>' : '')
            + '</div></div>'
            + '<button class="btn-delete" onclick="event.stopPropagation();removeMCPServer(\'' + s.id + '\')" title="删除服务器"><i class="fas fa-times"></i></button>'
            + '</div>'
            + '<div class="server-url" style="font-size:11px;">' + (s.url || s.description || '') + '</div>'
            + toolsHtml
            + '<div style="display:flex;gap:4px;margin-top:6px;">' + actionBtns + '</div></div>';
    }).join('');
}

function addRemoteMCPServer() {
    var name = document.getElementById('mcpServerName');
    var url = document.getElementById('mcpServerUrl');
    var desc = document.getElementById('mcpServerDesc');
    var apiKey = document.getElementById('mcpServerApiKey');
    if (!name || !url) return;
    if (!name.value.trim() || !url.value.trim()) { showToast('请填写名称和 URL', 'error'); return; }
    var serverId = name.value.toLowerCase().replace(/[^a-z0-9]/g, '_');
    var apiKeyVal = apiKey ? apiKey.value.trim() : '';
    // 检查是否是编辑模式：按钮上有 data-edit-sid 属性
    var addBtn = document.querySelector('#mcpSubRemote button[onclick*="addRemoteMCPServer"]');
    var editSid = addBtn ? addBtn.getAttribute('data-edit-sid') : null;
    var isEdit = editSid !== null && editSid !== '';
    var oldSid = isEdit ? editSid : null;

    function _afterSaved() {
        // 编辑模式：更新已有条目；否则新增
        if (isEdit && oldSid) {
            var idx = appState.mcpServers.findIndex(function(s) { return s.id === oldSid; });
            if (idx !== -1) {
                appState.mcpServers[idx] = { id: serverId, name: name.value.trim(), url: url.value.trim(), description: desc ? desc.value.trim() : '', enabled: true, online: appState.mcpServers[idx].online || false, tools: appState.mcpServers[idx].tools || [], env: apiKeyVal ? {API_KEY: apiKeyVal} : {} };
            } else {
                appState.mcpServers.push({ id: serverId, name: name.value.trim(), url: url.value.trim(), description: desc ? desc.value.trim() : '', enabled: true, online: false, tools: [], env: apiKeyVal ? {API_KEY: apiKeyVal} : {} });
            }
        } else {
            appState.mcpServers.push({ id: serverId, name: name.value.trim(), url: url.value.trim(), description: desc ? desc.value.trim() : '', enabled: true, online: false, tools: [], env: apiKeyVal ? {API_KEY: apiKeyVal} : {} });
        }
        renderMCPServers(); updateMCPBadge();
        showToast((isEdit ? '✅ 已更新服务器: ' : '✅ 已添加服务器: ') + name.value.trim(), 'success');
        name.value = ''; if (url) url.value = ''; if (desc) desc.value = ''; if (apiKey) apiKey.value = '';
        // 重置按钮为「添加服务器」，隐藏取消编辑按钮
        resetRemoteFormButtons();
        // 保存成功后强制刷新服务器列表（从后端重新加载配置）
        loadMCPServers();
    }

    if (window.mcp_bridge && window._bridgeReady) {
        // 编辑模式且 ID 变化时，先删除旧配置
        var deletePromise = (isEdit && oldSid && oldSid !== serverId)
            ? window.mcp_bridge.removeMCPServer(oldSid)
            : Promise.resolve(true);
        deletePromise.then(function() {
            return window.mcp_bridge.addMCPServer(serverId, name.value.trim(), url.value.trim(), desc ? desc.value.trim() : '', apiKeyVal);
        }).then(function(success) {
            if (success) { _afterSaved(); }
            else { showToast('❌ 保存服务器失败', 'error'); }
        });
    } else {
        _afterSaved();
    }
}

// 重置表单按钮状态：恢复「添加服务器」，隐藏「取消编辑」
function resetRemoteFormButtons() {
    var addBtn = document.querySelector('#mcpSubRemote button[onclick*="addRemoteMCPServer"]');
    if (addBtn) {
        addBtn.innerHTML = '<i class="fas fa-plus"></i> 添加服务器';
        addBtn.removeAttribute('data-edit-sid');
        addBtn.style.background = 'var(--accent-primary)';
        addBtn.style.display = '';
    }
    var cancelBtn = document.getElementById('mcpRemoteCancelEditBtn');
    if (cancelBtn) cancelBtn.style.display = 'none';
}

// 取消编辑：清空表单，恢复「添加服务器」按钮
function cancelRemoteEdit() {
    var name = document.getElementById('mcpServerName');
    var url = document.getElementById('mcpServerUrl');
    var desc = document.getElementById('mcpServerDesc');
    var apiKey = document.getElementById('mcpServerApiKey');
    if (name) name.value = '';
    if (url) url.value = '';
    if (desc) desc.value = '';
    if (apiKey) apiKey.value = '';
    resetRemoteFormButtons();
    showToast('已取消编辑', 'info');
}

// 点击远程服务器卡片：将配置信息回填到输入框
function editRemoteMCPServer(serverId) {
    var server = appState.mcpServers.find(function(s) { return s.id === serverId; });
    if (!server) return;
    var nameInput = document.getElementById('mcpServerName');
    var urlInput = document.getElementById('mcpServerUrl');
    var descInput = document.getElementById('mcpServerDesc');
    var apiKeyInput = document.getElementById('mcpServerApiKey');
    if (nameInput) nameInput.value = server.name || server.id || '';
    if (urlInput) urlInput.value = server.url || '';
    if (descInput) descInput.value = server.description || '';
    if (apiKeyInput) {
        var env = server.env || {};
        apiKeyInput.value = env['API_KEY'] || '';
    }
    // 更新按钮状态为「更新服务器」
    var addBtn = document.querySelector('#mcpSubRemote button[onclick*="addRemoteMCPServer"]');
    if (addBtn) {
        addBtn.innerHTML = '<i class="fas fa-save"></i> 更新服务器';
        addBtn.setAttribute('data-edit-sid', serverId);
        addBtn.style.background = 'var(--accent-warning, #d29922)';
    }
    // 显示「取消编辑」按钮
    var cancelBtn = document.getElementById('mcpRemoteCancelEditBtn');
    if (cancelBtn) cancelBtn.style.display = '';
    // 滚动到表单区域
    var section = document.getElementById('mcpSubRemote');
    if (section && section.scrollIntoView) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    showToast('✏️ 已载入配置: ' + (server.name || server.id), 'info');
}