// ============================================
// Models - 模型管理（UI 渲染 + 操作逻辑）
// ============================================

// 当前正在编辑的模型ID（用于更新模式）
var _editingModelId = null;

// ============================================
// 模型 UI 显示
// ============================================
function updateModelUI(){
    var m=appState.currentModel;if(!m)return;
    var el;
    el=document.getElementById('currentModelDisplay');if(el)el.textContent=m.name;
    el=document.getElementById('providerDisplay');if(el)el.textContent=m.provider;
    el=document.getElementById('headerModelLabel');if(el)el.textContent=m.name;
    el=document.getElementById('headerProviderLabel');if(el)el.textContent='('+m.provider+')';
    el=document.getElementById('footerModel');if(el)el.textContent=m.name;
    el=document.getElementById('welcomeModel');if(el)el.textContent=m.name;
    el=document.getElementById('statusDot');if(el)el.className='status-dot '+(m.online?'online':'offline');
    el=document.getElementById('activeModelName');if(el)el.textContent=m.name;
    el=document.getElementById('activeModelProvider');if(el)el.textContent='提供商: '+m.provider;
    el=document.getElementById('activeModelDesc');if(el)el.textContent=m.model;
    el=document.getElementById('activeModelStatus');if(el){el.textContent=m.online?'● 在线':'○ 离线';el.className='model-card-status '+(m.online?'online':'offline');}
}

function renderModelList(){
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

function addModel(){
    var provider=document.getElementById('providerSelect').value;
    var modelName=document.getElementById('modelNameInput').value.trim();
    var apiKey=document.getElementById('apiKeyInput').value.trim();
    var baseUrl=document.getElementById('baseUrlInput').value.trim();
    var temperature=parseFloat(document.getElementById('temperatureInput').value);
    if(isNaN(temperature))temperature=0.7;
    var maxTokens=parseInt(document.getElementById('maxTokensInput').value)||2000;
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
            exist.baseUrl=baseUrl||'https://api.deepseek.com/v1';
            exist.temperature=temperature;
            exist.maxTokens=maxTokens;
            if(setActive && !exist.active){
                appState.models.forEach(function(m){m.active=(m.id===_editingModelId);});
                appState.currentModel=exist;
                updateModelUI();
            }
            if(exist.active){
                appState.currentModel=exist;
                updateModelUI();
                if(window.config_bridge){
                    var cfg={provider:provider,model:modelName,temperature:temperature,maxTokens:maxTokens,apiKey:apiKey,baseUrl:baseUrl||'https://api.deepseek.com/v1'};
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
        baseUrl:baseUrl||'https://api.deepseek.com/v1',
        temperature:temperature,
        maxTokens:maxTokens,
        active:false,
        online:false,
        isDefault:false
    };
    appState.models.push(newModel);
    if(window.config_bridge){
        window.config_bridge.saveModels(JSON.stringify(appState.models));
    }
    if((setActive||appState.models.length===1)&&window.config_bridge){
        var cfg={provider:provider,model:modelName,temperature:temperature,maxTokens:maxTokens,apiKey:apiKey,baseUrl:baseUrl||'https://api.deepseek.com/v1'};
        window.config_bridge.saveConfig(JSON.stringify(cfg));
        window.config_bridge.reconnectAI();
        newModel.active=true;
        appState.models.forEach(function(m){if(m.id!==id)m.active=false;});
        appState.currentModel=newModel;
        updateModelUI();
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
    document.getElementById('apiKeyInput').value=model.apiKey||'';
    document.getElementById('baseUrlInput').value=model.baseUrl||'';
    document.getElementById('temperatureInput').value=(model.temperature!==undefined&&model.temperature!==null)?model.temperature:0.7;
    document.getElementById('maxTokensInput').value=model.maxTokens||2000;
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
    document.getElementById('providerSelect').value='deepseek';
    document.getElementById('modelNameInput').value='';
    document.getElementById('apiKeyInput').value='';
    document.getElementById('baseUrlInput').value='';
    document.getElementById('temperatureInput').value='0.7';
    document.getElementById('maxTokensInput').value='2000';
    document.getElementById('setActiveCheckbox').checked=true;
    var btn=document.querySelector('.btn-primary[onclick="addModel()"]');
    if(btn)btn.innerHTML='<i class="fas fa-plus"></i> 添加模型';
    var cancelBtn=document.getElementById('cancelEditBtn');
    if(cancelBtn)cancelBtn.style.display='none';
}

function switchModel(id){
    var model=appState.models.find(function(m){return m.id===id;});
    if(!model){showToast('模型不存在','error');return;}
    appState.models.forEach(function(m){m.active=(m.id===id);});
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
        var cfg={provider:model.provider,model:model.model,temperature:temperature,maxTokens:model.maxTokens||2000,apiKey:model.apiKey||'',baseUrl:model.baseUrl||''};
        window.config_bridge.saveConfig(JSON.stringify(cfg));
        window.config_bridge.reconnectAI();
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
                var cfg={provider:first.provider,model:first.model,temperature:temp,maxTokens:first.maxTokens||2000,apiKey:first.apiKey||'',baseUrl:first.baseUrl||''};
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
    }, {title:'删除模型', confirmText:'删除', cancelText:'取消', danger:true, icon:'\uD83D\uDDD1\uFE0F'});
}

function testCurrentModel(){
    showToast('正在测试连接...','info');
    if(window.config_bridge){
        var provider=document.getElementById('providerSelect').value;
        var modelName=document.getElementById('modelNameInput').value.trim()||document.getElementById('activeModelName').textContent;
        var apiKey=document.getElementById('apiKeyInput').value.trim();
        var baseUrl=document.getElementById('baseUrlInput').value.trim();
        var cfg={provider:provider,model:modelName,temperature:0.7,maxTokens:2000,apiKey:apiKey,baseUrl:baseUrl};
        window.config_bridge.saveConfig(JSON.stringify(cfg));
        window.config_bridge.reconnectAI();
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