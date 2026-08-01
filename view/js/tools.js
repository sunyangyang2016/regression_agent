// ============================================
// Tools - 工具面板（动态渲染 + 可展开详情）
// ============================================

function renderTools(){
    var c = document.getElementById('toolList');
    if(!c){ console.error('[Tools] toolList not found'); return; }

    // 优先使用缓存数据
    var tools = window._cachedTools;
    if (!tools && window.tool_bridge) {
        try {
            var toolsStr = window.tool_bridge.getTools();
            if (typeof toolsStr === 'string') {
                tools = JSON.parse(toolsStr);
                window._cachedTools = tools;
            }
        } catch(e) {
            console.warn('[Tools] 同步获取失败:', e);
        }
    }

    if (tools && tools.length > 0) {
        var html = '';
        tools.forEach(function(t, i) {
            var icon = t.icon || 'fa-cog';
            var name = t.name_cn || t.name || '?';
            var desc = t.description_cn || t.description || '';
            var engDesc = t.description || '';
            var paramsInfo = t.parameters_info || '';
            var checked = t.enabled ? 'checked' : '';
            html += '<div class="tool-group">' +
                '<div class="item-row" onclick="toggleToolDetail(' + i + ')" style="cursor:pointer;">' +
                    '<div class="icon builtin"><i class="fas ' + icon + '"></i></div>' +
                    '<div class="info"><div class="name">' + name + '</div><div class="desc">' + desc + '</div></div>' +
                    '<label class="switch" onclick="event.stopPropagation()"><input type="checkbox" ' + checked + ' data-tool-name="' + t.name + '"><span class="slider"></span></label>' +
                    '<span class="tool-expand-icon"><i class="fas fa-chevron-down" id="toolIcon' + i + '"></i></span>' +
                '</div>' +
                '<div class="tool-detail" id="toolDetail' + i + '">' +
                    '<div class="row"><span class="label">接口名</span><span class="value">' + t.name + '</span></div>' +
                    '<div class="row"><span class="label">英文描述</span><span class="value">' + engDesc + '</span></div>' +
                    (paramsInfo ? '<div class="row"><span class="label">参数</span><span class="value mono">' + paramsInfo + '</span></div>' : '') +
                '</div>' +
            '</div>';
        });
        c.innerHTML = html;

        // 绑定切换事件
        c.querySelectorAll('input[type="checkbox"][data-tool-name]').forEach(function(cb) {
            cb.addEventListener('change', function() {
                var toolName = this.getAttribute('data-tool-name');
                var enabled = this.checked;
                if (window.tool_bridge && window.tool_bridge.toggleTool) {
                    try {
                        window.tool_bridge.toggleTool(toolName, enabled);
                        console.log('[Tools] 切换 "' + toolName + '": ' + (enabled ? '启用' : '禁用'));
                    } catch(e) {
                        console.warn('[Tools] 切换失败:', e);
                        this.checked = !enabled;
                    }
                }
            });
        });

        console.log('[Tools] 渲染 ' + tools.length + ' 个工具');
    } else {
        c.innerHTML = '<div style="padding:16px;color:var(--text-muted);">暂无可用工具</div>';
    }
}

function toggleToolDetail(index) {
    var detail = document.getElementById('toolDetail' + index);
    var icon = document.getElementById('toolIcon' + index);
    if (detail) {
        var isOpen = detail.style.display === 'block';
        detail.style.display = isOpen ? 'none' : 'block';
        if (icon) {
            icon.style.transform = isOpen ? 'rotate(0deg)' : 'rotate(180deg)';
        }
    }
}
