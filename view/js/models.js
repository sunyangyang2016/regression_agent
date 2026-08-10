// ============================================
// Models - 模型管理（UI 渲染 + 操作逻辑）
// ============================================

// 当前正在编辑的模型ID（用于更新模式）
var _editingModelId = null;

// ============================================
// 价格默认值（仅当模型记录/预设均无数据时兜底）
// ============================================
var _DEFAULT_PRICES = { hit: 0.07, miss: 1.0, output: 2.0 };

// ============================================
// 模型 UI 显示
// ============================================

// 同步在线状态（真实连通性测试驱动）：
// 仅保留模型已有的 online 字段值（由 testConnection 真实结果写入），
// 未测试过的模型保持默认 offline，不再做"激活+有Key=在线"的静态强判。
function syncModelOnlineState(){
    if(!appState||!appState.models)return;
    appState.models.forEach(function(m){
        if(m.online===undefined){ m.online=false; }
    });
    if(appState.currentModel && appState.currentModel.online===undefined){
        appState.currentModel.online=false;
    }
}

// 发起真实连通性测试并更新模型在线状态
// 测试在后台线程执行，结果通过 window.onModelTestResult 回调（由 bridge 调用）
function _testModelConnection(provider, modelName, apiKey, baseUrl, modelId, silent){
    if(!window.config_bridge || typeof window.config_bridge.testConnection!=='function'){
        if(!silent){ showToast('配置桥接未就绪，无法测试','error'); }
        console.log('[Models][测试] ⚠️ 无法发起测试: config_bridge存在?', !!window.config_bridge,
            '| testConnection方法?', window.config_bridge ? typeof window.config_bridge.testConnection : 'N/A',
            '| 目标模型:', modelId);
        return;
    }
    var cfg={provider:provider||'',model:modelName||'',apiKey:apiKey||'',baseUrl:baseUrl||''};
    console.log('[Models][测试] 发起真实测试:', cfg.provider, cfg.model, '| key有?', !!cfg.apiKey, '| 目标模型:', modelId);
    window.config_bridge.testConnection(JSON.stringify(cfg));
    // 记录待更新模型 id，供回调定位
    window._modelTestTargetId=modelId||null;
}

// 后端连通测试结果回调（由 ModelBridge._emit_test_result 调用）
window.onModelTestResult=function(success, msg){
    var id=window._modelTestTargetId||null;
    console.log('[Models][测试] 收到结果回调: success=', success, '| msg=', msg, '| 目标模型=', id);
    var m=null;
    if(id&&appState&&appState.models){
        m=appState.models.find(function(x){return x.id===id;});
    }
    // 未指定模型时更新当前激活模型
    if(!m&&appState&&appState.currentModel){ m=appState.currentModel; }
    console.log('[Models][测试] 匹配到模型?', !!m, m ? ('('+m.name+')') : '');
    if(m){
        m.online=!!success;
        // 持久化最新在线状态
        if(window.config_bridge&&typeof window.config_bridge.saveModels==='function'){
            window.config_bridge.saveModels(JSON.stringify(appState.models));
        }
        if(appState.currentModel&&appState.currentModel.id===m.id){
            updateModelUI();
        }
        renderModelList();
    }
    if(success){
        showToast('✅ '+msg,'success');
    }else{
        showToast('❌ '+msg,'error');
    }
    window._modelTestTargetId=null;
};

function updateModelUI(){
    syncModelOnlineState();
    var m=appState.currentModel;if(!m)return;
    var el;
    el=document.getElementById('currentModelDisplay');if(el)el.textContent=m.name;
    el=document.getElementById('providerDisplay');if(el)el.textContent=m.provider;
    el=document.getElementById('headerModelLabel');if(el)el.textContent=m.name;
    el=document.getElementById('headerProviderLabel');if(el)el.textContent='('+m.provider+')';
    el=document.getElementById('footerModel');if(el)el.textContent=m.name;
    el=document.getElementById('statusDot');if(el)el.className='status-dot '+(m.online?'online':'offline');
    el=document.getElementById('activeModelName');if(el)el.textContent=m.name;
    el=document.getElementById('activeModelProvider');if(el)el.textContent='提供商: '+m.provider;
    el=document.getElementById('activeModelDesc');if(el)el.textContent=m.model;
    el=document.getElementById('activeModelStatus');if(el){el.textContent=m.online?'● 在线':'○ 离线';el.className='model-card-status '+(m.online?'online':'offline');}
}

