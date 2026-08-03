// 安全插件配置界面逻辑 - 通过插件自带 security_bridge 与 Python 通信
(function() {
    function $(id) { return document.getElementById(id); }
    function bridge() { return window.security_bridge; }
    function loadConfig() {
        if (!bridge()) { $('statusMsg').textContent = '桥接不可用'; return; }
        var p = bridge().getConfig();
        function fill(str) {
            try {
                var cfg = typeof str === 'string' ? JSON.parse(str) : str;
                cfg = cfg || {};
                $('filterMode').value = (cfg.content_filter || {}).mode || 'mask';
                $('dangerPatterns').value = ((cfg.content_filter || {}).danger_patterns || []).join('\n');
                $('permMode').value = (cfg.permission || {}).mode || 'blacklist';
                $('blockedTools').value = ((cfg.permission || {}).blocked_tools || []).join('\n');
                $('allowedTools').value = ((cfg.permission || {}).allowed_tools || []).join('\n');
            } catch(e) { console.warn('[SecurityView] parse fail', e); }
        }
        if (p && typeof p.then === 'function') p.then(fill); else fill(p);
    }
    function saveConfig() {
        if (!bridge()) { $('statusMsg').textContent = '桥接不可用'; return; }
        // enabled 顶层字段与 security_config.json 结构保持一致
        var cfg = {
            enabled: true,
            content_filter: {
                mode: $('filterMode').value,
                danger_patterns: $('dangerPatterns').value.split('\n').map(function(s){return s.trim();}).filter(Boolean),
                mask_char: '*'
            },
            permission: {
                mode: $('permMode').value,
                blocked_tools: $('blockedTools').value.split('\n').map(function(s){return s.trim();}).filter(Boolean),
                allowed_tools: $('allowedTools').value.split('\n').map(function(s){return s.trim();}).filter(Boolean)
            }
        };
        var p = bridge().saveConfig(JSON.stringify(cfg));
        function done(r) {
            try {
                r = typeof r === 'string' ? JSON.parse(r) : r;
                $('statusMsg').textContent = (r && r.ok) ? '已保存' : '保存失败';
            }
            catch(e) { $('statusMsg').textContent = '保存失败'; }
        }
        if (p && typeof p.then === 'function') p.then(done); else done(p);
    }
    $('saveBtn').addEventListener('click', saveConfig);
    loadConfig();
})();