(function(){
var root=document.documentElement,body=document.body;
function closeMenu(){body.classList.remove('menu-open');document.querySelectorAll('.js-burger').forEach(function(b){b.setAttribute('aria-expanded','false')});var m=document.getElementById('menu');if(m)m.setAttribute('aria-hidden','true')}
document.addEventListener('click',function(e){
 var b=e.target.closest('.js-burger');
 if(b){var o=!body.classList.contains('menu-open');body.classList.toggle('menu-open',o);document.querySelectorAll('.js-burger').forEach(function(x){x.setAttribute('aria-expanded',o)});document.getElementById('menu').setAttribute('aria-hidden',!o);return}
 var a11=e.target.closest('.js-a11y,.js-a11y-link');if(a11){e.preventDefault();document.getElementById('a11y').classList.toggle('on');return}
 if(!e.target.closest('#a11y'))document.getElementById('a11y').classList.remove('on');
 var q=e.target.closest('.fq__q');if(q){var f=q.parentNode;var o2=!f.classList.contains('open');f.classList.toggle('open',o2);q.setAttribute('aria-expanded',o2);return}
 var sb=e.target.closest('.js-seg button');
 if(sb){var seg=sb.parentNode;seg.querySelectorAll('button').forEach(function(x){x.classList.toggle('on',x===sb)});
  seg.parentNode.querySelectorAll(':scope > [data-pane]').forEach(function(p){p.classList.toggle('on',p.dataset.pane===sb.dataset.p)});return}
 var ch=e.target.closest('button.chip');
 if(ch){var g=ch.parentNode;g.querySelectorAll('.chip').forEach(function(x){x.classList.toggle('on',x===ch)});
  if(g.classList.contains('js-filter')){var f2=ch.dataset.f;g.parentNode.querySelectorAll('.fgroup').forEach(function(fg){fg.style.display=(f2==='all'||fg.dataset.g===f2)?'':'none'})}
  if(g.classList.contains('js-cf')){var d=ch.dataset.f;var grid=g.nextElementSibling;grid.querySelectorAll('.cf').forEach(function(c){c.classList.toggle('hide',!!d&&c.dataset.d!==d)})}
  return}
 var ml=e.target.closest('.menu a');if(ml)closeMenu();
});
document.addEventListener('keydown',function(e){if(e.key==='Escape'){closeMenu();document.getElementById('a11y').classList.remove('on')}});
var bar=document.getElementById('bar');window.addEventListener('scroll',function(){bar.classList.toggle('show',window.scrollY>420)},{passive:true});
function setA(g,v){document.querySelectorAll('#a11y [data-g="'+g+'"] button').forEach(function(b){b.classList.toggle('on',b.dataset.v===v)});
 var opts={fs:['fs1','fs2'],hc:['hc'],ff:['ff-serif'],ls:['ls1'],img:['noimg']}[g]||[];
 opts.forEach(function(c){root.classList.remove(c)});if(v)root.classList.add(v);
 try{localStorage.setItem('s93-'+g,v)}catch(e){}}
document.querySelectorAll('#a11y .row button').forEach(function(b){b.addEventListener('click',function(){setA(b.parentNode.dataset.g,b.dataset.v)})});
// главный документ «машет», когда попадает на экран (каждый раз при появлении)
if('IntersectionObserver' in window){var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.remove('nudge');void e.target.offsetWidth;e.target.classList.add('nudge')}})},{threshold:.8});
 document.querySelectorAll('.doc--key').forEach(function(d){io.observe(d)})}
try{['fs','hc','ff','ls','img'].forEach(function(g){var v=localStorage.getItem('s93-'+g);if(v)setA(g,v)})}catch(e){}
})();

// просмотр фото новости: клик, стрелки, свайп
(function(){var lb=document.getElementById('lbx');if(!lb)return;var L=JSON.parse(lb.dataset.photos||'[]'),i=0,im=lb.querySelector('img'),ct=lb.querySelector('.lbx__c');
function show(n){i=(n+L.length)%L.length;im.src=L[i];ct.textContent=L.length>1?(i+1)+' из '+L.length:'';lb.hidden=false;document.body.style.overflow='hidden'}
function close(){lb.hidden=true;document.body.style.overflow=''}
document.querySelectorAll('[data-lb]').forEach(function(b){b.addEventListener('click',function(){show(+b.dataset.lb)})});
lb.querySelector('.lbx__p').onclick=function(){show(i-1)};lb.querySelector('.lbx__n').onclick=function(){show(i+1)};lb.querySelector('.lbx__x').onclick=close;
lb.addEventListener('click',function(e){if(e.target===lb)close()});
document.addEventListener('keydown',function(e){if(lb.hidden)return;if(e.key==='Escape')close();if(e.key==='ArrowLeft')show(i-1);if(e.key==='ArrowRight')show(i+1)});
var x0=null;lb.addEventListener('touchstart',function(e){x0=e.touches[0].clientX},{passive:true});lb.addEventListener('touchend',function(e){if(x0===null)return;var d=e.changedTouches[0].clientX-x0;if(Math.abs(d)>40)show(i+(d<0?1:-1));x0=null})})();
