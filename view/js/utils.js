// ============================================
// Utils - 通用工具函数
// ============================================
function showToast(msg,type){var t=document.getElementById('toast'),m=document.getElementById('toastMessage');t.className='toast show '+type;m.textContent=msg;setTimeout(function(){t.classList.remove('show');},2000);}
function toggleSidebar(){
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebarOverlay');
    if (!sidebar) return;
    if (window.innerWidth <= 768) {
        sidebar.classList.toggle('open');
        if (overlay) overlay.classList.toggle('active');
    } else {
        var isCollapsed = sidebar.classList.toggle('collapsed');
        var headerMenuBtn = document.querySelector('.header-menu-btn');
        if (headerMenuBtn) headerMenuBtn.style.display = isCollapsed ? 'block' : 'none';
    }
}
document.getElementById('sidebarOverlay').addEventListener('click',function(){
    var sidebar = document.getElementById('sidebar');
    var overlay = document.getElementById('sidebarOverlay');
    if (sidebar) { sidebar.classList.remove('open'); sidebar.classList.remove('collapsed'); }
    if (overlay) overlay.classList.remove('active');
    var headerMenuBtn = document.querySelector('.header-menu-btn');
    if (headerMenuBtn && window.innerWidth > 768) headerMenuBtn.style.display = 'none';
});
document.addEventListener('keydown',function(e){
    if(e.key==='Escape'){
        closePanel();
        var sidebar = document.getElementById('sidebar');
        if (sidebar) { sidebar.classList.remove('open'); sidebar.classList.remove('collapsed'); }
        var headerMenuBtn = document.querySelector('.header-menu-btn');
        if (headerMenuBtn && window.innerWidth > 768) headerMenuBtn.style.display = 'none';
    }
});
function toggleAttachment(){showToast('附件功能开发中','info');}
function toggleCodeBlock(){showToast('代码块功能开发中','info');}
function showMCPStatus(){showToast('MCP 状态: '+appState.mcpServers.filter(function(s){return s.enabled;}).length+' 个服务器','info');}
function lazyLoadPanel(panelId, url, callback) {
    var el = document.getElementById(panelId);
    if (!el) return;
    if (el.getAttribute('data-loaded')) {
        if (typeof callback === 'function') setTimeout(callback, 50);
        return;
    }
    var xhr = new XMLHttpRequest();
    xhr.open('GET', url, true);
    xhr.onload = function() {
        if (xhr.status >= 200 && xhr.status < 400) {
            el.innerHTML = xhr.responseText;
            el.setAttribute('data-loaded', 'true');
            console.log('[Lazy] 已加载: ' + url);
            if (typeof callback === 'function') callback();
        }
    };
    xhr.onerror = function() { console.warn('[Lazy] 加载失败: ' + url); };
    xhr.send();
}
// 自定义确认对话框（替代原生 confirm，与主题风格一致）
function showConfirmDialog(message, onConfirm, opts){
    opts = opts || {};
    function esc(s){var d=document.createElement('div');d.appendChild(document.createTextNode(String(s==null?'':s)));return d.innerHTML;}
    var overlay=document.createElement('div');
    overlay.id='confirmDialogOverlay';
    overlay.style.cssText='position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:10000;display:flex;align-items:center;justify-content:center;';
    var dialog=document.createElement('div');
    dialog.style.cssText='background:var(--bg-primary,#1a1d23);border:1px solid var(--border-color,#2d3240);border-radius:12px;padding:24px;max-width:380px;width:90%;box-shadow:0 8px 30px rgba(0,0,0,0.4);';
    var dangerColor=opts.danger?'#e5484d':'var(--accent-color,#8ab4f8)';
    dialog.innerHTML=
        '<div style="display:flex;align-items:center;margin-bottom:14px;">'+
            '<div style="font-size:20px;margin-right:10px;">'+(opts.icon||'⚠️')+'</div>'+
            '<div style="font-size:15px;font-weight:600;color:var(--text-primary,#e8eaed);">'+esc(opts.title||'操作确认')+'</div>'+
        '</div>'+
        '<div style="font-size:13px;line-height:1.7;color:var(--text-secondary,#b0b6c0);word-break:break-all;margin-bottom:18px;">'+esc(message)+'</div>'+
        '<div style="display:flex;gap:10px;justify-content:flex-end;border-top:1px solid var(--border-color,#2d3240);padding-top:14px;">'+
            '<button id="confirmDialogCancel" style="padding:8px 20px;border:1px solid var(--border-color,#2d3240);border-radius:6px;background:var(--bg-secondary,#22252b);color:var(--text-primary,#e8eaed);cursor:pointer;font-size:13px;">'+esc(opts.cancelText||'取消')+'</button>'+
            '<button id="confirmDialogOk" style="padding:8px 20px;border:none;border-radius:6px;background:'+dangerColor+';color:#fff;cursor:pointer;font-size:14px;font-weight:600;">'+esc(opts.confirmText||'确定')+'</button>'+
        '</div>';
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);
    function close(){overlay.remove();}
    document.getElementById('confirmDialogOk').onclick=function(){close();if(typeof onConfirm==='function')onConfirm();};
    document.getElementById('confirmDialogCancel').onclick=close;
    overlay.onclick=function(e){if(e.target===overlay)close();};
    var onKey=function(e){if(e.key==='Escape'){close();document.removeEventListener('keydown',onKey);}};
    document.addEventListener('keydown',onKey);
    return overlay;
}