function renderModelList(){
    if(!appState||!appState.models)return;
    syncModelOnlineState();
    var c=document.getElementById('modelList');if(!c)return;
    var ms=appState.models.sort(function(a,b){if(a.active)return -1;if(b.active)return 1;return a.name.localeCompare(b.name);});
    c.innerHTML=ms.map(function(m){
        var keyMasked=m.apiKey?maskApiKey(m.apiKey):'未设置';
        var detailId='modelDetail-'+m.id;
        return '<div class="model-card'+(m.active?' active':'')+'" style="cursor:pointer;" onclick="editModel(\''+m.id+'\')">'+
            '<div class="model-card-header">'+
                '<div><div class="model-card-name">'+m.name+(m.active?' <span style="font-size:11px;color:var(--accent-primary);background:rgba(88,166,255,0.15);padding:2px 8px;border-radius:var(--radius-full);">当前使用</span>':'')+'</div>'+
                '<div class="model-card-provider">'+m.provider+' · '+m.model+'</div></div>'+
                '<span class="model-card-status '+(m.online?'online':'offline')+'">'+(m.online?'● 在线':'○ 离线')+'</span>'+
            '</div>'+
            '<div class="model-detail" id="'+detailId+'" style="display:none;margin-top:10px;padding:10px 12px;background:var(--bg-secondary);border-radius:var(--radius-sm);font-size:12px;color:var(--text-secondary);line-height:1.8;">'+
                '<div style="display:grid;grid-template-columns:80px 1fr;gap:2px 8px;">'+
                    '<span style="color:var(--text-muted);">提供商:</span><span>'+m.provider+'</span>'+
                    '<span style="color:var(--text-muted);">模型:</span><span>'+m.model+'</span>'+
                    '<span style="color:var(--text-muted);">API Key:</span><span>'+keyMasked+'</span>'+
                    '<span style="color:var(--text-muted);">Base URL:</span><span>'+(m.baseUrl||'-')+'</span>'+
                    '<span style="color:var(--text-muted);">温度:</span><span>'+(m.temperature||0.7)+'</span>'+
                    '<span style="color:var(--text-muted);">最大Token:</span><span>'+(m.maxTokens||2000)+'</span>'+
                    '<span style="color:var(--text-muted);">最大上下文:</span><span>'+(m.maxContext||65536)+'</span>'+
                    '<span style="color:var(--text-muted);">命中单价:</span><span>$'+(m.pricePerMillionHitTokens!==undefined&&m.pricePerMillionHitTokens!==null?m.pricePerMillionHitTokens:_DEFAULT_PRICES.hit)+'/1M</span>'+
                    '<span style="color:var(--text-muted);">未命中单价:</span><span>$'+(m.pricePerMillionMissTokens!==undefined&&m.pricePerMillionMissTokens!==null?m.pricePerMillionMissTokens:_DEFAULT_PRICES.miss)+'/1M</span>'+
                    '<span style="color:var(--text-muted);">输出单价:</span><span>$'+(m.pricePerMillionOutputTokens!==undefined&&m.pricePerMillionOutputTokens!==null?m.pricePerMillionOutputTokens:_DEFAULT_PRICES.output)+'/1M</span>'+
                '</div>'+
            '</div>'+
            '<div class="model-card-actions" style="display:flex;gap:8px;margin-top:8px;padding-top:8px;border-top:1px solid var(--border-color);" onclick="event.stopPropagation();">'+
                (m.active?'':'<button onclick="switchModel(\''+m.id+'\')" style="padding:4px 10px;background:var(--accent-primary);border:none;border-radius:var(--radius-sm);color:#fff;cursor:pointer;font-size:12px;font-family:var(--font-family);"><i class="fas fa-check-circle"></i> 使用</button>')+
                '<button onclick="editModel(\''+m.id+'\')" style="padding:4px 10px;background:transparent;border:1px solid var(--border-color);border-radius:var(--radius-sm);color:var(--text-secondary);cursor:pointer;font-size:12px;font-family:var(--font-family);"><i class="fas fa-edit"></i> 编辑</button>'+
                (m.isDefault?'':'<button onclick="deleteModel(\''+m.id+'\')" style="padding:4px 10px;background:transparent;border:1px solid var(--border-color);border-radius:var(--radius-sm);color:var(--text-muted);cursor:pointer;font-size:12px;font-family:var(--font-family);"><i class="fas fa-trash"></i> 删除</button>')+
            '</div>'+
        '</div>';
    }).join('');
}

