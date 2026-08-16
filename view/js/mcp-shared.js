// ============================================
// MCP Shared - 公共函数（日志、启动/停止、状态）
// ============================================

// 配置面板 HTML 注入
var MCP_CONFIG_HTML = '<div class="config-section"><div class="config-section-title"><i class="fas fa-code"></i> JSON 配置</div><div class="json-editor-container"><textarea class="json-editor" id="mcpJsonConfig" spellcheck="false" style="width:100%;min-height:400px;background:var(--bg-input);border:1px solid var(--border-color);border-radius:var(--radius-md);padding:12px;font-family:monospace;font-size:13px;color:var(--text-primary);">{"mcpServers":{}}</textarea><div class="json-actions" style="display:flex;gap:4px;margin-top:8px;"><button onclick="formatJSON()" style="padding:6px 12px;border:1px solid var(--border-color);border-radius:var(--radius-sm);background:var(--bg-secondary);color:var(--text-primary);cursor:pointer;font-size:12px;"><i class="fas fa-magic"></i> 格式化</button><button onclick="validateJSON()" style="padding:6px 12px;border:1px solid var(--border-color);border-radius:var(--radius-sm);background:var(--bg-secondary);color:var(--text-primary);cursor:pointer;font-size:12px;"><i class="fas fa-check-circle"></i> 验证</button><button onclick="loadMCPConfigToEditor()" style="padding:6px 12px;border:1px solid var(--border-color);border-radius:var(--radius-sm);background:var(--bg-hover);color:var(--text-primary);cursor:pointer;font-size:12px;"><i class="fas fa-sync"></i> 刷新</button><button onclick="applyJSONConfig()" style="padding:6px 12px;border:1px solid var(--border-color);border-radius:var(--radius-sm);background:var(--accent-primary);color:white;cursor:pointer;font-size:12px;"><i class="fas fa-save"></i> 应用</button></div></div></div>';

(function(){
    var el = document.getElementById('mcpSubConfig');
    if (el && !el.getAttribute('data-html-loaded')) {
        el.innerHTML = MCP_CONFIG_HTML;
        el.setAttribute('data-html-loaded', 'true');
    }
})();

// ============================================
// 日志（点击卡片展开，显示命令和运行输出）
// ============================================
function showMCPLog(itemId, title) {
    var logDiv = document.getElementById('mcpLog_' + itemId);
    if (!logDiv) return;
    logDiv.style.display = 'block';
    var content = logDiv.querySelector('.mcp-log-content');
    if (content) {
        content.innerHTML += '<div style="color:var(--text-secondary);margin-bottom:2px;font-size:11px;">' + title + '</div>';
        content.scrollTop = content.scrollHeight;
    }
    _updateLogCount(itemId, content);
}

// 已加载过数据库历史日志的集合（避免重复加载追加）
var _mcpLogLoadedFromDB = {};

// 从数据库加载该服务器的历史日志（应用重启/市场刷新后恢复日志显示）
function loadMCPLogFromDB(itemId) {
    if (!itemId || _mcpLogLoadedFromDB[itemId]) return;
    if (!window.mcp_bridge || !window._bridgeReady) return;
    _mcpLogLoadedFromDB[itemId] = true;
    var content = document.querySelector('#mcpLog_' + itemId + ' .mcp-log-content');
    if (!content) return;
    try {
        var p = window.mcp_bridge.getMCPLog(itemId);
        if (p && typeof p.then === 'function') {
            p.then(function(logStr) {
                if (logStr && typeof logStr === 'string' && logStr.trim()) {
                    var lines = logStr.split('\n');
                    for (var i = 0; i < lines.length; i++) {
                        if (lines[i] !== '') mcpAppendLog(itemId, lines[i]);
                    }
                    var countEl = document.getElementById('mcpLogCount_' + itemId);
                    if (countEl && content) countEl.textContent = '(' + content.children.length + ' 条)';
                }
            }).catch(function(e) {
                console.warn('[MCP] 加载历史日志失败:', itemId, e);
                delete _mcpLogLoadedFromDB[itemId];  // 失败允许重试
            });
        } else if (p && typeof p === 'string' && p.trim()) {
            var lines2 = p.split('\n');
            for (var j = 0; j < lines2.length; j++) {
                if (lines2[j] !== '') mcpAppendLog(itemId, lines2[j]);
            }
            var countEl2 = document.getElementById('mcpLogCount_' + itemId);
            if (countEl2 && content) countEl2.textContent = '(' + content.children.length + ' 条)';
        }
    } catch (e) {
        console.warn('[MCP] 加载历史日志异常:', itemId, e);
        delete _mcpLogLoadedFromDB[itemId];
    }
}

