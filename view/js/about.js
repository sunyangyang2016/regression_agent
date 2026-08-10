// ============================================
// About - 关于面板
// ============================================

function renderAbout() {
    console.log('[About] renderAbout called');
    var aboutBody = document.getElementById('tabAbout');
    if (!aboutBody) { console.warn('[About] tabAbout not found'); return; }

    // 先渲染占位内容，再异步从后端获取 agent_info
    aboutBody.innerHTML = '<div class="about-section">' +
        '<span class="about-logo">⚡</span>' +
        '<div class="about-title" id="aboutName">Regression Agent</div>' +
        '<div class="about-version" id="aboutVersion">版本 ...</div>' +
        '<div class="about-release" id="aboutRelease">加载中...</div>' +
        '<hr class="about-divider">' +
        '<div class="about-info-grid">' +
            '<div class="about-info-item"><div class="label">软件版本</div><div class="value" id="aboutVersionItem">...</div></div>' +
            '<div class="about-info-item"><div class="label">发布日期</div><div class="value" id="aboutReleaseItem">...</div></div>' +
            '<div class="about-info-item"><div class="label">作者</div><div class="value" id="aboutAuthor">...</div></div>' +
            '<div class="about-info-item"><div class="label">许可证</div><div class="value" id="aboutLicense">...</div></div>' +
            '<div class="about-info-item" id="aboutGitHubRow"><div class="label">GitHub</div><div class="value" id="aboutGitHub">...</div></div>' +
            '<div class="about-info-item" id="aboutDocsRow"><div class="label">文档</div><div class="value" id="aboutDocs">...</div></div>' +
        '</div>' +
        '<hr class="about-divider">' +
        '<div class="about-description" id="aboutDescription"><strong>📖 关于 Regression Agent</strong><br><br>加载中...</div>' +
        '<hr class="about-divider">' +
        '<div class="about-credits" id="aboutCredits"><div style="font-weight:600;margin-bottom:8px;">👥 贡献者</div><div>加载中...</div></div>' +
        '<div class="about-tech-stack" id="aboutTechStack"><span class="tech-tag">加载中...</span></div>' +
        '<hr class="about-divider">' +
        '<div style="text-align:center;font-size:13px;color:var(--text-muted);" id="aboutCopyright"></div>' +
        '<div class="about-actions">' +
            '<button onclick="showToast(\'检查更新中...\',\'info\')"><i class="fas fa-sync"></i> 检查更新</button>' +
            '<button onclick="showToast(\'日志已导出\',\'success\')"><i class="fas fa-file-export"></i> 导出日志</button>' +
            '<button class="primary" onclick="showToast(\'✅ 系统运行正常\',\'success\')"><i class="fas fa-check-circle"></i> 系统状态</button>' +
        '</div></div>';

    if (window.config_bridge && typeof window.config_bridge.getAgentInfo === 'function') {
        try {
            var p = window.config_bridge.getAgentInfo();
            if (p && typeof p.then === 'function') {
                p.then(function(dataStr) {
                    try {
                        var info = JSON.parse(dataStr);
                        applyAgentInfo(info);
                    } catch(e2) { console.warn('[About] 解析 agent_info 失败:', e2); }
                });
            } else if (typeof p === 'string') {
                try {
                    var info = JSON.parse(p);
                    applyAgentInfo(info);
                } catch(e2) { console.warn('[About] 解析 agent_info 失败:', e2); }
            }
        } catch(e) { console.warn('[About] getAgentInfo 调用失败:', e); }
    }

    // 强制重绘（参考单文件版本解决QWebEngine渲染问题）
    aboutBody.style.display = 'none';
    void aboutBody.offsetHeight;
    aboutBody.style.display = 'block';
}

function applyAgentInfo(info) {
    if (!info) return;
    var name = info.name || 'Regression Agent';
    var version = info.version || '';
    var releaseDate = info.releaseDate || '';
    var author = info.author || '';
    var license = info.license || '';
    var github = info.github || '';
    var docs = info.docs || '';
    var description = info.description || '';
    var features = info.features || [];
    var contributors = info.contributors || [];
    var techStack = info.techStack || [];
    var copyright = info.copyright || '';

    var setText = function(id, text) { var el = document.getElementById(id); if (el) el.textContent = text; };

    setText('aboutName', name);
    setText('aboutVersion', '版本 ' + version);
    setText('aboutRelease', '发布日期: ' + releaseDate);
    setText('aboutVersionItem', version);
    setText('aboutReleaseItem', releaseDate);
    setText('aboutAuthor', author);
    setText('aboutLicense', license);

    var gitEl = document.getElementById('aboutGitHub');
    if (gitEl && github) {
        gitEl.innerHTML = '<a href="' + github + '" target="_blank" onclick="event.preventDefault();window.mcp_bridge && window.mcp_bridge.openExternalUrl(\'' + github + '\');">' + github.replace('https://', '') + '</a>';
    }

    var docsEl = document.getElementById('aboutDocs');
    if (docsEl && docs) {
        docsEl.innerHTML = '<a href="#" onclick="showToast(\'文档: ' + docs + '\',\'info\')">' + docs + '</a>';
    }

    var descEl = document.getElementById('aboutDescription');
    if (descEl) {
        var featureHtml = (features && features.length > 0)
            ? '主要特性：<ul style="padding-left:20px;margin:8px 0;">' + features.map(function(f) { return '<li>' + f + '</li>'; }).join('') + '</ul>'
            : '';
        descEl.innerHTML = '<strong>📖 关于 ' + name + '</strong><br><br>' + (description || '') + '<br><br>' + featureHtml;
    }

    var creditsEl = document.getElementById('aboutCredits');
    if (creditsEl) {
        var creditHtml = '<div style="font-weight:600;margin-bottom:8px;">👥 贡献者</div>';
        if (contributors && contributors.length > 0) {
            creditHtml += contributors.map(function(c) {
                return '<div class="credit-item"><span>' + (c.role || '') + '</span><span>' + (c.name || '') + '</span></div>';
            }).join('');
        }
        creditsEl.innerHTML = creditHtml;
    }

    var techEl = document.getElementById('aboutTechStack');
    if (techEl) {
        techEl.innerHTML = (techStack && techStack.length > 0)
            ? techStack.map(function(t) { return '<span class="tech-tag">' + t + '</span>'; }).join('')
            : '';
    }

    var copyEl = document.getElementById('aboutCopyright');
    if (copyEl) {
        copyEl.textContent = copyright + ' Made with ❤️ and ☕';
    }
}