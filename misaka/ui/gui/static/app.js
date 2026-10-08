"use strict";
const $ = (s, root=document) => root.querySelector(s);
const $$ = (s, root=document) => [...root.querySelectorAll(s)];
const fragment = new URLSearchParams(location.hash.slice(1));
const token = fragment.get('token') || sessionStorage.getItem('misaka-token') || '';
if (token) sessionStorage.setItem('misaka-token', token);
history.replaceState(null, '', location.pathname);
window.addEventListener('hashchange',()=>{if(new URLSearchParams(location.hash.slice(1)).has('token'))location.reload();});
let state = null, workspace = '', selected = null, selectedChat = null, view = 'chat', screenBusy = false, stateBusy = false;
let lastScreen = '', lastSize = '', inputChain = Promise.resolve(), refreshTick = 0;
let guiClosed = false, readOnlyView = null;
let localWorkspace = localStorage.getItem('misaka-workspace') || '';
// The home composer creates its chat on the first message; these are its pending choices.
let homeRole = null, homeModel = null, homeThinking = null, rosterCache = null;
const chats = {};   // chat_id -> {cursor, items, results, exec, meta, streaming, queued, outbox}
const titles = {chat:'对话',research:'研究',board:'任务看板',team:'协作成员',documents:'材料与文件',skills:'技能库',settings:'设置',legacy:'终端进程'};
const statuses = {ready:'待启动',todo:'待处理',running:'运行中',review:'审查中',done:'已完成',failed:'失败',stopped:'已停止',blocked:'等待处理',triage:'需要介入',idle:'等待输入',working:'处理中',saved:'已保存',active:'进行中',waiting_input:'等待确认',stopping:'正在收尾',completed:'已完成',queued:'排队中',pending:'待处理',cancelled:'已暂停'};
const statusText = s => statuses[s] || s || '未知';
const statusTone = s => ['running','review','working','active','stopping','waiting_input'].includes(s)?'busy':['failed','blocked','triage'].includes(s)?'warn':['done','completed'].includes(s)?'ok':'';
const samePath = (a,b) => navigator.platform.toLowerCase().includes('win') ? String(a).replaceAll('\\','/').toLowerCase()===String(b).replaceAll('\\','/').toLowerCase() : a===b;
const baseName = path => String(path).replace(/[\\/]$/, '').split(/[\\/]/).pop();
const sleep = ms => new Promise(r=>setTimeout(r,ms));
function el(tag, cls='', text='', ...more) {
  const n=document.createElement(tag);if(cls)n.className=cls;
  for (const c of [text,...more]) if(c instanceof Node)n.append(c);else if(c!==''&&c!=null&&c!==false)n.append(String(c));
  return n;
}
function button(text, action, cls='btn sm', iconName='') {const n=el('button',cls);n.type='button';if(iconName)n.append(icon(iconName));if(text)n.append(text);n.onclick=e=>{e.stopPropagation();guard(action,n);};return n;}
function empty(parent,text) {parent.replaceChildren(el('div','empty',text));}
async function guard(fn, target) {if(target)target.disabled=true;try{return await fn();}catch(e){toast(e.message,true);}finally{if(target)target.disabled=false;}}
async function api(action, data={}, timeout=45000) {
  const response=await fetch('/api/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-Misaka-Token':token},body:JSON.stringify({...(workspace?{workspace}:{}),...data}),signal:AbortSignal.timeout(timeout)});
  const result=await response.json();if(!response.ok)throw new Error(result.error||'操作失败');return result;
}
function jsonStored(key,fallback){try{return JSON.parse(localStorage.getItem(key))||fallback;}catch{return fallback;}}

/* ---------- 图标 ---------- */
const ICONS = {
  home:'<path d="m3 10 9-7 9 7"/><path d="M5 9v11h5v-6h4v6h5V9"/>',
  chats:'<path d="M4 4h13a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9l-5 4v-4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/><path d="M7 8h8M7 12h5"/>',
  sidebar:'<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9.5 4v16"/>',
  compose:'<path d="M12 20h8"/><path d="M16.4 4.6a2 2 0 0 1 2.9 2.9L8 18.8l-3.8.9.9-3.8Z"/>',
  search:'<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
  folder:'<path d="M3.5 7.5a2 2 0 0 1 2-2h3.7l2 2h7.3a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2Z"/>',
  chevrons:'<path d="m8 9.5 4-4 4 4"/><path d="m8 14.5 4 4 4-4"/>',
  'chevron-down':'<path d="m6 9 6 6 6-6"/>',
  'chevron-right':'<path d="m9 6 6 6-6 6"/>',
  research:'<circle cx="6" cy="6.5" r="2.5"/><circle cx="18" cy="6.5" r="2.5"/><circle cx="12" cy="17.5" r="2.5"/><path d="M8.5 6.5h7"/><path d="m7.3 8.7 3.4 6.6"/><path d="m16.7 8.7-3.4 6.6"/>',
  board:'<rect x="3.5" y="4" width="4.5" height="12" rx="1.3"/><rect x="9.75" y="4" width="4.5" height="8" rx="1.3"/><rect x="16" y="4" width="4.5" height="15" rx="1.3"/>',
  team:'<circle cx="9" cy="8.5" r="3.2"/><path d="M3 19.5c.4-3.2 2.9-5.5 6-5.5s5.6 2.3 6 5.5"/><circle cx="17" cy="9.5" r="2.4"/><path d="M16.5 14.1c2.4.2 4.2 2.2 4.5 5.4"/>',
  library:'<path d="M3 5.5h5.5A3.5 3.5 0 0 1 12 9v10.5a2.8 2.8 0 0 0-2.8-2.8H3Z"/><path d="M21 5.5h-5.5A3.5 3.5 0 0 0 12 9v10.5a2.8 2.8 0 0 1 2.8-2.8H21Z"/>',
  skills:'<path d="M12 3.5 14 10l6.5 2-6.5 2-2 6.5-2-6.5-6.5-2L10 10Z"/>',
  settings:'<path d="M4 7h9"/><path d="M17 7h3"/><circle cx="15" cy="7" r="2"/><path d="M4 17h3"/><path d="M11 17h9"/><circle cx="9" cy="17" r="2"/>',
  copy:'<rect x="8.5" y="8.5" width="11" height="11" rx="2.2"/><path d="M15.5 8.5V6.7a2.2 2.2 0 0 0-2.2-2.2H6.7a2.2 2.2 0 0 0-2.2 2.2v6.6a2.2 2.2 0 0 0 2.2 2.2h1.8"/>',
  check:'<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  more:'<circle cx="5.5" cy="12" r="1.3" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.3" fill="currentColor" stroke="none"/><circle cx="18.5" cy="12" r="1.3" fill="currentColor" stroke="none"/>',
  'arrow-up':'<path d="M12 19V5.5"/><path d="m6 11 6-6 6 6"/>',
  'arrow-down':'<path d="M12 5v13.5"/><path d="m6 13 6 6 6-6"/>',
  'arrow-up-right':'<path d="M7 17 17 7"/><path d="M8.5 7H17v8.5"/>',
  stop:'<rect x="6" y="6" width="12" height="12" rx="2.5"/>',
  plus:'<path d="M12 5v14"/><path d="M5 12h14"/>',
  image:'<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><circle cx="9" cy="10" r="1.7"/><path d="m20.5 15.5-4.8-4.8L6 19.5"/>',
  x:'<path d="m6.5 6.5 11 11"/><path d="m17.5 6.5-11 11"/>',
  terminal:'<rect x="3" y="4.5" width="18" height="15" rx="2.5"/><path d="m7.5 9.5 3 2.5-3 2.5"/><path d="M13 15h3.5"/>',
  file:'<path d="M14 3.5H7.5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V8Z"/><path d="M14 3.5V8h4.5"/><path d="M9 13h6"/><path d="M9 16.5h4"/>',
  pencil:'<path d="M16.4 4.6a2 2 0 0 1 2.9 2.9L8 18.8l-3.8.9.9-3.8Z"/><path d="m14.5 6.5 3 3"/>',
  globe:'<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/><path d="M12 3.5c2.3 2.4 3.5 5.2 3.5 8.5s-1.2 6.1-3.5 8.5c-2.3-2.4-3.5-5.2-3.5-8.5s1.2-6.1 3.5-8.5Z"/>',
  wrench:'<path d="M14.6 6.4a4 4 0 0 0-5.3 5.2l-5 5a1.6 1.6 0 0 0 2.3 2.3l5-5a4 4 0 0 0 5.2-5.3l-2.4 2.4-2.2-.5-.5-2.2Z"/>',
  bulb:'<path d="M9.5 17.5h5"/><path d="M10.5 20.5h3"/><path d="M12 3.5a5.5 5.5 0 0 0-3.3 9.9c.6.5.8 1 .8 1.7v.4h5v-.4c0-.7.3-1.3.8-1.7A5.5 5.5 0 0 0 12 3.5Z"/>',
  history:'<path d="M4 12a8 8 0 1 0 2.4-5.7L4 8.5"/><path d="M4 4v4.5h4.5"/><path d="M12 8v4.2l3 1.8"/>',
  alert:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7.8v5"/><path d="M12 16.2v.01"/>',
  power:'<path d="M12 3.5v8"/><path d="M6.6 6.8a7.5 7.5 0 1 0 10.8 0"/>',
  compress:'<path d="M4 12h16"/><path d="m9 4.5 3 3 3-3"/><path d="M12 7.5V3"/><path d="m9 19.5 3-3 3 3"/><path d="M12 16.5V21"/>',
  sun:'<circle cx="12" cy="12" r="3.8"/><path d="M12 3v1.8M12 19.2V21M3 12h1.8M19.2 12H21M5.6 5.6l1.3 1.3M17.1 17.1l1.3 1.3M5.6 18.4l1.3-1.3M17.1 6.9l1.3-1.3"/>',
  moon:'<path d="M19.5 14.5A7.5 7.5 0 0 1 9.5 4.5a7.5 7.5 0 1 0 10 10Z"/>',
  monitor:'<rect x="3" y="4.5" width="18" height="12" rx="2"/><path d="M8.5 20h7"/><path d="M12 16.5V20"/>',
  refresh:'<path d="M19.5 11A7.5 7.5 0 0 0 6 7.2L4.5 9"/><path d="M4.5 4.5V9H9"/><path d="M4.5 13A7.5 7.5 0 0 0 18 16.8l1.5-1.8"/><path d="M19.5 19.5V15H15"/>',
  play:'<path d="M8 5.5v13l10-6.5Z"/>',
  pause:'<path d="M9 5.5v13"/><path d="M15 5.5v13"/>',
  model:'<path d="M12 3.5 19.5 7.8v8.4L12 20.5l-7.5-4.3V7.8Z"/><path d="m12 12 7.5-4.2"/><path d="M12 12v8.5"/><path d="M12 12 4.5 7.8"/>',
  layers:'<path d="m12 4 8.5 4.5L12 13 3.5 8.5Z"/><path d="m3.5 12.5 8.5 4.5 8.5-4.5"/><path d="m3.5 16.5 8.5 4.5 8.5-4.5"/>',
  clock:'<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  gauge:'<path d="M4.5 17a8.5 8.5 0 1 1 15 0"/><path d="m12 13 3.5-4"/><circle cx="12" cy="13.5" r="1.3"/>',
  task:'<rect x="4.5" y="4" width="15" height="16.5" rx="2"/><path d="m8.5 12 2.3 2.3 4.7-4.6"/>',
  quote:'<path d="M9.5 7.5H6A1.5 1.5 0 0 0 4.5 9v3A1.5 1.5 0 0 0 6 13.5h2.5v1A2.5 2.5 0 0 1 6 17"/><path d="M19.5 7.5H16a1.5 1.5 0 0 0-1.5 1.5v3a1.5 1.5 0 0 0 1.5 1.5h2.5v1A2.5 2.5 0 0 1 16 17"/>',
  tree:'<path d="M5 4.5v13a2 2 0 0 0 2 2h2"/><path d="M5 9.5h4"/><rect x="11" y="7.5" width="8" height="4" rx="1.2"/><rect x="11" y="17.5" width="8" height="4" rx="1.2"/>',
  dot:'<circle cx="12" cy="12" r="2.2" fill="currentColor" stroke="none"/>',
};
function icon(name, cls='') {
  const n=document.createElementNS('http://www.w3.org/2000/svg','svg');
  n.setAttribute('viewBox','0 0 24 24');n.setAttribute('class','i'+(cls?' '+cls:''));n.setAttribute('aria-hidden','true');
  n.innerHTML=ICONS[name]||ICONS.dot;return n;
}
for (const n of $$('i[data-icon]')) n.replaceWith(icon(n.dataset.icon, n.className));

/* ---------- 主题 ---------- */
function applyTheme(choice) {
  if (choice==='light'||choice==='dark') document.documentElement.dataset.theme=choice;
  else {delete document.documentElement.dataset.theme;choice='system';}
  localStorage.setItem('misaka-theme',choice);
  $$('[data-theme-choice]').forEach(b=>b.classList.toggle('active',b.dataset.themeChoice===choice));
}
applyTheme(localStorage.getItem('misaka-theme')||'system');
$$('[data-theme-choice]').forEach(b=>b.onclick=()=>applyTheme(b.dataset.themeChoice));

/* ---------- 提示、对话框与弹出菜单 ---------- */
function toast(text,error=false) {
  const box=$('#toasts'), n=el('div','toast'+(error?' error':''));
  n.append(icon(error?'alert':'check'), el('span','',String(text)));
  box.append(n);while(box.children.length>3)box.firstElementChild.remove();
  setTimeout(()=>{n.classList.add('out');setTimeout(()=>n.remove(),260);},error?8000:3200);
}
function modal(title, contents) {closePopover();$('#dialog-title').textContent=title;$('#dialog-body').replaceChildren(contents);if(!$('#dialog').open)$('#dialog').showModal();}
function closeDialog() {if($('#dialog').open)$('#dialog').close();}
$('#dialog-close').onclick=closeDialog;
let dialogBackdropDown=false;
function outsideDialog(e){const r=$('#dialog').getBoundingClientRect();return e.target===$('#dialog')&&(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom);}
$('#dialog').addEventListener('pointerdown',e=>{dialogBackdropDown=e.button===0&&outsideDialog(e);});
$('#dialog').addEventListener('pointercancel',()=>{dialogBackdropDown=false;});
$('#dialog').addEventListener('click',e=>{const dismiss=dialogBackdropDown&&outsideDialog(e);dialogBackdropDown=false;if(dismiss)closeDialog();});
$('#dialog').addEventListener('close',()=>{dialogBackdropDown=false;closePopover();});
function confirmAction(title,text,action,{label='确认',danger=false}={}) {
  const box=el('div'), actions=el('div','dialog-actions');
  actions.append(button('取消',closeDialog,'btn ghost'),button(label,async()=>{closeDialog();await action();},danger?'btn accent':'btn primary'));
  box.append(el('p','',text),actions);modal(title,box);
}
let popAnchor=null;
function openPopover(anchor, content, {align='start', prefer='bottom', width=0}={}) {
  closePopover();
  const pop=$('#popover');(anchor.closest('dialog')||document.body).append(pop);pop.replaceChildren(content);pop.hidden=false;
  pop.style.minWidth=width?width+'px':'';pop.style.left='0px';pop.style.top='0px';
  const a=anchor.getBoundingClientRect(), p=pop.getBoundingClientRect();
  let up=prefer==='top', top=up?a.top-p.height-8:a.bottom+6;
  if (!up&&top+p.height>innerHeight-8&&a.top-p.height-8>8) {up=true;top=a.top-p.height-8;}
  if (up&&top<8) {up=false;top=a.bottom+6;}
  const left=Math.max(8,Math.min(align==='end'?a.right-p.width:a.left, innerWidth-p.width-8));
  pop.style.left=(prefer==='side'?Math.min(a.right+14,innerWidth-p.width-8):left)+'px';pop.style.top=(prefer==='side'?Math.max(8,Math.min(a.top,innerHeight-p.height-8)):Math.max(8,top))+'px';
  pop.className='popover'+(up?' from-bottom':'')+(align==='end'?' right':'');
  popAnchor=anchor;anchor.setAttribute('aria-expanded','true');
  const search=pop.querySelector('input');if(search)setTimeout(()=>search.focus(),0);
}
function closePopover() {const pop=$('#popover');if(pop.hidden)return;pop.hidden=true;pop.replaceChildren();popAnchor?.setAttribute('aria-expanded','false');popAnchor=null;}
function togglePopover(anchor) {if(popAnchor===anchor){closePopover();return true;}return false;}
document.addEventListener('pointerdown', e=>{if(!$('#popover').hidden&&!e.target.closest('#popover')&&!popAnchor?.contains(e.target))closePopover();}, true);
window.addEventListener('resize', closePopover);
function menuItem({icon:ic, label, hint, checked, danger, tag, onClick, onRemove}) {
  const b=el('button','menu-item'+(checked?' checked':'')+(danger?' danger':''));b.type='button';
  if (ic) b.append(typeof ic==='string'?icon(ic):ic);
  const main=el('span','mi-main');main.append(el('b','',label));if(hint)main.append(el('small','',hint));b.append(main);
  if (tag) b.append(el('span','mi-tag',tag));
  if (onRemove) {const x=el('span','mi-x');x.append(icon('x'));x.title='移除';x.onclick=e=>{e.stopPropagation();onRemove();};b.append(x);}
  if (checked!==undefined) b.append(icon('check','mi-check'));
  b.onclick=()=>{closePopover();guard(onClick);};
  return b;
}
function menuSearch(box, placeholder) {
  const wrap=el('div','menu-search'), input=el('input');input.placeholder=placeholder;input.setAttribute('aria-label',placeholder);
  input.oninput=()=>{const q=input.value.trim().toLowerCase();
    for (const item of $$('.menu-item',box)) item.hidden=!!q&&!item.textContent.toLowerCase().includes(q);
    for (const head of $$('.menu-head',box)) {let n=head.nextElementSibling,any=false;while(n&&!n.classList.contains('menu-head')){if(n.classList.contains('menu-item')&&!n.hidden)any=true;n=n.nextElementSibling;}head.hidden=!any;}};
  wrap.append(input);return wrap;
}

// Keep select elements as form state; every visible choice uses the same menu.
const selectButtons=new WeakMap();
function enhanceSelects(){
  for(const select of $$('select')){
    let trigger=selectButtons.get(select);
    if(!trigger){trigger=button('',()=>showSelectMenu(select,trigger),'select-trigger');trigger.setAttribute('aria-haspopup','listbox');
      trigger.append(el('span','select-label'),icon('chevron-down'));selectButtons.set(select,trigger);select.classList.add('custom-select-source');select.tabIndex=-1;select.setAttribute('aria-hidden','true');
      select.addEventListener('change',enhanceSelects);trigger.addEventListener('keydown',e=>{if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();showSelectMenu(select,trigger);}});}
    if(trigger.previousElementSibling!==select)select.after(trigger);
    const label=select.selectedOptions[0]?.textContent||'请选择',name=select.getAttribute('aria-label')||select.closest('label')?.firstChild?.textContent||'选择';
    if(trigger.firstChild.textContent!==label)trigger.firstChild.textContent=label;
    if(trigger.disabled!==select.disabled)trigger.disabled=select.disabled;
    const aria=name+'：'+label;if(trigger.getAttribute('aria-label')!==aria)trigger.setAttribute('aria-label',aria);
  }
}
function showSelectMenu(select,trigger){
  if(select.disabled||togglePopover(trigger))return;
  const box=el('div'),items=el('div','select-options');items.setAttribute('role','listbox');items.setAttribute('aria-label',trigger.getAttribute('aria-label'));
  if(select.options.length>7)box.append(menuSearch(items,'搜索选项'));
  for(const option of select.options){const row=menuItem({label:option.textContent,checked:option.selected,onClick:()=>{select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));enhanceSelects();trigger.focus();}});
    row.disabled=option.disabled||option.parentElement.disabled;row.setAttribute('role','option');row.setAttribute('aria-selected',option.selected);items.append(row);}
  box.append(items);openPopover(trigger,box,{width:Math.max(240,Math.min(trigger.offsetWidth,380))});
  if(select.options.length<=7)(items.querySelector('[aria-selected="true"]:not(:disabled)')||items.querySelector('button:not(:disabled)'))?.focus();
}
document.addEventListener('keydown',e=>{
  const pop=$('#popover');if(pop.hidden||!['ArrowDown','ArrowUp','Home','End','Escape'].includes(e.key))return;
  if(e.key==='Escape'){e.preventDefault();e.stopPropagation();const anchor=popAnchor;closePopover();anchor?.focus();return;}
  if(e.target.tagName==='INPUT'&&['Home','End'].includes(e.key))return;
  const rows=$$('.menu-item:not(:disabled)',pop).filter(b=>!b.hidden);if(!rows.length)return;e.preventDefault();
  const i=rows.indexOf(document.activeElement),next=e.key==='Home'?0:e.key==='End'?rows.length-1:e.key==='ArrowDown'?(i+1)%rows.length:(i-1+rows.length)%rows.length;rows[next].focus();
},true);
let selectRefresh=0;
new MutationObserver(()=>{if(!selectRefresh)selectRefresh=requestAnimationFrame(()=>{selectRefresh=0;enhanceSelects();});}).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','selected','value','aria-label']});
enhanceSelects();
async function copyText(text, target) {
  try {await navigator.clipboard.writeText(text);}
  catch {const t=el('textarea');t.value=text;document.body.append(t);t.select();document.execCommand('copy');t.remove();}
  if (target) {const old=[...target.childNodes];target.classList.add('done');target.replaceChildren(icon('check'),...(target.classList.contains('text-btn')?['已复制']:[]));setTimeout(()=>{target.classList.remove('done');target.replaceChildren(...old);},1600);}
}
function lightbox(src) {const img=el('img');img.src=src;img.style.cssText='max-width:100%;border-radius:12px;display:block;margin:auto';modal('图片',img);}