function mcpAppendLog(itemId, line, replaceLast) {
    var content = document.querySelector('#mcpLog_' + itemId + ' .mcp-log-content');
    if (!content) {
        // 没有日志面板时跳过的警告日志（不创建浮动 DOM 元素）
        console.log('[mcp:' + itemId + '] ' + line);
        return;
    }
    if (replaceLast && content.lastChild) {
        content.lastChild.textContent = line;
    } else {
        var p = document.createElement('div');
        p.textContent = line;
        p.style.cssText = 'word-break:break-all;overflow-wrap:break-word;';
        content.appendChild(p);
    }
    content.scrollTop = content.scrollHeight;
    console.log('[mcp:' + itemId + '] ' + line);
}

// 记录正在卸载的服务器 ID，用于回调时区分安装/卸载操作
var _pendingUninstallIds = {};

function mcpFinishInstall(itemId, returnCode, installed) {
    var logDiv = document.getElementById('mcpLog_' + itemId);
    var content = logDiv ? logDiv.querySelector('.mcp-log-content') : null;
    if (content) {
        var p = document.createElement('div');
        p.style.cssText = 'margin-top:4px;padding-top:4px;border-top:1px solid var(--border-color);font-weight:600;font-size:11px;';
        p.textContent = returnCode === 0 ? '✅ 操作成功' : '❌ 操作失败 (code: ' + returnCode + ')';
        content.appendChild(p);
        content.scrollTop = content.scrollHeight;
    }
    if (logDiv && content) _updateLogCount(itemId, content);
    // 操作失败时清理卸载标记，避免影响后续安装
    if (returnCode !== 0 && _pendingUninstallIds[itemId]) {
        delete _pendingUninstallIds[itemId];
    }
    if (returnCode === 0) {
        var item = appState.mcpMarket.find(function(m) { return m.id === itemId; });
        if (item) {
            var name = item.title || item.name || itemId;
            var isUninstall = !!_pendingUninstallIds[itemId];
            if (isUninstall) {
                // ===== 卸载完成 =====
                item.installed = false;
                item.serverId = '';   // ★ 清除残留 serverId，避免后续 merge 误判为已安装
                appState.mcpServers = appState.mcpServers.filter(function(s) { return s.id !== itemId; });
                delete _pendingUninstallIds[itemId];
            } else {
                // ===== 安装完成 =====
                item.installed = true;
                // 用真实 serverId（repo-name，配置 key）关联服务器列表，而非市场 ID
                var serverRealId = item.serverId || itemId;
                item.serverId = serverRealId;   // ★ 回写市场项 serverId，确保后续 merge 不覆盖已安装态
                var existing = appState.mcpServers.find(function(s) { return s.id === serverRealId; });
                if (!existing) {
                    appState.mcpServers.push({
                        id: serverRealId, name: name,
                        url: item.githubRepoUrl || '', description: item.description || '',
                        transport: 'stdio', enabled: true, online: false, tools: []
                    });
                }
            }
            // 强制刷新市场与服务列表，确保「安装→卸载」按钮切换
            if (typeof loadMCPMarket === 'function') loadMCPMarket();
            if (typeof loadMCPServers === 'function') loadMCPServers();
            // 本地面板安装完成钩子：刷新下拉/表单并把按钮切为「启动并重启」
            if (typeof onLocalInstallFinished === 'function') onLocalInstallFinished(itemId);
            // 重新渲染但不关闭日志窗口：记录日志面板状态，渲染后恢复
            var wasLogOpen = logDiv && logDiv.style.display === 'block';
            if (typeof renderMCPMarket === 'function') renderMCPMarket();
            if (wasLogOpen) showMCPLog(itemId, '');  // 恢复日志显示
            if (typeof renderMCPServers === 'function') renderMCPServers();
            if (typeof renderMCPLocalServers === 'function') renderMCPLocalServers();
            showToast(isUninstall ? '🗑️ MCP 服务器已卸载: ' + name : '📦 MCP 服务器已安装: ' + name, isUninstall ? 'warning' : 'success');
        }
        if (typeof loadMCPServers === 'function') loadMCPServers();
    }
    if (typeof updateMCPBadge === 'function') updateMCPBadge();
}