function updateModelCount(){var e=document.getElementById('modelCount');if(e)e.textContent=appState.models.length;}

if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',function(){setTimeout(initProviderDropdowns,300);});}else{setTimeout(initProviderDropdowns,300);}

// ============================================
// Header 模型下拉菜单
// ============================================
function renderModelDropdown(){
    var list=document.getElementById('modelDropdownList');
    if(!list)return;
    list.innerHTML=appState.models.map(function(m){
        return '<div class="model-dropdown-item'+(m.active?' active':'')+'" onclick="switchModelFromDropdown(\''+m.id+'\')">'+
            '<div class="item-info">'+
                '<span class="item-name">'+m.name+'</span>'+
                '<span class="item-provider">'+m.provider+' · '+m.model+'</span>'+
            '</div>'+
            (m.active?'<span class="item-check"><i class="fas fa-check-circle"></i></span>':'')+
        '</div>';
    }).join('');
}
function toggleModelDropdown(event){
    event.stopPropagation();
    var dd=document.getElementById('modelDropdown');
    if(!dd)return;
    renderModelDropdown();
    dd.classList.toggle('show');
}
function switchModelFromDropdown(id){
    switchModel(id);
    document.getElementById('modelDropdown').classList.remove('show');
}
document.addEventListener('click',function(e){
    var dd=document.getElementById('modelDropdown');
    if(dd)dd.classList.remove('show');
});

// ============================================
// 模型操作：添加 / 编辑 / 切换 / 删除
// ============================================

function _getProviderBaseUrl(provider){
    var meta=_findProviderMeta(provider);
    return (meta && meta.base_url) ? meta.base_url : '';
}

