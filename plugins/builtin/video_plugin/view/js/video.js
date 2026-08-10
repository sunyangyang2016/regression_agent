// ============================================
// 视频中心 - 播放/列表/断点续播/5秒保存/AI控制
// 注意：QWebChannel bridge 调用是异步的，返回 Promise，需用 .then() 取值
// ============================================
window.videoApp = {
    _currentVideoId: null,
    _positionSaveTimer: null,
    _player: null,
    _allVideos: [],

    // ===== 初始化 =====
    init: function() {
        var self = this;
        this._player = document.getElementById('videoPlayer');
        if (!this._player) return;

        // 播放器事件
        this._player.addEventListener('pause', function() { self.savePosition(); });
        this._player.addEventListener('ended', function() { self.savePosition(); });
        this._player.addEventListener('timeupdate', function() {
            var el = document.getElementById('videoNowProgress');
            if (el) {
                el.textContent = self._formatTime(this.currentTime) + ' / ' +
                    self._formatTime(this.duration || 0);
            }
        });

        this.refreshList();
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
        // QWebChannel 调用返回 Promise → 用 .then() 接收结果
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
            // 兜底：万一某些环境下同步返回
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
        var countEl = document.getElementById('videoCount');
        if (!container) return;

        var videos = this._allVideos || [];
        if (videos.length === 0) {
            container.innerHTML = '<div class="video-empty">🎬 暂无视频<br>请让 AI 搜索教学视频</div>';
            if (countEl) countEl.textContent = '0 个视频';
            return;
        }
        if (countEl) countEl.textContent = videos.length + ' 个视频';

        var html = videos.map(function(v) {
            // 状态标签和操作
            var statusHtml = '';
            var actions = '';
            if (v.status === 'downloaded') {
                statusHtml = '<span class="video-status downloaded">✓ 已下载</span>';
                actions = '<button class="video-btn" title="删除" onclick="event.stopPropagation();window.videoApp.remove(\'' +
                    v.id + '\')"><i class="fas fa-trash"></i></button>';
            } else if (v.status === 'downloading') {
                statusHtml = '<span class="video-status downloading">⏳ 下载中 ' +
                    (v.downloadProgress || 0) + '%</span>';
            } else if (v.status === 'failed') {
                statusHtml = '<span class="video-status failed">✗ 下载失败</span>';
                actions = '<button class="video-btn" title="重新下载" onclick="event.stopPropagation();window.videoApp.download(\'' +
                    v.id + '\')"><i class="fas fa-redo"></i></button>';
            } else {
                statusHtml = '<span class="video-status online">在线</span>';
                actions = '<button class="video-btn" title="下载" onclick="event.stopPropagation();window.videoApp.download(\'' +
                    v.id + '\')"><i class="fas fa-download"></i></button>';
            }
            actions += '<button class="video-btn" title="播放" onclick="event.stopPropagation();window.videoApp.play(\'' +
                v.id + '\')"><i class="fas fa-play"></i></button>';

            // 封面图
            var thumb = v.thumbnail
                ? '<img src="' + v.thumbnail + '" class="video-thumb" onerror="this.outerHTML=window.videoApp._thumbFallback()">'
                : window.videoApp._thumbFallback();

            // 续播提示
            var resume = (v.lastPosition && v.lastPosition > 0)
                ? '<div class="video-resume">⏺ 上次播到 ' + window.videoApp._formatTime(v.lastPosition) + '</div>'
                : '';

            return '<div class="video-item' + (v.id === window.videoApp._currentVideoId ? ' active' : '') + '"' +
                ' onclick="window.videoApp.play(\'' + v.id + '\')">' +
                thumb +
                '<div class="video-item-info">' +
                    '<div class="video-item-title" title="' + v.title + '">' + v.title + '</div>' +
                    '<div class="video-item-meta">' +
                        '<i class="fas fa-book"></i> ' + (v.subject || '未知') +
                        ' · ' + (v.grade || '未知') +
                        ' · ' + (v.source || '未知') +
                        '<span style="margin-left:6px;">⏱ ' + window.videoApp._formatTime(v.duration || 0) + '</span>' +
                        (v.quality ? ' · ' + v.quality : '') +
                    '</div>' +
                    resume +
                    '<div class="video-item-actions">' + statusHtml + actions + '</div>' +
                '</div>' +
            '</div>';
        }).join('');

        container.innerHTML = html;
    },

    _thumbFallback: function() {
        return '<div class="video-thumb video-thumb-fallback"><i class="fas fa-play-circle"></i></div>';
    },

    // ===== 播放（断点续播）=====
    play: function(video_id) {
        var self = this;
        var videos = this._allVideos || [];
        var video = null;
        for (var i = 0; i < videos.length; i++) {
            if (videos[i].id === video_id) { video = videos[i]; break; }
        }
        if (!video) {
            // 可能筛选后不在当前列表，异步查数据库
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

    // 真正开始播放（含断点续播异步获取）
    _startPlay: function(video) {
        var self = this;
        var video_id = video.id;
        this._currentVideoId = video_id;
        var player = this._player;

        // 设置播放源（本地优先）
        var src = video.localPath || video.playUrl;
        if (!src) {
            if (typeof showToast === 'function') showToast('该视频没有可用的播放地址', 'error');
            return;
        }
        player.src = src;

        // ★ 断点续播（异步取位置）
        var pp = window.video_bridge.getLastPosition(video_id);
        if (pp && typeof pp.then === 'function') {
            pp.then(function(pos) {
                try { player.currentTime = pos || 0; } catch(e) {}
            });
        } else {
            try { player.currentTime = pp || 0; } catch(e) {}
        }

        player.play();

        // 更新"当前播放"信息
        document.getElementById('videoNowTitle').textContent = video.title || '';
        document.getElementById('videoNowMeta').textContent =
            (video.subject || '') + ' · ' + (video.grade || '') + ' · ' +
            (video.source || '');
        var link = document.getElementById('videoSourceLink');
        if (link) {
            link.style.display = video.pageUrl ? '' : 'none';
            link.setAttribute('data-url', video.pageUrl || '');
        }

        // 播放次数 +1（无需返回值）
        try { window.video_bridge.incrementPlayCount(video_id); } catch(e) {}

        // 启动 5 秒自动保存
        this.startPositionSave(video_id);

        // 刷新列表高亮
        this.refreshList();
    },

    // ===== ★ 每 5 秒自动保存播放位置 =====
    startPositionSave: function(video_id) {
        var self = this;
        if (this._positionSaveTimer) clearInterval(this._positionSaveTimer);
        this._positionSaveTimer = setInterval(function() {
            var player = self._player;
            if (player && !player.paused && !player.ended) {
                try {
                    window.video_bridge.updateLastPosition(
                        video_id, Math.floor(player.currentTime)
                    );
                } catch(e) {}
            }
        }, 5000);
    },

    // ===== 保存当前播放位置 =====
    savePosition: function() {
        if (this._positionSaveTimer) {
            clearInterval(this._positionSaveTimer);
            this._positionSaveTimer = null;
        }
        var player = this._player;
        if (this._currentVideoId && player) {
            try {
                window.video_bridge.updateLastPosition(
                    this._currentVideoId, Math.floor(player.currentTime)
                );
            } catch(e) {}
        }
    },

    // ===== AI 控制指令入口 =====
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
                    player.play();
                }
                break;
            case 'pause':
                player.pause();
                break;
            case 'stop':
                player.pause();
                try { player.currentTime = 0; } catch(e) {}
                break;
            case 'seek':
                var sec = parseInt(payload.seconds) || 0;
                try { player.currentTime += sec; } catch(e) {}
                break;
            case 'volume':
                var vol = Math.max(0, Math.min(1, parseFloat(payload.volume) || 0));
                player.volume = vol;
                break;
            case 'fullscreen':
                if (player.requestFullscreen) player.requestFullscreen();
                else if (player.webkitRequestFullscreen) player.webkitRequestFullscreen();
                break;
        }
        // 更新列表高亮
        this.refreshList();
    },

    // ===== 下载（无需返回值）=====
    download: function(video_id) {
        if (!window.video_bridge) return;
        try { window.video_bridge.downloadVideo(video_id); } catch(e) {}
    },

    // ===== 删除（无需返回值）=====
    remove: function(video_id) {
        if (!window.video_bridge) return;
        if (confirm('确定删除该视频？')) {
            try { window.video_bridge.deleteVideo(video_id); } catch(e) {}
        }
    },

    // ===== 搜索（先网络搜索 → 再刷新列表）=====
    search: function() {
        var self = this;
        var kw = (document.getElementById('videoSearchInput').value || '').trim();

        // 有关键词 → 先调后端网络搜索写入视频库（异步）
        if (kw && window.video_bridge && typeof window.video_bridge.searchOnline === 'function') {
            var p = window.video_bridge.searchOnline(kw);
            if (p && typeof p.then === 'function') {
                p.then(function(result) {
                    try {
                        var data = (typeof result === 'string') ? JSON.parse(result) : result;
                        if (typeof showToast === 'function') {
                            if (data && data.ok) {
                                showToast('✅ 搜索到 ' + data.total + ' 个视频，新增 ' + data.added + ' 个', 'success');
                            } else {
                                showToast('❌ ' + ((data && data.message) || '搜索失败'), 'error');
                            }
                        }
                    } catch(e) {}
                    self.refreshList();
                }).catch(function(e) {
                    console.warn('[videoApp] 网络搜索失败:', e);
                    self.refreshList();
                });
                return;
            } else {
                // 同步兜底
                try {
                    var result = p;
                    if (result && typeof result === 'string') {
                        var data = JSON.parse(result);
                        if (typeof showToast === 'function') {
                            if (data && data.ok) {
                                showToast('✅ 搜索到 ' + data.total + ' 个视频，新增 ' + data.added + ' 个', 'success');
                            } else {
                                showToast('❌ ' + ((data && data.message) || '搜索失败'), 'error');
                            }
                        }
                    }
                } catch(e) {
                    console.warn('[videoApp] 网络搜索失败:', e);
                }
            }
        }
        // 刷新列表（网络搜索后 / 或仅筛选）
        this.refreshList();
    },

    // ===== 打开源链接 =====
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

// 初始化
document.addEventListener('DOMContentLoaded', function() {
    setTimeout(function() {
        window.videoApp.init();
    }, 300);
});
// 若插件注入时 DOM 已就绪
if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(function() { window.videoApp.init(); }, 300);
}