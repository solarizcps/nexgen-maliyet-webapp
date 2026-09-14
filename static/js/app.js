const PAGES=['calc','materials','expenses','formulas'];
const API_BASE='';
let csrfToken='';
let weeklyReview={due:false,weeklyReviewMode:false,materialsSavedForReview:false};
function categoryOf(code){return['TIO2','PR122','BLK550','PBLUE154','BROWN600','BROWN660','PYELLOW13','YELLOW313'].includes(String(code).toUpperCase())?'Boya':['EVA-18','EVA-22','EVA-28','RECYCLED','POE-565','TPE-8201','PROFOR'].includes(String(code).toUpperCase())?'Ana Malzeme':'Katkı'}
function groupClass(category){return category==='Boya'?'group-color':category==='Ana Malzeme'?'group-main':'group-additive'}
const $=id=>document.getElementById(id),money=(n,d=3)=>Number.isFinite(n)?'$'+n.toFixed(d):'-',moneyOrDash=(n,d=3)=>Number.isFinite(n)?money(n,d):'—',fmt=(n,d=3)=>Number.isFinite(n)?n.toLocaleString('tr-TR',{minimumFractionDigits:d,maximumFractionDigits:d}):'-',esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function uid(p){return(p||'id')+'-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,8)}
function deepClone(o){return JSON.parse(JSON.stringify(o))}
function parseNum(v){if(v===null||v===undefined)return NaN;const s=String(v).trim().replace(/\s/g,'').replace(',','.');if(s===''||s==='-')return NaN;return Number(s)}
function formatSavedAt(iso){if(!iso)return'';const d=new Date(iso);return'Kaydedildi · '+d.toLocaleDateString('tr-TR')+' '+d.toLocaleTimeString('tr-TR',{hour:'2-digit',minute:'2-digit'})}
function normalizeMaterial(m){m.code=String(m.code??'').trim();m.name=String(m.name??'').trim();m.category=m.category||categoryOf(m.code);m.cash=parseNum(m.cash);if(!Number.isFinite(m.cash))m.cash=NaN;return m}
function syncLineCode(line,materials){const m=materials.find(x=>x.id===line.materialId);if(m){line.code=m.code;return m}return null}
function materialById(materials,id){return materials.find(m=>m.id===id)||null}
function migrateData(data){
  data.meta=data.meta||{};data.savedAt=data.savedAt||{};data.versions=data.versions||{};
  data.materials=data.materials||[];data.formulas=data.formulas||[];data.expenses=data.expenses||[];
  (data.materials||[]).forEach(m=>{if(!m.id)m.id=uid('mat');normalizeMaterial(m)});
  (data.formulas||[]).forEach(f=>{f.monthlyRate=Number.isFinite(+f.monthlyRate)?+f.monthlyRate:0;(f.lines||[]).forEach(l=>{
    if(l.materialId&&materialById(data.materials,l.materialId))syncLineCode(l,data.materials);
    else if(l.code){const code=String(l.code).trim();const m=data.materials.find(x=>x.code===code);if(m){l.materialId=m.id;l.code=m.code}}
    l.kg=parseNum(l.kg);if(!Number.isFinite(l.kg))l.kg=0;
  })});
  return data;
}
function formulaTotalKg(formula){return(formula.lines||[]).reduce((s,l)=>{const kg=parseNum(l.kg);return s+(Number.isFinite(kg)&&kg>0?kg:0)},0)}
function formulaLabel(f){let s=esc(f.company)+' — '+esc(f.name);if(f.colorName)s+=' · '+esc(f.colorName);return s}
function formatTrDecimal(n,d=3){return Number.isFinite(n)?n.toLocaleString('tr-TR',{minimumFractionDigits:d,maximumFractionDigits:d}):''}
function buildOverheadDetail(source){
  let allocated=0;(source.expenses||[]).forEach(e=>{allocated+=(+e.amount||0)*(+e.rate||0)/100});
  const prod=Math.max(+source.productionKg||0,1);const usd=Math.max(+source.usdTry||0,1);
  const tlKg=allocated/prod;const usdKg=tlKg/usd;
  return{allocated,prod,usd,tlKg,usdKg};
}
function renderOverheadDetail(source){
  const el=$('overheadDetail');if(!el)return;
  const d=buildOverheadDetail(source);
  el.innerHTML=`<dl>
    <dt>Üretime ayrılan aylık gider</dt><dd>₺${Math.round(d.allocated).toLocaleString('tr-TR')}</dd>
    <dt>Aylık üretim</dt><dd>${formatTrDecimal(d.prod,0)} kg</dd>
    <dt>Gider (TL/kg)</dt><dd>₺${formatTrDecimal(d.tlKg,4)}/kg</dd>
    <dt>USD/TL kuru</dt><dd>${formatTrDecimal(d.usd,2)}</dd>
    <dt>Sonuç (USD/kg)</dt><dd>$${formatTrDecimal(d.usdKg,4)}/kg</dd>
  </dl><div class="overhead-note">Genel gider her satış senaryosuna bir kez eklenir.</div>`;
}
function renderFormulaMeta(f){
  const meta=$('calcFormulaMeta');if(!meta)return;
  const parts=[];
  if(f.colorName)parts.push('Renk: '+esc(f.colorName));
  if(f.colorCode)parts.push('Kod: '+esc(f.colorCode));
  if(f.formulaDate)parts.push('Tarih: '+esc(String(f.formulaDate).split('T')[0].split('-').reverse().join('.')));
  if(Number.isFinite(parseNum(f.baseExpansionMeasure)))parts.push('Taban patlatma ölçüsü: '+formatTrDecimal(parseNum(f.baseExpansionMeasure),2));
  if(parts.length){meta.hidden=false;meta.innerHTML=parts.join(' · ')}else{meta.hidden=true;meta.textContent=''}
}
function missingPriceCodes(formula,materials){const codes=new Set();(formula.lines||[]).forEach(l=>{const kg=parseNum(l.kg);if(!(kg>0))return;const m=lineMaterial(l,materials);if(m&&(!Number.isFinite(parseNum(m.cash))||parseNum(m.cash)<=0))codes.add(m.code)});return[...codes]}
function formulaById(formulas,id){return(formulas||[]).find(f=>f.id===id)}
function formulaMissingCount(formula,source){if(!formula)return 0;const c=calculate(source,formula);return c.missing_price_count||missingPriceCodes(formula,source.materials).length}
function activeFormulaIssues(source){
  const f=formulaById(source.formulas,activeId)||source.formulas[0];
  if(!f)return{formula:null,valid:true,missingCodes:[],errors:[]};
  const c=calculate(source,f);
  return{formula:f,valid:!!c.valid,missingCodes:(c.missing_materials||missingPriceCodes(f,source.materials)).slice().sort(),errors:c.errors||[]};
}
function validateActiveFormula(data){
  const f=formulaById(data.formulas,activeId)||data.formulas[0];
  if(!f)return['Aktif formül bulunamadı'];
  const errors=[];
  if(!String(f.company||'').trim())errors.push('Firma adı boş');
  if(!String(f.name||'').trim())errors.push('Formül adı boş');
  (f.lines||[]).forEach((l,li)=>{
    const kg=parseNum(l.kg);
    if(Number.isFinite(kg)&&kg>0)errors.push(...lineIssues(l,data.materials,li));
    if(!l.materialId&&Number.isFinite(kg)&&kg>0)errors.push('Satır '+(li+1)+': malzeme seçilmedi');
  });
  return errors;
}
function hasUnsavedPreview(){return dirty.calc||dirty.formulas}
let activeWarnExpanded=false;
function buildActiveMissingHtml(codes){
  if(!codes.length)return'';
  const limit=activeWarnExpanded?codes.length:Math.min(3,codes.length);
  let html='<div class="warn-compact-title">Eksik fiyat ('+codes.length+')</div><ul class="warn-code-list">';
  codes.slice(0,limit).forEach(c=>{html+='<li>'+esc(c)+'</li>'});
  html+='</ul>';
  if(codes.length>3&&!activeWarnExpanded)html+='<button type="button" class="btn-link-warn" data-warn-expand="1">Tümünü göster</button>';
  else if(codes.length>3)html+='<button type="button" class="btn-link-warn" data-warn-collapse="1">Daralt</button>';
  html+='<div class="calc-error-actions"><button type="button" class="btn-fix-prices" id="btnFixPrices">Eksik fiyatları tamamla</button></div>';
  return html;
}
function bindActiveWarningActions(el){
  if(!el)return;
  const btn=el.querySelector('#btnFixPrices');if(btn)btn.onclick=goFixMissingPrices;
  el.querySelector('[data-warn-expand]')?.addEventListener('click',()=>{activeWarnExpanded=true;render()});
  el.querySelector('[data-warn-collapse]')?.addEventListener('click',()=>{activeWarnExpanded=false;render()});
}
function renderActiveFormulaBanner(el){
  if(!el)return;
  const issues=activeFormulaIssues(committed);
  const parts=[];
  if(hasUnsavedPreview())parts.push('<div class="preview-notice-inline">Önizleme — henüz kaydedilmedi</div>');
  if(issues.missingCodes.length)parts.push(buildActiveMissingHtml(issues.missingCodes));
  if(!parts.length){el.hidden=true;el.innerHTML='';el.className=el.className.replace(/\s*has-missing/g,'').trim();return}
  el.hidden=false;
  if(!el.className.includes('calc-error'))el.className=(el.className+' calc-error').trim();
  el.classList.toggle('has-missing',issues.missingCodes.length>0);
  el.innerHTML=parts.join('');
  bindActiveWarningActions(el);
}
function lineMaterial(line,materials){return line.materialId?materialById(materials,line.materialId):null}
let committed={materials:[],expenses:[],formulas:[],productionKg:420000,usdTry:42.45,savedAt:{},versions:{},meta:{}};
let draft=deepClone(committed);
let versions={materials:1,expenses:1,formulas:1,calc:1};
let activeId='';
let current='calc';
const dirty={calc:false,materials:false,expenses:false,formulas:false};
const saveErrors={calc:false,materials:false,expenses:false,formulas:false};
let pendingNav=null;
let loadError=null;
let loadState='loading';
let bootstrapSeq=0;
let highlightMaterialCodes=new Set();
let pendingReturnToCalc=false;
let calcFetchSeq=0;
let calcLoading=false;
let calcApiByFormula={};
function activeDraft(){return draft.formulas.find(x=>x.id===activeId)||draft.formulas[0]}
function activeCommitted(){return committed.formulas.find(x=>x.id===activeId)||committed.formulas[0]}
function overhead(source){return source.expenses.reduce((s,x)=>s+x.amount*x.rate/100,0)/Math.max(source.productionKg,1)/Math.max(source.usdTry,1)}
function lineIssues(line,materials,rowIndex){
  const issues=[];const kg=parseNum(line.kg);const m=lineMaterial(line,materials);
  if(!line.materialId||!m)issues.push('Satır '+(rowIndex+1)+': malzeme bağlantısı yok');
  else{
    if(!m.code)issues.push('Satır '+(rowIndex+1)+' ('+m.name+'): malzeme kodu boş');
    if(!Number.isFinite(parseNum(m.cash))||parseNum(m.cash)<=0)issues.push('Satır '+(rowIndex+1)+' — '+m.code+' ('+m.name+'): peşin fiyat girilmemiş veya geçersiz');
  }
  if(Number.isFinite(kg)&&kg<0)issues.push('Satır '+(rowIndex+1)+': kullanım miktarı negatif olamaz');
  if(Number.isFinite(kg)&&kg>0&&(!line.materialId||!m))issues.push('Satır '+(rowIndex+1)+': geçerli kg var fakat malzeme seçilmedi');
  if(line.materialId&&!Number.isFinite(kg))issues.push('Satır '+(rowIndex+1)+': kullanım miktarı sayı değil');
  return issues;
}
function normalizeLineKg(line){line.kg=parseNum(line.kg);if(!Number.isFinite(line.kg))line.kg=0;return line.kg}
function calculate(source,formula){
  const monthlyRate=+formula.monthlyRate||0,errors=[],rows=[];
  (formula.lines||[]).forEach((l,i)=>{
    const kg=parseNum(l.kg);const line={...l,kg:Number.isFinite(kg)?kg:NaN};const skip=Number.isFinite(kg)&&kg===0;const m=lineMaterial(line,source.materials);
    const rowIssues=lineIssues(line,source.materials,i);if(!skip&&rowIssues.length)errors.push(...rowIssues);
    if(skip)return;
    const cash=Number.isFinite(parseNum(m?.cash))?parseNum(m.cash):NaN;const applied=Number.isFinite(cash)?cash*(1+monthlyRate/100*(+formula.months||0)):NaN;
    rows.push({...line,code:m?.code||line.code||'',name:m?.name||'Bulunamadı',category:m?.category||'Katkı',cash,monthlyRate,applied,total:Number.isFinite(applied)&&Number.isFinite(kg)?applied*kg:NaN,cashTotal:Number.isFinite(cash)&&Number.isFinite(kg)?cash*kg:NaN,kg:Number.isFinite(kg)?kg:NaN,invalid:!!rowIssues.length||!m||!Number.isFinite(cash)||cash<=0});
  });
  const validRows=rows.filter(r=>!r.invalid&&Number.isFinite(r.kg)&&r.kg>0);
  const calcKg=validRows.reduce((s,x)=>s+x.kg,0);
  if(!validRows.length&&rows.length)errors.push('Hesaplanabilir reçete satırı yok');
  const raw=validRows.reduce((s,x)=>s+(Number.isFinite(x.total)?x.total:0),0);
  const cashRaw=validRows.reduce((s,x)=>s+(Number.isFinite(x.cashTotal)?x.cashTotal:0),0);
  const oh=overhead(source);
  const cashRawKg=calcKg>0?cashRaw/calcKg:NaN,rawKg=calcKg>0?raw/calcKg:NaN;
  const cashCost=Number.isFinite(cashRawKg)?cashRawKg+oh:NaN;
  const cashProfit=Number.isFinite(cashCost)?cashCost*formula.profit/100:NaN;
  const cashSale=Number.isFinite(cashCost)&&Number.isFinite(cashProfit)?cashCost+cashProfit:NaN;
  const cost=Number.isFinite(rawKg)?rawKg+oh:NaN;
  const profit=Number.isFinite(cost)?cost*formula.profit/100:NaN;
  const sale=Number.isFinite(cost)&&Number.isFinite(profit)?cost+profit:NaN;
  const missingMaterials=[...new Set(rows.filter(r=>r.invalid&&Number.isFinite(r.kg)&&r.kg>0&&r.code).map(r=>r.code))].sort();
  const valid=errors.length===0&&validRows.length>0&&rows.filter(r=>!r.invalid).length===rows.length&&Number.isFinite(cashSale);
  const nullIf=v=>valid&&Number.isFinite(v)?v:null;
  let cashCalculation=null,termCalculation=null;
  if(valid){
    cashCalculation={rawKg:cashRawKg,overhead:oh,cost:cashCost,profit:cashProfit,sale:cashSale};
    const months=+formula.months||0,monthlyRate=+formula.monthlyRate||0;
    if(months>0){
      if(monthlyRate>0)termCalculation={rawKg,overhead:oh,cost,profit,sale,months,monthlyRate,sameAsCash:false};
      else termCalculation={rawKg:cashRawKg,overhead:oh,cost:cashCost,profit:cashProfit,sale:cashSale,months,monthlyRate,sameAsCash:true};
    }
  }
  return{
    rows,allRows:rows,kg:calcKg,recipeKg:formulaTotalKg(formula),recipe_total_kg:formulaTotalKg(formula),
    cashRawKg:nullIf(cashRawKg),rawKg:nullIf(rawKg),cashCost:nullIf(cashCost),cashProfit:nullIf(cashProfit),cashSale:nullIf(cashSale),
    cost:nullIf(cost),profit:nullIf(profit),sale:nullIf(sale),errors,ok:valid,valid,
    missing_price_count:missingMaterials.length,missing_materials:missingMaterials,
    cash_calculation:cashCalculation,term_calculation:termCalculation,overhead:valid?oh:null,formulaId:formula.id
  };
}
function validateMaterials(data){const errors=[];const seen=new Map();data.materials.forEach((m,i)=>{normalizeMaterial(m);if(!m.code)errors.push('Satır '+(i+1)+': malzeme kodu boş olamaz');else if(seen.has(m.code))errors.push('Satır '+(i+1)+': "'+m.code+'" kodu yineleniyor (satır '+(seen.get(m.code)+1)+')');else seen.set(m.code,i);if(!m.name)errors.push('Satır '+(i+1)+' ('+(m.code||'?')+'): malzeme adı boş');if(!Number.isFinite(m.cash)||m.cash<0)errors.push('Satır '+(i+1)+' ('+(m.code||'?')+'): peşin fiyat geçersiz')});return errors;}
function validateExpenses(data){const errors=[];if(!Number.isFinite(+data.productionKg)||+data.productionKg<=0)errors.push('Aylık üretim sıfırdan büyük olmalı');if(!Number.isFinite(+data.usdTry)||+data.usdTry<=0)errors.push('USD/TL kuru sıfırdan büyük olmalı');data.expenses.forEach((x,i)=>{if(!String(x.name||'').trim())errors.push('Gider satır '+(i+1)+': ad boş');if(!Number.isFinite(+x.amount)||+x.amount<0)errors.push('Gider satır '+(i+1)+': tutar geçersiz');if(!Number.isFinite(+x.rate)||+x.rate<0)errors.push('Gider satır '+(i+1)+': oran geçersiz')});return errors;}
function validateFormulas(data){const errors=[];const ids=new Set();data.formulas.forEach((f,fi)=>{if(!String(f.company||'').trim())errors.push('Formül '+(fi+1)+': firma adı boş');if(!String(f.name||'').trim())errors.push((f.company||'Formül')+': formül adı boş');if(ids.has(f.id))errors.push('Yinelenen formül kimliği: '+f.id);ids.add(f.id);(f.lines||[]).forEach((l,li)=>{const kg=parseNum(l.kg);if(Number.isFinite(kg)&&kg>0)errors.push(...lineIssues(l,data.materials,li));if(!l.materialId&&Number.isFinite(kg)&&kg>0)errors.push((f.company||'Formül')+' satır '+(li+1)+': malzeme seçilmedi')})});return errors;}
function validateCalc(){const f=activeDraft(),cf=activeCommitted();const errors=[];if(!cf)return['Aktif formül bulunamadı'];if(!Number.isFinite(+f.months)||+f.months<0)errors.push('Vade ay değeri geçersiz');if(!Number.isFinite(+f.monthlyRate)||+f.monthlyRate<0)errors.push('Aylık vade oranı geçersiz');if(!Number.isFinite(+f.profit)||+f.profit<0)errors.push('Kâr oranı geçersiz');errors.push(...calculate(committed,cf).errors);return errors;}
function showErrors(el,errors){if(!el)return;if(errors.length){el.hidden=false;el.innerHTML=errors.map(e=>'• '+esc(e)).join('<br>')}else{el.hidden=true;el.innerHTML=''}}
function markDirty(page){dirty[page]=true;saveErrors[page]=false;updateSaveUI()}
function resolveActiveFormulaId(data){
  const formulas=data?.formulas||[];
  if(!formulas.length)return'';
  const preferred=data.meta?.activeFormulaId;
  if(preferred&&formulas.some(f=>f.id===preferred))return preferred;
  return formulas[0].id;
}
function validateDataPayload(body){
  if(!body||typeof body!=='object')throw new Error('Geçersiz veri yanıtı');
  if(!Array.isArray(body.formulas)||!body.formulas.length)throw new Error('Formül verisi bulunamadı');
  if(!Array.isArray(body.materials))throw new Error('Malzeme verisi bulunamadı');
}
function setLoadState(state,errorMsg){
  loadState=state;
  loadError=state==='error'?(errorMsg||'Veriler yüklenemedi'):null;
  document.body.classList.toggle('data-loading',state==='loading');
  document.body.classList.toggle('data-ready',state==='ready');
  document.body.classList.toggle('data-error',state==='error');
  const stack=$('bannerStack'),banner=$('loadStateBanner'),retry=$('btnRetryLoad');
  const showStack=state==='loading'||state==='error';
  if(stack){stack.hidden=!showStack;stack.setAttribute('aria-hidden',showStack?'false':'true')}
  if(banner){
    if(state==='loading'){banner.hidden=false;banner.className='load-state-banner loading';banner.textContent='Veriler yükleniyor…'}
    else if(state==='error'){banner.hidden=false;banner.className='load-state-banner error';banner.textContent=loadError||'Veriler yüklenemedi. Tekrar deneyin.'}
    else{banner.hidden=true;banner.textContent=''}
  }
  if(retry)retry.hidden=state!=='error';
  updateSaveUI();
}
function invalidateCalcCache(formulaId){
  if(formulaId)delete calcApiByFormula[formulaId];
  else calcApiByFormula={};
}
function calcFormulaForResult(){
  const c=activeCommitted(),d=activeDraft();
  if(!c)return null;
  if(dirty.formulas&&d){
    const preview=deepClone(d);
    if(!dirty.calc){
      preview.months=c.months;
      preview.monthlyRate=c.monthlyRate;
      preview.profit=c.profit;
    }
    return preview;
  }
  if(dirty.calc&&d)return{...c,months:d.months,monthlyRate:d.monthlyRate,profit:d.profit};
  return c;
}
function activateFormula(id,opts={}){
  const persistMeta=opts.persistMeta!==false;
  const refreshCalc=opts.refreshCalc!==false;
  const run=()=>{
    if(id===activeId&&!refreshCalc){render();return}
    activeWarnExpanded=false;
    activeId=id;
    if(persistMeta&&committed.meta)committed.meta.activeFormulaId=id;
    if(persistMeta)apiPut('/api/meta',{activeFormulaId:id}).catch(()=>{});
    invalidateCalcCache(id);
    render();
    if(refreshCalc)fetchCalcForFormula(id);
  };
  if(opts.navDirty!==false)requestNavigation(run);
  else run();
}
function selectFormulaCard(id){activateFormula(id,{persistMeta:false,refreshCalc:false})}
function updateSaveUI(){
  const savesAllowed=loadState==='ready';
  PAGES.forEach(p=>{const btn=$('save'+p.charAt(0).toUpperCase()+p.slice(1));const st=$('saveState'+p.charAt(0).toUpperCase()+p.slice(1));if(btn){btn.disabled=!savesAllowed||!dirty[p];btn.classList.toggle('dirty',!!dirty[p])}if(st){if(loadState==='loading'){st.textContent='Veriler yükleniyor…';st.className='save-state'}else if(loadState==='error'){st.textContent='Veri yüklenemedi';st.className='save-state err'}else if(saveErrors[p]){st.textContent='Kayıt başarısız';st.className='save-state err'}else if(dirty[p]){st.textContent='Kaydedilmemiş değişiklik var';st.className='save-state dirty'}else if(committed.savedAt?.[p]){st.textContent=formatSavedAt(committed.savedAt[p]);st.className='save-state ok'}else{st.textContent='Henüz kaydedilmedi';st.className='save-state ok'}}});
  const st=$('saveStatus');if(st){
    if(loadState==='loading'){st.textContent='Veriler yükleniyor…';st.className='status loading'}
    else if(loadState==='error'){st.textContent='! '+(loadError||'Veriler yüklenemedi');st.className='status err'}
    else if(loadError){st.textContent='! '+loadError;st.className='status err'}
    else if(Object.values(dirty).some(Boolean)){st.textContent='! Kaydedilmemiş değişiklik var';st.className='status dirty'}
    else{st.textContent='✓ SQLite veritabanı · Bağlı';st.className='status ok'}
  }
}
async function ensureCsrf(force){
  if(csrfToken&&!force)return csrfToken;
  try{
    const stored=sessionStorage.getItem('nexgen_csrf');
    if(stored&&!force){csrfToken=stored;sessionStorage.removeItem('nexgen_csrf');return csrfToken}
  }catch(e){}
  const resp=await fetch(API_BASE+'/api/auth/csrf');
  if(resp.status===401){window.location.replace('/login');throw new Error('Oturum sona erdi')}
  if(resp.ok){const d=await resp.json();csrfToken=d.csrfToken||''}
  return csrfToken;
}
async function apiRequest(path,method,payload){
  await ensureCsrf();
  const headers={};
  if(method!=='GET'){headers['Content-Type']='application/json';headers['X-CSRF-Token']=csrfToken}
  const resp=await fetch(API_BASE+path,{method,headers,body:payload!==undefined?JSON.stringify(payload):undefined});
  if(resp.status===401){window.location.replace('/login');throw new Error('Oturum sona erdi')}
  const contentType=(resp.headers.get('Content-Type')||'').toLowerCase();
  let body;
  if(contentType.includes('application/json')){
    body=await resp.json().catch(()=>({ok:false,error:'Geçersiz sunucu yanıtı'}));
  }else{
    const text=await resp.text().catch(()=>'');
    body={
      ok:false,
      error:text&&text.length<200?text:(resp.ok?'Geçersiz sunucu yanıtı':('Sunucu hatası ('+resp.status+')')),
    };
  }
  if(typeof body.error==='object'&&body.error?.message)body.error=body.error.message;
  return{resp,body};
}
async function apiPut(path,payload){return apiRequest(path,'PUT',payload)}
async function apiPost(path,payload){return apiRequest(path,'POST',payload)}
function clearLegacyStorage(){try{localStorage.removeItem('nexgen-maliyet-v1')}catch(e){}}
function applyWeeklyReviewState(wr){
  weeklyReview={...weeklyReview,...wr,due:!!wr?.due};
  const banner=$('reviewBanner'),last=$('reviewLastLine'),badge=$('reviewBadge'),pending=$('reviewPendingWarn');
  const matBanner=$('materialsWeeklyBanner'),completeBtn=$('completeWeeklyReview');
  if(banner){
    banner.hidden=false;
    if(last)last.textContent=wr?.lastReviewLine||'Henüz haftalık fiyat kontrolü kaydı yok.';
    if(badge){
      badge.textContent=wr?.badgeText||'';
      badge.className='review-badge '+(wr?.badge==='ok'?'ok':'pending');
    }
    if(pending)pending.hidden=!wr?.due;
  }
  if(matBanner)matBanner.hidden=!(weeklyReview.due&&weeklyReview.weeklyReviewMode);
  if(completeBtn){
    const show=weeklyReview.due&&weeklyReview.weeklyReviewMode;
    completeBtn.hidden=!show;
    completeBtn.disabled=!weeklyReview.materialsSavedForReview;
  }
  if(wr?.due&&!weeklyReview._modalShown&&loadState==='ready'){
    weeklyReview._modalShown=true;
    const modal=$('weeklyReviewModal');
    if(modal)modal.hidden=false;
  }
  if(!wr?.due){
    weeklyReview.weeklyReviewMode=false;
    weeklyReview.materialsSavedForReview=false;
    weeklyReview._modalShown=false;
    const modal=$('weeklyReviewModal');
    if(modal)modal.hidden=true;
  }
}
async function refreshWeeklyReview(){
  const{resp,body}=await apiRequest('/api/weekly-review/status','GET');
  if(resp.ok&&body.ok!==false)applyWeeklyReviewState(body);
}
function applyServerPayload(body,weeklyReviewPayload){
  migrateData(body);
  committed=deepClone(body);
  draft=deepClone(body);
  versions={...versions,...body.versions};
  activeId=resolveActiveFormulaId(body);
  PAGES.forEach(p=>{dirty[p]=false;saveErrors[p]=false});
  if(weeklyReviewPayload)applyWeeklyReviewState(weeklyReviewPayload);
}
async function reloadFromServer(){
  const{resp,body}=await apiRequest('/api/data','GET');
  if(!resp.ok)throw new Error('Veri yüklenemedi ('+resp.status+')');
  validateDataPayload(body);
  applyServerPayload(body,body.weeklyReview);
}
async function bootstrapApp(){
  const seq=++bootstrapSeq;
  setLoadState('loading');
  calcApiByFormula={};
  try{
    await ensureCsrf(true);
    const{resp,body}=await apiRequest('/api/data','GET');
    if(seq!==bootstrapSeq)return;
    if(resp.status===401){window.location.replace('/login');return}
    if(!resp.ok)throw new Error('Veri yüklenemedi ('+resp.status+')');
    validateDataPayload(body);
    applyServerPayload(body,null);
    setLoadState('ready');
    render();
    if(body.weeklyReview)applyWeeklyReviewState(body.weeklyReview);
    await fetchCalcForFormula(activeId);
  }catch(e){
    if(seq!==bootstrapSeq)return;
    if(String(e.message||'').includes('Oturum')){window.location.replace('/login');return}
    setLoadState('error',e.message||'Veriler yüklenemedi');
    render();
  }
}
function applySaveToCommitted(page){
  if(page==='materials'){committed.materials=deepClone(draft.materials);[draft,committed].forEach(src=>src.formulas.forEach(f=>f.lines.forEach(l=>syncLineCode(l,src.materials))))}
  else if(page==='expenses'){committed.productionKg=draft.productionKg;committed.usdTry=draft.usdTry;committed.expenses=deepClone(draft.expenses)}
  else if(page==='formulas'){draft.formulas.forEach(f=>f.lines.forEach(l=>{normalizeLineKg(l);syncLineCode(l,draft.materials)}));committed.formulas=deepClone(draft.formulas);committed.formulas.forEach(f=>f.lines.forEach(l=>syncLineCode(l,committed.materials)))}
  else if(page==='calc'){const d=activeDraft(),c=activeCommitted();if(d&&c){c.months=d.months;c.monthlyRate=d.monthlyRate;c.profit=d.profit}}
}
async function savePage(page){
  let errors=[];
  if(page==='materials')errors=validateMaterials(draft);
  else if(page==='expenses')errors=validateExpenses(draft);
  else if(page==='formulas')errors=validateActiveFormula(draft);
  else if(page==='calc')errors=validateCalc();
  showErrors($('materialsErrors'),page==='materials'?errors:[]);
  showErrors($('formulasErrors'),page==='formulas'?errors:[]);
  showErrors($('expensesErrors'),page==='expenses'?errors:[]);
  if(errors.length)return{ok:false,errors};
  try{
    let result;
    if(page==='materials'){
      const{resp,body}=await apiPut('/api/materials',{materials:draft.materials,version:versions.materials});
      if(!resp.ok||!body.ok){saveErrors.materials=true;updateSaveUI();return{ok:false,errors:[body.error||'Malzeme kaydı başarısız']}}
      applySaveToCommitted(page);committed.savedAt.materials=body.savedAt;versions.materials=body.version;result=body;
      if(weeklyReview.due&&weeklyReview.weeklyReviewMode&&(body.priceChanges||0)>0){
        weeklyReview.materialsSavedForReview=true;
        const completeBtn=$('completeWeeklyReview');
        if(completeBtn){completeBtn.hidden=false;completeBtn.disabled=false}
      }
      await refreshWeeklyReview();
    }else if(page==='expenses'){
      const{resp,body}=await apiPut('/api/expenses',{productionKg:draft.productionKg,usdTry:draft.usdTry,expenses:draft.expenses,version:versions.expenses});
      if(!resp.ok||!body.ok){saveErrors.expenses=true;updateSaveUI();return{ok:false,errors:[body.error||'Gider kaydı başarısız']}}
      applySaveToCommitted(page);committed.savedAt.expenses=body.savedAt;versions.expenses=body.version;result=body;
    }else if(page==='formulas'){
      const{resp,body}=await apiPut('/api/formulas',{formulas:draft.formulas,version:versions.formulas});
      if(!resp.ok||!body.ok){saveErrors.formulas=true;updateSaveUI();return{ok:false,errors:[body.error||'Formül kaydı başarısız']}}
      applySaveToCommitted(page);committed.savedAt.formulas=body.savedAt;versions.formulas=body.version;result=body;
    }else if(page==='calc'){
      const d=activeDraft();
      const{resp,body}=await apiPut('/api/calc',{formulaId:activeId,months:d.months,monthlyRate:d.monthlyRate,profit:d.profit,version:versions.calc});
      if(!resp.ok||!body.ok){saveErrors.calc=true;updateSaveUI();return{ok:false,errors:[body.error||'Maliyet kaydı başarısız']}}
      applySaveToCommitted(page);committed.savedAt.calc=body.savedAt;versions.calc=body.version;result=body;
    }
    dirty[page]=false;saveErrors[page]=false;updateSaveUI();
    if(page==='formulas'||page==='calc'){
      invalidateCalcCache(activeId);
      await fetchCalcForFormula(activeId);
    }
    if(page==='materials'&&pendingReturnToCalc){pendingReturnToCalc=false;highlightMaterialCodes.clear();calcApiByFormula={};await reloadFromServer();showPage('calc');render();fetchCalcForFormula(activeId);return{ok:true,result}}
    render();
    return{ok:true,result};
  }catch(e){saveErrors[page]=true;updateSaveUI();return{ok:false,errors:[e.message||'Ağ/API hatası']}}
}
function discardDraft(page){
  if(page==='materials')draft.materials=deepClone(committed.materials);
  else if(page==='expenses'){draft.productionKg=committed.productionKg;draft.usdTry=committed.usdTry;draft.expenses=deepClone(committed.expenses)}
  else if(page==='formulas')draft.formulas=deepClone(committed.formulas);
  else if(page==='calc'){const d=activeDraft(),c=activeCommitted();if(d&&c){d.months=c.months;d.monthlyRate=c.monthlyRate;d.profit=c.profit}}
  dirty[page]=false;saveErrors[page]=false;updateSaveUI();render();
}
function hasDirty(){return Object.values(dirty).some(Boolean)}
function requestNavigation(action){
  const dirtyPages=PAGES.filter(p=>dirty[p]);
  if(!dirtyPages.length){action();return}
  pendingNav={action,dirtyPages};
  $('unsavedModalText').textContent='Kaydedilmemiş değişiklikler var. Nasıl devam etmek istiyorsunuz?';
  $('unsavedModalErrors').hidden=true;
  $('unsavedModal').hidden=false;
}
function closeUnsavedModal(){$('unsavedModal').hidden=true;pendingNav=null}
function showPage(name){current=name;document.querySelectorAll('.page').forEach(x=>x.classList.toggle('active',x.id===name));document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('active',x.dataset.page===name));$('mobileNav').value=name;render();if(name==='calc'&&loadState==='ready')fetchCalcForFormula(activeId)}
function navigateTo(name){requestNavigation(()=>showPage(name))}
function clearCalcSummary(){
  ['cashRawKg','overKg','cashCostKg','cashProfitKg','cashSaleKg','rawKg','termOverKg','costKg','profitKg','saleKg'].forEach(id=>{const el=$(id);if(el)el.textContent='—'});
  const note=$('summaryInvalidNote');if(note){note.hidden=true;note.textContent=''}
  const block=$('termBlock'),final=$('termFinal');if(block)block.hidden=true;if(final)final.hidden=true;
  const z=$('termZeroNote');if(z)z.remove();
  $('calcSale').textContent='—';
}
async function fetchCalcForFormula(formulaId){
  const seq=++calcFetchSeq;
  calcLoading=true;
  clearCalcSummary();
  const summaryCard=document.querySelector('.cost-summary');if(summaryCard)summaryCard.classList.add('summary-loading');
  renderCalc();
  try{
    const{resp,body}=await apiRequest('/api/calculate/'+formulaId,'GET');
    if(seq!==calcFetchSeq||activeId!==formulaId)return;
    if(resp.ok&&body.result)calcApiByFormula[formulaId]=body.result;
  }catch(e){/* render local fallback */}
  finally{
    if(seq===calcFetchSeq){
      calcLoading=false;
      if(summaryCard)summaryCard.classList.remove('summary-loading');
      renderCalc();
    }
  }
}
function switchFormula(id){activateFormula(id,{persistMeta:true,refreshCalc:true})}
function calcResultFor(f){
  const calcF=calcFormulaForResult()||f;
  const paramsDirty=dirty.calc||dirty.formulas;
  const api=calcApiByFormula[f.id];
  if(!paramsDirty&&api&&api.formulaId===f.id)return api;
  return calculate(committed,calcF);
}
function goFixMissingPrices(){
  const f=activeCommitted();const codes=missingPriceCodes(f,committed.materials);
  highlightMaterialCodes=new Set(codes);pendingReturnToCalc=true;
  requestNavigation(()=>{showPage('materials');renderMaterials();setTimeout(()=>{const row=document.querySelector('#materialRows tr.missing-price-highlight');if(row)row.scrollIntoView({behavior:'smooth',block:'center'})},120)});
}
function renderTermPanel(f,c){
  const block=$('termBlock'),final=$('termFinal');
  if(!c.valid||f.months<=0){block.hidden=true;final.hidden=true;const note=$('termZeroNote');if(note)note.remove();return}
  const term=c.term_calculation;
  const hasTermZero=!!term?.sameAsCash;
  const hasTerm=f.monthlyRate>0;
  if(hasTermZero){
    block.hidden=false;final.hidden=false;block.classList.add('term-passive');
    const noteId='termZeroNote';let note=$(noteId);
    if(!note){note=document.createElement('div');note.id=noteId;note.className='term-zero-note';block.prepend(note)}
    note.textContent='Aylık vade oranı %'+fmt(f.monthlyRate,2)+' — vade farkı uygulanmıyor. Vadeli satış fiyatı nakit fiyatla aynıdır.';
    $('termMonths').textContent=f.months+' ay';$('termRate').textContent='× %'+fmt(f.monthlyRate,2);$('termTotalRate').textContent='= %'+fmt(f.months*f.monthlyRate,2);
    $('termNote').textContent='Vade farkı uygulanmıyor (oran %0)';
    $('rawKg').textContent=moneyOrDash(term.rawKg)+'/kg';$('termOverKg').textContent='+'+moneyOrDash(term.overhead,4)+'/kg';$('costKg').textContent=moneyOrDash(term.cost)+'/kg';
    $('profitLabel').textContent='Kâr %'+f.profit;$('profitKg').textContent='+'+moneyOrDash(term.profit)+'/kg';
    $('termFinalNote').textContent=f.months+' ay · oran %0 — nakit satış fiyatı geçerlidir';$('saleKg').textContent=moneyOrDash(term.sale)+'/kg';
    return;
  }
  block.classList.remove('term-passive');const note=$('termZeroNote');if(note)note.remove();
  if(!hasTerm||!term){block.hidden=true;final.hidden=true;return}
  block.hidden=false;final.hidden=false;
  $('termMonths').textContent=f.months+' ay';$('termRate').textContent='× %'+fmt(f.monthlyRate,2);$('termTotalRate').textContent='= %'+fmt(f.months*f.monthlyRate,2);
  $('termNote').textContent='Nakit hammadde + toplam %'+fmt(f.months*f.monthlyRate,2)+' vade';
  $('rawKg').textContent=moneyOrDash(term.rawKg)+'/kg';$('termOverKg').textContent='+'+moneyOrDash(term.overhead,4)+'/kg';$('costKg').textContent=moneyOrDash(term.cost)+'/kg';
  $('profitLabel').textContent='Kâr %'+f.profit;$('profitKg').textContent='+'+moneyOrDash(term.profit)+'/kg';
  $('termFinalNote').textContent=f.months+' ay vade ve %'+f.profit+' kâr uygulanmış';$('saleKg').textContent=moneyOrDash(term.sale)+'/kg';
}
function renderCalc(){
  if(loadState==='loading'){clearCalcSummary();$('calcOverhead').textContent='…';$('calcSale').textContent='…';$('calcRows').innerHTML='';$('calcFormula').innerHTML='';return}
  if(loadState==='error'){clearCalcSummary();$('calcOverhead').textContent='—';$('calcSale').textContent='—';$('calcRows').innerHTML='';$('calcFormula').innerHTML='';return}
  const f=activeCommitted();if(!f)return;
  const calcF=calcFormulaForResult()||f;
  const c=calcResultFor(f);
  const recipeKg=c.recipeKg??c.recipe_total_kg??formulaTotalKg(f);
  const missCount=c.missing_price_count??missingPriceCodes(f,committed.materials).length;
  $('calcTitle').textContent=f.company+' · '+f.name;
  renderFormulaMeta(f);
  $('calcFormula').innerHTML=committed.formulas.map(x=>`<option value="${x.id}" ${x.id===f.id?'selected':''}>${formulaLabel(x)}</option>`).join('');
  const df=activeDraft();
  $('calcMonths').value=df.months;$('calcMonthlyRate').value=df.monthlyRate;$('calcProfit').value=df.profit;
  $('calcOverhead').textContent=c.valid?moneyOrDash(c.overhead,4)+'/kg':'—';
  const ohNote=$('calcOverheadNote');
  if(ohNote&&c.valid){const od=buildOverheadDetail(committed);ohNote.textContent='₺'+formatTrDecimal(od.tlKg,4)+'/kg ÷ kur → tek sefer eklenir'}
  else if(ohNote)ohNote.textContent='';
  const errBox=$('calcError');
  if(calcLoading){errBox.hidden=false;errBox.className='calc-error loading';errBox.innerHTML='Hesap yükleniyor…';$('calcRows').innerHTML='';clearCalcSummary();$('calcKg').textContent=fmt(recipeKg)+' kg formül';$('summaryKg').textContent=fmt(recipeKg)+' kg';updateSaveUI();return}
  errBox.className='calc-error';
  renderActiveFormulaBanner(errBox);
  const showSale=c.valid?((calcF.months>0&&calcF.monthlyRate>0)?c.sale:c.cashSale):null;
  $('calcSale').textContent=Number.isFinite(showSale)?moneyOrDash(showSale)+'/kg':'—';
  $('calcKg').textContent=fmt(recipeKg)+' kg formül';$('summaryKg').textContent=fmt(recipeKg)+' kg';
  $('calcRows').innerHTML=(c.allRows||[]).map(r=>`<tr data-group="${esc(r.category)}" class="${r.invalid?'row-error':''}"><td><b>${esc(r.code)}</b><small>${esc(r.name)}</small>${r.invalid?'<small style="color:#b22">Eksik/hatalı veri</small>':''}</td><td><span class="group-badge ${groupClass(r.category)}">${esc(r.category||'-')}</span></td><td>${fmt(r.kg,4)}</td><td>${money(r.cash)}</td><td>%${fmt(r.monthlyRate,2)}</td><td>${money(r.applied)}</td><td><b>${money(r.total)}</b></td></tr>`).join('');
  const invalidNote=$('summaryInvalidNote');
  if(!c.valid){
    clearCalcSummary();
    if(invalidNote){invalidNote.hidden=false;invalidNote.textContent='Maliyet özeti hazırlanamadı. '+missCount+' malzemenin güncel alım fiyatını tamamlayın.'}
    renderTermPanel(calcF,c);
  }else{
    if(invalidNote){invalidNote.hidden=true;invalidNote.textContent=''}
    const cash=c.cash_calculation||{};
    $('cashRawKg').textContent=moneyOrDash(cash.rawKg??c.cashRawKg)+'/kg';
    $('overKg').textContent='+'+moneyOrDash(cash.overhead??c.overhead,4)+'/kg';
    $('cashCostKg').textContent=moneyOrDash(cash.cost??c.cashCost)+'/kg';
    $('cashProfitLabel').textContent='Kâr %'+calcF.profit;
    $('cashProfitKg').textContent='+'+moneyOrDash(cash.profit??c.cashProfit)+'/kg';
    $('cashSaleKg').textContent=moneyOrDash(cash.sale??c.cashSale)+'/kg';
    renderTermPanel(calcF,c);
  }
  updateSaveUI();
}
function renderMaterials(){
  if(loadState!=='ready'){$('materialRows').innerHTML='';updateSaveUI();return}
  const sorted=[...draft.materials].sort((a,b)=>{const ah=highlightMaterialCodes.has(a.code)?0:1,bh=highlightMaterialCodes.has(b.code)?0:1;return ah-bh||a.code.localeCompare(b.code)});
  const indexMap=new Map(sorted.map((m,i)=>[m.id,draft.materials.indexOf(m)]));
  $('materialRows').innerHTML=sorted.map(m=>{const i=indexMap.get(m.id);const hl=highlightMaterialCodes.has(m.code)?' missing-price-highlight':'';return `<tr class="${hl.trim()}"><td><input data-m="${i}" data-k="code" value="${esc(m.code)}"></td><td><input data-m="${i}" data-k="name" value="${esc(m.name)}"></td><td><select data-m="${i}" data-k="category"><option ${m.category==='Ana Malzeme'?'selected':''}>Ana Malzeme</option><option ${m.category==='Katkı'?'selected':''}>Katkı</option><option ${m.category==='Boya'?'selected':''}>Boya</option></select></td><td><input data-m="${i}" data-k="cash" type="text" inputmode="decimal" value="${Number.isFinite(m.cash)?m.cash:''}"></td><td><button class="icon" data-del-m="${i}">Sil</button></td></tr>`}).join('');
  updateSaveUI();
}
function renderExpenses(){
  if(loadState==='loading'){$('productionKg').value='';$('usdTry').value='';$('expenseResult').textContent='…';$('expenseCent').textContent='…';$('expenseRows').innerHTML='';if($('overheadDetail'))$('overheadDetail').innerHTML='';updateSaveUI();return}
  if(loadState==='error'){$('productionKg').value='';$('usdTry').value='';$('expenseResult').textContent='—';$('expenseCent').textContent='—';$('expenseRows').innerHTML='';if($('overheadDetail'))$('overheadDetail').innerHTML='';updateSaveUI();return}
  $('productionKg').value=draft.productionKg;$('usdTry').value=draft.usdTry;$('expenseResult').textContent=money(overhead(draft),4)+'/kg';$('expenseCent').textContent=(overhead(draft)*100).toFixed(2);$('expenseRows').innerHTML=draft.expenses.map((x,i)=>`<tr><td><input data-e="${i}" data-k="name" value="${esc(x.name)}"></td><td><input data-e="${i}" data-k="amount" type="number" value="${x.amount}"></td><td><input data-e="${i}" data-k="rate" type="number" value="${x.rate}"></td><td><b>₺${Math.round(x.amount*x.rate/100).toLocaleString('tr-TR')}</b></td><td><button class="icon" data-del-e="${i}">Sil</button></td></tr>`).join('');renderOverheadDetail(draft);updateSaveUI()}
