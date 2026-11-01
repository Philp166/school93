(function(){
var ed=document.querySelector('.ed');if(!ed)return;
var url=window.EDIT_URL,frame=document.getElementById('edFrame'),drawer=document.getElementById('drawer'),box=document.getElementById('edForm');
var cur=null,dirty=false,keepScroll=0,afterLoad=null;
function doc(){try{return frame.contentDocument}catch(e){return null}}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function post(u,data){var fd=new FormData();fd.append('csrf',window.CSRF);for(var k in data)if(data[k]!=null)fd.append(k,data[k]);return fetch(u,{method:'POST',body:fd}).then(function(r){return r.json()})}
// ---------- «Сохранено» и всплывашка ----------
var sv=document.querySelector('#saved span');
function saving(){sv.parentNode.classList.add('busy');sv.textContent='Сохраняю…'}
function saved(ok){sv.parentNode.classList.remove('busy');sv.parentNode.classList.toggle('err',!ok);sv.textContent=ok?'Все изменения сохранены':'Не сохранилось, обновите страницу'}
var tt,t2=document.getElementById('toast2');
function toast(text,undo){t2.querySelector('span').textContent=text;var b=t2.querySelector('button');b.hidden=!undo;b.onclick=function(){t2.classList.remove('on');undo()};t2.classList.add('on');clearTimeout(tt);tt=setTimeout(function(){t2.classList.remove('on')},undo?6000:2200)}
// ---------- страница в рамке ----------
function reloadFrame(then){var d=doc();keepScroll=d?d.defaultView.scrollY:0;afterLoad=then||null;frame.contentWindow.location.reload()}
frame.addEventListener('load',function(){var d=doc();if(!d)return;if(keepScroll)d.defaultView.scrollTo(0,keepScroll);keepScroll=0;
 var sel=new URLSearchParams(location.search).get('sel');if(sel&&!afterLoad){afterLoad=function(){focusBlock(sel,true)};history.replaceState(null,'',location.pathname+'?url='+encodeURIComponent(url))}
 if(afterLoad){var f=afterLoad;afterLoad=null;setTimeout(f,60)}});
function focusBlock(path,open){var d=doc();if(!d)return;var el=d.querySelector('[data-eb][data-path="'+path+'"]');if(!el)return;
 var pane=el.closest('.pane');if(pane&&!pane.classList.contains('on')){var seg=pane.parentNode.querySelector(':scope > .js-seg');var btn=seg&&seg.querySelector('button[data-p="'+pane.dataset.pane+'"]');if(btn)btn.click()}
 el.scrollIntoView({block:'center'});el.classList.add('eb-flash');setTimeout(function(){el.classList.remove('eb-flash')},1600);if(open)openBlock(path)}
// ---------- панель справа ----------
function closeDrawer(force){if(!force&&dirty&&!confirm('Изменения в блоке не сохранены. Закрыть?'))return false;dirty=false;cur=null;drawer.classList.remove('on');box.innerHTML='';mark(null);return true}
function mark(path){var d=doc();if(!d)return;d.querySelectorAll('.eb-sel').forEach(function(x){x.classList.remove('eb-sel')});if(path){var el=d.querySelector('[data-eb][data-path="'+path+'"]');if(el)el.classList.add('eb-sel')}}
function openBlock(path){
 if(dirty&&cur&&cur!==path&&!confirm('Изменения в блоке не сохранены. Перейти к другому?'))return;
 dirty=false;cur=path;mark(path);
 fetch('/admin/pages/form?url='+encodeURIComponent(url)+'&path='+encodeURIComponent(path)).then(function(r){return r.text()}).then(function(h){
  box.innerHTML=h;drawer.classList.add('on');box.scrollTop=0;
  var f=box.querySelector('form.bf__form');if(!f)return;
  f.addEventListener('input',function(){dirty=true});f.addEventListener('change',function(){dirty=true});
  if(f.classList.contains('bf__data'))initData(f);
  f.addEventListener('submit',function(e){e.preventDefault();var btn=f.querySelector('[type=submit]');btn.disabled=true;saving();
   var fd=new FormData(f);if(f.classList.contains('bf__data'))fd.append('data',JSON.stringify(collect(f)));
   fetch('/admin/pages/save',{method:'POST',body:fd}).then(function(r){return r.json()}).then(function(j){btn.disabled=false;saved(!!j.ok);if(!j.ok){alert('Не сохранилось. Обновите страницу.');return}
    dirty=false;var p=cur;closeDrawer(true);toast('Сохранено. Уже на сайте.');reloadFrame(function(){focusBlock(p)})})})})}
// ---------- блоки с данными ----------
var cache={};
function initData(f){var kind=f.closest('.bf').dataset.kind,data=JSON.parse(f.querySelector('.bf__json').textContent||'{}');f._kind=kind;f._data=data;
 if(kind==='clubs'||!data.groups){data.groups=[{title:'',ids:data.ids||[]}]}
 var ids=[];data.groups.forEach(function(g){(g.ids||[]).forEach(function(i){ids.push(i)})});
 var au=f.querySelector('[data-k=auto]');function syncAuto(){if(au)f.querySelector('.dgroups').hidden=au.checked}if(au)au.addEventListener('change',syncAuto);
 var vs=f.querySelector('[data-k=view]');if(vs)vs.addEventListener('change',function(){data.view=vs.value;readGroups(f);renderGroups(f)});
 var ag=f.querySelector('[data-add-group]');if(ag)ag.addEventListener('click',function(){readGroups(f);data.groups.push({title:'Новая группа',ids:[]});renderGroups(f);dirty=true});
 if(!ids.length){renderGroups(f);syncAuto();return}
 fetch('/admin/lib/'+kind+'/get?ids='+ids.join(',')).then(function(r){return r.json()}).then(function(j){(j.items||[]).forEach(function(it){cache[kind+it.id]=it});renderGroups(f);syncAuto()})}
function readGroups(f){var data=f._data,gs=[];f.querySelectorAll('.dgroup-a').forEach(function(g){var o={ids:[].map.call(g.querySelectorAll('.ditem'),function(x){return +x.dataset.id})};
 var t=g.querySelector('[data-g=title]');if(t)o.title=t.value;var ph=g.querySelector('[data-g=phone]');if(ph)o.phone=ph.value;var nt=g.querySelector('[data-g=note]');if(nt)o.note=nt.value;gs.push(Object.assign({},data.groups[gs.length]||{},o))});data.groups=gs}
function renderGroups(f){var data=f._data,kind=f._kind,limit=+f.dataset.limit||0,service=data.view==='service';
 f.querySelector('.dgroups').innerHTML=data.groups.map(function(g,gi){
  var head=(kind==='clubs'||limit||cur==='card')?'':'<div class="dgroup-a__head"><input data-g="title" value="'+esc(g.title||'')+'" placeholder="Подзаголовок группы (необязательно)">'+(data.groups.length>1?'<button type="button" class="x" data-del-group title="Удалить группу">×</button>':'')+'</div>';
  var extra=service?'<div class="dgroup-a__extra"><input data-g="phone" value="'+esc(g.phone||'')+'" placeholder="Телефон группы"><input data-g="note" value="'+esc(g.note||'')+'" placeholder="Часы приёма"></div>':'';
  var items=(g.ids||[]).map(function(id){var it=cache[kind+id]||{title:'Запись №'+id,sub:''};
   return '<div class="ditem" draggable="true" data-id="'+id+'"><span class="ditem__h">⋮⋮</span><div class="ditem__t"><b>'+esc(it.title)+'</b><span>'+esc(it.sub||'')+'</span></div><button type="button" class="x" data-rm title="Убрать из блока (из базы не удаляется)">×</button></div>'}).join('');
  return '<div class="dgroup-a" data-gi="'+gi+'">'+head+extra+'<div class="ditems">'+(items||'<div class="dempty">Пока пусто</div>')+'</div><button type="button" class="addrow" data-lib>'+(limit?((g.ids||[]).length?'Заменить':'Выбрать'):'+ Добавить из базы')+'</button></div>'}).join('')}
function collect(f){readGroups(f);var d=f._data,out={};
 f.querySelectorAll('[data-k]').forEach(function(i){out[i.dataset.k]=i.type==='checkbox'?i.checked:i.dataset.k==='word'?i.value.split(',').map(function(s){return s.trim()}).filter(Boolean):i.value});
 if(f._kind==='clubs'||cur==='card'){out.ids=(d.groups[0]||{}).ids||[]}else{out.groups=d.groups}return out}
box.addEventListener('click',function(e){var t=e.target,f=box.querySelector('form.bf__data');
 if(t.closest('[data-close]')){closeDrawer();return}
 if(f){var it=t.closest('.ditem');
  if(t.closest('[data-rm]')&&it){it.remove();dirty=true;readGroups(f);return}
  if(t.closest('[data-del-group]')){readGroups(f);f._data.groups.splice(+t.closest('.dgroup-a').dataset.gi,1);renderGroups(f);dirty=true;return}
  var lb=t.closest('[data-lib]');if(lb){readGroups(f);var gi=+lb.closest('.dgroup-a').dataset.gi,limit=+f.dataset.limit||0;
   openLibrary(f._kind,function(item){cache[f._kind+item.id]=item;readGroups(f);var g=f._data.groups[gi];if(limit){f._data.groups.forEach(function(x){x.ids=[]});g.ids=[item.id]}else if(g.ids.indexOf(item.id)<0)g.ids.push(item.id);renderGroups(f);dirty=true;return !limit},[].concat.apply([],f._data.groups.map(function(g){return g.ids})));return}}
 var mv=t.closest('[data-move]');if(mv&&cur&&cur.indexOf('b:')===0){move(cur.slice(2),mv.dataset.move);return}
 if(t.closest('[data-del-block]')&&cur){var id=cur.slice(2);closeDrawer(true);del(id);return}
 var rv=t.closest('[data-revert]');if(rv){if(rv.dataset.ask&&!confirm(rv.dataset.ask))return;saving();post('/admin/pages/revert',{url:url,path:cur,history:rv.dataset.revert}).then(function(j){saved(!!j.ok);if(!j.ok)return;var p=cur;dirty=false;toast('Блок восстановлен');reloadFrame(function(){openBlock(p)})})}});
box.addEventListener('dragstart',function(e){var it=e.target.closest&&e.target.closest('.ditem');if(!it)return;it.classList.add('drag');box._drag=it});
box.addEventListener('dragend',function(){if(box._drag)box._drag.classList.remove('drag');box._drag=null;dirty=true});
box.addEventListener('dragover',function(e){var d=box._drag;if(!d)return;var list=e.target.closest&&e.target.closest('.ditems');if(!list)return;e.preventDefault();
 var after=[].slice.call(list.querySelectorAll('.ditem:not(.drag)')).find(function(x){var r=x.getBoundingClientRect();return e.clientY<r.top+r.height/2});var em=list.querySelector('.dempty');if(em)em.remove();if(after)list.insertBefore(d,after);else list.appendChild(d)});
// ---------- действия с блоками ----------
function move(id,dir){saving();post('/admin/blocks/move',{id:id,dir:dir}).then(function(j){saved(true);if(!j.moved){toast('Блок уже крайний');return}reloadFrame(function(){focusBlock('b:'+id)})})}
function del(id){saving();post('/admin/blocks/delete',{id:id}).then(function(j){saved(!!j.ok);if(!j.ok){toast('Этот блок удалить нельзя: без него страница не соответствует требованиям');return}
 reloadFrame();toast('Блок удалён',function(){saving();post('/admin/blocks/restore',{id:id}).then(function(){saved(true);reloadFrame(function(){focusBlock('b:'+id)})})})})}
function saveField(path,field,value){saving();return post('/admin/pages/field',{url:url,path:path,field:field,value:value}).then(function(j){saved(!!j.ok);if(j.ok)toast('Сохранено. Уже на сайте.');return j.ok}).catch(function(){saved(false)})}
function status(st){saving();post('/admin/admission/status',{status:st}).then(function(j){saved(!!j.ok);toast('Статус приёма изменён. Обновлён и на главной.');reloadFrame()})}
// ---------- библиотека ----------
var lib=document.getElementById('library'),libKind=null,libPick=null,libHave=[],libTimer=null;
var KN={people:['Добавить человека','Фамилия или должность'],docs:['Добавить документ','Название документа'],clubs:['Добавить кружок','Название кружка']};
function openLibrary(kind,pick,have){libKind=kind;libPick=pick;libHave=have||[];lib.hidden=false;document.getElementById('libTitle').textContent=KN[kind][0];var q=lib.querySelector('.lib-q');q.value='';q.placeholder=KN[kind][1];
 lib.querySelectorAll('.lib-new').forEach(function(x){x.hidden=x.dataset.k!==kind;x.reset()});lib.querySelector('.lib-err').hidden=true;setTab('find');search('');setTimeout(function(){q.focus()},50)}
function setTab(n){lib.querySelectorAll('.lib-tabs button').forEach(function(b){b.classList.toggle('on',b.dataset.lt===n)});lib.querySelectorAll('.lib-pane').forEach(function(p){p.hidden=p.dataset.lp!==n})}
function search(q){fetch('/admin/lib/'+libKind+'?q='+encodeURIComponent(q)).then(function(r){return r.json()}).then(function(j){lib.querySelector('.lib-list').innerHTML=(j.items||[]).map(function(it){var here=libHave.indexOf(it.id)>=0;
 return '<div class="lib-it"><div><b>'+esc(it.title)+'</b><span>'+esc(it.sub||'')+'</span></div><em>'+(it.used?'на сайте: '+it.used:'нигде не стоит')+'</em><button type="button" class="a-btn a-btn--sm'+(here?' a-btn--ghost':'')+'" data-pick=\''+esc(JSON.stringify(it))+'\''+(here?' disabled':'')+'>'+(here?'Уже здесь':'Добавить')+'</button></div>'}).join('')||'<div class="dempty">Ничего не найдено. Можно создать новую запись на соседней вкладке.</div>'})}
lib.addEventListener('click',function(e){var t=e.target;if(t.closest('[data-modal-close]')||t===lib){lib.hidden=true;return}var lt=t.closest('[data-lt]');if(lt){setTab(lt.dataset.lt);return}
 var pk=t.closest('[data-pick]');if(pk){var it=JSON.parse(pk.dataset.pick);libHave.push(it.id);var keep=libPick(it);pk.disabled=true;pk.textContent='Добавлено';pk.classList.add('a-btn--ghost');if(keep===false)lib.hidden=true}});
lib.querySelector('.lib-q').addEventListener('input',function(e){clearTimeout(libTimer);var v=e.target.value;libTimer=setTimeout(function(){search(v)},220)});
lib.querySelectorAll('.lib-new').forEach(function(fm){fm.addEventListener('submit',function(e){e.preventDefault();var fd=new FormData(fm);fd.append('csrf',window.CSRF);
 fetch('/admin/lib/'+fm.dataset.k+'/new',{method:'POST',body:fd}).then(function(r){return r.json()}).then(function(j){var er=lib.querySelector('.lib-err');if(!j.ok){er.textContent=j.error||'Не получилось';er.hidden=false;return}libPick(j.item);lib.hidden=true;toast('Запись создана в базе и добавлена. Нажмите «Сохранить».')})})});
// ---------- каталог блоков ----------
var cat=document.getElementById('catalog'),insertAt=null,OPEN_AFTER={people:1,docs:1,clubs:1,cards:1,steps:1,faq:1,links:1,phones:1,checkcards:1,tabs:1,feed:1};
function insert(opts){if(dirty&&!closeDrawer())return;insertAt=opts;cat.hidden=false}
cat.addEventListener('click',function(e){var t=e.target;if(t.closest('[data-modal-close]')||t===cat){cat.hidden=true;return}var ti=t.closest('[data-type]');if(!ti||!insertAt)return;
 var data={url:url,type:ti.dataset.type};if(insertAt.after)data.after=insertAt.after;if(insertAt.parent){data.parent=insertAt.parent;data.tab=insertAt.tab}
 cat.hidden=true;saving();post('/admin/blocks/add',data).then(function(j){saved(!!j.ok);if(!j.ok){alert('Не получилось добавить блок.');return}var p='b:'+j.id,tp=ti.dataset.type;reloadFrame(function(){focusBlock(p,!!OPEN_AFTER[tp])})})});
document.addEventListener('keydown',function(e){if(e.key==='Escape'){lib.hidden=true;cat.hidden=true;closeDrawer()}});
// ---------- выбор страницы ----------
var pb=document.getElementById('pickB'),pm=document.getElementById('pickM');
pb.addEventListener('click',function(e){e.stopPropagation();pm.classList.toggle('on');if(pm.classList.contains('on'))pm.querySelector('.pick__q').focus()});
document.addEventListener('click',function(e){if(!e.target.closest('.pick'))pm.classList.remove('on')});
pm.querySelector('.pick__q').addEventListener('input',function(){var q=this.value.toLowerCase();pm.querySelectorAll('a').forEach(function(a){a.hidden=q&&a.dataset.t.indexOf(q)<0});pm.querySelectorAll('h5').forEach(function(h){var n=h.nextElementSibling,any=false;while(n&&n.tagName==='A'){if(!n.hidden)any=true;n=n.nextElementSibling}h.hidden=!any})});
// ---------- телефон / компьютер ----------
var cv=document.getElementById('canvas');
document.querySelectorAll('#dev button').forEach(function(b){b.addEventListener('click',function(){document.querySelectorAll('#dev button').forEach(function(x){x.classList.toggle('on',x===b)});cv.classList.toggle('phone',!!b.dataset.w)})});
window.S93Edit={open:openBlock,insert:insert,move:move,del:del,saveField:saveField,status:status,names:window.TYPE_NAMES,
 reset:function(){if(confirm('Вернуть исходный вид страницы? Все правки, добавленные и удалённые блоки на ней пропадут.'))document.getElementById('resetForm').submit()},
 go:function(href){if(!dirty||confirm('Изменения в блоке не сохранены. Уйти?'))location.href=href}};
window.addEventListener('beforeunload',function(e){if(dirty){e.preventDefault();e.returnValue=''}});
})();
