// ============================================
// Settings - 设置面板（主题、模型参数等）
// ============================================

// 主题切换
function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('agent-theme', theme);
    document.querySelectorAll('.theme-toggle-btn').forEach(function(b) {
        b.classList.remove('active');
    });
    if (theme === 'dark') {
        document.querySelector('.theme-toggle-btn:first-child')?.classList.add('active');
    } else {
        document.querySelector('.theme-toggle-btn:last-child')?.classList.add('active');
    }
    showToast('🎨 已切换至 ' + (theme === 'dark' ? '暗色' : '亮色') + ' 主题', 'success');
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

// 设置面板渲染接口
function renderSettings() {
    var s = document.getElementById('tabSettings');
    if (!s) return;
    s.innerHTML = '<div class="settings-group"><div class="settings-group-title"><i class="fas fa-palette"></i> 主题</div><div class="settings-card"><div class="settings-row"><span class="label">主题模式</span><div class="theme-toggle-group"><button class="theme-toggle-btn active" onclick="setTheme(\'dark\')"><i class="fas fa-moon"></i> 暗色</button><button class="theme-toggle-btn" onclick="setTheme(\'light\')"><i class="fas fa-sun"></i> 亮色</button></div></div></div></div></div>';
}