function mcpServerLog(itemId, line) {
    mcpAppendLog(itemId, '🔧 ' + line);
}

function _updateLogCount(itemId, content) {
    var countEl = document.getElementById('mcpLogCount_' + itemId);
    if (countEl && content) countEl.textContent = '(' + content.children.length + ' 条)';
}

// ============================================
// 服务器启动/停止/状态刷新
// ============================================
function startMCPServer(serverId) {
    if (window.mcp_bridge && window._bridgeReady) {
        showToast('⏳ 启动中: ' + serverId, 'info');
        window.mcp_bridge.startMCPServer(serverId).then(function(success) {
            if (success) { showToast('✅ 已启动: ' + serverId, 'success'); refreshServerStatus(); }
            else { showToast('❌ 启动失败: ' + serverId, 'error'); }
        });
    }
}
function stopMCPServer(serverId) {
    if (window.mcp_bridge && window._bridgeReady) {
        showToast('⏳ 停止中: ' + serverId, 'info');
        window.mcp_bridge.stopMCPServer(serverId).then(function(success) {
            if (success) { showToast('🛑 已停止: ' + serverId, 'warning'); refreshServerStatus(); }
        });
    }
}
function restartMCPServer(serverId) {
    if (window.mcp_bridge && window._bridgeReady) {
        showToast('🔄 重启中: ' + serverId, 'info');
        window.mcp_bridge.restartMCPServer(serverId).then(function(success) {
            if (success) { showToast('✅ 已重启: ' + serverId, 'success'); refreshServerStatus(); }
            else { showToast('❌ 重启失败: ' + serverId, 'error'); }
        });
    }
}
function refreshServerStatus() { if (typeof loadMCPServers === 'function') loadMCPServers(); }

// ============================================
// MCP 状态徽标
// ============================================
// MCP 状态触发更新 — 后端后台服务器启动完成后 push 通知前端
// 不再使用轮询，而是通过桥接层的 pushMCPStatus 触发
function startMCPStatusPolling() {
    // 3 秒后拉取一次初始状态（等后端连接就绪）
    setTimeout(function() {
        if (window.mcp_bridge && window._bridgeReady) {
            loadMCPServers();
        }
    }, 3000);
}

function updateMCPBadge() {
    var total = appState.mcpServers.length;
    var e = appState.mcpServers.filter(function(s) { return s.enabled && s.online; }).length;
    var t = appState.mcpServers.filter(function(s) { return s.enabled; }).length;
    var b = document.getElementById('mcpBadge');
    var f = document.getElementById('footerMCPStatus');
    if (t > 0) { b.style.display = 'inline'; b.textContent = e; if (f) f.textContent = '✅ ' + e + '/' + t + ' 在线'; }
    else { b.style.display = 'none'; if (f) f.textContent = '未连接'; }
}

