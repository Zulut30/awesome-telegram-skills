'use strict';
const catalog = JSON.parse(document.getElementById('recipe-data').textContent);
const byId = id => document.getElementById(id);
const labels = {sdk:'SDK',mock:'Mock',browser:'Браузер',not_run:'Справка',live:'Telegram'};
const maturityLabels = {stable:'Стабильный',experimental:'Экспериментальный',reference:'Справочный'};
const categories = {keyboards:'КЛАВИАТУРЫ И ВВОД',scenarios:'СЦЕНАРИИ БОТОВ','bot-api':'BOT API','mini-app':'MINI APPS'};
const norm = value => value.normalize('NFKC').toLocaleLowerCase().replaceAll('ё','е');
let selected;
byId('version').textContent = catalog.library_version;
function preview(data) {
  const root=byId('preview');root.replaceChildren();byId('preview-status').textContent='';
  if(!data)return;
  const caption=document.createElement('p');caption.className='preview-caption';caption.textContent='ВЕБ-ПРЕВЬЮ · НЕ НАСТОЯЩИЙ TELEGRAM';root.append(caption);
  const rows=data.inline_keyboard??data.keyboard;
  if(rows)for(const row of rows){
    const holder=document.createElement('div');holder.className='keyboard-row';
    for(const value of row){
      const button=document.createElement('button');button.type='button';button.textContent=value.text;
      if(['primary','success','danger'].includes(value.style))button.classList.add(value.style);
      button.disabled=value.disabled!==undefined;
      button.addEventListener('click',()=>{byId('preview-status').textContent='Веб-превью: выбрана кнопка «'+value.text+'». Запрос не отправлен.';});holder.append(button);
    }root.append(holder);
  }
  if(data.input_field_placeholder||data.force_reply){const input=document.createElement('input');input.type='text';input.placeholder=data.input_field_placeholder??'Ответ';input.setAttribute('aria-label','Пример поля ввода');root.append(input);}
  if(data.remove_keyboard){const note=document.createElement('p');note.className='preview-note';note.textContent='Reply-клавиатура скрывается; поле ввода остается обычным.';root.append(note);}
}
function choose(recipe){
  selected=recipe;byId('detail').hidden=false;
  byId('detail-category').textContent=categories[recipe.category]+' · '+maturityLabels[recipe.maturity]+' · '+labels[recipe.verification]+' · '+recipe.language;
  byId('detail-title').textContent=recipe.title;byId('detail-summary').textContent=recipe.summary;byId('detail-scope').textContent=recipe.scope;
  byId('code').textContent=recipe.code;byId('copy-status').textContent='';preview(recipe.preview);
  byId('sources').replaceChildren();
  recipe.sources.forEach((source,index)=>{const url=new URL(source);if(url.protocol!=='https:'||url.username)return;
    const link=document.createElement('a');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';link.textContent='Документация '+(index+1);byId('sources').append(link);});
  for(const button of byId('recipes').querySelectorAll('button'))button.setAttribute('aria-pressed',String(button.dataset.id===recipe.id));
}
function render(){
  const terms=norm(byId('search').value).split(/\s+/).filter(Boolean),category=byId('category').value,verification=byId('verification').value,maturity=byId('maturity').value;
  const items=catalog.recipes.filter(recipe=>{
    const text=norm([recipe.id,recipe.title,recipe.summary,recipe.language,...recipe.keywords].join(' '));
    return (!category||recipe.category===category)&&(!verification||recipe.verification===verification)&&(!maturity||recipe.maturity===maturity)&&terms.every(term=>text.includes(term));
  });
  byId('count').textContent=items.length+' из '+catalog.recipes.length;byId('recipes').replaceChildren();
  for(const recipe of items){
    const button=document.createElement('button');button.type='button';button.className='recipe-card';button.dataset.id=recipe.id;button.setAttribute('aria-label',recipe.title);button.setAttribute('aria-controls','detail');button.setAttribute('aria-pressed','false');
    const title=document.createElement('strong');title.textContent=recipe.title;const meta=document.createElement('span');meta.className='meta';
    const badge=document.createElement('span');badge.className='badge';badge.textContent=labels[recipe.verification];const language=document.createElement('span');language.textContent=recipe.language;const maturity=document.createElement('span');maturity.textContent=maturityLabels[recipe.maturity];meta.append(badge,language,maturity);
    const summary=document.createElement('p');summary.textContent=recipe.summary;button.append(meta,title,summary);button.addEventListener('click',()=>{choose(recipe);if(matchMedia('(max-width:720px)').matches)byId('detail').scrollIntoView({block:'start'});});byId('recipes').append(button);
  }
  if(items.length){choose(items.find(recipe=>recipe.id===selected?.id)??items[0]);}
  else{selected=undefined;byId('detail').hidden=true;const empty=document.createElement('p');empty.className='empty';empty.textContent='Рецепты не найдены. Измените запрос или сбросьте фильтры.';byId('recipes').append(empty);}
}
for(const id of ['search','category','verification','maturity'])byId(id).addEventListener(id==='search'?'input':'change',render);
byId('reset').addEventListener('click',()=>{for(const id of ['search','category','verification','maturity'])byId(id).value='';render();byId('search').focus();});
byId('copy').addEventListener('click',async()=>{
  if(!selected)return;const recipe=selected;
  try{if(!navigator.clipboard)throw Error('unavailable');await navigator.clipboard.writeText(recipe.code);if(selected===recipe)byId('copy-status').textContent='Код скопирован.';}
  catch{if(selected!==recipe)return;const selection=window.getSelection(),range=document.createRange();range.selectNodeContents(byId('code'));selection?.removeAllRanges();selection?.addRange(range);byId('copy-status').textContent='Буфер обмена недоступен. Код выделен; скопируйте вручную.';}
});
render();
