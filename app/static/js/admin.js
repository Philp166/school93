(function(){
// меню на телефоне
var t=document.getElementById('sideToggle');if(t)t.onclick=function(){document.body.classList.toggle('side-open')};
document.addEventListener('click',function(e){if(document.body.classList.contains('side-open')&&!e.target.closest('.side,#sideToggle'))document.body.classList.remove('side-open')});
// уведомление
var toast=document.getElementById('toast');if(toast){setTimeout(function(){toast.classList.remove('on')},3500);history.replaceState(null,'',location.pathname+location.search.replace(/([?&])ok=[^&]*&?/,'$1').replace(/[?&]$/,''))}
// подтверждение удаления
document.addEventListener('click',function(e){var b=e.target.closest('[data-confirm]');if(b&&!confirm(b.getAttribute('data-confirm'))){e.preventDefault()}});
// несохранённые изменения: только если форма реально отличается от исходной
function snap(f){var a=[];new FormData(f).forEach(function(v,k){if(k!=='csrf')a.push(k+'='+(v instanceof File?v.name+':'+v.size:v))});return a.join('&')}
document.querySelectorAll('form.js-dirty').forEach(function(f){var init=null,dirty=false,sent=false;
 setTimeout(function(){init=snap(f)},300);
 function check(){if(init===null)return;dirty=snap(f)!==init;document.body.classList.toggle('is-dirty',dirty)}
 f.addEventListener('input',check);f.addEventListener('change',check);
 f.addEventListener('submit',function(){sent=true});
 window.addEventListener('beforeunload',function(e){if(dirty&&!sent){e.preventDefault();e.returnValue=''}})});
// счётчик символов
document.querySelectorAll('[data-count]').forEach(function(i){var max=+i.getAttribute('data-count');var c=document.createElement('span');c.className='count';i.parentNode.insertBefore(c,i.nextSibling);
 function u(){c.textContent=i.value.length+' из '+max;c.classList.toggle('over',i.value.length>max)}i.addEventListener('input',u);u()});
// добавить / удалить строку
document.addEventListener('click',function(e){
 var a=e.target.closest('[data-add]');if(a){var rows=a.previousElementSibling;while(rows&&!rows.hasAttribute('data-rows'))rows=rows.previousElementSibling;
  var last=[].slice.call(rows.querySelectorAll(':scope > .rowi:not(.rowi--h)')).pop();var n=last.cloneNode(true);n.querySelectorAll('input,textarea').forEach(function(i){i.value=''});n.querySelectorAll('select').forEach(function(s){s.selectedIndex=0});rows.appendChild(n);var fi=n.querySelector('input,textarea');if(fi)fi.focus();rows.closest('form').dispatchEvent(new Event('input'));}
 var mv=e.target.closest('[data-up],[data-down]');if(mv){var row=mv.closest('.rowi');if(mv.hasAttribute('data-up')&&row.previousElementSibling&&!row.previousElementSibling.classList.contains('rowi--h'))row.parentNode.insertBefore(row,row.previousElementSibling);else if(mv.hasAttribute('data-down')&&row.nextElementSibling)row.parentNode.insertBefore(row.nextElementSibling,row);row.closest('form').dispatchEvent(new Event('input'));return}
 var d=e.target.closest('[data-del]');if(d){var rows2=d.closest('[data-rows]');var all=rows2.querySelectorAll('.rowi:not(.rowi--h)');if(all.length>1)d.closest('.rowi').remove();else d.closest('.rowi').querySelectorAll('input,textarea').forEach(function(i){i.value=''});rows2.closest('form').dispatchEvent(new Event('input'));}
});
// превью загрузки и перетаскивание
document.querySelectorAll('.drop').forEach(function(z){var inp=z.querySelector('input[type=file]');var txt=z.querySelector('span');
 ['dragenter','dragover'].forEach(function(ev){z.addEventListener(ev,function(e){e.preventDefault();z.classList.add('hover')})});
 ['dragleave','drop'].forEach(function(ev){z.addEventListener(ev,function(){z.classList.remove('hover')})});
 z.addEventListener('drop',function(e){e.preventDefault();if(e.dataTransfer.files.length){inp.files=e.dataTransfer.files;inp.dispatchEvent(new Event('change',{bubbles:true}))}});
 inp.addEventListener('change',function(){if(!inp.files.length)return;var f=inp.files[0];z.classList.add('has');txt.innerHTML='<b>'+f.name+'</b> выбран. Нажмите «Сохранить».';
  var box=z.closest('[data-preview]');if(box&&f.type.indexOf('image')===0){var img=box.querySelector('img');if(!img){img=document.createElement('img');box.insertBefore(img,box.firstChild)}img.src=URL.createObjectURL(f)}
  var form=z.closest('form');if(form)form.dispatchEvent(new Event('input'))});
});
// документ: подсветка отмеченных страниц и поиск
document.querySelectorAll('.place input[type=checkbox]').forEach(function(c){c.addEventListener('change',function(){c.closest('.place').classList.toggle('on',c.checked)})});
document.querySelectorAll('.place input[name^=grp_]').forEach(function(g){g.addEventListener('input',function(){var c=g.closest('.place').querySelector('input[type=checkbox]');if(g.value&&!c.checked){c.checked=true;g.closest('.place').classList.add('on')}})});
var ps=document.querySelector('.pgsearch');if(ps)ps.addEventListener('input',function(){var v=ps.value.toLowerCase();document.querySelectorAll('.place').forEach(function(p){p.style.display=p.textContent.toLowerCase().indexOf(v)>-1||p.classList.contains('on')?'':'none'})});
// текст новости: подзаголовок и фото
var ta=document.querySelector('.bodyta');
function ins(s){if(!ta)return;var p=ta.selectionStart,v=ta.value;var pre=v.slice(0,p),post=v.slice(p);var sep1=pre&&!/\n\n$/.test(pre)?(/\n$/.test(pre)?'\n':'\n\n'):'';ta.value=pre+sep1+s+'\n\n'+post.replace(/^\n+/,'');ta.focus();ta.dispatchEvent(new Event('input',{bubbles:true}))}
var hb=document.querySelector('.js-h');if(hb)hb.onclick=function(){ins('## Подзаголовок')};
var ib=document.querySelector('.js-img');if(ib)ib.onchange=function(){var f=ib.files[0];if(!f)return;var fd=new FormData();fd.append('file',f);fd.append('csrf',window.CSRF);
 ib.parentNode.firstChild.textContent='Загружаю…';fetch('/admin/upload-image',{method:'POST',body:fd}).then(function(r){return r.json()}).then(function(j){ib.parentNode.firstChild.textContent='Вставить фото';if(j.url)ins(j.url)})};
})();
// поля педсостава видны только при метке «Педагогический состав»
(function(){var box=document.querySelector('.js-teacher');var cb=document.querySelector('input[name=tags][value=teacher]');if(box&&cb)cb.addEventListener('change',function(){box.hidden=!cb.checked})})();