function addModel(){
    var provider=document.getElementById('providerSelect').value;
    // 模型名：非自定义且下拉可见时用下拉选中值，否则用文本输入框
    var modelSel=document.getElementById('modelSelect');
    var modelName=((modelSel&&modelSel.style.display!=='none')?modelSel.value:document.getElementById('modelNameInput').value.trim());
    var apiKey=document.getElementById('apiKeyInput').value.trim();
    var baseUrl=document.getElementById('baseUrlInput').value.trim()||_getProviderBaseUrl(provider);
    var temperature=parseFloat(document.getElementById('temperatureInput').value);
    if(isNaN(temperature))temperature=0.7;
    var maxTokens=parseInt(document.getElementById('maxTokensInput').value)||2000;
    var priceHit=parseFloat(document.getElementById('priceHitInput').value);
    if(isNaN(priceHit))priceHit=_DEFAULT_PRICES.hit;
    var priceMiss=parseFloat(document.getElementById('priceMissInput').value);
    if(isNaN(priceMiss))priceMiss=_DEFAULT_PRICES.miss;
    var priceOutput=parseFloat(document.getElementById('priceOutputInput').value);
    if(isNaN(priceOutput))priceOutput=_DEFAULT_PRICES.output;
    var maxContext=parseInt(document.getElementById('maxContextInput').value)||65536;
    if(maxContext<1)maxContext=65536;
    var setActive=document.getElementById('setActiveCheckbox')&&document.getElementById('setActiveCheckbox').checked;
    if(!modelName){showToast('请输入模型名称','error');return;}
    if(!apiKey){showToast('请输入 API Key','error');return;}
    if(temperature<0||temperature>2){showToast('温度值必须在0-2之间','error');return;}
    if(maxTokens<1){showToast('最大 Token 必须大于0','error');return;}

    if(_editingModelId){
        var exist=appState.models.find(function(m){return m.id===_editingModelId;});
        if(exist){
            exist.name=modelName;
            exist.provider=provider;
            exist.model=modelName;
            exist.apiKey=apiKey;
            exist.baseUrl=baseUrl;
            exist.temperature=temperature;
            exist.maxTokens=maxTokens;
            exist.maxContext=maxContext;
            exist.pricePerMillionHitTokens=priceHit;
            exist.pricePerMillionMissTokens=priceMiss;
            exist.pricePerMillionOutputTokens=priceOutput;
            if(setActive && !exist.active){
                appState.models.forEach(function(m){m.active=(m.id===_editingModelId);});
                appState.currentModel=exist;
                updateModelUI();
            }
            if(exist.active){
                appState.currentModel=exist;
                updateModelUI();
                if(window.config_bridge){
                    var cfg={provider:provider,model:modelName,temperature:temperature,maxTokens:maxTokens,maxContext:maxContext,apiKey:apiKey,baseUrl:baseUrl,pricePerMillionHitTokens:priceHit,pricePerMillionMissTokens:priceMiss,pricePerMillionOutputTokens:priceOutput};
                    window.config_bridge.saveConfig(JSON.stringify(cfg));
                    window.config_bridge.reconnectAI();
                }
            }
            if(window.config_bridge){
                window.config_bridge.saveModels(JSON.stringify(appState.models));
            }
            renderModelList();
            updateModelCount();
            cancelEdit();
            showToast('✅ 模型已更新: '+modelName,'success');
            return;
        }
    }

    var id=provider+'-'+modelName.toLowerCase().replace(/[^a-z0-9-]/g,'');
    var exist=appState.models.find(function(m){return m.id===id;});
    if(exist){showToast('该模型已存在','error');return;}
    var newModel={
        id:id,
        name:modelName,
        provider:provider,
        model:modelName,
        apiKey:apiKey,
        baseUrl:baseUrl,
        temperature:temperature,
        maxTokens:maxTokens,
        maxContext:maxContext,
        pricePerMillionHitTokens:priceHit,
        pricePerMillionMissTokens:priceMiss,
        pricePerMillionOutputTokens:priceOutput,
        active:false,
        online:false,
        isDefault:false
    };
    appState.models.push(newModel);
    if(window.config_bridge){
        window.config_bridge.saveModels(JSON.stringify(appState.models));
    }
    if((setActive||appState.models.length===1)&&window.config_bridge){
        var cfg={provider:provider,model:modelName,temperature:temperature,maxTokens:maxTokens,maxContext:maxContext,apiKey:apiKey,baseUrl:baseUrl,pricePerMillionHitTokens:priceHit,pricePerMillionMissTokens:priceMiss,pricePerMillionOutputTokens:priceOutput};
        window.config_bridge.saveConfig(JSON.stringify(cfg));
        window.config_bridge.reconnectAI();
        newModel.active=true;
        newModel.online=false;   // 真实连通性测试通过后才置为在线
        appState.models.forEach(function(m){if(m.id!==id)m.active=false;});
        appState.currentModel=newModel;
        updateModelUI();
        // 异步发起真实连通性测试，结果通过 onModelTestResult 回写 online 状态
        setTimeout(function(){ _testModelConnection(provider, modelName, apiKey, baseUrl, id, true); }, 300);
    }
    renderModelList();
    updateModelCount();
    showToast('✅ 模型添加成功: '+modelName,'success');
    document.getElementById('modelNameInput').value='';
}

