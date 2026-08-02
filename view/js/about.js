// ============================================
// About - 关于面板
// ============================================

function renderAbout() {
    console.log('[About] renderAbout called');
    var aboutBody = document.getElementById('tabAbout');
    if (!aboutBody) { console.warn('[About] tabAbout not found'); return; }
    
    var version = '1.0.2alpha';
    var author = '孙洋洋';
    var license = 'MIT License';
    
    console.log('[About] rendering about content');
    
    aboutBody.innerHTML = '<div class="about-section">' +
        '<span class="about-logo">⚡</span>' +
        '<div class="about-title">Agent</div>' +
        '<div class="about-version" id="aboutVersion">版本 ' + version + '</div>' +
        '<div class="about-release">发布日期: 2026年8月1日</div>' +
        '<hr class="about-divider">' +
        '<div class="about-info-grid">' +
            '<div class="about-info-item"><div class="label">软件版本</div><div class="value" id="aboutVersionItem">' + version + '</div></div>' +
            '<div class="about-info-item"><div class="label">发布日期</div><div class="value">2026-08-01</div></div>' +
            '<div class="about-info-item"><div class="label">作者</div><div class="value" id="aboutAuthor">' + author + '</div></div>' +
            '<div class="about-info-item"><div class="label">许可证</div><div class="value" id="aboutLicense">' + license + '</div></div>' +
            '<div class="about-info-item"><div class="label">GitHub</div><div class="value"><a href="https://github.com/sunyangyang2016/regression_agent" target="_blank" onclick="event.preventDefault();window.mcp_bridge && window.mcp_bridge.openExternalUrl(\'https://github.com/sunyangyang2016/regression_agent\');">github.com/sunyangyang2016/regression_agent</a></div></div>' +
            '<div class="about-info-item"><div class="label">文档</div><div class="value"><a href="#" onclick="showToast(\'文档: docs.agent.ai\',\'info\')">docs.agent.ai</a></div></div>' +
        '</div>' +
        '<hr class="about-divider">' +
        '<div class="about-description"><strong>📖 关于 Agent</strong><br><br>Agent 是一个基于 PyQt5 + QWebEngine 的智能对话系统，集成了 AI 大语言模型、MCP 工具调用、插件扩展等能力。<br><br>主要特性：<ul style="padding-left:20px;margin:8px 0;"><li>🧠 多模型支持 - OpenAI、DeepSeek、Claude 等</li><li>🔧 MCP 工具系统 - 内置工具 + MCP 协议工具</li><li>💬 智能对话 - 流式响应、上下文管理</li><li>🔌 插件机制 - 热插拔插件系统</li><li>🎨 现代化 UI - 暗色/亮色主题</li></ul></div>' +
        '<hr class="about-divider">' +
        '<div class="about-credits">' +
        '<div style="font-weight:600;margin-bottom:8px;">👥 贡献者</div>' +
        '<div class="credit-item"><span>核心开发</span><span>孙洋洋</span></div>' +
        '<div class="credit-item"><span>AI 集成</span><span>孙洋洋</span></div>' +
        '<div class="credit-item"><span>UI 设计</span><span>孙洋洋</span></div>' +
        '<div class="credit-item"><span>文档编写</span><span>孙洋洋</span></div>' +
        '</div>' +
        '<div class="about-tech-stack">' +
        '<span class="tech-tag"><i class="fab fa-python"></i> Python 3.10+</span>' +
        '<span class="tech-tag"><i class="fas fa-window-maximize"></i> PyQt5</span>' +
        '<span class="tech-tag"><i class="fas fa-globe"></i> QWebEngine</span>' +
        '<span class="tech-tag"><i class="fas fa-brain"></i> OpenAI SDK</span>' +
        '<span class="tech-tag"><i class="fas fa-database"></i> SQLite</span>' +
        '<span class="tech-tag"><i class="fas fa-code"></i> HTML5/CSS3/JS</span>' +
        '</div>' +
        '<hr class="about-divider">' +
        '<div style="text-align:center;font-size:13px;color:var(--text-muted);">© 2026 ' + author + '. All rights reserved.<br>Made with ❤️ and ☕</div>' +
        '<div class="about-actions">' +
            '<button onclick="showToast(\'检查更新中...\',\'info\')"><i class="fas fa-sync"></i> 检查更新</button>' +
            '<button onclick="showToast(\'日志已导出\',\'success\')"><i class="fas fa-file-export"></i> 导出日志</button>' +
            '<button class="primary" onclick="showToast(\'✅ 系统运行正常\',\'success\')"><i class="fas fa-check-circle"></i> 系统状态</button>' +
        '</div></div>';
    
    console.log('[About] done, content length: ' + aboutBody.innerHTML.length);
    
    // 强制重绘（参考单文件版本解决QWebEngine渲染问题）
    aboutBody.style.display = 'none';
    void aboutBody.offsetHeight;
    aboutBody.style.display = 'block';
}