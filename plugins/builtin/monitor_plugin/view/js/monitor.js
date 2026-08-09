// ============================================
// 系统监控插件 - 前端逻辑
// B1 纯推送方案：数据由 MCP 监控工具经 pushMonitorData 推送渲染
// 保留 fetchAlerts 告警轮询（仅显示在异常提醒框，不渲染横幅）；已删除 fetchAll 主数据轮询
// ============================================
(function() {
    'use strict';

    function $(id) { return document.getElementById(id); }
    function bridge() { return window.monitor_bridge || window.monitor_plugin_bridge; }

    // ---------- 格式化工具 ----------
    function formatBytes(num) {
        num = Number(num) || 0;
        var units = ['B', 'K', 'M', 'G', 'T'];
        var i = 0;
        while (num >= 1024 && i < units.length - 1) { num /= 1024; i++; }
        return (i === 0 ? num.toFixed(0) : num.toFixed(1)) + units[i];
    }

    // ---------- 渲染函数 ----------
    function renderStats(stats) {
        if (!stats) return;
        var cpu = stats.cpu || {};
        var mem = stats.memory || {};
        var dio = stats.disk_io || {};
        var net = stats.network || {};
        var load = stats.load || [];

        // CPU
        var cpuPct = Number(cpu.percent) || 0;
        var cpuEl = $('monCpuValue');
        if (cpuEl) cpuEl.innerHTML = cpuPct.toFixed(1) + '<small>%</small>';
        var cpuBar = $('monCpuBar');
        if (cpuBar) cpuBar.style.width = Math.min(100, cpuPct) + '%';
        var cpuFreq = $('monCpuFreq');
        if (cpuFreq) cpuFreq.innerHTML = '<i class="fas fa-arrow-up"></i> ' + (cpu.freq || '0 GHz');
        var cpuCores = $('monCpuCores');
        if (cpuCores) cpuCores.innerHTML = '<i class="fas fa-microchip"></i> ' + (cpu.cores || 0) + ' 核';

        // 内存
        var memPct = Number(mem.percent) || 0;
        var memUsed = formatBytes(mem.used);
        var memTotal = formatBytes(mem.total);
        var memEl = $('monMemValue');
        if (memEl) memEl.innerHTML = (Number(mem.used) >= 1024 * 1024 * 1024
            ? (Number(mem.used) / 1024 / 1024 / 1024).toFixed(1)
            : (Number(mem.used) / 1024 / 1024).toFixed(1)) + ' <small>GB</small>';
        var memBar = $('monMemBar');
        if (memBar) memBar.style.width = Math.min(100, memPct) + '%';
        var memTotalEl = $('monMemTotal');
        if (memTotalEl) memTotalEl.innerHTML = '<i class="fas fa-database"></i> 总 ' + memTotal;
        var memUsedEl = $('monMemUsed');
        if (memUsedEl) memUsedEl.textContent = '已用 ' + memUsed;

        // 磁盘 I/O
        var diskTotal = Number(dio.total_mb !== undefined ? dio.total_mb : dio.total) || 0;
        var diskEl = $('monDiskValue');
        if (diskEl) diskEl.innerHTML = diskTotal.toFixed(0) + ' <small>MB/s</small>';
        var diskBar = $('monDiskBar');
        if (diskBar) diskBar.style.width = Math.min(100, diskTotal / 2) + '%';
        var diskRead = $('monDiskRead');
        if (diskRead) diskRead.innerHTML = '<i class="fas fa-arrow-down"></i> 读 ' + (dio.readable || '0 MB/s');
        var diskWrite = $('monDiskWrite');
        if (diskWrite) diskWrite.innerHTML = '<i class="fas fa-arrow-up"></i> 写 ' + (dio.writable || '0 MB/s');

        // 网络
        var rxMbps = Number(net.rx_mbps) || 0;
        var txMbps = Number(net.tx_mbps) || 0;
        var netEl = $('monNetValue');
        if (netEl) netEl.innerHTML = (Math.max(rxMbps, txMbps) / 1000).toFixed(1) + ' <small>Gbps</small>';
        var netBar = $('monNetBar');
        if (netBar) netBar.style.width = Math.min(100, Math.max(rxMbps, txMbps) / 10) + '%';
        var netRx = $('monNetRx');
        if (netRx) netRx.innerHTML = '<i class="fas fa-cloud-download-alt"></i> 下行 ' + (net.rx || '0 B/s');
        var netTx = $('monNetTx');
        if (netTx) netTx.innerHTML = '<i class="fas fa-cloud-upload-alt"></i> 上行 ' + (net.tx || '0 B/s');

        // 负载
        var loadEl = $('monLoadRow');
        if (loadEl) {
            loadEl.innerHTML =
                '<span><i class="fas fa-tachometer-alt"></i> 1min: ' + (load[0] !== undefined ? load[0] : 0) + '</span>' +
                '<span><i class="fas fa-tachometer-alt"></i> 5min: ' + (load[1] !== undefined ? load[1] : 0) + '</span>' +
                '<span><i class="fas fa-tachometer-alt"></i> 15min: ' + (load[2] !== undefined ? load[2] : 0) + '</span>';
        }

        // 运行时长
        var upEl = $('monUptime');
        if (upEl) upEl.innerHTML = '<i class="fas fa-clock"></i> 运行: ' + (stats.uptime || '0d 0h');
    }

    function getProcIcon(name) {
        name = (name || '').toLowerCase();
        if (name.indexOf('nginx') !== -1) return 'fas fa-code';
        if (name.indexOf('postgres') !== -1 || name.indexOf('mysql') !== -1 || name.indexOf('redis') !== -1) return 'fas fa-database';
        if (name.indexOf('docker') !== -1) return 'fab fa-docker';
        if (name.indexOf('bash') !== -1 || name.indexOf('sh') !== -1 || name.indexOf('powershell') !== -1 || name.indexOf('cmd') !== -1) return 'fas fa-terminal';
        if (name.indexOf('systemd') !== -1 || name.indexOf('init') !== -1) return 'fas fa-cog';
        if (name.indexOf('prometheus') !== -1 || name.indexOf('grafana') !== -1) return 'fas fa-cloud';
        if (name.indexOf('chrome') !== -1 || name.indexOf('firefox') !== -1 || name.indexOf('edge') !== -1) return 'fab fa-chrome';
        if (name.indexOf('java') !== -1 || name.indexOf('python') !== -1 || name.indexOf('node') !== -1) return 'fas fa-code';
        return 'fas fa-microchip';
    }

    function renderProcesses(procs, summary) {
        var list = $('monProcessList');
        if (!list) return;
        if (!procs || procs.length === 0) {
            list.innerHTML = '<div class="mon-loading">暂无进程数据</div>';
            return;
        }
        list.innerHTML = procs.map(function(p) {
            var name = String(p.name || 'unknown');
            var pid = p.pid || 0;
            var cpu = Number(p.cpu_percent !== undefined ? p.cpu_percent : p.cpu) || 0;
            var mem = Number(p.mem_percent !== undefined ? p.mem_percent : p.mem) || 0;
            var rss = Number(p.rss || 0);
            var vsz = Number(p.vsz || p.vsz_mb || 0);
            var threads = Number(p.threads || 0);
            return '<div class="mon-process-item">' +
                '<div class="mon-proc-row">' +
                    '<div class="mon-proc-left">' +
                        '<div class="mon-proc-icon"><i class="' + getProcIcon(name) + '"></i></div>' +
                        '<span class="mon-proc-name" title="' + name + '">' + name +
                            '<span class="mon-proc-pid">PID ' + pid + '</span>' +
                        '</span>' +
                    '</div>' +
                    '<div class="mon-proc-stats">' +
                        '<span class="stat-cpu"><i class="fas fa-microchip"></i> ' + cpu.toFixed(1) + '%</span>' +
                        '<span class="stat-mem"><i class="fas fa-memory"></i> ' + mem.toFixed(1) + '%</span>' +
                        '<span class="stat-rss"><i class="fas fa-database"></i> RSS ' + formatBytes(rss) + '</span>' +
                        '<span class="stat-vsz"><i class="fas fa-cubes"></i> VSZ ' + formatBytes(vsz) + '</span>' +
                        '<span class="stat-thread"><i class="fas fa-fork"></i> 线程 ' + threads + '</span>' +
                    '</div>' +
                '</div>' +
            '</div>';
        }).join('');
    }

    function renderSummary(summary) {
        if (!summary) return;
        var bar = $('monSummaryBar');
        if (!bar) return;
        bar.innerHTML =
            '<span><i class="fas fa-arrow-up"></i> CPU 总计: ' + (Number(summary.cpu_total) || 0).toFixed(1) + '%</span>' +
            '<span><i class="fas fa-memory"></i> 内存总计: ' + (Number(summary.mem_total) || 0).toFixed(1) + '%</span>' +
            '<span><i class="fas fa-database"></i> RSS 总计: ' + (summary.rss_total_str || formatBytes(summary.rss_total || 0)) + '</span>' +
            '<span><i class="fas fa-fork"></i> 线程总计: ' + (summary.threads_total || 0) + '</span>';
    }

    function renderDisks(disks) {
        var grid = $('monDiskGrid');
        if (!grid) return;
        if (!disks || disks.length === 0) {
            grid.innerHTML = '<div class="mon-disk-loading">暂无磁盘数据</div>';
            return;
        }
        grid.innerHTML = disks.map(function(d) {
            var pct = Number(d.percent) || 0;
            var cls = pct >= 90 ? 'fill-red' : (pct >= 70 ? 'fill-orange' : '');
            var used = formatBytes(d.used);
            var total = formatBytes(d.total);
            return '<div class="mon-disk-item">' +
                '<div class="mon-disk-label"><span>' + String(d.mount || d.device || '/') + '</span> <span>' + pct.toFixed(0) + '%</span></div>' +
                '<div class="mon-disk-usage">' + used + ' / ' + total + '</div>' +
                '<div class="mon-disk-bar"><div class="fill ' + cls + '" style="width:' + Math.min(100, pct) + '%;"></div></div>' +
            '</div>';
        }).join('');
    }

    function renderNetworkNet(net) {
        if (!net) return;
        var rx = $('monNetRxValue');
        if (rx) rx.textContent = net.rx || '0 B/s';
        var tx = $('monNetTxValue');
        if (tx) tx.textContent = net.tx || '0 B/s';
        var rxBar = $('monNetRxBar');
        if (rxBar) rxBar.style.width = Math.min(100, (Number(net.rx_mbps) || 0) / 10) + '%';
        var txBar = $('monNetTxBar');
        if (txBar) txBar.style.width = Math.min(100, (Number(net.tx_mbps) || 0) / 10) + '%';
        var conns = $('monNetConns');
        if (conns) conns.innerHTML = '<i class="fas fa-flag"></i> 连接数: ' + (net.conns || 0);
    }

    function updateHostInfo(hostname, procCount) {
        var h = $('monHostname');
        if (h) h.textContent = hostname || 'localhost';
        var c = $('monProcCount');
        if (c) c.textContent = procCount || 0;
    }

    // ============================================
    // 结论显示（AI 分析总结 → UI 右侧结论区）
    // ============================================
    function renderConclusion(data) {
        var el = $('monConclusionText');
        if (!el) return;
        var conclusion = data.ai_judgment || data.conclusion || data.summary_text || '';
        if (!conclusion) {
            el.textContent = '等待 AI 分析结论…';
            return;
        }
        el.textContent = conclusion;
    }

    function applyAll(data) {
        if (!data) return;
        hideUnavailable();
        renderStats(data);
        renderProcesses(data.processes, data.summary);
        renderSummary(data.summary);
        renderDisks(data.disks);
        renderNetworkNet(data.network);
        updateHostInfo(data.hostname, data.processes ? data.processes.length : 0);
        showDataSourceLabel(data.remote_server || '远程设备');
        renderConclusion(data);
    }

    // ---------- 数据源标记 / 不可用 ----------
    function showUnavailable(msg) {
        var overlay = $('monUnavailableOverlay');
        if (overlay) {
            overlay.style.display = 'flex';
            overlay.innerHTML =
                '<div class="mon-unavailable-icon"><i class="fas fa-satellite-dish"></i></div>' +
                '<div class="mon-unavailable-title">远程监控源不可用</div>' +
                '<div class="mon-unavailable-msg">' + (msg || '请通过 AI 启动远程监控（说"开始系统性能监控"）') + '</div>';
        }
        var dash = document.querySelector('.mon-dashboard');
        if (dash) {
            var children = dash.children;
            for (var i = 0; i < children.length; i++) {
                if (children[i].id !== 'monAlertPanel' && children[i].id !== 'monUnavailableOverlay') {
                    children[i].style.display = 'none';
                }
            }
        }
    }

    function hideUnavailable() {
        var overlay = $('monUnavailableOverlay');
        if (overlay) overlay.style.display = 'none';
        var dash = document.querySelector('.mon-dashboard');
        if (dash) {
            var children = dash.children;
            for (var i = 0; i < children.length; i++) {
                if (children[i].id !== 'monUnavailableOverlay') {
                    children[i].style.display = '';
                }
            }
        }
    }

    function showDataSourceLabel(server) {
        var label = $('monDataSourceLabel');
        if (label) {
            label.style.display = 'flex';
            label.innerHTML = '<i class="fas fa-globe"></i> 远程数据源: <strong>' + server + '</strong>';
        }
    }

    // ============================================
    // MCP 推流入口（B1 纯推送）：监控工具结果直达渲染 + 自动弹窗
    // ============================================
    window.pushMonitorData = function(data) {
        if (typeof data === 'string') {
            try { data = JSON.parse(data); } catch(e) { console.warn('[Monitor] pushMonitorData 解析失败:', e); return; }
        }
        if (!data || typeof data !== 'object') return;
        data.data_source = 'remote';
        data.remote_server = data.remote_server || 'linux_monitor';
        applyAll(data);
        renderConclusion(data);
        // 注意：不自动切换/打开监控 Tab，避免打断用户当前视图
        // 数据只在后台静默渲染，用户手动切到监控 Tab 时即可看到最新数据
    };

    // ============================================
    // 异常提醒（5 秒主动拉取，仅显示在「异常提醒框」monAlertPanel，不渲染横幅/独立角标）
    // ============================================
    var alertList = [];
    var _alertUiSignature = null;  // 上次渲染的告警签名（防抖：数据无变化不重绘）

    function getAlertIcon(level) {
        return level === 'critical' ? 'fa-exclamation-circle' : 'fa-exclamation-triangle';
    }
    function getAlertClass(level) {
        return level === 'critical' ? 'alert-critical' : 'alert-warning';
    }
    function getMetricLabel(metric) {
        var map = { cpu: 'CPU', memory: '内存', disk: '磁盘', network: '网络', process: '进程', service: '服务' };
        return map[metric] || metric || '系统';
    }
    function formatAlertTime(ts) {
        if (!ts) return '';
        try {
            var d = new Date(ts);
            function pad(n) { return n < 10 ? '0' + n : n; }
            return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
        } catch(e) { return ''; }
    }

    function renderAlertHTML(alert) {
        var level = alert.level === 'critical' ? 'critical' : 'warning';
        var icon = getAlertIcon(level);
        var marker = level === 'critical' ? '<i class="fas ' + icon + '" style="color:#ff5c7a;"></i>'
                                          : '<i class="fas ' + icon + '" style="color:#f5b942;"></i>';
        return '<div class="mon-alert-item ' + getAlertClass(level) + '">' +
            '<div class="mon-alert-item-icon">' + marker + '</div>' +
            '<div class="mon-alert-item-content">' +
                '<div class="mon-alert-item-title">' +
                    '<span class="mon-alert-level">' + (level === 'critical' ? '严重' : '警告') + '</span> ' +
                    '<span class="mon-alert-title-text">' + (alert.title || '未知异常') + '</span>' +
                '</div>' +
                '<div class="mon-alert-item-msg">' + (alert.message || '') + '</div>' +
                '<div class="mon-alert-item-meta">' +
                    '<span class="mon-alert-metric"><i class="fas fa-tag"></i> ' + getMetricLabel(alert.metric) + '</span>' +
                    (alert.current ? '<span><i class="fas fa-arrow-right"></i> 当前: ' + alert.current + '</span>' : '') +
                    (alert.threshold ? '<span><i class="fas fa-flag"></i> 阈值: ' + alert.threshold + '</span>' : '') +
                    '<span><i class="fas fa-clock"></i> ' + formatAlertTime(alert.timestamp) + '</span>' +
                '</div>' +
            '</div>' +
        '</div>';
    }

    // 告警签名：长度 + 最后一条标识，用于判断有无实质变化（防抖）
    function alertSignature(arr) {
        if (!arr || arr.length === 0) return 'empty';
        var last = arr[arr.length - 1];
        return arr.length + ':' + (last.timestamp || '') + ':' + (last.title || '');
    }

    // 仅渲染「异常提醒框」内列表（不渲染任何横幅，不操作独立入口角标）
    function renderAlertPanel() {
        var sig = alertSignature(alertList);
        if (sig === _alertUiSignature) return;  // 数据无变化 → 不触碰 DOM，避免 UI 闪烁
        _alertUiSignature = sig;
        var panel = $('monAlertPanel');
        var list = $('monAlertList');
        if (panel && list) {
            if (alertList.length === 0) {
                list.innerHTML = '<div class="mon-alert-empty"><i class="fas fa-check-circle"></i> 暂无异常提醒</div>';
            } else {
                list.innerHTML = alertList.slice().reverse().map(renderAlertHTML).join('');
            }
        }
    }

    window.pushMonitorAlert = function(alert) {
        try {
            if (typeof alert === 'string') alert = JSON.parse(alert);
        } catch(e) { console.warn('[Monitor] 提醒解析失败:', e); return; }
        if (!alert || typeof alert !== 'object') return;
        var dup = alertList.some(function(a) {
            return a.title === alert.title && a.timestamp === alert.timestamp;
        });
        if (dup) return;
        alertList.push(alert);
        if (alertList.length > 50) alertList = alertList.slice(-50);
        renderAlertPanel();
    };

    window.toggleAlertPanel = function(forceShow) {
        var panel = $('monAlertPanel');
        if (!panel) return;
        var show = forceShow === true ? true : (forceShow === false ? false : panel.style.display === 'none');
        panel.style.display = show ? 'block' : 'none';
        if (show) refreshAlerts();
    };

    window.clearMonitorAlerts = function() {
        alertList = [];
        renderAlertPanel();
        try {
            var b = bridge();
            if (b && typeof b.clearAlerts === 'function') b.clearAlerts();
        } catch(e) { console.warn('[Monitor] 清空后端提醒失败:', e); }
    };

    function refreshAlerts() {
        var b = bridge();
        if (!b) return;
        try {
            var p = b.getAlerts();
            if (p && typeof p.then === 'function') {
                p.then(function(result) {
                    var data = parseResult(result);
                    if (Array.isArray(data)) { alertList = data; renderAlertPanel(); }
                });
                return;
            }
            var data = parseResult(p);
            if (Array.isArray(data)) { alertList = data; renderAlertPanel(); }
        } catch(e) {
            console.warn('[Monitor] 获取提醒失败:', e);
        }
    }

    function parseResult(r) {
        try {
            return typeof r === 'string' ? JSON.parse(r) : (r || {});
        } catch(e) {
            console.warn('[Monitor] 解析失败:', e);
            return {};
        }
    }

    // ---------- 启动 ----------
    function init() {
        // B1 纯推送：数据由 pushMonitorData 推送渲染（无主数据轮询）
        // 1. 若主页面已缓冲数据（monitor.js 未加载时推送来的）→ 立即渲染
        if (window._pendingMonitorData) {
            var d = window._pendingMonitorData;
            window._pendingMonitorData = null;
            applyAll(d);
        }
        // 2. 无缓冲 → 从 MonitorBridge 内存缓存读取（后端 pushData 已缓存）
        else {
            var b = bridge();
            if (b && typeof b.getAll === 'function') {
                try {
                    var p = b.getAll();
                    if (p && typeof p.then === 'function') {
                        p.then(function(result) {
                            var data = parseResult(result);
                            if (data && data.data_source === 'remote') applyAll(data);
                        });
                    } else {
                        var data2 = parseResult(p);
                        if (data2 && data2.data_source === 'remote') applyAll(data2);
                    }
                } catch(e) { console.warn('[Monitor] 读取内存缓存失败:', e); }
            }
        }
        // 保留告警 5 秒轮询（仅渲染到异常提醒框）
        refreshAlerts();
        setInterval(refreshAlerts, 5000);
        // ★ 绑定 dataPushed 信号：数据到达 → 立即渲染（弹窗由后端 MonitorBridge.pushData 统一负责，避免双弹）
        var b2 = bridge();
        if (b2 && b2.dataPushed && typeof b2.dataPushed.connect === "function") {
            b2.dataPushed.connect(function() {
                try {
                    var pp = b2.getAll();
                    var dd = function(r) {
                        var d2 = typeof r === "string" ? JSON.parse(r) : r;
                        if (d2 && d2.data_source === "remote") applyAll(d2);
                    };
                    if (pp && typeof pp.then === "function") pp.then(dd); else dd(pp);
                } catch(e) { console.warn("[Monitor] signal render fail", e); }
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();