// ============================================
// MCP 子标签切换
// ============================================
function switchMCPSubTab(tab) {
    console.log('[MCP] 🔄 switchMCPSubTab:', tab, 'bridgeReady=' + window._bridgeReady + ', mcp_bridge=' + !!window.mcp_bridge);
    document.querySelectorAll('.mcp-sub-tab').forEach(function(t) { t.classList.remove('active'); });
    document.querySelector('.mcp-sub-tab[data-subtab="' + tab + '"]')?.classList.add('active');
    ['mcpSubMarket', 'mcpSubLocal', 'mcpSubRemote', 'mcpSubConfig'].forEach(function(id) {
        var el = document.getElementById(id); if (el) el.style.display = 'none';
    });
    var map = { market: 'mcpSubMarket', local: 'mcpSubLocal', remote: 'mcpSubRemote', config: 'mcpSubConfig' };
    var el = document.getElementById(map[tab]);
    if (el) el.style.display = 'block';
    if (tab === 'local') {
        console.log('[MCP] 📍 扫描本地项目目录和加载服务列表...');
        if (typeof scanLocalServerDirs === 'function') scanLocalServerDirs();
        if (window.mcp_bridge && window._bridgeReady) { if (typeof loadMCPServers === 'function') loadMCPServers(); }
        else {
            setTimeout(function() {
                if (window.mcp_bridge && window._bridgeReady) {
                    if (typeof scanLocalServerDirs === 'function') scanLocalServerDirs();
                    if (typeof loadMCPServers === 'function') loadMCPServers();
                }
            }, 1000);
        }
    }
    if (tab === 'remote') {
        if (window.mcp_bridge && window._bridgeReady) { if (typeof loadMCPServers === 'function') loadMCPServers(); }
        else { setTimeout(function() { if (window.mcp_bridge && window._bridgeReady && typeof loadMCPServers === 'function') loadMCPServers(); }, 1000); }
    }
    if (tab === 'market' && typeof loadMCPMarket === 'function') loadMCPMarket();
    if (tab === 'config' && typeof loadMCPConfigToEditor === 'function') loadMCPConfigToEditor();
}

// ============================================
// API Key 输入对话框
// ============================================
// 关闭 API Key 对话框并通知后端取消（env 留空续接 AI 审阅）
function closeAPIKeyDialog(serverId) {
    var overlay = document.getElementById('apiKeyDialogOverlay');
    if (overlay) overlay.remove();
    // 仅当后端桥接就绪且提供了 serverId 时通知取消，避免遮罩连点重复调用
    if (serverId && window.mcp_bridge && window._bridgeReady) {
        window.mcp_bridge.cancelEnvVars(serverId);
    }
}

