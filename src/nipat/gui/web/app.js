/* NewPat desktop UI. Scientific work is performed only by the existing Python service. */
(() => {
'use strict';
const L=window.NipatI18n,t=k=>L.t(k),$=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const clone=v=>JSON.parse(JSON.stringify(v));
const absent=v=>v===null||v===undefined||v===''||v==='NA'||v==='NaN';
const number=v=>absent(v)?null:Number.isFinite(Number(v))?Number(v):null;
const format=(v,d=5)=>number(v)===null?t('notAvailable'):new Intl.NumberFormat(L.language==='en'?'en-GB':'it-IT',{maximumFractionDigits:d}).format(Number(v));
const basename=p=>String(p||'').split(/[\\/]/).pop();
const moduleName=m=>({'dnp-call':t('genotypes')+' DNP','snp-call':t('genotypes')+' SNP',contamination:t('contamination'),cpi:t('cpi'),cpin:t('cpin'),analysis:t('analysis')}[m]||m||'');
const icons={home:'<path d="m3 10 9-7 9 7v10H3Z"/><path d="M9 20v-7h6v7"/>',new:'<path d="M8 3v6l-4 9a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3l-4-9V3M7 3h10M7 15h10"/>',archive:'<path d="M3 6h7l2 2h9v12H3ZM3 8V4h7l2 2h9v2"/>',activity:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',igv:'<path d="M3 5h18M3 19h18M5 9h4m2 0h6m2 0h2M3 12h6m2 0h3m2 0h3M6 15h5m2 0h8"/>',catalog:'<path d="M4 4h6a3 3 0 0 1 3 3v14a4 4 0 0 0-4-2H4ZM20 4h-4a3 3 0 0 0-3 3M20 4v15h-3a4 4 0 0 0-4 2"/>',settings:'<path d="M4 7h16M4 17h16"/><circle cx="8" cy="7" r="3"/><circle cx="16" cy="17" r="3"/>',environment:'<rect x="3" y="3" width="18" height="13" rx="2"/><path d="M9 21h6m-3-5v5M7 8l3 2-3 2m6 0h4"/>',arrow:'<path d="m9 5 7 7-7 7"/>',back:'<path d="m15 5-7 7 7 7"/>',plus:'<path d="M12 4v16M4 12h16"/>',close:'<path d="m6 6 12 12M18 6 6 18"/>',file:'<path d="M5 3h9l5 5v13H5ZM14 3v6h5M8 13h8m-8 4h5"/>',download:'<path d="M12 3v12m-5-5 5 5 5-5M4 17v4H16"/>',check:'<path d="m5 12 4 4L19 6"/>',info:'<circle cx="12" cy="12" r="9"/><path d="M12 10v7m0-10v.1"/>',stop:'<rect x="6" y="6" width="12" height="12" rx="1"/>',play:'<path d="m8 4 12 8-12 8Z"/>'};
const icon=n=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[n]||icons.file}</svg>`;
const nav=['home','new','activity','archive','igv','catalog','settings','environment'];
const state={view:'home',boot:null,settings:{},draft:null,step:0,source:'bam',sampleKind:'bam',preview:null,error:'',jobs:[],recentRuns:[],archiveListing:null,run:null,runId:null,runTab:'results',overview:null,files:[],module:null,entry:0,table:null,tableFile:null,tableOffset:0,tableSearch:'',allColumns:false,curves:[],curvePages:{},curveModes:{},archiveSearch:'',archivePage:0,archiveStatus:'all',archiveMarker:'all',catalogModule:'all',catalogType:'parameters',catalogSearch:'',catalogDefaults:false,preferences:null,baseline:null,environment:null,resourcePreview:null,igv:{reference:{fasta:'',index:''},tracks:[],locus:'',loaded:false},motion:true};
let igvNavigationUnsubscribe=null,curveId=0;const curveViews=new Map();
let startingDraft=null,demoRevision=null;
const visibleLogs=new Map();
const pageTrail=[];

function pageLocation(){
 const page={view:state.view,scroll:window.scrollY||0};
 if(state.view==='catalog')page.catalogDefaults=state.catalogDefaults;
 if(state.view==='archive'&&!state.run){
  page.list={archivePage:state.archivePage,archiveSearch:state.archiveSearch,archiveStatus:state.archiveStatus,archiveMarker:state.archiveMarker};
 }
 if(state.view==='archive'&&state.run){
  Object.assign(page,{runId:state.runId,root:state.baseline?.runs_dir||state.boot.layout.runs_dir,
   tab:state.runTab,module:state.module,entry:state.entry,
   search:state.tableSearch,offset:state.tableOffset,allColumns:state.allColumns,
   curveModes:{...state.curveModes},curvePages:{...state.curvePages}});
  if(state.modalTable&&$('modal-root').innerHTML)page.tableDialog={id:state.modalTable.file.id,offset:state.modalTable.offset};
 }
 if(state.view==='igv'&&state.igv.loaded){
  page.viewer={...clone(state.igv.loadedSources),locus:state.igv.locus};
 }
 return page;
}
function rememberPage(){
 pageTrail.push(pageLocation());
 if(pageTrail.length>30)pageTrail.shift();
}
function forgetRunPages(id,root=state.baseline?.runs_dir||state.boot.layout.runs_dir){
 for(let index=pageTrail.length-1;index>=0;index--){
  const page=pageTrail[index];
  if(page.runId===id&&page.root===root)pageTrail.splice(index,1);
 }
}
async function restoreResultsPage(page){
 const version=runLoadVersion;
 const current=()=>state.view==='archive'&&state.runId===page.runId&&runLoadVersion===version;
 if(!current())return;
 const reload=state.module!==page.module||state.entry!==page.entry||(!state.table&&!state.curves.length);
 state.runTab=page.tab;state.module=page.module;state.entry=page.entry;state.allColumns=page.allColumns;
 if(page.module&&page.module!=='files'){
  if(reload)await loadEntry();
  if(!current()||state.module!==page.module||state.entry!==page.entry)return;
  if(state.tableFile&&(state.tableSearch!==page.search||state.tableOffset!==page.offset)){
   state.tableSearch=page.search;await loadTable(page.offset);
  }
  if(!current())return;
 }
 if(!current())return;
 state.curveModes=page.curveModes;state.curvePages=page.curvePages;render();
 if(page.tableDialog)await openFile(page.tableDialog.id,page.tableDialog.offset);
}
async function pageBack(){
 if(state.view==='new'&&state.step>0)return action('step',{index:state.step-1});
 if(state.view==='archive'&&state.run&&(state.runTab!=='results'||state.module)){
  state.runTab='results';return action('result-module',{module:''});
 }
 const page=pageTrail.pop()||{view:'home'};
 if(page.runId){
  if(page.root!==(state.baseline?.runs_dir||state.boot.layout.runs_dir))return navigate('archive',{remember:false});
  const cached=state.run?.id===page.runId,version=runLoadVersion+1;
  await navigate('archive',{remember:false,keepRun:cached});
  if(state.view!=='archive'||runLoadVersion!==version)return;
  if(!cached){
   // History can refer to a different page or a run hidden by another window.
   if(!state.archiveListing?.runs?.some(run=>run.id===page.runId)){
    const match=await rpc('runs.list',{run_id:page.runId,offset:0,limit:1});
    if(runLoadVersion!==version||!match.runs.some(run=>run.id===page.runId))return;
   }
   await loadRun(page.runId,false);
  }
  await restoreResultsPage(page);
 }else{
  if(page.view==='catalog')state.catalogDefaults=page.catalogDefaults;
  if(page.list)Object.assign(state,page.list);
  await navigate(page.view,{remember:false});
  if(page.viewer&&state.view==='igv'){
   Object.assign(state.igv,page.viewer);referenceForms.delete(state.igv);await action('igv-load',{});
  }
 }
 if(state.view===page.view)window.scrollTo?.(0,page.scroll||0);
}
let requestId=0,draftRevision=0,draftLoadVersion=0,igvLoadVersion=0,renderGeneration=0,toastTimer,searchTimer,pollTimer,previousFocus=null,entryLoadVersion=0,runLoadVersion=0,tableLoadVersion=0;
async function rpc(method,params={}){
 const id=++requestId,controller=new AbortController(),timer=setTimeout(()=>controller.abort(),method==='updates.download'?7200000:method==='environment.check'?600000:method==='references.register'?3600000:method.startsWith('dialog.')?600000:180000);
 try{const response=await fetch('../api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,method,params}),signal:controller.signal,credentials:'same-origin'});let message;try{message=await response.json()}catch{throw new Error(t('connectionError'))}if(message.error)throw new Error(typeof message.error==='string'?message.error:message.error.message||t('operationError'));if(!response.ok)throw new Error(t('connectionError'));return message.result??message;}catch(error){if(error.name==='AbortError'||error instanceof TypeError)throw new Error(t('connectionError'));throw error;}finally{clearTimeout(timer)}
}
window.nipatRpc=rpc;
function button(label,action,data={},kind='',ic=''){return `<button class="button ${kind}" data-action="${action}" ${Object.entries(data).map(([k,v])=>`data-${k}="${esc(v)}"`).join(' ')}>${ic?icon(ic):''}${esc(label)}</button>`}
function heading(title,subtitle='',actions='',eyebrow=''){return `<div class="page-heading"><div>${eyebrow?`<div class="eyebrow">${esc(eyebrow)}</div>`:''}<h1>${esc(title)}</h1>${subtitle?`<p>${esc(subtitle)}</p>`:''}</div>${actions?`<div class="actions">${actions}</div>`:''}</div>`}
function notice(message,type=''){return `<div class="notice ${type}" ${type==='error'?'role="alert"':''}>${esc(message)}</div>`}
function empty(title,copy='',action=''){return `<div class="empty-state"><div class="icon-box">${icon('info')}</div><h3>${esc(title)}</h3>${copy?`<p>${esc(copy)}</p>`:''}${action?`<div class="actions">${action}</div>`:''}</div>`}
function select(label,id,options,value,attrs=''){return `<div class="field"><label for="${id}">${esc(label)}</label><select id="${id}" class="input" ${attrs}>${options.map(([v,l])=>`<option value="${esc(v)}" ${v===value?'selected':''}>${esc(l)}</option>`).join('')}</select></div>`}
function input(label,id,value,attrs='',help=''){return `<div class="field"><label for="${id}">${esc(label)}</label><input id="${id}" class="input" value="${esc(value??'')}" ${attrs}>${help?`<p class="help">${esc(help)}</p>`:''}</div>`}
function fileField(label,key,value,filter='all'){return `<div class="field"><label>${esc(label)}</label><div class="file-field"><input class="input" value="${esc(value||'')}" readonly placeholder="${esc(t('chooseFile'))}" aria-label="${esc(label)}">${button(t('browse'),'choose-path',{key,filter},'small','archive')}${value?button(t('remove'),'clear-path',{key},'quiet small','close'):''}</div></div>`}
const referenceBuilds=[['file','directFasta'],['grch37','GRCh37 / hg19'],['grch38','GRCh38 / hg38'],['custom','savedCustomFasta']];
const assemblyLabel=build=>{const key=referenceBuilds.find(([id])=>id===build)?.[1];return key?.startsWith('GRCh')?key:t(key||'directFasta')};
const referenceForms=new WeakMap();
let referenceEntries=[],referenceListVersion=0;
const referenceDownloads=new Map(),referenceReceivers=new Map();
function referenceForm(scope){
 const owner=scope==='new'?state.draft:state.igv;
 if(!referenceForms.has(owner)){
  const saved=scope==='new'?(owner.reference_id?owner.reference_genome:null):owner.reference;
  referenceForms.set(owner,{build:saved?.build||(owner.reference_id?referenceEntries.find(e=>e.id===owner.reference_id)?.build:null)||'file',token:0});
 }
 return referenceForms.get(owner);
}
function referencePath(scope){return scope==='new'?state.draft.reference:state.igv.reference.fasta}
function setRegisteredReference(scope,entry){
 if(scope==='new'){
  state.draft.reference=entry?.fasta||null;
  delete state.draft.reference_genome;
  if(entry)state.draft.reference_id=entry.id;else delete state.draft.reference_id;
  invalidate();
 }else{
  ++igvLoadVersion;
  const reference={fasta:entry?.fasta||'',index:entry?.index||''};
  if(entry?.build&&entry.build!=='custom')reference.build=entry.build;
  for(const key of ['fasta_sha256','index_sha256','gzi_sha256'])if(entry?.[key])reference[key]=entry[key];
  if(entry?.compressedIndex)reference.compressedIndex=entry.compressedIndex;
  state.igv.reference=reference;
 }
}
async function loadReferenceEntries(){
 const version=++referenceListVersion;
 const result=await rpc('references.list',{language:L.language});
 if(version===referenceListVersion)referenceEntries=result.entries||[];
}
function activeTransfer(transfer){return ['downloading','unpacking','indexing'].includes(transfer?.status)}
function transferCaption(transfer){
 if(transfer?.status!=='downloading')return t(transfer?.status==='indexing'?'indexingFasta':'unpackingFasta');
 const mib=bytes=>format(bytes/1048576,0);
 const progress=transfer.total_bytes>0?mib(transfer.received_bytes)+' / '+mib(transfer.total_bytes):mib(transfer.received_bytes);
 return t('downloadingFasta')+' · '+progress+' MiB';
}
function renderReferencePicker(scope){
 const form=referenceForm(scope),build=form.build,path=referencePath(scope);
 const options=referenceBuilds.map(([id])=>[id,assemblyLabel(id)]);
 const selector=select(t('referenceAssembly'),scope+'-reference-assembly',options,build,`data-reference-build="${scope}"`);
 let body;
 if(build==='file'){
  body=scope==='new'?fileField(t('reference'),'reference',path,'reference'):
   fileField(t('reference'),'igv-reference.fasta',path,'igv-reference')+fileField(t('fastaIndex'),'igv-reference.index',state.igv.reference.index,'fai');
 }else{
  const saved=referenceEntries.filter(e=>e.build===build),id=scope==='new'?state.draft.reference_id:null;
  const selected=saved.find(e=>e.fasta===path&&(!id||e.id===id));
  const notation={chr:'chr1',unprefixed:'1',accession:'NC_000001…'};
  const records=[['',t('selectReferenceFile')],...saved.map(e=>{
   const convention=notation[e.naming]?' ('+notation[e.naming]+')':'';
   return [e.id,e.label+convention+' · '+e.fasta+(e.available?'':' · '+t('referenceFileMissing'))];
  })];
  const original=path&&!selected;
  if(original)records.push(['original',basename(path)+' · '+path]);
  const local=saved.length||original?select(t('savedFasta'),scope+'-registered-fasta',records,selected?.id||(original?'original':''),`data-reference-entry="${scope}"`):'';
  const unavailable=original||selected&&!selected.available;
  const named=build!=='custom',ucsc=named?(build==='grch37'?'hg19':'hg38'):'';
  const transfer=referenceDownloads.get(build),active=activeTransfer(transfer);
  const downloadButton=named&&!active?button(t('downloadUCSC')+' '+ucsc,'reference-download',{scope,build},'small','download'):'';
  const details=named?`<p class="help">${esc(t('referenceCompatibility'))}</p>`:'';
  body=`<div class="reference-library">${local}
   ${unavailable?notice(t('savedReferenceUnavailable'),'warning'):''}
   <div class="actions">${button(t('registerFasta'),'reference-register',{scope,build},'small','archive')}${downloadButton}</div>
   ${details}${named&&!active?`<p class="help">${esc(t('ucscDownloadHelp'))}</p>`:''}
   ${active?`<div class="actions"><span role="status" id="${scope}-fasta-transfer">${esc(transferCaption(transfer))}</span>${button(t('cancel'),'reference-cancel',{scope,build},'quiet small','stop')}</div>`:''}
   ${transfer?.status==='failed'?notice(transfer.error||t('referenceDownloadFailed'),'error'):''}</div>`;
 }
 return `<div class="reference-chooser section-gap">${selector}<div class="${build==='file'?'form-row':'reference-files'}">${body}</div></div>`;
}
function activeReferenceSelection(scope,form,token){return state.view===scope&&referenceForm(scope)===form&&form.token===token}
async function selectReferenceEntry(scope,id,form=referenceForm(scope)){
 const token=++form.token;
 if(id==='original')return;
 setRegisteredReference(scope,null);render();
 if(!id)return;
 const {entry}=await rpc('references.resolve',{id,language:L.language});
 if(activeReferenceSelection(scope,form,token)&&entry?.build===form.build){setRegisteredReference(scope,entry);render()}
}
async function chooseReferenceBuild(scope,build){
 if(!referenceBuilds.some(([id])=>id===build))return;
 const form=referenceForm(scope);form.build=build;++form.token;
 setRegisteredReference(scope,null);render();
 if(build==='file')return;
 const local=referenceEntries.filter(e=>e.build===build&&e.available);
 // A family with several FASTA variants always requires an explicit file choice.
 if(local.length===1)await selectReferenceEntry(scope,local[0].id,form);
 if(build==='custom'||state.view!==scope||referenceForm(scope)!==form||form.build!==build)return;
 const token=form.token;
 const transfer=await rpc('references.download_status',{build});
 if(!activeReferenceSelection(scope,form,token))return;
 if(activeTransfer(transfer)){referenceDownloads.set(build,transfer);render()}
}
async function updateReferenceTransfer(build,result,scope){
 referenceDownloads.set(build,result);
 if(result.status==='ready'){
  await loadReferenceEntries();
 }
 if(state.view===scope)render();
}
async function referenceAction(name,{scope,build}){
 if(!['igv','new'].includes(scope)||state.view!==scope)return;
 const form=referenceForm(scope);
 if(form.build!==build||build==='file')return;
 const token=++form.token;
 if(name==='reference-register'){
  const result=await rpc('references.register',{build,language:L.language});
  if(!result.entry)return;
  await loadReferenceEntries();
  if(activeReferenceSelection(scope,form,token)){setRegisteredReference(scope,result.entry);render()}
  return;
 }
 if(build==='custom')return;
 const cancel=name==='reference-cancel';
 const result=await rpc(cancel?'references.download_cancel':'references.download',cancel?{build}:{build,language:L.language});
 if(!cancel&&activeTransfer(result))referenceReceivers.set(build,{scope,form,token});
 else referenceReceivers.delete(build);
 await updateReferenceTransfer(build,result,scope);
 if(!cancel&&result.status==='ready'&&result.entry&&activeReferenceSelection(scope,form,token)){setRegisteredReference(scope,result.entry);render()}
}
async function pollReferenceDownloads(){
 for(const [build,last] of referenceDownloads){
  if(!activeTransfer(last))continue;
  const next=await rpc('references.download_status',{build});
  if(referenceDownloads.get(build)!==last)continue;
  referenceDownloads.set(build,next);
  if(!activeTransfer(next)){
   const receiver=referenceReceivers.get(build);referenceReceivers.delete(build);
   if(next.status==='ready'){
    await loadReferenceEntries();
    if(receiver&&next.entry&&activeReferenceSelection(receiver.scope,receiver.form,receiver.token))setRegisteredReference(receiver.scope,next.entry);
   }
  }
  if(!['new','igv'].includes(state.view)||referenceForm(state.view).build!==build)continue;
  if(next.status!==last.status)render();
  else{const caption=$(state.view+'-fasta-transfer');if(caption)caption.textContent=transferCaption(next)}
 }
}

const statusPresentation = {
 running: ['in-progress','activity'], starting: ['in-progress','activity'], finalizing: ['in-progress','activity'],
 succeeded: ['success','check'], completed: ['success','check'],
 failed: ['error','close'], error: ['error','close'],
 cancel_requested: ['warning','stop'], cancelling: ['warning','stop'], cancelled: ['warning','stop'],
 canceled: ['warning','stop'], interrupted: ['warning','stop'], unknown: ['warning','info'],
 queued: ['neutral','activity'], pending: ['neutral','activity'], planned: ['neutral','activity']
};
function badge(status){
 const [kind, glyph]=Object.hasOwn(statusPresentation,status)?statusPresentation[status]:['neutral','info'];
 return `<span class="badge ${kind}">${icon(glyph)}${esc(t(status)||status)}</span>`;
}
function date(value){if(!value)return '—';const d=new Date(value);return Number.isNaN(d.getTime())?esc(value):esc(d.toLocaleString(L.language==='en'?'en-GB':'it-IT',{dateStyle:'short',timeStyle:'short'}))}
function toast(text){$('toast').textContent=text;$('toast').classList.add('visible');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').classList.remove('visible'),5000)}
function defaults(){return Object.fromEntries(Object.entries(state.settings).map(([m,w])=>[m,Object.fromEntries(Object.entries(w.parameters||{}).map(([k,p])=>[k,p.default]))]))}
function profileSettings(name){
 const saved=state.baseline||state.preferences||{}, profiles=saved.parameter_profiles||{};
 const source=name&&Object.hasOwn(profiles,name)?profiles[name]:saved;
 const scientific=defaults();
 for(const [module,values] of Object.entries(source.scientific_settings||{})){
  if(scientific[module])Object.assign(scientific[module],values);
 }
 const execution={input_hashes:'auto',execution_mode:'auto',cpus:null,memory_mb:null,pids_limit:null,max_workers:null,dnp_block_mib:32,dnp_block_loci:64,performance_diagnostics:false,...source.execution};
 return {scientific_settings:scientific,execution};
}
function blankDraft(profile=state.baseline?.default_profile||''){
 return {name:'',caller:'dnp',samples:[],branches:{DNP:[],SNP:[]},reference:null,resources:{DNP:{},SNP:{}},families:{cpi:[],cpin:[]},...profileSettings(profile)};
}

const archivePageSize=25;
function archiveRows(){
 const listing=state.archiveListing;
 if(!listing)return '<p class="panel-body" role="status">'+esc(t('loading'))+'</p>';
 if(listing.error)return notice(listing.error,'error')+button(t('retry'),'archive-page',{page:state.archivePage},'small');
 const {runs,total,archive_total,offset}=listing;
 if(!total)return empty(t(archive_total?'noFilteredRuns':'noRuns'),archive_total?'':t('noRunsCopy'));
 return runRows(runs)+`<div class="pager"><span>${format(offset+1,0)}–${format(offset+runs.length,0)} / ${format(total,0)}</span><div class="actions"><button class="button small" data-action="archive-page" data-page="${state.archivePage-1}" ${offset===0?'disabled':''}>${t('previous')}</button><button class="button small" data-action="archive-page" data-page="${state.archivePage+1}" ${offset+runs.length>=total?'disabled':''}>${t('next')}</button></div></div>`;
}
function updateArchiveRows(){
 const container=$('archive-results');
 if(container&&state.view==='archive'&&!state.run)container.innerHTML=archiveRows();
}
function normalizeDraft(value){const base=blankDraft(''),draft=clone(value.draft||value);return {...base,...draft,branches:{...base.branches,...draft.branches},resources:{DNP:{...base.resources.DNP,...draft.resources?.DNP},SNP:{...base.resources.SNP,...draft.resources?.SNP}},families:{...base.families,...draft.families},scientific_settings:Object.fromEntries(Object.entries(base.scientific_settings).map(([module,values])=>[module,{...values,...draft.scientific_settings?.[module]}])),execution:{...base.execution,...draft.execution}}}
function applyDraft(value){state.profileChoice='';++draftLoadVersion;state.draft=normalizeDraft(value);state.source=state.draft.caller==='tables'?'tables':state.draft.samples.some(sample=>sample.kind.endsWith('-table'))?'mixed':'bam';state.sampleKind=state.source==='tables'?(state.draft.samples.find(s=>s.kind.endsWith('-table'))?.kind||'dnp-table'):'bam';state.step=0;invalidate()}
function newExperiment(){applyDraft(blankDraft());state.profileChoice=state.baseline?.default_profile||'';closeModal();return navigate('new')}
function submittedDraft(){const draft=clone(state.draft),markers=activeMarkers();for(const marker of ['DNP','SNP'])if(!markers.includes(marker))draft.branches[marker]=[];const selected=markers.flatMap(marker=>draft.branches[marker]||[]);if(!draft.samples.some(sample=>sample.kind==='bam')){draft.reference=null;delete draft.reference_id;delete draft.reference_genome}for(const module of ['cpi','cpin'])if(!selected.includes(module))draft.families[module]=[];for(const marker of ['DNP','SNP']){const branch=draft.branches[marker],resources=draft.resources[marker];if(!callerRuns(marker)&&!branch.includes('contamination'))delete resources.panel;if(!branch.some(module=>module==='cpi'||module==='cpin'))delete resources.popfreq;if(!branch.includes('contamination'))delete resources.contamination_panel;if(!branch.includes('cpi'))delete resources.cpi_cutoffs;if(!branch.includes('cpin'))delete resources.cpin_panel;}return draft}
function activeMarkers(){const set=new Set(state.draft.caller==='both'?['DNP','SNP']:state.draft.caller==='tables'?[]:[state.draft.caller.toUpperCase()]);for(const s of state.draft.samples)if(s.kind==='dnp-table')set.add('DNP');else if(s.kind==='snp-table')set.add('SNP');return [...set]}
function callerRuns(marker){return state.draft.caller==='both'||state.draft.caller===marker.toLowerCase()}
function selectedModules(){return [...new Set([...(state.draft.caller==='tables'?[]:state.draft.caller==='both'?['dnp-call','snp-call']:[state.draft.caller+'-call']),...activeMarkers().flatMap(m=>state.draft.branches[m]||[])])]}
function invalidate(){++draftRevision;state.preview=null;state.error=''}
function setPath(key,value){const [root,a,b]=key.split('.');if(root==='reference'){state.draft.reference=value;delete state.draft.reference_id;delete state.draft.reference_genome}else if(root==='resource')state.draft.resources[a][b]=value;else if(root==='preference')state.preferences[a]=value;else if(root==='igv-reference'){++igvLoadVersion;state.igv.reference[a]=value;for(const field of ['index_sha256','fasta_sha256','gzi_sha256','historical_identity_incomplete','build'])delete state.igv.reference[field];referenceForm('igv').build='file';if(a==='fasta'){state.igv.reference.index='';delete state.igv.reference.compressedIndex}}else if(root==='igv-track'){state.igv.tracks[Number(a)][b]=value;if(b==='path')state.igv.tracks[Number(a)].index=''}else if(root==='cutoff')state.draft.resources[a].cpi_cutoffs[Number(b)].path=value;invalidate()}
async function choosePath(key,filter='all',multiple=false){
 const extensions={bam:['bam'],pileup:['txt','tsv','pileup'],table:['txt','tsv','csv'],reference:['fa','fasta','fna'],'igv-reference':['fa','fasta','fna','gz','bgz'],fai:['fai'],bai:['bai','csi'],crai:['crai'],tabix:['tbi','csi'],index:['fai','bai','crai','csi','tbi'],alignment:['bam','cram','vcf','bed','gff','gff3','gtf','bw','bigwig','bb','bigbed','wig','bedgraph','seg','gz','bgz'],all:['*']}[filter]||['*'];
 const draft=state.draft,revision=draftRevision,draftField=!!key&&/^(reference$|resource\.|cutoff\.)/.test(key);
 const igvForm=key?.startsWith('igv-reference.')?referenceForm('igv'):null,igvToken=igvForm?.token;
 const current=()=>(!draftField||draft===state.draft&&revision===draftRevision)&&(!igvForm||activeReferenceSelection('igv',igvForm,igvToken));
 try{
  const result=await rpc('dialog.open',{kind:filter==='directory'?'directory':'files',directory:filter==='directory',multiple,title:t('browse'),filters:[{name:t('selectedFile'),extensions}]});
  if(!current())return[];const paths=Array.isArray(result)?result:result?.paths||[];if(!paths.length)return[];if(key)setPath(key,paths[0]);return paths;
 }catch(error){if(current())throw error;return[]}
}
let archiveListVersion=0,archiveSearchTimer;
async function loadRuns(){
 const view=state.view;
 if(view!=='home'&&(view!=='archive'||state.run))return false;
 const version=++archiveListVersion;
 const current=()=>version===archiveListVersion&&state.view===view&&(view==='home'||!state.run);
 const params=view==='home'?{offset:0,limit:5}:{offset:state.archivePage*archivePageSize,limit:archivePageSize};
 if(view==='archive'){
  if(state.archiveSearch)params.query=state.archiveSearch;
  if(state.archiveStatus!=='all')params.status=state.archiveStatus;
  if(state.archiveMarker!=='all')params.marker=state.archiveMarker;
 }
 try{
  while(current()){
   const result=await rpc('runs.list',params);
   if(!current())return false;
   if(view==='home'){
    const changed=JSON.stringify(state.recentRuns)!==JSON.stringify(result.runs);
    state.recentRuns=result.runs;
    return changed;
   }
   // Removing records can make the last page disappear between requests.
   const lastOffset=Math.max(0,Math.ceil(result.total/archivePageSize)-1)*archivePageSize;
   if(params.offset>lastOffset){params.offset=lastOffset;continue}
   const changed=JSON.stringify(state.archiveListing)!==JSON.stringify(result);
   state.archivePage=params.offset/archivePageSize;
   state.archiveListing=result;
   return changed;
  }
 }catch(error){
  if(!current())return false;
  if(view==='archive'){state.archiveListing={error:humanError(error)};updateArchiveRows()}
  throw error;
 }
 return false;
}
async function refreshVisibleRuns(){
 if(await loadRuns()){
  if(state.view==='home')render();
  else updateArchiveRows();
 }
}
function requestArchivePage(page,debounce=false){
 clearTimeout(archiveSearchTimer);
 ++archiveListVersion;
 state.archivePage=page;
 state.archiveListing=null;
 updateArchiveRows();
 const refresh=()=>state.view==='archive'&&!state.run?refreshVisibleRuns():Promise.resolve();
 if(debounce){archiveSearchTimer=setTimeout(()=>refresh().catch(showError),200);return}
 return refresh();
}
function runRows(runs){if(!runs.length)return empty(t('noRuns'),t('noRunsCopy'),button(t('openFolder'),'import-run',{},'','archive'));return `<div class="table-scroll" tabindex="0"><table class="table"><thead><tr><th>${t('name')}</th><th>${t('date')}</th><th>${t('analysis')}</th><th>${t('status')}</th><th><span class="screen-reader-only">${t('open')}</span></th></tr></thead><tbody>${runs.map(r=>`<tr><td><b>${esc(r.name||r.id)}</b><small>${r.samples?.length||0} ${t(r.samples?.length===1?'sample':'samples').toLowerCase()} · ${esc((r.markers||[]).join(' / '))}</small></td><td>${date(r.started_at)}</td><td>${esc((r.modules||[r.workflow]).map(m=>moduleName(typeof m==='string'?m:m.module)).join(' · '))}</td><td>${badge(r.status)}</td><td><div class="actions">${button(t('openResults'),'open-run',{id:r.id},'small result-link','arrow')}${button(t('rerun'),'reuse-run',{id:r.id},'quiet small','play')}${r.can_remove===true?button(t('removeFromList'),'remove-run',{id:r.id},'quiet small','close'):''}</div></td></tr>`).join('')}</tbody></table></div>`}
function renderHome(){
 const parameterCount=Object.values(state.settings).reduce((n,group)=>n+Object.keys(group.parameters||{}).length,0);
 const constantCount=Object.values(state.settings).reduce((n,group)=>n+Object.keys(group.constants||{}).length,0);
 const tools=[['igv',t('igvHelp')],['catalog',`${parameterCount} ${t('parameters').toLowerCase()} · ${constantCount} ${t('constants').toLowerCase()}`]];
 return heading(t('welcome'),t('welcomeCopy'),button(t('new'),'navigate',{view:'new'},'primary','plus'))+`
  <section class="panel"><div class="panel-header"><h2>${t('recent')}</h2>${button(t('allExperiments'),'navigate',{view:'archive'},'quiet','arrow')}</div>${runRows(state.recentRuns)}</section>
  <div class="grid two-columns section-gap">${tools.map(([view,description])=>`<button class="home-card" data-action="navigate" data-view="${view}"><span class="icon-box">${icon(view)}</span><span><strong>${t(view)}</strong><small>${esc(description)}</small></span>${icon('arrow')}</button>`).join('')}</div>`;
}
function renderInputs(){const d=state.draft,markers=activeMarkers();return `<div class="section-title"><h2>${t('addSamples')}</h2></div><div class="form-row">${input(t('experimentName'),'experiment-name',d.name,'data-draft="name" maxlength="120" placeholder="'+esc(t('experimentPlaceholder'))+'"')}${select(t('startFrom'),'source',[['bam',t('rawInputs')],['tables',t('existingTables')],['mixed',t('mixedInputs')]],state.source,'data-field="source"')}</div>${state.source!=='tables'?`<fieldset class="choice-fieldset"><legend>${t('whichMarkers')}</legend><div class="choices">${[['dnp','onlyDnp','dnpDescription'],['snp','onlySnp','snpDescription'],['both','both','bothDescription']].map(([v,key,help])=>`<label class="choice ${d.caller===v?'selected':''}"><input type="radio" name="caller" value="${v}" data-draft="caller" ${d.caller===v?'checked':''}><span><b>${t(key)}</b><small>${t(help)}</small></span></label>`).join('')}</div></fieldset>`:''}<div class="toolbar">${select(t('sampleKind'),'sample-kind',(state.source==='tables'?[['dnp-table',t('dnpTable')],['snp-table',t('snpTable')]]:state.source==='bam'?[['bam',t('bam')],['snp-pileup',t('snpPileup')]]:[['bam',t('bam')],['snp-pileup',t('snpPileup')],['dnp-table',t('dnpTable')],['snp-table',t('snpTable')]]),state.sampleKind,'data-field="sampleKind"')}${button(t('addSamples'),'add-samples',{},'primary','plus')}</div><div class="table-scroll"><table class="table"><thead><tr><th>${t('sampleName')}</th><th>${t('sampleFile')}</th><th>${t('fileType')}</th><th></th></tr></thead><tbody>${d.samples.map((s,i)=>`<tr><td class="sample-name"><input class="input" value="${esc(s.id)}" data-sample="${i}" maxlength="48" aria-label="${t('sampleName')} ${i+1}"></td><td><b>${esc(basename(s.path))}</b><details class="file-name"><summary>${t('details')}</summary>${esc(s.path)}</details></td><td>${esc({bam:t('bam'),'snp-pileup':t('snpPileup'),'dnp-table':t('dnpTable'),'snp-table':t('snpTable')}[s.kind])}</td><td>${button(t('remove'),'remove-sample',{index:i},'quiet small','close')}</td></tr>`).join('')}</tbody></table>${!d.samples.length?empty(t('noSamples')):''}</div><p class="help section-gap">${t('sampleIdHelp')}</p>${d.samples.some(s=>s.kind==='bam')||state.source!=='tables'&&state.sampleKind==='bam'?`${renderReferencePicker('new')}<p class="help">${t('referenceHelp')}</p>`:''}${d.caller!=='tables'?`<div class="form-row">${(d.caller==='both'?['DNP','SNP']:[d.caller.toUpperCase()]).map(m=>fileField(t('panel')+' '+m,'resource.'+m+'.panel',d.resources[m].panel,'table')).join('')}</div>`:''}`}
function renderFamilies(module){const rows=state.draft.families[module],roles=module==='cpi'?['mother','father']:['mother','father','child'];const samples=[...new Set(state.draft.samples.map(s=>s.id))];return `<section class="section-gap"><div class="section-title"><h3>${moduleName(module)} · ${t('family')}</h3>${button(t('addFamily'),'add-family',{module},'small','plus')}</div><p class="help">${t('familyHelp')}</p>${rows.map((r,i)=>`<div class="family-row ${module==='cpi'?'pair':''}">${input(t('familyName'),`${module}-family-${i}`,r.id,`data-family="${module}|${i}|id" maxlength="48"`)}${roles.map(role=>select(t(role==='mother'&&module==='cpi'?'maternalCfdna':role),`${module}-${i}-${role}`,[['',t('assign')],...samples.map(s=>[s,s])],r[role]||'',`data-family="${module}|${i}|${role}"`)).join('')}${button(t('remove'),'remove-family',{module,index:i},'quiet small','close')}</div>`).join('')}</section>`}
function renderAnalyses(){const d=state.draft,markers=activeMarkers(),selected=selectedModules();return `<h2>${t('whichAnalyses')}</h2><p class="muted section-gap">${t(d.caller==='tables'?'tableAnalyses':'optionalAnalyses')}</p><div class="grid ${markers.length>1?'two-columns':''} section-gap">${markers.map(m=>`<section class="branch"><div class="branch-header"><b>${m}</b><span class="badge neutral">${t(callerRuns(m)?'genotypes':'existingTables')}</span></div><div class="branch-body">${['contamination','cpi','cpin'].map(mod=>`<label class="check-row"><input type="checkbox" data-branch="${m}|${mod}" ${d.branches[m].includes(mod)?'checked':''}><span><b>${moduleName(mod)}</b><p>${t(mod+'Help')}</p></span></label>`).join('')}</div></section>`).join('')}</div>${selected.includes('cpi')?renderFamilies('cpi'):''}${selected.includes('cpin')?renderFamilies('cpin'):''}<div class="form-row">${markers.filter(m=>d.branches[m].some(a=>a==='cpi'||a==='cpin')).map(m=>fileField(t('population')+' '+m,'resource.'+m+'.popfreq',d.resources[m].popfreq,'table')).join('')}</div>${selected.some(mod=>mod==='cpi'||mod==='cpin')?`<p class="help">${esc(t('frequencyTableHelp'))}</p>`:''}<details class="disclosure"><summary>${t('optionalPanels')}</summary><div class="details-body">${markers.map(m=>`<h3 class="section-gap">${m}</h3><div class="form-row">${d.branches[m].includes('contamination')?fileField(t('contaminationPanel'),'resource.'+m+'.contamination_panel',d.resources[m].contamination_panel,'table'):''}${d.branches[m].includes('cpin')?fileField(t('cpinPanel'),'resource.'+m+'.cpin_panel',d.resources[m].cpin_panel,'table'):''}</div>${d.branches[m].includes('cpi')?`<div class="section-title"><h3>${t('cpiPanels')}</h3>${button(t('addPanel'),'add-cutoff',{marker:m},'small','plus')}</div><p class="help">${t('allSitesHelp')}</p>${(d.resources[m].cpi_cutoffs||[]).map((c,i)=>`<div class="form-row">${input(t('name'),`cutoff-${m}-${i}`,c.label,`data-cutoff="${m}|${i}"`)}<div class="actions">${fileField(t('panel'),`cutoff.${m}.${i}`,c.path,'table')}${button(t('remove'),'remove-cutoff',{marker:m,index:i},'quiet small','close')}</div></div>`).join('')}`:''}`).join('')}</div></details>`}
function phase(key){if(['min_base_quality','min_mapping_quality','max_depth','mapping_quality_adjustment','baq','redo_baq','count_overlaps','include_orphans','excluded_flags'].includes(key))return 'phasePileup';if(['err_const_snp','err_const_dnp','min_fetal_reads','min_fetal_percent','mismatch_probability_snp','mismatch_probability_dnp','min_child_reads','include_zero'].includes(key))return 'phaseEstimate';if(key.startsWith('log_cpi_'))return 'phasePlot';return 'phaseSelection'}
function parameterVisible(m,key,all=false){if(all)return true;if(phase(key)==='phasePileup'&&!state.draft.samples.some(s=>s.kind==='bam'))return false;if(['err_const_snp','mismatch_probability_snp'].includes(key)&&!activeMarkers().includes('SNP'))return false;if(['err_const_dnp','mismatch_probability_dnp'].includes(key)&&!activeMarkers().includes('DNP'))return false;return true}
function range(def){
 if(def.choices)return def.choices.map(choiceLabel).join(' / ');
 const bounds=[];
 if(def.minimum!==undefined)bounds.push((def.exclusive_minimum?'> ':'≥ ')+def.minimum);
 if(def.maximum!==undefined)bounds.push('≤ '+def.maximum);
 return bounds.join(' · ')
}
function parameterUnit(unit){
 const labels={probabilita:['probabilità','probability'],proporzione:['proporzione','proportion'],letture:['letture','reads'],coefficiente:['coefficiente','coefficient'],'bitmask SAM':['flag SAM','SAM flags'],'log10(CPI)':['log₁₀(CPI)','log₁₀(CPI)']};
 return labels[unit]?.[L.language==='en'?1:0]||unit
}
function choiceLabel(v){return {all:t('allCompatible'),other_allele:t('heterozygous'),heterozygous:t('heterozygous'),both:t('bothSiteSelections'),all_compatible_sites:t('allCompatible'),heterozygous_child_sites:t('heterozygous')}[v]||v}
function displayValue(v){if(v==null)return t('unspecified');if(typeof v==='boolean')return t(v?'yes':'no');if(Array.isArray(v))return v.join(', ');if(typeof v==='object')return JSON.stringify(v);return String(v??'')}
function parameterRows(module,scope='draft',readonly=false,all=false){const w=state.settings[module],values=scope==='defaults'?(state.preferences.scientific_settings?.[module]||{}):state.draft.scientific_settings[module];const entries=Object.entries(w.parameters||{}).filter(([key,def])=>parameterVisible(module,key,all)&&(state.view!=='catalog'||[L.field(key),L.description(key,def),t(phase(key))].join(' ').toLowerCase().includes(state.catalogSearch.toLowerCase())));const groups=[...new Set(entries.map(([k])=>phase(k)))];return groups.map(group=>`<section class="parameter-group"><h3>${t(group)}</h3>${entries.filter(([k])=>phase(k)===group).map(([key,def])=>{const value=values?.[key]??def.default;const attrs=`data-parameter="${module}|${key}|${scope}"`;return `<div class="parameter-row"><div><h3>${esc(L.field(key))}</h3><p>${esc(L.description(key,def))}</p><dl class="parameter-meta">${[[t('defaultValue'),key==='excluded_flags'?archivedFlagNames(def.default):def.choices?choiceLabel(def.default):displayValue(def.default)],[t('allowed'),range(def)],[t('unit'),parameterUnit(def.unit)]].filter(([,v])=>v!==null&&v!==undefined&&v!=='').map(([k,v])=>`<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl></div><div class="parameter-value">${readonly?`<b>${esc(key==='excluded_flags'?archivedFlagNames(value):def.choices?choiceLabel(value):displayValue(value))}</b>`:def.type==='boolean'?`<label class="check-row"><input type="checkbox" ${attrs} ${value?'checked':''}><span>${t('enabled')}</span></label>`:def.choices?`<select class="input" ${attrs} aria-label="${esc(L.field(key))}">${def.choices.map(v=>`<option value="${esc(v)}" ${v===value?'selected':''}>${esc(choiceLabel(v))}</option>`).join('')}</select>`:`<input class="input" type="number" ${attrs} value="${esc(value)}" ${def.minimum!==undefined?`min="${def.minimum}"`:''} ${def.maximum!==undefined?`max="${def.maximum}"`:''} ${def.nullable?`placeholder="${esc(t('unspecified'))}"`:''} step="${def.type==='integer'?'1':'any'}" aria-label="${esc(L.field(key))}">`}${!readonly?button(t('reset'),'reset-param',{module,key,scope},'quiet small'):''}</div></div>${key==='excluded_flags'&&!readonly?flagsEditor(module,value,scope):''}`}).join('')}</section>`).join('')}
function flagsEditor(module,value,scope){const flags=[[4,'Non allineate','Unmapped'],[8,'Compagno non allineato','Unmapped mate'],[256,'Allineamenti secondari','Secondary alignments'],[512,'Controllo qualità non superato','Failed quality control'],[1024,'Duplicati','Duplicates'],[2048,'Allineamenti supplementari','Supplementary alignments']];return `<details class="disclosure"><summary>${L.field('excluded_flags')}</summary><div class="details-body flags">${flags.map(([bit,it,en])=>`<label><input type="checkbox" data-flag="${module}|${bit}|${scope}" ${(Number(value)&bit)?'checked':''}>${esc(L.language==='en'?en:it)}</label>`).join('')}</div></details>`}
function executionFields(execution,scope='draft'){return `<p class="help">${t('executionHelp')}</p><div class="execution-grid section-gap">${select(t('mode'),scope+'-execution-mode',[['auto',t('automatic')],['serial',t('serial')]],execution.execution_mode||'auto',`data-execution="execution_mode|${scope}"`)}${[['max_workers','maxWorkers',1,1024],['cpus','cpuLimit',.1,1024],['memory_mb','memoryLimit',128,1048576],['pids_limit','processLimit',16,1048576],['dnp_block_mib','blockSize',1,4096],['dnp_block_loci','blockLoci',1,1000000]].filter(([key])=>scope!=='draft'||!key.startsWith('dnp_block_')||callerRuns('DNP')).map(([k,label,min,max])=>input(t(label),scope+'-'+k,execution[k]??'',`type="number" min="${min}" max="${max}" step="${k==='cpus'?'any':'1'}" data-execution="${k}|${scope}" placeholder="${t('automatic')}"`)).join('')}${select(t('hashes'),scope+'-input-hashes',[['auto',t('automatic')],['full',t('fullHashes')]],execution.input_hashes||'auto',`data-execution="input_hashes|${scope}"`)}</div>${scope==='draft'?`<label class="check-row section-gap"><input type="checkbox" data-execution="performance_diagnostics|${scope}" ${execution.performance_diagnostics?'checked':''}><span>${t('diagnostics')}</span></label>`:''}`}
function profileOptions(preferences){
 const names=Object.keys(preferences?.parameter_profiles||{}).sort((a,b)=>a.localeCompare(b,L.language));
 return [['',t('personalDefaults')],...names.map(name=>[name,name])];
}
function renderProfilePicker(){
 const selected=state.profileChoice||'';
 return `<div class="section-gap">${select(t('parameterProfile'),'parameter-profile',profileOptions(state.baseline),selected,'data-field="profileChoice"')}<p class="help">${t('profileScope')}</p><div class="actions">${button(t('applyProfile'),'apply-profile')}${button(t('saveAsProfile'),'new-profile',{},'','plus')}${selected?button(t('removeProfile'),'remove-profile',{name:selected},'quiet'):''}</div></div>`;
}
function renderParameters(){return `<h2>${t('parameters')}</h2>${renderProfilePicker()}${selectedModules().map(m=>`<details class="disclosure" open><summary>${moduleName(m)}</summary><div class="details-body">${m==='cpin'?`<p class="help">${t('postnatalSelectionHelp')}</p>`:''}${parameterRows(m)}</div></details>`).join('')}<details class="disclosure"><summary>${t('execution')}</summary><div class="details-body">${executionFields(state.draft.execution)}</div></details>`}
function renderReview(){const d=state.draft,processed=state.preview?.samples,labels=processed?[...new Set(processed.map(sample=>sample.biological_id||sample.id||sample.sample_id))]:d.samples.map(sample=>sample.id),branches=state.preview?.analyses_by_marker||d.branches;return `<h2>${t('review')}</h2>${demoRevision===draftRevision?demoExpectedResults():''}${state.jobs.some(job=>!terminal(job))?notice(t('concurrentWarning'),'warning'):''}<div class="review-block"><dl class="review-list"><dt>${t('experimentName')}</dt><dd>${esc(d.name)}</dd><dt>${t('samples')}</dt><dd>${labels.map(esc).join(', ')||t('emptyValue')}</dd><dt>${t('markers')}</dt><dd>${activeMarkers().join(' / ')}</dd>${d.reference&&d.samples.some(s=>s.kind==='bam')?`<dt>${t('reference')}</dt><dd class="path">${esc(d.reference_id?assemblyLabel((state.preview?.reference_genome||d.reference_genome)?.build||referenceForm('new').build)+' · ':'')}${esc(d.reference)}</dd>`:''}</dl></div><div class="review-block"><h3>${t('expectedResults')}</h3>${activeMarkers().map(marker=>{const analyses=[...(callerRuns(marker)?[t('genotypes')]:[]),...(branches[marker]||[]).map(moduleName)];return `<p><b>${marker}</b> · ${analyses.length?analyses.join(' · '):(L.language==='it'?'Nessuna analisi selezionata: queste tabelle non saranno elaborate.':'No analysis selected: these tables will not be processed.')}</p>`}).join('')}</div><div class="review-block"><h3>${t('resultLocation')}</h3><p>${t('archive')} → ${esc(d.name)} → ${t('results')}</p></div>${state.preview?`<div class="section-gap">${notice(t('validated'))}<ol class="plan-list">${state.preview.steps.map(step=>`<li>${esc(moduleName(step.workflow||step.module))}${step.parameters?.marker_type?' · '+esc(step.parameters.marker_type):''}${step.inputs?.sample?' · '+esc(step.inputs.sample):''}</li>`).join('')}</ol></div>`:`<p class="help section-gap">${t('startChecksHelp')}</p>`}<div class="actions section-gap">${startingDraft===d?`<span class="start-check" role="status"><span aria-hidden="true" class="check-spinner ${state.motion?'':'paused'}"></span>${t('checkingPlan')}</span>`:button(t('showPlan'),'validate-plan',{},'quiet small')}</div>`}
function renderNew(){const d=state.draft;return heading(t('new'),t('newCopy'))+`${state.error?notice(state.error,'error'):''}<div class="form-layout section-gap"><section class="panel"><div class="steps" role="tablist">${['samples','analysis','parameters','review'].map((key,i)=>`<button class="step ${state.step===i?'active':''}" data-action="step" data-index="${i}" role="tab" aria-selected="${state.step===i}"><span>${i+1}</span>${t(key)}</button>`).join('')}</div><div class="panel-body">${[renderInputs,renderAnalyses,renderParameters,renderReview][state.step]()}</div><div class="form-footer"><span class="help">${state.step+1} / 4</span><div class="actions">${state.step?button(t('back'),'step',{index:state.step-1},'','back'):''}${state.step<3?button(t('continue'),'step',{index:state.step+1},'primary','arrow'):`<button class="button primary" data-action="start-analysis" ${startingDraft?'disabled aria-busy="true"':''}>${icon('play')}${t('startAnalysis')}</button>`}</div></div></section><aside class="side-summary"><h3>${t('review')}</h3><dl><div><dt>${t('name')}</dt><dd>${esc(d.name)||'—'}</dd></div><div><dt>${t('samples')}</dt><dd>${d.samples.length}</dd></div><div><dt>${t('markers')}</dt><dd>${activeMarkers().join(' / ')||'—'}</dd></div><div><dt>${t('expectedResults')}</dt><dd>${selectedModules().map(moduleName).map(esc).join(', ')||'—'}</dd></div></dl></aside></div>`}
function renderArchive(){if(state.run)return renderRun();return heading(t('archive'),t('archiveCopy'),button(t('openFolder'),'import-run',{},'','archive')+button(t('new'),'navigate',{view:'new'},'primary','plus'))+`<section class="panel"><div class="panel-body"><div class="toolbar"><input class="input stretch" id="archive-search" maxlength="1000" placeholder="${t('archiveSearch')}" aria-label="${t('search')}" value="${esc(state.archiveSearch)}" data-search="archive">${select(t('status'),'archive-status',[['all',t('all')],['succeeded',t('succeeded')],['failed',t('failed')],['running',t('running')],['interrupted',t('interrupted')],['unknown',t('unknown')]],state.archiveStatus,'data-field="archiveStatus"')}${select(t('markers'),'archive-marker',[['all',t('all')],['DNP','DNP'],['SNP','SNP']],state.archiveMarker,'data-field="archiveMarker"')}</div></div><div id="archive-results">${archiveRows()}</div></section>`}
function jobProgress(job){const p=job.progress;if(p&&Number.isFinite(p.completed)&&Number.isFinite(p.total)&&p.total>0)return Math.max(0,Math.min(100,p.completed/p.total*100));if(typeof p==='number')return Math.max(0,Math.min(100,p));if(p&&typeof p==='object'){const value=p.percent??p.percentage??p.overall_percent;if(Number.isFinite(Number(value)))return Math.max(0,Math.min(100,Number(value)))}return null}
function terminal(job){return ['succeeded','completed','failed','cancelled','canceled','interrupted','planned'].includes(job.status)}
function jobDisplayStatus(job){
 if(job.status==='running'&&job.progress?.phase==='waiting-for-resources')return 'queued';
 return job.status;
}
function activityIndicator(jobs){
 const active=jobs.filter(job=>!terminal(job));
 const waiting=active.filter(job=>jobDisplayStatus(job)==='queued').length;
 return [[active.length-waiting,'running'],[waiting,'queued']].filter(([n])=>n).map(([n,key])=>n+' · '+t(key)).join(' / ');
}
function progressLabel(p, withSamples=true){if(!p)return '';const phases={'waiting-for-resources':['In attesa di CPU e memoria disponibili','Waiting for available CPU and memory'],'preparing-runtime':['Avvio dell’ambiente di calcolo','Starting the computation environment'],'verifying-engine':['Verifica del motore di analisi','Checking the analysis engine'],'checking-inputs':['Verifica degli input','Checking inputs'],'preparation':['Preparazione degli input','Preparing inputs'],'plan-preflight':['Verifica del piano','Checking plan'],'presentation-preparation':['Preparazione dei risultati','Preparing results'],'r-execution':['Calcolo R','R computation'],'output-validation':['Controllo dei risultati','Checking outputs'],'presentation-finalization':['Esportazione dei risultati','Exporting results'],'plan-presentation':['Riepilogo delle analisi','Analysis summary'],'pileup':['Preparazione del pileup','Preparing pileup'],'pileup-index':['Indicizzazione del pileup','Indexing pileup'],'pileup-reading':['Lettura del pileup','Reading pileup'],'dnp-processing':['Calcolo DNP','DNP computation'],'plots':['Creazione dei grafici','Creating plots'],'dnp-indexed-selection':['Selezione delle letture','Selecting reads'],'dnp-indexed-pileup':['Pileup dalle regioni indicizzate','Pileup from indexed regions'],'dnp-pileup':['Preparazione pileup DNP','Preparing DNP pileup']};const phase=phases[p.phase]?.[L.language==='en'?1:0]||p.phase||t('progressUnknown');return [p.workflow?moduleName(p.workflow):'',phase,...(withSamples?p.sample_ids||[]:[])].filter(Boolean).join(' · ')}
function elapsedTime(job){
 const started=Date.parse(job.created_at||job.started_at||''),finished=job.finished_at?Date.parse(job.finished_at):Date.now();
 if(!Number.isFinite(started)||!Number.isFinite(finished))return '';
 const seconds=Math.max(0,Math.floor((finished-started)/1000)),minutes=Math.floor(seconds/60),hours=Math.floor(minutes/60);
 return t('elapsed')+': '+(hours?hours+' h ':'')+(minutes?minutes%60+' min ':'')+seconds%60+' s';
}
function progressText(job){const p=jobProgress(job);return p===null?t('progressUnknown'):format(p,1)+' % · '+t('currentPhase')}
function phaseTitle(job){
 if(job.status==='queued'&&!job.progress?.phase)return t('waitingToPrepare');
 const label=progressLabel(job.progress,false);
 return label||job.message||(terminal(job)?t(job.status):t('preparingAnalysis'));
}
function sampleLabel(job){
 const current=job.progress?.sample_ids||[];
 if(current.length)return current.join(', ');
 if(job.only_sample)return job.only_sample;
 return job.sample_count?t('samplesInExperiment')+' · '+format(job.sample_count,0):'—';
}
function eventsMarkup(job){
 const events=job.events||[];
 return events.map(event=>{
  const time=new Date(event.at);
  const label=Number.isNaN(time.getTime())?'':time.toLocaleTimeString(L.language==='en'?'en-GB':'it-IT');
  return `<li><time datetime="${esc(event.at)}">${esc(label)}</time> ${esc(progressLabel(event.progress))}</li>`;
 }).join('');
}
function logText(entry){return entry.error||entry.lines.join('\n')||(entry.revision===null?t('loading'):t('noLogEntries'))}
async function refreshJobLog(job){
 const entry=visibleLogs.get(job.id);
 if(!entry||entry.busy||entry.revision===job.log_revision)return;
 entry.busy=true;
 try{
  const result=await rpc('jobs.logs',{job_id:job.id,after:entry.revision??0});
  if(visibleLogs.get(job.id)!==entry)return;
  entry.lines=(result.reset?result.lines:entry.lines.concat(result.lines)).slice(-result.limit);
  entry.revision=result.revision;entry.error='';
 }catch(error){entry.error=humanError(error)}
 finally{
  entry.busy=false;
  if(state.view==='activity'&&visibleLogs.get(job.id)===entry){
   const el=$('job-log-'+job.id);
   if(el){const atEnd=el.scrollHeight-el.scrollTop-el.clientHeight<20;el.textContent=logText(entry);if(atEnd)el.scrollTop=el.scrollHeight}
  }
 }
}
function dnaLoader(){return `<div class="dna-loader helix ${state.motion?'':'paused'}" aria-hidden="true">${Array.from({length:10},(_,i)=>`<span class="dna-rung" style="--rung:${i}"></span>`).join('')}</div>`}
function renderJobCard(job){
  const status=jobDisplayStatus(job),waiting=status==='queued';
  const p=jobProgress(job),indeterminate=p===null&&!terminal(job);
  const log=visibleLogs.get(job.id);
  return `<section class="panel section-gap" data-job-card="${esc(job.id)}" data-job-status="${esc(status)}" data-job-run="${esc(job.run_id||'')}"><div class="progress-card">
   <div class="job-header"><h2>${esc(job.name||job.run_name||job.id)}</h2>${badge(status)}</div>
   <dl class="job-facts"><div><dt>${t(terminal(job)?'lastPhase':'activityPhase')}</dt><dd data-job-phase>${esc(phaseTitle(job))}</dd></div><div><dt>${t('samples')}</dt><dd data-job-sample>${esc(sampleLabel(job))}</dd></div></dl>
   ${!waiting&&!terminal(job)?`<div class="job-progress">${dnaLoader()}<div><span data-job-progress-text>${progressText(job)}</span><p class="help" data-job-elapsed>${esc(elapsedTime(job))}</p></div></div>`:`<p class="help" data-job-elapsed>${esc(elapsedTime(job))}</p>`}
   ${waiting?'':`<div class="progress-track ${indeterminate?'indeterminate':''} ${state.motion?'':'paused'}" role="progressbar" aria-label="${esc(t('currentPhase'))}" aria-valuemin="0" aria-valuemax="100" ${p===null?'':`aria-valuenow="${p}"`}><span ${indeterminate?'':`style="width:${p??(job.status==='succeeded'?100:0)}%"`}></span></div>`}
   ${job.error?notice(humanError(job.error.message||job.error),job.status==='interrupted'?'warning':'error'):''}
   <section class="job-events" ${job.events?.length?'':'hidden'}><h3>${t('recentActivity')}</h3><ol data-event-revision="${job.event_revision??0}">${eventsMarkup(job)}</ol></section>
   <div class="actions section-gap">${terminal(job)?button(t('removeFromList'),'remove-job',{id:job.id},'quiet small','close'):['finalizing','cancel_requested'].includes(job.status)?'':button(t('stopAnalysis'),'cancel-job',{id:job.id},'danger','stop')}${job.run_id?button(t('openResults'),'open-run',{id:job.run_id,job:job.id},'primary','arrow'):''}
    <button class="button quiet small" data-action="job-log" data-id="${esc(job.id)}" aria-expanded="${!!log}" aria-controls="job-log-${esc(job.id)}">${t('technicalLog')}</button>
   </div><pre id="job-log-${esc(job.id)}" class="job-log" ${log?'':'hidden'}>${log?esc(logText(log)):''}</pre></div></section>`;
}
function renderActivity(){
 const active=state.jobs.filter(job=>!terminal(job)&&jobDisplayStatus(job)!=='queued');
 const waiting=state.jobs.filter(job=>jobDisplayStatus(job)==='queued'),finished=state.jobs.filter(terminal);
 const actions=button(t('reload'),'refresh-jobs',{},'','activity')+button(t('new'),'navigate',{view:'new'},'primary','plus');
 return heading(t('activity'),t('jobHelp'),actions)+(active.length?`<section><h2>${t('activeExperiments')}</h2>${active.map(renderJobCard).join('')}</section>`:'')
  +(waiting.length?`<section class="section-gap"><h2>${t('waitingExperiments')}</h2>${waiting.map(renderJobCard).join('')}</section>`:'')
  +(!active.length&&!waiting.length&&!finished.length?empty(t('noJobs')):'')
  +(finished.length?`<section class="section-gap"><h2>${t('finishedJobs')}</h2>${finished.map(renderJobCard).join('')}</section>`:'');
}
function updateActivity(){
 // Update the existing cards so DNA and indeterminate animations are not restarted by polling.
 const cards=[...document.querySelectorAll('[data-job-card]')];
 const byId=new Map(state.jobs.map(job=>[job.id,job]));
 if(cards.length!==byId.size||cards.some(card=>{const job=byId.get(card.dataset.jobCard);return !job||card.dataset.jobStatus!==jobDisplayStatus(job)||card.dataset.jobRun!==(job.run_id||'')}))return false;
 cards.forEach(card=>{
  const job=byId.get(card.dataset.jobCard),p=jobProgress(job),unknown=p===null&&!terminal(job);
  card.querySelector('[data-job-phase]').textContent=phaseTitle(job);
  card.querySelector('[data-job-sample]').textContent=sampleLabel(job);
  const events=card.querySelector('[data-event-revision]');
  if(events.dataset.eventRevision!==String(job.event_revision??0)){
   events.innerHTML=eventsMarkup(job);events.dataset.eventRevision=String(job.event_revision??0);
   card.querySelector('.job-events').hidden=!job.events?.length;
  }
  const label=card.querySelector('[data-job-progress-text]');if(label)label.textContent=progressText(job);
  card.querySelector('[data-job-elapsed]').textContent=elapsedTime(job);
  const track=card.querySelector('.progress-track');
  if(!track)return;
  const bar=track.querySelector('span');
  track.classList.toggle('indeterminate',unknown);track.classList.toggle('paused',!state.motion);
  if(p===null)track.removeAttribute('aria-valuenow');else track.setAttribute('aria-valuenow',String(p));
  if(unknown)bar.style.removeProperty('width');else bar.style.width=(p??(job.status==='succeeded'?100:0))+'%';
  const dna=card.querySelector('.dna-loader');if(dna)dna.classList.toggle('paused',!state.motion);

 });
 return true;
}
function currentGroup(){return (state.overview?.modules||[]).find(g=>g.module+'|'+g.marker===state.module)}
function currentEntry(){return currentGroup()?.entries?.[state.entry]}
function entryLabel(entry){return (entry.label||entry.sample_label||entry.family_id||t('summary'))+(entry.analysis?' · '+choiceLabel(entry.analysis):'')+(entry.cutoff?' · '+entry.cutoff:'')}
function metricValue(metric){if(metric.available===false||absent(metric.value))return t('notAvailable');const n=number(metric.value);if(n===null)return esc(metric.value);const v=n*(metric.scale??1);const value=v!==0&&(Math.abs(v)<.00001||Math.abs(v)>=1e7)?v.toExponential(5).replace('.',L.language==='it'?',':'.'):format(v,6);return value+(metric.unit==='%'?' %':['percentage_points','punti %','percentage points'].includes(metric.unit)?(L.language==='it'?' punti %':' percentage points'):'')}
const genotypeLabels={'0/0':'homozygousReference','0/1':'heterozygousCall','1/1':'homozygousAlternate'};
function genotypeCell(value,expanded){
 const label=t(genotypeLabels[value]);
 return `<span class="locus-genotype" title="${esc(label)}">${esc(value)}</span>${expanded?' '+esc(label):''}`;
}
function resultCell(value,column,expanded=false){if(absent(value))return `<span class="muted">${t('notAvailable')}</span>`;const key=column.key;if((key==='GT'||key.startsWith('GT_'))&&Object.hasOwn(genotypeLabels,value))return genotypeCell(value,expanded);if(/^(chr|chrom|chromosome|pos|pos1|pos2|start|end|id|sample_id|family_id)$/i.test(key))return esc(value);if(column.values&&column.values[value])return esc(column.values[value]);if(value==='TRUE'||value==='FALSE')return t(value==='TRUE'?'yes':'no');if(key==='Analysis')return esc(choiceLabel(value));if(key==='Status'){const names={eligible:['Ammissibile','Eligible'],mother_child_incompatible:['Incompatibilità madre–figlio','Mother–child incompatibility'],mother_not_homozygous:['Madre non omozigote','Mother not homozygous'],insufficient_child_support:['Letture del figlio insufficienti','Insufficient child reads'],quality_filter:['Filtro di qualità non superato','Quality filter not passed'],father_unassigned:['Genotipo paterno non assegnato','Father genotype unassigned']};return esc(names[value]?.[L.language==='en'?1:0]||value)}if(number(value)!==null){const n=Number(value)*(column.scale??1);const display=n!==0&&(Math.abs(n)<.00001||Math.abs(n)>=1e7)?n.toExponential(5).replace('.',L.language==='it'?',':'.'):format(n,6);return `<span title="${esc(t('originalValue')+': '+value)}">${esc(display)}${column.unit==='%'?' %':['percentage_points','punti %','percentage points'].includes(column.unit)?(L.language==='it'?' punti %':' percentage points'):''}</span>`}return esc(value)}
function metrics(entries){return `<div class="metrics">${entries.map(m=>{const v=metricValue(m);return `<div class="metric"><span>${esc(m.label)}</span><strong class="${v.length>18?'long':''}" title="${esc(absent(m.raw_value)?m.value??'':m.raw_value)}">${v}</strong>${m.description?`<small>${esc(m.description)}</small>`:''}</div>`}).join('')}</div>`}
function genotypeBars(entry){const counts=entry.genotype_counts;if(!counts)return '';const max=Math.max(1,...Object.values(counts));return `<section class="section-gap"><h3>${t('genotypeDistribution')}</h3><div class="genotype-bars">${['0/0','0/1','1/1','unassigned'].map(key=>`<div><span>${key==='unassigned'?t('unassigned'):key}</span><div class="bar-track"><span style="width:${(counts[key]||0)/max*100}%"></span></div><b>${format(counts[key]||0,0)}</b></div>`).join('')}</div></section>`}
function resultHelp(){return `<details class="disclosure"><summary>${t('resultHelpTitle')}</summary><div class="details-body"><p>${t('resultHelp')}</p></div></details>`}
const outcomeKeys={genotypes:'assigned',prenatal_cpi:'CPI_medianFF',postnatal_cpi:'CPI',contamination:'mean_contamination'};
const bandLabels={below:'bandBelow',at_lower:'bandLower',between:'bandBetween',at_upper:'bandUpper',above:'bandAbove'};
function outcomeValue(summary,metric){
 if(!metric?.available||absent(metric.value))return t('notAvailable');
 if(summary.kind==='prenatal_cpi'&&metric.key==='CPI_medianFF'||
    summary.kind==='postnatal_cpi'&&['CPI','Log10_CPI'].includes(metric.key)){
  let recorded=String(metric.value);
  if(summary.kind==='prenatal_cpi'&&/^[+-]?\d+(?:\.\d+)?$/.test(recorded)){
   const [integer,fraction='']=recorded.split('.');
   recorded=integer+'.'+fraction.padEnd(3,'0');
  }
  return esc(L.language==='it'?recorded.replace('.',','):recorded);
 }
 return metricValue(metric);
}
function outcomePanel(entry,compact=false){
 const summary=entry.summary;
 if(!summary||!Object.hasOwn(outcomeKeys,summary.kind))return '';
 const values=summary.metrics||[],primaryKey=outcomeKeys[summary.kind];
 const primary=values.find(item=>item.key===primaryKey);
 const metric=primary?.available===false&&summary.kind==='postnatal_cpi'?values.find(item=>item.key==='Log10_CPI'&&item.available)||primary:primary;
 if(!metric)return '';
 const complete=summary.step_status==='succeeded';
 const band=summary.guide_band;
 const bandKey=complete&&band&&Object.hasOwn(bandLabels,band.position)?bandLabels[band.position]:null;
 const total=summary.kind==='genotypes'&&values.find(item=>item.key==='site_count');
 const value=complete?outcomeValue(summary,metric):t('outcomeIncomplete');
 const sites=complete&&metric.available&&total?.available?' / '+metricValue(total):'';
 const label=summary.kind==='genotypes'?t('sitesWithGenotype'):metric.label;
 const outcome=`<span class="outcome-label"${metric.description?` title="${esc(metric.description)}"`: ''}>${esc(label)}</span><strong data-outcome-value>${value}${sites}</strong>`;
 if(compact)return `<div class="outcome-preview" data-outcome="${summary.kind}"><b>${esc(entryLabel(entry))}</b><span class="outcome-label">${esc(label)}</span><strong>${value}${sites}</strong>${bandKey?`<small>${t(summary.kind==='postnatal_cpi'?'logReferenceBand':'plotBand')} · ${t(bandKey)}</small>`:''}</div>`;
 const interval=bandKey?(summary.kind==='postnatal_cpi'? `[${esc(band.lower)}, ${esc(band.upper)}]` : `(${esc(band.lower)}, ${esc(band.upper)})`):'';
 const guideText=bandKey?`<div class="outcome-band" data-band="${esc(band.position)}"><span class="guide-scale" aria-hidden="true"><i></i><i></i><i></i></span><span><b>${t(summary.kind==='postnatal_cpi'?'logReferenceBand':'plotBand')}</b> · ${t(bandKey)} ${interval}</span></div>`:'';
 const guideNote=summary.kind==='prenatal_cpi'&&bandKey&&['at_lower','at_upper'].includes(band.position)?`<p class="help">${t('roundedBoundary')}</p>`:'';
 const secondary=values.filter(item=>item.key!==metric.key&&item.key!=='site_count'&&
     !(summary.kind==='genotypes'&&['hom_ref','heterozygous','hom_alt'].includes(item.key)));
 if(summary.kind==='genotypes'){
  const reads=entry.metrics?.find(item=>item.key==='read_observations');
  if(reads)secondary.push(reads);
 }
 return `<section class="outcome-panel" data-outcome="${summary.kind}" aria-label="${t('resultOverview')}">
  <div class="outcome-main">${outcome}</div>${guideText}${guideNote}
  ${complete&&secondary.length?`<dl class="outcome-support">${secondary.map(item=>`<div><dt>${esc(item.label)}</dt><dd>${outcomeValue(summary,item)}</dd></div>`).join('')}</dl>`:''}
 </section>`;
}
function reportButton(){return button(t('exportReport'),'choose-report',{},'','file')}
function renderResultsSummary(){
 const groups=state.overview?.modules||[];
 const cards=groups.map(group=>{
  const available=group.entries?.length||(group.files||[]).some(file=>['table','pdf'].includes(file.kind));
  const title=moduleName(group.module)+(group.module.endsWith('-call')?'':' · '+group.marker);
  const status=group.status==='pending'?(L.language==='it'?'In attesa':'Pending'):t(group.status||'planned');
  const entries=group.entries||[], previews=entries.slice(0,3).map(entry=>outcomePanel(entry,true)).join('');
  return `<article class="module-card"><div><h3>${esc(title)}</h3><p>${esc(status)}</p></div><div>${previews?'':`<span class="help">${t(available?'available':'noResults')}</span>`}${button(t(available?'openResults':'details'),'result-module',{module:group.module+'|'+group.marker},'primary small','arrow')}</div>${previews?`<div class="outcome-previews">${previews}${entries.length>3||group.summary_truncated?`<small>${t('moreResultsInModule')}</small>`:''}</div>`:''}</article>`;
 }).join('');
 const missing=Object.keys(state.settings).filter(module=>!groups.some(group=>group.module===module));
 const additional=missing.map(module=>`<div class="section-title"><h3>${esc(moduleName(module))}</h3>${button(t('prepareAnalysis'),'prepare-module',{module},'small','plus')}</div>`).join('');
 return `<div class="section-title"><h2>${t('results')}</h2><div class="actions">${groups.some(group=>group.entries?.length)?reportButton():''}${button(t('downloadAll'),'export-run',{},'','download')}</div></div>${cards?`<div class="module-grid">${cards}</div>`:empty(t('noResults'))}${additional?`<details class="disclosure"><summary>${t('notRun')}</summary><div class="details-body">${additional}</div></details>`:''}${resultHelp()}`;
}
function shownColumns(table,all=false){if(all)return table.columns;const preferred=['chr','pos','pos1','pos2','REF','ALT','GT','N_REF','N_ALT','N_Other','contamination','Status','Paternity_Index','Mismatch','Child_support','GT_child','Genotype_combination','Paternity_status','CPI','Log10_CPI','log_CPI','Iteration','Min_child_reads','Through_min_child_reads','N_sites','Matching_sites','Mismatching_sites'];const selected=table.columns.filter(c=>preferred.includes(c.key));return selected.length?selected:table.columns.slice(0,8)}
function rowLocus(row){
 const keys=Object.fromEntries(Object.keys(row||{}).map(key=>[key.toLowerCase(),key]));
 const chromosome=row?.[keys.chr||keys.chrom||keys.chromosome],position=row?.[keys.pos||keys.pos1];
 if(chromosome===undefined||position===undefined||!/^[A-Za-z0-9_.-]+$/.test(String(chromosome))||!/^\d+$/.test(String(position)))return null;
 const start=Number(position),last=keys.pos2&&/^\d+$/.test(String(row[keys.pos2]))?Number(row[keys.pos2]):start;
 if(!Number.isSafeInteger(start)||!Number.isSafeInteger(last)||start<1||last<start)return null;
 return String(chromosome)+':'+start+'-'+last;
}
function tableView(table,{compact=false,all=state.allColumns}={}){if(!table)return empty(t('noResults'));const columns=shownColumns(table,all);return `<div class="table-scroll" tabindex="0" role="region" aria-label="${esc(table.file?.label||t('results'))}"><table class="table result-table"><caption>${format(table.matched,0)} / ${format(table.total,0)} ${t('rows')}</caption><thead><tr>${columns.map(c=>`<th scope="col" title="${esc(c.description||'')}">${esc(c.label)}${c.unit&&!['proportion','log10','%','percentage_points'].includes(c.unit)?`<small> ${esc(c.unit)}</small>`:''}</th>`).join('')}<th scope="col">${t('details')}</th></tr></thead><tbody>${table.rows.map((row,i)=>`<tr>${columns.map(col=>`<td>${resultCell(row[col.key],col)}</td>`).join('')}<td><div class="actions">${button(t('details'),'row-details',{file:table.file.id,row:table.row_numbers?.[i]??table.offset+i},'quiet small','arrow')}${state.run?.has_igv_inputs&&rowLocus(row)?button(t('viewInIgv'),'run-igv',{locus:rowLocus(row)},'quiet small','igv'):''}</div></td></tr>`).join('')}</tbody></table>${!table.rows.length?empty(t('noRows')):''}</div>${compact?'':`<div class="pager"><span>${format(table.rows.length?table.offset+1:0,0)}–${format(Math.min(table.offset+table.rows.length,table.matched),0)} / ${format(table.matched,0)}</span><div class="actions"><button class="button small" data-action="table-page" data-offset="${Math.max(0,table.offset-table.limit)}" ${table.offset===0?'disabled':''}>${t('previous')}</button><button class="button small" data-action="table-page" data-offset="${table.offset+table.limit}" ${table.has_more?'':'disabled'}>${t('next')}</button></div></div>`}`}
function curveDefinition(table){
 const keys=new Set(table.columns.map(column=>column.key));
 if(keys.has('Min_child_reads')&&keys.has('Log10_CPI'))return{xkey:'Min_child_reads',ykey:'Log10_CPI',endkey:keys.has('Through_min_child_reads')?'Through_min_child_reads':null,xlabel:t('childReadThreshold'),counts:['N_sites','Matching_sites','Mismatching_sites'].filter(key=>keys.has(key)),combinedCounts:['Matching_sites','Mismatching_sites'].filter(key=>keys.has(key))};
 if(keys.has('Iteration')&&keys.has('log_CPI'))return{xkey:'Iteration',ykey:'log_CPI',endkey:null,xlabel:t('fetalReadThreshold'),counts:['NotMismatch','Mismatch'].filter(key=>keys.has(key)),combinedCounts:['NotMismatch','Mismatch'].filter(key=>keys.has(key))};
 return null;
}
function curvePointDetails(table,row,definition){
 const threshold=esc(row[definition.xkey])+(definition.endkey?'–'+esc(row[definition.endkey]):'');
 return `<b>${esc(definition.xlabel)}: ${threshold}</b><dl>${table.columns.filter(column=>column.key!==definition.xkey&&column.key!==definition.endkey).map(column=>`<div><dt>${esc(column.label||column.key)}</dt><dd data-curve-value="${esc(column.key)}">${absent(row[column.key])?`${esc(row[column.key]??'—')} · ${t('notAvailable')}`:esc(row[column.key])}</dd></div>`).join('')}</dl>${definition.endkey?`<p>${t('inclusiveIntervals')}</p>`:''}`;
}
function showCurvePoint(target,event){
 const point=target?.closest?.('[data-curve-point]'),container=point?.closest?.('[data-curve-chart]'),view=container&&curveViews.get(container.dataset.curveChart);
 if(!view)return false;const index=Number(point.dataset.curvePoint),row=view.rows[index];if(!row)return false;
 const tooltip=$(container.dataset.curveChart+'-tooltip');tooltip.innerHTML=curvePointDetails(view.table,row,view.definition);tooltip.hidden=false;
 container.querySelectorAll('[data-curve-point]').forEach(mark=>{mark.setAttribute('tabindex',mark===point?'0':'-1');mark.classList.toggle('selected',mark===point)});
 const bounds=container.getBoundingClientRect?.(),mark=point.getBoundingClientRect?.();
 if(bounds){const x=Number.isFinite(event?.clientX)?event.clientX:(mark?.left??bounds.left)+10,y=Number.isFinite(event?.clientY)?event.clientY:(mark?.bottom??bounds.top);tooltip.style.left=Math.max(8,Math.min(x-bounds.left+12,Math.max(8,bounds.width-340)))+'px';const height=tooltip.getBoundingClientRect?.().height||0,below=y-bounds.top+14;tooltip.style.top=Math.max(30,bounds.height&&below+height>bounds.height?y-bounds.top-height-14:below)+'px'}
 return true;
}
function hideCurvePoint(target){const container=target?.closest?.('[data-curve-chart]');if(container)$(container.dataset.curveChart+'-tooltip').hidden=true}
function curveKey(event){
 const point=event.target?.closest?.('[data-curve-point]'),container=point?.closest?.('[data-curve-chart]');if(!container)return false;
 if(event.key==='Escape'){hideCurvePoint(point);event.preventDefault();return true}
 if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(event.key))return false;
 const points=[...container.querySelectorAll('[data-curve-point]')],index=points.indexOf(point),next=event.key==='Home'?0:event.key==='End'?points.length-1:Math.max(0,Math.min(points.length-1,index+(['ArrowLeft','ArrowDown'].includes(event.key)?-1:1)));
 event.preventDefault();points.forEach(mark=>mark.setAttribute('tabindex',mark===points[next]?'0':'-1'));points[next]?.focus();showCurvePoint(points[next]);return true;
}
function combinedCurveScale(table,definition){
 const rows=(table.scaleRows||table.rows).filter(row=>Number.isSafeInteger(number(row[definition.xkey]))&&Number(row[definition.xkey])>=0&&(!definition.endkey||Number.isSafeInteger(number(row[definition.endkey]))&&Number(row[definition.endkey])>=Number(row[definition.xkey]))),logValues=rows.map(row=>number(row[definition.ykey])).filter(value=>value!==null),countValues=rows.flatMap(row=>definition.combinedCounts.map(key=>number(row[key]))).filter(value=>Number.isSafeInteger(value)&&value>=0);
 if(definition.combinedCounts.length!==2)return null;
 if(definition.xkey==='Iteration'){const values=[0,...logValues,...countValues];return{low:Math.min(...values),high:Math.max(1,...values),scale:1,offset:0,countMax:Math.max(1,...values),identity:true,guidesKnown:true}}
 if(!logValues.length)return null;
 const candidates=(state.run?.settings||[]).filter(item=>item.module==='cpin'&&(!table.file?.marker||item.marker===table.file.marker)),setting=candidates.find(item=>table.file?.step_id&&item.step_id===table.file.step_id)||(candidates.length===1?candidates[0]:null);
 const recorded=setting?.document?.parameters||{},lower=number(recorded.log_cpi_lower),upper=number(recorded.log_cpi_upper),guidesKnown=lower!==null&&upper!==null&&lower<upper;
 const values=guidesKnown?[...logValues,lower,upper]:logValues;let low=Math.min(...values),high=Math.max(...values);if(low===high){low-=.5;high+=.5}
 const countMax=Math.max(1,...countValues),scale=(high-low)/countMax;return{low,high,scale,offset:low,countMax,identity:false,guidesKnown};
}
function curveChart(table,mode='separate'){
 const definition=curveDefinition(table),partial=table.has_more?(L.language==='it'?`Il grafico mostra soltanto le prime ${format(table.rows.length,0)} di ${format(table.total,0)} righe. Consulta la tabella o il PDF originale per tutti i risultati.`:`The chart shows only the first ${format(table.rows.length,0)} of ${format(table.total,0)} rows. Consult the original table or PDF for all results.`):'';
 if(!definition)return notice(t('curveUnsupported'),'warning');
 const{xkey,ykey,endkey,xlabel}=definition,validThreshold=value=>number(value)!==null&&Number.isSafeInteger(Number(value))&&Number(value)>=0;
 const plotValue=(row,key)=>{const value=number(row[key]);return definition.counts.includes(key)&&(!Number.isSafeInteger(value)||value<0)?null:value};
 const rows=table.rows.filter(row=>validThreshold(row[xkey])&&(!endkey||validThreshold(row[endkey])&&Number(row[endkey])>=Number(row[xkey])));
 const skipped=table.rows.length-rows.length;
 const combined=mode==='combined'?combinedCurveScale(table,definition):null;
 if(mode==='combined'&&!combined)return notice(t('combinedUnavailable'),'warning')+curveChart(table,'separate');
 const panels=combined?[{keys:[ykey,...definition.combinedCounts],label:t('combinedCurve'),kind:'combined'}]:[{keys:[ykey],label:'log₁₀(CPI)',kind:'log'},...(definition.counts.length?[{keys:definition.counts,label:t('siteCounts'),kind:'counts'}]:[])];
 const charts=panels.map(panel=>{
  const series=panel.keys.map(key=>({key,label:table.columns.find(column=>column.key===key)?.label||key,color:key===ykey?'#000000':['Mismatch','Mismatching_sites'].includes(key)?'#C46B00':key==='N_sites'?'#536d9c':'#008A38'}));
  const points=rows.filter(row=>series.some(item=>plotValue(row,item.key)!==null));if(!points.length)return `<h4>${esc(panel.label)}</h4>`+empty(t('curveEmpty'));
  const xs=points.flatMap(row=>[Number(row[xkey]),...(endkey?[Number(row[endkey])]:[])]),ys=points.flatMap(row=>series.map(item=>plotValue(row,item.key)).filter(value=>value!==null));
  let xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys);if(xmin===xmax){xmin-=.5;xmax+=.5}
  if(combined){ymin=combined.low;ymax=combined.high}
  if(panel.kind==='counts'){ymin=Math.min(0,ymin);ymax=Math.max(1,ymax)}else{const pad=ymin===ymax?1:(ymax-ymin)*.12;ymin-=pad;ymax+=pad}
  if(!Number.isFinite(ymax-ymin)||ymax<=ymin||combined&&(!Number.isFinite(combined.scale)||combined.scale<=0))return notice(t('curveScaleUnavailable'),'warning');
  const W=740,H=280,left=85,right=combined?85:25,top=30,bottom=55,X=value=>left+(value-xmin)/(xmax-xmin)*(W-left-right),Y=value=>top+(ymax-value)/(ymax-ymin)*(H-top-bottom);
  const gridValues=[...new Set([0,.25,.5,.75,1].map(f=>panel.kind==='counts'?Math.round(ymin+(ymax-ymin)*f):ymin+(ymax-ymin)*f))];
  const grid=gridValues.map(value=>`<line class="chart-grid" x1="${left}" x2="${W-right}" y1="${Y(value)}" y2="${Y(value)}"/><text x="${left-10}" y="${Y(value)+4}" text-anchor="end">${format(value,panel.kind==='counts'?0:2)}</text>`).join('');
  const rightTicks=combined?[...new Set([0,.25,.5,.75,1].map(f=>Math.round(combined.countMax*f)))].map(value=>`<text class="curve-right-tick" x="${W-right+10}" y="${Y(value*combined.scale+combined.offset)+4}" text-anchor="start">${format(value,0)}</text>`).join(''):'';
  const unique=[...new Set(xs)].sort((a,b)=>a-b),tickValues=unique.length<8?unique:[unique[0],unique[Math.floor(unique.length/2)],unique.at(-1)];
  const ticks=tickValues.map(value=>`<text x="${X(value)}" y="${H-bottom+23}" text-anchor="middle">${format(value,0)}</text>`).join('');
  const id='curve-'+(++curveId);curveViews.set(id,{table,rows:points,definition});
  const connectors=combined&&!endkey?series.map(item=>{const segments=[];for(let i=1;i<points.length;i++){const previous=points[i-1],row=points[i],a=plotValue(previous,item.key),b=plotValue(row,item.key);if(Number(row[xkey])!==Number(previous[xkey])+1||a===null||b===null)continue;segments.push(`M${X(Number(previous[xkey]))},${Y(item.key===ykey?a:a*combined.scale+combined.offset)} L${X(Number(row[xkey]))},${Y(item.key===ykey?b:b*combined.scale+combined.offset)}`)}return segments.length?`<path class="curve-connector" data-curve-series="${esc(item.key)}" style="stroke:${item.color}" d="${segments.join(' ')}"${item.key==='Mismatch'?' stroke-dasharray="5 3"':''}/>`:''}).join(''):'';
  const marks=points.map((row,index)=>{
   const x=X(Number(row[xkey])),end=endkey?X(Number(row[endkey])):x,label=xlabel+': '+row[xkey]+(endkey?'–'+row[endkey]:'')+'; '+series.map(item=>item.label+': '+(row[item.key]??t('notAvailable'))).join('; ');
   return `<g class="curve-point" data-curve-point="${index}" tabindex="${index===0?'0':'-1'}" role="button" aria-label="${esc(label)}" aria-describedby="${id}-tooltip">${series.map(item=>{const value=plotValue(row,item.key);if(value===null)return'';const y=Y(combined&&item.key!==ykey?value*combined.scale+combined.offset:value),line=item.key===ykey?'curve-line':'site-curve-line';return `${endkey?`<path data-curve-series="${esc(item.key)}" class="${line}" style="stroke:${item.color}" d="M${x},${y} L${end},${y}"${['Mismatch','Mismatching_sites'].includes(item.key)?' stroke-dasharray="5 3"':''}/><path class="curve-hit" d="M${x},${y} L${end},${y}"/>`:''}<circle data-curve-series="${esc(item.key)}" class="curve-dot" style="fill:${item.color}" cx="${x}" cy="${y}" r="4"/><circle class="curve-hit-dot" cx="${x}" cy="${y}" r="9"/>${endkey?`<circle data-curve-series="${esc(item.key)}" class="curve-dot" style="fill:${item.color}" cx="${end}" cy="${y}" r="4"/>`:''}`}).join('')}</g>`;
  }).join('');
  return `<figure class="interactive-curve" data-curve-chart="${id}"><figcaption>${esc(panel.label)}</figcaption><div class="curve-legend">${series.map(item=>`<span><i style="background:${item.color}"></i>${esc(item.label)}</span>`).join('')}</div><div class="chart-scroll"><svg viewBox="0 0 ${W} ${H}" class="curve-chart" role="group" aria-label="${esc(panel.label+' · '+xlabel)}"><title>${esc(panel.label)}</title>${grid}${rightTicks}${ticks}${connectors}${marks}<text x="17" y="17">${esc(combined?'log₁₀(CPI)':panel.label)}</text>${combined?`<text class="curve-right-label" x="${W-17}" y="17" text-anchor="end">${t('siteCounts')}</text>`:''}<text x="${W/2}" y="${H-8}" text-anchor="middle">${esc(xlabel)}</text></svg></div><div id="${id}-tooltip" class="curve-tooltip" role="tooltip" aria-live="polite" hidden></div></figure>`;
 }).join('');
 const missing=rows.some(row=>number(row[ykey])===null||definition.counts.some(key=>plotValue(row,key)===null));
 return charts+(combined?`<p class="help combined-axis-help">${t(combined.identity?'combinedIdentityAxes':'combinedAffineAxes')}${!combined.guidesKnown?' '+t('combinedNoGuides'):''}</p>`:'')+`<p class="help curve-help">${t('curveInteraction')} ${t('curveHelp')} ${endkey?t('inclusiveIntervals'):t(combined?'combinedConnectors':'discreteThresholds')} ${t('curveOriginalHelp')}</p>`+((skipped||missing)?notice(t('curveInvalidValues'),'warning'):'')+(partial?notice(partial,'warning'):'');
}
function renderCurve(table){
 if(table.error)return notice(table.error,'warning');
 const limit=1000,total=table.rows.length,page=Math.min(state.curvePages[table.file.id]||0,Math.max(0,Math.ceil(total/limit)-1)),offset=page*limit,shown={...table,rows:table.rows.slice(offset,offset+limit),row_numbers:table.row_numbers?.slice(offset,offset+limit),offset,scaleRows:table.rows},mode=state.curveModes[table.file.id]||'separate',canCombine=curveDefinition(table)?.combinedCounts.length===2;
 const views=`<div class="actions curve-view-options" role="group" aria-label="${t('curveView')}">${['separate','combined'].map(value=>`<button class="button small ${mode===value?'primary':''}" data-action="curve-mode" data-id="${esc(table.file.id)}" data-mode="${value}" aria-pressed="${mode===value}" ${value==='combined'&&!canCombine?'disabled':''}>${t(value==='combined'?'combinedCurve':'separateCurves')}</button>`).join('')}</div>`;
 const pager=total>limit?`<div class="pager"><span>${t('curvePageRows')}: ${format(offset+1,0)}–${format(Math.min(offset+limit,total),0)} / ${format(total,0)}</span><div class="actions"><button class="button small" data-action="curve-page" data-id="${esc(table.file.id)}" data-page="${page-1}" ${page===0?'disabled':''}>${t('previous')}</button><button class="button small" data-action="curve-page" data-id="${esc(table.file.id)}" data-page="${page+1}" ${offset+limit>=total?'disabled':''}>${t('next')}</button></div></div>`:'';
 return `<section class="section-gap"><div class="section-title"><h3>${t('curves')}${table.file.cutoff?' · '+esc(table.file.cutoff):''}</h3>${button(t('download'),'export-file',{id:table.file.id},'small','download')}</div>${views}${pager}${curveChart(shown,mode)}<details class="disclosure"><summary>${t('details')}</summary><div class="details-body">${tableView(shown,{compact:true,all:true})}${button(t('open'),'open-file',{id:table.file.id},'small','arrow')}</div></details></section>`;
}
function renderFiles(files=state.files,includeCopies=false){const shown=files.filter(file=>includeCopies||file.canonical!==false),copies=includeCopies?[]:files.filter(file=>file.canonical===false);return `<div class="file-list">${shown.map(f=>`<article class="file-row"><span class="file-icon">${esc(f.kind==='table'?f.name.split('.').pop().toUpperCase():f.kind.toUpperCase())}</span><div><b>${esc(f.label||f.name)}</b><small>${esc([moduleName(f.module),f.marker,f.sample_label,f.family_label,f.analysis?choiceLabel(f.analysis):''].filter(Boolean).join(' · '))} · ${format(f.size_bytes/1024,1)} KB</small><details class="file-name"><summary>${t('fileName')}</summary>${esc(f.relative_path||f.name)}</details></div><div class="actions">${['table','pdf'].includes(f.kind)?button(t('open'),'open-file',{id:f.id},'small','file'):''}${button(t('download'),'export-file',{id:f.id},'small quiet','download')}</div></article>`).join('')||(copies.length?'':empty(t('noResults')))}</div>${copies.length?`<details class="disclosure"><summary>${L.language==='it'?'Copie di presentazione con i nomi dei campioni':'Presentation copies with sample names'} · ${copies.length}</summary><div class="details-body">${renderFiles(copies,true)}</div></details>`:''}`}
function resultRowDetails(row,columns){const groups=[['',columns.filter(c=>!/_mother$|_father$|_child$/.test(c.key))],...[['mother','mother'],['father','father'],['child','child']].map(([key,label])=>[t(label),columns.filter(c=>c.key.endsWith('_'+key))])];return groups.filter(([,cols])=>cols.length).map(([name,cols])=>`${name?`<h3 class="section-gap">${name}</h3>`:''}<dl class="detail-values">${cols.map(c=>`<div><dt>${esc(c.label)}</dt><dd>${resultCell(row[c.key],c,true)}${number(row[c.key])!==null?`<small>${t('originalValue')}: ${esc(row[c.key])}</small>`:''}${c.description?`<small>${esc(c.description)}</small>`:''}</dd></div>`).join('')}</dl>`).join('')}
function renderModule(){const group=currentGroup();if(!group)return empty(t('noResults'));const entry=currentEntry();return `<div class="toolbar">${select(t('markers'),'result-marker',(state.overview.modules||[]).filter(g=>g.module===group.module).map(g=>[g.module+'|'+g.marker,g.marker]),state.module,'data-result="module"')}${group.entries.length?select(group.module==='contamination'||group.module.endsWith('-call')?t('sample'):t('family'),'result-entry',group.entries.map((e,i)=>[String(i),entryLabel(e)]),String(state.entry),'data-result="entry"'):''}${entry?reportButton():''}</div>${group.warnings?.map(w=>notice(typeof w==='string'?w:w.message,'warning')).join('')||''}${entry?`${outcomePanel(entry)||metrics(entry.metrics||[])}${genotypeBars(entry)}${entry.row?`<details class="disclosure"><summary>${t('summary')}</summary><div class="details-body">${resultRowDetails(entry.row,Object.keys(entry.row).map(key=>group.summary_columns?.[key]||{key,label:resultFieldLabel(key)}))}</div></details>`:''}${state.curves.map(renderCurve).join('')}${state.table?`<div class="section-title"><h3>${t('siteDetails')}</h3>${button(t('download'),'export-file',{id:state.table.file.id},'small','download')}</div><div class="toolbar"><input id="site-search" class="input stretch" aria-label="${t('search')}" placeholder="${t('siteSearch')}" data-search="table" value="${esc(state.tableSearch)}"><label class="check-row"><input type="checkbox" data-field="allColumns" ${state.allColumns?'checked':''}><span>${t('allColumns')}</span></label></div>${tableView(state.table)}`:''}${group.matrix_file_ids?.length?`<details class="disclosure"><summary>${L.language==='it'?'Confronta i genotipi dei campioni':'Compare sample genotypes'}</summary><div class="details-body">${group.matrix_file_ids.map(id=>button(t('open'),'open-file',{id},'small','file')).join('')}</div></details>`:''}`:empty(t('noResults'))}<details class="disclosure"><summary>${t('originals')}</summary><div class="details-body">${renderFiles(group.files||[])}</div></details>${resultHelp()}`}
function resultFieldLabel(key){const fieldMap={Pair:['Coppia','Pair'],Trio:['Trio','Trio'],Marker_type:[t('markers'),t('markers')],Analysis:[t('phaseSelection'),t('phaseSelection')],CPI:['Indice di paternità combinato','Combined Paternity Index'],Log10_CPI:['log₁₀(CPI)','log₁₀(CPI)'],CPI_medianFF:['log₁₀(CPI) alla soglia mediana di letture fetali','log₁₀(CPI) at the median fetal read threshold'],Median_fetal_fraction_percent:['Frazione fetale mediana (%)','Median fetal fraction (%)'],Median_fetal_fraction_raw:['Frazione fetale mediana (proporzione)','Median fetal fraction (proportion)'],N_sites_mother:['Siti informativi materni','Maternal informative sites'],N_sites_father:['Siti paterni candidati','Paternal candidate sites'],paternal_used_at_median:['Siti paterni usati per il CPI alla soglia mediana','Paternal sites used for CPI at the median threshold'],Min_logCPI:['Minimo log₁₀(CPI)','Minimum log₁₀(CPI)'],Max_logCPI:['Massimo log₁₀(CPI)','Maximum log₁₀(CPI)'],Mean_logCPI:['Media log₁₀(CPI)','Mean log₁₀(CPI)'],Median_logCPI:['Mediana log₁₀(CPI)','Median log₁₀(CPI)'],Error_constant:['Probabilità di errore','Error probability'],Min_fetal_reads:[L.field('min_fetal_reads'),L.field('min_fetal_reads')],Min_child_reads:[L.field('min_child_reads'),L.field('min_child_reads')],N_sites:['Siti inclusi','Included sites'],N_heterozygous_child_sites:['Siti con figlio eterozigote','Heterozygous child sites'],N_homozygous_child:['Siti con figlio omozigote','Homozygous child sites'],Matching_sites:['Siti compatibili con il padre','Sites matching the father'],Mismatching_sites:['Siti incompatibili con il padre','Sites mismatching the father'],individuo:[t('sample'),t('sample')],informative_sites:['Siti informativi','Informative sites'],mean_contamination:['Contaminazione media (proporzione)','Mean contamination (proportion)'],sd_contamination:['Deviazione standard (proporzione)','Standard deviation (proportion)'],Cutoff:['Pannello di selezione','Selection panel']};return fieldMap[key]?.[L.language==='en'?1:0]||L.field(key)}
function renderRun(){const run=state.run,groups=state.overview?.modules||[];let content='';if(state.runTab==='results'){content=`<div class="module-tabs" role="tablist"><button role="tab" aria-selected="${!state.module}" class="${!state.module?'active':''}" data-action="result-module" data-module="">${t('summary')}</button>${[...new Set(groups.map(g=>g.module))].map(module=>`<button role="tab" aria-selected="${currentGroup()?.module===module}" class="${currentGroup()?.module===module?'active':''}" data-action="result-module" data-module="${esc(groups.find(g=>g.module===module).module+'|'+groups.find(g=>g.module===module).marker)}">${module.endsWith('-call')?module.startsWith('dnp')?'DNP':'SNP':moduleName(module)}</button>`).join('')}<button role="tab" aria-selected="${state.module==='files'}" class="${state.module==='files'?'active':''}" data-action="result-module" data-module="files">${t('files')}</button></div><div class="results-body">${state.module==='files'?`<div class="section-title"><h2>${t('files')}</h2>${button(t('downloadAll'),'export-run',{},'','download')}</div>`+renderFiles():state.module?renderModule():renderResultsSummary()}</div>`}else if(state.runTab==='samples'){content=`<div class="table-scroll"><table class="table"><thead><tr><th>${t('sampleName')}</th><th>${t('sampleFile')}</th></tr></thead><tbody>${run.samples.map(s=>`<tr><td>${esc(s.label||s.id)}</td><td>${esc(s.filename)}<details class="file-name"><summary>${t('details')}</summary>${esc(s.path||'')}</details></td></tr>`).join('')}</tbody></table></div>`}else if(state.runTab==='parameters'){content=renderArchivedSettings(run)}else{content=`<div class="panel-body"><dl class="review-list"><dt>${t('status')}</dt><dd>${badge(run.status)}</dd><dt>${t('date')}</dt><dd>${date(run.started_at)} → ${date(run.finished_at)}</dd><dt>${t('applicationVersion')}</dt><dd>${esc(run.version||'—')}</dd></dl>${run.error?notice(typeof run.error==='string'?run.error:run.error.message||JSON.stringify(run.error),'error'):''}${(run.warnings||[]).map(w=>notice(w.message||w.reason||JSON.stringify(w),'warning')).join('')}<details class="disclosure"><summary>${t('files')}</summary><div class="details-body">${renderFiles(state.files.filter(f=>!f.module))}</div></details></div>`}return heading(run.name||run.id,'',button(t('rerun'),'reuse-run',{},'','play')+button(t('openRunDirectory'),'open-run-directory',{id:run.id},'','archive')+button(t('exportDiagnostics'),'export-diagnostics',{id:run.id},'','download')+(run.has_igv_inputs?button(t('viewInIgv'),'run-igv',{},'','igv'):'')+(run.can_remove===true?button(t('removeFromList'),'remove-run',{id:run.id},'quiet','close'):''),t('archive'))+`<div class="meta-row"><span>${date(run.started_at)}</span><span>${esc(run.markers.join(' / '))}</span><span>${run.samples.length} ${t(run.samples.length===1?'sample':'samples').toLowerCase()}</span>${badge(run.status)}</div>${run.status!=='succeeded'?notice(t('partialResults'),'warning'):''}${run.status_note?notice(run.status_note,'warning'):''}<section class="panel section-gap"><div class="tabs" role="tablist">${[['results','results'],['samples','samples'],['parameters','usedSettings'],['provenance','provenance']].map(([value,key])=>`<button class="tab ${state.runTab===value?'active':''}" role="tab" aria-selected="${state.runTab===value}" data-action="run-tab" data-tab="${value}">${t(key)}</button>`).join('')}</div>${content}</section><div class="section-title"><div><h3>${t('newFromSettings')}</h3><p class="help">${t('rerunHelp')}</p></div>${button(t('rerun'),'reuse-run',{},'','play')}</div>`}
function archivedFlagNames(value){
 if(!Number.isSafeInteger(Number(value))||Number(value)<0)return displayValue(value);
 const flags=[[1,'Letture appaiate','Paired reads'],[2,'Coppie corrette','Proper pairs'],[4,'Non allineate','Unmapped'],[8,'Compagno non allineato','Unmapped mate'],[16,'Filamento inverso','Reverse strand'],[32,'Compagno sul filamento inverso','Mate on reverse strand'],[64,'Prima lettura della coppia','First read in pair'],[128,'Seconda lettura della coppia','Second read in pair'],[256,'Allineamenti secondari','Secondary alignments'],[512,'Controllo qualità non superato','Failed quality control'],[1024,'Duplicati','Duplicates'],[2048,'Allineamenti supplementari','Supplementary alignments']];
 const selected=flags.filter(([bit])=>(Number(value)&bit)!==0).map(([,it,en])=>L.language==='en'?en:it);
 if(Number(value)>4095)selected.push((L.language==='it'?'Altre categorie':'Additional categories')+': '+value);
 return selected.join(' · ')||t('emptyValue')
}
function renderArchivedSettings(run){
 const sections=(run.settings||[]).map(snapshot=>{
  const document=snapshot.document||{},step=(run.steps||[]).find(s=>s.id===snapshot.step_id),sample=(run.samples||[]).find(s=>s.id===step?.sample_id);
  const label=[moduleName(snapshot.module),snapshot.marker,sample?.label||sample?.id].filter(Boolean).join(' · ');
  const parameters=Object.entries(document.parameters||{}).filter(([key])=>!['SNP','DNP'].includes(snapshot.marker)||!key.startsWith('err_const_')||key==='err_const_'+snapshot.marker.toLowerCase()).map(([key,value])=>`<div><dt>${esc(L.field(key))}<small>${t(phase(key))}</small></dt><dd>${esc(absent(value)?t('notAvailable'):key==='excluded_flags'?archivedFlagNames(value):typeof value==='string'?choiceLabel(value):displayValue(value))}</dd></div>`).join('');
  const constants=Object.entries(document.constants||{}).map(([key,stored])=>{
   const entry=stored&&typeof stored==='object'&&!Array.isArray(stored)?stored:{value:stored},current=state.settings[snapshot.module]?.constants?.[key];
   const sameModel=current&&JSON.stringify(current.value)===JSON.stringify(entry.value);
   const description=sameModel?constantDescription(key,entry):(typeof entry.description==='object'?entry.description[L.language]||entry.description.it||entry.description.en||'':entry.description||'');
   const value=sameModel?constantValue(snapshot.module,key,entry):`<div class="readonly-value">${esc(displayValue(entry.value))}</div>`;
   return `<section class="parameter-group"><h3>${esc(constantLabel(key,entry))}</h3>${description?`<p class="help">${esc(description)}</p>`:''}${value}</section>`
  }).join('');
  return `<details class="disclosure" open><summary>${esc(label)}</summary><div class="details-body"><dl class="detail-values">${parameters}</dl>${constants?`<details class="disclosure"><summary>${t('constants')} · ${t('readOnly')}</summary><div class="details-body">${constants}</div></details>`:''}</div></details>`
 }).join('');
 const executionLabels={input_hashes:'hashes',cpus:'cpuLimit',memory_mb:'memoryLimit',pids_limit:'processLimit',performance_diagnostics:'diagnostics',execution_mode:'mode',max_workers:'maxWorkers',dnp_block_mib:'blockSize',dnp_block_loci:'blockLoci'};
 const execution=Object.entries(run.execution||{}).filter(([key])=>!key.startsWith('dnp_block_')||(run.modules||[]).includes('dnp-call')).map(([key,value])=>{
  const label=executionLabels[key]?t(executionLabels[key]):L.field(key),rendered=value===null?t('automatic'):value==='auto'?t('automatic'):value==='serial'?t('serial'):key==='input_hashes'&&value==='full'?t('fullHashes'):displayValue(value);
  return `<div><dt>${esc(label)}</dt><dd>${esc(rendered)}</dd></div>`
 }).join('');
 const provenance=L.language==='it'?'Valori registrati per questo esperimento, conservati in sola lettura.':'Recorded values for this experiment, preserved as read only.';
 return `<div class="panel-body"><p class="help">${provenance}</p>${sections}${execution?`<details class="disclosure"><summary>${t('execution')} · ${t('readOnly')}</summary><div class="details-body"><dl class="detail-values">${execution}</dl></div></details>`:''}${!sections&&!execution?empty(t('noResults')):''}</div>`
}
function math(expr,label){return `<div class="formula"><math xmlns="http://www.w3.org/1998/Math/MathML" display="block" aria-label="${esc(label)}"><mrow>${expr}</mrow></math></div>`}
const mn=v=>`<mn>${v}</mn>`,mi=v=>`<mi>${v}</mi>`,mo=v=>`<mo>${esc(v)}</mo>`,sub=(v,s)=>`<msub>${mi(v)}<mtext>${s}</mtext></msub>`,frac=(a,b)=>`<mfrac><mrow>${a}</mrow><mrow>${b}</mrow></mfrac>`,power=(a,b)=>`<msup><mrow>${a}</mrow><mrow>${b}</mrow></msup>`,par=s=>mo('(')+s+mo(')');
function constantLabel(key,entry){
 const label=L.field(key);
 return key==='missing_result'&&entry.value==='NA'?label+' (NA)':label;
}
function constantValue(module,key,entry){const nr=sub('n','REF'),na=sub('n','ALT'),no=sub('n',L.language==='en'?'other':'altre'),sum=nr+mo('+')+na,label=L.field(key);let expr='';
 if(key==='missing_result'&&entry.value==='NA')return ''; // The glossary heading shows the recorded marker.
 if(key==='phred_error_probability')expr=mi('ε')+mo('=')+power(mn(10),mo('−')+frac(mi('Q'),mn(10)));
 else if(key==='count_ratio')expr=mi('r')+mo('=')+frac(nr,sum);
 else if(key==='other_fraction_denominator')expr=nr+mo('+')+na+mo('+')+no;
 else if(key==='site_contamination')expr=sub('c','i')+mo('=')+frac(sub('n',L.language==='en'?'unexpected':'inattese'),sum);
 else if(key==='sample_contamination')expr=mi('c')+mo('=')+frac(mn(1),mi('m'))+`<munderover><mo>∑</mo><mrow><mi>i</mi><mo>=</mo><mn>1</mn></mrow><mi>m</mi></munderover>`+sub('c','i');
 else if(key==='pi_formula')expr=sub('PI','i')+mo('=')+frac(sub('t','i'),sub('p','i'));
 else if(key==='het_het_pi')expr=sub('PI','i')+mo('=')+frac(mn(1),sub('p','REF')+mo('+')+sub('p','ALT'));
 else if(key==='fetal_fraction_formula')expr=mi('F')+mo('=')+`<mi mathvariant="normal">${L.language==='en'?'median':'mediana'}</mi>`+par(frac(mn(2)+mo('·')+sub('n',L.language==='en'?'fetal':'fetali'),sum));
 else if(key==='likelihood_formula'){const g=mi('g'),eps=mi('ε'),p=par(frac(mn(2)+mo('−')+g,mn(2))+mo('·')+par(mn(1)+mo('−')+eps)+mo('+')+frac(g,mn(2))+mo('·')+eps);expr=sub('ℓ','REF')+par(g)+mo('=')+`<mo>∑</mo><mi mathvariant="normal">ln</mi>`+p;return math(expr,label)+`<p class="help">${L.language==='en'?'REF observations; REF/ALT weights are exchanged for ALT. The selected genotype maximizes the combined natural log-likelihood. Other reads do not contribute.':'Osservazioni REF; per ALT i pesi REF/ALT sono scambiati. Il genotipo scelto massimizza la somma delle log-verosimiglianze naturali. Le altre letture non contribuiscono.'}</p>`}
 else if(key==='heterozygous_transmission')expr=mi('P')+mo('=')+frac(mn(1),mn(2));
 else if(key==='homozygous_transmission')expr=mi('P')+mo('=')+mn(1);
 else if(key==='population_frequencies')expr=mn(0)+mo('<')+mi('p')+mo('≤')+mn(1);
 else if(key==='log_cpi_base')expr=`<msub><mi mathvariant="normal">log</mi>${mn(10)}</msub>`+par('<mi mathvariant="normal">CPI</mi>');
 if(expr){
  const legend={pi_formula:'piSymbols',phred_error_probability:'phredSymbols',sample_contamination:'contaminationSymbols',count_ratio:'readCountSymbols',other_fraction_denominator:'readCountSymbols',site_contamination:'readCountSymbols',fetal_fraction_formula:'readCountSymbols'}[key];
  return math(expr,label)+(legend?`<p class="help">${esc(t(legend))}</p>`:'')
 }
 const meanings={one_site_sd:[t('notAvailable'),t('notAvailable')],likelihood_log_base:['Logaritmo naturale (base e)','Natural logarithm (base e)'],indel_policy:['Escludi le osservazioni con inserzioni o delezioni in una posizione della finestra.','Discard observations with an insertion or deletion at any position in the window.'],maternal_selection:['Siti con madre omozigote','Sites with a homozygous mother'],curve_threshold_semantics:['Supporto dell’allele paterno obbligato dopo il filtro iniziale degli alleli del figlio.','Obligatory paternal allele support after the initial child genotype support filter.'],likelihood_quality:module==='dnp-call'?['Media aritmetica delle qualità Phred delle due basi centrali','Arithmetic mean of the two central Phred qualities']:['Qualità Phred della base SNP centrale','Phred quality of the central SNP base']};return `<div class="readonly-value">${esc(meanings[key]?.[L.language==='en'?1:0]??displayValue(entry.value))}</div>`}
function constantDescription(key,entry){if(key==='missing_result'&&entry.value==='NA')return t('missingResultHelp');if(key==='population_frequencies')return t('frequencyDomain');if(L.language!=='en')return entry.description||'';return {het_het_pi:'For a heterozygous mother and child, PI equals 1 when the two population frequencies sum to 1.',ploidy:'Diploid model; changing ploidy requires a different scientific model.',allele_alphabet:'Alleles supported by this model.',phred_offset:'Phred+33 quality encoding, not a quality threshold.',phred_error_probability:'Definition of the conversion from Phred quality to error probability.',genotypes:'Diploid states in the biallelic model.',likelihood_log_base:'Likelihoods are sums of natural logarithms, not normalized probabilities.',other_filter_comparison:'Comparison used at the other-read threshold.',indel_policy:'Applies to the complete observation window.',window_bases:'The site plus one flanking base on each side.',count_ratio:'REF fraction among REF and ALT observations only.',likelihood_quality:'Flanking bases determine whether a complete window exists.',likelihood_formula:'The called genotype maximizes the likelihood of REF and ALT observations.',other_fraction_denominator:'All REF, ALT and other observations.',site_contamination:'Unexpected reads divided by REF and ALT reads at each informative site.',sample_contamination:'Arithmetic mean of retained per-site contamination estimates.',one_site_sd:'Sample standard deviation is undefined with a single informative site.',heterozygous_transmission:'Mendelian transmission from a heterozygous father.',homozygous_transmission:'Mendelian transmission from a homozygous father.',log_cpi_base:'Base of the logarithm reported for the Combined Paternity Index.',pi_formula:'Paternal transmission probability, or the mismatch error probability, divided by the population frequency of the obligatory allele.',fetal_fraction_formula:'Median of twice the fetal read fraction at informative sites.',maternal_selection:'The postnatal model selects homozygous maternal sites.',curve_threshold_semantics:'The curve threshold is evaluated after the initial support filter.'}[key]||''}
function renderCatalog(){const modules=Object.keys(state.settings).filter(m=>state.catalogModule==='all'||state.catalogModule===m);return heading(t('catalog'),state.catalogDefaults?t('preferencesHelp'):'',state.catalogDefaults?button(t('savePreferences'),'save-preferences',{},'primary','check'):'')+`<section class="panel"><div class="panel-body"><div class="toolbar"><input id="catalog-search" class="input stretch" placeholder="${t('parameterSearch')}" aria-label="${t('search')}" value="${esc(state.catalogSearch)}" data-search="catalog">${select(t('analysis'),'catalog-module',[['all',t('all')],...Object.keys(state.settings).map(m=>[m,moduleName(m)])],state.catalogModule,'data-field="catalogModule"')}${select(t('catalog'),'catalog-type',[['parameters',t('parameters')],['constants',t('constants')]],state.catalogType,'data-field="catalogType"')}</div>${modules.map(m=>{const content=state.catalogType==='parameters'?parameterRows(m,state.catalogDefaults?'defaults':'draft',!state.catalogDefaults,true):Object.entries(state.settings[m].constants).filter(([key,p])=>[constantLabel(key,p),constantDescription(key,p)].join(' ').toLowerCase().includes(state.catalogSearch.toLowerCase())).map(([key,p])=>`<div class="parameter-row"><div><h3>${esc(constantLabel(key,p))}</h3><p>${esc(constantDescription(key,p))}</p>${constantValue(m,key,p)}</div><div><span class="badge neutral">${t(key==='population_frequencies'?'inputConstraint':'readOnly')}</span></div></div>`).join('');return content?`<section class="parameter-group"><h2>${moduleName(m)}</h2>${content}</section>`:''}).join('')}</div></section>`}
function renderPreferences(){const p=state.preferences;return heading(t('settings'),t('preferencesHelp'),button(t('savePreferences'),'save-preferences',{},'primary','check'))+`<div class="grid two-columns"><section class="panel"><div class="panel-header"><h2>${t('dataDirectory')}</h2></div><div class="panel-body">${fileField(t('dataDirectory'),'preference.data_dir',p.data_dir||state.boot.layout.data_dir,'directory')}<div class="section-gap">${fileField(t('runsDirectory'),'preference.runs_dir',p.runs_dir||state.boot.layout.runs_dir,'directory')}</div><div class="divider"></div><h3>${t('scientificDefaults')}</h3>${select(t('defaultProfile'),'default-profile',profileOptions(p),p.default_profile||'','data-preference="default_profile"')}<p class="help">${t('profileLocation')}</p><div class="actions section-gap">${button(t('editDefaults'),'edit-defaults',{},'','catalog')}</div></div></section><section class="panel"><div class="panel-header"><h2>${t('updates')}</h2></div><div class="panel-body">${select(t('updateChannel'),'update-channel',[['stable',t('stable')],['testing',t('testing')]],p.update_channel,'data-preference="update_channel"')}<label class="check-row section-gap"><input type="checkbox" data-preference="check_updates_on_startup" ${p.check_updates_on_startup?'checked':''}><span>${t('checkStartup')}</span></label><div class="divider"></div><div class="settings-row"><div><b>${t('motion')}</b><p>${t('motionHelp')}</p></div><input aria-label="${t('motion')}" type="checkbox" data-field="motion" ${state.motion?'checked':''}></div></div></section></div><section class="panel section-gap"><div class="panel-header"><h2>${t('execution')}</h2></div><div class="panel-body">${executionFields(p.execution||{},'defaults')}</div></section>`}
function renderResources(){const s=state.environment||{},runtime=s.runtime||{};const rows=[[L.language==='it'?'Computer':'Computer',s.host],[L.language==='it'?'Ambiente · configurazione salvata':'Environment · saved configuration',runtime.configured],[L.language==='it'?'Ambiente · risorse effettive':'Environment · effective resources',runtime.effective],[L.language==='it'?'Limiti delle analisi':'Analysis limits',s.container]];return `<table class="table"><thead><tr><th>${t('environment')}</th><th>CPU</th><th>RAM · MiB</th></tr></thead><tbody>${rows.map(([label,v])=>`<tr><td>${esc(label)}</td><td>${format(v?.cpus,2)}</td><td>${format(v?.memory_mib,0)}</td></tr>`).join('')}</tbody></table>${(s.warnings||[]).map(w=>notice(w,'warning')).join('')}${s.backend==='wsl'?notice(L.language==='it'?'RAM e CPU di WSL2 sono condivise con tutte le distribuzioni WSL2 dell’utente.':'WSL2 memory and CPU limits are shared by all WSL2 distributions for this user.','warning'):''}${['wsl','lima'].includes(s.backend)?`<div class="form-row">${input(t('memoryLimit'),'runtime-memory',state.runtimeMemory??runtime.configured?.memory_mib??'','type="number" min="128" data-field="runtimeMemory"')}${input(t('cpuLimit'),'runtime-cpus',state.runtimeCpus??runtime.configured?.cpus??'','type="number" min="1" data-field="runtimeCpus"')}</div>${button(t('previewResources'),'preview-resources',{},'','settings')}`:''}`}
function renderInstallation(){const s=state.installation;if(!s)return '';const items=[...(s.runtimes||[]),...(s.cache||[])];return `<details class="disclosure"><summary>${L.language==='it'?'Installazione e spazio':'Installation and storage'}</summary><div class="details-body">${items.map(item=>`<div class="settings-row"><div><b>${esc(item.name)}</b><p>${format(item.size_bytes/1024/1024,1)} MiB · ${esc(item.reason||'')}</p><p class="path">${esc(item.path)}</p></div>${item.removable?button(t('remove'),'maintain',{operation:'cleanup',target:item.id},'danger small'):''}</div>`).join('')}${s.recovery?.reason?`<p class="help section-gap">${esc(s.recovery.reason)}</p>`:''}${s.recovery?.recoverable?button(L.language==='it'?'Ripara / riprendi preparazione':'Repair / resume setup','maintain',{operation:'recover',target:s.recovery.id},'','settings'):''}${(s.warnings||[]).map(w=>notice(w,'warning')).join('')}</div></details>`}
function renderUpdate(){
 const u=state.update, check=button(t('checkUpdates'),'check-updates',{},'','activity');
 let content=u?`<p>${esc(u.message||u.status)}</p>`:`<p class="help">${t('updateChannel')}: ${t(state.preferences.update_channel)}</p>`;
 if(u?.offer){
  content+=`<p class="section-gap"><b>NewPat ${esc(u.offer.version)}</b> · ${esc(u.offer.channel)}</p>`;
  let action=button(t('downloadAndVerify'),'download-update',{},'primary','download');
  if(u.downloaded){
   if(u.offer.asset?.platform?.startsWith('darwin-')){
    content+=`<p>${t('installMacUpdateHelp')}</p><p class="path">${esc(u.downloaded.path)}</p>`;
    action=button(t('showInFinder'),'reveal-update',{},'primary','archive');
   }else action=button(t('installAndClose'),'install-update',{},'primary','check');
  }
  content+=`<div class="actions section-gap">${action}</div>`;
 }
 return `<section class="panel section-gap"><div class="panel-header"><h2>${t('updates')}</h2>${check}</div><div class="panel-body">${content}</div></section>`;
}
function demoExpectedResults(){
 return `<details class="disclosure section-gap"><summary>${t('demoExpected')}</summary><div class="details-body"><p>${t('demoLoci')}</p><p>${t('demoCounts')}</p></div></details>`;
}
function renderExamples(){
 return `<section class="panel section-gap"><div class="panel-body"><h2>${t('sampleDataset')}</h2>
  <p class="section-gap">${t('demoHelp')}</p>${button(t('openDemo'),'open-demo',{},'primary','arrow')}
  ${demoExpectedResults()}
  <p class="section-gap">${t('sampleDatasetHelp')}</p>${button(t('saveExampleData'),'save-example-data',{},'','download')}</div></section>`;
}
function renderEnvironment(){return heading(t('environment'),t('environmentHelp'),button(t('checkEnvironment'),'check-environment',{},'primary','check')+button(t('exportDiagnostics'),'export-diagnostics',{},'','download'))+`<section class="panel"><div class="panel-header"><h2>${t('resourceSettings')}</h2>${button(t('reload'),'load-resources',{},'small','activity')}</div><div class="panel-body">${state.environment?renderResources():empty(t('loading'))}</div></section>${state.environmentCheck?`<div class="section-gap">${notice(L.language==='it'?'Verifica dell’ambiente completata.':'Environment check completed.')}<details class="disclosure"><summary>${t('logs')}</summary><div class="details-body"><pre class="job-log">${esc(state.environmentCheck.logs.join('\n'))}</pre></div></details></div>`:''}${renderUpdate()}${renderInstallation()}${renderExamples()}<section class="panel section-gap"><div class="panel-body"><h2>${t('helpTitle')}</h2><p class="section-gap">${t('helpText')}</p></div></section>`}
function trackIndexFilter(path){return /\.bam$/i.test(path||'')?'bai':/\.cram$/i.test(path||'')?'crai':'tabix'}
function renderIgvNavigation(){
 const v=state.igv,n=v.navigation||{},disabled=v.loaded?'':'disabled',chromosomes=n.chromosomes||v.chromosomes||[];
 const controls=`<div class="igv-navigation-row">${select(t('chromosome'),'igv-chromosome',[['all',t('wholeGenome')],...chromosomes.filter(c=>c.name!=='all').map(c=>[c.name,c.name])],n.chromosome||'all',`data-field="igvChromosome" ${disabled}`)}<div class="field igv-region-field"><label for="igv-locus">${t('region')}</label><div class="file-field"><input id="igv-locus" class="input" value="${esc(v.locus||'all')}" placeholder="${esc(t('regionExample'))}" data-field="igvLocus" ${disabled}><button class="button" data-action="igv-search" ${disabled}>${icon('arrow')}${t('goRegion')}</button></div></div></div><div class="igv-navigation-actions"><div class="actions"><button class="button small" data-action="igv-back" ${v.loaded&&n.canBack?'':'disabled'}>${icon('back')}${t('previousRegion')}</button><button class="button small" data-action="igv-all" ${disabled}>${icon('home')}${t('backToGenome')}</button><button class="button small" data-action="igv-zoom-in" ${v.loaded&&n.canZoom?'':'disabled'} aria-label="${t('zoomIn')}">${icon('plus')}${t('zoomIn')}</button><button class="button small" data-action="igv-zoom-out" ${v.loaded&&n.canZoom?'':'disabled'} aria-label="${t('zoomOut')}">− ${t('zoomOut')}</button></div><button class="button quiet small" data-action="igv-save" ${disabled}>${icon('download')}${t('saveSession')}</button></div>`;
 const wide=n.wholeGenome||Number.isFinite(n.start)&&Number.isFinite(n.end)&&n.end-n.start>=100000;
 const hasAlignment=(v.loadedSources?.tracks||[]).some(track=>/\.(bam|cram)$/i.test(track.path||'')||['bam','cram'].includes(String(track.format||'').toLowerCase()));
 const help=!v.loaded?(!v.reference.fasta?'igvSelectReference':'igvOpenFirst'):!hasAlignment?'igvAddAlignment':wide?'igvZoomHelp':'igvRegionHelp';
 return controls+`<p class="help igv-navigation-help" role="status">${t(help)}</p>`;
}
function syncIgvNavigation(n){
 if(!n)return;state.igv.navigation=n;state.igv.locus=n.locus||'all';
 if(state.view==='igv'&&state.igv.loaded&&$('igv-navigation'))$('igv-navigation').innerHTML=renderIgvNavigation();
}
function renderIGV(){
 const v=state.igv,loaded=v.loadedSources,dirty=v.loaded&&JSON.stringify({reference:v.reference,tracks:v.tracks})!==JSON.stringify({reference:loaded?.reference,tracks:loaded?.tracks});
 const infoLabel=esc(t('igvAbout'));
 const header=`<div class="page-heading"><div><div class="igv-title"><h1>${esc(t('igv'))}</h1><button type="button" class="button igv-info" data-action="igv-about" title="${infoLabel}" aria-label="${infoLabel}">${icon('info')}</button></div><p>${esc(t('igvHelp'))}</p></div></div>`;
 return header+(v.reference?.historical_identity_incomplete?notice(t('historicalReferenceUnverified'),'warning'):'')+`<details class="panel igv-sources" ${v.loaded?'':'open'}><summary>${t('igvFiles')}${v.loaded?` · ${esc(basename(loaded?.reference?.fasta))} · ${loaded?.tracks?.length||0} ${t('tracks').toLowerCase()}`:''}</summary><div class="panel-body"><h2>${t('igvReferenceStep')}</h2><p class="help section-gap">${t('igvReferenceHelp')}</p>${renderReferencePicker('igv')}<div class="section-title"><h2>${t('igvTracksStep')}</h2>${button(t('addTrack'),'igv-add-track',{},'small','plus')}</div><p class="help">${t('igvTrackHelp')}</p>${v.tracks.map((track,i)=>`<div class="igv-track">${input(t('name'),'track-name-'+i,track.name,`data-track-name="${i}"`)}${fileField(t('alignment'),`igv-track.${i}.path`,track.path,'alignment')}${fileField(t(trackIndexFilter(track.path)==='crai'?'cramIndex':trackIndexFilter(track.path)==='tabix'?'annotationIndex':'alignmentIndex'),`igv-track.${i}.index`,track.index,trackIndexFilter(track.path))}${button(t('removeTrack'),'igv-remove-track',{index:i},'quiet small','close')}</div>`).join('')}<div class="actions section-gap">${button(t(v.loaded?'reloadGenome':'loadGenome'),'igv-load',{},'primary','igv')}<span class="help">${t('igvMissing')}</span></div></div></details>${dirty?notice(t('igvUnapplied'),'warning'):''}<section id="igv-navigation" class="panel igv-navigation section-gap" aria-label="${t('igvNavigation')}">${renderIgvNavigation()}</section><div id="igv-container" class="igv-container section-gap">${empty(t('igvNotLoaded'))}</div>`;
}
function render(){if(!state.boot)return;curveViews.clear();const existingIgv=state.view==='igv'&&state.igv.loaded?$('igv-container'):null;renderGeneration++;$('navigation').innerHTML=nav.map((key,i)=>`${i===5?'<div class="nav-divider"></div>':''}<button class="nav-button ${state.view===key?'active':''}" data-action="navigate" data-view="${key}" ${state.view===key?'aria-current="page"':''}>${icon(key)}<span>${t(key)}</span></button>`).join('');$('breadcrumb').textContent='NewPat / '+t(state.view);$('page-back').hidden=state.view==='home';$('version').textContent=state.boot.version;$('language-'+L.language).checked=true;document.querySelectorAll('[data-text]').forEach(el=>el.textContent=t(el.dataset.text));$('job-indicator').textContent=activityIndicator(state.jobs);$('main').innerHTML=({home:renderHome,new:renderNew,archive:renderArchive,activity:renderActivity,catalog:renderCatalog,settings:renderPreferences,environment:renderEnvironment,igv:renderIGV}[state.view]||renderHome)();if(existingIgv){$('igv-container').replaceWith(existingIgv);window.NipatIGV?.resize?.()}}
function refreshPreservingInput(id){const inputElement=$(id),start=inputElement?.selectionStart,value=inputElement?.value;render();const next=$(id);if(next){next.focus();if(typeof start==='number'&&next.setSelectionRange)next.setSelectionRange(start,start)}}
function humanError(error){let message=String(error?.message||error||t('operationError'));message=message.replace(/(Ref_f\.pop|Alt_f\.pop) deve essere finita tra 0 e 1\./g,(_,column)=>column+' '+t('frequencyError'));message=message.replace(/--(dnp|snp)-(contamination-panel|cpi-cutoffs|cpin-panel|popfreq|panel)/g,(_,marker,kind)=>({panel:t('panel'),popfreq:t('population'),'contamination-panel':t('contaminationPanel'),'cpi-cutoffs':t('cpiPanels'),'cpin-panel':t('cpinPanel')}[kind]+' '+marker.toUpperCase()));for(const key of Object.keys(L.fields).sort((a,b)=>b.length-a.length))message=message.replaceAll(key,L.field(key));message=message.replace(/\b(dnp-call|snp-call|contamination|cpin|cpi)\b/g,module=>moduleName(module));return message}
function showError(error){const message=humanError(error);if(state.view==='new'){state.error=message;render()}else toast(message)}
let modalRevision=0,reportCaptureController=null;
function modal(title,body,footer='',backAction=''){modalRevision++;if(!$('modal-root').innerHTML)previousFocus=document.activeElement;$('modal-root').innerHTML=`<div class="modal-backdrop" data-action="modal-backdrop"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><header class="modal-header"><h2 id="dialog-title">${esc(title)}</h2>${backAction?button(t('back'),backAction,{},'small','back'):button(t('close'),'close-modal',{},'small','close')}</header><div class="modal-body">${body}</div>${footer?`<footer class="modal-footer">${footer}</footer>`:''}</section></div>`;$('modal-root').querySelector('button')?.focus()}
function closeModal(){modalRevision++;reportCaptureController?.abort();$('modal-root').innerHTML='';state.modalTable=null;previousFocus?.focus?.();previousFocus=null}
function reportSelection(){
 const field=$('report-cases');
 return Array.from(field.querySelectorAll('input[name="report-case"]'));
}
function updateReportCount(){
 const boxes=reportSelection();
 const selected=boxes.filter(box=>box.checked).length;
 $('report-count').textContent=t('reportSelected')+' '+format(selected,0)+' / '+format(boxes.length,0);
 if(selected&&$('report-status').textContent===t('chooseReportResult'))$('report-status').textContent='';
}
function reportResultFields(cases,selected,includeAll){
 const groups=new Map();
 for(const item of cases){
  const key=item.module+'|'+item.marker;
  if(!groups.has(key))groups.set(key,[]);
  groups.get(key).push(item);
 }
 const fields=Array.from(groups.values(),rows=>{
  const first=rows[0],module=moduleName(first.module);
  const title=first.marker&&!module.endsWith(' '+first.marker)?module+' · '+first.marker:module;
  return `<fieldset class="report-group"><legend>${esc(title)}</legend>`+rows.map(item=>
   `<label class="check-row"><input type="checkbox" name="report-case" value="${esc(item.id)}" ${includeAll||item.id===selected?.id?'checked':''}><span>${esc(item.label.startsWith(title+' · ')?item.label.slice(title.length+3):item.label)}</span></label>`).join('')+'</fieldset>';
 }).join('');
 const actions=cases.length>1?button(t('reportSelectAll'),'report-select',{scope:'all'},'quiet small')+button(t('reportSelectNone'),'report-select',{scope:'none'},'quiet small'):'';
 return `<fieldset id="report-cases" class="choice-fieldset"><legend>${t('reportResult')}</legend><div class="actions report-select-actions">${actions}<span id="report-count" class="help" role="status"></span></div><div class="report-case-list">${fields}</div></fieldset>`;
}
async function chooseReport(){
 const runId=state.runId,language=L.language,version=runLoadVersion,entry=currentEntry();
 modal(t('exportReport'),`<p role="status">${t('loading')}</p>`);
 const revision=modalRevision;
 const current=()=>revision===modalRevision&&version===runLoadVersion&&state.view==='archive'&&state.runId===runId&&L.language===language;
 let result;
 try{result=await rpc('reports.cases',{run_id:runId,language})}
 catch(error){if(current()){closeModal();throw error}return}
 if(!current())return;
 let notes=(result.notes||[]).map(message=>notice(message,'warning')).join('');
 if(!result.cases.length){modal(t('exportReport'),`<p>${t('noReportResults')}</p>`+notes);return}
 const selected=entry&&result.cases.find(item=>item.file_id===entry.file_id&&(item.row_number??null)===(entry.row_number??null));
 if(entry&&!selected)notes=notice(t('reportEntryUnavailable'),'warning')+notes;
 const resultField=reportResultFields(result.cases,selected,!entry);
 const formatField=`<fieldset id="report-kind" class="choice-fieldset"><legend>${t('reportFormat')}</legend><div class="form-row">
  <label class="choice"><input id="report-summary" type="radio" name="report-kind" value="summary" checked><span><b>${t('summaryPdf')}</b><small>${t('summaryPdfHelp')}</small></span></label>
  <label class="choice"><input id="report-detailed" type="radio" name="report-kind" value="detailed"><span><b>${t('detailedPdf')}</b><small>${t('detailedPdfHelp')}</small></span></label>
  <label class="choice"><input id="report-combined" type="radio" name="report-kind" value="combined"><span><b>${t('combinedPdf')}</b><small>${t('combinedPdfHelp')}</small></span></label>
 </div></fieldset>`;
 modal(t('exportReport'),notes+resultField+formatField,'<span id="report-status" class="help" role="status"></span>'+button(t('cancel'),'close-modal')+
  button(t('savePdf'),'save-report',{run:runId,language,revision:version},'primary','download'));
 updateReportCount();
}
async function storeReportPdf(selection,pdf){
 if(pdf.length<=1200000)return rpc('reports.save',{...selection,data_base64:pdf});
 // Decode independently aligned groups to avoid a second full binary string in memory.
 const parts=[];
 for(let i=0;i<pdf.length;i+=65536){
  const chunk=atob(pdf.slice(i,i+65536)),bytes=new Uint8Array(chunk.length);
  for(let j=0;j<chunk.length;j++)bytes[j]=chunk.charCodeAt(j);
  parts.push(bytes);
 }
 const {case_ids,...metadata}=selection;
 metadata.selection=case_ids.length===1?case_ids[0]:'combined';
 const encoded=new TextEncoder().encode(JSON.stringify(metadata));
 const header=btoa(Array.from(encoded,byte=>String.fromCharCode(byte)).join(''));
 const response=await fetch('../report-pdf',{method:'POST',credentials:'same-origin',headers:{
  'Content-Type':'application/pdf','X-NewPat-Report':header},body:new Blob(parts,{type:'application/pdf'})});
 const message=await response.json();
 if(!response.ok||message.error)throw new Error(message.error?.message||t('connectionError'));
 return message.result;
}
async function addReportIgv(bundle,selection,current,signal){
 let views={};
 try{
  const response=await rpc('reports.igv',{run_id:selection.run_id,language:selection.language,case_ids:selection.case_ids});
  views=response.views;
 }catch{/* Archived results remain reportable when IGV inputs are unavailable. */}
 for(const result of bundle.results){
  if(!current())return;
  const view=views?.[result.case_id];
  const reason=[view?.reason||t('reportIgvUnavailable'),view?.site,view?.selection_note].filter(Boolean).join(' ');
  result.igv={reason,site:view?.site||''};
  if(!view?.available)continue;
  try{
   const capture=await window.NewPatReportIGV.capture(view,{language:selection.language,signal});
   if(capture?.image)result.igv={...capture,site:view.site,build:view.build,
    caption:[capture.caption,view.selection_note].filter(Boolean).join(' ')};
  }catch{/* A viewer failure must not discard selected scientific results. */}
 }
}
async function saveReport(data){
 const revision=modalRevision;
 const current=()=>revision===modalRevision&&state.view==='archive'&&state.runId===data.run&&runLoadVersion===Number(data.revision)&&L.language===data.language;
 if(!current())return;
 const field=$('report-cases'),format=$('report-kind'),status=$('report-status');
 if(field.disabled)return;
 const boxes=reportSelection(),caseIds=boxes.filter(box=>box.checked).map(box=>box.value);
 if(!caseIds.length){status.textContent=t('chooseReportResult');boxes[0]?.focus();return}
 const kind=$('report-combined').checked?'combined':$('report-detailed').checked?'detailed':'summary';
 const selection={run_id:data.run,language:data.language,case_ids:caseIds,kind};
 const controller=new AbortController();
 reportCaptureController=controller;
 field.disabled=true;
 format.disabled=true;
 status.textContent=t('preparingPdf');
 try{
  const model=await rpc('reports.prepare',selection);
  if(!current())return;
  if(selection.kind!=='summary'){
   await addReportIgv(model,selection,current,controller.signal);
   if(!current())return;
  }
  const pdf=await window.NewPatReports.render(model,selection.kind);
  if(!current())return;
  status.textContent='';
  const result=await storeReportPdf(selection,pdf);
  if(current()&&!result.cancelled){closeModal();toast(t('reportSaved'))}
 }catch(error){if(current())throw error}
 finally{
  if(reportCaptureController===controller)reportCaptureController=null;
  field.disabled=false;format.disabled=false;status.textContent='';
 }
}
async function loadRun(id,remember=true){const version=++runLoadVersion;++entryLoadVersion;++tableLoadVersion;const [run,overview,files]=await Promise.all([rpc('runs.get',{run_id:id}),rpc('runs.overview',{run_id:id}),rpc('runs.files',{run_id:id})]);if(version!==runLoadVersion)return;if(remember&&(state.view!=='archive'||state.runId!==id||!state.run))rememberPage();state.run=run;state.runId=id;state.overview=overview;state.files=files.files||files;state.runTab='results';state.module=null;state.table=null;state.curves=[];state.entry=0;state.view='archive';render();$('main').focus()}
function fetchEntryCurves(entry){
 return Promise.all((entry.curve_file_ids||[]).map(id=>
  rpc('runs.curve',{run_id:state.runId,file_id:id}).catch(error=>({file:{id},error:humanError(error)}))
 ));
}
async function loadEntry(){const version=++entryLoadVersion;++tableLoadVersion;const context=[state.runId,state.module,state.entry].join('|');const entry=currentEntry();state.table=null;state.tableFile=null;state.curves=[];state.curvePages={};state.curveModes={};state.tableOffset=0;state.tableSearch='';if(!entry){render();return}const group=currentGroup(),file=entry.site_file_id||(group.module.endsWith('-call')?entry.file_id:null);const [table,curves]=await Promise.all([file?rpc('runs.table',{run_id:state.runId,file_id:file,offset:0,limit:100}):null,fetchEntryCurves(entry)]);if(version!==entryLoadVersion||context!==[state.runId,state.module,state.entry].join('|'))return;state.table=table;state.tableFile=file;state.curves=curves;render()}
async function loadTable(offset=0){if(!state.tableFile)return;const version=++tableLoadVersion;const context=[state.runId,state.module,state.entry,state.tableFile].join('|');const table=await rpc('runs.table',{run_id:state.runId,file_id:state.tableFile,offset,limit:100,query:state.tableSearch});if(version!==tableLoadVersion||context!==[state.runId,state.module,state.entry,state.tableFile].join('|'))return;state.table=table;state.tableOffset=offset;render()}
function safeLocalUrl(url){const parsed=new URL(url,location.href);if(parsed.origin!==location.origin||!['http:','https:'].includes(parsed.protocol))throw new Error(t('operationError'));return parsed.href}
function showTableDialog(table){
 state.modalTable=table;
 const pager=`<div class="pager"><span>${format(table.rows.length?table.offset+1:0,0)}–${format(table.offset+table.rows.length,0)} / ${format(table.total,0)} ${t('rows')}</span><div class="actions"><button class="button small" data-action="modal-table-page" data-offset="${Math.max(0,table.offset-100)}" ${!table.offset?'disabled':''}>${t('previous')}</button><button class="button small" data-action="modal-table-page" data-offset="${table.offset+100}" ${table.has_more?'':'disabled'}>${t('next')}</button></div></div>`;
 modal(table.file.label||table.file.name,tableView(table,{compact:true,all:true})+pager,button(t('download'),'export-file',{id:table.file.id},'','download'),'close-modal');
}
async function openFile(id,offset=0){
 const file=state.files.find(item=>item.id===id);if(!file)return;
 const run=state.runId,generation=runLoadVersion;
 if(file.kind==='table'){
  const table=await rpc('runs.table',{run_id:run,file_id:id,offset,limit:100});
  if(generation===runLoadVersion)showTableDialog(table);
 }else if(file.kind==='pdf'){
  const info=await rpc('files.url',{run_id:run,file_id:id});
  if(generation===runLoadVersion)modal(file.label||file.name,`<p class="help">${t('pdfFallback')}</p><iframe class="pdf-preview" src="${esc(safeLocalUrl(info.url))}" title="${esc(file.label||file.name)}"></iframe>`,button(t('download'),'export-file',{id},'','download'),'close-modal');
 }
}
async function navigate(view,{remember=true,keepRun=false}={}){if(!nav.includes(view))return;clearTimeout(archiveSearchTimer);++archiveListVersion;if(remember&&(view!==state.view||view==='archive'&&state.run&&!keepRun))rememberPage();if(view==='home')pageTrail.length=0;if(view!=='activity')visibleLogs.clear();++runLoadVersion;++entryLoadVersion;++tableLoadVersion;if(state.view==='igv'&&view!=='igv'){++igvLoadVersion;igvNavigationUnsubscribe?.();igvNavigationUnsubscribe=null;window.NipatIGV?.dispose();state.igv.loaded=false}state.error='';state.view=view;if(view==='archive'&&!keepRun){state.run=null;state.archiveListing=null}render();$('main').focus();try{if(['home','archive'].includes(view)){await refreshVisibleRuns()}else if(view==='activity'){const jobs=await rpc('jobs.list',{include_logs:false});state.jobs=jobs.jobs||jobs;if(state.view===view)render()}else if(view==='new'||view==='igv'){await loadReferenceEntries();if(state.view===view)render()}else if(view==='environment'){const results=await Promise.allSettled([rpc('resources.get'),rpc('installation.get')]);if(results[0].status==='fulfilled')state.environment=results[0].value;else showError(results[0].reason);if(results[1].status==='fulfilled')state.installation=results[1].value;if(state.view===view)render()}}catch(error){showError(error)}}
async function savePreferences(){const saved=await rpc('preferences.save',{preferences:state.preferences,baseline:state.baseline});if(saved.runs_dir!==state.baseline.runs_dir){++archiveListVersion;state.recentRuns=[];state.archiveListing=null;state.archivePage=0}state.preferences=clone(saved);state.baseline=clone(saved);await rpc('ui.save',{preferences:{language:L.language,reduce_motion:!state.motion}});toast(t('saved'))}
async function persistProfile(name,remove=false){
 const baseline=state.baseline;
 let profiles={...baseline.parameter_profiles};
 let defaultProfile=baseline.default_profile||'';
 if(remove){
  delete profiles[name];
  if(defaultProfile===name)defaultProfile='';
 }else{
  const snapshot=clone({scientific_settings:state.draft.scientific_settings,execution:state.draft.execution});
  delete snapshot.execution.performance_diagnostics;
  profiles={...profiles,[name]:snapshot};
 }
 const requested={...baseline,parameter_profiles:profiles,default_profile:defaultProfile};
 // Persist the named profile independently from unsaved edits in Settings.
 try{
  const saved=await rpc('preferences.save',{preferences:requested,baseline});
  const nextBaseline=clone(saved);
  for(const [key,value] of Object.entries(saved)){
   if(key==='parameter_profiles'||JSON.stringify(state.preferences[key])===JSON.stringify(baseline[key])){
    state.preferences[key]=clone(value);
   }else if(Object.hasOwn(baseline,key)){nextBaseline[key]=clone(baseline[key]);}
  }
  if(remove&&state.preferences.default_profile===name)state.preferences.default_profile='';
  if(remove&&nextBaseline.default_profile===name)nextBaseline.default_profile='';
  state.baseline=nextBaseline;state.profileChoice=remove?'':name;
  closeModal();render();toast(t('saved'));
 }catch(error){closeModal();throw error;}
}
function showConfirmation(title,message,action,data={}){modal(title,`<p>${esc(message)}</p>`,button(t('cancel'),'close-modal')+button(title,action,data,'primary'))}
function safeSampleId(path,kind){let name=basename(path).replace(/\.[^.]+$/,'').replace(/[^A-Za-z0-9_-]/g,'_');if(!/^[A-Za-z]/.test(name))name='S_'+name;name=name.slice(0,42)||'Sample';let candidate=name,n=2;while(state.draft.samples.some(s=>s.id.toLowerCase()===candidate.toLowerCase()&&(s.kind===kind||(!s.kind.endsWith('-table')&&!kind.endsWith('-table')))))candidate=name+'_'+n++;return candidate}
async function action(name,data,element){
 if(['reference-register','reference-download','reference-cancel'].includes(name))return referenceAction(name,data);
 if(name==='page-back')return pageBack();
 if(name==='back-to-table'&&state.modalTable)return showTableDialog(state.modalTable);
 if(name==='navigate'){
  if(data.view==='catalog')state.catalogDefaults=false;
  return data.view==='new'?newExperiment():navigate(data.view);
 }
 if(name==='new-experiment')return newExperiment();
 if(name==='archive-page')return requestArchivePage(Math.max(0,Number(data.page)));
 if(name==='retry-boot')return boot();
 if(name==='close-modal')return closeModal();
 if(name==='modal-backdrop'){closeModal();return}
 if(name==='choose-path'){await choosePath(data.key,data.filter);render();return}
 if(name==='clear-path'){setPath(data.key,null);render();return}
 if(name==='add-samples'){const kind=state.sampleKind,draft=state.draft,revision=draftRevision;let paths;try{paths=await choosePath(null,kind==='bam'?'bam':kind==='snp-pileup'?'pileup':'table',true)}catch(error){if(draft===state.draft&&revision===draftRevision)throw error;return}if(draft!==state.draft||revision!==draftRevision)return;for(const path of paths){if(state.draft.samples.some(s=>s.path===path&&s.kind===kind))continue;state.draft.samples.push({id:safeSampleId(path,kind),path,kind})}if(paths.length)invalidate();render();return}
 if(name==='remove-sample'){state.draft.samples.splice(Number(data.index),1);invalidate();render();return}
 if(name==='step'){const next=Number(data.index);if(next>state.step&&(!state.draft.name.trim()||!state.draft.samples.length)){state.error=t('inputRequired');render();return}state.step=next;state.error='';render();return}
 if(name==='add-family'){const rows=state.draft.families[data.module];let n=rows.length+1;while(rows.some(r=>r.id==='Family_'+n))n++;rows.push({id:'Family_'+n,mother:'',father:'',...(data.module==='cpin'?{child:''}:{})});invalidate();render();return}
 if(name==='remove-family'){state.draft.families[data.module].splice(Number(data.index),1);invalidate();render();return}
 if(name==='add-cutoff'){const r=state.draft.resources[data.marker];r.cpi_cutoffs??=[];r.cpi_cutoffs.push({label:'Panel_'+(r.cpi_cutoffs.length+1),path:''});invalidate();render();return}
 if(name==='remove-cutoff'){state.draft.resources[data.marker].cpi_cutoffs.splice(Number(data.index),1);invalidate();render();return}
 if(name==='reset-param'){const target=data.scope==='defaults'?(state.preferences.scientific_settings[data.module]??={}):state.draft.scientific_settings[data.module];target[data.key]=state.settings[data.module].parameters[data.key].default;invalidate();render();return}
 if(name==='validate-plan'){state.error='';const revision=draftRevision,draft=state.draft;let result;try{result=await rpc('plan.preview',{draft:submittedDraft()})}catch(error){if(draft===state.draft&&revision===draftRevision)throw error;return}if(draft!==state.draft)return;if(revision!==draftRevision){toast(L.language==='it'?'La configurazione è cambiata. Verificala di nuovo.':'Configuration changed. Validate it again.');return}state.preview=result;render();return}
 if(name==='start-analysis'){
  const draft=state.draft,revision=draftRevision;
  if(startingDraft)return;
  startingDraft=draft;state.error='';render();
  const current=()=>draft===state.draft&&revision===draftRevision;
  try{
   const preview=state.preview||await rpc('plan.preview',{draft:submittedDraft()});
   if(!current())return;
   const job=await rpc('analysis.start',{preview_id:preview.preview_id});
   state.jobs=[job,...state.jobs.filter(item=>item.id!==job.id)];
   if(current()&&state.view==='new'){rememberPage();state.view='activity';render();$('main').focus()}
   await refreshVisibleRuns();
  }catch(error){if(current())throw error}
  finally{startingDraft=null;if(current())state.preview=null;if(state.view==='new')render()}
  return;
 }
 if(name==='job-log'){
  const job=state.jobs.find(item=>item.id===data.id);if(!job)return;
  if(visibleLogs.has(job.id))visibleLogs.delete(job.id);
  else visibleLogs.set(job.id,{revision:null,lines:[],busy:false,error:''});
  const toggle=document.querySelectorAll('[data-action="job-log"]');
  const control=[...toggle].find(button=>button.dataset.id===job.id);
  const area=$('job-log-'+job.id),entry=visibleLogs.get(job.id);
  if(control&&area){control.setAttribute('aria-expanded',String(!!entry));area.hidden=!entry;area.textContent=entry?logText(entry):''}
  if(entry)await refreshJobLog(job);
  return;
 }
 if(name==='refresh-jobs'){const jobs=await rpc('jobs.list',{include_logs:false});state.jobs=jobs.jobs||jobs;render();return}
 if(name==='cancel-job'){showConfirmation(t('stopAnalysis'),t('stopConfirm'),'confirm-cancel-job',{id:data.id});return}
 if(name==='remove-job'){const job=state.jobs.find(job=>job.id===data.id);showConfirmation(t('removeFromList'),t(job?.run_id?'removeRunConfirm':'dismissJobConfirm'),'confirm-remove-job',{id:data.id});return}
 if(name==='confirm-remove-job'){
  const job=state.jobs.find(item=>item.id===data.id);
  const removed=await rpc('jobs.remove',{job_id:data.id});
  if(removed.run_id&&job?.results_root)forgetRunPages(removed.run_id,job.results_root);
  if(removed.archive_id)forgetRunPages(removed.archive_id);
  visibleLogs.delete(data.id);closeModal();
  await Promise.all([loadRuns(),action('refresh-jobs',{})]);
  render();toast(t('removedFromList'));return;
 }
 if(name==='confirm-cancel-job'){await rpc('jobs.cancel',{job_id:data.id});closeModal();const jobs=await rpc('jobs.list',{include_logs:false});state.jobs=jobs.jobs||jobs;render();return}
 if(name==='open-run'){
  if(!data.job)return loadRun(data.id);
  const version=++runLoadVersion,result=await rpc('jobs.result_id',{job_id:data.job});
  if(version===runLoadVersion)return loadRun(result.run_id);
  return;
 }
 if(name==='import-run'){const paths=await choosePath(null,'directory');if(paths.length){const result=await rpc('runs.import',{path:paths[0]});const id=result.imported?.[0];if(id)return loadRun(id);await navigate('archive')}return}
 if(name==='run-tab'){state.runTab=data.tab;render();return}
 if(name==='result-module'){++entryLoadVersion;++tableLoadVersion;state.module=data.module||null;state.entry=0;state.tableSearch='';if(state.module&&state.module!=='files')await loadEntry();else render();return}
 if(name==='table-page')return loadTable(Number(data.offset));
 if(name==='open-file')return openFile(data.id);
 if(name==='export-file'){await rpc('files.export',{run_id:state.runId,file_id:data.id});return}
 if(name==='choose-report')return chooseReport();
 if(name==='report-select'){
  for(const box of reportSelection())box.checked=data.scope==='all';
  updateReportCount();
  return;
 }
 if(name==='save-report')return saveReport(data);
 if(name==='export-run'){await rpc('runs.export',{run_id:state.runId});return}
 if(name==='open-run-directory'){await rpc('runs.open_directory',{run_id:data.id});return}
 if(name==='open-demo'||name==='confirm-open-demo'){
  if(name==='open-demo'&&demoRevision!==draftRevision&&JSON.stringify(state.draft)!==JSON.stringify(blankDraft())){
   showConfirmation(t('openDemo'),t('demoReplace'),'confirm-open-demo');return;
  }
  closeModal();
  const version=++draftLoadVersion,revision=draftRevision,page=runLoadVersion;
  const current=()=>version===draftLoadVersion&&revision===draftRevision&&page===runLoadVersion&&state.view==='environment';
  try{
   const {draft}=await rpc('examples.demo',{language:L.language});
   if(!current())return;
   const preview=await rpc('plan.preview',{draft});
   if(!current())return;
   applyDraft(draft);
   demoRevision=draftRevision;state.preview=preview;state.step=3;
   return navigate('new');
  }catch(error){if(current())throw error}
  return;
 }
 if(name==='save-example-data'){
  const result=await rpc('examples.save',{language:L.language});
  if(!result.cancelled&&result.path)modal(t('exampleSaved'),`<p class="path">${esc(result.path)}</p>`);
  return;
 }
 if(name==='export-diagnostics'){const result=await rpc('diagnostics.export',data.id?{run_id:data.id}:{});if(!result.cancelled&&result.path)toast(t('diagnosticsSaved'));return}
 if(name==='curve-mode'){if(['combined','separate'].includes(data.mode)&&state.curves.some(item=>item.file.id===data.id&&!item.error)){state.curveModes[data.id]=data.mode;render()}return}
 if(name==='curve-page'){const curve=state.curves.find(item=>item.file.id===data.id);if(curve&&!curve.error){state.curvePages[data.id]=Math.max(0,Math.min(Number(data.page)||0,Math.ceil(curve.rows.length/1000)-1));render()}return}
 if(name==='row-details'){const version=runLoadVersion,entryVersion=entryLoadVersion;const table=await rpc('runs.table',{run_id:state.runId,file_id:data.file,offset:Number(data.row),limit:1});if(version===runLoadVersion&&entryVersion===entryLoadVersion&&table.rows[0])modal(t('siteDetails'),resultRowDetails(table.rows[0],table.columns),button(t('download'),'export-file',{id:data.file},'','download'),state.modalTable?.file.id===data.file&&$('modal-root').innerHTML?'back-to-table':'close-modal');return}
 if(name==='modal-table-page')return openFile(state.modalTable.file.id,Number(data.offset));
 if(name==='reuse-run'){const version=++draftLoadVersion,revision=draftRevision;let result;try{result=await rpc('run.reuse',{run_id:data.id||state.runId})}catch(error){if(version===draftLoadVersion&&revision===draftRevision)throw error;return}if(version!==draftLoadVersion||revision!==draftRevision)return;applyDraft(result);await navigate('new');toast(t('rerunHelp'));return}
 if(name==='remove-run'){showConfirmation(t('removeFromList'),t('removeRunConfirm'),'confirm-remove-run',{id:data.id||state.runId});return}
 if(name==='confirm-remove-run'){await rpc('runs.remove',{run_id:data.id});const jobs=await rpc('jobs.list',{include_logs:false});state.jobs=jobs.jobs||jobs;closeModal();forgetRunPages(data.id);if(state.runId===data.id){state.run=null;state.runId=null;state.module=null}await loadRuns();render();toast(t('removedFromList'));return}
 if(name==='run-igv'){const version=runLoadVersion;const selection=await rpc('run.igv',{run_id:state.runId,...(data.locus?{locus:data.locus}:{})});if(version!==runLoadVersion||state.view!=='archive')return;rememberPage();closeModal();state.igv={reference:selection.reference,tracks:selection.tracks,locus:selection.locus||'all',loaded:false,padResultLocus:!!data.locus};await navigate('igv',{remember:false});return action('igv-load',{})}
 if(name==='prepare-module'){const caller=data.module.endsWith('-call'),version=++draftLoadVersion,revision=draftRevision;let result;try{result=await rpc(caller?'run.reuse':'run.prepare',{run_id:state.runId,...(caller?{}:{module:data.module})})}catch(error){if(version===draftLoadVersion&&revision===draftRevision)throw error;return}if(version!==draftLoadVersion||revision!==draftRevision)return;applyDraft(result);if(caller){state.draft.caller=data.module.startsWith('dnp')?'dnp':'snp';state.source='bam';state.draft.samples=state.draft.samples.filter(sample=>sample.kind==='bam'||state.draft.caller==='snp'&&sample.kind==='snp-pileup');state.draft.branches={DNP:[],SNP:[]}}else state.step=1;return navigate('new')}
 if(name==='edit-defaults'){state.catalogDefaults=true;state.catalogType='parameters';state.catalogSearch='';return navigate('catalog')}
 if(name==='apply-profile'){
  const settings=profileSettings(state.profileChoice);
  settings.execution.performance_diagnostics=state.draft.execution.performance_diagnostics;
  Object.assign(state.draft,settings);
  invalidate();render();toast(t('profileApplied'));return;
 }
 if(name==='new-profile'){
  modal(t('saveAsProfile'),input(t('profileName'),'profile-name',state.profileChoice||'','maxlength="80" required',t('profileScope')),
   button(t('cancel'),'close-modal')+button(t('saveProfile'),'save-profile',{},'primary'));
  $('profile-name').focus();return;
 }
 if(name==='save-profile'){
  const name=$('profile-name').value.trim();
  if(!name){$('profile-name').value='';$('profile-name').reportValidity();return;}
  if(Object.hasOwn(state.baseline.parameter_profiles||{},name)){
   showConfirmation(t('replaceProfile'),t('replaceProfileQuestion')+' '+name,'confirm-save-profile',{name});return;
  }
  return persistProfile(name);
 }
 if(name==='confirm-save-profile')return persistProfile(data.name);
 if(name==='remove-profile'){
  showConfirmation(t('removeProfile'),t('removeProfileQuestion')+' '+data.name,'confirm-remove-profile',{name:data.name});return;
 }
 if(name==='confirm-remove-profile')return persistProfile(data.name,true);
 if(name==='save-preferences')return savePreferences();
 if(name==='load-resources'){state.environment=await rpc('resources.get');render();return}
 if(name==='check-environment'){state.environmentCheck=await rpc('environment.check',{check_runtime:true});state.environment=await rpc('resources.get');render();return}
 if(name==='preview-resources'){state.resourcePreview=await rpc('resources.preview',{memory_mib:Number(state.runtimeMemory??state.environment.runtime.configured.memory_mib),cpus:Number(state.runtimeCpus??state.environment.runtime.configured.cpus)});const r=state.resourcePreview;modal(t('resourceConfirm'),`<dl class="review-list"><dt>RAM · MiB</dt><dd>${format(r.before?.memory_mib,0)} → ${format(r.after.memory_mib,0)}</dd><dt>CPU</dt><dd>${format(r.before?.cpus,0)} → ${format(r.after.cpus,0)}</dd></dl>${(r.warnings||[]).map(w=>notice(w,'warning')).join('')}${r.affected_running?.length?`${notice(t('resourceRestart'),'warning')}<p class="section-gap">${esc(r.affected_running.join(', '))}</p><label class="check-row"><input type="checkbox" id="confirm-resource-restart"><span>${L.language==='it'?'Confermo il riavvio degli ambienti indicati':'I confirm restarting the listed environments'}</span></label>`:''}`,button(t('cancel'),'close-modal')+button(t('applyResources'),'apply-resources',{},'primary'));return}
 if(name==='apply-resources'){const restart=!!$('confirm-resource-restart')?.checked;const result=await rpc('resources.apply',{preview_id:state.resourcePreview.preview_id,confirmed:true,restart_confirmed:restart});closeModal();state.environment=await rpc('resources.get');state.resourcePreview=null;render();if(result.status==='saved-restart-required')toast(t('resourceRestart'));else toast(t('saved'));return}
 if(name==='check-updates'){state.update=await rpc('updates.check',{channel:state.preferences.update_channel});render();return}
 if(name==='download-update'){const offerId=state.update.offer_id;const downloaded=await rpc('updates.download',{offer_id:offerId});if(state.update?.offer_id===offerId)state.update.downloaded=downloaded;render();return}
 if(name==='reveal-update'){
  try{await rpc('updates.reveal',{offer_id:state.update.offer_id})}
  catch{throw new Error(t('showInFinderFailed'))}
  return;
 }
 if(name==='install-update'){showConfirmation(L.language==='it'?'Installa aggiornamento':'Install update',L.language==='it'?`Installare NewPat ${state.update.offer.version} e chiudere l’app?`:`Install NewPat ${state.update.offer.version} and close the app?`,'confirm-install-update');return}
 if(name==='confirm-install-update'){const r=await rpc('updates.install',{offer_id:state.update.offer_id,confirmed:true});closeModal();if(r.close_required)await rpc('app.close');return}
 if(name==='maintain'){const item=[...(state.installation.runtimes||[]),...(state.installation.cache||[])].find(i=>i.id===data.target)||state.installation.recovery;showConfirmation(data.operation==='cleanup'?t('remove'):(L.language==='it'?'Ripara installazione':'Repair installation'),`${item.name||''} ${item.path||''}\n${item.reason||''}\n${L.language==='it'?'NewPat verrà chiuso per questa operazione.':'NewPat will close for this operation.'}`,'confirm-maintain',{operation:data.operation,target:data.target});return}
 if(name==='confirm-maintain'){const r=await rpc('installation.maintain',{operation:data.operation,target:data.target,confirmed:true});closeModal();if(r.close_required)await rpc('app.close');return}
 if(name==='igv-about'){
  const result=await rpc('igv.about');
  if(!result.opened)throw new Error(t('igvAboutFailed'));
  return;
 }
 if(name==='igv-add-track'){state.igv.tracks.push({name:'',path:'',index:''});render();return}
 if(name==='igv-remove-track'){state.igv.tracks.splice(Number(data.index),1);render();return}
 if(name==='igv-load'){
  const version=++igvLoadVersion;igvNavigationUnsubscribe?.();igvNavigationUnsubscribe=null;window.NipatIGV?.dispose();state.igv.loaded=false;state.igv.navigation=null;render();$('igv-container').innerHTML=empty(t('viewerLoading'));
  const request=clone({reference:state.igv.reference,tracks:state.igv.tracks,locus:state.igv.locus||'all'});
  try{
   const prepared=await rpc('igv.prepare',request);if(state.view!=='igv'||version!==igvLoadVersion)return;
   if(state.igv.padResultLocus){const match=/^([^:]+):(\d+)-(\d+)$/.exec(prepared.locus||'');const chromosome=match&&(prepared.chromosomes||[]).find(c=>c.name===match[1]);if(chromosome)prepared.locus=chromosome.name+':'+Math.max(1,Number(match[2])-50)+'-'+Math.min(chromosome.length,Number(match[3])+50);state.igv.padResultLocus=false;}
   window.NipatIGV.setLanguage(L.language);await window.NipatIGV.mount($('igv-container'),prepared);if(state.view!=='igv'||version!==igvLoadVersion)return;
   state.igv.loaded=true;state.igv.loadedSources=clone(prepared.sources||request);state.igv.reference=clone(state.igv.loadedSources.reference);state.igv.tracks=clone(state.igv.loadedSources.tracks);state.igv.chromosomes=prepared.chromosomes||[];
   state.igv.navigation=window.NipatIGV.getNavigation?.()||{locus:prepared.locus||'all',chromosome:'all',chromosomes:state.igv.chromosomes,wholeGenome:true};state.igv.locus=state.igv.navigation.locus;
   render();igvNavigationUnsubscribe=window.NipatIGV.onNavigation?.(syncIgvNavigation);
  }catch(error){if(state.view==='igv'&&version===igvLoadVersion){state.igv.loaded=false;$('igv-container').innerHTML=notice(humanError(error),'error')}throw error}return;
 }
 if(name==='igv-search'){await window.NipatIGV.search(state.igv.locus);return}
 if(name==='igv-all'){await window.NipatIGV.wholeGenome();return}
 if(name==='igv-back'){await window.NipatIGV.back();return}
 if(name==='igv-zoom-in'){await window.NipatIGV.zoomIn();return}
 if(name==='igv-zoom-out'){await window.NipatIGV.zoomOut();return}
 if(name==='igv-save'){const snapshot=await window.NipatIGV.exportSession(),sources=state.igv.loadedSources||state.igv;await rpc('igv.session.save',{session:{schema_version:1,reference:sources.reference,tracks:sources.tracks,locus:snapshot.locus||state.igv.locus,view:snapshot}});return}
}
function onValue(target){const value=target.type==='checkbox'?target.checked:target.value;
 if(target.name==='report-case'){updateReportCount();return}
 if(target.dataset.referenceBuild)return chooseReferenceBuild(target.dataset.referenceBuild,value).catch(showError);
 if(target.dataset.referenceEntry)return selectReferenceEntry(target.dataset.referenceEntry,value).catch(showError);
 if(target.dataset.draft){state.draft[target.dataset.draft]=value;invalidate();if(target.dataset.draft==='caller')render();return}
 if(target.dataset.sample!==undefined){state.draft.samples[Number(target.dataset.sample)].id=value;invalidate();return}
 if(target.dataset.family){const [m,index,key]=target.dataset.family.split('|');state.draft.families[m][Number(index)][key]=value;invalidate();return}
 if(target.dataset.branch){const [marker,module]=target.dataset.branch.split('|'),branch=state.draft.branches[marker];if(value&&!branch.includes(module))branch.push(module);if(!value)state.draft.branches[marker]=branch.filter(m=>m!==module);invalidate();render();return}
 if(target.dataset.cutoff){const [m,index]=target.dataset.cutoff.split('|');state.draft.resources[m].cpi_cutoffs[Number(index)].label=value;invalidate();return}
 if(target.dataset.parameter){const [module,key,scope]=target.dataset.parameter.split('|');const def=state.settings[module].parameters[key];const v=def.type==='boolean'?!!value:def.type==='string'?value:value===''?null:Number(value);const dest=scope==='defaults'?(state.preferences.scientific_settings[module]??={}):state.draft.scientific_settings[module];dest[key]=v;invalidate();return}
 if(target.dataset.flag){const [module,bit,scope]=target.dataset.flag.split('|');const dest=scope==='defaults'?(state.preferences.scientific_settings[module]??={}):state.draft.scientific_settings[module];const current=dest.excluded_flags??state.settings[module].parameters.excluded_flags.default;dest.excluded_flags=value?current|Number(bit):current&~Number(bit);invalidate();render();return}
 if(target.dataset.execution){const [key,scope]=target.dataset.execution.split('|');const dest=scope==='defaults'?state.preferences.execution:state.draft.execution;dest[key]=['execution_mode','input_hashes'].includes(key)?value:key==='performance_diagnostics'?!!value:value===''?null:Number(value);invalidate();return}
 if(target.dataset.preference){state.preferences[target.dataset.preference]=value;return}
 if(target.dataset.trackName!==undefined){state.igv.tracks[Number(target.dataset.trackName)].name=value;return}
 if(target.dataset.field){const key=target.dataset.field;if(key==='source'){state.source=value;state.draft.caller=value==='tables'?'tables':state.draft.caller==='tables'?'dnp':state.draft.caller;state.sampleKind=value==='tables'?'dnp-table':'bam';if(value==='tables'){state.draft.samples=state.draft.samples.filter(s=>s.kind.endsWith('-table'));state.draft.reference=null;delete state.draft.reference_id;delete state.draft.reference_genome;referenceForms.delete(state.draft)}else if(value==='bam')state.draft.samples=state.draft.samples.filter(s=>!s.kind.endsWith('-table'));invalidate();render()}else if(key==='igvLocus'){state.igv.locus=value}else if(key==='igvChromosome'){window.NipatIGV.search(value).catch(showError)}else if(key==='runtimeMemory'||key==='runtimeCpus'){state[key]=value;state.resourcePreview=null}else{state[key]=value;if(key==='archiveStatus'||key==='archiveMarker')return requestArchivePage(0).catch(showError);if(key==='sampleKind'&&value==='snp-pileup'&&state.draft.caller==='dnp'){state.draft.caller='snp';invalidate()}if(key!=='motion')render();else rpc('ui.save',{preferences:{language:L.language,reduce_motion:!value}}).catch(showError)}return}
 if(target.dataset.result){if(target.dataset.result==='module'){state.module=value;state.entry=0}else state.entry=Number(value);loadEntry().catch(showError);return}
}
let languageWrite=Promise.resolve();
async function changeLanguage(language){
 const preferences={language,reduce_motion:!state.motion};
 // Native radio arrows can change the selection again before the first save finishes.
 const write=languageWrite.catch(()=>{}).then(()=>rpc('ui.save',{preferences}));
 languageWrite=write;
 try{await write}catch(error){
  if(write===languageWrite)render();
  throw error;
 }
 L.setLanguage(language);
 window.NipatIGV?.setLanguage(L.language);
 if(write!==languageWrite)return;
 if(state.view==='archive'&&state.run){
  const page=pageLocation(),version=runLoadVersion+1;
  await loadRun(page.runId,false);
  if(version===runLoadVersion&&write===languageWrite)await restoreResultsPage(page);
 }else{
  render();
  await refreshVisibleRuns();
 }
}
function bind(){
 document.addEventListener('mouseover',event=>showCurvePoint(event.target,event));
 document.addEventListener('focusin',event=>showCurvePoint(event.target));
 document.addEventListener('mouseout',event=>{const point=event.target.closest?.('[data-curve-point]');if(point&&!point.contains?.(event.relatedTarget))hideCurvePoint(point)});
 document.addEventListener('focusout',event=>hideCurvePoint(event.target));
 document.addEventListener('click',async event=>{if(showCurvePoint(event.target,event))event.target.closest('[data-curve-point]').focus();const element=event.target.closest('[data-action]');if(!element||element.disabled)return;if(element.dataset.action==='modal-backdrop'){if(event.target===element)closeModal();return}event.preventDefault();const actionName=element.dataset.action;const longAction=['open-demo','confirm-open-demo','validate-plan','start-analysis','import-run','reuse-run','run-igv','confirm-remove-run','prepare-module','check-environment','check-updates','download-update','igv-load','export-diagnostics','reference-register','save-report'].includes(actionName);try{element.disabled=true;if(longAction){$('operation-indicator').textContent=t('loading');element.setAttribute?.('aria-busy','true');}await action(actionName,element.dataset,element)}catch(error){showError(error)}finally{element.disabled=false;if(longAction){$('operation-indicator').textContent='';element.removeAttribute?.('aria-busy');}}});
 document.addEventListener('change',event=>{if(event.target.name==='language'&&event.target.checked){changeLanguage(event.target.value).catch(showError);return}onValue(event.target)});
 document.addEventListener('input',event=>{const el=event.target;if(el.dataset.search){clearTimeout(searchTimer);const kind=el.dataset.search;const value=el.value;if(kind==='archive'){state.archiveSearch=value;requestArchivePage(0,true)}else if(kind==='catalog'){state.catalogSearch=value;refreshPreservingInput('catalog-search')}else{state.tableSearch=value;searchTimer=setTimeout(()=>loadTable(0).then(()=>$('site-search')?.focus()).catch(showError),300)}return}if(el.tagName==='INPUT'&&!['checkbox','radio'].includes(el.type))onValue(el)});
 document.addEventListener('keydown',event=>{if(curveKey(event))return;const dialog=$('modal-root').querySelector('[role=dialog]');if(dialog){if(event.key==='Escape'){closeModal();return}if(event.key==='Tab'){const nodes=[...dialog.querySelectorAll('button,input,select,summary,[tabindex="0"]')].filter(n=>!n.disabled);const first=nodes[0],last=nodes[nodes.length-1];if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus()}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus()}}}else if(event.key==='Enter'&&event.target.id==='igv-locus'){event.preventDefault();action('igv-search',{}).catch(showError)}});
}
async function refreshOpenedRun(){
 const id=state.runId,version=runLoadVersion;
 if(state.view!=='archive'||!state.run||!id||$('modal-root').innerHTML)return;
 const [run,overview,files]=await Promise.all([rpc('runs.get',{run_id:id}),rpc('runs.overview',{run_id:id}),rpc('runs.files',{run_id:id})]);
 if(version!==runLoadVersion||state.view!=='archive'||state.runId!==id||!state.run||$('modal-root').innerHTML)return;
 const changed=JSON.stringify([run,overview,files.files||files])!==JSON.stringify([state.run,state.overview,state.files]);
 state.run=run;state.overview=overview;state.files=files.files||files;
 if(changed){
  // Keep the selected tab, module, sample, search and page while updating live outputs.
  if(state.module&&state.module!=='files'){const entry=currentEntry();if(!state.tableFile&&entry)await loadEntry();else if(state.tableFile)await loadTable(state.tableOffset);else render()}else render();
 }
}
async function poll(){
 try{
  await pollReferenceDownloads().catch(()=>{});
  const jobs=await rpc('jobs.list',{include_logs:false});
  const archiveKeys=rows=>JSON.stringify(rows.map(job=>[job.id,job.run_id,job.status]));
  const before=archiveKeys(state.jobs);state.jobs=jobs.jobs||jobs;
  $('job-indicator').textContent=activityIndicator(state.jobs);
  if(state.view==='activity'&&!$('modal-root').innerHTML&&!updateActivity()){
   render();
  }
  if(state.view==='activity'&&visibleLogs.size){
   await Promise.all(state.jobs.filter(job=>visibleLogs.has(job.id)).map(refreshJobLog));
  }
  const listing=state.view==='home'||state.view==='archive'&&!state.run;
  const rows=state.view==='home'?state.recentRuns:(state.archiveListing?.runs||[]);
  const checking=rows.some(run=>run.status_reason==='checking')||(state.view==='archive'&&state.archiveListing?.checking_status);
  if(listing&&(before!==archiveKeys(state.jobs)||checking))await refreshVisibleRuns();
  if(state.view==='archive'&&state.run&&(!terminal(state.run)||state.jobs.some(j=>!terminal(j)&&j.run_id===state.runId)))await refreshOpenedRun();
 }catch{/* A transient poll error must not replace work in progress. */}
 finally{pollTimer=setTimeout(poll,state.jobs.some(j=>!terminal(j))||[...referenceDownloads.values()].some(activeTransfer)?1500:5000)}
}
async function boot(){delete document.documentElement.dataset.nipatReady;try{const data=await rpc('bootstrap');state.view='home';state.boot=data;state.settings=data.settings?.workflows||data.settings||{};state.preferences=clone(data.preferences);state.preferences.scientific_settings??={};state.preferences.execution??={};state.baseline=clone(data.preferences);state.jobs=data.jobs||[];state.motion=!data.ui?.reduce_motion;L.setLanguage(data.ui?.language||'it');applyDraft(blankDraft());state.profileChoice=state.baseline?.default_profile||'';await loadRuns();render();document.documentElement.dataset.nipatReady='true';clearTimeout(pollTimer);pollTimer=setTimeout(poll,1500);if(state.preferences.check_updates_on_startup){rpc('updates.check',{channel:state.preferences.update_channel}).then(result=>{state.update=result;if(result.offer)toast(result.message)}).catch(()=>{})}}catch(error){$('main').innerHTML=heading(t('loadingFailed'))+notice(humanError(error),'error')+`<div class="actions section-gap">${button(t('retry'),'retry-boot',{},'primary')}</div>`}}
window.NipatApp={state,rpc,boot,render,navigate,action,onValue,activeMarkers,selectedModules,blankDraft,normalizeDraft,submittedDraft,loadRuns,parameterVisible,range,choiceLabel,metricValue,resultCell,shownColumns,curveChart,curvePointDetails,curveDefinition,combinedCurveScale,renderCurve,constantValue,genotypeBars,jobProgress,terminal,safeSampleId,missing:absent,number,esc,changeLanguage,loadRun,loadEntry,loadTable,renderRun,renderNew,renderActivity,updateActivity,elapsedTime,rowLocus,renderIGV,renderIgvNavigation,syncIgvNavigation,refreshOpenedRun,poll};
bind();boot();
})();
