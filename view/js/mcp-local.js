// ============================================
// MCP 本地服务器 - 渲染、添加、管理
// ============================================

var MCP_LOCAL_HTML = '<div class="config-section"><div class="config-section-title"><i class="fas fa-laptop"></i> 本地服务器</div><div style="margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid var(--border-color);"><div class="config-section-title" style="margin-bottom:12px;"><i class="fas fa-plus-circle"></i> 添加本地 STDIO 服务器</div><div style="margin-bottom:12px;"><label style="font-weight:600;font-size:13px;display:block;margin-bottom:6px;color:var(--text-primary);">选择本地项目目录</label><select id="localServerDir" onchange="onLocalDirChange()" style="width:100%;padding:8px 10px;border:1px solid var(--border-color);border-radius:var(--radius-md);background:var(--bg-primary);color:var(--text-primary);font-size:13px;"><option value="">— 选择已下载的 MCP 项目 —</option></select></div><div id="localAutoDetect" style="display:none;background:var(--bg-secondary);padding:10px 12px;border-radius:var(--radius-md);margin-bottom:12px;font-size:13px;line-height:1.8;color:var(--text-primary);"><div>📦 <strong id="localDetectName" style="color:var(--text-primary);">-</strong></div><div>📄 描述: <span id="localDetectDesc">-</span></div><div>🔧 入口: <code id="localDetectEntry" style="color:var(--accent-primary);">-</code></div><div>📋 包管理器: <span id="localDetectPM" style="color:var(--text-secondary);">-</span></div></div><div style="border-top:1px solid var(--border-color);margin:12px 0;"></div><div style="font-size:13px;font-weight:600;margin-bottom:8px;color:var(--text-primary);">⚙️ MCP 服务器配置 (JSON 字段对应)</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;"><div><label style="font-size:12px;display:block;margin-bottom:4px;color:var(--text-secondary);">服务器 ID <span style="color:var(--accent-danger);">*</span></label><input type="text" id="localServerId" placeholder="mcpServers 的键名" style="width:100%;padding:7px 10px;border:1px solid var(--border-color);border-radius:var(--radius-md);background:var(--bg-primary);color:var(--text-primary);font-size:13px;box-sizing:border-box;"></div><div><label style="font-size:12px;display:block;margin-bottom:4px;color:var(--text-secondary);">名称 <span style="color:var(--text-muted);">(name)</span></label><input type="text" id="localServerName" placeholder="如 My MCP Server" style="width:100%;padding:7px 10px;border:1px solid var(--border-color);border-radius:var(--radius-md);background:var(--bg-primary);color:var(--text-primary);font-size:13px;box-sizing:border-box;"></div></div><div style="margin-top:10px;"><label style="font-size:12px;display:block;margin-bottom:4px;color:var(--text-secondary);">命令 <span style="color:var(--accent-danger);">*</span> <span style="color:var(--text-muted);font-size:11px;">(command)</span></label><input type="text" id="localCommand" placeholder="如 node" style="width:100%;padding:7px 10px;border:1px solid var(--border-color);border-radius:var(--radius-md);background:var(--bg-primary);color:var(--text-primary);font-size:13px;box-sizing:border-box;"></div><div style="margin-top:10px;"><label style="font-size:12px;display:block;margin-bottom:4px;color:var(--text-secondary);">参数 <span style="color:var(--text-muted);font-size:11px;">(args, 每行一个)</span></label><textarea id="localArgs" rows="2" placeholder="dist/index.js" style="width:100%;padding:7px 10px;border:1px solid var(--border-color);border-radius:var(--radius-md);background:var(--bg-primary);color:var(--text-primary);font-size:13px;box-sizing:border-box;resize:vertical;font-family:monospace;"></textarea></div><div style="margin-top:10px;"><label style="font-size:12px;display:block;margin-bottom:4px;color:var(--text-secondary);">工作目录 <span style="color:var(--text-muted);font-size:11px;">(cwd)</span></label><input type="text" id="localCwd" placeholder="E:\path\to\server" style="width:100%;padding:7px 10px;border:1px solid var(--border-color);border-radius:var(--radius-md);background:var(--bg-primary);color:var(--text-primary);font-size:13px;box-sizing:border-box;"></div><div style="margin-top:10px;"><label style="font-size:12px;display:block;margin-bottom:4px;color:var(--text-secondary);">环境变量 <span style="color:var(--text-muted);font-size:11px;">(可选, env, JSON: {"KEY":"value"})</span></label><textarea id="localEnv" rows="4" placeholder=\'{"KEY1":"value1","KEY2":"value2"}\' style="width:100%;padding:7px 10px;border:1px solid var(--border-color);border-radius:var(--radius-md);background:var(--bg-primary);color:var(--text-primary);font-size:13px;box-sizing:border-box;resize:vertical;font-family:monospace;"></textarea></div><div style="margin-top:10px;"><label style="font-size:12px;display:block;margin-bottom:4px;color:var(--text-secondary);">描述 <span style="color:var(--text-muted);font-size:11px;">(description)</span></label><input type="text" id="localDescription" placeholder="服务器功能简介" style="width:100%;padding:7px 10px;border:1px solid var(--border-color);border-radius:var(--radius-md);background:var(--bg-primary);color:var(--text-primary);font-size:13px;box-sizing:border-box;"></div><div style="margin-top:16px;display:flex;gap:10px;"><button onclick="addLocalMCPServer()" style="padding:8px 20px;background:var(--accent-primary);color:white;border:none;border-radius:var(--radius-md);cursor:pointer;font-size:14px;"><i class="fas fa-plus"></i> 添加并启动</button><button id="localCancelEditBtn" onclick="cancelLocalEdit()" style="display:none;padding:8px 20px;background:var(--bg-secondary);color:var(--text-primary);border:1px solid var(--border-color);border-radius:var(--radius-md);cursor:pointer;font-size:14px;"><i class="fas fa-times"></i> 取消编辑</button></div></div><div class="config-section-title" style="margin-top:0;"><i class="fas fa-list"></i> 已安装的本地服务器</div><div id="mcpLocalServerList"></div></div>';