function showAPIKeyDialog(data) {
    var serverId = data.server_id || 'unknown';
    var envVars = data.env_vars || [];
    if (envVars.length === 0) {
        envVars = [{name: 'API_KEY', description: '请从该 MCP 服务器的官网获取 API 密钥', required: true}];
    }
    var overlay = document.createElement('div');
    overlay.id = 'apiKeyDialogOverlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;';
    var dialog = document.createElement('div');
    dialog.style.cssText = 'background:var(--bg-primary,#1a1d23);border:1px solid var(--border-color,#2d3240);border-radius:12px;padding:24px;max-width:500px;width:90%;max-height:80vh;overflow-y:auto;';
    // 收集所有唯一的 URL
    var urls = [];
    var urlSet = {};
    envVars.forEach(function(v) {
        if (v.url && !urlSet[v.url]) { urlSet[v.url] = true; urls.push(v.url); }
    });
    var urlHtml = '';
    if (urls.length > 0) {
        urlHtml = '<div style="margin-bottom:12px;padding:8px 10px;background:rgba(138,180,248,0.08);border:1px solid rgba(138,180,248,0.2);border-radius:6px;">';
        urlHtml += '<div style="font-size:11px;color:var(--text-muted,#9aa0a6);margin-bottom:4px;">🔗 点击下面的链接获取 API Key：</div>';
        urls.forEach(function(u) {
            var safeUrl = u.replace(/'/g, "\\'");
            urlHtml += '<div style="margin:2px 0;"><a href="' + safeUrl + '" target="_blank" style="font-size:12px;color:var(--accent-color,#8ab4f8);word-break:break-all;" onclick="event.preventDefault();window.mcp_bridge && window.mcp_bridge.openExternalUrl(\'' + safeUrl + '\');">' + safeUrl + '</a></div>';
        });
        urlHtml += '</div>';
    }
    var html = '<div style="display:flex;align-items:center;margin-bottom:16px;"><div style="font-size:24px;margin-right:10px;">🔑</div><div><div style="font-size:16px;font-weight:600;color:var(--text-primary,#e8eaed);">输入配置</div><div style="font-size:12px;color:var(--text-muted,#9aa0a6);margin-top:2px;">' + serverId + '</div></div></div>' + urlHtml;
    envVars.forEach(function(v, i) {
        var defaultValue = v.default || '';
        html += '<div style="margin-bottom:12px;"><div style="font-size:13px;font-weight:500;color:var(--text-primary,#e8eaed);font-family:monospace;margin-bottom:4px;">' + v.name + '</div>';
        if (v.description) html += '<div style="font-size:11px;color:var(--text-muted,#9aa0a6);margin-bottom:6px;">' + v.description + '</div>';
        html += '<input type="password" id="envInput_' + i + '" value="' + defaultValue + '" placeholder="填写 ' + v.name + '" style="width:100%;padding:10px 12px;border:1px solid var(--border-color,#2d3240);border-radius:6px;background:var(--bg-secondary,#22252b);color:var(--text-primary,#e8eaed);font-size:14px;outline:none;box-sizing:border-box;" />';
        if (v.url) {
            html += '<div style="margin-top:6px;"><span onclick="window.mcp_bridge && window.mcp_bridge.openExternalUrl(\'' + v.url + '\')" style="font-size:11px;color:var(--accent-color,#8ab4f8);cursor:pointer;">🔗 获取 ' + v.name + '</span></div>';
        } else {
            html += '<div style="margin-top:6px;font-size:11px;color:var(--text-muted,#9aa0a6);">💡 请查看该 MCP 服务器的官方文档（README / 官网）获取此密钥</div>';
        }
        html += '</div>';
    });
    html += '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px;border-top:1px solid var(--border-color,#2d3240);padding-top:12px;">';
    html += '<button id="apiKeyCancelBtn" style="padding:8px 20px;border:1px solid var(--border-color,#2d3240);border-radius:6px;background:var(--bg-secondary,#22252b);color:var(--text-primary,#e8eaed);cursor:pointer;font-size:13px;">取消</button>';
    html += '<button id="apiKeyConfirmBtn" style="padding:8px 20px;border:none;border-radius:6px;background:var(--accent-color,#8ab4f8);color:#fff;cursor:pointer;font-size:14px;font-weight:600;">保存并继续</button></div>';
    dialog.innerHTML = html;
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);
    document.getElementById('apiKeyCancelBtn').onclick = function() { closeAPIKeyDialog(serverId); };
    document.getElementById('apiKeyConfirmBtn').onclick = function() {
        // 校验必填字段
        var missing = [];
        envVars.forEach(function(v, i) {
            var input = document.getElementById('envInput_' + i);
            if (v.required && (!input || !input.value.trim())) {
                missing.push(v.name);
            }
        });
        if (missing.length > 0) {
            showToast('❌ 请填写必填项: ' + missing.join(', '), 'error');
            return;  // 不关闭对话框，等待用户填写
        }
        var envValues = {};
        envVars.forEach(function(v, i) {
            var input = document.getElementById('envInput_' + i);
            if (input && input.value.trim()) envValues[v.name] = input.value.trim();
        });
        if (window.mcp_bridge && window._bridgeReady) window.mcp_bridge.confirmEnvVars(serverId, JSON.stringify(envValues));
        overlay.remove();
        showToast('✅ 已保存', 'success');
    };
    overlay.onclick = function(e) {
        if (e.target === overlay) closeAPIKeyDialog(serverId);
    };
}