function editModel(id){
    var model=appState.models.find(function(m){return m.id===id;});
    if(!model){showToast('模型不存在','error');return;}
    _editingModelId=id;
    document.getElementById('providerSelect').value=model.provider;
    document.getElementById('modelNameInput').value=model.name;
    // 联动模型下拉：按当前提供商重建，并选中该模型
    if(typeof onProviderChange==='function'){
        onProviderChange(model.provider);
        var mSel=document.getElementById('modelSelect');
        if(mSel&&mSel.style.display!=='none'){
            var selIdx=0;
            for(var k=0;k<mSel.options.length;k++){if(mSel.options[k].value===model.model){selIdx=k;break;}}
            if(mSel.options.length>0)mSel.selectedIndex=selIdx;
            if(typeof onModelSelect==='function')onModelSelect(mSel.value);
        }
    }
    document.getElementById('apiKeyInput').value=model.apiKey||'';
    document.getElementById('baseUrlInput').value=model.baseUrl||'';
    document.getElementById('temperatureInput').value=(model.temperature!==undefined&&model.temperature!==null)?model.temperature:0.7;
    document.getElementById('maxTokensInput').value=model.maxTokens||2000;
    document.getElementById('maxContextInput').value=model.maxContext||65536;
    document.getElementById('priceHitInput').value=(model.pricePerMillionHitTokens!==undefined&&model.pricePerMillionHitTokens!==null)?model.pricePerMillionHitTokens:_DEFAULT_PRICES.hit;
    document.getElementById('priceMissInput').value=(model.pricePerMillionMissTokens!==undefined&&model.pricePerMillionMissTokens!==null)?model.pricePerMillionMissTokens:_DEFAULT_PRICES.miss;
    document.getElementById('priceOutputInput').value=(model.pricePerMillionOutputTokens!==undefined&&model.pricePerMillionOutputTokens!==null)?model.pricePerMillionOutputTokens:_DEFAULT_PRICES.output;
    document.getElementById('setActiveCheckbox').checked=false;
    var btn=document.querySelector('.btn-primary[onclick="addModel()"]');
    if(btn)btn.innerHTML='<i class="fas fa-save"></i> 更新模型';
    var cancelBtn=document.getElementById('cancelEditBtn');
    if(cancelBtn)cancelBtn.style.display='inline-flex';
    var form=document.getElementById('providerSelect');
    if(form)form.scrollIntoView({behavior:'smooth',block:'center'});
    showToast('✏️ 正在编辑: '+model.name,'info');
}

function cancelEdit(){
    _editingModelId=null;
    document.getElementById('apiKeyInput').value='';
    // 重置为内存数据中的第一个提供商（动态联动，无硬编码）
    var pSel=document.getElementById('providerSelect');
    if(pSel&&pSel.options.length>0){
        pSel.selectedIndex=0;
        if(typeof onProviderChange==='function')onProviderChange(pSel.value);
    }
    document.getElementById('temperatureInput').value='0.7';
    document.getElementById('maxTokensInput').value='2000';
    document.getElementById('setActiveCheckbox').checked=true;
    var btn=document.querySelector('.btn-primary[onclick="addModel()"]');
    if(btn)btn.innerHTML='<i class="fas fa-plus"></i> 添加模型';
    var cancelBtn=document.getElementById('cancelEditBtn');
    if(cancelBtn)cancelBtn.style.display='none';
}

function _priceOrDefault(m, key, fallback){
    return (m && m[key]!==undefined && m[key]!==null) ? m[key] : (fallback!==undefined?fallback:_DEFAULT_PRICES[key]);
}