// карточка человека: замена на единственном месте, корпус обязателен для служб
(function(){var H=window.HOLDERS;if(!H)return;var form=document.querySelector('form.js-dirty');if(!form)return;
 var svc=['psiholog','logoped','social','med','mediaciya'];
 function cb(v){return form.querySelector('input[name=tags][value="'+v+'"]')}
 var dir=cb('director'),lead=cb('lead'),bld=form.querySelector('select[name=building]');
 function sync(){var anySvc=svc.some(function(s){var c=cb(s);return c&&c.checked});
  if(lead){lead.disabled=!anySvc;if(!anySvc)lead.checked=false;lead.closest('label').style.opacity=anySvc?1:.45}
  if(bld){bld.required=anySvc}}
 form.addEventListener('change',function(e){var t=e.target;
  if(t===dir&&dir.checked&&H.director&&!confirm('Директором сейчас отмечен(а) '+H.director+'. Заменить? У прежнего отметка снимется после сохранения.')){dir.checked=false}
  if(t===lead&&lead.checked){svc.forEach(function(s){var c=cb(s);if(c&&c.checked&&H['lead_'+s]&&!confirm('Руководителем этой службы сейчас отмечен(а) '+H['lead_'+s]+'. Заменить?')){lead.checked=false}})}
  sync()});
 sync()})();