// ============================================
// AI 安装助手
// ============================================
function startMCPInstallAnalysis(itemId, repoUrl, serverDir, serverName, absPath, configDraft) {
    // 不关闭右侧导航栏，保持用户当前的浏览状态
    if (window.chatApp) window.chatApp.newChat();
    if (window.py_bridge) { try { window.py_bridge.newConversation(); } catch(e) {} }
    var displayName = serverDir || serverName;
    var cwdPath = absPath || ('tools/mcp/server/' + serverDir);
    // 通知后端进入"等待 AI 审阅配置"阶段（AI 回复完成后自动捕获 config JSON）
    window._mcpAwaitingAiConfig = true;
    // 已登记市场 ID，供后端捕获配置后回写预览
    window._mcpInstallItemId = itemId;
    var draftText = '';
    if (configDraft && typeof configDraft === 'object' && Object.keys(configDraft).length > 0) {
        draftText = '\n\n程序已自动检测到配置草稿，请审阅并修正：\n' + JSON.stringify(configDraft, null, 2);
    }
    var msg = [
        '安装: ' + displayName, '',
        '下载路径: ' + repoUrl, '📁 目录: ' + cwdPath, '',
        '请按内置技能 **mcp-server-install** 的流程处理，逐步说明当前步骤即可，无需复述技能名或引导语。' + draftText,
        '分析完成后，在回复末尾只输出最终配置 JSON（对象格式）。',
    ].join('\n');
    if (window.chatApp) {
        var welcome = document.getElementById('welcomeScreen');
        if (welcome) welcome.remove();
        window.chatApp.addMessage('user', msg);
        // 安装审阅期间保持输入框可用：用户可中途补充问题（不锁定 isProcessing）
        window.chatApp._currentAssistantId = window.chatApp.addMessage('assistant', '');
        if (window.py_bridge && typeof window.py_bridge.sendToAI === 'function') window.py_bridge.sendToAI(msg);
    }
}

// ============================================
// 后端回调和数据加载
// ============================================
window._onMCPRefreshStarted = function() { console.log('[MCP] 刷新已开始（后台线程）'); };
window._onMCPMarketRefreshed = function(marketStr) {
    try {
        var data = typeof marketStr === 'string' ? JSON.parse(marketStr) : marketStr;
        var items = data.market || data || [];
        if (items.length > 0) {
            items.forEach(function(item) {
                var local = appState.mcpMarket.find(function(m) { return m.id === item.id; });
                // 本地该市场项已有 serverId（已安装）→ 强制保留已安装态，避免被旧值覆盖
                if (local && local.serverId && item.installed) {
                    item.installed = true;
                    item.serverId = local.serverId;
                } else if (local && item.installed === false) {
                    // 后端明确返回未安装（卸载后 serverId 已清空）→ 清理本地残留
                    local.serverId = '';
                }
                // 否则用后端 getMCPMarket 返回的 installed
            });
            appState.mcpMarket = items;
            if (typeof renderMCPMarket === 'function') renderMCPMarket();
            showToast('✅ 已刷新 ' + items.length + ' 条市场数据', 'success');
        } else { showToast('⚠️ 刷新失败，未获取到数据', 'error'); }
    } catch (e) { console.warn('[MCP] 刷新市场数据失败:', e); showToast('❌ 刷新失败', 'error'); }
    var buttons = document.querySelectorAll('#mcpMarketSearchBar button');
    buttons.forEach(function(b) {
        if (b.innerHTML.indexOf('fa-sync-alt') !== -1) {
            b.disabled = false; b.style.opacity = '1';
            var icon = b.querySelector('i');
            icon.style.animation = ''; icon.style.display = '';
        }
    });
};

function loadMCPServers() {
    console.log('[MCP] 🔄 loadMCPServers() 被调用, bridgeReady=' + window._bridgeReady + ', mcp_bridge=' + !!window.mcp_bridge);
    if (window.mcp_bridge && window._bridgeReady) {
        window.mcp_bridge.getMCPServers().then(function(serversStr) {
            try {
                var servers = typeof serversStr === 'string' ? JSON.parse(serversStr) : serversStr;
                appState.mcpServers = servers || [];
                console.log('[MCP] ✅ 解析后得到', appState.mcpServers.length, '个服务器');
                if (typeof renderMCPServers === 'function') renderMCPServers();
                if (typeof renderMCPLocalServers === 'function') renderMCPLocalServers();
                updateMCPBadge();
                if (typeof renderMCPMarket === 'function') renderMCPMarket();
                if (typeof scanLocalServerDirs === 'function') scanLocalServerDirs();
            } catch (e) { console.warn('[MCP] ❌ 解析服务器列表失败:', e); }
        });
    }
}

