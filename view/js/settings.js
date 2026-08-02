// Settings - 设置面板（主题、模型参数等）

// 主题切换（持久化到 agent_config.json：defaults 提供默认，用户修改写 user 目录）
function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('agent-theme', theme);
    updateThemeButtons(theme);
    if (window.agent_config_bridge && window.agent_config_bridge.saveConfig) {
        try { window.agent_config_bridge.saveConfig(JSON.stringify({theme:theme})); } catch(e){}
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
    s.innerHTML = '<div class="settings-group"><div class="settings-group-title"><i class="fas fa-palette"></i> 主题</div><div class="settings-card"><div class="settings-row"><span class="label">主题模式</span><div class="theme-toggle-group"><button class="theme-toggle-btn ' + darkActive + '" onclick="setTheme(\'dark\')"><i class="fas fa-moon"></i> 暗色</button><button class="theme-toggle-btn ' + lightActive + '" onclick="setTheme(\'light\')"><i class="fas fa-sun"></i> 亮色</button></div></div></div></div></div>';
}