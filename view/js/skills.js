// ============================================
// Skills - 技能管理（内建/注册双 tab + 目录上传）
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
        // MD 技能：显示 SKILL.md 正文内容
        var content = detail.content || '';
        if(content){
            html += '<div class="skill-detail-section">' +
                '<div class="skill-detail-label"><i class="fas fa-file-alt"></i> 详细说明</div>' +
                '<pre class="skill-detail-content">' + escHtml(content) + '</pre>' +
            '</div>';
        }
        if(detail.filepath){
            html += '<div class="skill-detail-row"><span class="skill-detail-label">SKILL.md</span><span class="skill-detail-value">' + escHtml(detail.filepath) + '</span></div>';
        }
        // 资源文件列表
        var sections = [
            {key:'scripts', label:'脚本 (scripts)', icon:'fa-terminal'},
            {key:'references', label:'参考文档 (references)', icon:'fa-book'},
            {key:'assets', label:'资源文件 (assets)', icon:'fa-paperclip'}
        ];
        sections.forEach(function(sec){
            var files = detail[sec.key] || [];
            if(files.length > 0){
                html += '<div class="skill-detail-section">' +
                    '<div class="skill-detail-label"><i class="fas ' + sec.icon + '"></i> ' + sec.label + '</div>' +
                    '<div class="skill-detail-files">';
                files.forEach(function(f){
                    html += '<div class="skill-detail-file"><i class="fas fa-file"></i>' + escHtml(f) + '</div>';
                });
                html += '</div></div>';
            }
        });
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

function buildSkillItemHtml(s){
    var iconMap={development:'fa-code',data:'fa-chart-line',writing:'fa-pen-fancy',utility:'fa-tools',communication:'fa-envelope',productivity:'fa-check-double',creativity:'fa-lightbulb',analysis:'fa-search',general:'fa-file-alt',md:'fa-folder'};
    var iconName=iconMap[s.category]||'fa-file-alt';
    var sourceLabel=s.source==='python'?'Python 技能':'MD 技能';
    var sourceClass=s.source==='python'?'tag-blue':'tag-green';
    var detailHtml = buildSkillDetailHtml(s);
    // 内建技能（python）不显示删除按钮；受保护的内置 MD 技能也不显示删除按钮；仅普通注册技能可删除
    var removeBtn = (s.source === 'markdown' && !s.protected)
        ? '<button class="skill-remove-btn" title="删除技能" onclick="event.stopPropagation();removeSkill(\''+escHtml(s.name)+'\')"><i class="fas fa-trash"></i></button>'
        : '';
    return '<div class="item-row" onclick="toggleSkillDetail(\''+escHtml(s.name)+'\')" style="cursor:pointer;">'+
        '<div class="icon builtin"><i class="fas '+iconName+'"></i></div>'+
        '<div class="info">'+
            '<div class="name">'+escHtml(s.name)+'</div>'+
            '<div class="desc">'+escHtml(s.description||'')+'</div>'+
            '<div class="tags"><span class="tag active">'+(s.category||'general')+'</span><span class="tag '+sourceClass+'">'+sourceLabel+'</span>'+
            (s.version?' <span class="tag">v'+s.version+'</span>':'')+
            '</div>'+
        '</div>'+
        '<label class="switch" onclick="event.stopPropagation()"><input type="checkbox" '+(s.enabled!==false?'checked':'')+' onchange="toggleSkill(\''+escHtml(s.name)+'\', this)"><span class="slider"></span></label>'+
        removeBtn+
        '<span class="skill-expand-icon"><i class="fas fa-chevron-down" data-skill-name="'+escHtml(s.name)+'"></i></span>'+
    '</div>'+
    (detailHtml ? '<div class="skill-detail" data-skill-name="'+escHtml(s.name)+'" style="display:none;">'+detailHtml+'</div>' : '');
}

function renderSkills(){
    var builtinEl=document.getElementById('skillListBuiltin');
    var registeredEl=document.getElementById('skillListRegistered');
    if(!builtinEl&&!registeredEl)return;
    var items=appState.skills||[];
    var builtin=[],registered=[];
    items.forEach(function(s){
        if(s.source==='markdown'){
            registered.push(s);
        } else {
            builtin.push(s);
        }
    });
    if(builtinEl){
        builtinEl.innerHTML=builtin.length===0
            ? '<div style="text-align:center;padding:20px;color:var(--text-muted);">暂无内建技能</div>'
            : builtin.map(buildSkillItemHtml).join('');
    }
    if(registeredEl){
        registeredEl.innerHTML=registered.length===0
            ? '<div style="text-align:center;padding:20px;color:var(--text-muted);">暂无注册技能（上传技能目录后显示）</div>'
            : registered.map(buildSkillItemHtml).join('');
    }
}