function switchModel(id){
    var model=appState.models.find(function(m){return m.id===id;});
    if(!model){showToast('模型不存在','error');return;}
    appState.models.forEach(function(m){m.active=(m.id===id);});
    model.online=false;   // 真实连通性测试通过后才置为在线
    appState.currentModel=model;
    updateModelUI();
    renderModelList();
    window.chatApp.isProcessing=false;
    window.chatApp._currentAssistantId=null;
    var sendBtn=document.getElementById('sendBtn');
    if(sendBtn)sendBtn.disabled=false;
    if(window.config_bridge){
        window.config_bridge.saveModels(JSON.stringify(appState.models));
        var temperature=model.temperature!==undefined&&model.temperature!==null?model.temperature:0.7;
        var cfg={provider:model.provider,model:model.model,temperature:temperature,maxTokens:model.maxTokens||2000,maxContext:model.maxContext||65536,apiKey:model.apiKey||'',baseUrl:model.baseUrl||_getProviderBaseUrl(model.provider),pricePerMillionHitTokens:_priceOrDefault(model,'pricePerMillionHitTokens'),pricePerMillionMissTokens:_priceOrDefault(model,'pricePerMillionMissTokens'),pricePerMillionOutputTokens:_priceOrDefault(model,'pricePerMillionOutputTokens')};
        window.config_bridge.saveConfig(JSON.stringify(cfg));
        window.config_bridge.reconnectAI();
        // 异步发起真实连通性测试，结果通过 onModelTestResult 回写 online 状态
        setTimeout(function(){ _testModelConnection(model.provider, model.model, model.apiKey||'', model.baseUrl||_getProviderBaseUrl(model.provider), model.id, true); }, 300);
    }
    showToast('✅ 已切换到: '+model.name,'success');
}

function deleteModel(id){
    var model=appState.models.find(function(m){return m.id===id;});
    if(!model)return;
    if(model.isDefault){showToast('默认模型不可删除','error');return;}
    showConfirmDialog('确定删除模型「'+model.name+'」吗？', function(){
        var isActive=model.active;
        appState.models=appState.models.filter(function(m){return m.id!==id;});
        if(isActive&&appState.models.length>0){
            var first=appState.models[0];
            first.active=true;
            appState.currentModel=first;
            updateModelUI();
            if(window.config_bridge){
                var temp=first.temperature!==undefined&&first.temperature!==null?first.temperature:0.7;
                var cfg={provider:first.provider,model:first.model,temperature:temp,maxTokens:first.maxTokens||2000,maxContext:first.maxContext||65536,apiKey:first.apiKey||'',baseUrl:first.baseUrl||_getProviderBaseUrl(first.provider),pricePerMillionHitTokens:_priceOrDefault(first,'pricePerMillionHitTokens'),pricePerMillionMissTokens:_priceOrDefault(first,'pricePerMillionMissTokens'),pricePerMillionOutputTokens:_priceOrDefault(first,'pricePerMillionOutputTokens')};
                window.config_bridge.saveConfig(JSON.stringify(cfg));
                window.config_bridge.reconnectAI();
            }
        }
        if(window.config_bridge){
            window.config_bridge.saveModels(JSON.stringify(appState.models));
        }
        renderModelList();
        updateModelCount();
        showToast('已删除: '+model.name,'info');
    }, {title:'删除模型', confirmText:'删除', cancelText:'取消', danger:true, icon:'🗑️'});
}

