// ============================================
// 视频中心 - 播放/列表/断点续播/5秒保存/AI控制
// 注意：QWebChannel bridge 调用是异步的，返回 Promise，需用 .then() 取值
// ============================================
window.videoApp = {
    _currentVideoId: null,
    _positionSaveTimer: null,
    _pendingPlay: null,      // ★ 异步播放待续项（等待 playReady/playUrlReady 回调）
    _pendingSeek: null,      // ★ 异步 seek 待续项（等待 seekReady 回调）
    _retryTimer: null,       // ★ SRC_NOT_SUPPORTED 自动重试定时器句柄
    _streamStartPos: 0,      // 转码/直通流 URL 携带的实际起始位置（秒）
    _initialized: false,
    _player: null,
    _allVideos: [],
    _currentDuration: 0,   // 当前播放视频的真实总时长（秒），来自数据库/列表，优于 Chromium 推断值
    // ★ 2026-08-14 三级分组规范顺序（与 index.html 工具栏下拉 value 一致）；未收录/空值放最后
    _videoDimOrder: {
        subject: ['数学', '语文', '英语', '科学', '艺术', '健康'],
        grade:   ['学前班', '大班', '中班', '小班'],
        source:  ['智慧教育平台', 'bilibili', '优酷']
    },
    // ★ 2026-08-14 展开列表分组折叠状态：key → true（展开）；缺省 = 折叠
    //   key 形如 's:语文' / 's:语文|g:大班' / 's:语文|g:大班|src:bilibili'；重渲染后仍保持
    _expandedGroups: {},

    // ===== 初始化 =====
    // ===== ★ 解码能力探测（证明 QWebEngine 支持什么编码）=====
    supportProbe: function() {
        try {
            var v = document.createElement('video');
            var a = document.createElement('audio');
            var results = {
                'H.264 mp4': v.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"'),
                'HEVC mp4': v.canPlayType('video/mp4; codecs="hvc1"'),
                'VP8 webm': v.canPlayType('video/webm; codecs="vp8"'),
                'VP9 webm': v.canPlayType('video/webm; codecs="vp9"'),
                'AV1 mp4': v.canPlayType('video/mp4; codecs="av01"'),
                'AAC': a.canPlayType('audio/mp4; codecs="mp4a.40.2"'),
                'MP3': a.canPlayType('audio/mpeg'),
                'Opus': a.canPlayType('audio/webm; codecs="opus"'),
                'EAC3': a.canPlayType('audio/mp4; codecs="ec-3"'),
                'FLAC': a.canPlayType('audio/flac')
            };
            console.log('[videoApp] 🔍 解码能力探测:', JSON.stringify(results));
        } catch(e) {}
    },

    init: function() {
        // ★ 2026-08-13 幂等守卫：重复 init 不重复绑定事件/重复刷新
        if (this._initialized) return;
        this._initialized = true;
        var self = this;
        this._player = document.getElementById('videoPlayer');
        if (!this._player) return;
        this.supportProbe();

        // 播放器事件
        this._player.addEventListener('pause', function() { self.savePosition(); });
        this._player.addEventListener('ended', function() { self.savePosition(); });
        // ★ 修复：pause 时 savePosition() 会清掉 5s 定时器；这里在再次 play（原生控制条/AI resume）
        //   时恢复定时保存，避免续播后位置不再自动落库
        this._player.addEventListener('play', function() {
            if (self._currentVideoId && !self._positionSaveTimer) {
                self.startPositionSave(self._currentVideoId);
            }
        });
        // ★ 2026-08-13 真正开始播放 → 隐藏等待旋转动画
        this._player.addEventListener('playing', function() { self._hideSpinner(); });
        // ★ 播放时间只显示在 <video> 内部原生 controls 上，下方卡片不再更新

        this.refreshList();
    },

    // ===== 全屏展开列表（★ 2026-08-14 在普通列表基础上加全屏多列网格，缩略图原尺寸）=====
    openFullscreen: function() {
        var el = document.getElementById('videoListFullscreen');
        if (el) el.style.display = 'flex';
    },
    closeFullscreen: function() {
        var el = document.getElementById('videoListFullscreen');
        if (el) el.style.display = 'none';
    },

    // ===== 列表加载（异步 Promise）=====
    refreshList: function(payload) {
        var self = this;
        if (!window.video_bridge) return;
        var filter = {
            subject: document.getElementById('videoSubjectFilter').value,
            grade: document.getElementById('videoGradeFilter').value,
            source: document.getElementById('videoSourceFilter').value,
            keyword: document.getElementById('videoSearchInput').value
        };
        var p = window.video_bridge.getVideos(JSON.stringify(filter));
        if (p && typeof p.then === 'function') {
            p.then(function(result) {
                try {
                    var parsed = (typeof result === 'string') ? JSON.parse(result) : result;
                    self._allVideos = Array.isArray(parsed) ? parsed : [];
                } catch(e) {
                    self._allVideos = [];
                }
                self._renderList();
            }).catch(function(e) {
                console.warn('[videoApp] getVideos 失败:', e);
                self._allVideos = [];
                self._renderList();
            });
        } else {
            try {
                var parsed = (typeof p === 'string') ? JSON.parse(p) : p;
                this._allVideos = Array.isArray(parsed) ? parsed : [];
            } catch(e) {
                this._allVideos = [];
            }
            this._renderList();
        }
    },

    _renderList: function() {
        var container = document.getElementById('videoList');
        var fullscreenContainer = document.getElementById('fullscreenVideoList');
        var countEl = document.getElementById('videoCount');
        var fullscreenCountEl = document.getElementById('fullscreenVideoCount');
        if (!container) return;

        var videos = this._allVideos || [];
        var emptyHtml = '<div class="video-empty">🎬 暂无视频<br>请让 AI 搜索教学视频</div>';
        if (videos.length === 0) {
            container.innerHTML = emptyHtml;
            if (fullscreenContainer) fullscreenContainer.innerHTML = emptyHtml;
            if (countEl) countEl.textContent = '0 个视频';
            if (fullscreenCountEl) fullscreenCountEl.textContent = '0 个视频';
            return;
        }
        if (countEl) countEl.textContent = videos.length + ' 个视频';
        if (fullscreenCountEl) fullscreenCountEl.textContent = videos.length + ' 个视频';

        var self = this;
        // 分支 1：普通列表保持扁平平铺（现状不变）
        container.innerHTML = videos.map(function(v) { return self._renderItem(v); }).join('');
        // 分支 2：展开列表三级嵌套分组（科目 > 年级 > 来源），并绑定分组标题点击折叠
        if (fullscreenContainer) {
            this._bindGroupToggle();
            fullscreenContainer.innerHTML = self._renderFullscreenList(videos);
        }
    },

    // ★ 2026-08-14 分组标题点击展开/收起：事件委托挂在 #fullscreenVideoList（innerHTML 重建不影响监听）
    _bindGroupToggle: function() {
        if (this._groupToggleBound) return;
        this._groupToggleBound = true;
        var self = this;
        var container = document.getElementById('fullscreenVideoList');
        if (!container) return;
        container.addEventListener('click', function(e) {
            var el = e.target;
            while (el && el !== container) {
                if (el.getAttribute && el.getAttribute('data-expand')) {
                    self.toggleGroup(el);
                    return;
                }
                el = el.parentNode;
            }
        });
    },

    // 切换分组展开/收起；折叠状态写入 _expandedGroups 并在重渲染后保持
    // 箭头为 fa-chevron-right，展开时由 CSS (:not(.collapsed) 旋转 90°) 指向下，无需 JS 改图标
    toggleGroup: function(section) {
        var key = section.getAttribute('data-expand');
        var map = this._expandedGroups || (this._expandedGroups = {});
        var isCollapsed = section.classList.contains('collapsed');
        if (isCollapsed) {
            section.classList.remove('collapsed');
            map[key] = true;
        } else {
            section.classList.add('collapsed');
            delete map[key];
        }
    },

    // 单条 .video-item HTML（普通列表与分组网格共用）
    _renderItem: function(v) {
        var esc = this._esc;
        var statusHtml = '';
        var actions = '';
        var id = esc(v.id);
        // ★ 2026-08-13 播放中标识：当前正在播放的视频在列表中明确显示「▶ 播放中」
        var playingHtml = (v.id === this._currentVideoId)
            ? '<span class="video-status playing">▶ 播放中</span>'
            : '';
        if (v.status === 'downloaded') {
            statusHtml = '<span class="video-status downloaded">✓ 已下载</span>';
        } else if (v.status === 'downloading') {
            statusHtml = '<span class="video-status downloading">⏳ 下载中 ' +
                (v.downloadProgress || 0) + '%</span>';
        } else if (v.status === 'failed') {
            statusHtml = '<span class="video-status failed">✗ 下载失败</span>';
            actions = '<button class="video-btn" title="重新下载" onclick="event.stopPropagation();window.videoApp.download(\'' +
                id + '\')"><i class="fas fa-redo"></i></button>';
        } else {
            statusHtml = '<span class="video-status online">在线</span>';
            actions = '<button class="video-btn" title="下载" onclick="event.stopPropagation();window.videoApp.download(\'' +
                id + '\')"><i class="fas fa-download"></i></button>';
        }
        if (v.status === 'downloaded' || v.status === 'online' || v.status === 'failed') {
            actions += '<button class="video-btn" title="删除" onclick="event.stopPropagation();window.videoApp.remove(\'' +
                id + '\')"><i class="fas fa-trash"></i></button>';
        }
        // ★ 2026-08-13 移除列表播放按钮：点击条目本身（video-item onclick）即播放，按钮多余

        var thumb = v.thumbnail
            ? '<img src="' + esc(v.thumbnail) + '" class="video-thumb" onerror="this.outerHTML=window.videoApp._thumbFallback()">'
            : this._thumbFallback();

        var resume = (v.lastPosition && v.lastPosition > 0)
            ? '<div class="video-resume">⏺ 上次播到 ' + this._formatTime(v.lastPosition) + '</div>'
            : '';

        return '<div class="video-item' + (v.id === this._currentVideoId ? ' active' : '') + '"' +
            ' onclick="window.videoApp.play(\'' + id + '\')">' +
            thumb +
            '<div class="video-item-info">' +
                (v.seriesTitle
                    ? '<div class="video-series-tag" title="所属系列">📚 ' + esc(v.seriesTitle) + '</div>'
                    : '') +
                '<div class="video-item-title" title="' + esc(v.title) + '">' + esc(v.title) + '</div>' +
                '<div class="video-item-meta">' +
                    '<i class="fas fa-book"></i> ' + esc(v.subject || '未知') +
                    ' · ' + esc(v.grade || '未知') +
                    ' · ' + esc(v.source || '未知') +
                    '<span style="margin-left:6px;">⏱ ' + this._formatTime(v.duration || 0) + '</span>' +
                    (v.episodeIndex ? ' · 第' + esc(v.episodeIndex) + '集' : '') +
                    (v.quality ? ' · ' + esc(v.quality) : '') +
                '</div>' +
                resume +
                '<div class="video-item-actions">' + playingHtml + statusHtml + actions + '</div>' +
            '</div>' +
        '</div>';
    },

    // ===== 展开列表三级嵌套分组（科目 > 年级 > 来源）=====
    // ★ 2026-08-14 用户需求：展开页面按 科目/年级/来源 分类显示；普通列表保持平铺
    // 分组键归一化：空/空白统一为 ''
    _dimKey: function(value) {
        return (value == null ? '' : String(value).trim());
    },
    // 分组标题展示名：空值给维度专属文案；来源 value → 显示名（bilibili → B站）
    _dimLabel: function(key, dim) {
        if (!key) {
            return (dim === 'subject') ? '未知科目'
                 : (dim === 'grade')   ? '未知年级'
                 : '未知来源';
        }
        if (dim === 'source' && key === 'bilibili') return 'B站';
        return key;
    },
    // 按规范顺序排序（_videoDimOrder），规范表外/空值追加到末尾
    _sortDimKeys: function(group, dim) {
        var order = this._videoDimOrder[dim] || [];
        var index = {};
        for (var i = 0; i < order.length; i++) index[order[i]] = i;
        var known = [], unknown = [];
        Object.keys(group).forEach(function(k) {
            if (Object.prototype.hasOwnProperty.call(index, k)) known.push(k);
            else unknown.push(k);
        });
        known.sort(function(a, b) { return index[a] - index[b]; });
        return known.concat(unknown);
    },
    // 三级分桶：subject → grade → source，最内层收集视频条目
    _groupVideos: function(videos) {
        var root = {};
        var self = this;
        videos.forEach(function(v) {
            var sKey = self._dimKey(v.subject);
            var gKey = self._dimKey(v.grade);
            var srcKey = self._dimKey(v.source);
            if (!root[sKey])          root[sKey]          = { count: 0, grades: {} };
            var sG = root[sKey];
            if (!sG.grades[gKey])     sG.grades[gKey]     = { count: 0, sources: {} };
            var gG = sG.grades[gKey];
            if (!gG.sources[srcKey])  gG.sources[srcKey]  = { count: 0, items: [] };
            var srcG = gG.sources[srcKey];
            srcG.items.push(v);
            srcG.count++; gG.count++; sG.count++;
        });
        return root;
    },
    // 生成三级嵌套分组 HTML（所有标题经 _esc 转义；★ 2026-08-14 默认全部折叠，标题可点击展开）
    // ★ 2026-08-14 图标化：箭头 fa-chevron-right（展开时 CSS 旋转 90°）、
    //   科目 fa-graduation-cap / 年级 fa-users / 来源 fa-tv
    _renderFullscreenList: function(videos) {
        var self = this;
        var grouped = this._groupVideos(videos);
        var expanded = this._expandedGroups || {};
        var html = '';
        this._sortDimKeys(grouped, 'subject').forEach(function(sKey) {
            var sG = grouped[sKey];
            var sExpKey = 's:' + sKey;
            var sCollapsed = expanded[sExpKey] ? '' : ' collapsed';
            var subHtml = '';
            self._sortDimKeys(sG.grades, 'grade').forEach(function(gKey) {
                var gG = sG.grades[gKey];
                var gExpKey = 's:' + sKey + '|g:' + gKey;
                var gCollapsed = expanded[gExpKey] ? '' : ' collapsed';
                var srcHtml = '';
                self._sortDimKeys(gG.sources, 'source').forEach(function(srcKey) {
                    var srcG = gG.sources[srcKey];
                    var srcExpKey = 's:' + sKey + '|g:' + gKey + '|src:' + srcKey;
                    var srcCollapsed = expanded[srcExpKey] ? '' : ' collapsed';
                    var itemsHtml = srcG.items.map(function(v) { return self._renderItem(v); }).join('');
                    srcHtml +=
                        '<div class="video-cat-source' + srcCollapsed + '" data-expand="' + self._esc(srcExpKey) + '">' +
                            '<div class="video-cat-label video-cat-toggle">' +
                                '<i class="video-cat-arrow fas fa-chevron-right"></i>' +
                                '<i class="video-cat-ico fas fa-tv"></i>' +
                                '<span class="video-cat-name">' + self._esc(self._dimLabel(srcKey, 'source')) + '</span>' +
                                '<span class="video-cat-count">' + srcG.items.length + ' 个视频</span>' +
                            '</div>' +
                            '<div class="video-cat-body">' +
                                '<div class="video-cat-grid">' + itemsHtml + '</div>' +
                            '</div>' +
                        '</div>';
                });
                subHtml +=
                    '<div class="video-cat-sub' + gCollapsed + '" data-expand="' + self._esc(gExpKey) + '">' +
                        '<div class="video-cat-label video-cat-toggle">' +
                            '<i class="video-cat-arrow fas fa-chevron-right"></i>' +
                            '<i class="video-cat-ico fas fa-users"></i>' +
                            '<span class="video-cat-name">' + self._esc(self._dimLabel(gKey, 'grade')) + '</span>' +
                            '<span class="video-cat-count">' + gG.count + ' 个视频</span>' +
                        '</div>' +
                        '<div class="video-cat-body">' + srcHtml + '</div>' +
                    '</div>';
            });
            html +=
                '<div class="video-cat-group' + sCollapsed + '" data-expand="' + self._esc(sExpKey) + '">' +
                    '<div class="video-cat-header video-cat-toggle">' +
                        '<i class="video-cat-arrow fas fa-chevron-right"></i>' +
                        '<i class="video-cat-ico fas fa-graduation-cap"></i>' +
                        '<span class="video-cat-name">' + self._esc(self._dimLabel(sKey, 'subject')) + '</span>' +
                        '<span class="video-cat-count">' + sG.count + ' 个视频</span>' +
                    '</div>' +
                    '<div class="video-cat-body">' + subHtml + '</div>' +
                '</div>';
        });
        return html;
    },

    _thumbFallback: function() {
        return '<div class="video-thumb video-thumb-fallback"><i class="fas fa-play-circle"></i></div>';
    },

    // ★ HTML 转义（列表渲染所有外部字段必须先经此函数，防标题含引号/尖括号破坏布局或注入脚本）
    _esc: function(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    },

    // ★ 2026-08-13 播放区等待旋转动画：_startPlay 显示，开始播放(playing)/出错(error)隐藏
    // ★ 2026-08-13 修复双圈：用户看到「黑圈(上面) + 白圈(下面)」——黑圈是 Chromium 原生
    //   <video controls> 媒体控件内建的加载环，渲染在 shadow DOM 里，页面 CSS 无法隐藏；
    //   它只在 controls 属性存在时才渲染。因此白圈显示期间先摘掉 controls（原生黑圈随之消失），
    //   白圈隐藏（真正开始播放/出错）时再恢复 controls → 原生进度条/时长照常显示。
    _showSpinner: function() {
        try {
            var el = document.getElementById('videoSpinner');
            if (el) el.style.display = 'block';
            if (this._player) this._player.controls = false;  // 摘原生控件 → 黑圈消失
        } catch(e) {}
    },
    _hideSpinner: function() {
        try {
            var el = document.getElementById('videoSpinner');
            if (el) el.style.display = 'none';
            if (this._player) this._player.controls = true;   // 恢复原生控件（时长/进度条）
        } catch(e) {}
    },

    // ===== 播放（断点续播）=====
    play: function(video_id) {
        var self = this;
        // ★ 2026-08-14 从全屏列表点视频 → 播放并收起全屏
        this.closeFullscreen();
        var videos = this._allVideos || [];
        var video = null;
        for (var i = 0; i < videos.length; i++) {
            if (videos[i].id === video_id) { video = videos[i]; break; }
        }
        if (!video) {
            var p = window.video_bridge.getVideos('{}');
            if (p && typeof p.then === 'function') {
                p.then(function(allStr) {
                    try {
                        var all = JSON.parse(allStr);
                        for (var j = 0; j < all.length; j++) {
                            if (all[j].id === video_id) { self._startPlay(all[j]); break; }
                        }
                    } catch(e) {}
                });
            }
            return;
        }
        this._startPlay(video);
    },

    // 真正开始播放
    _startPlay: function(video) {
        var self = this;
        var video_id = video.id;
        var prevId = this._currentVideoId;
        // ★ 2026-08-13 修复：切换视频前先把上一视频断点落库（此时 _currentVideoId 仍是旧值）。
        //   否则先改 _currentVideoId 再 pause（_releasePlayerSource 内部）
        //   会触发 savePosition()，把旧位置写到新视频 ID 上。
        //   同一视频重播（prevId === video_id）无需重复保存。
        if (prevId && prevId !== video_id) this.savePosition();
        // ★ 2026-08-14 修复：切换视频时【立即停止】旧视频。
        //   此前只 _showSpinner()（46px 小圈居中不遮画面），旧视频画面+声音继续播到新流就绪
        //   → 用户感知「新视频就绪前一直播旧视频」。
        //   在改 _currentVideoId 之前释放（pause 事件 → savePosition 仍写旧视频位置）。
        if (prevId && prevId !== video_id && this._player) {
            this._releasePlayerSource(this._player);
            this._stopAudioSync();
        }
        this._currentVideoId = video_id;
        // ★ 2026-08-13 播放启动中 → 播放区显示等待旋转动画（playing/error 时隐藏）
        this._showSpinner();
        // ★ 每次新播放清除上一次未完成的异步解析待续项 + 自动重试定时器
        this._pendingPlay = null;
        this._pendingSeek = null;
        if (this._retryTimer) { clearTimeout(this._retryTimer); this._retryTimer = null; }
        // ★ 2026-08-13 修复：SRC_NOT_SUPPORTED 自动重试标记只在【切换视频】时重置
        //   （此前在 _playStreamUrl/_doPlay 每次播放都重置 → 同一视频转码流报错时持续重试死循环）
        if (prevId !== video_id && this._player) this._player._retriedOnce = false;
        var player = this._player;

        // 已下载 → 本地播放（探测原生支持则直接 file://，否则 ffmpeg 转码）
        if (video.localPath) {
            this._playLocalExternal(video);
            return;
        }

        // 在线 → 先解析真实可播放地址（yt-dlp）
        var nowTitle = document.getElementById('videoNowTitle');
        if (nowTitle) nowTitle.textContent = '⏳ 正在解析视频地址...';
        var p = window.video_bridge.getPlayableUrl(video_id);
        if (p && typeof p.then === 'function') {
            p.then(function(result) {
                try {
                    var data = (typeof result === 'string') ? JSON.parse(result) : result;
                    if (data && data.ok && data.url) {
                        if (data.local) {
                            // ★ 本地兜底命中（DB 无 localPath 但磁盘有文件）→ 走本地播放链路
                            video.localPath = data.url;
                            if (data.audio_url) video.audioPath = data.audio_url;
                            self._playLocalExternal(video);
                        } else {
                            // ★ 2026-08-13 异步化：playOnlineVideo 后台线程启动转码流 → playReady 回调
                            self._startOnlineStream(data.url, video, data.audio_url);
                        }
                    } else if (data && data.need_auth) {
                        self._hideSpinner();  // 弹认证框接管界面，先收起转圈
                        self._showAuthDialog(data.site, video_id, video);
                    } else if (data && data.started) {
                        // ★ 异步解析中：结果完成后由 playUrlReady 回调继续
                        self._pendingPlay = { video: video };
                    } else {
                        var msg = (data && data.message) || '无法获取播放地址';
                        self._hideSpinner();
                        if (nowTitle) nowTitle.textContent = video.title || '';
                        if (typeof showToast === 'function') showToast(msg, 'error');
                    }
                } catch(e) {
                    self._hideSpinner();
                    if (nowTitle) nowTitle.textContent = video.title || '';
                    if (typeof showToast === 'function') showToast('解析视频地址失败', 'error');
                }
            }).catch(function(e) {
                console.warn('[videoApp] 解析视频地址失败:', e);
                self._hideSpinner();
                if (nowTitle) nowTitle.textContent = video.title || '';
                if (typeof showToast === 'function') showToast('解析视频地址失败，请重试或下载后播放', 'error');
            });
        } else {
            try {
                var data = (typeof p === 'string') ? JSON.parse(p) : p;
                if (data && data.ok && data.url) {
                    if (data.local) {
                        // ★ 本地兜底命中 → 走本地播放链路
                        video.localPath = data.url;
                        if (data.audio_url) video.audioPath = data.audio_url;
                        this._playLocalExternal(video);
                    } else {
                        this._doPlay(video, data.url, data.audio_url);
                    }
                } else if (data && data.need_auth) {
                    this._hideSpinner();  // 弹认证框接管界面，先收起转圈
                    this._showAuthDialog(data.site, video_id, video);
                } else if (data && data.started) {
                    // ★ 异步解析中：结果完成后由 playUrlReady 回调继续
                    this._pendingPlay = { video: video };
                } else {
                    this._hideSpinner();
                    if (nowTitle) nowTitle.textContent = video.title || '';
                    if (typeof showToast === 'function') showToast((data && data.message) || '无法获取播放地址', 'error');
                }
            } catch(e) {
                this._hideSpinner();
                if (nowTitle) nowTitle.textContent = video.title || '';
                if (typeof showToast === 'function') showToast('解析视频地址失败', 'error');
            }
        }
    },

    // ★ 在线 URL 异步解析完成回调（后端后台线程 → playUrlReady(video_id, data)）
    playUrlReady: function(video_id, data) {
        var self = this;
        console.log('[videoApp] playUrlReady', video_id, data);
        var pending = this._pendingPlay;
        var video = (pending && pending.video) || null;
        var nowTitle = document.getElementById('videoNowTitle');
        // 无待续项或 video_id 不匹配 → 过期回调，直接忽略
        if (!video || video.id !== video_id) return;

        if (data && data.ok && data.url) {
            if (data.local) {
                // ★ 本地兜底命中（DB 无 localPath 但磁盘有文件）→ 走本地播放链路
                video.localPath = data.url;
                if (data.audio_url) video.audioPath = data.audio_url;
                self._playLocalExternal(video);
            } else {
                // ★ 2026-08-14：后端解析补出的时长（DB 缺失时）透传给 video → _currentDuration 正确
                if (data.duration && data.duration > 0 && !(video.duration > 0)) {
                    video.duration = data.duration;
                }
                // ★ 2026-08-13 异步化：playOnlineVideo 后台线程启动转码流 → playReady 回调
                self._startOnlineStream(data.url, video, data.audio_url);
            }
        } else if (data && data.need_auth) {
            self._hideSpinner();  // 弹认证框接管界面，先收起转圈
            self._showAuthDialog(data.site, video_id, video);
        } else {
            self._pendingPlay = null;
            var msg = (data && data.message) || '无法获取播放地址';
            self._hideSpinner();
            if (nowTitle) nowTitle.textContent = video.title || '';
            if (typeof showToast === 'function') showToast(msg, 'error');
        }
    },

    // ★ 2026-08-13 启动在线转码流（playOnlineVideo 后台线程启动，完成后回调 playReady）
    _startOnlineStream: function(url, video, audioUrl) {
        var self = this;
        var nowTitle = document.getElementById('videoNowTitle');
        // ★ 2026-08-13 防御性修复：发起异步调用【前】同步置待续项，
        //   避免后端 playReady 先于 Promise 回调到达 → playReady 视作过期回调丢弃 → spinner 卡死。
        self._pendingPlay = { video: video };
        // ★ 2026-08-14 续播显式化：把上次位置传给后端（后端 start_pos==0 时仍会读库兜底）
        var lastPos = (video.lastPosition && video.lastPosition > 0) ? video.lastPosition : 0;
        var p2 = window.video_bridge.playOnlineVideo(url, video.id, lastPos, audioUrl || '');
        if (p2 && typeof p2.then === 'function') {
            p2.then(function(res) {
                var r = (typeof res === 'string') ? JSON.parse(res) : res;
                if (r && r.started) {
                    // 后台转码启动中 → 保持待续项（已同步置位），等待 playReady 回调
                    if (nowTitle) nowTitle.textContent = (video.title || '') + ' ⏳ 启动中...';
                } else if (r && r.ok && r.url) {
                    self._pendingPlay = null;
                    self._playStreamUrl(r.url, video);
                } else {
                    self._pendingPlay = null;
                    self._doPlay(video, url, audioUrl);
                }
            }).catch(function() {
                self._pendingPlay = null;
                self._doPlay(video, url, audioUrl);
            });
        } else if (p2) {
            var s = (typeof p2 === 'string') ? JSON.parse(p2) : p2;
            if (s && s.started) { self._pendingPlay = { video: video }; }
            else if (s && s.ok && s.url) { self._playStreamUrl(s.url, video); }
            else { self._doPlay(video, url, audioUrl); }
        } else {
            self._doPlay(video, url, audioUrl);
        }
    },

    // ★ 2026-08-13 后台播放流就绪回调（playLocalVideoNative/playLocalVideo/playOnlineVideo 完成）
    //   后台线程 → execute_js → 本函数在 GUI 线程执行
    playReady: function(video_id, data) {
        var self = this;
        console.log('[videoApp] playReady', video_id, data);
        var pending = this._pendingPlay;
        this._pendingPlay = null;
        var video = (pending && pending.video) || null;
        var nowTitle = document.getElementById('videoNowTitle');
        // 无待续项或 video_id 不匹配 → 过期回调（已切换视频），直接忽略
        if (!video || video.id !== video_id) return;
        if (data && data.ok && data.url) {
            var url = (data.mode === 'native') ? self._toMediaUrl(data.url) : data.url;
            if (data.mode === 'native') {
                console.log('[videoApp] ⚡ QWebEngine 原生直通播放:', url);
            }
            self._playStreamUrl(url, video);
        } else {
            var msg = (data && data.message) || '播放启动失败';
            self._hideSpinner();
            if (nowTitle) nowTitle.textContent = video.title || '';
            if (typeof showToast === 'function') showToast(msg, 'error');
        }
    },

    // ★ 2026-08-13 后台 seek 完成回调（seekVideo 后台线程重启转码 → seekReady）
    seekReady: function(video_id, data) {
        var self = this;
        if (!this._pendingSeek) return; // 过期 seek（已切换/重复拖放）→ 忽略
        this._pendingSeek = null;
        if (data && data.ok && data.url) {
            self._applySeekUrl(data.url);
        } else {
            if (typeof showToast === 'function') showToast((data && data.message) || '定位失败', 'error');
        }
    },

    // ===== ★ ffmpeg 解码帧 → Web 渲染 =====
    onFrame: function(b64) {
        try {
            if (!b64) return;
            this._ensureFrameUI();
            var imgEl = document.getElementById('videoFrameImg');
            if (!imgEl) return;
            imgEl.src = 'data:image/jpeg;base64,' + b64;
        } catch(e) {
            console.warn('[videoApp] onFrame 异常:', e);
        }
    },

    _ensureFrameUI: function() {
        var vEl = document.getElementById('videoPlayer');
        var imgEl = document.getElementById('videoFrameImg');
        var oldCv = document.getElementById('videoFrameCanvas');
        if (oldCv) oldCv.remove();
        var oldBar = document.getElementById('videoFrameBar');
        if (oldBar) oldBar.remove();

        if (!imgEl) {
            imgEl = document.createElement('img');
            imgEl.id = 'videoFrameImg';
            imgEl.style.position = 'fixed';
            imgEl.style.background = '#000';
            imgEl.style.objectFit = 'contain';
            imgEl.style.zIndex = '999998';
            imgEl.style.pointerEvents = 'none';
            document.body.appendChild(imgEl);
            this._frameImg = imgEl;
        }
        var NATIVE_CONTROLS_H = 48;
        var r = vEl ? vEl.getBoundingClientRect() : null;
        var left = (r && r.width > 0) ? r.left : 0;
        var top = (r && r.height > 0) ? r.top : 0;
        var w = (r && r.width > 0) ? r.width : 640;
        var h = (r && r.height > 0) ? r.height : 360;
        var drawH = Math.max(0, h - NATIVE_CONTROLS_H);
        imgEl.style.left = left + 'px';
        imgEl.style.top = top + 'px';
        imgEl.style.width = w + 'px';
        imgEl.style.height = drawH + 'px';

        if (vEl) {
            vEl.style.visibility = '';
            vEl.setAttribute('controls', '');
        }
    },

    // SVG 图标（播放/暂停/快退/快进/音量/全屏）
    _svgIcon: function(name) {
        var icons = {
            play: '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>',
            pause: '<svg viewBox="0 0 24 24"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>',
            back: '<svg viewBox="0 0 24 24"><path d="M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg>',
            fwd: '<svg viewBox="0 0 24 24"><path d="M12 5V1l5 5-5 5V7c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6h2c0 4.42-3.58 8-8 8s-8-3.58-8-8 3.58-8 8-8z"/></svg>',
            vol: '<svg viewBox="0 0 24 24"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>',
            full: '<svg viewBox="0 0 24 24"><path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/></svg>'
        };
        return icons[name] || icons.play;
    },

    _setProgressPct: function(val) {
        var prog = document.getElementById('vfProgress');
        if (prog) prog.style.setProperty('--progress-pct', val + '%');
    },

    toggleFullscreen: function() {
        var vEl = document.getElementById('videoPlayer');
        if (!vEl) return;
        if (!document.fullscreenElement) {
            if (vEl.requestFullscreen) vEl.requestFullscreen();
            else if (vEl.webkitRequestFullscreen) vEl.webkitRequestFullscreen();
        } else {
            if (document.exitFullscreen) document.exitFullscreen();
            else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
        }
    },

    _repositionFrameUI: function() {
        var vEl = document.getElementById('videoPlayer');
        var imgEl = document.getElementById('videoFrameImg');
        if (!vEl || !imgEl) return;
        var NATIVE_CONTROLS_H = 48;
        var r = vEl.getBoundingClientRect();
        if (!r || r.width <= 0) return;
        var left = r.left, top = r.top, w = r.width, h = r.height;
        var drawH = Math.max(0, h - NATIVE_CONTROLS_H);
        imgEl.style.left = left + 'px';
        imgEl.style.top = top + 'px';
        imgEl.style.width = w + 'px';
        imgEl.style.height = drawH + 'px';
    },

    _pollExternal: function() {
        try {
            if (!window.video_bridge) return;
            var self = this;
            var durP = window.video_bridge.getExternalDuration();
            var posP = window.video_bridge.getExternalPosition();
            var set = function(d, p) {
                if (typeof d === 'number') self._extDur = d;
                if (typeof p === 'number') self._extPos = p;
                var dur = self._extDur || 0;
                var pos = self._extPos || 0;
                var prog = document.getElementById('vfProgress');
                var time = document.getElementById('vfTime');
                if (prog && dur > 0) {
                    var pct = Math.min(100, (pos / dur) * 100);
                    prog.value = pct;
                    prog.style.setProperty('--progress-pct', pct + '%');
                }
                if (time) time.textContent = self._fmt(pos) + ' / ' + self._fmt(dur);
            };
            if (durP && typeof durP.then === 'function') {
                durP.then(function(d) { posP.then(function(p) { set(d, p); }); });
            } else {
                set(durP, posP);
            }
        } catch(e) {}
    },

    togglePlay: function() {
        try {
            if (!window.video_bridge) return;
            var btn = document.getElementById('vfPlay');
            if (btn && btn.getAttribute('data-state') === 'playing') {
                window.video_bridge.controlExternalPlayer('pause', '');
                this._setPlayIcon(btn, false);
            } else {
                window.video_bridge.controlExternalPlayer('resume', '');
                this._setPlayIcon(btn, true);
            }
        } catch(e) {}
    },

    _setPlayIcon: function(btn, isPlaying) {
        if (!btn) return;
        if (isPlaying) {
            btn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M6 5h4v14H6zM14 5h4v14h-4z"/></svg>';
            btn.setAttribute('data-state', 'playing');
        } else {
            btn.innerHTML = '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>';
            btn.setAttribute('data-state', 'paused');
        }
    },

    skip: function(delta) {
        try {
            if (!window.video_bridge) return;
            var dur = this._extDur || 0;
            var pos = this._extPos || 0;
            this.seekTo(Math.max(0, Math.min(dur || pos + delta, pos + delta)));
        } catch(e) {}
    },

    seekTo: function(sec) {
        try {
            if (!window.video_bridge) return;
            window.video_bridge.controlExternalPlayer('seek', sec.toString());
        } catch(e) {}
    },

    setExternalVolume: function(v) {
        try {
            if (!window.video_bridge) return;
            window.video_bridge.controlExternalPlayer('volume', v.toString());
        } catch(e) {}
    },

    _fmt: function(s) {
        s = Math.max(0, Math.floor(s || 0));
        var m = Math.floor(s / 60);
        var ss = s % 60;
        return (m < 10 ? '0' : '') + m + ':' + (ss < 10 ? '0' : '') + ss;
    },

    _playOnlineQt: function(url, video_id, audioUrl) {
        try {
            if (!url || !window.video_bridge || typeof window.video_bridge.playOnlineVideo !== 'function') return false;
            var pp = window.video_bridge.getLastPosition(video_id);
            if (pp && typeof pp.then === 'function') {
                pp.then(function(pos) {
                    try { window.video_bridge.playOnlineVideo(url, video_id, pos || 0); } catch(e) {}
                });
            } else {
                try { window.video_bridge.playOnlineVideo(url, video_id, pp || 0); } catch(e) {}
            }
            this._ensureCanvas();
            return true;
        } catch(e) {
            return false;
        }
    },

    _ensureCanvas: function() {
        var vEl = document.getElementById('videoPlayer');
        var cv = document.getElementById('videoFrameCanvas');
        if (!cv && vEl) {
            cv = document.createElement('canvas');
            cv.id = 'videoFrameCanvas';
            cv.style.cssText = 'position:absolute;left:0;top:0;width:100%;height:100%;background:#000;z-index:99;';
            vEl.appendChild(cv);
        }
        if (cv) {
            cv.style.display = 'block';
            cv.width = (vEl && vEl.clientWidth) || 640;
            cv.height = (vEl && vEl.clientHeight) || 360;
        }
    },

    // 已下载 → 本地播放
    _playLocalExternal: function(video) {
        var self = this;
        var video_id = video.id;
        this._currentVideoId = video_id;

        var nowTitle = document.getElementById('videoNowTitle');
        if (nowTitle) nowTitle.textContent = video.title || '';
        document.getElementById('videoNowMeta').textContent =
            (video.subject || '') + ' · ' + (video.grade || '') + ' · ' + (video.source || '');
        var link = document.getElementById('videoSourceLink');
        if (link) {
            link.style.display = video.pageUrl ? '' : 'none';
            link.setAttribute('data-url', video.pageUrl || '');
        }
        // ★ 播放次数由 _playStreamUrl 统一累加（此处不再重复累加，避免本地播放 double count）

        // 清理旧的 canvas/img 覆盖层（转码流由 <video> 自身内部渲染，无需覆盖层）
        var oldCv = document.getElementById('videoFrameCanvas');
        if (oldCv) oldCv.remove();
        var oldImg = document.getElementById('videoFrameImg');
        if (oldImg) oldImg.remove();

        var lastPos = video.lastPosition || 0;
        var audioPath = (video && video.audioPath) || '';

        // ★ 2026-08-13 异步化：playLocalVideoNative 后台线程一次性完成
        //   ①探测 QWebEngine 原生直通（VP8/VP9/Opus file:// 零转码）
        //   ②不支持时启动 ffmpeg 转码流
        //   完成后回调 playReady(video_id, {mode:'native'|'transcode', ok, url})。
        //   （此前同步 ffprobe 探测最坏阻塞 GUI ~15s）
        if (window.video_bridge && typeof window.video_bridge.playLocalVideoNative === 'function') {
            // ★ 2026-08-13 防御性修复：发起异步调用【前】同步置待续项（同 _startOnlineStream）
            self._pendingPlay = { video: video };
            var np = window.video_bridge.playLocalVideoNative(video.localPath, video_id, lastPos, audioPath);
            var _onNativeProbe = function(res) {
                var data = (typeof res === 'string') ? JSON.parse(res) : res;
                if (data && data.started) {
                    // 后台探测/转码启动中 → 保持待续项（已同步置位），等待 playReady 回调
                    if (nowTitle) nowTitle.textContent = (video.title || '') + ' ⏳ 启动中...';
                    return true;
                }
                if (data && data.ok && data.url) {
                    var url = (data.mode === 'native') ? self._toMediaUrl(data.url) : data.url;
                    if (data.mode === 'native') {
                        console.log('[videoApp] ⚡ QWebEngine 原生直通播放:', url);
                    }
                    self._playStreamUrl(url, video);
                    return true;
                }
                return false;
            };
            if (np && typeof np.then === 'function') {
                np.then(function(res) {
                    if (!_onNativeProbe(res)) self._playLocalTranscode(video, lastPos, audioPath);
                }).catch(function() {
                    self._playLocalTranscode(video, lastPos, audioPath);
                });
                return;
            } else if (np && _onNativeProbe(np)) {
                return;
            }
        }

        // 非原生支持（H.264/HEVC/AAC）→ ffmpeg 转码流 → <video> 内部渲染
        this._playLocalTranscode(video, lastPos, audioPath);
    },

    // 解码直渲兜底
    _playLocalDirect: function(video, lastPos, audioPath) {
        var self = this;
        var video_id = video.id;
        if (!window.video_bridge || typeof window.video_bridge.playDirect !== 'function') {
            this._playLocalTranscode(video, lastPos, audioPath);
            return;
        }
        var p = window.video_bridge.playDirect(video.localPath, video_id, lastPos || 0, audioPath || '');
        if (p && typeof p.then === 'function') {
            p.then(function(result) {
                if (result === 'ok') {
                    self._ensureFrameUI();
                    var nowTitle = document.getElementById('videoNowTitle');
                    if (nowTitle) nowTitle.textContent = video.title || '';
                    var meta = document.getElementById('videoNowMeta');
                    if (meta) meta.textContent =
                        (video.subject || '') + ' · ' + (video.grade || '') + ' · ' + (video.source || '');
                    self.refreshList();
                    self.startPositionSave(video_id);
                    console.log('[videoApp] ⚡ 解码直渲模式启动:', video.localPath);
                } else {
                    self._playLocalTranscode(video, lastPos, audioPath);
                }
            }).catch(function(e) {
                console.warn('[videoApp] 解码直渲异常，回退转码流:', e);
                self._playLocalTranscode(video, lastPos, audioPath);
            });
        } else if (p === 'ok') {
            self._ensureFrameUI();
            self.refreshList();
            self.startPositionSave(video_id);
        } else {
            this._playLocalTranscode(video, lastPos, audioPath);
        }
    },

    _hideNativeVideo: function() {
        var v = document.getElementById('videoPlayer');
        if (v) v.style.visibility = 'hidden';
    },

    _showNativeVideo: function() {
        var v = document.getElementById('videoPlayer');
        if (v) v.style.visibility = '';
    },

    // ffmpeg 转码流播放本地视频（异步：playLocalVideo 后台线程启动 → playReady 回调）
    _playLocalTranscode: function(video, lastPos, audioPath) {
        var self = this;
        var video_id = video.id;
        var p = window.video_bridge.playLocalVideo(video.localPath, video_id, lastPos, audioPath);
        if (p && typeof p.then === 'function') {
            p.then(function(res) {
                var r = (typeof res === 'string') ? JSON.parse(res) : res;
                if (r && r.started) {
                    // 后台转码启动中 → 等待 playReady 回调
                    self._pendingPlay = { video: video };
                } else if (r && r.ok && r.url) {
                    self._playStreamUrl(r.url, video);
                } else {
                    if (typeof showToast === 'function') showToast((r && r.message) || '转码播放失败', 'error');
                }
            }).catch(function(e) {
                console.warn('[videoApp] 本地播放失败:', e);
                if (typeof showToast === 'function') showToast('本地播放失败', 'error');
            });
        } else if (p) {
            this._playStreamUrl(p, video);
        } else {
            if (typeof showToast === 'function') showToast('播放器接口不可用', 'error');
        }
        this.refreshList();
    },

    // ===== ★ 播放错误诊断 =====
    _bindPlayerError: function(player, url) {
        try {
            if (player._errBound) return;
            player._errBound = true;
            var self = this;
            player.addEventListener('error', function() {
                // ★ 2026-08-13 出错 → 隐藏等待旋转动画（重试会重新显示）
                self._hideSpinner();
                var err = player.error;
                var code = err ? err.code : '?';
                var msg = err && err.message ? err.message : '未知错误';
                var MEDIA = {
                    1: 'MEDIA_ERR_ABORTED(取消失败)',
                    2: 'MEDIA_ERR_NETWORK(网络错误)',
                    3: 'MEDIA_ERR_DECODE(解码失败)',
                    4: 'MEDIA_ERR_SRC_NOT_SUPPORTED(源格式不支持)'
                };
                console.warn('[videoApp] ⚠️ <video> 播放错误:', MEDIA[code] || code, '|', msg);
                console.warn('[videoApp]   当前 src:', String(player.currentSrc || url || '').slice(0, 120));
                // ★ 2026-08-13 修复：在线播放转码流 Format error 自动重试 1 次
                //   根因：ffmpeg 首帧延迟长 / -ss 边界 / CDN 抖动 → Chromium 判定格式损坏
                //   重试后 ffmpeg 通常已缓存 CDN 数据，可成功解析
                // ★ 2026-08-13 增强：MEDIA_ERR_NETWORK（code 2，含 PIPELINE_ERROR_READ）同属
                //   瞬时网络/数据源抖动 → 同样自动重试 1 次（根因已修复，此重试为兜底）。
                if ((code === 4 || code === 2) && !player._retriedOnce) {
                    player._retriedOnce = true;
                    console.warn('[videoApp] 🔄 ' + (code === 4 ? 'SRC_NOT_SUPPORTED' : '网络错误') + '，3 秒后自动重试...');
                    // ★ 2026-08-13 定时器句柄存入 this._retryTimer，
                    //   新播放 / 切换视频时清除 → 避免过期重试打断新视频
                    if (self._retryTimer) clearTimeout(self._retryTimer);
                    self._retryTimer = setTimeout(function() {
                        self._retryTimer = null;
                        try {
                            if (self._currentVideoId) {
                                self.play(self._currentVideoId);
                            } else {
                                // 无 video_id → 重新加载当前 src
                                player.load();
                                self._awaitPlaySafe(player);
                            }
                        } catch(e) {}
                    }, 3000);
                    return; // 不提示 toast，等待重试结果
                }
                if (typeof showToast === 'function') {
                    if (code === 4) {
                        showToast('视频格式不受支持或转码流不可用，请尝试下载后播放', 'error');
                    } else if (code === 2 || code === 3) {
                        showToast('视频加载失败（网络或解码错误），请重试', 'error');
                    }
                }
            });
        } catch(e) {}
    },

    // ★ 2026-08 修复：从流 URL 解析后端实际起始位置（秒）
    //   转码/直通流 URL 携带 start=<秒>（回退 0 后为 0）或 seek=<秒> 参数
    //   返回实际起点；无参数返回 0
    _getStreamBasePos: function(url) {
        try {
            var u = String(url || '');
            var m = u.match(/[?&](?:start|seek)=(\d+)/);
            if (m) return parseInt(m[1]) || 0;
            return 0;
        } catch(e) { return 0; }
    },

    // ★ 把转码 HTTP 流 URL 交给原生 <video> 播放（内部渲染 + 原生 controls）
    // ★ 2026-08-13 修复：切换视频前显式释放旧源（解码器 + GPU 共享纹理）。
    //   直接 player.src = 新URL 会在旧纹理仍被显示合成器引用时销毁它，
    //   QtWebEngine/Chromium 输出大量 "invalid mailbox / non-existent mailbox"
    //   GL 报错（可能伴随黑帧/闪烁）。标准做法：先 pause → 清空 src → load()。
    //   注：pause() 会触发 savePosition()，正好把上一个视频的断点写入数据库。
    _releasePlayerSource: function(player) {
        if (!player) return;
        try { player.pause(); } catch(e) {}
        if (player.getAttribute('src') || player.currentSrc) {
            try {
                player.removeAttribute('src');
                player.load();
            } catch(e) {}
        }
    },

    _playStreamUrl: function(url, video) {
        var player = this._player;
        if (!player || !url) return;
        var video_id = video.id || '';
        this._currentVideo = video;
        // ★ 2026-08-14 在线完整流：复位待续 seek / 等待提示 / 稳定播放位置
        this._deferredSeek = null;
        if (this._deferredSeekTimer) { clearTimeout(this._deferredSeekTimer); this._deferredSeekTimer = null; }
        this._streamWaitBase = undefined;
        this._stablePos = 0;
        // ★ 2026-08 修复：从流 URL 解析后端实际起始位置（start/seek 参数）
        //   后端转码/直通流 URL 已携带 start=<秒>（回退 0 后为 0）
        //   前端基于它计算绝对播放位置 → 彻底解决位置累加
        //   （此前依赖 this._currentVideo.lastPosition，可能被错误累加
        //     → 每次播放位置越存越大 → 超过视频时长 → -ss 定位失败回退 → 循环）
        this._streamStartPos = this._getStreamBasePos(url);
        var fullDur = (video && video.duration && video.duration > 0) ? video.duration : 0;
        // 判断是否为 ffmpeg 转码 HTTP 流：后端已用 -ss 定位，前端从 0 播放、不重复 seek
        var isLiveStream = /^https?:\/\/127\.0\.0\.1/.test(url) || /^http:\/\/localhost/.test(url);
        // ★ 2026-08-13 修复：原生直通/缓存 webm 流（src=native）是【整文件全量提供】，
        //   currentTime 本身就是绝对位置（前端 seek 后），不能再叠加 _streamStartPos
        //   （否则 _absolutePosition/savePosition 变 231+231=462 → 超过时长 → 续播被重置回 0）。
        //   转码流（src=transcode）仍是「流从续播点开始、currentTime 从 0 起」，需叠加偏移。
        var isNative = /src=native/.test(url);
        var resumePos = this._streamStartPos;
        if (isNative) this._streamStartPos = 0;
        if (isLiveStream) {
            // ★ 2026-08 修复：进度条总时长 = 完整总时长（显示真实总时长）
            //   配合自绘控制条显示「绝对位置 / 完整总时长」
            this._currentDuration = fullDur;
        } else {
            // file:// 原生直通 / 普通 URL → 可正常 seek 到上次位置
            this._currentDuration = fullDur;
        }
        // ★ 2026-08-14 在线完整流标记（src=native = 从 0 转码、缓冲只增不减）
        this._onlineFullActive = !!isNative;
        // 播放区下方文字指示器「当前 / 总时长」（自绘条移除后此指示器无人更新，恢复绑定）
        this._bindNowProgressUpdate();
        this._bindPlayerError(player, url);
        if (!isLiveStream) {
            var pp = window.video_bridge.getLastPosition(video_id);
            var _doSeek = function(pos) { try { if (pos > 0) player.currentTime = pos; } catch(e) {} };
            if (pp && typeof pp.then === 'function') { pp.then(_doSeek); } else { _doSeek(pp || 0); }
        }
        // 移除旧 img/canvas 覆盖层
        var oldImg = document.getElementById('videoFrameImg');
        if (oldImg) oldImg.remove();
        var oldCv = document.getElementById('videoFrameCanvas');
        if (oldCv) oldCv.remove();
        // ★ 2026-08 修复：始终使用【原生 controls】（UI 与浏览器完全一致）
        //   自绘控制条无法 100% 复刻 Chromium 内部原生控件（Skia 绘制），
        //   因此统一使用浏览器原生 <video> controls
        var oldBar = document.getElementById('videoCustomBar');
        if (oldBar) oldBar.remove();
        // ★ 2026-08-13 修复双圈：_startPlay 已 _showSpinner()（等待中白圈 → controls 已摘除）。
        //   若此处无条件强制 controls=true，原生控件内建的加载黑圈会跟着出现 → 黑圈+白圈同时转。
        //   等待旋转期间保持 controls 摘除，真正开始播放(playing)时 _hideSpinner() 再恢复原生控件。
        var _spinnerEl = document.getElementById('videoSpinner');
        var _waiting = _spinnerEl && _spinnerEl.style.display !== 'none';
        if (_waiting) {
            player.removeAttribute('controls');
            player.controls = false;
        } else {
            player.setAttribute('controls', '');
            player.controls = true;
        }
        // ★ 2026-08-13 修复：先显式释放上一视频（避免快速切换时 GL mailbox 报错/黑帧）
        this._releasePlayerSource(player);
        // ★ 2026-08-13 修复：SRC_NOT_SUPPORTED 自动重试标记不在每次播放时重置
        //   （否则同一视频转码流报错时持续重试死循环）；只在 _startPlay 切换视频时重置。
        // ★ 2026-08-13 修复：清除未决的自动重试定时器 + 释放上一视频残留的 DASH 音频元素
        if (this._retryTimer) { clearTimeout(this._retryTimer); this._retryTimer = null; }
        this._stopAudioSync();
        player.src = url;
        player.load();
        var nowTitle = document.getElementById('videoNowTitle');
        if (nowTitle) nowTitle.textContent = video.title || '';
        document.getElementById('videoNowMeta').textContent =
            (video.subject || '') + ' · ' + (video.grade || '') + ' · ' + (video.source || '');
        var link = document.getElementById('videoSourceLink');
        if (link) { link.style.display = video.pageUrl ? '' : 'none'; link.setAttribute('data-url', video.pageUrl || ''); }
        try { window.video_bridge.incrementPlayCount(video_id); } catch(e) {}
        // ★ 2026-08-14 修复：在线完整流（src=native）续播/前拖。
        //   Chromium 媒体管道 seek 有 ~15s 超时：直接 currentTime=续播位置而转码未到
        //   → Range 请求挂起 → seek 超时 → 播放失败。故改为【轮询转码进度 → 数据就绪后
        //   才 seek】（Range 秒回，seek 瞬间完成），等待期标题提示「正在准备续播 XX:XX」。
        if (isNative) {
            if (resumePos > 0) {
                // ★ 2026-08-14 修复：续播等待期【保持旋转等待动画】不提前收起——
                //   转码从 0 需先追到续播点，spinner 持续旋转直到真正跳到续播位置
                //   开始播放（playing 事件自动收起，见 _player playing 监听）。
                //   若用户手动播放则 abortIfUserPlayed 放弃自动续播，改为从头看。
                this._deferSeek(player, resumePos, {
                    msg: '正在准备续播 ' + this._formatTime(resumePos),
                    abortIfUserPlayed: true
                });
            } else {
                this._awaitPlaySafe(player);
            }
            // 前拖守卫：用户拖进度条到未转码处 → 取消 + 排队等待（同样防 seek 超时）
            this._bindSeekGuard();
        } else {
            this._awaitPlaySafe(player);
        }
        this.startPositionSave(video_id);
        this.refreshList();
    },

    // ===== ★ 2026-08-14 在线完整流：转码进度等待 + 安全 seek =====
    // 背景：在线完整流（src=native）从 0 实时转码、缓冲只增不减；但 Chromium 媒体管道
    //   seek 有 ~15s 超时 → 直接 seek 到「未转码位置」会挂起超时报错。
    //   方案：先轮询桥 getStreamProgress（转码已推进的虚拟秒数），数据就绪后才 seek。
    _queryProgress: function(video_id, cb) {
        try {
            if (!window.video_bridge || typeof window.video_bridge.getStreamProgress !== 'function') {
                cb(0); return;
            }
            var p = window.video_bridge.getStreamProgress(video_id || '');
            var _apply = function(res) {
                var r = (typeof res === 'string') ? JSON.parse(res) : res;
                cb((r && typeof r.t === 'number') ? r.t : 0);
            };
            if (p && typeof p.then === 'function') p.then(_apply);
            else _apply(p);
        } catch(e) { cb(0); }
    },

    // 标题尾部等待提示（还原时恢复原标题）
    _showStreamWait: function(msg) {
        var el = document.getElementById('videoNowTitle');
        if (!el) return;
        if (this._streamWaitBase === undefined) this._streamWaitBase = el.textContent;
        el.textContent = this._streamWaitBase + ' ⏳ ' + msg + '…';
    },
    _clearStreamWait: function() {
        var el = document.getElementById('videoNowTitle');
        if (el && this._streamWaitBase !== undefined) el.textContent = this._streamWaitBase;
        this._streamWaitBase = undefined;
    },

    // ★ 续播/前拖统一处理：排队等待转码追到目标位置 → seek + 播放
    _deferSeek: function(player, target, opts) {
        var self = this;
        if (!player || !target || target <= 0) { this._awaitPlaySafe(player); return; }
        if (this._deferredSeek !== null && this._deferredSeek !== undefined) return;  // 已在排队
        opts = opts || {};
        var abortIfUserPlayed = !!opts.abortIfUserPlayed;
        this._deferredSeek = target;
        if (opts.msg) this._showStreamWait(opts.msg);
        else this._showStreamWait('正在转码到 ' + this._formatTime(target));
        // 取消当前 seek → 回到稳定位置（解除 Chromium seek 挂起，避免 ~15s 超时）
        try { player.currentTime = this._stablePos || 0; } catch(e) {}
        try { player.pause(); } catch(e) {}
        var startTs = Date.now();
        var _poll = function() {
            var cur = self._deferredSeek;
            if (cur === null || cur === undefined) { self._deferredSeekTimer = null; return; }
            // 用户已手动从头播放 → 放弃自动跳
            if (abortIfUserPlayed) {
                try {
                    if (player.currentTime > 0.5 && !player.paused) {
                        self._deferredSeek = null; self._deferredSeekTimer = null;
                        self._clearStreamWait(); return;
                    }
                } catch(e) {}
            }
            // 超时兜底（10 分钟，与后端 do_GET 预算一致）
            if (Date.now() - startTs > 600000) {
                self._deferredSeek = null; self._deferredSeekTimer = null;
                self._clearStreamWait();
                try { player.currentTime = cur; } catch(e) {}
                self._awaitPlaySafe(player);
                return;
            }
            // 元数据未就绪时先等（避免 readyState==0 时 seek 无效）
            try { if (player.readyState < 1) { self._deferredSeekTimer = setTimeout(_poll, 500); return; } } catch(e) {}
            self._queryProgress((self._currentVideo && self._currentVideo.id) || '', function(t) {
                var cur2 = self._deferredSeek;
                if (cur2 === null || cur2 === undefined) { self._deferredSeekTimer = null; return; }
                if (abortIfUserPlayed) {
                    try {
                        if (player.currentTime > 0.5 && !player.paused) {
                            self._deferredSeek = null; self._deferredSeekTimer = null;
                            self._clearStreamWait(); return;
                        }
                    } catch(e) {}
                }
                if (t >= cur2 + 2) {   // +2s 覆盖关键帧间隔与解析余量 → seek 秒回
                    self._deferredSeek = null; self._deferredSeekTimer = null;
                    self._clearStreamWait();
                    try { player.currentTime = cur2; } catch(e) {}
                    self._awaitPlaySafe(player);
                } else {
                    self._deferredSeekTimer = setTimeout(_poll, 1000);
                }
            });
        };
        this._deferredSeekTimer = setTimeout(_poll, 1000);
    },

    // 前拖守卫：拖动到未转码处 → 取消该 seek + 排队等待（就绪后自动 seek）
    _bindSeekGuard: function() {
        var self = this;
        if (this._seekGuardBound) return;
        this._seekGuardBound = true;
        var p = document.getElementById('videoPlayer');
        if (!p) return;
        p.addEventListener('timeupdate', function() {
            if (!self._onlineFullActive) return;
            try { self._stablePos = p.currentTime || 0; } catch(e) {}
        });
        p.addEventListener('seeking', function() {
            if (!self._onlineFullActive) return;
            if (self._deferredSeek !== null && self._deferredSeek !== undefined) return;  // 已在排队
            var target;
            try { target = p.currentTime || 0; } catch(e) { return; }
            self._queryProgress((self._currentVideo && self._currentVideo.id) || '', function(t) {
                if (!self._onlineFullActive) return;
                if (self._deferredSeek !== null && self._deferredSeek !== undefined) return;
                if (target > t + 2) self._deferSeek(p, target);
            });
        });
    },

    // 播放区下方文字指示器：「当前 / 总时长」（原生条外的独立文字，显示播放到哪里了）
    _bindNowProgressUpdate: function() {
        var self = this;
        if (this._nowProgressBound) return;
        this._nowProgressBound = true;
        var p = document.getElementById('videoPlayer');
        var el = document.getElementById('videoNowProgress');
        if (!p || !el) return;
        var _update = function() {
            var t = (p.currentTime || 0) + (self._streamStartPos || 0);
            var dur = self._currentDuration || (p.duration || 0);
            el.textContent = self._formatTime(t) + ' / ' + self._formatTime(dur);
        };
        p.addEventListener('timeupdate', _update);
        p.addEventListener('durationchange', _update);
        p.addEventListener('seeked', _update);
        _update();
    },

    // ===== ★ 自绘控制条（功能完整、外观贴近原生 Web 播放器）=====
    _ensureCustomControls: function() {
        var vEl = document.getElementById('videoPlayer');
        if (!vEl) return;
        if (document.getElementById('videoCustomBar')) {
            this._bindCustomTimeupdate();
            this._positionCustomBar();
            return;
        }
        var bar = document.createElement('div');
        bar.id = 'videoCustomBar';
        // ★ 2026-08 修复：控制条挂在视频容器内（position:absolute + bottom:0）
        //   → 视频缩放/移动时控制条自动跟随，真正一体（无需 JS 计算位置）
        bar.style.cssText =
            'position:absolute;left:0;right:0;bottom:0;height:48px;background:linear-gradient(transparent,rgba(0,0,0,0.85));' +
            'display:flex;align-items:center;gap:10px;padding:0 14px;z-index:100001;box-sizing:border-box;' +
            'pointer-events:auto;';
        bar.innerHTML =
            '<button id="videoCustomPlay" style="cursor:pointer;background:none;border:none;color:#fff;font-size:20px;width:28px" title="播放/暂停">⏸</button>' +
            '<span id="videoCustomCur" style="color:#fff;font-size:12px;white-space:nowrap">00:00</span>' +
            '<input id="videoCustomProgress" type="range" min="0" max="1000" value="0" style="flex:1;cursor:pointer;accent-color:#e74c3c">' +
            '<span id="videoCustomTotal" style="color:#ccc;font-size:12px;white-space:nowrap">00:00</span>' +
            '<button id="videoCustomMute" style="cursor:pointer;background:none;border:none;color:#fff;font-size:16px;width:24px" title="静音">🔊</button>' +
            '<input id="videoCustomVol" type="range" min="0" max="100" value="80" style="width:80px;cursor:pointer;accent-color:#e74c3c">' +
            '<button id="videoCustomFull" style="cursor:pointer;background:none;border:none;color:#fff;font-size:16px;width:24px" title="全屏">⛶</button>';
        // ★ 2026-08 修复：挂载到视频容器（#videoPlayerContainer）内 → 一体跟随
        var container = document.getElementById('videoPlayerContainer')
            || (vEl ? vEl.parentElement : null) || document.body;
        container.appendChild(bar);
        this._positionCustomBar();
        this._bindCustomBarResize();
        var totalEl = document.getElementById('videoCustomTotal');
        if (totalEl) totalEl.textContent = this._formatTime(this._currentDuration || 0);

        var self = this;
        bar.querySelector('#videoCustomProgress').addEventListener('change', function() {
            var ratio = this.value / 1000;
            var sec = Math.round((self._currentDuration || 1) * ratio);
            self._seekToSecond(sec);
        });
        bar.querySelector('#videoCustomProgress').addEventListener('input', function() {
            var ratio = this.value / 1000;
            var sec = Math.floor((self._currentDuration || 1) * ratio);
            var cEl = document.getElementById('videoCustomCur');
            if (cEl) cEl.textContent = self._formatTime(sec);
        });
        document.getElementById('videoCustomPlay').onclick = function() {
            if (self._player.paused) { self._player.play(); }
            else { self._player.pause(); }
        };
        document.getElementById('videoCustomMute').onclick = function() {
            self._player.muted = !self._player.muted;
            this.textContent = self._player.muted ? '🔇' : '🔊';
        };
        document.getElementById('videoCustomVol').onchange = function() {
            self._player.volume = this.value / 100;
            self._player.muted = (this.value == 0);
        };
        document.getElementById('videoCustomFull').onclick = function() {
            var p = self._player;
            if (p.requestFullscreen) p.requestFullscreen();
            else if (p.webkitRequestFullscreen) p.webkitRequestFullscreen();
        };
        self._player.addEventListener('pause', function() {
            var b = document.getElementById('videoCustomPlay'); if (b) b.textContent = '▶';
        });
        self._player.addEventListener('play', function() {
            var b = document.getElementById('videoCustomPlay'); if (b) b.textContent = '⏸';
        });
        this._bindCustomTimeupdate();
    },

    _bindCustomTimeupdate: function() {
        var self = this;
        if (this._customTickerBound) return;
        this._customTickerBound = true;
        this._player.addEventListener('timeupdate', function() {
            var dur = self._currentDuration || 0;  // 完整总时长（数据库值）
            // ★ 2026-08 修复：当前位置 = currentTime + 起始偏移（绝对时间线）
            //   显示「7:01 / 4:05」而不是「0:01 / 3:58」
            var cur = (this.currentTime || 0) + (self._streamStartPos || 0);
            var prog = document.getElementById('videoCustomProgress');
            var cEl = document.getElementById('videoCustomCur');
            if (prog && dur > 0) prog.value = Math.min(1000, (cur / dur) * 1000);
            if (cEl) cEl.textContent = self._formatTime(cur);
        });
    },

    _positionCustomBar: function() {
        var bar = document.getElementById('videoCustomBar');
        var vEl = document.getElementById('videoPlayer');
        // ★ 2026-08 修复：控制条已 absolute 挂载到容器内（left/right/bottom 自动跟随），
        //   此函数仅需保证 bar 存在时可见（无需 JS 定位）
        if (!bar) return;
        // 兜底：极少数情况 JS 未重新挂载，确保宽高跟随
        if (vEl && vEl.clientWidth > 0) {
            if (!bar.parentElement || !bar.parentElement.id) {
                var container = document.getElementById('videoPlayerContainer')
                    || (vEl ? vEl.parentElement : null) || document.body;
                container.appendChild(bar);
                bar.style.left = '0';
                bar.style.right = '0';
                bar.style.bottom = '0';
                bar.style.top = 'auto';
            }
        }
    },

    // ★ 2026-08 修复：窗口大小变化 / 视频元素尺寸变化时，自动重定位控制条
    _bindCustomBarResize: function() {
        var self = this;
        if (this._barResizeBound) return;
        this._barResizeBound = true;
        // 窗口 resize
        var _onResize = function() { self._positionCustomBar(); };
        if (window.addEventListener) window.addEventListener('resize', _onResize);
        // 视频元素尺寸变化（ResizeObserver 检测 #videoPlayer 的 box 变化）
        var vEl = document.getElementById('videoPlayer');
        if (vEl && typeof ResizeObserver === 'function') {
            try {
                var ro = new ResizeObserver(function() { self._positionCustomBar(); });
                ro.observe(vEl);
            } catch(e) {}
        } else {
            // 兜底：setInterval 定期刷新位置（不支持 ResizeObserver 时）
            if (!this._barResizeTimer) {
                this._barResizeTimer = setInterval(function() { self._positionCustomBar(); }, 500);
            }
        }
    },

    // ★ 拖放进度条 → 后端重启转码到新位置
    _seekToSecond: function(sec) {
        var self = this;
        if (!window.video_bridge || typeof window.video_bridge.seekVideo !== 'function') return;
        sec = Math.max(0, sec || 0);
        // ★ 2026-08 修复：自绘进度条基于完整总时长（245s）计算，
        //   sec 已是绝对位置（0~245），直接传给后端，不再重复加 _streamStartPos
        //   （旧的偏移逻辑是配合「剩余时长进度条」用的，现已废弃）
        // ★ 2026-08-13 异步化：seekVideo 后台线程重启转码（此前同步阻塞 GUI ~1-3s），
        //   完成后回调 seekReady(video_id, {ok, url}) 应用新 URL。
        //   连续拖放只保留最后一次（_pendingSeek 覆盖）
        this._pendingSeek = { video_id: this._currentVideoId || '' };
        var p = window.video_bridge.seekVideo(sec, this._currentVideoId || '');
        // 同步失败（异常）→ 清待续项
        if (p && typeof p.then === 'function') {
            p.then(function(res) {
                var r = (typeof res === 'string') ? JSON.parse(res) : res;
                if (r && r.started) return; // 等待 seekReady 回调
                self._pendingSeek = null;
                if (r && r.ok && r.url) self._applySeekUrl(r.url);
            }).catch(function() { self._pendingSeek = null; });
        } else if (p) {
            var s = (typeof p === 'string') ? JSON.parse(p) : p;
            if (s && s.started) return;
            self._pendingSeek = null;
            if (s && s.ok && s.url) self._applySeekUrl(s.url);
        } else {
            self._pendingSeek = null;
        }
    },

    // ★ 应用 seek 新流 URL（seekReady 回调与同步返回共用）
    _applySeekUrl: function(newUrl) {
        var self = this;
        if (!newUrl) return;
        // ★ 2026-08 修复：seek 返回的新 URL 携带 ?seek=<秒>，
        //   更新 _streamStartPos 为新起点（避免旧值导致位置偏离）
        self._streamStartPos = self._getStreamBasePos(newUrl);
        self._player.src = newUrl;
        self._player.load();
        self._awaitPlaySafe(self._player);
    },

    _doPlay: function(video, src, audioSrc) {
        var self = this;
        var video_id = video.id;
        var player = this._player;

        if (!src) {
            if (typeof showToast === 'function') showToast('该视频没有可用的播放地址', 'error');
            return;
        }
        console.log('[videoApp] 🎯 裸 URL 播放（回退路径），请确认浏览器可解码:', (src || '').slice(0, 100));
        this._bindPlayerError(player, src);
        var vTest = document.createElement('video');
        var canH264 = vTest.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"');
        var looksM4s = /\.m4s($|\?)/i.test(src);
        if (looksM4s || (!canH264 && /\.m4s|hevc|hvc1/i.test(src))) {
            console.warn('[videoApp] ⚠️ 该源疑似 m4s/HEVC 分离流，Chromium 可能无法直接解码，建议下载后播放');
        }
        if (audioSrc && audioSrc !== src) {
            this._setupAudioSync(video_id, audioSrc);
        } else if (this._audioEl) {
            this._stopAudioSync();
        }
        var nowTitle = document.getElementById('videoNowTitle');
        if (nowTitle) nowTitle.textContent = video.title || '';
        // ★ 2026-08-13 修复：先显式释放上一视频（避免快速切换时 GL mailbox 报错/黑帧）
        this._releasePlayerSource(player);
        // ★ 2026-08-13 修复：重试标记只在 _startPlay 切换视频时重置（防同一视频死循环重试）
        if (this._retryTimer) { clearTimeout(this._retryTimer); this._retryTimer = null; }
        player.src = src;
        var pp = window.video_bridge.getLastPosition(video_id);
        if (pp && typeof pp.then === 'function') {
            pp.then(function(pos) {
                try { player.currentTime = pos || 0; } catch(e) {}
            });
        } else {
            try { player.currentTime = pp || 0; } catch(e) {}
        }
        this._awaitPlaySafe(player);
        document.getElementById('videoNowTitle').textContent = video.title || '';
        document.getElementById('videoNowMeta').textContent =
            (video.subject || '') + ' · ' + (video.grade || '') + ' · ' + (video.source || '');
        var link = document.getElementById('videoSourceLink');
        if (link) {
            link.style.display = video.pageUrl ? '' : 'none';
            link.setAttribute('data-url', video.pageUrl || '');
        }
        try { window.video_bridge.incrementPlayCount(video_id); } catch(e) {}
        this.startPositionSave(video_id);
        this.refreshList();
    },

    _toMediaUrl: function(src) {
        if (!src) return src;
        if (/^[a-z][a-z0-9+.-]*:\/\//i.test(src)) return src;
        return 'file:///' + String(src).replace(/\\/g, '/').replace(/^\/+/, '');
    },

    _awaitPlaySafe: function(el) {
        var self = this;
        try {
            var p = el.play();
            if (p && typeof p.catch === 'function') {
                p.catch(function(e) {
                    var msg = (e && e.message) || String(e || '');
                    if (/interrupted by a new load request/i.test(msg)) return;
                    // ★ 2026-08-13 播放被拒（非换源打断）→ 隐藏等待旋转动画，避免卡在转圈
                    self._hideSpinner();
                    console.warn('[videoApp] 播放失败（自动忽略）:', msg);
                });
            }
        } catch(e) {}
    },

    // ===== ★ DASH 分离流：创建隐藏 <audio> 同步播放音频 =====
    _setupAudioSync: function(video_id, audioUrl) {
        var self = this;
        this._stopAudioSync();
        if (!audioUrl) return;

        var audio = document.createElement('audio');
        audio.src = audioUrl;
        audio.preload = 'auto';
        audio.style.display = 'none';
        audio.muted = false;
        audio.volume = 1;
        document.body.appendChild(audio);
        this._audioEl = audio;

        audio.addEventListener('error', function() {
            var errMsg = audio.error ? (audio.error.code + ':' + (audio.error.message || 'unknown')) : '未知错误';
            console.warn('[videoApp] 🔊 audio 加载失败:', errMsg);
        });

        var player = this._player;
        if (!player) return;

        audio.play().then(function() {
            if (player.paused) {
                self._awaitPlaySafe(player);
            }
        }).catch(function(e) {
            self._stopAudioSync();
            console.warn('[videoApp] 音频流不支持，仅播放画面:', e && e.message || e);
        });

        var onPause = function() { try { audio.pause(); } catch(e) {} };
        var onPlay = function() {
            try {
                self._awaitPlaySafe(audio);
                if (audio.currentTime != null && player.currentTime != null) {
                    audio.currentTime = player.currentTime;
                }
            } catch(e) {}
        };
        var onEnded = function() { self._stopAudioSync(); };

        player.addEventListener('pause', onPause);
        player.addEventListener('play', onPlay);
        player.addEventListener('ended', onEnded);
        this._audioSyncHandlers = { onPause: onPause, onPlay: onPlay, onEnded: onEnded };

        this._audioSyncTimer = setInterval(function() {
            try {
                if (audio.paused && !player.paused) self._awaitPlaySafe(audio);
                if (!audio.paused && !player.paused) {
                    var diff = Math.abs(audio.currentTime - player.currentTime);
                    if (diff > 1.5) audio.currentTime = player.currentTime;
                }
            } catch(e) {}
        }, 500);
    },

    _stopAudioSync: function() {
        if (this._audioSyncTimer) {
            clearInterval(this._audioSyncTimer);
            this._audioSyncTimer = null;
        }
        if (this._audioSyncHandlers) {
            var h = this._audioSyncHandlers;
            if (this._player) {
                this._player.removeEventListener('pause', h.onPause);
                this._player.removeEventListener('play', h.onPlay);
                this._player.removeEventListener('ended', h.onEnded);
            }
            this._audioSyncHandlers = null;
        }
        if (this._audioEl) {
            try { this._audioEl.pause(); } catch(e) {}
            try { this._audioEl.remove(); } catch(e) {}
            this._audioEl = null;
        }
    },

    // 计算"原始视频时间线"上的播放位置
    _absolutePosition: function() {
        var player = this._player;
        if (!player) return 0;
        try {
            var t = player.currentTime || 0;
            var url = player.currentSrc || player.src || '';
            var isLiveStream = /^https?:\/\/127\.0\.0\.1/.test(url) || /^http:\/\/localhost/.test(url);
            if (isLiveStream) {
                // ★ 2026-08 修复：使用后端流 URL 携带的实际起始位置 _streamStartPos
                //   （此前用 this._currentVideo.lastPosition，会被错误累加
                //     → 每次播放位置越存越大 → 超过视频时长 → -ss 定位失败回退 → 循环）
                var base = this._streamStartPos || 0;
                return t + base;
            }
            return t;
        } catch(e) { return 0; }
    },

    startPositionSave: function(video_id) {
        var self = this;
        if (this._positionSaveTimer) clearInterval(this._positionSaveTimer);
        this._positionSaveTimer = setInterval(function() {
            var player = self._player;
            if (player && !player.paused && !player.ended) {
                try {
                    window.video_bridge.updateLastPosition(video_id, Math.floor(self._absolutePosition()));
                } catch(e) {}
            }
        }, 5000);
    },

    savePosition: function() {
        if (this._positionSaveTimer) {
            clearInterval(this._positionSaveTimer);
            this._positionSaveTimer = null;
        }
        var player = this._player;
        if (this._currentVideoId && player) {
            try {
                window.video_bridge.updateLastPosition(this._currentVideoId, Math.floor(this._absolutePosition()));
            } catch(e) {}
        }
    },

    // ===== AI 控制指令入口 =====
    // ★ 2026-08-13 修复：只驱动当前生效的 HTML5 <video>（原生 controls + ffmpeg 转码流）。
    //   此前同时调用 controlExternalPlayer（FFmpegDecoder 直渲方法）：AI 暂停会杀掉正在播放的
    //   转码 ffmpeg 进程 → 流中断、resume 切到已废弃的直渲模式画面消失；seek 外部按绝对值
    //   处理而 AI 语义是相对秒数 → 双重执行。现统一走 HTML5 元素，行为与 AI 语义一致。
    control: function(payload) {
        var player = this._player;
        if (!player) return;
        switch (payload.action) {
            case 'play':
                if (payload.video_id) this.play(payload.video_id);
                else if (payload.url) {
                    player.src = payload.url;
                    if (payload.lastPosition) {
                        try { player.currentTime = payload.lastPosition; } catch(e) {}
                    }
                    this._awaitPlaySafe(player);
                } else if (player.src || player.currentSrc) {
                    // 暂停后续播（未带 video_id/url）
                    this._awaitPlaySafe(player);
                }
                break;
            case 'resume':
                if (player.src || player.currentSrc) this._awaitPlaySafe(player);
                break;
            case 'pause':
                player.pause();
                break;
            case 'stop':
                player.pause();
                try { player.currentTime = 0; } catch(e) {}
                break;
            case 'seek':
                // ★ AI seek 是相对秒数（正=快进，负=快退），相对当前播放位置累加并夹紧到 [0, 时长]
                var sec = parseInt(payload.seconds) || 0;
                try {
                    var dur = player.duration || 0;
                    var target = (player.currentTime || 0) + sec;
                    target = Math.max(0, target);
                    if (dur > 0) target = Math.min(dur, target);
                    player.currentTime = target;
                } catch(e) {}
                break;
            case 'volume':
                // ★ 2026-08-13 修复：volume 未提供时不动音量（此前 `|| 0` 会把默认音量静音）
                if (payload.volume === undefined || payload.volume === null || payload.volume === '') break;
                var vol = Math.max(0, Math.min(1, parseFloat(payload.volume) || 0));
                player.volume = vol;
                player.muted = (vol === 0);
                if (this._audioEl) {
                    this._audioEl.volume = vol;
                    this._audioEl.muted = (vol === 0);
                }
                break;
            case 'fullscreen':
                // ★ 2026-08-13 修复：已是全屏则退出，实现 toggle 语义
                if (document.fullscreenElement || document.webkitFullscreenElement) {
                    if (document.exitFullscreen) document.exitFullscreen();
                    else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
                } else if (player.requestFullscreen) {
                    player.requestFullscreen();
                } else if (player.webkitRequestFullscreen) {
                    player.webkitRequestFullscreen();
                }
                break;
        }
        // ★ 2026-08-13 修复：control() 不再无条件 refreshList()（拖进度条/调音量会触发列表重渲染，
        //   破坏拖放/闪烁；列表只在真正 play 时刷新）
    },

    // ===== 下载 =====
    download: function(video_id) {
        if (!window.video_bridge) return;
        try { window.video_bridge.downloadVideo(video_id); } catch(e) {}
    },

    remove: function(video_id) {
        if (!window.video_bridge) return;
        var videos = this._allVideos || [];
        var video = null;
        for (var i = 0; i < videos.length; i++) {
            if (videos[i].id === video_id) { video = videos[i]; break; }
        }
        this._deleteVideoId = video_id;
        var titleEl = document.getElementById('confirmVideoTitle');
        if (titleEl) titleEl.textContent = (video && video.title) ? '《' + video.title + '》' : '该视频';
        var modal = document.getElementById('videoConfirmModal');
        if (modal) modal.style.display = 'flex';
    },

    confirmDelete: function() {
        var modal = document.getElementById('videoConfirmModal');
        if (modal) modal.style.display = 'none';
        if (this._deleteVideoId) {
            try { window.video_bridge.deleteVideo(this._deleteVideoId); } catch(e) {}
            this._deleteVideoId = null;
        }
        this.refreshList();
    },

    cancelDelete: function() {
        var modal = document.getElementById('videoConfirmModal');
        if (modal) modal.style.display = 'none';
        this._deleteVideoId = null;
    },

    _showAuthDialog: function(site, video_id, video) {
        this._authVideoId = video_id;
        this._authVideo = video || null;
        var modal = document.getElementById('videoAuthModal');
        var siteEl = document.getElementById('authSiteName');
        if (siteEl) siteEl.textContent = site || '未知网站';
        if (modal) modal.style.display = 'flex';
        var input = document.getElementById('authInput');
        if (input) input.value = '';
    },

    confirmAuth: function() {
        var self = this;
        var modal = document.getElementById('videoAuthModal');
        var siteEl = document.getElementById('authSiteName');
        var input = document.getElementById('authInput');
        var site = (siteEl && siteEl.textContent) || '';
        var raw = (input && input.value || '').trim();
        if (!raw) {
            if (typeof showToast === 'function') showToast('请输入 Cookie / Token 认证信息', 'error');
            return;
        }
        if (modal) modal.style.display = 'none';
        var authInfo = JSON.stringify({ type: 'cookies', cookies: raw, user_agent: navigator.userAgent || '' });
        if (!window.video_bridge || typeof window.video_bridge.saveSiteAuth !== 'function') {
            if (typeof showToast === 'function') showToast('认证保存接口不可用', 'error');
            return;
        }
        var p = window.video_bridge.saveSiteAuth(site, authInfo);
        if (p && typeof p.then === 'function') {
            p.then(function(result) {
                try {
                    var data = (typeof result === 'string') ? JSON.parse(result) : result;
                    if (data && data.ok) {
                        if (typeof showToast === 'function') showToast('✅ 认证信息已保存，正在重新播放...', 'success');
                        if (self._authVideo) {
                            self._startPlay(self._authVideo);
                        } else if (self._authVideoId) {
                            self.play(self._authVideoId);
                        }
                    } else {
                        if (typeof showToast === 'function') showToast('❌ ' + ((data && data.message) || '保存失败'), 'error');
                    }
                } catch(e) {}
            }).catch(function(e) {
                console.warn('[videoApp] 保存认证失败:', e);
                if (typeof showToast === 'function') showToast('保存认证失败', 'error');
            });
        }
    },

    closeAuth: function() {
        var modal = document.getElementById('videoAuthModal');
        if (modal) modal.style.display = 'none';
        this._authVideoId = null;
        this._authVideo = null;
    },

    // ===== 搜索 =====
    search: function() {
        var self = this;
        var kw = (document.getElementById('videoSearchInput').value || '').trim();
        // ★ 2026-08-14 多源搜索：把来源下拉当前值传给后端（''=全部/B站/智慧教育平台/优酷）
        var srcSel = document.getElementById('videoSourceFilter');
        var source = srcSel ? srcSel.value : '';
        if (kw && window.video_bridge && typeof window.video_bridge.searchOnline === 'function') {
            var p = window.video_bridge.searchOnline(kw, source);
            if (p && typeof p.then === 'function') {
                p.then(function(result) {
                    try {
                        var data = (typeof result === 'string') ? JSON.parse(result) : result;
                        // ★ 异步搜索：结果完成后由 searchDone 回调提示并刷新列表
                        if (data && data.started) {
                            if (typeof showToast === 'function') {
                                showToast('⏳ ' + ((data.message) || '正在搜索...'), 'info');
                            }
                            return;
                        }
                        if (typeof showToast === 'function') {
                            if (data && data.ok) {
                                var _skipped = data.skipped || 0;
                                showToast('✅ 搜索到 ' + data.total + ' 个视频，新增 ' + data.added + ' 个'
                                    + (_skipped ? '（重复 ' + _skipped + ' 个已跳过）' : ''), 'success');
                            } else {
                                showToast('❌ ' + ((data && data.message) || '搜索失败'), 'error');
                            }
                        }
                    } catch(e) {}
                    self._resetSourceFilterAndRefresh();
                }).catch(function(e) {
                    console.warn('[videoApp] 网络搜索失败:', e);
                    self._resetSourceFilterAndRefresh();
                });
                return;
            }
        }
        this.refreshList();
    },

    // ★ 异步搜索结果回调（后端后台线程完成搜索后调用）
    searchDone: function(data) {
        try {
            if (typeof showToast === 'function') {
                if (data && data.ok) {
                    var _skipped = data.skipped || 0;
                    showToast('✅ 搜索到 ' + data.total + ' 个视频，新增 ' + data.added + ' 个'
                        + (_skipped ? '（重复 ' + _skipped + ' 个已跳过）' : ''), 'success');
                } else {
                    showToast('❌ ' + ((data && data.message) || '搜索失败'), 'error');
                }
            }
        } catch(e) {}
        this._resetSourceFilterAndRefresh();
    },

    // ★ 2026-08-14 搜索后把来源筛选重置为"全部"，避免结果被自身来源筛选过滤掉
    _resetSourceFilterAndRefresh: function() {
        var sel = document.getElementById('videoSourceFilter');
        if (sel) sel.value = '';
        this.refreshList();
    },

    openSourceLink: function() {
        var link = document.getElementById('videoSourceLink');
        if (link && link.getAttribute('data-url')) {
            var url = link.getAttribute('data-url');
            if (window.mcp_bridge && window.mcp_bridge.openExternalUrl) {
                try { window.mcp_bridge.openExternalUrl(url); } catch(e) {}
            } else if (window.py_bridge && window.py_bridge.openExternalUrl) {
                try { window.py_bridge.openExternalUrl(url); } catch(e) {}
            }
        }
    },

    // ===== 工具 =====
    _formatTime: function(sec) {
        if (!sec || sec <= 0) return '00:00';
        var m = Math.floor(sec / 60);
        var s = Math.floor(sec % 60);
        return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
    }
};

document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() { window.videoApp.init(); }, 300);
});
if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(function() { window.videoApp.init(); }, 300);
}