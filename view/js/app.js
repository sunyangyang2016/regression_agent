// ============================================
// Agent - 应用初始化与全局状态
// ============================================
const APP_INFO = { name: 'Regression Agent', version: '1.0.1alpha', releaseDate: '2026-07-19' };
var appState = {
    currentModel: null, models: [], mcpServers: [], mcpMarket: [],
    skills: [], conversations: [], currentTab: 'mcp', isProcessing: false,
    messages: [],
    config: { provider: 'deepseek', model: 'deepseek-chat', temperature: 0.7, maxTokens: 2000 }
};
window.appState = appState;

const defaultModels = [{ id:'deepseek', name:'DeepSeek', provider:'deepseek', model:'deepseek-chat', apiKey:'', baseUrl:'https://api.deepseek.com/v1', temperature:0.7, maxTokens:2000, active:true, online:true, isDefault:true }];

document.addEventListener('DOMContentLoaded', function() {
    appState.models = defaultModels;
    appState.currentModel = appState.models.find(m=>m.active)||appState.models[0];
    const t = localStorage.getItem('agent-theme')||'dark';
    setTheme(t);
    if(typeof loadAgentConfigTheme==='function')loadAgentConfigTheme();
    updateModelUI(); renderMCPServers(); renderMCPLocalServers(); renderMCPMarket(); renderModelList();
    renderTools(); renderSkills(); renderPlugins(); updateMCPBadge(); updateModelCount();
    // 初始化聊天/插件 Tab 栏（固定「聊天」Tab 始终显示）
    try { if (typeof initPluginTabs === 'function') initPluginTabs(); } catch(e) { console.warn('[App] initPluginTabs error:', e); }
    ['tabMCP','tabModels','tabTools','tabSkills','tabPlugins','tabSettings','tabAbout'].forEach(function(id){
        var el=document.getElementById(id);
        if(el) el.style.display = id==='tabMCP' ? 'block' : 'none';
    });
    switchMCPSubTab('market');
    console.log('Agent loaded');
    setTimeout(function() { lazyLoadPanel('tabAbout', 'html/about.html'); }, 500);
    setTimeout(function() { lazyLoadPanel('tabSettings', 'html/settings.html'); }, 600);
    setTimeout(function() { lazyLoadPanel('tabTools', 'html/tools.html'); }, 700);
    setTimeout(function() {
        lazyLoadPanel('tabSkills', 'html/skills.html', function(){
            // 面板加载完成后渲染技能
            if (typeof renderSkills === 'function') {
                renderSkills();
                console.log('[Skills] 面板加载完成，重新渲染');
            }
        });
    }, 800);
    setTimeout(function() { lazyLoadPanel('tabPlugins', 'html/plugins.html'); }, 900);
    setTimeout(function() { lazyLoadPanel('tabModels', 'html/models.html'); }, 1000);
});