function switchSkillSubTab(tab){
    // 技能面板内的子 tab 通过容器定位：先找 skillListBuiltin/skillListRegistered 祖先
    var builtinBtn=null,registeredBtn=null;
    var builtinEl=document.getElementById('skillListBuiltin');
    if(builtinEl){
        var btns=builtinEl.parentElement.querySelectorAll('.mcp-sub-tab');
        btns.forEach(function(b){
            if(b.dataset.subtab==='builtin')builtinBtn=b;
            if(b.dataset.subtab==='registered')registeredBtn=b;
        });
    }
    if(builtinBtn)builtinBtn.classList.toggle('active',tab==='builtin');
    if(registeredBtn)registeredBtn.classList.toggle('active',tab==='registered');
    var bEl=document.getElementById('skillListBuiltin');
    var rEl=document.getElementById('skillListRegistered');
    if(bEl)bEl.style.display=tab==='builtin'?'block':'none';
    if(rEl)rEl.style.display=tab==='registered'?'block':'none';
    // 上传技能目录区域仅显示在"注册技能" tab 下
    var uploadEl=document.getElementById('skillUploadSection');
    if(uploadEl)uploadEl.style.display=tab==='registered'?'block':'none';
}

function toggleSkillDetail(name){
    var detail=null,icon=null;
    // 查两个列表中的详情容器和箭头图标（按 data-skill-name 定位）
    var detailEls=document.querySelectorAll('.skill-detail[data-skill-name="'+name+'"]');
    if(detailEls.length>0)detail=detailEls[0];
    var iconEls=document.querySelectorAll('.skill-expand-icon i[data-skill-name="'+name+'"]');
    if(iconEls.length>0)icon=iconEls[0];
    if(detail){
        var isOpen=detail.style.display==='block';
        detail.style.display=isOpen?'none':'block';
        if(icon){
            icon.style.transform=isOpen?'rotate(0deg)':'rotate(180deg)';
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

// ============================================
// 目录上传技能包
// ============================================

function skillDirChanged(input){
    var nameEl=document.getElementById('skillDirName');
    if(nameEl){
        var files = input.files || [];
        if(files.length > 0){
            // 取第一个文件的相对路径的第一段作为目录名
            var firstRel = files[0].webkitRelativePath || '';
            var dirName = firstRel.split('/')[0];
            nameEl.textContent = dirName ? ('已选: ' + dirName + ' (' + files.length + ' 个文件)') : '已选择目录';
        } else {
            nameEl.textContent='未选择目录';
        }
    }
}

function uploadSkillDir(){
    var fileInput=document.getElementById('skillDirInput');
    var files=fileInput.files;
    if(!files || files.length===0){
        showToast('请先选择技能目录','error');
        return;
    }
    // 从 webkitRelativePath 提取顶层目录名
    var firstRel = files[0].webkitRelativePath || '';
    var dirName = firstRel.split('/')[0];
    if(!dirName){
        showToast('无法识别目录名','error');
        return;
    }

    // 检查是否存在 SKILL.md
    var hasSkillMd = false;
    for(var i=0; i<files.length; i++){
        var rel = files[i].webkitRelativePath || '';
        var parts = rel.split('/');
        parts.shift(); // 移除顶层目录名
        var relPath = parts.join('/');
        if(relPath === 'SKILL.md'){
            hasSkillMd = true;
            break;
        }
    }
    if(!hasSkillMd){
        showToast('⚠️ 技能目录中必须包含 SKILL.md 文件','error');
        return;
    }

    // 前置重名校验：与已存在技能（内置 + 已注册）重名则拒绝上传
    var conflict = (appState.skills || []).some(function(s){ return s.name === dirName; });
    if(conflict){
        showToast('⚠️ 技能 "'+dirName+'" 已存在（内置或已注册），不能重复上传','error');
        return;
    }

    // 递归读取所有文件为 {相对路径: 内容}
    var fileMap = {};
    var pendingCount = files.length;
    var readError = false;

    files.forEach(function(file){
        var rel = file.webkitRelativePath || file.name;
        var parts = rel.split('/');
        parts.shift(); // 移除顶层目录名
        var relPath = parts.join('/');
        var reader = new FileReader();
        reader.onload = function(e){
            fileMap[relPath] = e.target.result;
            pendingCount--;
            if(pendingCount === 0){
                if(readError){
                    showToast('部分文件读取失败','error');
                    return;
                }
                doSubmitSkillDir(dirName, fileMap);
            }
        };
        reader.onerror = function(){
            readError = true;
            pendingCount--;
            if(pendingCount === 0){
                showToast('部分文件读取失败','error');
            }
        };
        reader.readAsText(file);
    });
}

function doSubmitSkillDir(name, fileMap){
    if(!window.skill_bridge){
        showToast('❌ 技能桥接不可用','error');
        return;
    }
    try{
        var filesJson = JSON.stringify(fileMap);
        var ok = window.skill_bridge.on_upload_skill_dir(name, filesJson);
        if(ok === false){
            showToast('⚠️ 技能 "'+name+'" 已存在或上传失败','error');
            return;
        }
        // 清空选择
        var fileInput=document.getElementById('skillDirInput');
        if(fileInput) fileInput.value='';
        var nameEl=document.getElementById('skillDirName');
        if(nameEl) nameEl.textContent='未选择目录';
        setTimeout(loadSkillsFromBridge, 150);
        showToast('✅ 技能 "'+name+'" 已上传 ('+Object.keys(fileMap).length+' 个文件)','success');
    }catch(e){
        console.warn('[Skills] upload error:',e);
        showToast('❌ 上传失败: '+e.message,'error');
    }
}