function renderFormulas(){
  if(loadState!=='ready'){$('formulaList').innerHTML='';$('formulaRows').innerHTML='';updateSaveUI();return}
  const f=activeDraft();$('formulaList').innerHTML=draft.formulas.map(x=>{
    const miss=formulaMissingCount(x,committed);
    const badge=miss?`<span class="formula-miss-badge">${miss} eksik fiyat</span>`:'';
    return `<button type="button" role="button" tabindex="0" aria-pressed="${x.id===f.id?'true':'false'}" data-f="${x.id}" class="${x.id===f.id?'active':''}"><b>${esc(x.company)}</b><small>${formulaLabel(x).replace(esc(x.company)+' — ','')}</small>${badge}</button>`;
  }).join('');
  if(!saveErrors.formulas)renderActiveFormulaBanner($('formulasErrors'));
  $('fCompany').value=f.company||'';$('fName').value=f.name||'';$('fColorName').value=f.colorName||'';$('fColorCode').value=f.colorCode||'';
  $('fFormulaDate').value=(f.formulaDate||'').split('T')[0]||'';
  $('fBaseExpansion').value=Number.isFinite(parseNum(f.baseExpansionMeasure))?String(f.baseExpansionMeasure).replace('.',','):'';
  $('fMonths').value=f.months;$('fMonthlyRate').value=f.monthlyRate;$('fProfit').value=f.profit;
  $('formulaRows').innerHTML=(f.lines||[]).map((l,i)=>{const m=materialById(draft.materials,l.materialId)||{cash:NaN,code:''};const selected=l.materialId||'';const kgVal=l.kg===0||l.kg==='0'? (l.kg??'') : (l.kg??'');return `<tr><td><select data-l="${i}" data-k="materialId">${draft.materials.map(mat=>`<option value="${esc(mat.id)}" ${mat.id===selected?'selected':''}>${esc(mat.code)} — ${esc(mat.name)}</option>`).join('')}</select></td><td><input data-l="${i}" data-k="kg" type="text" inputmode="decimal" value="${esc(kgVal)}"></td><td><b>${money(parseNum(m.cash))}</b><small>Peşin fiyat</small></td><td><button class="icon" data-del-l="${i}">Sil</button></td></tr>`}).join('');
  updateSaveUI();
}
function render(){if(current==='calc')renderCalc();if(current==='materials')renderMaterials();if(current==='expenses')renderExpenses();if(current==='formulas')renderFormulas()}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>navigateTo(b.dataset.page));
$('mobileNav').onchange=e=>navigateTo(e.target.value);
$('calcFormula').onchange=e=>switchFormula(e.target.value);
$('saveCalc').onclick=async()=>{const r=await savePage('calc');if(!r.ok&&current==='calc'){showErrors($('calcError'),r.errors);$('calcError').hidden=false}};
$('saveMaterials').onclick=async()=>{const r=await savePage('materials');if(!r.ok)showErrors($('materialsErrors'),r.errors)};
$('saveExpenses').onclick=async()=>{const r=await savePage('expenses');if(!r.ok)showErrors($('expensesErrors'),r.errors)};
$('saveFormulas').onclick=async()=>{const r=await savePage('formulas');if(!r.ok)showErrors($('formulasErrors'),r.errors)};
$('calcMonths').oninput=e=>{activeDraft().months=parseNum(e.target.value)||0;markDirty('calc');renderCalc()};
$('calcMonthlyRate').oninput=e=>{activeDraft().monthlyRate=parseNum(e.target.value)||0;markDirty('calc');renderCalc()};
$('calcProfit').oninput=e=>{activeDraft().profit=parseNum(e.target.value)||0;markDirty('calc');renderCalc()};
$('addMaterial').onclick=()=>{draft.materials.push({id:uid('mat'),code:'YENI-'+(draft.materials.length+1),name:'Yeni malzeme',cash:NaN,category:'Katkı'});markDirty('materials');renderMaterials()};
$('addExpense').onclick=()=>{draft.expenses.push({name:'Yeni gider',amount:0,rate:100});markDirty('expenses');renderExpenses()};
$('addFormula').onclick=()=>{const id='firma-'+Date.now();draft.formulas.push({id,company:'YENİ FİRMA',name:'Yeni formül',colorName:'',colorCode:'',formulaDate:'',baseExpansionMeasure:null,months:0,monthlyRate:0,profit:0,lines:[]});activeId=id;markDirty('formulas');renderFormulas()};
$('addLine').onclick=()=>{const mat=draft.materials[0];activeDraft().lines.push({materialId:mat?.id||'',code:mat?.code||'',kg:0});markDirty('formulas');renderFormulas()};
$('productionKg').oninput=e=>{draft.productionKg=parseNum(e.target.value)||0;markDirty('expenses');renderExpenses()};
$('usdTry').oninput=e=>{draft.usdTry=parseNum(e.target.value)||0;markDirty('expenses');renderExpenses()};
$('fCompany').oninput=e=>{activeDraft().company=e.target.value;markDirty('formulas')};
$('fName').oninput=e=>{activeDraft().name=e.target.value;markDirty('formulas')};
$('fColorName').oninput=e=>{activeDraft().colorName=e.target.value;markDirty('formulas')};
$('fColorCode').oninput=e=>{activeDraft().colorCode=e.target.value;markDirty('formulas')};
$('fFormulaDate').onchange=e=>{activeDraft().formulaDate=e.target.value;markDirty('formulas')};
$('fBaseExpansion').oninput=e=>{activeDraft().baseExpansionMeasure=parseNum(e.target.value);markDirty('formulas')};
$('fMonths').oninput=e=>{activeDraft().months=parseNum(e.target.value)||0;markDirty('formulas')};
$('fMonthlyRate').oninput=e=>{activeDraft().monthlyRate=parseNum(e.target.value)||0;markDirty('formulas')};
$('fProfit').oninput=e=>{activeDraft().profit=parseNum(e.target.value)||0;markDirty('formulas')};
document.addEventListener('input',e=>{const t=e.target;if(t.dataset.m!==undefined){const m=draft.materials[+t.dataset.m],k=t.dataset.k;if(!m)return;m[k]=k==='cash'?parseNum(t.value):t.value;markDirty('materials')}if(t.dataset.e!==undefined){const x=draft.expenses[+t.dataset.e],k=t.dataset.k;x[k]=['amount','rate'].includes(k)?parseNum(t.value):t.value;markDirty('expenses')}if(t.dataset.l!==undefined){const l=activeDraft().lines[+t.dataset.l],k=t.dataset.k;if(k==='kg')l.kg=t.value;markDirty('formulas');if(current==='calc')renderCalc()}});
document.addEventListener('change',e=>{const t=e.target;if(t.dataset.l!==undefined&&t.dataset.k==='materialId'){const l=activeDraft().lines[+t.dataset.l];const mat=materialById(draft.materials,t.value);l.materialId=mat?.id||'';l.code=mat?.code||'';markDirty('formulas');renderFormulas()}if(t.dataset.m!==undefined&&t.dataset.k==='category'){draft.materials[+t.dataset.m].category=t.value;markDirty('materials')}});
document.addEventListener('click',e=>{const t=e.target.closest('button');if(!t)return;if(t.dataset.f&&t.closest('#formulaList')){selectFormulaCard(t.dataset.f);return}if(t.dataset.delM!==undefined&&confirm('Malzeme silinsin mi?')){draft.materials.splice(+t.dataset.delM,1);markDirty('materials');renderMaterials()}if(t.dataset.delE!==undefined&&confirm('Gider silinsin mi?')){draft.expenses.splice(+t.dataset.delE,1);markDirty('expenses');renderExpenses()}if(t.dataset.delL!==undefined){activeDraft().lines.splice(+t.dataset.delL,1);markDirty('formulas');renderFormulas()}});
document.addEventListener('keydown',e=>{const t=e.target.closest('#formulaList [data-f]');if(!t)return;if(e.key==='Enter'||e.key===' '){e.preventDefault();selectFormulaCard(t.dataset.f)}});
$('unsavedCancel').onclick=closeUnsavedModal;
$('unsavedDiscard').onclick=async()=>{if(!pendingNav)return;for(const p of pendingNav.dirtyPages)discardDraft(p);const act=pendingNav.action;closeUnsavedModal();act()};
$('unsavedSave').onclick=async()=>{if(!pendingNav)return;const errors=[];for(const p of pendingNav.dirtyPages){const r=await savePage(p);if(!r.ok)errors.push(...r.errors.map(e=>'['+p+'] '+e))}if(errors.length){$('unsavedModalErrors').hidden=false;$('unsavedModalErrors').innerHTML=errors.map(e=>'• '+esc(e)).join('<br>');return}const act=pendingNav.action;closeUnsavedModal();act()};
window.addEventListener('beforeunload',e=>{if(hasDirty()){e.preventDefault();e.returnValue=''}});
history.pushState({nx:'init'},'');
window.addEventListener('popstate',()=>{if(hasDirty()){history.pushState({nx:'stay'},'');requestNavigation(()=>history.back())}else history.back()});
async function confirmWeeklyUnchanged(){
  const err=$('weeklyModalError');
  if(err){err.hidden=true;err.textContent=''}
  const{resp,body}=await apiPost('/api/weekly-review/unchanged',{});
  if(!resp.ok||!body.ok){
    if(err){err.hidden=false;err.textContent=body.error||'Onay kaydedilemedi'}
    return;
  }
  $('weeklyReviewModal').hidden=true;
  weeklyReview.weeklyReviewMode=false;
  weeklyReview.materialsSavedForReview=false;
  await reloadFromServer();
  render();
}
async function completeWeeklyReviewFlow(){
  const{resp,body}=await apiPost('/api/weekly-review/complete',{});
  if(!resp.ok||!body.ok){showErrors($('materialsErrors'),[body.error||'Haftalık kontrol tamamlanamadı']);return}
  weeklyReview.weeklyReviewMode=false;
  weeklyReview.materialsSavedForReview=false;
  await reloadFromServer();
  showPage('calc');
  render();
}
async function logout(){
  try{await apiPost('/api/auth/logout',{})}catch(e){}
  csrfToken='';
  loadState='loading';
  window.location.replace('/login');
}
$('weeklyGoMaterials')?.addEventListener('click',()=>{$('weeklyReviewModal').hidden=true;weeklyReview.weeklyReviewMode=true;showPage('materials');renderMaterials()});
$('weeklyUnchanged')?.addEventListener('click',confirmWeeklyUnchanged);
$('completeWeeklyReview')?.addEventListener('click',completeWeeklyReviewFlow);
$('btnLogout')?.addEventListener('click',logout);
window.__nx={get committed(){return committed},get draft(){return draft},get loadState(){return loadState},get activeId(){return activeId},dirty,calculate,parseNum,reloadFromServer,bootstrapApp,savePage,versions,formulaTotalKg,missingPriceCodes,formulaMissingCount,activeFormulaIssues,weeklyReview,refreshWeeklyReview,logout,ensureCsrf};
clearLegacyStorage();
setLoadState('loading');
render();
$('btnRetryLoad')?.addEventListener('click',()=>bootstrapApp());
window.addEventListener('pageshow',e=>{if(e.persisted)bootstrapApp()});
document.addEventListener('visibilitychange',()=>{
  if(document.visibilityState!=='visible'||loadState!=='ready')return;
  fetch(API_BASE+'/api/data',{credentials:'same-origin'}).then(r=>{if(r.status===401)window.location.replace('/login')}).catch(()=>{});
});
bootstrapApp();