window._bridgeReady = false;
window.py_bridge = null;
window.config_bridge = null;
window.tool_bridge = null;
window.skill_bridge = null;
window.mcp_bridge = null;
window.plugin_bridge = null;
window.security_bridge = null;
window.monitor_bridge = null;
window.video_bridge = null;
window.rag_bridge = null;
window.ui_state_bridge = null;
function connectBridge() {
    if(typeof QWebChannel==='undefined'||typeof qt==='undefined'||!qt.webChannelTransport){setTimeout(connectBridge,200);return;}
    try{
    new QWebChannel(qt.webChannelTransport,function(ch){
            window.py_bridge=ch.objects.py_bridge;
            window.config_bridge=ch.objects.config_bridge;
            window.tool_bridge=ch.objects.tool_bridge;
            window.skill_bridge=ch.objects.skill_bridge;
            window.mcp_bridge=ch.objects.mcp_bridge;
            window.plugin_bridge=ch.objects.plugin_bridge;
            window.agent_config_bridge=ch.objects.agent_config_bridge;
            window.security_bridge=ch.objects.security_bridge||ch.objects.security_plugin_bridge;
            window.monitor_bridge=ch.objects.monitor_bridge||ch.objects.monitor_plugin_bridge;
            window.video_bridge=ch.objects.video_bridge;
            window.rag_bridge=ch.objects.rag_bridge;
            window.voice_bridge=ch.objects.voice_bridge;
            window.ui_state_bridge=ch.objects.ui_state_bridge;
            window._bridgeReady=true;
            console.log('[Bridge] OK');
            if(window.py_bridge) showToast('后端已连接','success');
            if (typeof startMCPStatusPolling === 'function') startMCPStatusPolling();
            setTimeout(function(){
                loadAllData();
                if(typeof loadAgentConfigTheme==='function')loadAgentConfigTheme();
                // 后端数据就绪后恢复上次的 UI 状态（面板/侧边栏/插件 Tab）
                if (typeof restoreUIState === 'function') restoreUIState();
            }, 200);
        });
    }catch(e){console.error('[Bridge]',e);setTimeout(connectBridge,500);}
}
function loadAllData() {
    if(window.config_bridge){
        try{
            var promise=window.config_bridge.getModels();
            if(promise && typeof promise.then==='function'){
                promise.then(function(modelsStr){
                    try{
                        if(typeof modelsStr==='string') modelsStr=JSON.parse(modelsStr);
                        if(modelsStr&&modelsStr.length>0){
                            appState.models=modelsStr;
                            appState.currentModel=appState.models.find(function(m){return m.active;})||appState.models[0];
                            console.log('[Models] 已加载',modelsStr.length,'个模型');
                            updateModelUI();renderModelList();
                            // 启动后自动对激活模型发起真实连通性测试（解决"日志已连接但 UI 离线"）
                            setTimeout(function(){
                                if(typeof _testModelConnection==='function' && appState && appState.currentModel){
                                    var cm=appState.currentModel;
                                    if(cm.apiKey){
                                        _testModelConnection(cm.provider, cm.model, cm.apiKey, cm.baseUrl||'', cm.id, true);
                                    }
                                }
                            }, 800);
                            loadConfig();
                        }
                    }catch(e2){console.warn('[Models] 解析失败:',e2);}
                });
            } else if(typeof models==='string'){
                var models=JSON.parse(models);
                if(models&&models.length>0){
                    appState.models=models;
                    appState.currentModel=appState.models.find(function(m){return m.active;})||appState.models[0];
                }
            }
        }catch(e){console.warn('[Models] 加载模型列表失败:',e);}
    }
    if(window.py_bridge){
        try{
            var promise=window.py_bridge.getConversations();
            if(promise && typeof promise.then==='function'){
                promise.then(function(convStr){
                    if(convStr && typeof convStr==='string'){
                        var convList=JSON.parse(convStr);
                        // 无论是否为空数组都渲染（空时显示"暂无对话"），避免一直停留在加载中
                        appState.conversations=convList||[];
                        renderChatList(appState.conversations);
                        console.log('[App] 已加载 '+appState.conversations.length+' 个对话');
                    }
                }).catch(function(e){console.warn('[App] Promise 失败:',e);});
            } else if(convStr && typeof convStr==='string'){
                var convList=JSON.parse(convStr);
                // 无论是否为空数组都渲染（空时显示"暂无对话"），避免一直停留在加载中
                appState.conversations=convList||[];
                renderChatList(appState.conversations);
            }
        }catch(e){console.warn('[App] 加载对话列表失败:',e);}
    }
    if(window.skill_bridge){
        try{
            var promise=window.skill_bridge.getSkills();
            if(promise && typeof promise.then==='function'){
                promise.then(function(skillsStr){
                    if(skillsStr && typeof skillsStr==='string'){
                        var skills=JSON.parse(skillsStr);
                        if(skills && skills.length>0){
                            appState.skills=skills;
                            renderSkills();
                            console.log('[Skills] 已加载 '+skills.length+' 个技能');
                        } else {
                            console.log('[Skills] 后端返回的技能列表为空');
                        }
                    }
                }).catch(function(e){console.warn('[Skills] Promise 失败:',e);});
            } else {
                console.warn('[Skills] skill_bridge.getSkills 不支持 Promise');
                try {
                    var raw = window.skill_bridge.getSkills();
                    if (raw) {
                        var skills = JSON.parse(raw);
                        if (skills && skills.length>0) {
                            appState.skills = skills;
                            renderSkills();
                            console.log('[Skills] 已加载(no-promise) '+skills.length+' 个技能');
                        }
                    }
                } catch(e) { console.warn('[Skills] 同步加载失败:', e); }
            }
        }catch(e){console.warn('[Skills] 加载技能列表失败:',e);}
    }
    if(window.tool_bridge){
        try{
            var promise = window.tool_bridge.getTools();
            if(promise && typeof promise.then==='function'){
                promise.then(function(toolsStr){
                    if(toolsStr && typeof toolsStr==='string'){
                        var tools = JSON.parse(toolsStr);
                        if(tools && tools.length>0){
                            window._cachedTools = tools;
                            renderTools();
                            console.log('[Tools] 已加载 '+tools.length+' 个工具');
                        }
                    }
                }).catch(function(e){console.warn('[Tools] Promise 失败:',e);});
            }
        }catch(e){console.warn('[Tools] 加载工具列表失败:',e);}
    }
    if (window.mcp_bridge && window._bridgeReady) {
        try {
            var promise = window.mcp_bridge.getMCPMarket();
            if (promise && typeof promise.then === 'function') {
                promise.then(function(marketStr) {
                    try {
                        var data = typeof marketStr === 'string' ? JSON.parse(marketStr) : marketStr;
                        var items = data.market || data || [];
                        // 无论是否有数据都更新（空数组显示"暂无市场数据"，不再保留默认项）
                        items.forEach(function(item) {
                            var server = appState.mcpServers.find(function(s) { return s.id === item.id; });
                            if (server) item.installed = true;
                        });
                        appState.mcpMarket = items;
                        renderMCPMarket();
                        console.log('[MCP] 已加载 ' + items.length + ' 个市场项');
                    } catch(e) { console.warn('[MCP] 解析市场数据失败:', e); }
                }).catch(function(e) { console.warn('[MCP] 市场数据 Promise 失败:', e); });
            }
        } catch(e) { console.warn('[MCP] 加载市场数据失败:', e); }
    }
    if (window.mcp_bridge && window._bridgeReady) {
        try {
            var promise = window.mcp_bridge.getMCPServers();
            if (promise && typeof promise.then === 'function') {
                promise.then(function(serversStr) {
                    try {
                        var servers = typeof serversStr === 'string' ? JSON.parse(serversStr) : serversStr;
                        appState.mcpServers = servers || [];
                        renderMCPServers();
                        renderMCPLocalServers();
                        updateMCPBadge();
                        console.log('[MCP] 已加载 ' + (appState.mcpServers.length) + ' 个服务器');
                    } catch(e) { console.warn('[MCP] 解析服务器列表失败:', e); }
                }).catch(function(e) { console.warn('[MCP] 服务器 Promise 失败:', e); });
            }
        } catch(e) { console.warn('[MCP] 加载服务器失败:', e); }
    }
    if (window.plugin_bridge && window._bridgeReady) {
        try {
            var promise = window.plugin_bridge.getPlugins();
            if (promise && typeof promise.then === 'function') {
                promise.then(function(pluginsStr) {
                    try {
                        var plugins = typeof pluginsStr === 'string' ? JSON.parse(pluginsStr) : pluginsStr;
                        appState.plugins = plugins || [];
                        if (typeof renderPlugins === 'function') renderPlugins();
                        console.log('[Plugins] 已加载 ' + (appState.plugins.length) + ' 个插件');
                    } catch(e) { console.warn('[Plugins] 解析插件列表失败:', e); }
                }).catch(function(e) { console.warn('[Plugins] 插件 Promise 失败:', e); });
            }
        } catch(e) { console.warn('[Plugins] 加载插件列表失败:', e); }
    }
    updateModelUI();renderModelList();updateModelCount();renderTools();
    _retryLoadMCPConfig(0);
}

