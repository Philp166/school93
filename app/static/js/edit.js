(function(){
// режим правки внутри страницы: панель у блока, «+» между блоками, тексты правятся прямо здесь
document.documentElement.classList.add('s93-edit');
function host(){return window.parent&&window.parent.S93Edit}
var DATA={people:'Выбрать людей',docs:'Выбрать документы',clubs:'Выбрать кружки',card_people:'Выбрать людей'};
var FIXED={sveden_data:1,newspage:1,status1:1,menu:1,buildings:1,requisites:1};
function el(tag,cls,html){var e=document.createElement(tag);if(cls)e.className=cls;if(html!=null)e.innerHTML=html;return e}
function btn(text,act,extra){var b=el('button','',text);b.type='button';b.dataset.act=act;if(extra)for(var k in extra)b.dataset[k]=extra[k];return b}
function toolbar(w){
 var t=w.dataset.t,path=w.dataset.path,names=(host()&&host().names)||{},tb=el('div','eb-tb');
 tb.appendChild(el('span','eb-tb__l',names[t]||(path==='hero'?'Шапка страницы':'Блок')));
 if(DATA[t])tb.appendChild(btn(DATA[t],'open'));
 else if(t==='status1')tb.appendChild(btn('Изменить статус','status'));
 else if(w.dataset.lock)tb.appendChild(btn('Изменить в разделе «'+w.dataset.lock+'»','go'));
 else if(path==='hero')tb.appendChild(btn('Подзаголовок и кнопки','open'));
 else tb.appendChild(btn('Настроить','open'));
 if(path.indexOf('b:')===0){tb.appendChild(btn('↑','up'));tb.appendChild(btn('↓','down'));if(!FIXED[t])tb.appendChild(btn('Удалить','del',{danger:1}))}
 if(t==='status1'){var pop=el('div','eb-pop','<button type="button" data-st="soon"><b>Скоро</b><span>Приём откроется в указанную дату</span></button><button type="button" data-st="open"><b>Идёт приём</b><span>Кнопка «Подать заявление» на всех страницах</span></button><button type="button" data-st="closed"><b>Закрыт</b><span>Ссылка на свободные места</span></button>');tb.appendChild(pop)}
 if(w.dataset.lock&&!DATA[t]){w.appendChild(el('span','eb-src','Данные из раздела «'+w.dataset.lock+'»'))}
 w.appendChild(tb)}
function plus(attrs){var b=el('button','eb-plus','<span>+</span>');b.type='button';b.title='Добавить блок';for(var k in attrs)if(attrs[k]!=null)b.dataset[k]=attrs[k];return b}
function setup(){
 var first=true;
 document.querySelectorAll('[data-eb]').forEach(function(w){var anc=w.parentElement&&w.parentElement.closest('[data-eb]');
  if(anc&&anc.dataset.t!=='tabs'&&anc.dataset.path!=='hero')return;
  toolbar(w);
  if(w.dataset.path.indexOf('b:')!==0)return;
  var id=w.dataset.path.slice(2);
  if(w.tagName==='SECTION'){var wr=w.querySelector('.wrap');if(wr)wr.appendChild(plus({after:id}))}else w.parentNode.insertBefore(plus({after:id}),w.nextSibling);
  if(!anc&&first){first=false;w.parentNode.insertBefore(plus({first:'1'}),w)}});
 document.querySelectorAll('[data-insert-parent]').forEach(function(em){em.appendChild(plus({parent:em.dataset.insertParent,tab:em.dataset.insertTab}))});
 // тексты: правка прямо на странице
 document.querySelectorAll('[data-f]').forEach(function(f){
  try{f.contentEditable='plaintext-only'}catch(e){f.contentEditable='true'}
  if(f.contentEditable!=='plaintext-only')f.contentEditable='true';
  f.spellcheck=true;
  f.addEventListener('focus',function(){f._orig=f.innerText.trim();var w=f.closest('[data-eb]');if(w)w.classList.add('eb-typing')});
  f.addEventListener('keydown',function(e){if(e.key==='Enter'&&!f.dataset.multi){e.preventDefault();f.blur()}if(e.key==='Escape'){f.innerText=f._orig;f.blur()}});
  f.addEventListener('blur',function(){var w=f.closest('[data-eb]');if(w)w.classList.remove('eb-typing');var v=f.innerText.replace(/\u00a0/g,' ').trim();
   if(v===f._orig)return;if(!v&&!f.dataset.ph){f.innerText=f._orig;return}
   if(host())host().saveField(w.dataset.path,f.dataset.f,v).then(function(ok){if(!ok)f.innerText=f._orig})});
 });
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);else setup();
document.addEventListener('click',function(e){var t=e.target;
 var p=t.closest('.eb-plus');if(p){e.preventDefault();e.stopPropagation();if(host())host().insert({after:p.dataset.after||null,parent:p.dataset.parent||null,tab:p.dataset.tab||null});return}
 var st=t.closest('[data-st]');if(st){e.preventDefault();st.closest('.eb-pop').classList.remove('on');if(host())host().status(st.dataset.st);return}
 var a=t.closest('.eb-tb [data-act]');if(a){e.preventDefault();e.stopPropagation();var w=a.closest('[data-eb]'),path=w.dataset.path,act=a.dataset.act,H=host();if(!H)return;
  if(act==='open')H.open(path);if(act==='up'||act==='down')H.move(path.slice(2),act);if(act==='del')H.del(path.slice(2));if(act==='go')H.go(w.dataset.href);
  if(act==='status')w.querySelector('.eb-pop').classList.toggle('on');return}
 if(t.closest('[data-f]')){var lk=t.closest('a');if(lk)e.preventDefault();return}
 if(t.closest('.js-seg button,.fq__q,button.chip,.js-a11y,.js-burger,[data-lb]'))return;
 var lk2=t.closest('a');if(lk2)e.preventDefault();
 var w2=t.closest('[data-eb]');if(w2&&(DATA[w2.dataset.t])){e.preventDefault();if(host())host().open(w2.dataset.path)}
},true);
document.addEventListener('submit',function(e){e.preventDefault()},true);
})();
