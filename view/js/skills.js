// ============================================
// Skills - 技能管理
// ============================================

function escHtml(str){
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(String(str||'')));
    return d.innerHTML;
}

function renderSkills(){
    var c=document.getElementById('skillList');if(!c)return;
    var items=appState.skills||[];
    if(items.length===0){
        c.innerHTML='<div style="text-align:center;padding:20px;color:var(--text-muted);">\u6682\u65E0\u6280\u80FD</div>';
        return;
    }
    c.innerHTML=items.map(function(s){
        var iconMap={development:'fa-code',data:'fa-chart-line',writing:'fa-pen-fancy',utility:'fa-tools',communication:'fa-envelope',productivity:'fa-check-double',creativity:'fa-lightbulb',analysis:'fa-search',general:'fa-file-alt'};
        var iconName=iconMap[s.category]||'fa-file-alt';
        var sourceLabel=s.source==='python'?'Python \u6280\u80FD':'MD \u6280\u80FD';
        var sourceClass=s.source==='python'?'tag-blue':'tag-green';
        return '<div class="item-row">'+
            '<div class="icon builtin"><i class="fas '+iconName+'"></i></div>'+
            '<div class="info">'+
                '<div class="name">'+escHtml(s.name)+'</div>'+
                '<div class="desc">'+escHtml(s.description||'')+'</div>'+
                '<div class="tags"><span class="tag active">'+(s.category||'general')+'</span><span class="tag '+sourceClass+'">'+sourceLabel+'</span>'+
                (s.version?' <span class="tag">v'+s.version+'</span>':'')+
                '</div>'+
            '</div>'+
            '<label class="switch"><input type="checkbox" '+(s.enabled!==false?'checked':'')+' onchange="toggleSkill(\''+escHtml(s.name)+'\', this)"><span class="slider"></span></label>'+
            '<button class="skill-remove-btn" title="删除技能" onclick="removeSkill(\''+escHtml(s.name)+'\')"><i class="fas fa-trash"></i></button>'+
        '</div>';
    }).join('');
}

function loadSkillsFromBridge(){
    if(!window.skill_bridge){console.warn('[Skills] skill_bridge not available');return;}
    try{
        var raw=window.skill_bridge.getSkills();
        var data=JSON.parse(raw);
        if(data&&data.length>0){
            appState.skills=data;
            renderSkills();
        }
    }catch(e){console.warn('[Skills] load error:',e);}
}

function toggleSkill(name, checkbox){
    if(!window.skill_bridge){if(checkbox){checkbox.checked=!checkbox.checked;}return;}
    try{
        window.skill_bridge.on_toggle_skill(name);
        // 后端确认后重新拉取，保持显示与后端一致
        setTimeout(loadSkillsFromBridge, 120);
    }catch(e){
        console.warn('[Skills] toggle error:',e);
        if(checkbox){checkbox.checked=!checkbox.checked;}
    }
}

function removeSkill(name){
    if(!window.skill_bridge){return;}
    showConfirmDialog('确定删除技能 "'+name+'" 吗？', function(){
        try{
            window.skill_bridge.on_remove_skill(name);
            // 本地立即移除并渲染
            if(appState.skills){
                appState.skills=appState.skills.filter(function(s){return s.name!==name;});
                renderSkills();
            }
            setTimeout(loadSkillsFromBridge, 150);
        }catch(e){
            console.warn('[Skills] remove error:',e);
        }
    }, {title:'删除技能', confirmText:'删除', cancelText:'取消', danger:true, icon:'\uD83D\uDDD1\uFE0F'});
}

function skillFileChanged(input){
    var nameEl=document.getElementById('skillFileName');
    if(nameEl){nameEl.textContent=(input.files&&input.files[0])?input.files[0].name:'未选择文件';}
}

function uploadSkillMD(){
    var fileInput=document.getElementById('skillFileInput');
    var nameInput=document.getElementById('skillNameInput');
    var descInput=document.getElementById('skillDescInput');
    var file=fileInput.files[0];
    if(!file){showToast('\u8BF7\u9009\u62E9\u4E00\u4E2A .md \u6587\u4EF6','error');return;}
    if(!file.name.endsWith('.md')){showToast('\u8BF7\u4E0A\u4F20 .md \u683C\u5F0F\u7684 Markdown \u6587\u4EF6','error');return;}
    var reader=new FileReader();
    reader.onload=function(e){
        var content=e.target.result;
        var finalName=nameInput.value.trim()||file.name.replace('.md','');
        var skillDesc=descInput.value.trim()||'\u4ECE Markdown \u6587\u4EF6\u5BFC\u5165\u7684\u6280\u80FD';
        var newSkill={name:finalName,description:skillDesc,source:'markdown',category:'general',enabled:true,version:'1.0.0',tags:[]};
        if(window.skill_bridge && typeof window.skill_bridge.on_upload_md==='function'){
            var ok=window.skill_bridge.on_upload_md(finalName, skillDesc, content);
            if(ok===false){
                showToast('\u26A0\uFE0F \u6280\u80FD "'+finalName+'" \u5DF2\u5B58\u5728\u6216\u4E0A\u4F20\u5931\u8D25','error');
                return;
            }
            setTimeout(loadSkillsFromBridge, 150);
        } else {
            appState.skills.push(newSkill);
            renderSkills();
        }
        nameInput.value='';descInput.value='';fileInput.value='';
        var nameEl=document.getElementById('skillFileName');if(nameEl){nameEl.textContent='未选择文件';}
        showToast('\u2705 \u6280\u80FD "'+finalName+'" \u5DF2\u4ECE '+file.name+' \u5BFC\u5165','success');
    };
    reader.onerror=function(){showToast('\u8BFB\u53D6\u6587\u4EF6\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5','error');};
    reader.readAsText(file);
}