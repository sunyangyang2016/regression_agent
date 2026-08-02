// ============================================
// Skills - 技能管理
// ============================================

function escHtml(str){
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(String(str||'')));
    return d.innerHTML;
}

function buildSkillDetailHtml(s){
    var detail = s.detail || {};
    var html = '';
    if(s.source === 'markdown'){
        // MD 技能：显示 Markdown 正文内容
        var content = detail.content || '';
        if(content){
            html += '<div class="skill-detail-section">' +
                '<div class="skill-detail-label"><i class="fas fa-file-alt"></i> 详细说明</div>' +
                '<pre class="skill-detail-content">' + escHtml(content) + '</pre>' +
            '</div>';
        }
        if(detail.filepath){
            html += '<div class="skill-detail-row"><span class="skill-detail-label">文件路径</span><span class="skill-detail-value">' + escHtml(detail.filepath) + '</span></div>';
        }
    } else {
        // Python 技能：显示元数据信息
        var rows = [];
        if(detail.version) rows.push(['版本', detail.version]);
        if(detail.category) rows.push(['分类', detail.category]);
        if(detail.priority !== undefined && detail.priority !== null) rows.push(['优先级', detail.priority]);
        if(detail.execution_count !== undefined && detail.execution_count !== null) rows.push(['执行次数', detail.execution_count]);
        if(detail.created_at) rows.push(['创建时间', detail.created_at]);
        if(rows.length){
            html += '<div class="skill-detail-section">' +
                '<div class="skill-detail-label"><i class="fas fa-info-circle"></i> 基本信息</div>';
            rows.forEach(function(r){
                html += '<div class="skill-detail-row"><span class="skill-detail-label">' + escHtml(r[0]) + '</span><span class="skill-detail-value">' + escHtml(r[1]) + '</span></div>';
            });
            html += '</div>';
        }
        if(detail.input_schema){
            html += '<div class="skill-detail-section">' +
                '<div class="skill-detail-label"><i class="fas fa-keyboard"></i> 参数 Schema</div>' +
                '<pre class="skill-detail-content">' + escHtml(JSON.stringify(detail.input_schema, null, 2)) + '</pre>' +
            '</div>';
        }
        if(detail.triggers && detail.triggers.length > 0){
            html += '<div class="skill-detail-section">' +
                '<div class="skill-detail-label"><i class="fas fa-bolt"></i> 触发器</div>' +
                '<pre class="skill-detail-content">' + escHtml(JSON.stringify(detail.triggers, null, 2)) + '</pre>' +
            '</div>';
        }
    }
    return html;
}

function renderSkills(){
    var c=document.getElementById('skillList');if(!c)return;
    var items=appState.skills||[];
    if(items.length===0){
        c.innerHTML='<div style="text-align:center;padding:20px;color:var(--text-muted);">暂无技能</div>';
        return;
    }
    c.innerHTML=items.map(function(s, i){
        var iconMap={development:'fa-code',data:'fa-chart-line',writing:'fa-pen-fancy',utility:'fa-tools',communication:'fa-envelope',productivity:'fa-check-double',creativity:'fa-lightbulb',analysis:'fa-search',general:'fa-file-alt',md:'fa-file-alt'};
        var iconName=iconMap[s.category]||'fa-file-alt';
        var sourceLabel=s.source==='python'?'Python 技能':'MD 技能';
        var sourceClass=s.source==='python'?'tag-blue':'tag-green';
        var detailHtml = buildSkillDetailHtml(s);
        return '<div class="item-row" onclick="toggleSkillDetail('+i+')" style="cursor:pointer;">'+
            '<div class="icon builtin"><i class="fas '+iconName+'"></i></div>'+
            '<div class="info">'+
                '<div class="name">'+escHtml(s.name)+'</div>'+
                '<div class="desc">'+escHtml(s.description||'')+'</div>'+
                '<div class="tags"><span class="tag active">'+(s.category||'general')+'</span><span class="tag '+sourceClass+'">'+sourceLabel+'</span>'+
                (s.version?' <span class="tag">v'+s.version+'</span>':'')+
                '</div>'+
            '</div>'+
            '<label class="switch" onclick="event.stopPropagation()"><input type="checkbox" '+(s.enabled!==false?'checked':'')+' onchange="toggleSkill(\''+escHtml(s.name)+'\', this)"><span class="slider"></span></label>'+
            '<button class="skill-remove-btn" title="删除技能" onclick="event.stopPropagation();removeSkill(\''+escHtml(s.name)+'\')"><i class="fas fa-trash"></i></button>'+
            '<span class="skill-expand-icon"><i class="fas fa-chevron-down" id="skillIcon'+i+'"></i></span>'+
        '</div>'+
        (detailHtml ? '<div class="skill-detail" id="skillDetail'+i+'" style="display:none;">'+detailHtml+'</div>' : '');
    }).join('');
}

function toggleSkillDetail(index){
    var detail = document.getElementById('skillDetail' + index);
    var icon = document.getElementById('skillIcon' + index);
    if (detail) {
        var isOpen = detail.style.display === 'block';
        detail.style.display = isOpen ? 'none' : 'block';
        if (icon) {
            icon.style.transform = isOpen ? 'rotate(0deg)' : 'rotate(180deg)';
        }
    }
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
    }, {title:'删除技能', confirmText:'删除', cancelText:'取消', danger:true, icon:'🗑️'});
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
    if(!file){showToast('请选择一个 .md 文件','error');return;}
    if(!file.name.endsWith('.md')){showToast('请上传 .md 格式的 Markdown 文件','error');return;}
    var reader=new FileReader();
    reader.onload=function(e){
        var content=e.target.result;
        var finalName=nameInput.value.trim()||file.name.replace('.md','');
        var skillDesc=descInput.value.trim()||'从 Markdown 文件导入的技能';
        var newSkill={name:finalName,description:skillDesc,source:'markdown',category:'general',enabled:true,version:'1.0.0',tags:[]};
        if(window.skill_bridge && typeof window.skill_bridge.on_upload_md==='function'){
            var ok=window.skill_bridge.on_upload_md(finalName, skillDesc, content);
            if(ok===false){
                showToast('⚠️ 技能 "'+finalName+'" 已存在或上传失败','error');
                return;
            }
            setTimeout(loadSkillsFromBridge, 150);
        } else {
            appState.skills.push(newSkill);
            renderSkills();
        }
        nameInput.value='';descInput.value='';fileInput.value='';
        var nameEl=document.getElementById('skillFileName');if(nameEl){nameEl.textContent='未选择文件';}
        showToast('✅ 技能 "'+finalName+'" 已从 '+file.name+' 导入','success');
    };
    reader.onerror=function(){showToast('读取文件失败，请重试','error');};
    reader.readAsText(file);
}