(function(){
    var el = document.getElementById('mcpSubLocal');
    if (el && !el.getAttribute('data-html-loaded')) {
        el.innerHTML = MCP_LOCAL_HTML;
        el.setAttribute('data-html-loaded', 'true');
    }
})();

function renderMCPLocalServers() {
    var c = document.getElementById('mcpLocalServerList');
    if (!c) { console.warn('[MCP-Local] ❌ 找不到 mcpLocalServerList 元素'); return; }
    console.log('[MCP-Local] renderMCPLocalServers 被调用, 当前 mcpServers=', appState.mcpServers.length, '条');
    var filtered = appState.mcpServers.filter(function(s) { return s.transport === 'stdio'; });
    if (filtered.length === 0) {
        c.innerHTML = '<div style="text-align:center;padding:30px 20px;color:var(--text-muted);">'
            + '<div style="font-size:36px;margin-bottom:10px;">📦</div>'
            + '<div style="font-size:14px;color:var(--text-secondary);">暂无已安装的本地服务器</div></div>';
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
            toolsHtml = '<div class="server-tools">';
            tools.forEach(function(t) { toolsHtml += '<span class="tool-tag">' + t.name + '</span>'; });
            toolsHtml += '</div>';
        }
        return '<div class="mcp-server-card">'
            + '<div class="server-header"><div style="flex:1;min-width:0;">'
            + '<div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;">'
            + '<span class="server-name">' + (s.name || s.id) + '</span>'
            + '<span class="server-status ' + statusClass + '">' + statusText + '</span>'
            + '<span class="server-badge">本地</span>'
            + (online ? '<span class="server-tool-count">🔧 ' + toolCount + ' 工具</span>' : '')
            + '</div></div>'
            + '<button class="btn-delete" onclick="removeMCPServer(\'' + s.id + '\')" title="删除服务器"><i class="fas fa-times"></i></button>'
            + '</div>'
            + '<div class="server-url">' + (s.url || s.description || '') + '</div>'
            + toolsHtml + '<div class="server-actions">' + actionBtns + '</div></div>';
    }).join('');
}

// ============================================
// 本地项目目录扫描与选择
// ============================================

function scanLocalServerDirs() {
    var select = document.getElementById('localServerDir');
    if (!select) return;
    var savedVal = select.getAttribute('data-selected') || '';
    select.innerHTML = '<option value="">— 加载中... —</option>';
    if (window.mcp_bridge && window._bridgeReady) {
        // 始终拉取 tools/mcp/server/ 全部目录 + 当前配置，合并后全量展示
        Promise.all([window.mcp_bridge.getLocalServerDirs(), window.mcp_bridge.getMCPConfig()]).then(function(res) {
            try {
                var dirs = typeof res[0] === 'string' ? JSON.parse(res[0]) : res[0];
                var config = typeof res[1] === 'string' ? JSON.parse(res[1]) : res[1];
                populateLocalServerDropdown(dirs || [], (config && config.mcpServers) || {}, savedVal);
            } catch(e) { scanServerDirsFallback(select); }
        }).catch(function() { scanServerDirsFallback(select); });
    } else {
        setTimeout(function() {
            if (window.mcp_bridge && window._bridgeReady) scanLocalServerDirs();
            else scanServerDirsFallback(select);
        }, 1000);
    }
}