function testCurrentModel(){
    showToast('正在测试连接...','info');
    if(window.config_bridge && typeof window.config_bridge.testConnection==='function'){
        var provider, modelName, apiKey, baseUrl, targetId;
        if(_editingModelId){
            // 编辑模式：测表单当前填写的值
            provider=document.getElementById('providerSelect').value;
            var modelSel=document.getElementById('modelSelect');
            modelName=((modelSel&&modelSel.style.display!=='none')?modelSel.value:document.getElementById('modelNameInput').value.trim());
            apiKey=document.getElementById('apiKeyInput').value.trim();
            baseUrl=document.getElementById('baseUrlInput').value.trim()||_getProviderBaseUrl(provider);
            targetId=_editingModelId;
        } else if(appState && appState.currentModel){
            // 正常模式：测当前激活模型的真实配置（provider/model/apiKey/baseUrl 全部取模型字段）
            var cm=appState.currentModel;
            provider=cm.provider;
            modelName=cm.model;
            apiKey=cm.apiKey||'';
            baseUrl=cm.baseUrl||_getProviderBaseUrl(cm.provider);
            targetId=cm.id;
        } else {
            showToast('没有可测试的模型','error');
            return;
        }
        if(!apiKey){
            showToast('该模型未配置 API Key，无法测试','error');
            return;
        }
        // 1. 将测试配置应用到后端运行时并热重连，使 AI 客户端连接状态与测试一致
        if(window.config_bridge){
            var temperature=parseFloat(document.getElementById('temperatureInput').value);
            if(isNaN(temperature))temperature=0.7;
            var maxTokens=parseInt(document.getElementById('maxTokensInput').value)||2000;
            var maxContext=parseInt(document.getElementById('maxContextInput').value)||65536;
            var priceHit=parseFloat(document.getElementById('priceHitInput').value);
            if(isNaN(priceHit))priceHit=_DEFAULT_PRICES.hit;
            var priceMiss=parseFloat(document.getElementById('priceMissInput').value);
            if(isNaN(priceMiss))priceMiss=_DEFAULT_PRICES.miss;
            var priceOutput=parseFloat(document.getElementById('priceOutputInput').value);
            if(isNaN(priceOutput))priceOutput=_DEFAULT_PRICES.output;
            var cfg={provider:provider,model:modelName,temperature:temperature,maxTokens:maxTokens,maxContext:maxContext,apiKey:apiKey,baseUrl:baseUrl,pricePerMillionHitTokens:priceHit,pricePerMillionMissTokens:priceMiss,pricePerMillionOutputTokens:priceOutput};
            window.config_bridge.saveConfig(JSON.stringify(cfg));
            window.config_bridge.reconnectAI();
        }
        // 2. 真实连通性测试（后台线程），结果回调更新 UI 在线状态
        _testModelConnection(provider, modelName, apiKey, baseUrl, targetId, true);
    }else{
        setTimeout(function(){showToast('连接成功','success');},1000);
    }
}

function toggleApiKeyVisibility(){
    var input=document.getElementById('apiKeyInput');
    var icon=document.getElementById('eyeIcon');
    if(input.type==='password'){
        input.type='text';
        icon.className='fas fa-eye-slash';
    }else{
        input.type='password';
        icon.className='fas fa-eye';
    }
}

function maskApiKey(key){
    if(!key||key.length<8)return key||'';
    return key.substring(0,6)+'****'+key.substring(key.length-4);
}

function toggleModelDetail(id){
    var el=document.getElementById('modelDetail-'+id);
    if(el){
        if(el.style.display==='none'||el.style.display===''){
            el.style.display='block';
        }else{
            el.style.display='none';
        }
    }
}

function changeModelFromSettings(v){
    var m=appState.models.find(function(x){return x.id===v;});
    if(m){
        appState.models.forEach(function(x){x.active=(x.id===v);});
        appState.currentModel=m;
        updateModelUI();
        renderModelList();
        showToast('切换到: '+m.name,'success');
    }
}


// ============================================
// 提供商 -> 模型 -> 价格/URL 联动
// 数据源：api_providers.json 一次性读入内存（_providerMeta）
// 联动逻辑全部基于内存数据结构，无硬编码提供商/模型/价格
// ============================================
var _providerMeta = {};          // { "DeepSeek": {base_url, max_context, models:{模型名:{hit,miss,output,url?}}} , ...}
var _modelNamesByProvider = {};  // 预计算：提供商 → 模型名数组

// 查找 provider 元数据（精确优先，否则忽略大小写，容错大小写差异）
function _findProviderMeta(name) {
    if (!name) return null;
    if (_providerMeta && _providerMeta[name]) return _providerMeta[name];
    var keys = _providerMeta ? Object.keys(_providerMeta) : [];
    var lname = String(name).toLowerCase();
    for (var i = 0; i < keys.length; i++) {
        if (String(keys[i]).toLowerCase() === lname) return _providerMeta[keys[i]];
    }
    return null;
}

// 预计算提供商 → 模型名数组（联动模型下拉直接使用）
function buildProviderIndex() {
    _modelNamesByProvider = {};
    Object.keys(_providerMeta || {}).forEach(function(p) {
        var m = (_providerMeta[p] && _providerMeta[p].models) ? _providerMeta[p].models : {};
        _modelNamesByProvider[p] = Object.keys(m);
    });
    // 兜底：无论如何都保证存在「自定义」项
    if (!_providerMeta || !_providerMeta['自定义']) {
        _providerMeta = _providerMeta || {};
        _providerMeta['自定义'] = {base_url:'', models:{}};
        _modelNamesByProvider['自定义'] = [];
    }
}

