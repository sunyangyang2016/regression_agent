// ============================================
// Plugins - 插件管理面板
// ============================================

function renderPlugins() {
    var c = document.getElementById('pluginList');
    if (!c) return;
    var plugins = [
        {name:'安全插件', desc:'内容过滤和权限管理', version:'v2.1', icon:'fa-shield-alt', enabled:true},
        {name:'监控插件', desc:'性能监控和统计', version:'v1.0', icon:'fa-chart-pie', enabled:true},
        {name:'Git 集成', desc:'版本控制和代码管理', version:'v1.2', icon:'fa-git', enabled:false}
    ];
    c.innerHTML = plugins.map(function(p) {
        return '<div class="item-row">' +
            '<div class="icon" style="background:rgba(247,120,186,0.15);color:var(--accent-pink);">' +
                '<i class="fas ' + p.icon + '"></i>' +
            '</div>' +
            '<div class="info">' +
                '<div class="name">' + p.name + '</div>' +
                '<div class="desc">' + p.desc + '</div>' +
                '<div class="tags"><span class="tag active">' + p.version + '</span></div>' +
            '</div>' +
            '<label class="switch">' +
                '<input type="checkbox"' + (p.enabled ? ' checked' : '') + '>' +
                '<span class="slider"></span>' +
            '</label>' +
        '</div>';
    }).join('');
}