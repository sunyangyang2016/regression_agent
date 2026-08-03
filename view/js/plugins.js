// ============================================
// Plugins - 插件管理面板（三卡片 + 开关 + 显示按钮）
// 配置窗口只做「壳」：注入插件自身 index.html 片段 + 执行插件自身 js
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
                '<button class="plugin-show-btn" onclick="showPlugin(\'' + String(p.name).replace(/'/g, "\\'") + '\')" title="打开配置面板">' +
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
// 配置窗口壳 - 每个插件独立窗口，互不覆盖
// 窗口内注入插件自身 config_ui.html/css/js（由后端 get_config_ui 提供）
// ============================================
function showPlugin(name) {
    // 若窗口已存在则直接显示
    var win = document.getElementById('pluginFloat_' + name);
    if (win) {
        win.style.display = 'block';
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

    // 创建独立窗口
    win = document.createElement('div');
    win.id = 'pluginFloat_' + name;
    win.className = 'plugin-float-window';
    win.style.display = 'block';

    var head = '<div class="plugin-float-header">' +
        '<h3><i class="fas ' + icon + '" style="color:' + fg + ';"></i> ' + title + '</h3>' +
        '<div class="plugin-float-controls">' +
            '<button class="plugin-float-min" onclick="minimizePlugin(\'' + name + '\')" title="隐藏">─</button>' +
            '<button class="plugin-float-max" onclick="maximizePlugin(\'' + name + '\')" title="最大化 / 还原">□</button>' +
            '<button class="plugin-float-close" onclick="closePlugin(\'' + name + '\')" title="关闭">✕</button>' +
        '</div>' +
    '</div>';

    var styleTag = css ? '<style>' + css + '</style>' : '';
    var bodyDiv = '<div class="plugin-float-body">' + html + '</div>';

    win.innerHTML = head + styleTag + bodyDiv;
    document.body.appendChild(win);

    // 窗口拖拽 + 边缘调整大小（结合实现）
    // - 按住标题栏/内容空白区域拖动 → 移动窗口
    // - 鼠标移到窗口四角/四边 → 出现 resize 光标，按住拖动 → 动态调整大小
    // - 交互元素（按钮/输入框/文本域/下拉框/链接/标签等）不触发任何拖拽
    var drag = null;
    var RESIZE_EDGE = 8;   // 边缘检测阈值（px）
    var MIN_W = 220;       // 最小宽度
    var MIN_H = 160;       // 最小高度

    // 根据鼠标位置返回调整方向：'' 表示不在边缘
    function hitTestResize(e) {
        var r = win.getBoundingClientRect();
        var x = e.clientX - r.left;
        var y = e.clientY - r.top;
        var nearN = y <= RESIZE_EDGE, nearS = y >= r.height - RESIZE_EDGE;
        var nearW = x <= RESIZE_EDGE, nearE = x >= r.width - RESIZE_EDGE;
        if (nearN && nearW) return 'nw';
        if (nearN && nearE) return 'ne';
        if (nearS && nearW) return 'sw';
        if (nearS && nearE) return 'se';
        if (nearN) return 'n';
        if (nearS) return 's';
        if (nearW) return 'w';
        if (nearE) return 'e';
        return '';
    }

    // 鼠标在窗口内移动时更新光标，提示可调整大小
    win.addEventListener('mousemove', function(e) {
        var dir = hitTestResize(e);
        var map = {
            n: 'ns-resize', s: 'ns-resize',
            w: 'ew-resize', e: 'ew-resize',
            nw: 'nwse-resize', se: 'nwse-resize',
            ne: 'nesw-resize', sw: 'nesw-resize'
        };
        win.style.cursor = dir ? (map[dir] || '') : '';
    });

    // 边缘拖拽动态调整大小
    function startResize(e, dir) {
        var startX = e.clientX, startY = e.clientY;
        var r = win.getBoundingClientRect();
        var startLeft = r.left, startTop = r.top;
        var startW = r.width, startH = r.height;
        // 若处于最大化状态，先退出
        if (win.dataset.max === '1') {
            win.dataset.max = '0';
            var mb = win.querySelector('.plugin-float-max');
            if (mb) mb.innerHTML = '□';
        }
        win.style.maxWidth = 'none';
        function doResize(ev) {
            var dx = ev.clientX - startX, dy = ev.clientY - startY;
            var w = startW, h = startH, left = startLeft, top = startTop;
            if (dir.indexOf('e') !== -1) w = startW + dx;
            if (dir.indexOf('s') !== -1) h = startH + dy;
            if (dir.indexOf('w') !== -1) { w = startW - dx; left = startLeft + dx; }
            if (dir.indexOf('n') !== -1) { h = startH - dy; top = startTop + dy; }
            if (w < MIN_W) { if (dir.indexOf('w') !== -1) left = startLeft + (startW - MIN_W); w = MIN_W; }
            if (h < MIN_H) { if (dir.indexOf('n') !== -1) top = startTop + (startH - MIN_H); h = MIN_H; }
            win.style.width = w + 'px';
            win.style.height = h + 'px';
            win.style.left = left + 'px';
            win.style.top = top + 'px';
        }
        function upResize() {
            document.removeEventListener('mousemove', doResize);
            document.removeEventListener('mouseup', upResize);
        }
        document.addEventListener('mousemove', doResize);
        document.addEventListener('mouseup', upResize);
        e.preventDefault();
    }

    // 窗口按下：边缘 → 调整大小；否则 → 移动
    function startDrag(e) {
        var t = e.target;
        var interactive = t && t.closest && t.closest('button, input, textarea, select, a, label, .plugin-float-controls');
        if (interactive) return;
        var dir = hitTestResize(e);
        if (dir) { startResize(e, dir); return; }
        drag = { x: e.clientX - win.offsetLeft, y: e.clientY - win.offsetTop };
        function move(ev) {
            win.style.left = (ev.clientX - drag.x) + 'px';
            win.style.top = (ev.clientY - drag.y) + 'px';
        }
        function up() {
            document.removeEventListener('mousemove', move);
            document.removeEventListener('mouseup', up);
        }
        document.addEventListener('mousemove', move);
        document.addEventListener('mouseup', up);
        e.preventDefault();
    }
    win.addEventListener('mousedown', startDrag);

    // 定位（右上角层叠）
    win.style.position = 'fixed';
    win.style.width = '560px';
    win.style.maxWidth = 'calc(100vw - 48px)';
    win.style.top = Math.max(24, (window.innerHeight - 300) / 3 + 20) + 'px';
    win.style.left = Math.max(24, window.innerWidth - 620) + 'px';

    // 执行插件自身 js（依赖 window.security_bridge，由 app.js 全局注入）
    if (js) {
        try {
            // eslint-disable-next-line no-new-func
            (new Function('window', 'document', js))(window, document);
        } catch(e) {
            console.warn('[Plugins] 执行插件 js 失败:', name, e);
        }
    }
}

function closePlugin(name) {
    var win = document.getElementById('pluginFloat_' + name);
    if (win) win.style.display = 'none';
}

// 隐藏（最小化）：同关闭，但保留数据以便再次「显示」直接恢复
function minimizePlugin(name) {
    var win = document.getElementById('pluginFloat_' + name);
    if (win) win.style.display = 'none';
}

// 最大化 / 还原：切换窗口尺寸，记录原尺寸与位置
function maximizePlugin(name) {
    var win = document.getElementById('pluginFloat_' + name);
    if (!win) return;
    if (win.dataset.max === '1') {
        // 还原
        win.dataset.max = '0';
        var orig = {};
        try { orig = JSON.parse(win.dataset.orig || '{}'); } catch(e) { orig = {}; }
        win.style.width = orig.width || '560px';
        win.style.height = orig.height || '';
        win.style.maxWidth = 'calc(100vw - 48px)';
        win.style.top = orig.top || '24px';
        win.style.left = orig.left || 'auto';
        var btn = win.querySelector('.plugin-float-max');
        if (btn) btn.innerHTML = '□';
    } else {
        // 记录当前尺寸/位置
        win.dataset.max = '1';
        win.dataset.orig = JSON.stringify({
            width: win.style.width || '560px',
            height: win.style.height || '',
            top: win.style.top || '',
            left: win.style.left || ''
        });
        // 最大化：铺满视口（留 24px 边距）
        win.style.width = 'calc(100vw - 48px)';
        win.style.height = 'calc(100vh - 48px)';
        win.style.maxWidth = 'none';
        win.style.top = '24px';
        win.style.left = '24px';
        var btn = win.querySelector('.plugin-float-max');
        if (btn) btn.innerHTML = '❐';
    }
}