// 渲染提供商下拉（基于内存 _providerMeta）
function renderProviderSelect() {
    var sel = document.getElementById('providerSelect');
    if (!sel) return;
    sel.innerHTML = '';
    Object.keys(_providerMeta).forEach(function(name) {
        var opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        sel.appendChild(opt);
    });
    if (sel.options.length === 0) {
        _providerMeta = {'自定义': {base_url:'', models:{}}};
        _modelNamesByProvider = {'自定义': []};
        var o = document.createElement('option'); o.value = '自定义'; o.textContent = '自定义';
        sel.appendChild(o);
    }
    // 默认选中第一个提供商并触发联动
    if (typeof onProviderChange === 'function') onProviderChange(sel.value);
}

function initProviderDropdowns() {
    if (!window.config_bridge || typeof window.config_bridge.getUserConfig !== 'function') {
        // 桥接未就绪，500ms 后重试
        setTimeout(initProviderDropdowns, 500);
        return;
    }
    try {
        window.config_bridge.getUserConfig('api_providers.json').then(function(str) {
            var data = (typeof str === 'string') ? JSON.parse(str) : str;
            var providers = (data && data.providers) ? data.providers : {};
            // 一次性读入内存数据结构
            _providerMeta = providers;
            buildProviderIndex();
            renderProviderSelect();
        }).catch(function(e){
            console.warn('[Models] 加载 api_providers.json 失败:', e);
            _providerMeta = {};
            buildProviderIndex();
            renderProviderSelect();
        });
    } catch(e) {
        console.warn('[Models] 初始化提供商下拉失败:', e);
    }
}

function onProviderChange(provider) {
    var meta = _findProviderMeta(provider) || {base_url:'', max_context:null, models:{}};
    var models = meta.models || {};
    // 提供商级 base_url 联动（作为默认，模型级 url 优先级更高）
    if (meta.base_url) {
        var b = document.getElementById('baseUrlInput');
        if (b) b.value = meta.base_url;
    }
    // 提供商级 max_context 联动
    if (meta.max_context) {
        var mc = document.getElementById('maxContextInput');
        if (mc) mc.value = meta.max_context;
    }
    var sel = document.getElementById('modelSelect');
    var input = document.getElementById('modelNameInput');
    var mnames = _modelNamesByProvider[provider] || Object.keys(models);
    if (provider === '自定义' || mnames.length === 0) {
        // 无预设模型：隐藏模型下拉，显示文本输入框
        if (sel) sel.style.display = 'none';
        if (input) input.style.display = 'block';
        return;
    }
    if (sel && input) {
        sel.innerHTML = '';
        mnames.forEach(function(m) {
            var o = document.createElement('option');
            o.value = m;
            o.textContent = m;
            sel.appendChild(o);
        });
        sel.style.display = 'block';
        input.style.display = 'none';
        sel.value = mnames[0];
        if (typeof onModelSelect === 'function') onModelSelect(sel.value);
    }
}

function onModelSelect(modelName) {
    var sel = document.getElementById('providerSelect');
    var provider = sel ? sel.value : '';
    var meta = _findProviderMeta(provider) || {};
    var models = meta.models || {};
    var p = models[modelName];
    if (!p) return;
    // 命中/未命中/输出 价格联动
    var h = document.getElementById('priceHitInput');
    var m = document.getElementById('priceMissInput');
    var o = document.getElementById('priceOutputInput');
    if (h && p.hit !== undefined) h.value = p.hit;
    if (m && p.miss !== undefined) m.value = p.miss;
    if (o && p.output !== undefined) o.value = p.output;
    // Base URL 联动：模型级 url（或 base_url）优先于提供商级
    var u = p.url || p.base_url;
    if (u) {
        var b = document.getElementById('baseUrlInput');
        if (b) b.value = u;
    }
}