/* ---------- 原生会话：事件回放 ---------- */
function freshChat() {return {cursor:0, items:null, results:{}, exec:{}, meta:{}, queued:0, streaming:false, outbox:[]};}
function chatState(id) {if(!chats[id])chats[id]=freshChat();return chats[id];}
function isAttached(id) {return String(id).startsWith('attached:');}
function isSnapshot(id) {return String(id).startsWith('snapshot:');}
function blockText(block) {
  if (block==null) return '';
  if (typeof block==='string') return block;
  if (block.type==='text') return block.text||'';
  if (block.type==='thinking') return block.thinking||block.text||'';
  return '';
}
function messageText(message) {
  const content=message?.content;
  if (typeof content==='string') return content;
  return (Array.isArray(content)?content:[]).filter(b=>b?.type!=='thinking').map(blockText).join('\n').trim();
}
function messageImages(message) {return (Array.isArray(message?.content)?message.content:[]).filter(b=>b?.type==='image');}
function buildItemsFromHistory(ch, messages) {
  ch.items=[];ch.results={};ch.exec={};ch.streaming=false;
  for (const m of messages||[]) {
    if (m.role==='user') ch.items.push({kind:'user', text:messageText(m), images:messageImages(m)});
    else if (m.role==='assistant') ch.items.push({kind:'assistant', blocks:m.content||[], streaming:false, stopReason:m.stopReason, errorMessage:m.errorMessage, usage:m.usage});
    else if (m.role==='toolResult') ch.results[m.toolCallId]={content:m.content||[], isError:!!m.isError, toolName:m.toolName};
    else ch.items.push({kind:'note', title:m.role||'消息', text:m.output||messageText(m)});
  }
}
function ensureAssistant(ch) {
  const last=ch.items[ch.items.length-1];
  if (last&&last.kind==='assistant'&&last.streaming) return last;
  const item={kind:'assistant', blocks:[], streaming:true};
  ch.items.push(item);return item;
}
function applyChatEvent(ch, ev) {
  if(!ch.items)ch.items=[];
  if (ev.type==='ready') {ch.meta={...ch.meta, ...ev}; if(ch.items) ch.items=[]; return;}
  if (ev.type==='history') {buildItemsFromHistory(ch, ev.messages); return;}
  if (ev.type==='prompt_error') {ch.items.push({kind:'error', text:ev.message||'发送失败'}); return;}
  if (ev.type==='extension_error') {ch.items.push({kind:'error', text:'扩展：'+(ev.message||'未知错误')}); return;}
  if (ev.type==='diagnostics') {for (const d of ev.items||[]) if(d.type!=='info') ch.items.push({kind:'note', title:d.type==='error'?'启动错误':'提示', text:d.message}); return;}
  if (ev.type==='fatal') {ch.items.push({kind:'error', text:ev.message||'会话进程异常退出'}); return;}
  if (ev.type==='closed') return;
  if (ev.type==='ui_request') {ch.items.push({kind:'ui', id:ev.id, req:ev, done:false}); return;}
  if (ev.type==='ui_resolved') {const it=ch.items.find(i=>i.kind==='ui'&&i.id===ev.id); if(it) it.done=true; return;}
  if (ev.type==='ui_notify') {if(ch.live) toast(ev.message, ev.level==='error'); return;}
  if (ev.type!=='event') return;
  const e=ev.event||{};
  switch (e.type) {
    case 'message_start': {
      const m=e.message||{};
      if (m.role==='user') ch.items.push({kind:'user', text:messageText(m), images:messageImages(m)});
      else if (m.role==='assistant') ensureAssistant(ch);
      break;
    }
    case 'message_update': {
      const a=e.assistantMessageEvent||{}, item=ensureAssistant(ch);
      const ci=a.contentIndex??item.blocks.length;
      if (a.type==='text_start'||a.type==='thinking_start') {if(!item.blocks[ci]) item.blocks[ci]={type:a.type==='text_start'?'text':'thinking', text:''};}
      else if (a.type==='text_delta'||a.type==='thinking_delta') {if(!item.blocks[ci]) item.blocks[ci]={type:a.type==='text_delta'?'text':'thinking', text:''}; item.blocks[ci].text+=a.delta||'';}
      // The call's id and name arrive inside the partial message, not on the delta event.
      else if (a.type==='toolcall_start'||a.type==='toolcall_delta') {
        const partial=a.partial?.content?.[ci]||{};
        if(!item.blocks[ci]||a.type==='toolcall_start') item.blocks[ci]={type:'toolCall', id:a.id||partial.id, toolName:a.toolName||partial.name||'', argsText:''};
        const b=item.blocks[ci];b.id=b.id||partial.id;b.toolName=b.toolName||partial.name||'';
        if(a.type==='toolcall_delta') b.argsText+=a.delta||'';}
      if (a.type==='done'||a.type==='error') item.stopReason=a.reason;
      if (e.usage) item.usage=e.usage;
      break;
    }
    case 'message_end': {
      const m=e.message||{};
      if (m.role!=='assistant') break;
      const last=ch.items[ch.items.length-1];
      const item=(last&&last.kind==='assistant')?last:{kind:'assistant', blocks:[], streaming:false};
      if (item!==last) ch.items.push(item);
      item.blocks=m.content||[]; item.streaming=false; item.stopReason=m.stopReason; item.errorMessage=m.errorMessage; item.usage=m.usage;
      break;
    }
    case 'tool_execution_start': {
      ch.exec[e.toolCallId]={status:'running'};
      let hit=false;
      for (const item of [...ch.items].reverse()) {if (item.kind!=='assistant') continue;
        let found=false;
        for (const b of item.blocks||[]) if (b.type==='toolCall'&&b.id===e.toolCallId) {b.toolName=b.toolName||e.toolName; b.args=e.args; found=true; break;}
        if (found) {hit=true; break;}}
      if (!hit) ch.items.push({kind:'assistant', streaming:false, blocks:[{type:'toolCall', id:e.toolCallId, toolName:e.toolName, args:e.args}]});
      break;
    }
    case 'tool_execution_end': {
      ch.exec[e.toolCallId]={status:e.isError?'error':'done'};
      ch.results[e.toolCallId]={content:e.result?.content||[], isError:!!e.isError};
      break;
    }
    case 'agent_start': ch.streaming=true; break;
    case 'agent_end': ch.streaming=false; break;
    case 'queue_update': ch.queued=(e.queued?.steering?.length||0)+(e.queued?.followUps?.length||0)+(e.steering?.length||0)+(e.followUps?.length||0); break;
    case 'compaction_start': ch.items.push({kind:'note', title:'压缩', text:'正在压缩上下文…'}); break;
    case 'compaction_end': ch.items.push({kind:'note', title:'压缩', text:'上下文已压缩。'}); break;
    case 'auto_retry_start': ch.items.push({kind:'note', title:'自动重试', text:'第 '+(e.attempt||1)+' 次重试'}); break;
    default: break;
  }
}

