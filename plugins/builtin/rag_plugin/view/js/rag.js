// ============================================
// RAG 知识库 - 导入/记录/统计/检索预览
// 注意：QWebChannel bridge 调用是异步的，返回 Promise，需用 .then() 取值
// 后端推送（导入进度/日志/完成/统计/检索结果）经 execute_js 调 window.ragApp.*
// ============================================
window.ragApp = {
    _initialized: false,
    _page: 1,
    _pageSize: 50,
    _importing: false,
    _saveTimer: null,
    _restoreCollection: '',   // 上次保存的集合选择（applyStats 填充下拉后恢复）
    _lastImport: null,        // 最近一次成功启动的导入目标 {database, collection}（导入完成后记录表跟随它）
    _persistedDb: '',         // 持久化的状态栏向量库（getDefaults 恢复，首屏加载用）
    _persistedColl: '',       // 持久化的状态栏集合（getDefaults 恢复，首屏加载用）

    // ===== 初始化 =====
    init: function() {
        var self = this;
        if (!window.rag_bridge) {
            setTimeout(function() { self.init(); }, 300);
            return;
        }
        if (!this._initialized) {
            this._initialized = true;
            this._wireUiPersistence();
            this._wireComboDrops();
            this.appendLog('✅ RAG 数据库插件已就绪');
        }
        // ★ 先恢复持久化的状态栏库/集合上下文，再用该上下文加载统计与记录。
        //   否则首屏拿 default/空集合（下拉还没填充），新库导入的数据不显示、
        //   集合下拉显示（空）。
        this.loadDefaults().then(function() {
            var db = self._persistedDb || 'default';
            var coll = self._persistedColl || '';
            self.refreshStatus();
            self.refreshStats(db, coll);
            self.loadRecords(1, { db: db, coll: coll });
        });
    },

    // 自绘下拉事件接线（仅初始化一次）：
    // ① 选项点击选中（mousedown 委托，先于 input blur/外部 click 的收起执行）
    // ② 点击下拉外部任意处关闭
    _wireComboDrops: function() {
        var self = this;
        var lists = document.querySelectorAll('.rag-combo-list');
        for (var i = 0; i < lists.length; i++) {
            (function(ul) {
                ul.addEventListener('mousedown', function(e) {
                    var li = e.target;
                    while (li && li !== ul
                           && !(li.classList && li.classList.contains('rag-combo-item'))) {
                        li = li.parentNode;
                    }
                    if (li && li !== ul) {
                        self.pickCombo(ul.id, li.getAttribute('data-value'));
                        e.preventDefault();
                    }
                });
            })(lists[i]);
        }
        document.addEventListener('click', function(e) {
            var el = e.target;
            var inside = false;
            while (el) {
                if (el.classList && el.classList.contains('rag-combo')) { inside = true; break; }
                el = el.parentNode;
            }
            if (!inside) self._closeAllCombos();
        });
    },

    loadDefaults: function() {
        var self = this;
        return window.rag_bridge.getDefaults().then(function(s) {
            try {
                var d = JSON.parse(s);
                if (!d || d.error) return;
                if (document.getElementById('ragRootDir')) document.getElementById('ragRootDir').value = d.root_dir || '';
                if (document.getElementById('ragCollection')) document.getElementById('ragCollection').value = d.collection || 'knowledge';
                if (document.getElementById('ragDatabase')) document.getElementById('ragDatabase').value = d.database || 'default';
                self._fillDatalist('ragDbList', d.databases);
                self._fillDatalist('ragCollectionList', d.collections);
                if (document.getElementById('ragSplitMode')) document.getElementById('ragSplitMode').value = d.split_mode || 'smart';
                if (document.getElementById('ragSkipExisting')) document.getElementById('ragSkipExisting').checked = !!d.skip_existing;
                if (document.getElementById('ragDetectChanges')) document.getElementById('ragDetectChanges').checked = !!d.detect_changes;
                if (document.getElementById('ragCodeStructure')) document.getElementById('ragCodeStructure').checked = !!d.enable_code_structure;
                if (document.getElementById('ragFileTypes')) document.getElementById('ragFileTypes').value = (d.file_extensions || '');
                self._persistedDb = d.database || 'default';
                self._persistedColl = d.current_collection || '';
                self._restoreCollection = self._persistedColl;
            } catch(e) {}
        });
    },

    // ===== 状态 / 统计 =====
    refreshStatus: function() {
        var self = this;
        window.rag_bridge.getStatus().then(function(s) {
            try {
                var d = JSON.parse(s);
                if (!d || d.error) return;
                self._setImporting(!!d.running);
                var mm = d.model_ready || {};
                var el = document.getElementById('ragModelStatus');
                if (el) {
                    var emb = mm.embedding ? '就绪' : '未就绪';
                    var rrk = mm.rerank ? '就绪' : '未就绪';
                    el.innerHTML = '<i class="fas fa-microchip"></i> 模型: ' +
                        '<b class="' + (mm.embedding ? 'rag-ok' : 'rag-err') + '">嵌入 ' + emb + '</b>' +
                        ' / <b class="' + (mm.rerank ? 'rag-ok' : 'rag-err') + '">重排 ' + rrk + '</b>';
                }
                // 「已处理」计数由 applyStats（按当前库+集合过滤）统一刷新
            } catch(e) {}
        });
    },

    // 当前查看上下文（状态栏）：向量库 + 集合（空 = 全部集合）
    _currentContext: function() {
        var db = (document.getElementById('ragDbSelect') && document.getElementById('ragDbSelect').value) || 'default';
        var coll = (document.getElementById('ragCollections') && document.getElementById('ragCollections').value) || '';
        return { db: db, coll: coll };
    },

    // 填充自绘下拉选项（<ul class="rag-combo-list"> 的 <li> 项）。
    // 点击选中经事件委托（见 init），随 innerHTML 重建仍生效。
    _fillDatalist: function(id, items) {
        var ul = document.getElementById(id);
        if (!ul) return;
        ul.innerHTML = (items || []).map(function(it) {
            var s = String(it);
            return '<li class="rag-combo-item" data-value="' + s.replace(/"/g, '&quot;') + '">'
                 + s.replace(/</g, '&lt;') + '</li>';
        }).join('');
    },

    // ===== 自绘可编辑下拉（导入表单库/集合）=====
    // 说明：QtWebEngine 不渲染 <input list>+<datalist> 的下拉，故自绘成
    // 「输入框（可打字新名）+ ▾ 按钮 + 选项列表」，外观对齐状态栏 select。

    // 输入变化：打开并过滤列表；是「向量数据库」则顺带刷新「集合名称」下拉
    onComboInput: function(listId, isDb) {
        var self = this;
        var input = (listId === 'ragDbList')
            ? document.getElementById('ragDatabase')
            : document.getElementById('ragCollection');
        var v = ((input && input.value) || '').trim().toLowerCase();
        self._openComboFiltered(listId, v);
        if (isDb) self.onImportDbChange();
    },

    // ▾ 按钮：展开/收起（展开时显示全部选项）
    toggleCombo: function(listId) {
        var ul = document.getElementById(listId);
        if (!ul) return;
        var wasOpen = ul.style.display === 'block';
        this._closeAllCombos();
        if (!wasOpen) this._openComboFiltered(listId, '');
    },

    // 选项点击选中（onmousedown 由 init 事件委托调用）：填输入框 + 关闭 + 刷关联
    pickCombo: function(listId, value) {
        var input = (listId === 'ragDbList')
            ? document.getElementById('ragDatabase')
            : document.getElementById('ragCollection');
        if (input) input.value = value;
        this._closeAllCombos();
        if (listId === 'ragDbList') this.onImportDbChange();
    },

    // 输入框按键：Enter 选中第一个可见项；Esc 关闭
    onComboKeydown: function(e, listId) {
        if (e.key === 'Enter') {
            var ul = document.getElementById(listId);
            if (ul && ul.style.display === 'block') {
                var items = ul.querySelectorAll('.rag-combo-item');
                for (var i = 0; i < items.length; i++) {
                    if (items[i].style.display !== 'none') {
                        this.pickCombo(listId, items[i].getAttribute('data-value'));
                        break;
                    }
                }
                e.preventDefault();
            }
        } else if (e.key === 'Escape') {
            this._closeAllCombos();
        }
    },

    // 按输入过滤并显示列表；无匹配项时收起
    _openComboFiltered: function(listId, v) {
        var ul = document.getElementById(listId);
        if (!ul) return;
        var items = ul.querySelectorAll('.rag-combo-item');
        var shown = 0;
        for (var i = 0; i < items.length; i++) {
            var match = !v || items[i].getAttribute('data-value').toLowerCase().indexOf(v) >= 0;
            items[i].style.display = match ? '' : 'none';
            if (match) shown++;
        }
        ul.style.display = shown ? 'block' : 'none';
    },

    _closeAllCombos: function() {
        var lists = document.querySelectorAll('.rag-combo-list');
        for (var i = 0; i < lists.length; i++) lists[i].style.display = 'none';
    },

    refreshStats: function(db, coll) {
        var ctx = this._currentContext();
        try {
            window.rag_bridge.refreshStats(
                db || ctx.db,
                (coll === undefined || coll === null) ? ctx.coll : coll);
        } catch(e) {}
    },

    applyStats: function(payload) {
        try {
            var p = payload || {};
            if (p.error) return;
            // 状态栏向量库下拉 + 导入区自绘可编辑下拉（列表来自后端 list_databases）
            var curDb = (document.getElementById('ragDbSelect') && document.getElementById('ragDbSelect').value)
                        || p.current_database || 'default';
            this._fillDbSelect('ragDbSelect', p.databases, curDb, false);
            this._fillDatalist('ragDbList', p.databases);
            this._fillDatalist('ragCollectionList', p.collections);
            // 状态栏集合下拉：无集合 → 显示（空）；有集合 → 「全部集合」+ 各集合（保留当前/上次选择）
            var selC = document.getElementById('ragCollections');
            if (selC) {
                var cols = p.collections || [];
                var curColl = selC.value || this._restoreCollection || '';
                selC.innerHTML = cols.length
                    ? '<option value="">全部集合</option>' + cols.map(function(c) {
                        return '<option value="' + String(c).replace(/"/g, '&quot;') + '">' + String(c) + '</option>';
                      }).join('')
                    : '<option value="">（空）</option>';
                if (curColl && cols.indexOf(curColl) >= 0) selC.value = curColl;
                this._restoreCollection = '';
            }
            // 向量块：当前集合为空 → 整库总数；否则该集合块数
            var collName = (document.getElementById('ragCollections') || {}).value || '';
            var pp = p.per_collection || {};
            var chunks = collName ? (pp[collName] || 0) : (p.total_chunks || 0);
            if (document.getElementById('ragChunks')) document.getElementById('ragChunks').textContent = chunks;
            // 已处理：后端已按当前库+集合过滤
            var counts = p.counts || {};
            var total = 0;
            for (var k in counts) total += counts[k];
            if (document.getElementById('ragProcessed')) document.getElementById('ragProcessed').textContent = total;
            if (document.getElementById('ragSize')) document.getElementById('ragSize').textContent = (p.total_size_mb || 0).toFixed(1) + ' MB';
        } catch(e) {}
    },

    // ===== UI 状态持久化（写入 user/rag_config.json 的 ui.*，defaults/ 不改） =====
    saveUiState: function() {
        var state = {
            root_dir: (document.getElementById('ragRootDir') || {}).value || '',
            database: (document.getElementById('ragDatabase') || {}).value || '',
            collection: (document.getElementById('ragCollection') || {}).value || '',
            split_mode: (document.getElementById('ragSplitMode') || {}).value || 'smart',
            file_extensions: (document.getElementById('ragFileTypes') || {}).value || '',
            skip_existing: !!(document.getElementById('ragSkipExisting') || {}).checked,
            detect_changes: !!(document.getElementById('ragDetectChanges') || {}).checked,
            enable_code_structure: !!(document.getElementById('ragCodeStructure') || {}).checked,
            current_collection: (document.getElementById('ragCollections') || {}).value || ''
        };
        try { window.rag_bridge.saveUiState(JSON.stringify(state)); } catch(e) {}
    },

    // 文本输入防抖保存（下拉/复选即时保存）
    _scheduleSave: function() {
        var self = this;
        if (this._saveTimer) clearTimeout(this._saveTimer);
        this._saveTimer = setTimeout(function() { self.saveUiState(); }, 600);
    },

    // 表单控件变更 → 自动持久化
    _wireUiPersistence: function() {
        var self = this;
        var changeIds = ['ragSplitMode', 'ragSkipExisting', 'ragDetectChanges', 'ragCodeStructure'];
        var inputIds = ['ragRootDir', 'ragDatabase', 'ragCollection', 'ragFileTypes'];
        changeIds.forEach(function(id) {
            var el = document.getElementById(id);
            if (el) el.addEventListener('change', function() { self.saveUiState(); });
        });
        inputIds.forEach(function(id) {
            var el = document.getElementById(id);
            if (el) el.addEventListener('input', function() { self._scheduleSave(); });
        });
    },

    // 状态栏切换集合：同步刷新统计（已处理/向量块）+ 已处理文件记录 + 持久化
    pickCollection: function(name) {
        this.saveUiState();
        this.refreshStats();
        this.loadRecords(1);
    },

    // ===== 向量数据库 =====
    // 填充向量数据库下拉（id = select 的 DOM id；keepValue 是否尝试保持当前选中值）
    _fillDbSelect: function(id, databases, cur, keepValue) {
        var sel = document.getElementById(id);
        if (!sel) return;
        var list = databases && databases.length ? databases : [];
        if (keepValue && cur && list.indexOf(cur) < 0) list.unshift(cur);
        sel.innerHTML = (list.length ? '' : '<option value="">（空）</option>') +
            list.map(function(db) {
                return '<option value="' + String(db).replace(/"/g, '&quot;') + '">' + String(db) + '</option>';
            }).join('');
        if (cur && list.indexOf(cur) >= 0) sel.value = cur;
    },

    // 状态栏切换向量数据库：同步导入区默认库 + 持久化 + 重置集合 + 刷新统计与记录
    pickDatabase: function(name) {
        if (!name) return;
        var inp = document.getElementById('ragDatabase');
        if (inp) inp.value = name;
        var sel = document.getElementById('ragCollections');
        if (sel) sel.value = '';
        var self = this;
        self.onImportDbChange();   // 按新库刷新「集合名称」下拉
        window.rag_bridge.setDatabase(name).then(function(s) {
            try { JSON.parse(s); } catch(e) {}
            self.saveUiState();
            self.refreshStats();
            self.loadRecords(1);
        });
    },

    // ===== 导入 =====

    // 导入区「向量数据库」输入变化（或下拉选库）→ 按该库刷新「集合名称」下拉；
    // 新库名查不到 → 集合下拉清空（首次导入自动创建）。防抖 300ms。
    onImportDbChange: function() {
        var self = this;
        clearTimeout(this._dbChangeTimer);
        this._dbChangeTimer = setTimeout(function() {
            var db = (document.getElementById('ragDatabase') || {}).value || '';
            window.rag_bridge.getCollections(db).then(function(s) {
                try {
                    self._fillDatalist('ragCollectionList', JSON.parse(s));
                } catch(e) {}
            });
        }, 300);
    },

    startImport: function() {
        if (this._importing) { showToast('已有导入任务进行中', 'warning'); return; }
        var root = (document.getElementById('ragRootDir').value || '').trim();
        var collection = (document.getElementById('ragCollection').value || '').trim();
        var database = (document.getElementById('ragDatabase').value || '').trim() || 'default';
        if (!root) { showToast('请先填写文档目录', 'warning'); return; }
        if (!collection) { showToast('请填写集合名称', 'warning'); return; }

        var extText = (document.getElementById('ragFileTypes').value || '').trim();
        var fileExtensions = [];
        if (extText) {
            extText.split(',').forEach(function(e) {
                e = e.trim();
                if (e) fileExtensions.push(e.startsWith('.') ? e : '.' + e);
            });
        }

        var options = {
            root_dir: root,
            collection: collection,
            database: database,
            split_mode: document.getElementById('ragSplitMode').value,
            file_extensions: fileExtensions,
            skip_existing: document.getElementById('ragSkipExisting').checked,
            detect_changes: document.getElementById('ragDetectChanges').checked,
            enable_code_structure: document.getElementById('ragCodeStructure').checked,
            max_file_size_mb: 100
        };
        var self = this;
        window.rag_bridge.startImport(JSON.stringify(options)).then(function(s) {
            try {
                var r = JSON.parse(s);
                if (r && r.ok) {
                    self._lastImport = { database: database, collection: collection };
                    self._setImporting(true);
                    self.saveUiState();
                    showToast('导入已启动', 'success');
                } else {
                    showToast((r && r.message) || '启动导入失败', 'error');
                }
            } catch(e) { showToast('启动导入失败', 'error'); }
        });
    },

    stopImport: function() {
        try {
            window.rag_bridge.stopImport();
            this.appendLog('⚠ 正在停止导入…');
        } catch(e) {}
    },

    browseFolder: function() {
        var self = this;
        window.rag_bridge.browseFolder().then(function(path) {
            if (path && document.getElementById('ragRootDir')) {
                document.getElementById('ragRootDir').value = path;
            }
        });
    },

    downloadModels: function() {
        var self = this;
        this.appendLog('⬇ 正在检查模型…');
        window.rag_bridge.downloadModels().then(function(s) {
            try {
                var r = JSON.parse(s);
                if (r && r.ok) showToast(r.message || '已开始下载', 'info');
                else showToast((r && r.message) || '下载触发失败', 'error');
            } catch(e) { showToast('下载触发失败', 'error'); }
        });
    },

    _setImporting: function(running) {
        this._importing = !!running;
        var start = document.getElementById('ragStartBtn');
        var stop = document.getElementById('ragStopBtn');
        if (start) start.disabled = running;
        if (stop) stop.disabled = !running;
    },

    // ===== 后端推送（execute_js 调用） =====
    importProgress: function(done, total) {
        var wrap = document.getElementById('ragProgressWrap');
        var bar = document.getElementById('ragProgressBar');
        var txt = document.getElementById('ragProgressText');
        if (wrap) wrap.style.display = 'flex';
        var pct = total > 0 ? Math.round(done * 100 / total) : 0;
        if (bar) bar.style.width = pct + '%';
        if (txt) txt.textContent = done + ' / ' + total;
    },

    importLog: function(msg) {
        this.appendLog(msg || '');
    },

    importDone: function(stats) {
        var self = this;
        self._setImporting(false);
        var bar = document.getElementById('ragProgressBar');
        if (bar) bar.style.width = '100%';
        var s = stats || {};
        self.appendLog('📊 完成：成功 ' + (s.imported || 0) + '，跳过 ' + (s.skipped || 0) +
            '，失败 ' + (s.failed || 0) + '，写入 ' + (s.chunks_written || 0) + ' 块，耗时 ' +
            (s.duration_sec || 0) + 's');
        if (s.error_messages && s.error_messages.length) {
            s.error_messages.forEach(function(m) { self.appendLog('❌ ' + m, 'err'); });
        }
        setTimeout(function() {
            if (document.getElementById('ragProgressWrap')) document.getElementById('ragProgressWrap').style.display = 'none';
            self.refreshStatus();
            self._followLastImport();
        }, 400);
    },

    refreshRecords: function() {
        this.loadRecords(this._page);
    },

    // 导入完成：把状态栏（库/集合）与记录表切到本次导入目标，让刚导入的记录直接可见
    // （否则记录表按状态栏上下文过滤，新库/新集合的记录会被隐藏，集合下拉也显示空）
    _followLastImport: function() {
        var target = this._lastImport;
        this._lastImport = null;
        if (!target || !target.database) {
            this.refreshStats();
            this.loadRecords(1);
            return;
        }
        // 预置下拉选中值：applyStats 按 p.current_database / 保留选中 还原，非选项时自动回落到新库
        var dbSel = document.getElementById('ragDbSelect');
        var collSel = document.getElementById('ragCollections');
        if (dbSel) dbSel.value = target.database;
        if (collSel) collSel.value = target.collection || '';
        var self = this;
        window.rag_bridge.setDatabase(target.database).then(function() {
            self.saveUiState();
            // 显式传库/集合刷新：新库集合下拉能立刻填充；记录表用显式上下文过滤，不依赖下拉时序
            self.refreshStats(target.database, target.collection || '');
            self.loadRecords(1, { db: target.database, coll: target.collection || '' });
        });
    },

    // ===== 记录表 =====
    loadRecords: function(page, ctxOverride) {
        if (!window.rag_bridge) return;
        if (page < 1) page = 1;
        this._page = page;
        var search = (document.getElementById('ragRecordSearch').value || '').trim();
        var status = document.getElementById('ragRecordStatus').value || '';
        var ctx = ctxOverride || this._currentContext();
        var self = this;
        window.rag_bridge.getRecords(JSON.stringify({
            search: search, status: status, page: page, page_size: self._pageSize,
            database: ctx.db, collection: ctx.coll
        })).then(function(s) {
            try {
                var d = JSON.parse(s);
                if (!d || d.error) { self._renderRecords([], 0, page); return; }
                self._renderRecords(d.rows || [], d.total || 0, d.page || page);
            } catch(e) { self._renderRecords([], 0, page); }
        });
    },

    _renderRecords: function(rows, total, page) {
        var body = document.getElementById('ragRecordBody');
        if (!body) return;
        if (!rows.length) {
            body.innerHTML = '<tr><td colspan="8" class="rag-empty">暂无记录</td></tr>';
        } else {
            var html = '';
            var statusMap = { success: ['成功', 'rag-status-success'], failed: ['失败', 'rag-status-failed'],
                              skipped: ['跳过', 'rag-status-skipped'], processing: ['处理中', 'rag-status-processing'] };
            var splitMap = { smart: '智能分段', paragraph: '按段落', heading: '按章节', fixed: '按固定大小', code: '代码结构化' };
            var self = this;
            rows.forEach(function(r) {
                var st = statusMap[r.status] || [r.status || '-', ''];
                var t = r.processed_at ? new Date(r.processed_at * 1000).toLocaleString('zh-CN') : '-';
                var err = (r.status === 'failed' && r.error_message) ? (' title="' + String(r.error_message).replace(/"/g, '&quot;') + '"') : '';
                var path = String(r.file_path).replace(/\\/g, '\\\\').replace(/'/g, "\\'");
                var ops = '';
                if (r.status === 'failed') {
                    ops += '<button class="rag-btn rag-btn-sm" onclick="window.ragApp.retryFile(\'' + path + '\')">重试</button>';
                }
                ops += '<button class="rag-btn rag-btn-sm rag-btn-danger" title="删除记录及对应向量数据" onclick="window.ragApp.deleteRecord(\'' + path + '\')">删除</button>';
                html += '<tr' + err + '>' +
                    '<td>' + (r.file_name || '') + '</td>' +
                    '<td><span class="rag-status-tag ' + st[1] + '">' + st[0] + '</span></td>' +
                    '<td>' + (r.chunk_count || 0) + '</td>' +
                    '<td>' + (r.database || '-') + '</td>' +
                    '<td>' + (r.collection_name || '-') + '</td>' +
                    '<td>' + (splitMap[r.split_strategy] || r.split_strategy || '-') + '</td>' +
                    '<td>' + t + '</td>' +
                    '<td>' + ops + '</td>' +
                    '</tr>';
            });
            body.innerHTML = html;
        }
        var totalEl = document.getElementById('ragRecordTotal');
        if (totalEl) totalEl.textContent = '共 ' + total + ' 条';
        var pageEl = document.getElementById('ragRecordPage');
        if (pageEl) pageEl.textContent = '第 ' + page + ' 页';
    },

    retryFile: function(filePath) {
        var self = this;
        window.rag_bridge.retryFile(filePath).then(function(s) {
            try {
                var r = JSON.parse(s);
                if (r && r.ok) { self._setImporting(true); showToast('已开始重试该文件', 'success'); }
                else showToast((r && r.message) || '重试启动失败', 'error');
            } catch(e) { showToast('重试启动失败', 'error'); }
        });
    },

    // 删除单个文件：处理记录 + 对应向量数据
    deleteRecord: function(filePath) {
        var self = this;
        self.openConfirm('确定删除该文件的处理记录及对应的向量数据？', '确认删除', function() {
            window.rag_bridge.deleteRecord(filePath).then(function(s) {
                try {
                    var r = JSON.parse(s);
                    if (r && r.ok) {
                        showToast('已删除该文件记录' + (r.deleted_chunks ? '（删除 ' + r.deleted_chunks + ' 个块）' : ''), 'success');
                        self.loadRecords(self._page);
                        self.refreshStats();
                    }
                    else showToast((r && r.message) || '删除失败', 'error');
                } catch(e) { showToast('删除失败', 'error'); }
            });
        });
    },

    // 删除集合：向量数据 + 该库下该集合的记录
    deleteCollection: function() {
        var coll = (document.getElementById('ragCollection').value || '').trim();
        if (!coll) { showToast('请先输入集合名称', 'warning'); return; }
        var db = (document.getElementById('ragDatabase').value || '').trim() || 'default';
        var self = this;
        self.openConfirm('确定删除集合「' + coll + '」？将删除其全部向量数据与文件记录，且不可恢复。', '确认删除', function() {
            window.rag_bridge.deleteCollection(coll, db).then(function(s) {
                try {
                    var r = JSON.parse(s);
                    if (r && r.ok) {
                        showToast('已删除集合「' + coll + '」（删除 ' + (r.records_deleted || 0) + ' 条记录）', 'success');
                        if (document.getElementById('ragCollection').value === coll) document.getElementById('ragCollection').value = '';
                        self.saveUiState();
                        self.refreshStats();
                        self.loadRecords(1);
                    }
                    else showToast((r && r.message) || '删除失败', 'error');
                } catch(e) { showToast('删除失败', 'error'); }
            });
        });
    },

    // 删除向量数据库：全部集合 + 该库全部记录
    deleteDatabase: function() {
        var db = (document.getElementById('ragDatabase').value || '').trim();
        if (!db) { showToast('请先输入向量数据库名称', 'warning'); return; }
        var self = this;
        self.openConfirm('确定删除向量数据库「' + db + '」？将删除其全部集合与文件记录，且不可恢复。', '确认删除', function() {
            window.rag_bridge.deleteDatabase(db).then(function(s) {
                try {
                    var r = JSON.parse(s);
                    if (r && r.ok) {
                        showToast('已删除数据库「' + db + '」（删除 ' + (r.collections_deleted || 0) + ' 个集合、' + (r.records_deleted || 0) + ' 条记录）', 'success');
                        if (document.getElementById('ragDatabase').value === db) document.getElementById('ragDatabase').value = '';
                        self.saveUiState();
                        self.refreshStats();
                        self.loadRecords(1);
                    }
                    else showToast((r && r.message) || '删除失败', 'error');
                } catch(e) { showToast('删除失败', 'error'); }
            });
        });
    },

    exportCsv: function() {
        var self = this;
        window.rag_bridge.exportCsv().then(function(s) {
            try {
                var r = JSON.parse(s);
                if (r && r.ok) showToast('已导出 ' + (r.count || 0) + ' 条记录', 'success');
                else if (r && r.cancelled) { /* 用户取消 */ }
                else showToast((r && r.message) || '导出失败', 'error');
            } catch(e) { showToast('导出失败', 'error'); }
        });
    },

    // 打开确认模态框（替代原生 confirm——QtWebEngine 原生弹窗是系统白色样式）
    openConfirm: function(text, okLabel, onOk) {
        var mask = document.getElementById('ragConfirmMask');
        if (!mask) { if (confirm(text)) onOk && onOk(); return; }
        document.getElementById('ragConfirmText').textContent = text || '';
        document.getElementById('ragConfirmOkBtn').textContent = okLabel || '确认';
        this._confirmOnOk = onOk;
        mask.style.display = 'flex';
    },
    closeConfirm: function(ok) {
        var mask = document.getElementById('ragConfirmMask');
        if (mask) mask.style.display = 'none';
        var cb = this._confirmOnOk;
        this._confirmOnOk = null;
        if (ok && cb) cb();
    },

    clearRecords: function() {
        var self = this;
        self.openConfirm('确定清空全部文件处理记录？同时将删除向量库中的全部数据（所有集合），此操作不可恢复。', '确认清空', function() {
            window.rag_bridge.clearRecords().then(function(s) {
                try {
                    var r = JSON.parse(s);
                    if (r && r.ok) {
                        showToast('已清空 ' + (r.count || 0) + ' 条记录，删除 ' + (r.collections_deleted || 0) + ' 个集合', 'success');
                        self.loadRecords(1);
                        self.refreshStats();
                    }
                    else showToast((r && r.message) || '清空失败', 'error');
                } catch(e) { showToast('清空失败', 'error'); }
            });
        });
    },

    // ===== 检索预览 =====
    runSearch: function() {
        var query = (document.getElementById('ragSearchQuery').value || '').trim();
        if (!query) { showToast('请输入检索问题', 'warning'); return; }
        var topK = parseInt(document.getElementById('ragSearchTopK').value || '5', 10) || 5;
        var ctx = this._currentContext();
        var self = this;
        var box = document.getElementById('ragSearchResults');
        if (box) box.innerHTML = '<div class="rag-result-empty">🔍 检索中…</div>';
        window.rag_bridge.testSearch(JSON.stringify({
            query: query, top_k: topK, database: ctx.db, collection: ctx.coll || null,
            enable_rerank: true
        })).then(function(s) {
            try {
                var r = JSON.parse(s);
                if (!(r && r.ok)) { showToast((r && r.message) || '检索启动失败', 'error'); }
            } catch(e) { showToast('检索启动失败', 'error'); }
        });
    },

    searchPreview: function(payload) {
        var box = document.getElementById('ragSearchResults');
        if (!box) return;
        var p = payload || {};
        if (p.error && !p.chunks) {
            box.innerHTML = '<div class="rag-result-error">❌ 检索异常：' + p.error + '</div>';
            return;
        }
        if (!p.chunks || !p.chunks.length) {
            box.innerHTML = '<div class="rag-result-empty">未检索到相关内容（知识库可能为空，或模型未就绪）</div>';
            return;
        }
        var html = '';
        p.chunks.forEach(function(c) {
            var heading = c.heading_path ? ('｜<span class="rag-result-heading">' + c.heading_path + '</span>') : '';
            html += '<div class="rag-result-card">' +
                '<div class="rag-result-head">' +
                '<span class="rag-result-score">' + c.score.toFixed(3) + '</span>' +
                '<span class="rag-result-file">📄 ' + (c.file_name || c.file_path || '未知') + '</span>' + heading +
                '</div>' +
                '<div class="rag-result-content">' + (c.content || '') + '</div>' +
                '</div>';
        });
        html += '<div class="rag-result-meta">候选 ' + (p.rough_count || 0) + ' 条｜返回 ' + p.count + ' 条｜耗时 ' +
            (p.total_time_ms || 0) + 'ms' + (p.rerank_skipped ? '｜重排降级（模型未就绪）' : '') + '</div>';
        box.innerHTML = html;
    },

    // ===== 日志 =====
    appendLog: function(msg, cls) {
        var log = document.getElementById('ragLog');
        if (!log) return;
        var div = document.createElement('div');
        var text = String(msg);
        var clsName = cls;
        if (!clsName) {
            if (text.indexOf('✅') === 0) clsName = 'rag-ok';
            else if (text.indexOf('❌') === 0) clsName = 'rag-err';
            else if (text.indexOf('⏭') === 0) clsName = 'rag-skip';
            else if (text.indexOf('⚠') === 0 || text.indexOf('🔶') === 0) clsName = 'rag-warn';
            else clsName = 'rag-info';
        }
        div.className = clsName;
        div.textContent = text;
        log.appendChild(div);
        log.scrollTop = log.scrollHeight;
        // 防止日志无限增长
        while (log.childNodes.length > 300) log.removeChild(log.firstChild);
    }
};

// 插件 tab 打开时由 plugins.js 注入执行，自动初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() { window.ragApp.init(); });
} else {
    window.ragApp.init();
}