function loadMCPMarket() {
    if (window.mcp_bridge && window._bridgeReady) {
        window.mcp_bridge.getMCPMarket().then(function(marketStr) {
            try {
                var data = typeof marketStr === 'string' ? JSON.parse(marketStr) : marketStr;
                var items = data.market || data || [];
                items.forEach(function(item) {
                    var local = appState.mcpMarket.find(function(m) { return m.id === item.id; });
                    // 本地该市场项已有 serverId（已安装）→ 强制保留已安装态，避免被旧值覆盖
                    if (local && local.serverId && item.installed) {
                        item.installed = true;
                        item.serverId = local.serverId;
                    } else if (local && item.installed === false) {
                        // 后端明确返回未安装（卸载后 serverId 已清空）→ 清理本地残留
                        local.serverId = '';
                    }
                    // 否则用后端 getMCPMarket 返回的 installed
                });
                appState.mcpMarket = items;
                if (typeof renderMCPMarket === 'function') renderMCPMarket();
            } catch (e) { console.warn('[MCP] 解析市场数据失败:', e); }
        });
    }
}

// ============================================
// JSON 配置编辑
// ============================================
function formatJSON() {
    var editor = document.getElementById('mcpJsonConfig');
    if (!editor) return;
    try { var obj = JSON.parse(editor.value); editor.value = JSON.stringify(obj, null, 2); showToast('JSON 已格式化', 'success'); }
    catch (e) { showToast('JSON 格式错误: ' + e.message, 'error'); }
}
function validateJSON() {
    var editor = document.getElementById('mcpJsonConfig');
    if (!editor) return;
    try { JSON.parse(editor.value); showToast('✅ JSON 格式验证通过', 'success'); }
    catch (e) { showToast('❌ JSON 格式错误: ' + e.message, 'error'); }
}
function applyJSONConfig() {
    var editor = document.getElementById('mcpJsonConfig');
    if (!editor) return;
    try {
        var config = JSON.parse(editor.value);
        if (config.mcpServers) {
            if (window.mcp_bridge && window._bridgeReady) {
                window.mcp_bridge.saveMCPConfig(editor.value).then(function(success) {
                    if (success) { showToast('✅ 配置已保存并应用', 'success'); loadMCPServers(); }
                    else { showToast('❌ 保存配置失败', 'error'); }
                });
            } else {
                Object.keys(config.mcpServers).forEach(function(k) {
                    var s = config.mcpServers[k];
                    if (!appState.mcpServers.find(function(m) { return m.id === k; })) {
                        appState.mcpServers.push({ id: k, name: k, url: s.url || '', description: s.description || '', enabled: s.enabled !== false, online: false, tools: s.tools || [] });
                    }
                });
                if (typeof renderMCPServers === 'function') renderMCPServers();
                updateMCPBadge();
                showToast('✅ 配置已应用（本地）', 'success');
            }
        }
    } catch (e) { showToast('❌ JSON 解析错误: ' + e.message, 'error'); }
}
function loadMCPConfigToEditor() {
    var editor = document.getElementById('mcpJsonConfig');
    if (!editor) return;
    if (window.mcp_bridge && window._bridgeReady) {
        window.mcp_bridge.getMCPConfig().then(function(configStr) {
            try {
                var config = typeof configStr === 'string' ? JSON.parse(configStr) : configStr;
                editor.value = JSON.stringify(config, null, 2);
                console.log('[MCP] ✅ 配置已加载到编辑器');
            } catch (e) { console.warn('[MCP] 解析配置失败:', e); }
        });
    }
}