function _retryLoadMCPConfig(tries) {
    if (tries > 15) return;
    if (typeof loadMCPConfigToEditor === 'function' && window.mcp_bridge && window._bridgeReady) {
        loadMCPConfigToEditor();
    } else {
        setTimeout(function() { _retryLoadMCPConfig(tries + 1); }, 500);
    }
}

function loadConfig() {
    if(!window.config_bridge) return;
    try{
        var promise=window.config_bridge.getConfig();
        if(promise && typeof promise.then==='function'){
            promise.then(function(cfgStr){
                try{
                    if(typeof cfgStr==='string') cfgStr=JSON.parse(cfgStr);
                    if(cfgStr&&cfgStr.provider){
                        appState.config=cfgStr;
                        var model=appState.models.find(function(m){
                            return m.id===cfgStr.provider||(m.name||'').toLowerCase()===cfgStr.provider.toLowerCase();
                        });
                        if(model){appState.currentModel=model;}
                        console.log('[Config] 已加载后端配置:',cfgStr.provider,cfgStr.model);
                        updateModelUI();
                    }
                }catch(e2){console.warn('[Config] 解析失败:',e2);}
            });
        }
    }catch(e){console.warn('[Config] 加载后端配置失败:',e);}
    updateModelUI();renderModelList();updateModelCount();
}
setTimeout(connectBridge,300);
function loadAgentConfigTheme(){if(window.agent_config_bridge&&window.agent_config_bridge.getConfig){try{window.agent_config_bridge.getConfig().then(function(c){try{var cfg=typeof c==='string'?JSON.parse(c):c;if(cfg&&cfg.theme){localStorage.setItem('agent-theme',cfg.theme);if(typeof setTheme==='function')setTheme(cfg.theme);}}catch(e){}});}catch(e){}}}