function parseLocalDirValue(val) {
    if (!val) return null;
    try { return JSON.parse(val); } catch(e) { return null; }
}

function buildLocalInstalledMap(servers, dirs) {
    var map = {};
    var seen = {};
    (dirs || []).forEach(function(d) { var n = (d && (d.name || d.path)) || d; if (n) seen[n] = true; });
    var extra = [];
    Object.keys(servers || {}).forEach(function(sid) {
        var s = servers[sid];
        if (!s || s.transport === 'http') return;
        var cwd = s.cwd || '';
        var folder = '';
        if (cwd) {
            var parts = String(cwd).replace(/\\/g, '/').split('/').filter(Boolean);
            folder = parts.length > 0 ? parts[parts.length - 1] : '';
        }
        var key = folder || sid;
        if (!map[key]) map[key] = { sid: sid };
        // 目录名 / server_id 都不在 tools/mcp/server 列表里 → 追加到下拉末尾，保持老功能不丢
        if (!seen[folder] && !seen[sid]) extra.push(sid);
    });
    return { map: map, extra: extra };
}

function populateLocalServerDropdown(dirs, servers, savedVal) {
    var select = document.getElementById('localServerDir');
    if (!select) return;
    var installed = buildLocalInstalledMap(servers, dirs);
    var options = '<option value="">— 选择已下载的 MCP 项目 —</option>';
    var seenDirs = {};
    (dirs || []).forEach(function(d) {
        var name = (d && (d.name || d.path)) || d;
        if (!name) return;
        seenDirs[name] = true;
        var info = installed.map[name];
        var val = JSON.stringify({ dir: name, installed: info ? 1 : 0, sid: info ? info.sid : '' });
        options += '<option value="' + val.replace(/"/g, '&quot;') + '">' + (info ? '✅ ' : '📁 ') + name + '</option>';
    });
    installed.extra.forEach(function(sid) {
        if (seenDirs[sid]) return;
        seenDirs[sid] = true;
        var val = JSON.stringify({ dir: sid, installed: 1, sid: sid });
        options += '<option value="' + val.replace(/"/g, '&quot;') + '">✅ ' + sid + '</option>';
    });
    select.innerHTML = options;
    // 恢复选中：按 dir 匹配（value 可能因 installed 状态变化字符串不同，不能直接 select.value=）
    if (savedVal) {
        var savedSel = parseLocalDirValue(savedVal);
        var found = false;
        if (savedSel) {
            for (var i = 0; i < select.options.length; i++) {
                var o = parseLocalDirValue(select.options[i].value);
                if (o && o.dir === savedSel.dir) { select.selectedIndex = i; found = true; break; }
            }
        }
        if (!found) select.value = '';
        select.removeAttribute('data-selected');
    }
    if (select.value) onLocalDirChange();
    else clearLocalForm();
}

function scanServerDirsFallback(select) {
    if (window.mcp_bridge && window._bridgeReady) {
        window.mcp_bridge.getLocalServerDirs().then(function(dirsStr) {
            try {
                var dirs = typeof dirsStr === 'string' ? JSON.parse(dirsStr) : dirsStr;
                if (dirs && dirs.length > 0) {
                    var options = '<option value="">— 选择已下载的 MCP 项目 —</option>';
                    dirs.forEach(function(d) {
                        var name = (d && (d.name || d.path)) || d;
                        var val = JSON.stringify({ dir: name, installed: 0, sid: '' });
                        options += '<option value="' + val.replace(/"/g, '&quot;') + '">📁 ' + name + '</option>';
                    });
                    select.innerHTML = options;
                } else select.innerHTML = '<option value="">— 暂无可选目录 —</option>';
            } catch(e) { select.innerHTML = '<option value="">— 暂无可选目录 —</option>'; }
        }).catch(function() { select.innerHTML = '<option value="">— 暂无可选目录 —</option>'; });
    } else select.innerHTML = '<option value="">— 暂无可选目录 —</option>';
}

// ============================================
// 本地服务器添加/编辑/删除
// ============================================

function addLocalMCPServer() {
    var addBtn = document.querySelector('#mcpSubLocal button[onclick*="addLocalMCPServer"]');
    var mode = addBtn ? (addBtn.getAttribute('data-local-mode') || 'manual') : 'manual';
    var dirSelect = document.getElementById('localServerDir');
    var dirVal = dirSelect ? dirSelect.value : '';
    var sel = dirVal ? parseLocalDirValue(dirVal) : null;

    // 启动并重启（刚安装完成的状态）：直接重启（未运行则启动）
    if (mode === 'start') {
        var startSid = document.getElementById('localServerId').value.trim();
        if (!startSid) { showToast('请先选择已安装的服务器', 'error'); return; }
        if (window.mcp_bridge && window._bridgeReady) {
            showToast('🔄 正在启动/重启: ' + startSid, 'info');
            window.mcp_bridge.restartMCPServer(startSid).then(function(success) {
                if (success) { showToast('✅ 已启动: ' + startSid, 'success'); refreshServerStatus(); }
                else { showToast('❌ 启动失败: ' + startSid, 'error'); }
            });
        }
        return;
    }

    // 选中了未安装目录 → 启动 AI 安装助手
    if (sel && !sel.installed) {
        startLocalServerInstall(sel.dir);
        return;
    }

    // ===== 手动添加 / 配置并重启已有服务器 =====
    var id = document.getElementById('localServerId');
    var name = document.getElementById('localServerName');
    var cmd = document.getElementById('localCommand');
    var args = document.getElementById('localArgs');
    var cwd = document.getElementById('localCwd');
    var env = document.getElementById('localEnv');
    var desc = document.getElementById('localDescription');
    if (!id || !cmd || !id.value.trim() || !cmd.value.trim()) { showToast('请填写服务器 ID 和命令', 'error'); return; }
    var serverId = id.value.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '_');
    var argsList = args.value.trim().split('\n').filter(function(l) { return l.trim(); });
    var envObj = {};
    if (env.value.trim()) { try { envObj = JSON.parse(env.value.trim()); } catch(e) { showToast('环境变量 JSON 格式错误', 'error'); return; } }
    var config = { "transport": "stdio", "command": cmd.value.trim(), "args": argsList, "cwd": cwd.value.trim() || '', "env": envObj, "enabled": true, "description": desc.value.trim() || '', "name": name.value.trim() || serverId };

    // 编辑已有服务器（"配置并重启"模式）：按钮上有 data-edit-sid 属性
    var editSid = addBtn ? addBtn.getAttribute('data-edit-sid') : null;
    var isEdit = mode === 'edit' && editSid !== null && editSid !== '';

    if (window.mcp_bridge && window._bridgeReady) {
        window.mcp_bridge.getMCPConfig().then(function(configStr) {
            try {
                var fullConfig = typeof configStr === 'string' ? JSON.parse(configStr) : configStr;
                var servers = fullConfig.mcpServers || {};
                servers[serverId] = config;
                fullConfig.mcpServers = servers;

                if (isEdit) {
                    // 配置并重启：先保存配置，再重启指定服务器
                    showToast('🔄 正在配置并重启服务器: ' + serverId, 'info');
                    // 1. 写入配置（saveMCPConfig 只会重启有变化的服务器，但我们的配置可能没变）
                    window.mcp_bridge.saveMCPConfig(JSON.stringify(fullConfig));
                    // 2. 如果不是同一台服务器（改了 ID），停止旧的
                    if (editSid && editSid !== serverId) {
                        window.mcp_bridge.stopMCPServer(editSid);
                    }
                    // 3. 重启目标服务器（unregister + register）
                    window.mcp_bridge.restartMCPServer(serverId);
                    showToast('✅ 已配置并重启: ' + serverId, 'success');
                    clearLocalForm(); loadMCPServers();
                } else {
                    // 手动添加新服务器（未选择目录）
                    var saveOk = window.mcp_bridge.saveMCPConfig(JSON.stringify(fullConfig));
                    if (saveOk !== false) { showToast('✅ 已保存服务器: ' + serverId, 'success'); clearLocalForm(); loadMCPServers(); }
                    else { showToast('❌ 保存失败', 'error'); }
                }
            } catch(e) { showToast('❌ 配置解析失败', 'error'); }
        });
    } else {
        appState.mcpServers.push({ id: serverId, name: name.value.trim() || serverId, url: '', description: desc.value.trim() || '', transport: 'stdio', enabled: true, online: false, tools: [] });
        renderMCPLocalServers(); updateMCPBadge();
        showToast('✅ 已添加服务器（本地）', 'success');
        clearLocalForm();
    }
}

function startLocalServerInstall(dirName) {
    // 未安装目录 → 后端 installLocalServer 启动 AI 安装助手（新开 AI 对话走安装审阅）
    if (!window.mcp_bridge || !window._bridgeReady) { showToast('后端未就绪', 'error'); return; }
    showToast('🚀 正在启动 AI 安装助手: ' + dirName, 'info');
    window.mcp_bridge.installLocalServer(dirName);
}

function clearLocalForm() {
    var ids = ['localServerId','localServerName','localCommand','localArgs','localCwd','localEnv','localDescription'];
    ids.forEach(function(id) { var el = document.getElementById(id); if (el) el.value = ''; });
    var dir = document.getElementById('localServerDir'); if (dir) dir.value = '';
    var detect = document.getElementById('localAutoDetect'); if (detect) detect.style.display = 'none';
    updateLocalButtonState(null);
}

function onLocalDirChange() {
    var select = document.getElementById('localServerDir');
    var val = select.value;
    var detectDiv = document.getElementById('localAutoDetect');
    // 用户切换了下拉选项 → 清除「刚安装」标记（同一安装的多次自动重扫 value 不变，标记保留到 2s 超时）
    if (window._localSelectedValue !== undefined && window._localSelectedValue !== val) {
        window._localJustInstalledDir = null;
    }
    window._localSelectedValue = val;
    if (!val) { if (detectDiv) detectDiv.style.display = 'none'; clearLocalForm(); return; }
    var sel = parseLocalDirValue(val);
    if (!sel) { fillLocalFormFromPipe(val); return; }
    if (sel.installed && sel.sid) {
        if (window.mcp_bridge && window._bridgeReady) {
            window.mcp_bridge.getMCPConfig().then(function(configStr) {
                try {
                    var config = typeof configStr === 'string' ? JSON.parse(configStr) : configStr;
                    var serverConfig = (config.mcpServers || {})[sel.sid];
                    if (serverConfig) {
                        fillLocalFormFromConfig(sel.sid, serverConfig, window._localJustInstalledDir === sel.sid);
                        return;
                    }
                } catch(e) {}
                fillLocalFormFromSelection(sel);
            });
        } else { fillLocalFormFromSelection(sel); }
    } else {
        fillLocalFormFromSelection(sel);
    }
}

function fillLocalFormFromSelection(sel) {
    var detectDiv = document.getElementById('localAutoDetect');
    if (detectDiv) {
        detectDiv.style.display = 'block';
        document.getElementById('localDetectName').textContent = sel.dir;
        document.getElementById('localDetectDesc').textContent = '';
        document.getElementById('localDetectEntry').textContent = '';
        document.getElementById('localDetectPM').textContent = sel.installed ? '✅ 已安装' : '未安装 → 点击「添加并启动配置」启动 AI 安装助手';
    }
    document.getElementById('localServerId').value = String(sel.dir).toLowerCase().replace(/[^a-z0-9_-]/g, '_');
    document.getElementById('localServerName').value = sel.dir;
    document.getElementById('localCommand').value = '';
    document.getElementById('localArgs').value = '';
    document.getElementById('localCwd').value = '';
    document.getElementById('localEnv').value = '';
    document.getElementById('localDescription').value = '';
    updateLocalButtonState(sel.installed ? sel.sid : null, sel.installed ? 'edit' : 'add');
}

function fillLocalFormFromConfig(sid, cfg, justInstalled) {
    var detectDiv = document.getElementById('localAutoDetect');
    if (detectDiv) { detectDiv.style.display = 'block';
        document.getElementById('localDetectName').textContent = cfg.name || sid;
        document.getElementById('localDetectDesc').textContent = cfg.description || '';
        document.getElementById('localDetectEntry').textContent = (cfg.args || []).join(' ') || cfg.command || '';
        document.getElementById('localDetectPM').textContent = cfg.cwd ? '📁 ' + cfg.cwd : ''; }
    document.getElementById('localServerId').value = sid;
    document.getElementById('localServerName').value = cfg.name || sid;
    document.getElementById('localCommand').value = cfg.command || '';
    document.getElementById('localArgs').value = (cfg.args || []).join('\n');
    document.getElementById('localCwd').value = cfg.cwd || '';
    document.getElementById('localEnv').value = cfg.env && Object.keys(cfg.env).length > 0 ? JSON.stringify(cfg.env, null, 2) : '';
    document.getElementById('localDescription').value = cfg.description || '';
    updateLocalButtonState(sid, justInstalled ? 'start' : 'edit');
}

function fillLocalFormFromPipe(val) {
    var detectDiv = document.getElementById('localAutoDetect');
    if (detectDiv) { detectDiv.style.display = 'block';
        var parts = val.split('|');
        document.getElementById('localDetectName').textContent = parts[0] || '-';
        document.getElementById('localDetectDesc').textContent = parts[1] || '-';
        document.getElementById('localDetectEntry').textContent = parts[2] || '-';
        document.getElementById('localDetectPM').textContent = parts[3] || '-'; }
    document.getElementById('localServerId').value = val.split('|')[0].toLowerCase().replace(/[^a-z0-9_-]/g, '_');
    document.getElementById('localServerName').value = val.split('|')[0];
    var entry = val.split('|')[2];
    if (entry) {
        if (entry.endsWith('.js')) { document.getElementById('localCommand').value = 'node'; document.getElementById('localArgs').value = entry; }
        else if (entry.endsWith('.py')) { document.getElementById('localCommand').value = 'python'; document.getElementById('localArgs').value = entry; }
    }
    document.getElementById('localCwd').value = val.split('|cwd:')[1] || '';
    document.getElementById('localEnv').value = '';
    document.getElementById('localDescription').value = val.split('|')[1] || '';
    updateLocalButtonState(null, 'add');
}

function updateLocalButtonState(existingSid, mode) {
    var addBtn = document.querySelector('#mcpSubLocal button[onclick*="addLocalMCPServer"]');
    if (!addBtn) return;
    var cancelBtn = document.getElementById('localCancelEditBtn');
    var m = mode || (existingSid ? 'edit' : 'manual');
    addBtn.setAttribute('data-local-mode', m);
    if (existingSid) addBtn.setAttribute('data-edit-sid', existingSid);
    else addBtn.removeAttribute('data-edit-sid');
    var html = '<i class="fas fa-plus"></i> 添加并启动';
    var bg = 'var(--accent-primary)';
    var showCancel = false;
    if (m === 'edit') { html = '<i class="fas fa-sync"></i> 配置并重启'; bg = 'var(--accent-warning, #d29922)'; showCancel = true; }
    else if (m === 'start') { html = '<i class="fas fa-play"></i> 启动并重启'; bg = 'var(--accent-success, #2ea043)'; showCancel = true; }
    else if (m === 'add') { html = '<i class="fas fa-rocket"></i> 添加并启动配置'; bg = 'var(--accent-primary)'; showCancel = false; }
    addBtn.innerHTML = html;
    addBtn.style.background = bg;
    if (cancelBtn) cancelBtn.style.display = showCancel ? 'inline-flex' : 'none';
}

function onLocalInstallFinished(serverId) {
    // 本地面板：AI 安装完成 → 重新扫描下拉（标记已安装），表单按钮切「启动并重启」
    window._localJustInstalledDir = serverId;
    if (window._localJustInstalledTimeout) clearTimeout(window._localJustInstalledTimeout);
    window._localJustInstalledTimeout = setTimeout(function() { window._localJustInstalledDir = null; }, 2000);
    var select = document.getElementById('localServerDir');
    if (select && select.value) {
        select.setAttribute('data-selected', select.value);
        if (typeof scanLocalServerDirs === 'function') scanLocalServerDirs();
    }
}

function cancelLocalEdit() {
    clearLocalForm();
    showToast('已取消编辑', 'info');
}

function removeMCPServer(serverId) {
    if (!window.mcp_bridge || !window._bridgeReady) {
        appState.mcpServers = appState.mcpServers.filter(function(s) { return s.id !== serverId; });
        if (typeof renderMCPServers === 'function') renderMCPServers();
        renderMCPLocalServers(); updateMCPBadge(); return;
    }
    window.mcp_bridge.removeMCPServer(serverId).then(function(success) {
        if (success) {
            appState.mcpServers = appState.mcpServers.filter(function(s) { return s.id !== serverId; });
            if (typeof renderMCPServers === 'function') renderMCPServers();
            renderMCPLocalServers(); updateMCPBadge();
            showToast('✅ 已删除服务器: ' + serverId, 'success');
        } else { showToast('❌ 删除失败', 'error'); }
    });
}