function loadMCPMarketRefresh() {
    if (window.mcp_bridge && window._bridgeReady) {
        var buttons = document.querySelectorAll('#mcpMarketSearchBar button');
        var refreshBtn = null;
        buttons.forEach(function(b) {
            if (b.innerHTML.indexOf('fa-sync-alt') !== -1) refreshBtn = b;
        });
        if (refreshBtn) {
            refreshBtn.disabled = true; refreshBtn.style.opacity = '0.7';
            var icon = refreshBtn.querySelector('i');
            icon.style.animation = 'spin 1s linear infinite'; icon.style.display = 'inline-block';
        }
        showToast('🔄 正在从 GitHub 刷新市场数据...', 'info');
        window.mcp_bridge.refreshMCPMarket();
    }
}

// ============================================
// MCP 安装配置预览 + 确认安装（替代 mcp_finalize_install 工具）
// ============================================
function showMCPConfigPreview(itemId, configObj) {
    // 在市场中显示配置预览（悬浮层）
    var overlay = document.getElementById('mcpConfigPreviewOverlay');
    if (overlay) overlay.remove();
    overlay = document.createElement('div');
    overlay.id = 'mcpConfigPreviewOverlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.6);z-index:9998;display:flex;align-items:center;justify-content:center;';
    var configText = typeof configObj === 'string' ? configObj : JSON.stringify(configObj || {}, null, 2);
    var html = '<div style="background:var(--bg-primary,#1a1d23);border:1px solid var(--border-color,#2d3240);border-radius:12px;padding:24px;max-width:600px;width:92%;max-height:80vh;overflow-y:auto;box-sizing:border-box;">';
    html += '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">';
    html += '<div style="font-size:16px;font-weight:600;color:var(--text-primary,#e8eaed);">📝 配置预览（' + (itemId || '') + '）</div>';
    html += '<button onclick="document.getElementById(\'mcpConfigPreviewOverlay\').remove()" style="background:none;border:none;color:var(--text-muted,#9aa0a6);cursor:pointer;font-size:18px;">✕</button></div>';
    html += '<div style="font-size:12px;color:var(--text-muted,#9aa0a6);margin-bottom:8px;">AI 审阅后的配置，请确认后点击「确认安装」完成启动：</div>';
    html += '<div style="background:var(--bg-secondary,#22252b);border:1px solid var(--border-color,#2d3240);border-radius:8px;padding:12px;font-family:monospace;font-size:12px;color:var(--text-primary,#e8eaed);white-space:pre-wrap;word-break:break-all;max-height:400px;overflow-y:auto;">' + configText.replace(/&/g,'&').replace(/</g,'<').replace(/>/g,'>') + '</div>';
    html += '<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:14px;">';
    html += '<button onclick="document.getElementById(\'mcpConfigPreviewOverlay\').remove()" style="padding:8px 18px;border:1px solid var(--border-color,#2d3240);border-radius:6px;background:var(--bg-secondary,#22252b);color:var(--text-primary,#e8eaed);cursor:pointer;font-size:13px;">取消</button>';
    html += '<button onclick="confirmMCPInstallFromPreview()" style="padding:8px 20px;border:none;border-radius:6px;background:var(--accent-color,#8ab4f8);color:#fff;cursor:pointer;font-size:14px;font-weight:600;">✅ 确认安装</button></div>';
    html += '</div>';
    overlay.innerHTML = html;
    document.body.appendChild(overlay);
    // 保存当前预览配置供确认按钮使用
    window._mcpPreviewConfigRaw = configText;
    window._mcpPreviewItemId = itemId;
}

function confirmMCPInstallFromPreview() {
    var overlay = document.getElementById('mcpConfigPreviewOverlay');
    var configText = window._mcpPreviewConfigRaw || '';
    var itemId = window._mcpPreviewItemId || '';
    try {
        // 校验 JSON 合法
        JSON.parse(configText);
    } catch(e) {
        showToast('❌ 配置 JSON 格式无效，无法安装', 'error');
        return;
    }
    if (overlay) overlay.remove();
    if (window.mcp_bridge && window._bridgeReady) {
        window.mcp_bridge.confirmMCPInstall(itemId, configText);
        showToast('✅ 已确认，正在启动 MCP 服务器...', 'success');
    } else {
        showToast('❌ MCP 桥接不可用', 'error');
    }
}
