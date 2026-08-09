// Settings - 设置面板（主题、模型参数等）

// 主题切换（持久化到 agent_config.json：defaults 提供默认，用户修改写 user 目录）
function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('agent-theme', theme);
    updateThemeButtons(theme);
    if (window.agent_config_bridge && window.agent_config_bridge.getConfig && window.agent_config_bridge.saveConfig) {
        try {
            // 合并保存：保留 github_mirror 等其他字段
            var cfgObj = JSON.parse(window.agent_config_bridge.getConfig());
            cfgObj.theme = theme;
            window.agent_config_bridge.saveConfig(JSON.stringify(cfgObj));
        } catch(e){}
    }
    showToast('🎨 已切换至 ' + (theme === 'dark' ? '暗色' : '亮色') + ' 主题', 'success');
}

// 同步主题按钮高亮状态
function updateThemeButtons(theme) {
    var cur = theme || document.documentElement.getAttribute('data-theme') || 'dark';
    var btns = document.querySelectorAll('.theme-toggle-btn');
    if (btns.length === 2) {
        btns[0].classList.toggle('active', cur === 'dark');
        btns[1].classList.toggle('active', cur !== 'dark');
    }
}

// 模型选择器切换
function changeModelFromSettings(modelId) {
    var m = appState.models.find(function(x) { return x.id === modelId; });
    if (!m) return;
    appState.models.forEach(function(x) { x.active = false; x.isDefault = false; });
    m.active = true;
    m.isDefault = true;
    appState.currentModel = m;
    if (typeof renderModelList === 'function') renderModelList();
    if (typeof updateModelUI === 'function') updateModelUI();
    if (typeof updateModelCount === 'function') updateModelCount();
    if (typeof showToast === 'function') showToast('✅ 切换到模型: ' + m.name, 'success');
}

// 设置面板渲染接口（按钮高亮根据当前主题动态刷新）
function renderSettings() {
    var s = document.getElementById('tabSettings');
    if (!s) return;
    var curTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    var darkActive = (curTheme === 'dark') ? 'active' : '';
    var lightActive = (curTheme !== 'dark') ? 'active' : '';
    // 读取已保存的 GitHub 镜像配置
    var savedMirror = localStorage.getItem('github_mirror') || '';
    if (!savedMirror && window.agent_config_bridge && window.agent_config_bridge.getConfig) {
        try {
            var cfgObj = JSON.parse(window.agent_config_bridge.getConfig());
            if (cfgObj && cfgObj.github_mirror) savedMirror = cfgObj.github_mirror;
        } catch(e) {}
    }
    s.innerHTML = '<div class="settings-group"><div class="settings-group-title"><i class="fas fa-palette"></i> 主题</div><div class="settings-card"><div class="settings-row"><span class="label">主题模式</span><div class="theme-toggle-group"><button class="theme-toggle-btn ' + darkActive + '" onclick="setTheme(\'dark\')"><i class="fas fa-moon"></i> 暗色</button><button class="theme-toggle-btn ' + lightActive + '" onclick="setTheme(\'light\')"><i class="fas fa-sun"></i> 亮色</button></div></div></div></div>'
        + '<div class="settings-group"><div class="settings-group-title"><i class="fas fa-rocket"></i> GitHub 加速</div><div class="settings-card"><div class="settings-row">'
        + '<span class="label">镜像前缀</span>'
        + '<input type="text" id="githubMirrorInput" value="' + (savedMirror || '') + '" placeholder="如 https://ghfast.top/ 或留空使用默认直连+内置镜像" style="flex:1;padding:6px 10px;border:1px solid var(--border-color);border-radius:var(--radius-md);background:var(--bg-secondary);color:var(--text-primary);font-size:12px;outline:none;">'
        + '<button class="theme-toggle-btn" onclick="saveGitHubMirror()" style="margin-left:8px;padding:6px 14px;border:1px solid var(--border-color);border-radius:var(--radius-md);background:var(--bg-tertiary);color:var(--text-primary);cursor:pointer;font-size:12px;"><i class="fas fa-save"></i> 保存</button>'
        + '</div><div style="font-size:11px;color:var(--text-muted);margin-top:6px;line-height:1.5;">用于 MCP 市场安装时加速 GitHub 克隆。留空则自动尝试：直连 → ghfast.top → gh-proxy.com → moeyy → ghproxy.net。可配置如 <code style="background:var(--bg-tertiary);padding:1px 4px;border-radius:3px;">https://ghfast.top/</code> 或内网代理地址。</div></div></div>';
}

// 保存 GitHub 镜像配置到 agent_config（user 目录）
function saveGitHubMirror() {
    var inp = document.getElementById('githubMirrorInput');
    if (!inp) return;
    var mirror = inp.value.trim();
    // 规范化：补全协议前缀
    if (mirror && !/^https?:\/\//i.test(mirror)) {
        mirror = 'https://' + mirror;
    }
    localStorage.setItem('github_mirror', mirror);
    try {
        if (window.agent_config_bridge && window.agent_config_bridge.getConfig && window.agent_config_bridge.saveConfig) {
            var cfgObj = JSON.parse(window.agent_config_bridge.getConfig());
            cfgObj.github_mirror = mirror;
            window.agent_config_bridge.saveConfig(JSON.stringify(cfgObj));
        }
    } catch(e) {
        console.error('[Settings] 保存 GitHub 镜像失败', e);
    }
    if (typeof showToast === 'function') {
        showToast(mirror ? '✅ GitHub 镜像已保存: ' + mirror : 'ℹ️ 已清除自定义镜像（使用默认直连+内置镜像）', 'success');
    }
}