/* ---------- Markdown 渲染 ---------- */
const TICK = String.fromCharCode(96);
function mdInline(text) {
  const out=document.createDocumentFragment();
  let rest=String(text);
  while (rest) {
    const start=rest.indexOf(TICK);
    if (start<0) {appendStyled(out, rest);break;}
    if (start>0) {appendStyled(out, rest.slice(0,start));rest=rest.slice(start);}
    let run=0; while (rest[run]===TICK) run++;
    const marker=TICK.repeat(run);
    const end=rest.indexOf(marker,run);
    if (end<0) {appendStyled(out, rest);break;}
    out.append(el('code','',rest.slice(run,end)));
    rest=rest.slice(end+run);
  }
  return out;
}
function linkEnd(rest, start) {
  // [title](http-url) — parsed with indexOf so no shell-like syntax appears in this file
  const close=rest.indexOf(']', start);
  if (close<0||rest[close+1]!=='(') return -1;
  const end=rest.indexOf(')', close+2);
  if (end<0) return -1;
  const url=rest.slice(close+2,end);
  return /^https?:\/\/\S+$/.test(url) ? [close, end, url] : -1;
}
function appendStyled(out, text) {
  let rest=String(text);
  while (rest) {
    const open=rest.indexOf('[');
    const link=open>=0?linkEnd(rest,open):-1;
    if (link===-1) {appendEmphasis(out, rest);break;}
    appendEmphasis(out, rest.slice(0,open));
    const a=el('a','',rest.slice(open+1,link[0]));
    a.href=link[2];a.target='_blank';a.rel='noopener noreferrer';
    out.append(a);
    rest=rest.slice(link[1]+1);
  }
}
const URL_STOP=' \t\n<>"\'「」，。；：！？()[]{}|';
function appendUrl(out, text) {
  let rest=String(text);
  while (rest) {
    let at=rest.indexOf('http://');
    const ats=rest.indexOf('https://');
    if (ats>=0&&(at<0||ats<at)) at=ats;
    if (at<0) {out.append(rest);break;}
    if (at>0) {out.append(rest.slice(0,at));rest=rest.slice(at);}
    let end=0;
    while (end<rest.length&&!URL_STOP.includes(rest[end])) end++;
    const url=rest.slice(0,end);
    const a=el('a','',url);a.href=url;a.target='_blank';a.rel='noopener noreferrer';
    out.append(a);
    rest=rest.slice(end);
  }
}
function appendEmphasis(out, text) {
  const re=/\*\*([\s\S]+?)\*\*|__([\s\S]+?)__|\*([^*\n]+?)\*|~~([\s\S]+?)~~/g;
  let last=0;
  for (const m of text.matchAll(re)) {
    if (m.index>last) appendUrl(out, text.slice(last, m.index));
    if (m[1]!==undefined||m[2]!==undefined) out.append(el('strong','',m[1]??m[2]));
    else if (m[3]!==undefined) out.append(el('em','',m[3]));
    else if (m[4]!==undefined) out.append(el('del','',m[4]));
    last=m.index+m[0].length;
  }
  if (last<text.length) appendUrl(out, text.slice(last));
}
function headingOf(line) {
  let i=0; while (i<line.length&&line[i]==='#') i++;
  if (i>=1&&i<=6&&line[i]===' ') return {level:i, text:line.slice(i+1).replace(/#+\s*$/,'')};
  return null;
}
function fenceOf(line) {
  const trimmed=line.trim();
  if (trimmed.length<3) return null;
  const ch=trimmed[0];
  if (ch!==TICK&&ch!=='~') return null;
  let run=0; while (trimmed[run]===ch) run++;
  if (run<3) return null;
  const rest=trimmed.slice(run).trim();
  if (rest&&!/^[A-Za-z0-9_+.#-]+$/.test(rest)) return null;
  return {ch, run, lang:rest};
}
function fenceCloses(line, fence) {
  const t=line.trim();
  return t.startsWith(fence.ch.repeat(fence.run))&&t.slice(fence.run).trim()==='';
}
function hrOf(line) {
  const t=line.trim();
  if (t.length<3) return false;
  const ch=t[0];
  return (ch==='-'||ch==='*'||ch==='_')&&t.split(ch).join('').length===0;
}
function listMarker(line) {
  let indent=0; while (indent<line.length&&line[indent]===' ') indent++;
  const rest=line.slice(indent);
  if (rest.startsWith('- ')||rest.startsWith('* ')||rest.startsWith('+ ')) return {ordered:false, text:rest.slice(2)};
  let d=0; while (d<rest.length&&rest[d]>='0'&&rest[d]<='9') d++;
  if (d>0&&(rest[d]==='.'||rest[d]===')')&&rest[d+1]===' ') return {ordered:true, text:rest.slice(d+2), start:Number(rest.slice(0,d))};
  return null;
}
function tableCells(line) {
  return line.trim().replace(/^\||\|$/g,'').split('|').map(c=>c.trim());
}
function tableSeparator(line) {
  const t=line.trim();
  return t.includes('|')&&t.replace(/[\s:|-]/g,'').length===0;
}
function codeBlock(text, lang) {
  const wrap=el('div','code-block'), head=el('div','code-head'), pre=el('pre','md-code'), code=el('code','',text);
  if (lang) code.dataset.lang=lang;
  const copy=el('button','text-btn');copy.type='button';copy.append(icon('copy'),'复制');copy.onclick=()=>copyText(text,copy);
  head.append(el('span','',lang||'text'),copy);pre.append(code);wrap.append(head,pre);
  return wrap;
}
function renderMarkdown(text) {
  const out=document.createDocumentFragment(), lines=String(text||'').replaceAll('\r\n','\n').split('\n');
  let i=0;
  while (i<lines.length) {
    const line=lines[i];
    if (!line.trim()) {i++;continue;}
    const fence=fenceOf(line);
    if (fence) {const body=[];i++;
      while (i<lines.length&&!fenceCloses(lines[i],fence)) {body.push(lines[i]);i++;}
      i++;
      out.append(codeBlock(body.join('\n'), fence.lang));continue;}
    const head=headingOf(line);
    if (head) {const h=el('h'+head.level,'md-h');h.append(mdInline(head.text));out.append(h);i++;continue;}
    if (hrOf(line)) {out.append(el('hr','md-hr'));i++;continue;}
    if (line.trimStart().startsWith('>')) {const body=[];
      while (i<lines.length&&lines[i].trimStart().startsWith('>')) {body.push(lines[i].replace(/^\s*>\s?/,''));i++;}
      const quote=el('blockquote','md-quote');quote.append(renderMarkdown(body.join('\n')));out.append(quote);continue;}
    const marker=listMarker(line);
    if (marker) {const list=el(marker.ordered?'ol':'ul','md-list');
      if (marker.ordered&&marker.start>1) list.start=marker.start;
      while (i<lines.length) {const m2=listMarker(lines[i]);
        if (!m2||m2.ordered!==marker.ordered) break;
        const li=el('li');li.append(mdInline(m2.text));
        const sub=lines[i+1]?listMarker(lines[i+1]):null;
        if (sub&&/^\s{2,}/.test(lines[i+1])) {const subList=el(sub.ordered?'ol':'ul','md-list');
          while (i+1<lines.length) {const s=listMarker(lines[i+1]);
            if (!s||!/^\s{2,}/.test(lines[i+1])) break;
            const subLi=el('li');subLi.append(mdInline(s.text));subList.append(subLi);i++;}
          li.append(subList);}
        list.append(li);i++;}
      out.append(list);continue;}
    if (line.trim().startsWith('|')&&i+1<lines.length&&tableSeparator(lines[i+1])) {
      const head=tableCells(line);i+=2;
      const wrap=el('div','table-wrap'), table=el('table','md-table'), thead=el('thead'), trh=el('tr');
      for (const c of head) {const th=el('th');th.append(mdInline(c));trh.append(th);}
      thead.append(trh);table.append(thead);
      const tbody=el('tbody');
      while (i<lines.length&&lines[i].trim().startsWith('|')) {const tr=el('tr');
        for (const c of tableCells(lines[i])) {const td=el('td');td.append(mdInline(c));tr.append(td);}
        tbody.append(tr);i++;}
      table.append(tbody);wrap.append(table);out.append(wrap);continue;}
    const para=[];
    while (i<lines.length&&lines[i].trim()&&!lines[i].trimStart().startsWith('>')&&!headingOf(lines[i])&&!fenceOf(lines[i])&&!listMarker(lines[i])&&!hrOf(lines[i])&&!(lines[i].trim().startsWith('|')&&tableSeparator(lines[i+1]||''))) {para.push(lines[i]);i++;}
    const p=el('p','md-p');p.append(mdInline(para.join('\n')));out.append(p);
  }
  return out;
}
function truncate(text, limit=4000) {return String(text??'').length>limit?String(text).slice(0,limit)+'\n…（已截断）':String(text??'');}

/* ---------- 原生会话：增量渲染 ---------- */
// Rows and segments are keyed; unchanged nodes stay in place so open tool cards,
// selections and enter animations survive the 80ms streaming refresh.
let renderTimer=null, renderedChat=null, forceScroll=false;
const openState=new Map();
function scheduleRender() {if(renderTimer)return;renderTimer=setTimeout(()=>{renderTimer=null;renderChat();updateChatHeader();drawSidebar();},80);}
function reconcile(parent, specs, animate) {
  const old=new Map();for(const n of parent.children)old.set(n._key,n);
  const keep=new Set();let prev=null;
  for (const spec of specs) {
    let node=old.get(spec.key);
    if (node&&spec.patch&&node._sig===spec.sig) spec.patch(node);
    else if (!node||node._sig!==spec.sig) {
      const fresh=spec.build();fresh._key=spec.key;fresh._sig=spec.sig;
      if (spec.patch) spec.patch(fresh);
      if (!node&&animate) fresh.classList.add('enter');
      if (node) node.replaceWith(fresh);
      node=fresh;
    }
    keep.add(node);
    const expected=prev?prev.nextElementSibling:parent.firstElementChild;
    if (node!==expected) parent.insertBefore(node, expected);
    prev=node;
  }
  for (const n of old.values()) if(!keep.has(n)) n.remove();
}
function trackDetails(details, summary, key, defaultOpen) {
  const k=selectedChat+'|'+key;
  details.open=openState.has(k)?openState.get(k):defaultOpen;
  summary.addEventListener('click',()=>openState.set(k,!details.open));
}
function userCount(ch) {let n=0;for(const it of ch.items||[])if(it.kind==='user')n++;return n;}
function pruneOutbox(ch) {
  const users=userCount(ch);
  ch.outbox=(ch.outbox||[]).filter(o=>!o.sent||(!o.silent&&users<=o.base&&(ch.streaming||Date.now()-o.at<20000)));
}
function agentName(role) {return role?'Sister '+role:'Last Order';}
function agentBlurb(role) {
  if (!role) return '研究协调者 · 与你讨论问题、制定计划、分配任务，并汇总研究结论。';
  const m=(rosterCache||[]).find(x=>x.id===role);
  const text=(m?.description||'').replace(/^---[\s\S]*?---\s*/,'').replace(/^#+ /gm,'').trim().split('\n').find(Boolean);
  return text||'研究助手 · 拥有独立专长、技能与模型配置。';
}
function chatTitle(meta) {
  if (meta.name) return meta.name;
  if (meta.role) return 'Sister '+meta.role;
  return 'Last Order';
}
function buildRows(ch) {
  if (!Array.isArray(ch.items)) return [{type:'loading'}];
  const rows=[];let turn=null;
  for (const item of ch.items) {
    if (item.kind==='assistant') {if(!turn){turn={type:'turn',items:[]};rows.push(turn);}turn.items.push(item);continue;}
    turn=null;rows.push({type:item.kind==='ui'?'ui':item.kind,item});
  }
  pruneOutbox(ch);
  for (const o of ch.outbox) if(!o.silent) rows.push({type:'user',item:{kind:'user',text:o.text,images:o.images,pending:o.sent?(ch.streaming?'queued':'sent'):'sending'}});
  // A reply placeholder follows the newest message unless that message is merely
  // queued behind a reply that is still streaming above it.
  const last=rows[rows.length-1];
  const waiting=ch.streaming||ch.outbox.some(o=>!o.sent)||(ch.meta.status==='starting'&&ch.outbox.length);
  if (last&&last.type==='user'&&last.item.pending!=='queued'&&waiting) rows.push({type:'turn',items:[],placeholder:true});
  if (!rows.length) rows.push({type:'intro'});
  return rows;
}
// Persisted calls carry name/arguments; live ones are assembled from deltas.
const toolNameOf=call=>call.toolName||call.name||'工具';
function toolArgs(call) {
  if (call.args!==undefined) return call.args;
  const given=call.arguments&&typeof call.arguments==='object'&&Object.keys(call.arguments).length?call.arguments:undefined;
  if (given||!call.argsText) return given??call.arguments;
  try {return JSON.parse(call.argsText);} catch {return call.argsText;}
}
function toolState(call, ch, live) {
  const exec=ch.exec[call.id]||{}, result=ch.results[call.id];
  if (exec.status==='running') return 'running';
  if (result) return result.isError?'error':'done';
  return live?'running':'idle';
}
function toolIcon(name) {
  const n=String(name||'').toLowerCase();
  if (/web|fetch|http|browse|url|download/.test(n)) return 'globe';
  if (/bash|shell|exec|command|terminal|powershell|run/.test(n)) return 'terminal';
  if (/write|edit|patch|replace|create|append|insert|move|delete/.test(n)) return 'pencil';
  if (/grep|search|find|glob|lookup|query/.test(n)) return 'search';
  if (/doc|pdf|page|cite|quote|verify/.test(n)) return 'library';
  if (/read|cat|view|open|ls|list|tree|file/.test(n)) return 'file';
  if (/sister|agent|task|card|delegate|mail|message|ally|team|send/.test(n)) return 'team';
  if (/research|graph|node/.test(n)) return 'research';
  if (/think|plan|todo|note/.test(n)) return 'bulb';
  return 'wrench';
}
function toolBrief(args) {
  if (args==null) return '';
  const tidy=s=>String(s).trim().replace(/\s+/g,' ').slice(0,180);
  if (typeof args==='string') {
    const m=args.match(/"(command|cmd|path|file_path|pattern|query|url|task|goal)"\s*:\s*"((?:[^"\\]|\\.)*)/);
    return m?tidy(m[2].replaceAll('\\n',' ')):tidy(args);
  }
  if (typeof args!=='object') return tidy(args);
  for (const k of ['command','cmd','path','file_path','filePath','file','pattern','query','q','url','glob','task','prompt','goal','question','text','message','name','id']) {
    const v=args[k];
    if (typeof v==='string'&&v.trim()) return tidy(v)+(k==='pattern'&&typeof args.path==='string'?'  ·  '+args.path:'');
  }
  const first=Object.values(args).find(v=>typeof v==='string'&&v.trim());
  if (first) return tidy(first);
  const json=JSON.stringify(args);return json==='{}'?'':tidy(json);
}
function turnSegments(turn, ch, live) {
  const segs=[];
  for (const item of turn.items) {
    const blocks=item.blocks||[];
    blocks.forEach((b,bi)=>{
      if (!b) return;
      if (b.type==='toolCall') {const last=segs[segs.length-1];if(last&&last.type==='tools')last.calls.push(b);else segs.push({type:'tools',calls:[b]});return;}
      const text=blockText(b);if(!text.trim())return;
      segs.push({type:b.type==='thinking'?'thinking':'text', text, live:!!item.streaming&&bi===blocks.length-1});
    });
    if (item.stopReason==='aborted') segs.push({type:'stopped'});
    else if (item.errorMessage) segs.push({type:'error',text:item.errorMessage});
  }
  if (live) {
    const last=segs[segs.length-1];
    const busyTools=last&&last.type==='tools'&&last.calls.some(c=>toolState(c,ch,false)==='running'||!ch.results[c.id]);
    const liveText=last&&(last.type==='text'||last.type==='thinking')&&last.live;
    if (!busyTools&&!liveText) segs.push({type:'pending',label:ch.meta.status==='starting'?'正在唤醒 '+agentName(ch.meta.role)+'…':last&&last.type==='tools'?'正在整理结果…':'正在思考…'});
  }
  return segs;
}
function segSig(seg, ch, live) {
  if (seg.type==='tools') return 'tools:'+seg.calls.map(c=>[c.id,toolNameOf(c),toolState(c,ch,live),JSON.stringify(toolArgs(c)??'').length,(ch.results[c.id]?.content||[]).length].join(',')).join('|');
  if (seg.type==='text'||seg.type==='thinking') return seg.type+':'+seg.text.length+':'+seg.live;
  return seg.type+':'+(seg.text||seg.label||'');
}
function textSeg(seg) {
  const div=el('div','md');div.append(renderMarkdown(seg.text));
  if (seg.live) {
    let target=div.lastElementChild||div;
    if (target.classList.contains('code-block')||target.classList.contains('table-wrap')) target=div;
    else if (target.tagName==='UL'||target.tagName==='OL') target=target.lastElementChild||target;
    target.append(el('span','caret'));
  }
  return div;
}
function thinkingSeg(seg, key) {
  if(seg.text.trim().length<=320&&seg.text.trim().split(/\n\s*\n/).length<=3){
    const row=el('div','work-progress'+(seg.live?' live':'')),body=el('div','md');body.append(renderMarkdown(seg.text));row.append(icon('bulb'),body);return row;
  }
  const d=el('details','thinking'+(seg.live?' live':'')), sum=el('summary');
  sum.append(icon('bulb'), el('span',seg.live?'shimmer':'',seg.live?'正在思考':'思考摘要'));
  if (seg.live) sum.append(el('span','th-preview',seg.text.trim().split('\n').pop().slice(-90)));
  sum.append(icon('chevron-right','chev'));
  const body=el('div','th-body md');body.append(renderMarkdown(seg.text));d.append(sum,body);
  trackDetails(d,sum,'th:'+key,false);
  return d;
}
function toolDetail(call, ch) {
  const box=el('div','tc-detail'), args=toolArgs(call), result=ch.results[call.id];
  if (args!==undefined&&!(typeof args==='object'&&args&&!Object.keys(args).length)) box.append(el('small','','参数'), el('pre','',truncate(typeof args==='string'?args:JSON.stringify(args,null,2))));
  if (result) {
    const text=(result.content||[]).map(blockText).join('\n');
    box.append(el('small','',result.isError?'结果（出错）':'结果'));
    const pre=el('pre',result.isError?'err':'',truncate(text||'（无文本输出）'));box.append(pre);
    if (text.length>4000) box.append(button('显示全部',()=>{pre.textContent=truncate(text,200000);box.lastChild.remove();},'text-btn'));
    for (const img of (result.content||[]).filter(b=>b?.type==='image')) {const t=el('img');t.src='data:'+(img.mimeType||img.mime||'image/png')+';base64,'+img.data;t.onclick=()=>lightbox(t.src);box.append(t);}
  } else if ((ch.exec[call.id]||{}).status==='running') box.append(el('small','shimmer','正在执行…'));
  return box;
}
function toolStepSummary(call, st, sum) {
  const ic=el('span','st-icon');ic.append(icon(toolIcon(toolNameOf(call))));
  const stateNode=el('span','st-state');stateNode.append(st==='running'?el('span','spinner'):icon(st==='done'?'check':st==='error'?'alert':'dot'));
  sum.append(ic, el('span','st-name',toolNameOf(call)), el('span','st-brief',toolBrief(toolArgs(call))), stateNode, icon('chevron-right','chev'));
}
function toolsSeg(seg, ch, live) {
  const states=seg.calls.map(c=>toolState(c,ch,live));
  const running=states.includes('running'), errors=states.filter(s=>s==='error').length;
  const status=running?'running':errors?'error':states.every(s=>s==='done')?'done':'idle';
  if (seg.calls.length===1) {
    const call=seg.calls[0], d=el('details','toolchain single tc-step '+status), sum=el('summary');
    toolStepSummary(call, states[0], sum);d.append(sum, toolDetail(call, ch));
    trackDetails(d,sum,'ts:'+call.id,false);
    return d;
  }
  const d=el('details','toolchain '+status), sum=el('summary'), ic=el('span','tc-icon');
  ic.append(running?el('span','spinner'):icon(status==='error'?'alert':status==='done'?'check':'wrench'));
  const current=running?seg.calls[states.lastIndexOf('running')]:null;
  const title=current?'正在运行 '+toolNameOf(current)+'（第 '+(states.lastIndexOf('running')+1)+' 步）':'调用了 '+seg.calls.length+' 个工具'+(errors?' · '+errors+' 个出错':'');
  const names=[...new Set(seg.calls.map(toolNameOf))].join(' · ');
  sum.append(ic, el('span','tc-title'+(running?' shimmer':''),title), el('span','tc-names',names), icon('chevron-right','chev'));
  const steps=el('div','tc-steps');
  seg.calls.forEach((call,i)=>{const step=el('details','tc-step '+states[i]), s=el('summary');toolStepSummary(call,states[i],s);step.append(s,toolDetail(call,ch));trackDetails(step,s,'ts:'+call.id,false);steps.append(step);});
  d.append(sum, steps);
  trackDetails(d,sum,'tc:'+seg.calls[0].id,running);
  return d;
}
function segmentNode(seg, ch, live, key) {
  if (seg.type==='text') return textSeg(seg);
  if (seg.type==='thinking') return thinkingSeg(seg, key);
  if (seg.type==='tools') return toolsSeg(seg, ch, live);
  if (seg.type==='error') {const n=el('div','error-card');n.append(icon('alert'),el('span','',seg.text));return n;}
  if (seg.type==='stopped') {const n=el('div','stopped-mark');n.append(icon('stop'),'已停止回复');return n;}
  const n=el('div','pending-row'), mark=el('span','mini-seal'+(ch.meta.role?' sister':''),ch.meta.role?String(ch.meta.role).slice(-2):'M');
  n.append(mark, el('span','shimmer',seg.label));return n;
}
function fmtTokens(n) {return n>=1000?(n/1000).toFixed(n>=10000?0:1)+'k':String(n);}
function usageText(u) {
  if (!u||typeof u!=='object') return '';
  const input=u.input??u.inputTokens, output=u.output??u.outputTokens, parts=[];
  if (Number.isFinite(input)) parts.push('输入 '+fmtTokens(input+(u.cacheRead||0)));
  if (Number.isFinite(output)) parts.push('输出 '+fmtTokens(output));
  return parts.join(' · ');
}
function turnText(turn) {return turn.items.flatMap(i=>(i.blocks||[]).filter(b=>b&&b.type==='text').map(blockText)).join('\n\n').trim();}
function turnSpec(turn, ch, key, live, animate) {
  return {key, sig:'turn', build:()=>{const n=el('article','turn');n.append(el('div','turn-body'),el('div','turn-foot'));return n;},
    patch:node=>{
      const segs=turnSegments(turn, ch, live);
      reconcile(node.firstElementChild, segs.map((seg,i)=>({key:'seg:'+i+':'+seg.type, sig:segSig(seg,ch,live), build:()=>segmentNode(seg,ch,live,key+':'+i)})), animate);
      const foot=node.lastElementChild, text=turnText(turn), usage=usageText([...turn.items].reverse().find(i=>i.usage)?.usage);
      const footSig=live?'':text.length+'|'+usage;
      if (foot._sig===footSig) return;
      foot._sig=footSig;foot.replaceChildren();foot.hidden=live||!text;
      if (!live&&text) {const tools=el('div','msg-tools'), copy=el('button','icon-btn');copy.type='button';copy.title='复制回复';copy.append(icon('copy'));copy.onclick=()=>copyText(text,copy);tools.append(copy);foot.append(tools);if(usage)foot.append(el('span','usage',usage));}
    }};
}
function userNode(item) {
  const node=el('article','msg-user'+(item.pending?' pending':''));
  if (item.images?.length) {const imgs=el('div','user-images');
    for (const img of item.images) {const thumb=el('img','image-thumb');thumb.src='data:'+(img.mimeType||img.mime||'image/png')+';base64,'+img.data;thumb.onclick=()=>lightbox(thumb.src);imgs.append(thumb);}
    node.append(imgs);}
  if (item.text) {
    const bubble=el('div','bubble'), text=el('div','user-text',item.text);bubble.append(text);
    if (item.text.length>700||item.text.split('\n').length>10) {bubble.classList.add('clamped');const more=el('button','expand','展开全文');more.type='button';more.onclick=()=>{const c=bubble.classList.toggle('clamped');more.textContent=c?'展开全文':'收起';};bubble.append(more);}
    node.append(bubble);
  }
  const meta=el('div','msg-meta');
  if (item.pending) {if(item.pending==='queued')meta.append('排队中，将在当前回复后处理');else{meta.append(el('span','spinner'),'发送中');}}
  else {const tools=el('div','msg-tools'), copy=el('button','icon-btn');copy.type='button';copy.title='复制';copy.append(icon('copy'));copy.onclick=()=>copyText(item.text||'',copy);tools.append(copy);meta.append(tools);}
  node.append(meta);
  return node;
}
// Dialogs an extension or AskUserQuestion opens mid-run, answered in place.
function uiNode(item) {
  const r=item.req, card=el('div','ui-card'+(item.done?' done':''));
  const head=el('div','ui-head');head.append(icon(r.kind==='questions'?'quote':r.kind==='confirm'?'alert':'bulb'),el('b','',r.kind==='questions'?'需要你的回答':(r.title||'需要你的确认')));
  card.append(head);
  if (item.done) {card.append(el('small','ui-answer',item.answerText||'已处理'));return card;}
  const chatId=selectedChat;
  const send=(value,text)=>guard(async()=>{await api('chat_ui_response',{chat_id:chatId,id:item.id,value});item.done=true;item.answerText=text;scheduleRender();});
  const actions=el('div','ui-actions');
  if (r.kind==='confirm') {
    if (r.message) card.append(el('p','',r.message));
    actions.append(button('确认',()=>send(true,'已确认'),'btn primary sm','check'),button('取消',()=>send(false,'已拒绝'),'btn ghost sm'));
  } else if (r.kind==='select') {
    const opts=el('div','ui-options');
    for (const o of r.options||[]) opts.append(button(o,()=>send(o,'已选择：'+o),'ui-option'));
    card.append(opts);actions.append(button('取消',()=>send(null,'已取消'),'btn ghost sm'));
  } else if (r.kind==='input'||r.kind==='editor') {
    const input=r.kind==='editor'?el('textarea','mono-area'):textInput('',r.placeholder||'');
    if (r.kind==='editor') {input.rows=8;input.value=r.prefill||'';}
    card.append(input);
    actions.append(button('提交',()=>send(input.value,'已提交'),'btn primary sm'),button('取消',()=>send(null,'已取消'),'btn ghost sm'));
  } else if (r.kind==='questions') {
    const forms=[];
    for (const q of r.questions||[]) {
      const block=el('div','q-block'), name='q'+Math.random().toString(36).slice(2), preview=el('pre','q-preview');preview.hidden=true;
      block.append(el('span','q-chip',q.header),el('p','q-text',q.question));
      const opts=el('div','q-options');
      for (const o of q.options) {const l=el('label','q-option'), inp=el('input');inp.type=q.multiSelect?'checkbox':'radio';inp.name=name;inp.value=o.label;
        inp.onchange=()=>{const sel=$$('input:checked',opts).map(x=>q.options.find(y=>y.label===x.value)).find(y=>y?.preview);preview.hidden=!sel;preview.textContent=sel?.preview||'';};
        const t=el('span');t.append(el('b','',o.label),el('small','',o.description));l.append(inp,t);opts.append(l);}
      const other=el('label','q-option other'), otherInput=textInput('','其他（自己填写）'), otherBox=el('input');otherBox.type=q.multiSelect?'checkbox':'radio';otherBox.name=name;otherBox.value='__other';
      otherInput.oninput=()=>{otherBox.checked=!!otherInput.value.trim();};other.append(otherBox,otherInput);opts.append(other);
      const notes=textInput('','补充说明（可选）');
      block.append(opts,preview,notes);card.append(block);
      forms.push({q,opts,otherInput,notes,preview});
    }
    const collect=action=>{const answers={},annotations={};
      for (const f of forms) {const picked=$$('input:checked',f.opts).map(x=>x.value==='__other'?f.otherInput.value.trim():x.value).filter(Boolean);
        if (picked.length) answers[f.q.question]=picked.join(', ');
        const a={};if(f.notes.value.trim())a.notes=f.notes.value.trim();if(!f.preview.hidden)a.preview=f.preview.textContent;if(Object.keys(a).length)annotations[f.q.question]=a;}
      return {action,answers,annotations};};
    actions.append(button('提交回答',()=>{const v=collect('submit');if(!Object.keys(v.answers).length){toast('请至少回答一个问题',true);return;}send(v,'已回答：'+Object.values(v.answers).join('；'));},'btn primary sm','check'),
      button('先讨论一下',()=>send(collect('clarify'),'想先讨论'),'btn sm'),button('跳过',()=>send({action:'cancel',answers:{},annotations:{}},'已跳过'),'btn ghost sm'));
  }
  card.append(actions);
  return card;
}
function introNode(ch) {
  const role=ch.meta.role, starting=ch.meta.status==='starting', n=el('div','intro'+(starting?' loading':''));
  n.append(el('span','seal'+(role?' sister':''),role?String(role).slice(-2):'M'), el('h2','',agentName(role)), el('p','',starting?'正在唤醒会话，加载模型与技能…':agentBlurb(role)));
  return n;
}
function renderChat() {
  const ch=selectedChat?chatState(selectedChat):null, stream=$('#chat-stream'), scroller=$('#chat-scroll');
  if (!ch) {stream.replaceChildren();renderedChat=null;return;}
  const fresh=renderedChat!==selectedChat;
  if (fresh) {stream.replaceChildren();renderedChat=selectedChat;}
  const near=scroller.scrollHeight-scroller.scrollTop-scroller.clientHeight<140;
  const rows=buildRows(ch), animate=!fresh, lastTurn=rows.map(r=>r.type).lastIndexOf('turn');
  const specs=rows.map((row,i)=>{
    const key=row.type+':'+i;
    if (row.type==='turn') return turnSpec(row, ch, key, i===lastTurn&&(ch.streaming||!!row.placeholder||(ch.meta.status==='starting'&&ch.outbox.length>0)), animate);
    if (row.type==='user') return {key, sig:'u:'+(row.item.text||'').length+':'+(row.item.images||[]).length+':'+(row.item.pending||''), build:()=>userNode(row.item)};
    if (row.type==='ui') return {key, sig:'ui:'+row.item.id+':'+row.item.done+':'+(row.item.answerText||''), build:()=>uiNode(row.item)};
    if (row.type==='intro') return {key, sig:'intro:'+ch.meta.status+':'+ch.meta.role+':'+!!rosterCache, build:()=>introNode(ch)};
    if (row.type==='loading') return {key, sig:'loading', build:()=>{const n=el('div','intro loading');n.append(el('span','seal','M'),el('p','','正在载入对话…'));return n;}};
    if (row.type==='error') return {key, sig:'e:'+row.item.text, build:()=>{const n=el('div','error-card');n.append(icon('alert'),el('span','',row.item.text));return n;}};
    return {key, sig:'n:'+row.item.title+row.item.text, build:()=>{const n=el('div','note-row'), s=el('span');if(row.item.title)s.append(el('b','',row.item.title+' · '));s.append(row.item.text||'');n.append(s);return n;}};
  });
  reconcile(stream, specs, animate);
  if (fresh||near||forceScroll) {
    if (forceScroll&&!fresh) scroller.scrollTo({top:scroller.scrollHeight,behavior:'smooth'});
    else scroller.scrollTop=scroller.scrollHeight;
  }
  forceScroll=false;updateJump();
}
function updateJump() {const s=$('#chat-scroll');$('#jump-latest').hidden=!selectedChat||s.scrollHeight-s.scrollTop-s.clientHeight<260;}
$('#chat-scroll').addEventListener('scroll',updateJump,{passive:true});
$('#jump-latest').onclick=()=>$('#chat-scroll').scrollTo({top:$('#chat-scroll').scrollHeight,behavior:'smooth'});
new ResizeObserver(()=>$('#view-chat').style.setProperty('--dock-h',($('#dock').offsetHeight+14)+'px')).observe($('#dock'));

/* ---------- 顶栏与输入框状态 ---------- */
function greetingText() {const h=new Date().getHours();return h<5?'夜深了':h<11?'早上好':h<13?'中午好':h<18?'下午好':'晚上好';}
function chatFlags() {
  const ch=selectedChat?chatState(selectedChat):null, id=selectedChat||'';
  const snapshot=!!ch&&isSnapshot(id), attached=!!ch&&isAttached(id);
  const readonly=!!ch&&(readOnlyView===id||['closed','error'].includes(ch.meta.status));
  return {ch, snapshot, attached, readonly, native:!!ch&&!snapshot&&!attached};
}
function sendMode() {
  const {ch}=chatFlags(), text=$('#chat-input').value.trim();
  if (ch&&ch.streaming&&!text&&!pendingImages.length) return 'stop';
  return 'send';
}
function updateSendButton() {
  const {readonly}=chatFlags(), mode=sendMode(), send=$('#chat-send');
  send.classList.toggle('stop',mode==='stop');
  send.title=mode==='stop'?'停止回复（Esc）':chatFlags().ch?.streaming?'排队发送（Enter）':'发送（Enter）';
  send.disabled=readonly||(mode==='send'&&!$('#chat-input').value.trim());
}
function updateChatHeader() {
  const {ch, snapshot, attached, readonly, native}=chatFlags();
  $('#view-chat').classList.toggle('is-home', !ch);
  if (view==='chat') {
    const title=$('#page-title');
    title.textContent=!ch?'新对话':snapshot?(ch.meta.title||'历史会话'):chatTitle(ch.meta);
    const editable=native&&!readonly&&ch.meta.status==='ready';
    title.classList.toggle('editable',editable);title.title=editable?'点击重命名':'';
    const role=$('#chat-role');role.hidden=!ch||!ch.meta.role||!ch.meta.name;role.textContent=ch?.meta.role?'Sister '+ch.meta.role:'';
    const chip=$('#chat-status');chip.replaceChildren();chip.className='status-chip';
    let label='';
    if (ch?.meta.error) {chip.classList.add('warn');chip.append(icon('alert'));label='异常';}
    else if (ch&&ch.meta.status==='starting') {chip.append(el('span','spinner'));label='正在启动';}
    else if (ch?.streaming) {chip.classList.add('busy');chip.append(el('span','dot busy'));label=attached?'运行中':'回复中';}
    else if (attached&&ch.meta.paused) {chip.classList.add('busy');chip.append(icon('pause'));label='已暂停';}
    else if (snapshot||(attached&&readonly)) label='只读';
    else if (ch&&ch.meta.status==='closed') label='已结束';
    chip.append(label);chip.hidden=!label;
    $('#chat-actions').hidden=!ch;
  }
  // Composer
  const form=$('#chat-form'), input=$('#chat-input');
  const showResume=!!ch&&readonly&&!attached;
  $('#readonly-bar').hidden=!(ch&&readonly);
  $('#resume-snapshot').hidden=!showResume||!(ch.meta.sessionPath||ch.meta.sessionFile);
  $('#readonly-bar span').textContent=attached?'任务已结束，以下是保存的对话记录。':snapshot?'这是已保存的历史记录（只读）。':ch?.meta.status==='error'?'会话进程异常退出：'+(ch.meta.error||'')+'。':'会话已结束，记录已保存。';
  form.hidden=!!ch&&readonly;$('.composer-foot').hidden=!!ch&&readonly;
  input.disabled=!!ch&&readonly;
  input.placeholder=!ch?'向 '+agentName(homeRole)+' 提问，或描述你想研究的问题…':attached?'给这个任务补充要求或讨论计划…':ch.meta.status==='starting'?'会话正在启动，可以先输入，启动后自动发送…':ch.streaming?'继续输入，消息会排队到当前回复之后…':'回复 '+(ch.meta.role?'Sister '+ch.meta.role:'Last Order')+'…';
  // Agent / model / thinking pills
  const agent=$('#agent-pick');agent.hidden=!!ch;
  $('#agent-label').textContent=agentName(homeRole);
  const seal=$('#agent-seal');seal.textContent=homeRole?String(homeRole).slice(-2):'L';seal.className='mini-seal'+(homeRole?' sister':'');
  const modelBtn=$('#chat-model'), thinkBtn=$('#chat-thinking');
  modelBtn.hidden=attached||snapshot;thinkBtn.hidden=attached||snapshot;
  if (!ch) {
    $('#model-label').textContent=homeModel?.name||homeModel?.id||shortModel(state?.model)||'默认模型';
    $('#thinking-label').textContent=thinkingLabels[homeThinking]?'思考 · '+thinkingLabels[homeThinking]:'思考';
    modelBtn.disabled=false;thinkBtn.disabled=false;
  } else if (native) {
    const model=ch.meta.model;
    $('#model-label').textContent=model?.name||model?.id||(ch.meta.status==='starting'?'启动中…':'选择模型');
    const levels=ch.meta.availableThinkingLevels;
    thinkBtn.hidden=Array.isArray(levels)&&levels.length<=1;
    $('#thinking-label').textContent='思考 · '+(thinkingLabels[ch.meta.thinkingLevel]||ch.meta.thinkingLevel||'默认');
    modelBtn.disabled=readonly||ch.meta.status!=='ready';thinkBtn.disabled=readonly||ch.meta.status!=='ready';
  }
  const queued=ch?ch.queued||ch.outbox.filter(o=>o.sent&&!o.silent&&ch.streaming).length:0;
  const hint=$('#chat-hint');hint.replaceChildren('Enter 发送 · Shift+Enter 换行 · 输入 / 查看指令 · 可粘贴或拖入图片');
  if (queued) {hint.append(' · ');hint.append(el('b','',queued+' 条消息排队中'));}
  // Banner (tasks, model fallback)
  const banner=$('#chat-banner'), bannerText=ch?.meta.banner||(native&&ch.meta.modelFallbackMessage)||'';
  banner.hidden=!bannerText||(!!ch&&readonly);
  if (bannerText) banner.replaceChildren(icon(attached?'task':'alert'),el('span','',bannerText));
  if (!ch) {$('#greeting').textContent=greetingText();$('#welcome-project').textContent=workspace?baseName(workspace):'当前项目';$('#home-sub').lastChild.textContent=homeRole?' 中与 Sister '+homeRole+' 开始对话':' 中继续你的研究';}
  updateSendButton();
}
function shortModel(name) {return name?String(name).split('/').pop():'';}

/* ---------- 原生会话：长轮询与发送队列 ---------- */
async function pollChats() {
  while (!guiClosed) {
    const id=selectedChat;
    if(isAttached(id)){await refreshAttached(id);await sleep(1200);continue;}
    // No document.hidden guard here: the long poll is one idle request, and an
    // embedded webview can report hidden permanently, which would freeze chats.
    if (!id||view!=='chat'||readOnlyView===id||isSnapshot(id)) {await sleep(500);continue;}
    const ch=chatState(id);
    try {
      const res=await api('chat_events', {chat_id:id, cursor:ch.cursor, wait:1});
      if (id!==selectedChat) continue;
      if (res.reset) {const snapshot=await api('chat_replay',{chat_id:id});buildItemsFromHistory(ch,snapshot.messages);ch.cursor=snapshot.cursor;ch.meta={...ch.meta,...snapshot.meta};scheduleRender();continue;}
      ch.live=ch.cursor>0;
      for (const ev of res.events) applyChatEvent(ch, ev);
      const name=ch.meta.name;
      ch.cursor=res.cursor;ch.meta={...ch.meta, ...res.meta,status:res.status};ch.streaming=!!res.meta.streaming;
      if (!ch.meta.name&&name) ch.meta.name=name;
      if (res.status==='error'||res.status==='closed') failOutbox(id, res.status==='error'?'会话启动失败，消息未发送':'会话已结束，消息未发送');
      else flushOutbox(id);
      scheduleRender();
    } catch (e) {
      if (String(e.message||'').includes('会话不存在')) {toast(e.message,true);await sleep(3000);}
      else await sleep(1500);
    }
  }
}
// Messages wait in the outbox until their chat is ready, then go out in order.
// Unsent entries are shown optimistically; sent ones vanish once the echo lands.
async function flushOutbox(id) {
  const ch=chatState(id);
  if (ch.flushing||(ch.meta.status!=='ready'&&!isAttached(id))) return;
  const next=ch.outbox.find(o=>!o.sent);
  if (!next) return;
  ch.flushing=true;
  try {
    if (ch.boot) {const boot=ch.boot;ch.boot=null;
      if (boot.model) await api('chat_set_model',{chat_id:id,provider:boot.model.provider,model:boot.model.id}).then(u=>Object.assign(ch.meta,u)).catch(e=>toast('未能切换模型：'+e.message,true));
      if (boot.thinking) await api('chat_set_thinking',{chat_id:id,level:boot.thinking}).then(u=>Object.assign(ch.meta,u)).catch(e=>toast('未能调整思考深度：'+e.message,true));}
    pruneOutbox(ch);
    next.base=userCount(ch)+ch.outbox.filter(o=>o.sent&&!o.silent).length;
    next.sent=true;next.at=Date.now();
    if (isAttached(id)) await api('session_input',{session_id:id.slice(9),text:next.text});
    else await api('chat_send',{chat_id:id,text:next.text,images:next.images});
    if (!ch.meta.name&&!next.text.startsWith('/')) ch.meta.name=next.text.split('\n')[0].slice(0,40);
  } catch (e) {
    ch.outbox=ch.outbox.filter(o=>o!==next);
    toast('消息未能发送：'+e.message,true);
    if (id===selectedChat&&!$('#chat-input').value.trim()) {$('#chat-input').value=next.text;autoSize();}
  } finally {ch.flushing=false;scheduleRender();}
  if (ch.outbox.some(o=>!o.sent)) flushOutbox(id);
}
function failOutbox(id, reason) {
  const ch=chatState(id), lost=ch.outbox.filter(o=>!o.sent);
  if (!lost.length) return;
  ch.outbox=ch.outbox.filter(o=>o.sent);
  (ch.items||=[]).push({kind:'error',text:reason});
  if (id===selectedChat&&!$('#chat-input').value.trim()) {$('#chat-input').value=lost.map(o=>o.text).join('\n\n');autoSize();}
}
function flipComposer(change) {
  const form=$('#chat-form'), before=form.getBoundingClientRect();change();
  const after=form.getBoundingClientRect(), dy=before.top-after.top;
  if (Math.abs(dy)>4&&!matchMedia('(prefers-reduced-motion: reduce)').matches) form.animate([{transform:`translateY(${dy}px)`},{transform:'none'}],{duration:520,easing:'cubic-bezier(.16,1,.3,1)'});
}
function selectChat(id) {
  closePopover();saveDraft();selectedChat=id;selected=null;
  readOnlyView=isSnapshot(id)?id:null;
  sessionStorage.setItem('misaka-chat', id);sessionStorage.removeItem('misaka-pane');
  chatState(id);restoreDraft();drawSidebar();updateChatHeader();renderChat();rememberSelection();guard(()=>showView('chat'));
  if (!readOnlyView&&innerWidth>860) setTimeout(()=>$('#chat-input').focus(),60);
}
function goHome(role) {
  closePopover();saveDraft();selectedChat=null;selected=null;readOnlyView=null;
  if (role!==undefined) homeRole=role;
  sessionStorage.removeItem('misaka-chat:'+workspace);sessionStorage.removeItem('misaka-chat');
  restoreDraft();drawSidebar();updateChatHeader();renderChat();guard(()=>showView('chat'));
  setTimeout(()=>$('#chat-input').focus(),60);
}
async function startFromHome(text) {
  const images=pendingImages.map(({data,mime})=>({data,mime})), role=homeRole, source=workspace, input=$('#chat-input');
  input.value='';pendingImages=[];drawChips();autoSize();drafts.delete(draftKey());
  let result;
  try {result=await api('chat_native', role?{role}:{});}
  catch (e) {if(!input.value)input.value=text;autoSize();throw e;}
  if (source!==workspace) return;
  const ch=chatState(result.chat_id);
  ch.items=[];ch.meta={workspace,status:'starting',role,name:text.startsWith('/')?'':text.split('\n')[0].slice(0,40)};
  ch.outbox=[{text,images,silent:text.startsWith('/'),sent:false,at:Date.now()}];
  ch.boot={model:homeModel,thinking:homeThinking};
  flipComposer(()=>selectChat(result.chat_id));
  forceScroll=true;
  refreshState();
}
function stopChat() {
  const {ch, attached}=chatFlags();if(!ch)return;
  const id=selectedChat;
  return guard(async()=>{
    if (attached) {await api(ch.meta.paused?'session_resume':'session_pause',{session_id:id.slice(9)});toast(ch.meta.paused?'已请求恢复任务':'已请求暂停任务');}
    else {await api('chat_stop',{chat_id:id});toast('已停止回复');}
  });
}
function closeChat(id) {
  confirmAction('结束当前会话','会话记录已自动保存，之后可以随时在“历史会话”中继续。',async()=>{
    await api('chat_close',{chat_id:id});
    delete chats[id];
    if (selectedChat===id) goHome();
    await refreshState();loadSaved();
  },{label:'结束会话',danger:true});
}
function compactChat() {return api('chat_compact',{chat_id:selectedChat}).then(()=>toast('已开始压缩上下文'));}
async function copyTranscript() {
  const ch=chatState(selectedChat), who=agentName(ch.meta.role);
  const lines=(ch.items||[]).map(item=>{
    if (item.kind==='user') return '## 你\n\n'+item.text;
    if (item.kind==='assistant') {const text=(item.blocks||[]).filter(b=>b&&b.type==='text').map(blockText).join('\n\n').trim();return text?'## '+who+'\n\n'+text:'';}
    if (item.kind==='error') return '> '+item.text;
    return '';
  }).filter(Boolean);
  await copyText(lines.join('\n\n'));
  toast('对话记录已复制到剪贴板');
}
function startRename() {
  const {ch, native, readonly}=chatFlags();
  if (!native||readonly||ch.meta.status!=='ready') return;
  const id=selectedChat, title=$('#page-title'), input=el('input','title-input');
  input.value=ch.meta.name||chatTitle(ch.meta);input.maxLength=120;
  title.hidden=true;title.after(input);input.focus();input.select();
  let done=false;
  const finish=async save=>{
    if (done) return;done=true;
    const value=input.value.trim();input.remove();title.hidden=false;
    if (save&&value&&value!==ch.meta.name) {
      try {await api('chat_rename',{chat_id:id,name:value});ch.meta.name=value;const summary=(state?.chats||[]).find(c=>c.id===id);if(summary)summary.name=value;drawSidebar();toast('已重命名');}
      catch (e) {toast(e.message,true);}
    }
    updateChatHeader();
  };
  input.onkeydown=e=>{if(e.isComposing)return;if(e.key==='Enter'){e.preventDefault();finish(true);}if(e.key==='Escape'){e.preventDefault();finish(false);}};
  input.onblur=()=>finish(true);
}
async function resumeCurrent() {
  const ch=chatState(selectedChat), path=ch.meta.sessionPath||ch.meta.sessionFile, role=ch.meta.role;
  if (!path) throw new Error('找不到这段对话的记录文件');
  const r=await api('chat_native',{session_path:path,...(role?{role}:{})});
  await refreshState();selectChat(r.chat_id);
}

/* ---------- 弹出菜单：模型 / 思考 / 对象 / 会话 / 项目 ---------- */
const thinkingLabels={off:'关闭',minimal:'最轻',low:'较低',medium:'中等',high:'较高',xhigh:'最高'};
const thinkingHints={off:'直接作答，速度最快',minimal:'只做必要的推理',low:'适合简单问题',medium:'兼顾速度与深度',high:'适合复杂分析',xhigh:'最周全，耗时与消耗最多'};
async function showModelPicker(anchor=$('#chat-model')) {
  if (togglePopover(anchor)) return;
  const {ch, native}=chatFlags();
  if (ch&&!native) return;
  let models, current;
  if (ch) {const data=await api('chat_models',{chat_id:selectedChat});models=data.models||[];current=data.current;localStorage.setItem('misaka-models',JSON.stringify(models));}
  else {models=jsonStored('misaka-models',[]);current=homeModel;}
  const box=el('div');
  if (!models.length) {
    box.append(el('div','menu-note','开始第一段对话后，就能在这里为每个会话单独切换模型。当前默认：'+(state?.model||'尚未配置')));
    box.append(menuItem({icon:'settings',label:'登录模型服务',hint:'在设置中登录并选择默认模型',onClick:()=>openSettings('models')}));
    openPopover(anchor,box,{prefer:'top',align:'end',width:300});return;
  }
  if (models.length>7) box.append(menuSearch(box,'搜索模型'));
  if (!ch) box.append(menuItem({icon:'model',label:'默认模型',hint:state?.model||'沿用全局设置',checked:!homeModel,onClick:()=>{homeModel=null;updateChatHeader();}}));
  const groups={};for(const m of models)(groups[m.provider]??=[]).push(m);
  for (const [provider,list] of Object.entries(groups)) {
    box.append(el('div','menu-head',provider));
    for (const m of list) {
      const isCurrent=!!(current&&current.provider===m.provider&&current.id===m.id);
      box.append(menuItem({label:m.name||m.id,hint:m.id+(m.contextWindow?' · '+fmtTokens(m.contextWindow)+' 上下文':''),tag:m.configured===false?'未配置':'',checked:isCurrent,onClick:async()=>{
        if (!ch) {homeModel={provider:m.provider,id:m.id,name:m.name||m.id};updateChatHeader();return;}
        const updated=await api('chat_set_model',{chat_id:selectedChat,provider:m.provider,model:m.id});Object.assign(chatState(selectedChat).meta,updated);updateChatHeader();toast('已切换到 '+(m.name||m.id));
      }}));
    }
  }
  box.append(el('div','menu-note','只影响当前会话。默认模型可在「设置与工具」中修改。'));
  openPopover(anchor,box,{prefer:'top',align:'end',width:320});
}
function showThinkingPicker(anchor=$('#chat-thinking')) {
  if (togglePopover(anchor)) return;
  const {ch, native}=chatFlags();
  if (ch&&!native) return;
  const levels=ch?.meta.availableThinkingLevels||['off','minimal','low','medium','high','xhigh'];
  const current=ch?ch.meta.thinkingLevel:homeThinking, box=el('div');
  box.append(el('div','menu-head','思考深度'));
  if (!ch) box.append(menuItem({icon:'bulb',label:'默认',hint:'沿用模型与全局设置',checked:!homeThinking,onClick:()=>{homeThinking=null;updateChatHeader();}}));
  for (const level of levels) box.append(menuItem({label:thinkingLabels[level]||level,hint:thinkingHints[level],checked:current===level,onClick:async()=>{
    if (!ch) {homeThinking=level;updateChatHeader();return;}
    const updated=await api('chat_set_thinking',{chat_id:selectedChat,level});Object.assign(chatState(selectedChat).meta,updated);updateChatHeader();toast('思考深度：'+(thinkingLabels[level]||level));
  }}));
  box.append(el('div','menu-note','思考越深，回答越周全，耗时与消耗也相应增加。'));
  openPopover(anchor,box,{prefer:'top',align:'end',width:260});
}
async function loadRoster() {if(!rosterCache){try{rosterCache=(await api('roster')).members||[];}catch{rosterCache=[];}}return rosterCache;}
async function showAgentPicker(anchor=$('#agent-pick')) {
  if (togglePopover(anchor)) return;
  await loadRoster();
  const box=el('div');box.append(el('div','menu-head','对话对象'));
  const ids=[null,...new Set([...(state?.sisters||[]),...rosterCache.map(m=>m.id)])];
  for (const id of ids) box.append(menuItem({icon:el('span','mini-seal'+(id?' sister':''),id?String(id).slice(-2):'L'),label:agentName(id),hint:agentBlurb(id),checked:homeRole===id,onClick:()=>{homeRole=id;updateChatHeader();$('#chat-input').focus();}}));
  openPopover(anchor,box,{prefer:'top',width:320});
}
function showChatMenu(anchor=$('#chat-menu')) {
  if (togglePopover(anchor)) return;
  const {ch, native, attached, snapshot, readonly}=chatFlags();if(!ch)return;
  const box=el('div');
  if (native&&!readonly) {
    box.append(menuItem({icon:'pencil',label:'重命名',onClick:startRename}));
    box.append(menuItem({icon:'compress',label:'压缩上下文',hint:'释放上下文空间（可能调用模型）',onClick:compactChat}));
  }
  if (attached&&!readonly) box.append(menuItem({icon:ch.meta.paused?'play':'pause',label:ch.meta.paused?'恢复任务':'暂停任务',onClick:stopChat}));
  if ((snapshot||readonly)&&(ch.meta.sessionPath||ch.meta.sessionFile)&&!attached) box.append(menuItem({icon:'play',label:'继续这段对话',onClick:resumeCurrent}));
  box.append(menuItem({icon:'copy',label:'复制对话记录',hint:'Markdown 格式',onClick:copyTranscript}));
  if (native&&!readonly) {box.append(el('div','menu-sep'));box.append(menuItem({icon:'power',label:'结束会话',hint:'记录会保存，可随时继续',danger:true,onClick:()=>closeChat(selectedChat)}));}
  openPopover(anchor,box,{align:'end',width:240});
}
function showProjectMenu(anchor=$('#project-switch')) {
  if (togglePopover(anchor)) return;
  const box=el('div');box.append(el('div','menu-head','项目文件夹'));
  for (const path of recentProjects) box.append(menuItem({icon:'folder',label:baseName(path),hint:path,checked:samePath(path,workspace),onClick:()=>switchProject(path)}));
  box.append(el('div','menu-sep'));
  box.append(menuItem({icon:'plus',label:'添加项目文件夹…',onClick:showProjectPicker}));
  box.append(menuItem({icon:'pencil',label:'输入文件夹路径…',onClick:showProjectPathDialog}));
  openPopover(anchor,box,{width:anchor.offsetWidth});
}

/* ---------- 历史与指令 ---------- */
async function showNativeHistory() {
  const box=el('div');
  const roles=[['', 'Last Order'], ...(state?.sisters||[]).map(s=>[s,'Sister '+s])];
  const tabs=el('div','role-tabs');
  const list=el('div','list-card');
  async function load(role) {
    $$('button',tabs).forEach(b=>b.classList.toggle('active',(b.dataset.role||'')===(role||'')));
    list.replaceChildren(el('div','empty','正在加载…'));
    try {
      const data=await api('chat_sessions', role?{role}:{});
      list.replaceChildren();
      if (!data.sessions.length) {list.append(el('div','empty','这个身份还没有历史会话。'));return;}
      for (const s of data.sessions) {
        const row=el('div','row'), info=el('div','row-main'), actions=el('div','row-actions');
        info.append(el('strong','',s.title), el('small','',s.messages+' 条消息 · '+(s.modified?new Date(s.modified*1000).toLocaleString('zh-CN'):'尚未保存')+(s.live?' · 正在终端中运行':'')));
        row.append(icon(s.live?'terminal':'history'),info,actions);
        if (!s.live) actions.append(button('继续',async()=>{closeDialog();const result=await api('chat_native',Object.assign(role?{role}:{},{session_path:s.path}));chatState(result.chat_id);await refreshState();selectChat(result.chat_id);},'btn primary sm'));
        actions.append(button(s.live?'打开任务对话':'查看',async()=>{closeDialog();if(s.live){const entry=(state.sessions||[]).find(e=>e.path===s.path);if(!entry)throw new Error('任务对话正在初始化，请稍后再试');await openAttached(entry);}else await openSnapshot(s.path, s.title, role||null);}));
        list.append(row);
      }
    } catch (e) {list.replaceChildren(el('div','empty','加载失败：'+e.message));}
  }
  for (const [role,label] of roles) {const t=el('button','role-tab',label);t.type='button';t.dataset.role=role||'';t.onclick=()=>guard(()=>load(role),t);tabs.append(t);}
  box.append(tabs,list);
  modal('历史会话',box);
  await load('');
}
async function openSnapshot(path, title, role=null) {
  const data=await api('chat_snapshot',{path});
  const id='snapshot:'+path;
  const ch=chatState(id);
  buildItemsFromHistory(ch, data.messages);
  ch.meta={name:title, title, model:null, role, sessionPath:path};
  renderedChat=null;selectChat(id);
}
const SLASH=[['/new','新建对话'],['/model','切换模型'],['/thinking','调整思考深度'],['/compact','压缩上下文'],['/rename','重命名会话'],['/history','打开历史会话'],['/export','复制对话记录'],['/research','打开研究工作流'],['/board','查看任务看板'],['/team','查看协作成员'],['/files','浏览材料与文件'],['/settings','打开设置与工具'],['/sister ','与指定 Sister 对话（交给会话处理）',true],['/session','查看用量与会话信息（交给会话处理）'],['/help','查看全部指令']];
function showCommandHelp() {
  const box=el('div','list-card');
  for (const [command,description] of SLASH) {const row=el('div','row'), info=el('div','row-main');info.append(el('strong','',command.trim()),el('small','',description));row.append(icon('chevron-right'),info);box.append(row);}
  box.append(el('p','hint','以 / 开头的其他指令会交给会话本身处理，技能与扩展提供的指令同样可用。'));
  modal('可用指令',box);
}
let slashIndex=0;
function slashMatches() {
  const v=$('#chat-input').value;
  if (!v.startsWith('/')||/\s/.test(v.trimEnd())&&!v.endsWith(' ')||v.includes('\n')) return [];
  const q=v.trim().toLowerCase();
  return SLASH.filter(([c])=>c.trim().startsWith(q)&&c.trim()!==q.trim()||(q==='/'));
}
function drawSlash() {
  const menu=$('#slash-menu'), items=slashMatches();
  if (!items.length) {menu.hidden=true;return;}
  slashIndex=Math.min(slashIndex,items.length-1);
  menu.replaceChildren(el('div','slash-head','指令'));
  items.forEach(([command,description,arg],i)=>{
    const b=el('button','slash-item'+(i===slashIndex?' active':''));b.type='button';
    b.append(el('code','',command.trim()+(arg?' <编号>':'')),el('span','',description),el('kbd','','Enter'));
    b.onmousedown=e=>{e.preventDefault();acceptSlash(i);};b.onmousemove=()=>{if(slashIndex!==i){slashIndex=i;drawSlash();}};
    menu.append(b);
  });
  menu.hidden=false;
  menu.children[slashIndex+1]?.scrollIntoView({block:'nearest'});
}
function acceptSlash(i=slashIndex) {
  const item=slashMatches()[i];if(!item)return;
  const input=$('#chat-input');input.value=item[0];$('#slash-menu').hidden=true;autoSize();updateSendButton();
  if (!item[2]) $('#chat-form').requestSubmit();else input.focus();
}

/* ---------- 输入框 ---------- */
let pendingImages=[];
function autoSize() {const t=$('#chat-input');t.style.height='auto';t.style.height=Math.min(t.scrollHeight,innerHeight*.4)+'px';}
const nativeCommands={'/new':()=>goHome(),'/model':()=>showModelPicker(),'/thinking':()=>showThinkingPicker(),'/compact':()=>chatFlags().native?compactChat():null,'/rename':startRename,'/history':showNativeHistory,'/export':()=>selectedChat?copyTranscript():null,'/research':()=>showView('research'),'/board':()=>showView('board'),'/team':()=>showView('team'),'/files':()=>showView('documents'),'/settings':()=>showView('settings'),'/help':showCommandHelp};
async function submitChat() {
  const input=$('#chat-input'), text=input.value.trim();
  if (!text) {if(pendingImages.length)toast('请输入一句说明再发送图片',true);return;}
  $('#slash-menu').hidden=true;
  const {ch, readonly, attached}=chatFlags();
  if (ch&&readonly) {toast('这是只读的记录；请先选择“继续这段对话”。',true);return;}
  if (attached&&['/pause','/resume'].includes(text)) {await api(text==='/pause'?'session_pause':'session_resume',{session_id:selectedChat.slice(9)});input.value='';autoSize();return;}
  if (text.startsWith('/')) {
    const command=text.split(/\s+/)[0].toLowerCase();
    if (nativeCommands[command]&&!text.includes(' ')) {input.value='';autoSize();updateSendButton();await nativeCommands[command]();return;}
  }
  if (!ch) return startFromHome(text);
  const id=selectedChat, images=pendingImages.map(({data,mime})=>({data,mime}));
  if (attached&&images.length) throw new Error('任务对话暂不支持图片，请在普通对话中发送');
  ch.outbox.push({text,images,silent:text.startsWith('/'),sent:false,at:Date.now()});
  input.value='';pendingImages=[];drawChips();autoSize();drafts.delete(draftKey());
  forceScroll=true;scheduleRender();updateSendButton();
  await flushOutbox(id);
}
function drawChips() {
  const wrap=$('#image-chips');wrap.replaceChildren();
  for (const [index,img] of pendingImages.entries()) {
    const chip=el('span','image-chip');
    const thumb=el('img');thumb.src='data:'+img.mime+';base64,'+img.data;thumb.alt='';
    const remove=el('button','chip-remove');remove.type='button';remove.title='移除图片';remove.append(icon('x'));remove.onclick=()=>{pendingImages.splice(index,1);drawChips();};
    chip.append(thumb,remove);wrap.append(chip);
  }
  wrap.hidden=!pendingImages.length;updateSendButton();
}
function addImageFile(file) {
  if (!file.type.startsWith('image/')) {toast('仅支持图片附件',true);return;}
  if (file.size>4*1024*1024) {toast('图片超过 4 MB，请先压缩',true);return;}
  const reader=new FileReader();
  reader.onload=()=>{const data=String(reader.result).split(',',2)[1];pendingImages.push({data,mime:file.type});if(pendingImages.length>6)pendingImages=pendingImages.slice(-6);drawChips();};
  reader.readAsDataURL(file);
}

/* ---------- 终端窗格（研究 / 设置 / 命令等） ---------- */
function projectPanes() {return (state?.panes||[]).filter(p=>(samePath(p.cwd,workspace)||samePath(String(p.cwd).replaceAll('\\','/').slice(0,workspace.replaceAll('\\','/').replace(/\/$/,'').length+1),workspace.replaceAll('\\','/').replace(/\/$/,'')+'/'))||(state?.cards||[]).some(c=>c.id===p.card));}
function paneLabel(p) {if(!p.alive)return '已退出 · '+(p.exit_code??'—');const reported=p.reported?.state;if(!reported)return (p.argv||[]).includes('chat')?'初始化中':p.busy?'运行中':'交互中';return statusText(reported);}
function drawPanes() {
  const panes=projectPanes(), list=$('#pane-list');list.replaceChildren();$('#pane-count').textContent=panes.length;
  if(!panes.length)empty(list,'研究工作流、设置向导等终端进程会出现在这里。');
  for(const p of panes){const b=button('',()=>selectPane(p.id),'pane-item'+(p.id===selected?' selected':''));b.title=p.title+' · '+paneLabel(p);b.append(el('i','dot'+(p.alive?(p.busy?' busy':' ok'):'')),el('span','',p.title),el('small','',paneLabel(p)));list.append(b);}
  const pane=state?.panes.find(p=>p.id===selected);
  $('#terminal-stack').hidden=!pane;$('#pane-actions').hidden=!pane;
  if (pane) {$('#session-title').textContent=pane.title;$('#pane-status').textContent=paneLabel(pane);$('#pane-status').className='status-chip'+(pane.alive?(pane.busy?' busy':' ok'):'');}
  $('#send-button').disabled=!!selected&&!pane?.alive;
}

/* ---------- 侧栏 ---------- */
let savedSessions=[], projectSwitch=0, attachedBusy=false, sidebarSig='';
function timeGroup(seconds) {
  if (!seconds) return '更早';
  const day=new Date();day.setHours(0,0,0,0);const t=seconds*1000;
  return t>=day.getTime()?'今天':t>=day.getTime()-864e5?'昨天':t>=day.getTime()-7*864e5?'过去 7 天':t>=day.getTime()-30*864e5?'过去 30 天':'更早';
}
function drawSidebar() {
  $('#project-name').textContent=workspace?baseName(workspace):'加载项目…';$('#project-switch').title=workspace||'切换项目文件夹';
  const filter=$('#chat-filter').value.trim().toLowerCase(), match=t=>!filter||String(t).toLowerCase().includes(filter);
  const projects=recentProjects.map(path=>({path,entries:sidebarEntries(path),data:projectData.get(projectKey(path))}));
  const sig=JSON.stringify([filter,selectedChat,workspace,sidebarView,[...collapsedProjects],projects]);
  if (sig===sidebarSig) return;
  sidebarSig=sig;
  const list=$('#chat-list'),changedView=list.dataset.view!==sidebarView;
  if(changedView){list.replaceChildren();list.dataset.view=sidebarView;if(!matchMedia('(prefers-reduced-motion: reduce)').matches){list._switchAnimation?.cancel();list._switchAnimation=list.animate([{opacity:.4,transform:'translateY(4px)'},{opacity:1,transform:'translateY(0)'}],{duration:180,easing:'ease-out'});}}
  $('#view-projects').setAttribute('aria-pressed',sidebarView==='projects');$('#view-recent').setAttribute('aria-pressed',sidebarView==='recent');
  $('.sidebar-views').dataset.active=sidebarView;
  const item=(entry,recent=false)=>({key:'entry:'+projectKey(entry.workspace)+'|'+entry.id,sig:'entry',build:()=>{const b=button('',()=>openSidebarEntry(b._entry),'chat-item');return b;},patch:b=>{
    b._entry=entry;b.classList.toggle('selected',entry.id===selectedChat&&samePath(entry.workspace,workspace));b.title=entry.title+'\n'+entry.workspace;
    const content=JSON.stringify([entry.kind,entry.title,entry.role,entry.busy,recent]);if(b._content===content)return;b._content=content;
    const text=el('span','ci-main');text.append(el('span','ci-title',entry.title));if(recent)text.append(el('small','ci-project',baseName(entry.workspace)));
    b.replaceChildren(entry.kind==='live'?el('i','dot '+(entry.busy?'busy':'ok')):icon(entry.kind==='task'?'task':'history'),text);if(entry.role)b.append(el('span','ci-role',entry.role));
  }});
  const message=(key,text,retry=false)=>({key,sig:text,build:()=>retry?button(text,()=>refreshProjects(),'project-empty warn-text'):el('div','project-empty',text)});
  const specs=[];
  if(sidebarView==='recent'){
    let group='';const entries=projects.flatMap(p=>p.entries).filter(e=>match(e.title+' '+e.workspace)).sort((a,b)=>b.modified-a.modified);
    for(const entry of entries){const g=timeGroup(entry.modified);if(g!==group){group=g;specs.push({key:'date:'+g,sig:g,build:()=>el('div','cl-group',g)});}specs.push(item(entry,true));}
    if(!entries.length)specs.push(message('empty',filter?'没有匹配的对话':projectsBusy?'正在读取各项目的对话…':'还没有对话，选择项目后开始吧'));
    for(const p of projects.filter(p=>p.data?.error))specs.push(message('error:'+projectKey(p.path),baseName(p.path)+' · 读取失败，重试',true));
  }else{
    for(const p of projects){const projectMatch=match(p.path),entries=p.entries.filter(e=>projectMatch||match(e.title));if(filter&&!projectMatch&&!entries.length)continue;
      const key=projectKey(p.path),expanded=!!filter||!collapsedProjects.has(key);
      specs.push({key:'project:'+key,sig:'project',build:()=>{
        const group=el('section','project-group'),header=el('div','project-row');
        const toggle=button('',()=>{if(collapsedProjects.has(key))collapsedProjects.delete(key);else collapsedProjects.add(key);localStorage.setItem('misaka-collapsed-projects',JSON.stringify([...collapsedProjects]));drawSidebar();},'icon-btn project-fold','chevron-right');
        const name=button('',()=>switchProject(p.path),'project-link');name.title=p.path;name.append(icon('folder'),el('span','',baseName(p.path)));header.append(toggle,name);
        const collapse=el('div','project-collapse');collapse.append(el('div','project-chats'));group.append(header,collapse);return group;
      },patch:group=>{
        group.classList.toggle('expanded',expanded);const header=group.firstElementChild,toggle=header.firstElementChild,name=header.lastElementChild,collapse=group.lastElementChild,current=samePath(p.path,workspace);
        header.classList.toggle('current',current);toggle.setAttribute('aria-label',(expanded?'收起':'展开')+'项目 '+baseName(p.path));toggle.setAttribute('aria-expanded',expanded);
        if(current)name.setAttribute('aria-current','true');else name.removeAttribute('aria-current');collapse.inert=!expanded;
        const children=entries.map(entry=>item(entry));if(!entries.length)children.push(message('empty',p.data?.error?'暂时无法读取 · 重试':p.data||current?'暂无对话':'正在读取…',!!p.data?.error));
        reconcile(collapse.firstElementChild,children,!changedView&&!filter);
      }});
    }
    if(!specs.length)specs.push(message('empty',filter?'没有匹配的项目或对话':'添加文件夹，开始一个项目'));
  }
  reconcile(list,specs,!changedView&&!filter);
  $('#chat-count').textContent=projects.reduce((n,p)=>n+p.entries.length,0);
}

function sidebarEntries(path){
  const current=samePath(path,workspace),data=current?{...state,saved:savedSessions}:projectData.get(projectKey(path));if(!data)return [];
  const entries=[],seen=new Set(),key=p=>projectKey(p||'');
  for(const s of data.chats||[]){if(['closed','error'].includes(s.status))continue;const ch=chatState(s.id),name=ch.meta.name;
    if(s.id!==selectedChat||!ch.meta.status){Object.assign(ch.meta,s);if(!s.name&&name)ch.meta.name=name;ch.streaming=!!s.streaming;}
    if(s.sessionFile)seen.add(key(s.sessionFile));const saved=(data.saved||[]).find(x=>samePath(x.path,s.sessionFile));
    entries.push({kind:'live',id:s.id,title:ch.meta.name||chatTitle(s),role:s.role,busy:ch.streaming||s.status==='starting',modified:Math.max(s.updatedAt||s.startedAt||0,saved?.modified||0),workspace:path});}
  for(const s of data.sessions||[]){if(!s.control||s.state==='saved'||seen.has(key(s.path)))continue;seen.add(key(s.path));
    entries.push({kind:'task',id:'attached:'+s.id,title:s.title||s.role||'任务对话',role:s.role,modified:Number(s.modified)||0,workspace:path,session:s});}
  for(const s of data.saved||[]){if(seen.has(key(s.path)))continue;seen.add(key(s.path));entries.push({kind:'saved',id:'snapshot:'+s.path,title:s.title,role:s.role,modified:s.modified||0,workspace:path,session:s});}
  return entries.sort((a,b)=>b.modified-a.modified);
}
async function openSidebarEntry(entry){
  if(!samePath(entry.workspace,workspace)){const switched=await switchProject(entry.workspace);if(!switched)return;}
  if(!samePath(entry.workspace,workspace))return;
  if(entry.kind==='live')selectChat(entry.id);else if(entry.kind==='task')await openAttached(entry.session);else await resumeSaved(entry.session);
}
function drawState() {
  $('#version').textContent='v'+state.version;$('#connection-text').textContent=state.connected?'本地服务已连接':'本地服务待启动';
  $('#connection-dot').className=state.connected?'ok':'warn';
  if(selected&&!state.panes.find(p=>p.id===selected))selected=null;
  const busy=(state.cards||[]).filter(c=>['running','review','blocked','triage'].includes(c.status)).length;
  $('#board-badge').hidden=!busy;$('#board-badge').textContent=busy;
  updateChatHeader();drawSidebar();drawPanes();
  if(view==='board')drawBoard();
  for (const s of state.chats||[]) if(s.status==='ready'&&chats[s.id]?.outbox?.some(o=>!o.sent)){chats[s.id].meta.status='ready';flushOutbox(s.id);}
}
async function refreshState(force=false) {
  if(stateBusy)return;stateBusy=true;const requestedWorkspace=workspace;
  try{const next=await api('state');if(workspace!==requestedWorkspace)return;state=next;workspace=state.workspace;drawState();if(force)toast('已刷新');$('#notice').hidden=true;}
  catch(e){$('#notice').hidden=false;$('#notice').textContent='连接异常：'+e.message;$('#connection-text').textContent='连接异常';$('#connection-dot').className='err';}
  finally{stateBusy=false;}
}
async function selectPane(id) {
  selected=id;selectedChat=null;readOnlyView=null;
  sessionStorage.setItem('misaka-pane',id);sessionStorage.removeItem('misaka-chat');
  lastScreen='';lastSize='';drawState();await showView('legacy');await resizeTerminal();await refreshScreen();
}
function sidebarVisible(){return innerWidth<=860?$('#app').classList.contains('sb-open'):!$('#app').classList.contains('sb-collapsed');}
function syncSidebarVisibility(){
  const open=sidebarVisible(),sidebar=$('#sidebar');if(!open&&sidebar.contains(document.activeElement))$('#rail-chats').focus();
  sidebar.inert=!open;sidebar.setAttribute('aria-hidden',String(!open));$('#rail-chats').setAttribute('aria-expanded',String(open));
  $('#sidebar-toggle').setAttribute('aria-label',open?'收起项目列表':'展开项目列表');
}
function setSidebarOpen(open){
  if(innerWidth<=860)$('#app').classList.toggle('sb-open',open);else{$('#app').classList.toggle('sb-collapsed',!open);localStorage.setItem('misaka-sidebar',open?'open':'collapsed');}
  closePopover();syncSidebarVisibility();
}
function toggleSidebar(){setSidebarOpen(!sidebarVisible());}
function syncRail(){
  $('#rail-home').classList.toggle('active',view==='chat');$('#rail-tools').classList.toggle('active',['board','team','skills','legacy'].includes(view));
  $$('.rail-item[data-view]').forEach(n=>{n.classList.toggle('active',n.dataset.view===view);if(n.dataset.view===view)n.setAttribute('aria-current','page');else n.removeAttribute('aria-current');});
}
function showToolsMenu(){
  const anchor=$('#rail-tools');if(togglePopover(anchor))return;const box=el('div','tools-menu');box.append(el('div','menu-head','项目工具'));
  for(const [name,label,ic] of [['board','任务看板','board'],['team','协作成员','team'],['skills','技能库','skills']])box.append(menuItem({icon:ic,label,checked:view===name,onClick:()=>showView(name)}));
  box.append(menuItem({icon:'history',label:'当前项目全部历史',onClick:showNativeHistory}));
  if(projectPanes().length||view==='legacy')box.append(menuItem({icon:'terminal',label:'外部终端',onClick:()=>showView('legacy')}));
  openPopover(anchor,box,{width:240,prefer:'side'});
}
async function showView(name) {
  if(!titles[name])return;view=name;closePopover();
  $$('.view').forEach(n=>n.hidden=n.id!=='view-'+name);
  syncRail();if(innerWidth<=860)setSidebarOpen(false);
  if(name!=='chat'){const t=$('#page-title');t.textContent=titles[name];t.classList.remove('editable');t.title='';$('#chat-status').hidden=true;$('#chat-role').hidden=true;$('#chat-actions').hidden=true;}
  if(name==='chat'){updateChatHeader();renderChat();}
  if(name==='board'){if(!state?.connected)await api('connect');await refreshState();drawBoard();}
  if(name==='legacy'){drawPanes();await refreshScreen();await resizeTerminal();}
  if(name==='team')await loadTeam();
  if(name==='research')await loadResearch();
  if(name==='documents')await loadDocuments();
  if(name==='settings')drawSettingsShell();
}

/* ---------- 终端渲染 ---------- */
async function refreshScreen() {if(guiClosed||!selected||view!=='legacy'||screenBusy||document.hidden)return;screenBusy=true;const id=selected;try{const screen=await api('screen',{id});if(id===selected)drawScreen(screen);}catch(e){if(id===selected){$('#notice').hidden=false;$('#notice').textContent='读取会话失败：'+e.message;}}finally{screenBusy=false;}}
async function resizeTerminal() {if(!selected||view!=='legacy'||!state?.panes.find(p=>p.id===selected)?.alive)return;const term=$('#terminal');const width=term.clientWidth-28,height=term.clientHeight-24;if(width<=0||height<=0)return;
  const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d');ctx.font=getComputedStyle(term).font;const charWidth=ctx.measureText('M').width||7.8;const cols=Math.max(40,Math.floor(width/charWidth)),rows=Math.max(8,Math.floor(height/20));const key=selected+':'+rows+':'+cols;if(key===lastSize)return;lastSize=key;await api('resize',{id:selected,rows,cols});}
new ResizeObserver(()=>guard(resizeTerminal)).observe($('#terminal'));
function queueInput(action,data={}) {const id=selected;if(!id)return Promise.resolve();inputChain=inputChain.catch(()=>{}).then(()=>api(action,{id,...data})).then(()=>refreshScreen());return inputChain;}
async function sendPaneMessage(enter=true) {
  const text=$('#message').value;if(!text.trim()||!selected){if(!selected)toast('请先选择一个终端进程',true);return;}
  await queueInput('send',{text,enter});$('#message').value='';
}
$('#message-form').onsubmit=e=>{e.preventDefault();guard(()=>sendPaneMessage(),$('#send-button'));};
$('#message').addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'&&!e.isComposing){e.preventDefault();guard(()=>sendPaneMessage(),$('#send-button'));}});
const specialKeys={Enter:'enter',Escape:'escape',ArrowUp:'up',ArrowDown:'down',ArrowLeft:'left',ArrowRight:'right',Tab:'tab',Backspace:'backspace',Delete:'delete',Home:'home',End:'end',PageUp:'pageup',PageDown:'pagedown'};
$('#terminal').addEventListener('keydown',e=>{
  if(!selected||e.isComposing)return;if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='c'&&window.getSelection()?.toString())return;
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='v')return;
  e.stopPropagation();
  if(specialKeys[e.key]){e.preventDefault();guard(()=>queueInput('key',{key:specialKeys[e.key]}));}
  else if(e.ctrlKey&&/^[a-z]$/i.test(e.key)){e.preventDefault();guard(()=>queueInput('input',{text:String.fromCharCode(e.key.toUpperCase().charCodeAt(0)-64)}));}
  else if(e.key.length===1&&!e.metaKey&&!e.altKey){e.preventDefault();guard(()=>queueInput('input',{text:e.key}));}
});
$('#terminal').addEventListener('compositionend',e=>{if(e.data)guard(()=>queueInput('input',{text:e.data}));});
$('#terminal').addEventListener('paste',e=>{e.preventDefault();const text=e.clipboardData?.getData('text/plain');if(text)guard(()=>queueInput('send',{text,enter:false}));});
$('#terminal').addEventListener('wheel',e=>{if(!selected)return;e.preventDefault();guard(()=>api('scroll',{id:selected,delta:Math.sign(e.deltaY)*4}).then(refreshScreen));},{passive:false});
$('#scroll-up').onclick=()=>guard(()=>api('scroll',{id:selected,delta:-20}).then(refreshScreen));
$('#scroll-bottom').onclick=()=>guard(()=>api('scroll',{id:selected,bottom:true}).then(refreshScreen));
$('#close-pane').onclick=()=>{const id=selected;confirmAction('关闭当前会话','这会结束当前会话进程。已保存的对话与项目文件会保留。',async()=>{await api('close',{id});if(selected===id)selected=null;await refreshState();},{label:'关闭',danger:true});};
const palette=['#25303b','#d88080','#90b793','#d7bc87','#8ba9ce','#b49ac6','#8cbfc5','#d6dee6','#768491','#e39292','#a3c7a4','#e8cf99','#a7bde1','#c8abdc','#a6d6db','#f1f5f8'];
function color(c) {if(Array.isArray(c))return 'rgb('+c.map(v=>Math.max(0,Math.min(255,Number(v)))).join(',')+')';if(Number.isInteger(c))return palette[c>=90?c-90+8:c-30]||'';return '';}
function drawScreen(screen) {
  const signature=JSON.stringify(screen.rows);if(lastScreen===signature)return;lastScreen=signature;
  const frag=document.createDocumentFragment();
  for(const runs of screen.rows){const row=el('div','terminal-line');for(const [text,s] of runs){const span=el('span','',text);let fg=color(s[0]),bg=color(s[1]);if(s[7])[fg,bg]=[bg||'#15140f',fg||'#ddd6c9'];if(fg)span.style.color=fg;if(bg)span.style.backgroundColor=bg;if(s[2])span.style.fontWeight='bold';if(s[3])span.style.opacity='.65';if(s[4])span.style.fontStyle='italic';if(s[5]||s[8])span.style.textDecoration=[s[5]?'underline':'',s[8]?'line-through':''].join(' ');row.append(span);}frag.append(row);}
  $('#terminal').replaceChildren(frag);
}

/* ---------- 其他视图 ---------- */
$('#research-form').onsubmit=e=>{e.preventDefault();guard(async()=>{const data=Object.fromEntries(new FormData(e.target));for(const k of Object.keys(data))if(k!=='goal')data[k]=Number(data[k]);await api('research',data);toast('研究已在后台启动，进度会出现在下方');e.target.reset();await loadResearch();refreshState();},$('button[type=submit]',e.target));};
function waitingNode(r) {return (r.nodes||[]).find(n=>n.status==='waiting_input')||((r.status==='waiting_input')?(r.nodes||[])[0]:null);}
async function openNode(node) {
  await refreshState();
  const session=(state?.sessions||[]).find(s=>s.path===node.session_file);
  if (!session) throw new Error('研究对话正在初始化，请稍后再试');
  await openAttached(session);
}
function showResearchLog(query, title) {
  const box=el('div'), status=el('p','status-chip'), output=el('pre');let alive=true;
  box.append(status,output);modal(title||'研究日志',box);
  $('#dialog').addEventListener('close',()=>{alive=false;},{once:true});
  (async()=>{while(alive&&!guiClosed){try{const r=await api('research_log',query);status.replaceChildren(r.running?el('span','spinner'):icon(r.exit_code===0?'check':'alert'),r.running?'运行中':r.exit_code===0?'已结束':'已退出（代码 '+r.exit_code+'）');output.textContent=r.output||'等待输出…';output.scrollTop=output.scrollHeight;if(!r.running)return;}catch(e){status.replaceChildren(icon('alert'),e.message);return;}await sleep(1500);}})();
}
async function loadResearch() {
  const root=$('#research-list');
  const [result, jobs]=await Promise.all([api('research_list'), api('research_jobs').catch(()=>({jobs:[]}))]);
  root.replaceChildren();
  const known=new Set(result.runs.map(r=>r.id));
  for (const j of jobs.jobs.filter(j=>!known.has(j.run_id)&&(j.running||Date.now()/1000-j.started<600))) {
    const card=el('article','card run-card pending-run'), top=el('div','run-top'), info=el('div');
    const meta=el('small');meta.append(j.running?el('span','spinner'):icon('alert'),j.running?'  正在初始化…':'  进程已退出（代码 '+j.exit_code+'），请查看日志');
    info.append(el('h3','',j.title),meta);top.append(info,button('查看日志',()=>showResearchLog({job_id:j.id},j.title),'btn ghost sm','terminal'));card.append(top);root.append(card);
  }
  if(!result.runs.length&&!root.children.length)return empty(root,'还没有研究记录。填写上方问题，开始第一项研究。');
  for (const r of result.runs) {
    const card=el('article','card run-card'+(waitingNode(r)?' needs-you':'')), top=el('div','run-top'), info=el('div'), actions=el('div','actions');
    const meta=el('small');meta.append(el('span','pill '+statusTone(r.status),statusText(r.status)),'  '+r.id+' · 第 '+(r.wave||0)+' 轮');
    info.append(el('h3','',r.question),meta);
    const job=jobs.jobs.filter(j=>j.run_id===r.id).sort((a,b)=>b.started-a.started)[0];
    if (job) actions.append(button('日志',()=>showResearchLog({run_id:r.id},r.question),'btn ghost sm','terminal'));
    if (!job?.running&&r.status!=='done') actions.append(button('继续运行',async()=>{await api('research_resume',{run_id:r.id});toast('研究已在后台恢复');await loadResearch();},'btn sm','play'));
    if (['active','waiting_input','stopping'].includes(r.status)) actions.append(button('停止',()=>confirmAction('停止研究','停止继续展开研究，并由原生工作流整理阶段性报告。',async()=>{const result=await api('research_stop',{run_id:r.id});toast(result.message);await loadResearch();},{label:'停止研究',danger:true}),'btn ghost sm danger','stop'));
    top.append(info,actions);card.append(top);
    const waiting=waitingNode(r);
    if (waiting) {const bar=el('div','needs-bar');bar.append(icon('alert'),el('span','','Last Order 拟好了计划，正在等你确认。打开研究对话讨论或同意后，她会让 Sisters 开始执行。'),button('打开研究对话',()=>openNode(waiting),'btn primary sm','arrow-up-right'));card.append(bar);}
    const nodes=el('div','nodes');
    for (const n of r.nodes) {const node=el('div','node'+(n.status==='waiting_input'?' waiting':''));node.append(el('b','',n.question),el('small','','深度 '+n.depth+' · '+statusText(n.status)));node.title=n.id;
      if(n.session_file)node.append(button('打开对话',()=>openNode(n),'btn sm','arrow-up-right'));nodes.append(node);}
    if (r.nodes.length) card.append(nodes);
    if (r.last_error) card.append(el('div','run-error',r.last_error));
    root.append(card);
  }
}
$('#refresh-research').onclick=()=>guard(loadResearch);
function drawBoard() {
  const cards=state?.cards||[], groups=[['待处理',['ready','todo','queued','pending']],['进行中 · 需介入',['running','review','blocked','triage']],['已结束',['done','failed','stopped','cancelled']]];
  const stats=$('#board-stats');stats.replaceChildren();
  for (const [name,value] of [['全部任务',cards.length],['进行中',cards.filter(c=>['running','review'].includes(c.status)).length],['已完成',cards.filter(c=>c.status==='done').length],['需要关注',cards.filter(c=>['blocked','triage','failed'].includes(c.status)).length]]) {const n=el('div','stat');n.append(el('span','',name),el('strong','',String(value)));stats.append(n);}
  const root=$('#board');root.replaceChildren();
  for (const [name,group] of groups) {
    const column=el('section','board-column'), items=cards.filter(c=>group.includes(c.status)||(!groups.some(g=>g[1].includes(c.status))&&name===groups[1][0]));
    const h=el('h3','',name);h.append(el('em','',String(items.length)));column.append(h);
    if (!items.length) column.append(el('div','empty','暂无任务'));
    for (const c of items) {
      const card=el('article','task-card');card.append(el('span','pill '+statusTone(c.status),statusText(c.status)),el('h4','',c.title),el('small','',c.id+' · '+c.assignee));
      const actions=el('div','actions');
      if (['ready','todo','stopped','failed'].includes(c.status)) actions.append(button('启动',async()=>{await api('card',{operation:'run',task_id:c.id});await refreshState();toast('任务已启动');},'btn sm','play'));
      if (c.has_session) actions.append(button('查看记录',()=>openCard(c)));
      const pane=state.panes.find(p=>p.card===c.id&&p.alive);
      if (pane) actions.append(button('进入会话',()=>openCard(c)),button('停止',()=>confirmAction('停止任务','结束这张任务卡的运行进程。',async()=>{const r=await api('card',{operation:'stop',task_id:c.id});toast(r.message||'已请求停止');await refreshState();},{label:'停止',danger:true}),'btn ghost sm danger'));
      else if (c.has_session) actions.append(button('继续对话',()=>cardReply(c)));
      card.append(actions);column.append(card);
    }
    root.append(column);
  }
}
function cardReply(card){const form=el('form'),input=el('textarea');input.rows=4;input.required=true;input.placeholder='输入补充要求或后续问题';const actions=el('div','dialog-actions');actions.append(button('发送并继续',async()=>{if(!input.value.trim())return;await api('card',{operation:'continue',task_id:card.id,text:input.value});await refreshState();toast('已发送补充要求');closeDialog();},'btn primary'));form.append(input,actions);form.onsubmit=e=>e.preventDefault();modal('继续任务 · '+card.title,form);input.focus();}
$('#refresh-board').onclick=()=>guard(()=>refreshState(true));
async function loadTeam() {
  const data=await api('roster'), root=$('#team-grid');rosterCache=data.members||[];root.replaceChildren();
  const members=[{id:null,label:'Last Order',sub:'最后之作 · 研究协调者',description:'与你讨论问题、制定计划、分配任务，并汇总研究结论。',model:state?.model},...rosterCache.map(m=>({...m,label:'Sister '+m.id,sub:'研究助手'}))];
  for (const m of members) {
    const card=el('article','card member-card'), head=el('div','member-head'), names=el('div');
    names.append(el('h3','',m.label),el('small','',m.sub));
    head.append(el('span','seal'+(m.id?' sister':''),m.id?String(m.id).slice(-2):'M'),names);
    card.append(head,el('p','',String(m.description||'').replace(/^---[\s\S]*?---\s*/, '').replace(/^#+ /gm,'').trim()),el('div','member-model',m.model||'使用全局默认模型'),button('开始对话',()=>goHome(m.id),'btn primary sm','compose'));
    root.append(card);
  }
}
async function loadDocuments(){
  const data=await api('documents'), root=$('#document-list');root.replaceChildren();
  if(!data.documents.length)empty(root,'当前项目还没有索引文档。导入材料后可以检索原文与核查引用。');
  for (const d of data.documents) {const row=el('div','row'), info=el('div','row-main'), actions=el('div','row-actions');info.append(el('strong','',d.title),el('small','',d.pages+' 页 · '+d.doc_id+' · '+(d.has_tree?'有结构索引':'按页索引')));actions.append(button('查看结构',()=>runCommand(['doc','tree',d.doc_id],'文档结构'),'btn ghost sm','tree'),button('核查引文',()=>verifyQuote(d),'btn ghost sm','quote'));row.append(icon('library'),info,actions);root.append(row);}
  await loadFiles('.');
}
function verifyQuote(doc){const form=el('form'),input=el('textarea');input.rows=4;input.placeholder='粘贴需要核查的原文引句';input.required=true;const actions=el('div','dialog-actions');actions.append(button('核查',async()=>{if(!input.value.trim())return;const quote=input.value;closeDialog();await runCommand(['doc','verify',quote,'--doc',doc.doc_id],'核查引文');},'btn primary'));form.append(input,actions);form.onsubmit=e=>e.preventDefault();modal('核查引文 · '+doc.title,form);input.focus();}
$('#document-form').onsubmit=e=>{e.preventDefault();guard(()=>{const data=new FormData(e.target);return runCommand(['doc','add',data.get('path'),...(data.has('tree')?[]:['--no-tree'])],'导入文档');},$('button[type=submit]',e.target));};
$('#document-search').onsubmit=e=>{e.preventDefault();guard(()=>runCommand(['doc','find',new FormData(e.target).get('query')],'检索原文'));};
$('#refresh-documents').onclick=()=>guard(loadDocuments);$('#file-root').onclick=()=>guard(()=>loadFiles('.'));
async function loadFiles(path){
  const result=await api('files',{path}), root=$('#file-list');
  if('content' in result){modal(result.path,el('pre','',result.content));return;}
  root.replaceChildren(el('div','file-path',result.path==='.'?workspace:result.path));
  if(result.path!=='.'){const up=button('',()=>loadFiles(result.path.split('/').slice(0,-1).join('/')||'.'),'row file-row');up.append(icon('arrow-up'),el('span','row-main','上一级'));root.append(up);}
  for(const f of result.entries){const b=button('',()=>loadFiles(f.path),'row file-row');b.append(icon(f.directory?'folder':'file'),el('span','row-main',f.name));root.append(b);}
  if(!result.entries.length)root.append(el('div','empty','这个文件夹是空的'));
}
async function runCommand(args,title='操作结果',after=null){
  const source=workspace,result=await api('command_output',{args,title}),box=el('div'),status=el('p','status-chip'),output=el('pre');
  status.append(el('span','spinner'),'正在运行…');box.append(status,output);modal(title,box);
  while(!guiClosed){const job=await api('job',{workspace:source,job_id:result.job_id});status.replaceChildren(job.status==='running'?el('span','spinner'):icon(job.status==='done'?'check':'alert'),statusText(job.status));status.className='status-chip '+(job.status==='done'?'ok':job.status==='running'?'':'warn');output.textContent=job.output||(job.status==='running'?'等待输出…':job.status==='done'?'操作已完成，没有返回内容。':'操作失败，没有返回详细信息。');output.scrollTop=output.scrollHeight;if(job.status!=='running'){if(job.status==='failed')toast(title+'执行失败，请查看输出',true);if(view==='documents'&&source===workspace)await loadDocuments();if(after)after(job);return;}await sleep(1000);}
}
function splitCommand(text){const tokens=[];let current='',quote=null,started=false;for(const c of text.trim()){if(quote){if(c===quote)quote=null;else current+=c;started=true;}else if(c==='"'||c==="'"){quote=c;started=true;}else if(/\s/.test(c)){if(started){tokens.push(current);current='';started=false;}}else{current+=c;started=true;}}if(quote)throw new Error('引号没有闭合');if(started)tokens.push(current);if(tokens[0]==='misaka')tokens.shift();return tokens;}

/* ---------- 事件绑定 ---------- */
$('#project-switch').onclick=()=>showProjectMenu();
$('#add-project').onclick=()=>guard(showProjectPicker,$('#add-project'));
for(const mode of ['projects','recent'])$('#view-'+mode).onclick=()=>{sidebarView=mode;localStorage.setItem('misaka-sidebar-view',mode);drawSidebar();};
document.addEventListener('click',e=>{const b=e.target.closest('button,a[data-action]');if(!b)return;
  if(b.dataset.view){e.preventDefault();guard(()=>showView(b.dataset.view));}
  if(b.dataset.action==='new-chat'){e.preventDefault();goHome();}
  if(b.dataset.action==='history')guard(showNativeHistory,b);
  if(b.dataset.key)guard(()=>queueInput('key',{key:b.dataset.key}),b);
  if(b.dataset.settings){e.preventDefault();openSettings(b.dataset.settings);}
  if(b.dataset.command)guard(()=>runCommand(JSON.parse(b.dataset.command),b.querySelector('h3')?.textContent||'MISAKA 命令'),b);});
$('#sidebar-toggle').onclick=toggleSidebar;$('#sidebar-open').onclick=toggleSidebar;$('#rail-chats').onclick=toggleSidebar;$('#rail-tools').onclick=showToolsMenu;$('#scrim').onclick=()=>setSidebarOpen(false);
window.addEventListener('resize',syncSidebarVisibility);
$('#chat-filter').addEventListener('input',drawSidebar);
$('#chat-filter').addEventListener('keydown',e=>{if(e.key==='Escape'){e.target.value='';drawSidebar();e.target.blur();}});
$('#chat-form').onsubmit=e=>{e.preventDefault();if(sendMode()==='stop')stopChat();else guard(submitChat);};
$('#chat-input').addEventListener('input',()=>{autoSize();slashIndex=0;drawSlash();updateSendButton();});
$('#chat-input').addEventListener('blur',()=>setTimeout(()=>{$('#slash-menu').hidden=true;},120));
$('#chat-input').addEventListener('keydown',e=>{
  if (e.isComposing) return;
  const menu=$('#slash-menu');
  if (!menu.hidden) {
    const n=slashMatches().length;
    if (e.key==='ArrowDown'||e.key==='ArrowUp') {e.preventDefault();slashIndex=(slashIndex+(e.key==='ArrowDown'?1:n-1))%n;drawSlash();return;}
    if (e.key==='Tab'||(e.key==='Enter'&&!e.shiftKey)) {e.preventDefault();acceptSlash();return;}
    if (e.key==='Escape') {e.preventDefault();menu.hidden=true;return;}
  }
  if (e.key==='Enter'&&!e.shiftKey&&!e.altKey) {e.preventDefault();if($('#chat-input').value.trim())$('#chat-form').requestSubmit();}
  else if (e.key==='Escape'&&chatFlags().ch?.streaming) {e.preventDefault();stopChat();}
  else if (e.key==='ArrowUp'&&!e.target.value&&selectedChat) {const last=[...(chatState(selectedChat).items||[])].reverse().find(i=>i.kind==='user');if(last?.text){e.preventDefault();e.target.value=last.text;autoSize();updateSendButton();}}
});
$('#chat-input').addEventListener('paste',e=>{for(const file of e.clipboardData?.files||[]){e.preventDefault();addImageFile(file);}});
$('#attach-btn').onclick=()=>$('#attach-input').click();
$('#attach-input').onchange=e=>{for(const file of e.target.files||[])addImageFile(file);e.target.value='';};
let dragDepth=0;
const dragHasFiles=e=>[...(e.dataTransfer?.types||[])].includes('Files');
$('#view-chat').addEventListener('dragenter',e=>{if(!dragHasFiles(e))return;e.preventDefault();dragDepth++;$('#drop-overlay').hidden=false;});
$('#view-chat').addEventListener('dragover',e=>{if(dragHasFiles(e))e.preventDefault();});
$('#view-chat').addEventListener('dragleave',()=>{if(--dragDepth<=0){dragDepth=0;$('#drop-overlay').hidden=true;}});
$('#view-chat').addEventListener('drop',e=>{e.preventDefault();dragDepth=0;$('#drop-overlay').hidden=true;if(chatFlags().readonly)return;for(const file of e.dataTransfer?.files||[])addImageFile(file);$('#chat-input').focus();});
$('#chat-model').onclick=e=>guard(()=>showModelPicker(e.currentTarget));
$('#chat-thinking').onclick=e=>guard(()=>showThinkingPicker(e.currentTarget));
$('#agent-pick').onclick=e=>guard(()=>showAgentPicker(e.currentTarget));
$('#chat-menu').onclick=e=>showChatMenu(e.currentTarget);
$('#chat-export').onclick=()=>guard(copyTranscript);
$('#page-title').onclick=()=>{if($('#page-title').classList.contains('editable'))startRename();};
$('#resume-snapshot').onclick=e=>guard(resumeCurrent,e.currentTarget);
function shutdownGui(){confirmAction('关闭网页服务','关闭服务会停止网页对话，记录保留。后台研究继续运行。仅关闭浏览器页面不会停止对话。',async()=>{const result=await api('shutdown');guiClosed=true;toast(result.message);$('#connection-text').textContent='网页服务已关闭';$('#connection-dot').className='err';$('#notice').hidden=false;$('#notice').textContent=result.message;},{label:'关闭服务',danger:true});}
document.addEventListener('keydown',e=>{
  if(e.defaultPrevented)return;
  const mod=e.ctrlKey||e.metaKey, key=e.key.toLowerCase();
  if (mod&&e.shiftKey&&key==='o') {e.preventDefault();goHome();}
  else if (mod&&!e.shiftKey&&key==='b') {e.preventDefault();toggleSidebar();}
  else if (mod&&key==='k') {e.preventDefault();setSidebarOpen(true);$('#chat-filter').focus();$('#chat-filter').select();}
  else if (e.key==='Escape'&&!$('#dialog').open&&view==='chat'&&e.target.id!=='chat-input'&&chatFlags().ch?.streaming) stopChat();
  else if (view==='chat'&&!mod&&!e.altKey&&e.key.length===1&&(e.target===document.body||e.target.closest?.('#chat-scroll'))&&!$('#dialog').open&&!$('#chat-input').disabled) $('#chat-input').focus();
});

/* ---------- 项目、草稿与任务对话 ---------- */
const drafts=new Map();
let recentProjects=jsonStored('misaka-projects',[]);if(!Array.isArray(recentProjects))recentProjects=[];
recentProjects=recentProjects.filter(p=>typeof p==='string');
const projectKey=path=>navigator.platform.toLowerCase().includes('win')?String(path).replaceAll('\\','/').toLowerCase():String(path);
let sidebarView=localStorage.getItem('misaka-sidebar-view')==='recent'?'recent':'projects',projectsBusy=false;
const projectData=new Map(),collapsedProjects=new Set(Array.isArray(jsonStored('misaka-collapsed-projects',[]))?jsonStored('misaka-collapsed-projects',[]):[]);
function rememberProject(path){if(!recentProjects.some(p=>samePath(p,path)))recentProjects.push(path);localStorage.setItem('misaka-projects',JSON.stringify(recentProjects));}
async function syncProjects(paths=[],migrate=false){const data=await api('projects',{paths,migrate});recentProjects=data.projects.map(p=>p.path);localStorage.setItem('misaka-projects',JSON.stringify(recentProjects));drawSidebar();}
async function refreshProjects(){if(projectsBusy)return;projectsBusy=true;
  try{await syncProjects();const paths=[...recentProjects];let cursor=0;
    await Promise.all(Array.from({length:Math.min(3,paths.length)},async()=>{while(cursor<paths.length){const path=paths[cursor++];try{const data=await api('project_sessions',{workspace:path});projectData.set(projectKey(path),data);}catch(e){projectData.set(projectKey(path),{...projectData.get(projectKey(path)),error:e.message});}drawSidebar();}}));
  }finally{projectsBusy=false;sidebarSig='';drawSidebar();}}
function rememberSelection(){if(selectedChat&&!isSnapshot(selectedChat))sessionStorage.setItem('misaka-chat:'+workspace,selectedChat);}
function draftKey(){return workspace+'|'+(selectedChat||'new');}
function saveDraft(){drafts.set(draftKey(),{text:$('#chat-input').value,images:[...pendingImages]});}
function restoreDraft(){const d=drafts.get(draftKey());$('#chat-input').value=d?.text||'';pendingImages=[...(d?.images||[])];drawChips();autoSize();updateSendButton();}
async function switchProject(path){const ticket=++projectSwitch;const next=await api('state',{workspace:path});if(ticket!==projectSwitch)return false;
  await syncProjects([next.workspace]);if(ticket!==projectSwitch)return false;
  saveDraft();rememberSelection();if(workspace)projectData.set(projectKey(workspace),{...state,saved:savedSessions});
  workspace=next.workspace;state=next;selected=null;selectedChat=null;readOnlyView=null;savedSessions=projectData.get(projectKey(workspace))?.saved||[];sidebarSig='';collapsedProjects.delete(projectKey(workspace));
  localStorage.setItem('misaka-workspace',workspace);const saved=sessionStorage.getItem('misaka-chat:'+workspace);if(saved&&(state.chats||[]).some(s=>s.id===saved&&!['closed','error'].includes(s.status)))selectedChat=saved;
  restoreDraft();closeDialog();drawState();renderChat();await showView('chat');await loadSaved();return ticket===projectSwitch;}
async function loadSaved(){const source=workspace;const data=await api('chat_sessions',{all_roles:true});if(source!==workspace)return;savedSessions=data.sessions;drawSidebar();}
async function resumeSaved(s){if(s.live){const entry=(state.sessions||[]).find(e=>e.path===s.path);if(entry)return openAttached(entry);throw new Error('此记录仍由后台进程使用，请稍后刷新');}const source=workspace;const r=await api('chat_native',{session_path:s.path,...(s.role?{role:s.role}:{})});if(source!==workspace)return;await refreshState();selectChat(r.chat_id);}
let folderPickerBusy=false;
async function showProjectPicker(){if(folderPickerBusy)return;folderPickerBusy=true;closePopover();$('#add-project').disabled=true;
  try{const result=await api('pick_folder',{},310000);if(result.path){await switchProject(result.path);toast('已添加项目 '+baseName(result.path));guard(refreshProjects);}}
  catch(e){toast(e.message,true);showProjectPathDialog();}finally{folderPickerBusy=false;$('#add-project').disabled=false;}}
function showProjectPathDialog(){
  const box=el('div'),form=el('form'),label=el('label','field','项目文件夹'),input=el('input'),actions=el('div','btn-row');
  input.value=workspace;input.required=true;input.setAttribute('aria-label','项目文件夹路径');label.append(input);
  actions.append(button('添加并打开',()=>form.requestSubmit(),'btn primary','folder'),button('系统选择文件夹…',showProjectPicker,'btn'));
  form.append(label,actions);form.onsubmit=e=>{e.preventDefault();guard(()=>switchProject(input.value));};
  box.append(form,el('p','hint','添加后，项目会保留在侧栏。每个项目拥有独立的对话与文件。'));
  modal('输入项目文件夹路径',box);input.focus();
}
async function openAttached(session){const id='attached:'+session.id;const ch=chatState(id);ch.meta={...ch.meta,name:session.title||session.role||'任务对话',workspace,role:session.role,status:'ready'};selectChat(id);await refreshAttached(id);}
async function refreshAttached(id){if(attachedBusy||id!==selectedChat||view!=='chat')return;attachedBusy=true;try{const r=await api('session_snapshot',{session_id:id.slice(9)});if(id!==selectedChat)return;const ch=chatState(id);buildItemsFromHistory(ch,r.messages);ch.streaming=r.state==='working';ch.meta.error=r.error;ch.meta.status=r.state==='saved'?'closed':'ready';ch.meta.paused=r.paused;readOnlyView=r.readonly?id:null;ch.meta.banner=r.readonly?'':r.paused?'任务已暂停。发送 /resume 或在右上角菜单中恢复。':'已连接到原任务。可以直接讨论计划、补充要求；发送 /pause 或 /resume 暂停与恢复。';flushOutbox(id);renderChat();updateChatHeader();}catch(e){if(id===selectedChat){chatState(id).meta.banner=e.message;updateChatHeader();}}finally{attachedBusy=false;}}
async function openCard(card){await refreshState();const s=(state.sessions||[]).find(s=>s.task_id===card.id||s.card===card.id||s.task===card.id);if(!s)throw new Error('任务对话正在初始化，请稍后再打开');await openAttached(s);}

/* ---------- 设置中心（原生替代终端设置向导） ---------- */
const SETTINGS_TABS=[['overview','概览与环境','gauge'],['models','模型与账号','model'],['team','研究团队','team'],['web','联网工具','globe'],['research','研究流程','research'],['project','项目与资料','folder'],['skills','技能','skills'],['appearance','外观','sun'],['advanced','高级','terminal']];
let settingsTab='overview', settingsCache={}, settingsTicket=0;
const sapi=(op,params={})=>api('settings',{op,params});
function openSettings(tab) {settingsTab=SETTINGS_TABS.some(t=>t[0]===tab)?tab:'overview';guard(()=>showView('settings'));}
function drawSettingsShell() {
  const nav=$('#settings-nav');nav.replaceChildren();
  for (const [key,label,ic] of SETTINGS_TABS) {const b=el('button','settings-tab'+(key===settingsTab?' active':''));b.type='button';b.append(icon(ic),el('span','',label));b.onclick=()=>{settingsTab=key;drawSettingsShell();};nav.append(b);}
  const body=$('#settings-body'), ticket=++settingsTicket;
  body.replaceChildren(skeleton());
  const draw={overview:drawOverview,models:drawModels,team:drawTeamSettings,web:drawWeb,research:drawResearchSettings,project:drawProjectSettings,skills:drawSkillsSettings,appearance:drawAppearance,advanced:drawAdvanced}[settingsTab];
  Promise.resolve().then(()=>draw(ticket)).catch(e=>{if(ticket===settingsTicket)body.replaceChildren(errorBox(e.message,()=>drawSettingsShell()));});
}
function skeleton() {const n=el('div','skeleton');n.append(el('div','sk-line w40'),el('div','sk-block'),el('div','sk-line w70'),el('div','sk-line w55'));const s=el('div','sk-note');s.append(el('span','spinner'),'正在读取本机配置…');n.append(s);return n;}
function errorBox(text, retry) {const n=el('div','error-card');n.append(icon('alert'),el('span','',text));if(retry)n.append(button('重试',retry,'btn sm'));return n;}
function settled(ticket, ...nodes) {if(ticket!==settingsTicket)return false;$('#settings-body').replaceChildren(...nodes);return true;}
function section(title, hint, ...children) {const c=el('section','card set-card');const h=el('div','set-head');h.append(el('h3','',title));if(hint)h.append(el('p','hint',hint));c.append(h,...children.filter(Boolean));return c;}
function check(ok, name, detail, action) {
  const row=el('div','check-row '+(ok===true?'ok':ok===false?'bad':'opt'));
  const mark=el('span','check-mark');mark.append(icon(ok===true?'check':ok===false?'x':'dot'));
  const main=el('div','row-main');main.append(el('strong','',name));if(detail)main.append(el('small','',detail));
  row.append(mark,main);if(action)row.append(action);return row;
}
function codeLine(text) {const n=el('div','code-line');n.append(el('code','',text));const b=el('button','icon-btn');b.type='button';b.title='复制';b.append(icon('copy'));b.onclick=()=>copyText(text,b);n.append(b);return n;}
function fieldInput(label, input, hint) {const f=el('label','field');f.append(label,input);if(hint)f.append(el('small','field-hint',hint));return f;}
function textInput(value='', placeholder='', type='text') {const i=el('input');i.type=type;i.value=value||'';i.placeholder=placeholder;i.autocomplete='off';i.spellcheck=false;return i;}
function selectInput(options, value) {const s=el('select');for(const [v,l] of options){const o=el('option','',l);o.value=v??'';if((v??'')===(value??''))o.selected=true;s.append(o);}return s;}
function linkTo(tab,label) {return button(label,()=>{settingsTab=tab;drawSettingsShell();},'btn ghost sm','chevron-right');}
async function settingsAction(fn, target, refresh=true) {
  return guard(async()=>{const r=await fn();if(r?.message)toast(r.message);for(const w of r?.warnings||[])toast(w,true);if(refresh){settingsCache={};drawSettingsShell();}return r;},target);
}

async function drawOverview(ticket) {
  const [ov, mo, team]=await Promise.all([sapi('overview'), sapi('models_overview').catch(()=>null), sapi('sisters').catch(()=>null)]);
  settingsCache.overview=ov;
  const provider=mo?.providers.find(p=>p.id===ov.provider);
  const steps=section('准备情况','按顺序完成这几步就可以开始研究。全部在这个页面完成，不需要打开终端。',
    check(!!provider?.configured,'登录模型服务',provider?.configured?`${provider.name} · ${provider.source||'已配置'}`:`当前默认服务商 ${ov.provider||'未设置'} 还没有可用凭证`,linkTo('models',provider?.configured?'管理':'去登录')),
    check(!!ov.model,'默认模型',ov.provider&&ov.model?`${ov.provider} / ${ov.model}`:'尚未选择',linkTo('models','更改')),
    check((team?.sisters||[]).length>0,'研究团队',(team?.sisters||[]).length?`${team.sisters.length} 位 Sister：${team.sisters.map(s=>s.id).join('、')}`:'还没有 Sister，研究任务没人接手；建议先建两位',linkTo('team',(team?.sisters||[]).length?'管理':'去添加')),
    check(ov.plan_approval?true:null,'研究计划审批',ov.plan_approval?'每个计划先由你确认再执行':'已关闭：计划会自动执行',linkTo('research','设置')));
  const env=section('运行环境','缺少的工具不影响对话，但会影响检索、读取 PDF 与提交结果。安装后刷新本页即可。',
    check(ov.python_ok,'Python',ov.python+(ov.python_ok?'':'（需要 3.12 或更新）')),
    ...ov.tools.map(t=>{const row=check(t.present?true:t.required?false:null,t.name,t.purpose);if(!t.present&&t.install)row.querySelector('.row-main').append(codeLine(t.install));return row;}),
    check(ov.office,'Office 文档','python-docx / openpyxl / python-pptx'+(ov.office?'':' 缺失：请重新安装 MISAKA')),
    (()=>{const row=check(ov.pageindex?true:null,'PDF 目录结构（PageIndex）',ov.pageindex?'已安装':'未安装：PDF 会按页索引，没有章节结构');if(ov.pageindex_install){row.querySelector('.row-main').append(codeLine(ov.pageindex_install.command));if(ov.pageindex_install.after_exit)row.querySelector('.row-main').append(el('small','','需要先关闭 MISAKA，再在命令行运行上面的命令。'));}return row;})(),
    el('div','set-actions',button('重新检查',()=>drawSettingsShell(),'btn sm','refresh')));
  settled(ticket, steps, env);
}

async function drawModels(ticket) {
  const data=await sapi('models_overview');settingsCache.models=data;
  const list=el('div','provider-list'), showAll=el('button','text-btn','显示全部服务商');showAll.type='button';
  const row=p=>{
    const r=el('div','provider-row'+(p.configured?' on':''));
    const main=el('div','row-main');const name=el('strong','',p.name);main.append(name);
    const meta=el('small');meta.append(p.configured?'已配置 · '+(p.source||'凭证已保存'):'未配置',p.oauth?' · 支持浏览器登录':'');main.append(meta);
    if(p.extras?.length&&p.extras_install){main.append(el('small','warn-text','缺少这个服务商的组件（'+p.extras.join('、')+'）'),codeLine(p.extras_install.command));}
    const actions=el('div','row-actions');
    if(p.id==='amazon-bedrock')actions.append(el('small','hint','使用本机 AWS 凭证'));
    else {if(p.oauth)actions.append(button('浏览器登录',()=>startLogin(p),'btn sm'+(p.configured?'':' primary'),'globe'));
      actions.append(button(p.oauth?'API Key':'填写 API Key',()=>apiKeyDialog(p),'btn sm'+(p.oauth||p.configured?'':' primary')));
      if(p.configured&&p.source&&!/环境|env/i.test(p.source))actions.append(button('',()=>confirmAction('移除登录信息','移除 '+p.name+' 在本机保存的凭证。环境变量中的密钥不受影响。',()=>settingsAction(()=>sapi('logout',{provider:p.id}))),'icon-btn','x'));}
    r.append(main,actions);return r;
  };
  const featured=data.providers.filter(p=>p.featured||p.configured), rest=data.providers.filter(p=>!p.featured&&!p.configured);
  featured.forEach(p=>list.append(row(p)));
  showAll.onclick=()=>{rest.forEach(p=>list.append(row(p)));showAll.remove();};
  const login=section('模型服务','有 ChatGPT Plus/Pro、Claude 等订阅可以直接浏览器登录；也可以填写按量计费的 API Key。密钥只保存在本机。',list,rest.length?showAll:null);
  // default model form
  const targetSel=selectInput(data.targets.map(t=>[t.key||'',t.label+(t.pinned?'（'+t.pinned+'）':t.key?'（跟随全局）':'')]),'');
  const providerSel=el('select'), modelSel=el('select'), info=el('p','hint');
  const configured=data.providers.filter(p=>p.configured);
  const fillProviders=current=>{providerSel.replaceChildren();for(const p of [...configured,...data.providers.filter(p=>!p.configured)]){const o=el('option','',p.name+(p.configured?'':'（未配置）'));o.value=p.id;if(p.id===current)o.selected=true;providerSel.append(o);}};
  const loadModels=async(current)=>{modelSel.replaceChildren(el('option','','正在读取…'));modelSel.disabled=true;
    try{const r=await sapi('models',{provider:providerSel.value});modelSel.replaceChildren();for(const m of r.models){const o=el('option','',m.name&&m.name!==m.id?m.name+' · '+m.id:m.id);o.value=m.id;if(m.id===current)o.selected=true;modelSel.append(o);}if(!r.models.length)modelSel.append(el('option','','这个服务商没有可选模型'));}
    catch(e){modelSel.replaceChildren(el('option','',e.message));}finally{modelSel.disabled=false;}};
  const syncTarget=()=>{const t=data.targets.find(t=>(t.key||'')===targetSel.value);const ref=t.pinned||(data.global.provider+'/'+data.global.model);const [prov,...rest]=ref.split('/');fillProviders(prov);loadModels(rest.join('/'));
    info.textContent=t.key?(t.pinned?`${t.label} 当前单独使用 ${t.pinned}。`:`${t.label} 当前跟随全局默认（${data.global.provider} / ${data.global.model}）。`)+'只影响这个角色。':`全局默认：${data.global.provider} / ${data.global.model}。没有单独设置的角色都使用它。`;
    follow.hidden=!t.key||!t.pinned;};
  targetSel.onchange=syncTarget;providerSel.onchange=()=>loadModels('');
  const save=button('保存为默认',()=>settingsAction(()=>sapi('set_default',{target:targetSel.value||null,provider:providerSel.value,model:modelSel.value})),'btn primary','check');
  const test=button('测试连接',()=>settingsAction(()=>sapi('verify',{provider:providerSel.value,model:modelSel.value}),null,false),'btn','refresh');
  const follow=button('改为跟随全局',()=>settingsAction(()=>sapi('set_default',{target:targetSel.value})),'btn ghost');
  const grid=el('div','form-grid two');grid.append(fieldInput('为谁设置',targetSel),fieldInput('服务商',providerSel),fieldInput('模型',modelSel));
  const defaults=section('默认模型','测试连接会发送一个极小的请求，确认凭证真的可用。',grid,info,el('div','set-actions',save,test,follow));
  syncTarget();
  settled(ticket, login, defaults);
}
function apiKeyDialog(p) {
  const form=el('form'), key=textInput('','粘贴 API Key','password'), actions=el('div','dialog-actions');
  actions.append(button('取消',closeDialog,'btn ghost'),button('保存',()=>form.requestSubmit(),'btn primary'));
  form.append(el('p','hint','密钥保存在本机的 MISAKA 凭证文件中，不会发送到别处。'),fieldInput(p.name+' API Key',key),actions);
  form.onsubmit=e=>{e.preventDefault();settingsAction(async()=>{const r=await sapi('set_key',{provider:p.id,key:key.value});closeDialog();return r;});};
  modal('填写 API Key',form);key.focus();
}
let loginId=null;
async function startLogin(p) {
  const r=await api('login_start',{provider:p.id});loginId=r.login_id;
  const box=el('div','login-box'), events=el('div','login-events'), promptBox=el('div','login-prompt'), status=el('p','status-chip');
  status.append(el('span','spinner'),'正在准备登录…');box.append(status,events,promptBox);
  modal('登录 '+p.name,box);
  const id=r.login_id;let shownEvents=0, shownPrompt='';
  $('#dialog').addEventListener('close',()=>{if(loginId===id){api('login_cancel',{login_id:id}).catch(()=>{});loginId=null;}},{once:true});
  while(loginId===id&&!guiClosed){
    let s;try{s=await api('login_status',{login_id:id});}catch(e){status.replaceChildren(icon('alert'),e.message);return;}
    for(const ev of s.events.slice(shownEvents)){
      const n=el('div','login-event');
      if(ev.event==='auth_url'){n.append(el('b','',ev.opened?'已在浏览器中打开登录页面':'请在浏览器中打开下面的链接'));const a=el('a','',ev.url);a.href=ev.url;a.target='_blank';a.rel='noopener noreferrer';n.append(a);if(ev.instructions)n.append(el('small','',ev.instructions));}
      else if(ev.event==='device_code'){n.append(el('b','','在浏览器中打开链接并输入代码'));const a=el('a','',ev.url);a.href=ev.url;a.target='_blank';a.rel='noopener noreferrer';const code=el('div','device-code',ev.code);n.append(a,code,button('复制代码',()=>copyText(ev.code),'btn sm','copy'));}
      else n.append(el('span','',ev.message));
      events.append(n);
    }
    shownEvents=s.events.length;
    const pr=s.prompt;
    if((pr?.id||'')!==shownPrompt){shownPrompt=pr?.id||'';promptBox.replaceChildren();
      if(pr){promptBox.append(el('b','',pr.message||'请输入'));
        if(pr.kind==='select'){const opts=el('div','btn-row');for(const o of pr.options)opts.append(button(o.label,()=>api('login_answer',{login_id:id,prompt_id:pr.id,value:o.id}),'btn'));promptBox.append(opts);}
        else{const f=el('form','inline-form'),i=textInput('',pr.kind==='manual_code'?'如果浏览器没有自动完成，把页面上的代码粘贴到这里':'',pr.kind==='secret'?'password':'text');f.append(i,button('提交',()=>f.requestSubmit(),'btn primary'));f.onsubmit=e=>{e.preventDefault();if(i.value.trim())guard(()=>api('login_answer',{login_id:id,prompt_id:pr.id,value:i.value.trim()}));};promptBox.append(f);setTimeout(()=>i.focus(),50);}}}
    if(s.status==='running'){status.replaceChildren(el('span','spinner'),pr?'等待你的输入':'等待浏览器完成登录…');}
    else{status.replaceChildren(icon(s.status==='done'?'check':'alert'),s.message||(s.status==='done'?'登录成功':'登录失败'));status.className='status-chip '+(s.status==='done'?'ok':'warn');promptBox.replaceChildren();loginId=null;
      if(s.status==='done'){toast(s.message||'登录成功');settingsCache={};if(view==='settings')drawSettingsShell();setTimeout(closeDialog,900);}return;}
    await sleep(800);
  }
}

async function drawTeamSettings(ticket) {
  const data=await sapi('sisters');
  const list=el('div','stack');
  if(!data.sisters.length)list.append(el('div','empty','还没有 Sister。Last Order 会把研究任务交给 Sisters；建议先添加两位，一位查找证据，一位质疑论证。'));
  for(const s of data.sisters){
    const card=el('div','member-row'), head=el('div','member-head');
    const names=el('div');names.append(el('h3','','Sister '+s.id),el('small','',s.model?'模型：'+s.model:'模型：跟随全局默认'));
    head.append(el('span','seal sister',String(s.id).slice(-2)),names);
    const actions=el('div','row-actions');
    actions.append(button('专长',()=>roleFileEditor(s.id,'DESCRIBE.md','Sister '+s.id+' 的专长（DESCRIBE.md）','Last Order 按这里的描述分配任务。'),'btn sm','pencil'),
      button('性格与声音',()=>roleFileEditor(s.id,'SOUL.md','Sister '+s.id+' 的 SOUL.md','她说话与工作的方式。'),'btn sm'),
      button('模型',()=>{settingsTab='models';drawSettingsShell();},'btn sm','model'),
      button('',()=>confirmAction('移除 Sister '+s.id,'移除她的配置文件夹。历史任务卡、工作区与对话记录会保留；有未完成的任务时无法移除。',()=>settingsAction(()=>sapi('remove_sister',{id:s.id})),{label:'移除',danger:true}),'icon-btn','x'));
    card.append(head,el('p','',s.description||'尚未填写专长'),actions);list.append(card);
  }
  const id=textInput(data.next_id,'例如 10032'), specialty=textInput('','例如：查找文献、整理证据'), modelSel=selectInput([['','跟随全局默认']],'');
  sapi('models',{configured_only:true}).then(r=>{for(const m of r.models){const o=el('option','',m.provider+' / '+(m.name||m.id));o.value=m.provider+'/'+m.id;modelSel.append(o);}}).catch(()=>{});
  const form=el('form');const grid=el('div','form-grid two');grid.append(fieldInput('编号',id),fieldInput('模型',modelSel,'Sisters 负责阅读与检索，用更便宜的模型很常见。'));
  form.append(grid,fieldInput('专长（用于任务分配，可选）',specialty),el('div','set-actions',button('添加 Sister',()=>form.requestSubmit(),'btn primary','plus')));
  form.onsubmit=e=>{e.preventDefault();settingsAction(()=>sapi('create_sister',{id:id.value.trim(),specialty:specialty.value.trim(),model:modelSel.value}));};
  const identity=section('身份文件','每个角色都会读取这些文件，直接在这里编辑。',
    check(null,'共享身份','所有角色最先读取的身份设定',button('编辑',()=>roleFileEditor(null,'SHARED_SOUL','共享身份','所有角色共用。'),'btn sm','pencil')),
    check(null,'Last Order 的 SOUL.md','协调者的声音与工作方式',button('编辑',()=>roleFileEditor('last_order','SOUL.md','Last Order 的 SOUL.md',''),'btn sm','pencil')));
  settled(ticket, section('Sisters','研究时 Last Order 拆分问题，把任务卡交给 Sisters 并行完成。',list), section('添加 Sister','',form), identity);
}
async function roleFileEditor(role, file, title, hint) {
  const r=await sapi('read_role_file',{role,file});
  const form=el('form'), area=el('textarea','mono-area');area.value=r.content;area.rows=16;
  const actions=el('div','dialog-actions');actions.append(button('取消',closeDialog,'btn ghost'),button('保存',()=>form.requestSubmit(),'btn primary'));
  form.append(el('p','hint',(hint?hint+' ':'')+r.path),area,actions);
  form.onsubmit=e=>{e.preventDefault();settingsAction(async()=>{const x=await sapi('write_role_file',{role,file,content:area.value});closeDialog();return x;});};
  modal(title,form);area.focus();
}

async function drawWeb(ticket) {
  const data=await sapi('web_overview');settingsCache.web=data;
  const state_=(r,label)=>check(r.ready,label,r.backend?(r.backend+(r.ready?' · 已就绪':' · 尚未就绪')+(r.error?' · '+r.error:'')):(r.error||'未选择'));
  const current=section('当前状态','这里只读取本机配置，不会发送网络请求。',state_(data.resolved.search,'搜索'),state_(data.resolved.extract,'网页提取'),check(data.keyless?true:null,'免密钥兜底',data.keyless?'开启：没有凭证时使用免费服务':'关闭'));
  // provider setup
  const capSel=selectInput([['both','搜索和提取'],['search','只用于搜索'],['extract','只用于网页提取']],'both');
  const provSel=el('select'), rowSel=el('select'), envBox=el('div','stack'), tag=el('p','hint');
  const usable=()=>data.providers.filter(p=>!p.disabled&&(capSel.value==='both'?p.search&&p.extract:p[capSel.value]));
  const fillProv=()=>{provSel.replaceChildren(selectInput([['','自动路由（有凭证的优先，再用免费兜底）']],'').firstChild);for(const p of usable()){const o=el('option','',p.display+(p.ready?' · 已就绪':''));o.value=p.name;provSel.append(o);}fillRows();};
  const fillRows=()=>{const p=data.providers.find(x=>x.name===provSel.value);rowSel.replaceChildren();rowSel.parentElement&&(rowSel.parentElement.hidden=!p||p.rows.length<2);if(!p){envBox.replaceChildren();tag.textContent='';return;}p.rows.forEach((r,i)=>{const o=el('option','',r.name+(r.badge?' · '+r.badge:''));o.value=i;rowSel.append(o);});fillEnv();};
  const fillEnv=()=>{const p=data.providers.find(x=>x.name===provSel.value);const r=p?.rows[Number(rowSel.value)||0];envBox.replaceChildren();tag.textContent=r?.tag||'';
    for(const v of r?.env_vars||[]){const set=data.credentials.find(c=>c.name===v.key)?.set;const i=textInput('',set?'已设置，留空保持不变':'','password');i.dataset.key=v.key;envBox.append(fieldInput(v.prompt||v.key,i,v.url?'获取：'+v.url:''));}};
  capSel.onchange=fillProv;provSel.onchange=fillRows;rowSel.onchange=fillEnv;
  const grid=el('div','form-grid two');grid.append(fieldInput('用途',capSel),fieldInput('服务',provSel),fieldInput('方案',rowSel));
  const providerForm=section('搜索与网页提取服务','选择研究时用来搜索与读取网页的服务。',grid,tag,envBox,el('div','set-actions',button('保存',()=>settingsAction(()=>sapi('web_provider',{name:provSel.value,capability:capSel.value,row:Number(rowSel.value)||0,env:Object.fromEntries($$('input',envBox).filter(i=>i.value.trim()).map(i=>[i.dataset.key,i.value.trim()]))})),'btn primary','check')));
  fillProv();
  // enable/disable
  const toggles=el('div','toggle-list');
  for(const p of data.providers){const r=el('label','toggle-row'),cb=el('input');cb.type='checkbox';cb.checked=!p.disabled;cb.onchange=()=>settingsAction(()=>sapi('web_enable',{name:p.name,enabled:cb.checked}));const main=el('span','row-main');main.append(el('strong','',p.display),el('small','',[p.search?'搜索':'',p.extract?'提取':''].filter(Boolean).join(' · ')+(p.ready?' · 已就绪':' · 未就绪')));r.append(cb,main);toggles.append(r);}
  // browser
  const b=data.browser, modeSel=selectInput([['off','不使用浏览器工具'],['local','本机浏览器'],['cdp','连接已打开的浏览器（CDP）'],...Object.keys(data.browser_services).map(n=>[n,'云端浏览器 · '+n])],b.enabled===false?'off':(b.cdp?'cdp':(b.cloud_provider&&b.cloud_provider!=='local'?b.cloud_provider:(b.enabled?'local':'off'))));
  const engineSel=selectInput([['auto','自动'],['chrome','Chrome'],['lightpanda','Lightpanda']],b.engine||'auto'), lpPath=textInput(b.lightpanda_path,'Lightpanda 可执行文件路径'), cdpUrl=textInput('','http://127.0.0.1:9222 或 ws://…','password'), svcBox=el('div','stack');
  const browserFields=el('div','stack');
  const syncBrowser=()=>{browserFields.replaceChildren();const m=modeSel.value;
    if(m==='local'){browserFields.append(fieldInput('引擎',engineSel));if(engineSel.value==='lightpanda')browserFields.append(fieldInput('路径',lpPath));}
    else if(m==='cdp')browserFields.append(fieldInput('CDP 地址',cdpUrl,b.cdp?'已设置；留空会要求重新填写':''));
    else if(m!=='off'){svcBox.replaceChildren();const rows=data.browser_services[m]||[];const rs=selectInput(rows.map((r,i)=>[String(i),r.name]),'0');const envs=el('div','stack');const fill=()=>{envs.replaceChildren();for(const v of rows[Number(rs.value)]?.env_vars||[]){const i=textInput('','留空保持不变','password');i.dataset.key=v.key;envs.append(fieldInput(v.prompt||v.key,i));}};rs.onchange=fill;fill();svcBox.append(fieldInput('方案',rs),envs);browserFields.append(svcBox);}};
  modeSel.onchange=syncBrowser;engineSel.onchange=syncBrowser;syncBrowser();
  const browser=section('浏览器工具','让 Agent 打开网页、点击与截图。',fieldInput('连接方式',modeSel),browserFields,el('div','set-actions',button('保存',()=>settingsAction(()=>sapi('web_browser',{mode:modeSel.value,engine:engineSel.value,lightpanda_path:lpPath.value.trim(),cdp_url:cdpUrl.value.trim(),env:Object.fromEntries($$('input[data-key]',browserFields).filter(i=>i.value.trim()).map(i=>[i.dataset.key,i.value.trim()]))})),'btn primary','check')));
  // credentials
  const creds=el('div','stack');
  for(const c of data.credentials){const i=textInput('',c.set?'已设置（'+(c.source||'')+'）':'未设置','password');const row=el('div','cred-row');row.append(el('code','',c.name),i,button('保存',()=>i.value.trim()&&settingsAction(()=>sapi('web_save',{changes:{['env.'+c.name]:i.value.trim()}})),'btn sm'));if(c.set&&c.source!=='env')row.append(button('',()=>settingsAction(()=>sapi('web_save',{remove:['env.'+c.name]})),'icon-btn','x'));creds.append(row);}
  // advanced
  const adv=el('div','stack');
  for(const g of data.groups){const d=el('details','adv-group');const s=el('summary');s.append(el('span','',g.title),el('em','',g.fields.filter(f=>f.value!==null).length+' 项已设置'),icon('chevron-right','chev'));d.append(s);const body=el('div','stack');
    for(const f of g.fields){const row=el('div','adv-row');let input;
      if(f.type==='bool')input=selectInput([['','（继承默认）'],['true','开启'],['false','关闭']],f.value==='true'?'true':f.value==='false'?'false':'');
      else if(f.type==='choice')input=selectInput([['','（继承默认）'],...f.choices.map(c=>[c,c])],f.value||'');
      else input=textInput(f.hidden?'':(f.value||''),f.hidden?'已设置（隐藏），留空保持不变':f.type==='list'?'用逗号分隔':f.type==='json'?'JSON':'（继承默认）',f.hidden?'password':'text');
      row.append(el('code','',f.key),input,button('保存',()=>{const v=input.value.trim();if(!v){if(f.value!==null)settingsAction(()=>sapi('web_save',{remove:[f.key]}));return;}settingsAction(()=>sapi('web_save',{changes:{[f.key]:v}}));},'btn sm'));body.append(row);}
    d.append(body);adv.append(d);}
  const tools=section('账号与可选工具','这些操作会联网或下载软件包，运行时在弹窗中显示输出。',el('div','btn-row',
    button('查看 xAI 账号',()=>runCommand(['web','accounts'],'xAI 账号'),'btn sm'),button('登录 xAI',()=>runCommand(['web','login'],'登录 xAI（按输出中的链接与代码操作）'),'btn sm','globe'),button('退出 xAI',()=>runCommand(['web','logout'],'退出 xAI'),'btn sm'),
    button('安装 ddgs（免费搜索）',()=>runCommand(['web','setup','ddgs','--install','--yes'],'安装 ddgs',()=>drawSettingsShell()),'btn sm','plus'),
    button('安装 agent-browser',()=>runCommand(['web','browser-install','agent-browser','--yes'],'安装 agent-browser'),'btn sm','plus'),button('安装 browser-use',()=>runCommand(['web','browser-install','browser-use','--yes'],'安装 browser-use'),'btn sm','plus')));
  const statusBox=el('details','card adv-status');const ss=el('summary');ss.append('完整状态（本机配置）',icon('chevron-right','chev'));statusBox.append(ss,el('pre','',data.status));
  settled(ticket,current,providerForm,section('启用或停用服务','停用后不会被自动选中。',toggles),browser,section('凭证与地址','值不会显示；留空保存不会修改。进程环境变量会覆盖这里的值。',creds),section('高级设置','保存位置：'+data.path+'。留空并保存会移除这一层的设置，恢复继承值。',adv),tools,statusBox);
}

async function drawResearchSettings(ticket) {
  const ov=settingsCache.overview||await sapi('overview');settingsCache.overview=ov;
  const seg=el('div','segmented');
  for(const [v,label,ic] of [[true,'先由我确认计划','check'],[false,'自动执行','play']]){const b=el('button',ov.plan_approval===v?'active':'');b.type='button';b.append(icon(ic),label);b.onclick=()=>settingsAction(()=>sapi('set_research',{plan_approval:v}));seg.append(b);}
  const approval=section('计划审批','开启时，每个研究节点的计划都会在研究对话里等你同意后才执行；没有固定口令，和 Last Order 讨论、同意即可。发起研究时也可以单独选择。',seg);
  const L=ov.limits, rows=[['节点并行数',L.parallel],['每个节点的任务卡并行数',L.sister_parallel],['追加轮次',L.max_followups],['修订次数',L.max_revisions],['研究深度',L.max_depth],['节点上限',L.max_nodes]];
  const table=el('div','kv-grid');for(const [k,v] of rows){table.append(el('span','',k),el('b','',String(v)));}
  const key=textInput('',ov.openalex.stored?'已保存，填写新值可替换':'粘贴 OpenAlex API Key','password');
  const oa=section('文献覆盖检查（OpenAlex）','Last Order 会用 OpenAlex 检查计划在文献中的位置。免费的 API Key 能避免匿名访问被暂停。',
    check(ov.openalex.stored||ov.openalex.shell?true:null,ov.openalex.name,ov.openalex.stored?'已保存在 '+ov.openalex.file:ov.openalex.shell?'由启动环境提供':'未设置：使用匿名访问'),
    fieldInput('API Key',key,'免费申请：'+ov.openalex.url),
    el('div','set-actions',button('保存',()=>key.value.trim()&&settingsAction(()=>sapi('set_research',{openalex_key:key.value.trim()})),'btn primary','check'),ov.openalex.stored?button('移除',()=>settingsAction(()=>sapi('set_research',{openalex_remove:true})),'btn ghost danger'):null));
  settled(ticket,approval,section('默认研究规模','发起研究时可以逐项调整；第一次建议深度 1、节点上限 3。',table),oa);
}

async function drawProjectSettings(ticket) {
  const folder=textInput(workspace,'项目文件夹'), create=el('input');create.type='checkbox';
  const createRow=el('label','check');createRow.append(create,el('span','','文件夹不存在时创建'));
  const init=section('初始化项目','把文件夹设为 MISAKA 项目：git 仓库、PROJECT.md 与任务卡目录。研究产物会存放在这里。',fieldInput('文件夹',folder),createRow,
    el('div','set-actions',button('初始化',()=>settingsAction(async()=>{const r=await sapi('init_project',{folder:folder.value.trim(),create:create.checked});if(r.lines?.length)modal('项目已就绪',el('pre','',r.lines.join('\n')));return r;},null,false),'btn primary','check'),button('切换到其他项目',showProjectPicker,'btn ghost','folder')));
  const src=textInput('sources','相对于项目的文件夹，或完整路径');
  const index=section('索引资料','把 PDF、Word、Markdown 等资料放进文件夹并建立索引，研究时 Sisters 就能引用具体页码。',fieldInput('资料文件夹',src),
    el('div','set-actions',button('开始索引',()=>runCommand(['doc','scan',src.value.trim()||'.'],'索引资料'),'btn primary','library'),button('查看已索引资料',()=>showView('documents'),'btn ghost')));
  settled(ticket, section('当前项目','',check(true,baseName(workspace),workspace)), init, index);
}

async function drawSkillsSettings(ticket) {
  const ov=settingsCache.overview||await sapi('overview');settingsCache.overview=ov;
  const P=ov.paths;
  const layers=section('技能层','技能是带 SKILL.md 的文件夹，角色在需要时读取。按优先顺序：',
    check(null,'角色自己的技能',P.roles+'/<角色>/skills/'),check(null,'所有角色共享',P.shared_skills),
    check(P.external_names?true:null,'与其他 Agent 工具共享（只读）',P.external_names?(P.external+'：'+(P.external_names.join('、')||'空')):'~/.agents/skills 不存在；其他 Agent 工具创建后会自动出现'));
  const id=textInput('','待审技能编号');
  const review=section('审阅与目录','',el('div','btn-row',button('已启用技能',()=>runCommand(['skills','list'],'已启用技能'),'btn sm'),button('待审阅',()=>runCommand(['skills','pending'],'待审阅技能'),'btn sm'),button('扫描项目',()=>runCommand(['skills','scan'],'扫描项目技能'),'btn sm')),
    el('div','inline-form',id,button('批准',()=>id.value.trim()&&runCommand(['skills','approve',id.value.trim()],'批准技能'),'btn sm primary'),button('拒绝',()=>id.value.trim()&&runCommand(['skills','reject',id.value.trim()],'拒绝技能'),'btn sm')));
  settled(ticket,layers,review);
}

function drawAppearance(ticket) {
  const seg=el('div','segmented');const cur=localStorage.getItem('misaka-theme')||'system';
  for(const [v,label,ic] of [['light','浅色','sun'],['dark','深色','moon'],['system','跟随系统','monitor']]){const b=el('button',cur===v?'active':'');b.type='button';b.dataset.themeChoice=v;b.append(icon(ic),label);b.onclick=()=>{applyTheme(v);};seg.append(b);}
  settled(ticket, section('配色','跟随系统时会随操作系统的深浅色自动切换。',seg));
}

function drawAdvanced(ticket) {
  const summary=el('div','kv-grid');for(const [k,v] of [['当前项目',workspace],['数据目录',state?.home||''],['默认模型',[state?.provider,state?.model].filter(Boolean).join(' / ')||'尚未配置'],['运行环境',(state?.platform||'')+' · MISAKA '+(state?.version||'')]]){summary.append(el('span','',k),el('b','',v));}
  const input=textInput('','例如：doc list 或 auth check');
  const form=el('form','inline-form');form.append(input,button('运行',()=>form.requestSubmit(),'btn primary'));
  form.onsubmit=e=>{e.preventDefault();guard(()=>runCommand(splitCommand(input.value),'misaka '+input.value.trim()));};
  const cmd=section('命令输出','运行不需要交互的 MISAKA 命令并查看输出，例如 doc list、doc scan sources、skills pending、auth check、web status。需要交互的功能都已在本页提供。',form);
  const panes=projectPanes();
  const ext=panes.length?section('外部终端进程','由终端版 MISAKA 启动的进程。',el('div','set-actions',button('查看 '+panes.length+' 个进程',()=>showView('legacy'),'btn','terminal'))):null;
  settled(ticket, section('本机信息','',summary), cmd, ext, section('网页服务','关闭后网页对话停止并保存；后台研究继续运行。',el('div','set-actions',button('关闭网页服务',shutdownGui,'btn ghost danger','power'))));
}

// Plan approval is the one moment a run needs the person; surface it wherever they are.
let waitingSeen=new Set();
async function checkResearchWaiting() {
  try {
    const r=await api('research_list');
    const waiting=r.runs.filter(run=>waitingNode(run));
    $('#research-badge').hidden=!waiting.length;$('#research-badge').textContent=waiting.length;
    for (const run of waiting) if(!waitingSeen.has(run.id)){waitingSeen.add(run.id);if(view!=='research')toast('研究「'+run.question.slice(0,24)+'」的计划等待你确认');}
  } catch {}
}
/* ---------- 启动 ---------- */
async function boot(){
  if (localStorage.getItem('misaka-sidebar')==='collapsed'&&innerWidth>860) $('#app').classList.add('sb-collapsed');
  syncSidebarVisibility();syncRail();
  updateChatHeader();
  if(!token){$('#notice').hidden=false;$('#notice').textContent='请通过 MISAKA GUI 启动器打开页面，以取得本次访问凭证。';$('#connection-text').textContent='等待授权入口';return;}
  try{
    if(localWorkspace){try{state=await api('state',{workspace:localWorkspace});}catch{localStorage.removeItem('misaka-workspace');localWorkspace='';}}
    if(!state)state=await api('state');
    workspace=state.workspace;rememberProject(workspace);await syncProjects(recentProjects,true);
    const savedChat=sessionStorage.getItem('misaka-chat:'+workspace)||sessionStorage.getItem('misaka-chat');
    if(savedChat&&(state.chats||[]).some(c=>c.id===savedChat))selectChat(savedChat);
    drawState();updateChatHeader();
    await loadSaved();guard(refreshProjects);checkResearchWaiting();loadRoster().then(()=>{if(selectedChat)renderChat();});
  }catch(e){$('#notice').hidden=false;$('#notice').textContent='启动失败：'+e.message;}
  pollChats();
  setInterval(()=>{if(guiClosed)return;refreshScreen();if(++refreshTick%6===0){refreshState();if(view==='research')guard(loadResearch);if(refreshTick%24===0){guard(loadSaved);guard(refreshProjects);}if(refreshTick%12===0)checkResearchWaiting();}if(refreshTick%120===0&&!selectedChat)updateChatHeader();},500);
}
boot();
