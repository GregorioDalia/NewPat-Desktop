/* Contract and state tests for the desktop frontend. No browser layout claims. */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),web=path.join(root,'src/nipat/gui/web');
const settings=JSON.parse(fs.readFileSync(path.join(root,'src/nipat_scientific/settings_data.json'),'utf8'));
const events={},elements=new Map(),requests=[],checks=[];let dialogPaths=[],jobs=[],navigationCallback=null;
function element(id){if(!elements.has(id))elements.set(id,{id,innerHTML:'',textContent:'',value:'',checked:false,style:{},dataset:{},classList:{add(){},remove(){}},focus(){document.activeElement=this},querySelector(){return element('modal-button')},querySelectorAll(){return[]},setSelectionRange(){},replaceWith(){},appendChild(){},remove(){}});return elements.get(id)}
const document={getElementById:element,documentElement:{lang:'it',dataset:{}},activeElement:null,querySelectorAll(){return[]},addEventListener(type,cb){(events[type]??=[]).push(cb)}};
const files=[{id:'calling',name:'SNPcall_output.txt',kind:'table',label:'Conteggi e genotipi',module:'snp-call',marker:'SNP',sample_id:'A',sample_label:'A',canonical:true,size_bytes:300,relative_path:'output/SNPcall_output.txt'},{id:'cpi-summary',name:'Summary_FetalFraction_CPI.csv',kind:'table',label:'CPI prenatale',module:'cpi',marker:'DNP',canonical:true,size_bytes:200,relative_path:'output/Summary_FetalFraction_CPI.csv'},{id:'curve',name:'curve.tsv',kind:'table',label:'Curva',module:'cpin',marker:'DNP',canonical:true,size_bytes:100,relative_path:'output/curve.tsv'},{id:'sites',name:'sites.tsv',kind:'table',label:'Siti',module:'cpin',marker:'DNP',canonical:true,size_bytes:200,relative_path:'output/sites.tsv'},{id:'plot',name:'plot.pdf',kind:'pdf',label:'Grafico',module:'cpin',marker:'DNP',canonical:true,size_bytes:400,relative_path:'output/plot.pdf'}];
const tables={calling:{columns:[{key:'chr',label:'Cromosoma'},{key:'pos',label:'Posizione'},{key:'GT',label:'Genotipo'},{key:'total_count',label:'Letture'}],rows:[{chr:'chr1',pos:'50',GT:'NA',total_count:'0'},{chr:'chr1',pos:'100',GT:'0/1',total_count:'12'}]},curve:{columns:[{key:'Min_child_reads',label:'Letture minime'},{key:'Through_min_child_reads',label:'Fino a'},{key:'Log10_CPI',label:'log₁₀(CPI)'},{key:'N_sites',label:'Siti'}],rows:[{Min_child_reads:'2',Through_min_child_reads:'5',Log10_CPI:'-3.33278849686833',N_sites:'3'},{Min_child_reads:'6',Through_min_child_reads:'6',Log10_CPI:'-3.42969850987639',N_sites:'2'},{Min_child_reads:'7',Through_min_child_reads:'10',Log10_CPI:'0.221848749616356',N_sites:'1'}]},sites:{columns:[{key:'chr',label:'Cromosoma'},{key:'pos1',label:'Posizione'},{key:'Status',label:'Ammissibilità',values:{eligible:'Ammissibile',father_unassigned:'Genotipo paterno non assegnato'}},{key:'GT_child',label:'Genotipo figlio'},{key:'Paternity_Index',label:'Indice del sito'}],rows:[{chr:'chr1',pos1:'100',Status:'eligible',GT_child:'0/1',Paternity_Index:'1.25'},{chr:'chr1',pos1:'200',Status:'father_unassigned',GT_child:'0/1',Paternity_Index:'NA'}]},'cpi-summary':{columns:[{key:'CPI_medianFF',label:'log₁₀(CPI) alla soglia mediana di letture fetali',unit:'log10'}],rows:[{CPI_medianFF:'0.602'}]}};
const run={id:'run-1',name:'Famiglia α <test>',status:'succeeded',workflow:'analysis',version:'0.8.99',started_at:'2026-11-15T10:00:00Z',finished_at:'2026-11-15T10:01:00Z',can_remove:true,has_igv_inputs:true,samples:[{id:'A',label:'A',filename:'a.bam',path:'C:\\samples\\a.bam'}],modules:['snp-call','cpi','cpin'],markers:['DNP','SNP'],settings:[{module:'snp-call',marker:'SNP',document:{parameters:{max_depth:0}}}],warnings:[]};
const overview={modules:[{module:'snp-call',marker:'SNP',status:'succeeded',files:files.filter(f=>f.module==='snp-call'),entries:[{label:'A',sample_id:'A',file_id:'calling',genotype_counts:{'0/1':1,unassigned:1},metrics:[{key:'assigned',label:'Genotipi assegnati',value:'1',available:true,scale:1}]}]},{module:'cpi',marker:'DNP',status:'succeeded',files:files.filter(f=>f.module==='cpi'),entries:[{family_id:'F',label:'Mother / Father',file_id:'cpi-summary',row:{CPI_medianFF:'0.602'},metrics:[{key:'Median_fetal_fraction_percent',label:'Frazione fetale mediana',value:'6',available:true,scale:1,unit:'%'},{key:'CPI_medianFF',label:'log₁₀(CPI) alla soglia mediana di letture fetali',value:'0.602',available:true,scale:1,unit:'log10'}],curve_file_ids:[]}]},{module:'cpin',marker:'DNP',status:'succeeded',files:files.filter(f=>f.module==='cpin'),entries:[{family_id:'F',label:'Mother / Father / Child',analysis:'all_compatible_sites',file_id:'cpi-summary',site_file_id:'sites',curve_file_ids:['curve'],metrics:[{key:'CPI',label:'CPI',value:'0.00046474155109453',available:true},{key:'N_sites',label:'Siti inclusi',value:'3',available:true}]}]}]};
const boot={version:'0.9.0',settings,preferences:{data_dir:null,runs_dir:null,workflows:{},update_channel:'stable',check_updates_on_startup:false,execution:{},scientific_settings:{}},layout:{data_dir:'/data',runs_dir:'/runs',project_dir:'/project'},ui:{language:'it',reduce_motion:false},jobs:[]};
const handlers={bootstrap:()=>boot,'runs.list':()=>({runs:[run],total:1}),'runs.get':()=>run,'runs.overview':()=>overview,'runs.files':()=>files,'runs.table':p=>{const base=tables[p.file_id];assert(base,'Unknown table fixture');const rows=base.rows.map((row,i)=>({row,i})).filter(x=>!p.query||JSON.stringify(x.row).toLowerCase().includes(p.query.toLowerCase()));const offset=p.offset||0,limit=p.limit||100,chosen=rows.slice(offset,offset+limit);return {file:files.find(f=>f.id===p.file_id),columns:base.columns,rows:chosen.map(x=>x.row),row_numbers:chosen.map(x=>x.i),total:base.rows.length,matched:rows.length,offset,limit,has_more:offset+limit<rows.length}},'dialog.open':()=>({paths:dialogPaths}),'plan.preview':p=>({preview_id:'preview-1',steps:[{id:'snp_0001',workflow:'snp-call'}],samples:p.draft.samples,effective_settings:p.draft.scientific_settings}),'analysis.start':()=>{const job={id:'job-1',name:'Analysis',status:'running',run_id:'run-1',progress:{phase:'pileup',workflow:'snp-call',completed:2,total:4,unit:'sites'},logs:[]};jobs.push(job);return job},'jobs.list':()=>jobs,'jobs.cancel':p=>{jobs[0].status='interrupted';return jobs[0]},'ui.save':p=>p.preferences,'preferences.save':p=>p.preferences,'files.url':()=>({url:'http://127.0.0.1:1234/token/result/plot',mime:'application/pdf'}),'files.export':()=>({saved:true}),'runs.export':()=>({saved:true}),'runs.import':()=>({imported:['run-1'],count:1}),'run.reuse':()=>({name:'Copy',caller:'snp',samples:[{id:'A',path:'/a.bam',kind:'bam'}],branches:{DNP:[],SNP:[]},reference:'/ref.fa',resources:{DNP:{},SNP:{panel:'/panel.tsv'}},families:{cpi:[],cpin:[]},scientific_settings:Object.fromEntries(Object.entries(settings.workflows).map(([m,w])=>[m,Object.fromEntries(Object.entries(w.parameters).map(([k,p])=>[k,p.default]))])),execution:{execution_mode:'auto'}}),'resources.get':()=>({host:{memory_mib:16000,cpus:8},runtime:{configured:{memory_mib:8192,cpus:4},effective:{memory_mib:8192,cpus:4}},container:{},backend:'wsl',warnings:[]}),'resources.preview':p=>({preview_id:'resource-1',before:{memory_mib:8192,cpus:4},after:p,affected_running:[],warnings:[]}),'resources.apply':()=>({status:'saved'}),'installation.get':()=>({runtimes:[],cache:[],backups:[],warnings:[],recovery:{recoverable:false}}),'environment.check':()=>({status:'passed',logs:['ready']}),'updates.check':()=>({status:'available',offer_id:'offer-1',message:'0.9.1 available',offer:{version:'0.9.1',channel:'testing'}}),'updates.download':()=>({status:'verified'}),'updates.install':()=>({close_required:true}),'app.close':()=>({closing:true}),'runs.remove':p=>({removed:true,run_id:p.run_id,outputs_preserved:true}),'run.igv':p=>({reference:{fasta:'/ref.fa',index:''},tracks:[{name:'A',path:'/a.bam'}],locus:p.locus||'all'}),'igv.prepare':p=>({chromosomes:[{name:'chr1',length:1000000},{name:'X',length:100000}],sources:{reference:{...p.reference,index:p.reference.index||p.reference.fasta+'.fai'},tracks:p.tracks.map(track=>({...track,index:track.index||track.path+'.bai'}))},reference:{fastaURL:'http://127.0.0.1:1234/token/ref',indexURL:'http://127.0.0.1:1234/token/index'},tracks:[],locus:p.locus}),'igv.session.save':()=>({saved:true})};
let referenceTestEntries=[],transferTestState={status:'idle'};
handlers['references.list']=()=>({entries:referenceTestEntries});
handlers['references.download_status']=()=>transferTestState;
handlers['references.resolve']=({id})=>({entry:referenceTestEntries.find(e=>e.id===id)});
handlers['runs.curve']=p=>handlers['runs.table']({...p,offset:0,limit:20000});
const env={console,document,Intl,URL,AbortController,location:{href:'http://127.0.0.1:1234/token/web/index.html',origin:'http://127.0.0.1:1234'},setTimeout:()=>1,clearTimeout(){},fetch:async(url,options)=>{assert.equal(url,'../api');const body=JSON.parse(options.body);requests.push(body);const fn=handlers[body.method];assert(fn,'Unexpected RPC '+body.method);return{ok:true,json:async()=>({id:body.id,result:fn(body.params)})}},NipatIGV:{dispose(){navigationCallback=null},getNavigation(){return {locus:env.locus||'all',chromosome:env.locus&&env.locus!=='all'?env.locus.split(':')[0]:'all',chromosomes:[{name:'chr1',length:1000000},{name:'X',length:100000}],canBack:!!env.locus,canZoom:!!env.locus&&env.locus!=='all',wholeGenome:!env.locus||env.locus==='all'}},onNavigation(callback){navigationCallback=callback;callback(this.getNavigation());return()=>{navigationCallback=null}},async wholeGenome(){await this.search('all')},async back(){await this.search('chr1:100-200')},async zoomIn(){await this.search('chr1:125-175')},async zoomOut(){await this.search('chr1:50-250')},setLanguage(){},resize(){},async mount(node,config){env.viewer={node,config}},async search(locus){env.locus=locus;navigationCallback?.(this.getNavigation())},async exportSession(){return {locus:'chr1:100-200',tracks:[]}}}};env.window=env;vm.createContext(env);vm.runInContext(fs.readFileSync(path.join(web,'i18n.js'),'utf8'),env);vm.runInContext(fs.readFileSync(path.join(web,'app.js'),'utf8'),env);
const tick=()=>new Promise(resolve=>setImmediate(resolve));const check=(condition,label)=>{assert(condition,label);checks.push(label)};
(async()=>{
 await tick();await tick();const app=env.NipatApp;
 const recent=app.state.runs;
 for(const entries of [recent,[]]){
  app.state.runs=entries;app.render();
  check((element('main').innerHTML.match(/data-view="new"/g)||[]).length===1,'Populated and empty overview have one primary creation action');
 }
 app.state.runs=recent;app.render();
 check(app.state.boot.version==='0.9.0','Bootstrap uses actual version');check(element('main').innerHTML.includes('Famiglia α &lt;test&gt;'),'Archive name HTML escaped');check(app.state.draft.samples.length===0,'No embedded demonstration samples');
 for(const view of ['home','new','activity','archive','catalog','settings','environment','igv']){await app.navigate(view);check(element('main').innerHTML.length>300,'Render '+view)}
 const pickBuild=(scope,value)=>app.onValue({dataset:{referenceBuild:scope},type:'select-one',value});
 const pickEntry=(scope,value)=>app.onValue({dataset:{referenceEntry:scope},type:'select-one',value});
 const reference=(build,label)=>({id:build+'-'+label,build,label,fasta:'/ref/'+label+'.fa',index:'/ref/'+label+'.fa.fai',index_sha256:'a'.repeat(64),naming:'chr',available:true});
 const hg19=reference('grch37','hg19'),hg38=reference('grch38','hg38'),b37=reference('grch37','b37');
 await app.navigate('new');app.state.draft.samples=[{kind:'bam',id:'test',path:'/samples/test.bam'}];
 check(app.renderNew().includes('GRCh37 / hg19')&&app.renderNew().includes('GRCh38 / hg38'),'New experiments offer both assemblies on a fresh install');
 await pickBuild('new','grch37');
 check(!app.state.draft.reference&&app.renderNew().includes('Scarica da UCSC hg19')&&!requests.some(r=>r.method==='references.download'),'Choosing an unavailable assembly offers a local FASTA or explicit download');
 handlers['references.register']=()=>({cancelled:true});await app.action('reference-register',{scope:'new',build:'grch37'});
 check(!app.state.draft.reference,'Cancelling the assembly picker preserves the empty selection');
 handlers['references.register']=()=>{referenceTestEntries.push(hg19);return {entry:hg19}};
 await app.action('reference-register',{scope:'new',build:'grch37'});
 check(app.submittedDraft().reference===hg19.fasta&&app.submittedDraft().reference_id===hg19.id,'A registered reference applies its file identity and actual FASTA to the experiment');
 await pickBuild('new','grch38');handlers['references.download']=()=>transferTestState={status:'downloading',received_bytes:64,total_bytes:100};
 await app.action('reference-download',{scope:'new',build:'grch38'});
 check(app.renderNew().includes('data-action="reference-cancel"')&&requests.at(-1).params.build==='grch38','Explicit transfer has progress and cancellation for the correct assembly');
 handlers['references.download_cancel']=()=>transferTestState={status:'cancelled'};
 await app.action('reference-cancel',{scope:'new',build:'grch38'});
 check(!app.state.draft.reference&&!app.renderNew().includes('data-action="reference-cancel"'),'Cancelled transfer does not attach a partial reference');
 await app.action('reference-download',{scope:'new',build:'grch38'});
 referenceTestEntries.push(hg38);transferTestState={status:'ready',entry:hg38};await app.poll();
 check(app.state.draft.reference===hg38.fasta&&app.state.draft.reference_id===hg38.id,'Completed explicit transfer applies to its still-current choice');
 referenceTestEntries.push(b37);await app.navigate('igv');await pickBuild('igv','grch37');
 check(!app.state.igv.reference.fasta&&app.renderIGV().includes(b37.fasta)&&app.renderIGV().includes(hg19.fasta),'Multiple FASTA variants for one assembly require choosing a concrete file');
 await pickEntry('igv',b37.id);await app.action('igv-load',{});
 check(requests.findLast(r=>r.method==='igv.prepare').params.reference.build==='grch37'&&app.state.igv.reference.index_sha256===b37.index_sha256&&app.state.igv.reference.fasta===b37.fasta,'IGV loads the chosen exact variant with assembly, file and index');
 await pickBuild('igv','file');dialogPaths=['/manual.fa'];await app.action('choose-path',{key:'igv-reference.fasta',filter:'igv-reference'});
 check(!app.state.igv.reference.build&&!app.state.igv.reference.index_sha256&&app.state.igv.reference.fasta==='/manual.fa','A direct user file clears the previous registered build');
 await app.action('new-experiment',{});check(!app.state.draft.reference&&!app.state.draft.reference_id,'New experiments have no silently preselected file');
 const expectedCounts=Object.values(settings.workflows).reduce((a,w)=>a+Object.keys(w.parameters).length,0);app.state.catalogModule='all';app.state.catalogType='parameters';await app.navigate('catalog');check((element('main').innerHTML.match(/class="parameter-row"/g)||[]).length===expectedCounts,'Every scientific parameter is accessible');check(!element('main').innerHTML.includes('<h3>other_fraction_max'),'No implementation key as parameter heading');app.state.catalogType='constants';app.render();check((element('main').innerHTML.match(/class="parameter-row"/g)||[]).length===52,'Every model constant is accessible');check(element('main').innerHTML.includes('<mfrac>')&&!element('main').innerHTML.includes('<mo><</mo>'),'Formulae rendered as valid escaped MathML fragments');
 check(element('main').innerHTML.includes('Vincolo sui dati di ingresso')&&element('main').innerHTML.includes('zero è escluso'),'Population frequency domain identifies the table constraint and its reason');
 for(const [language,label,description] of [
  ['it','Risultato non disponibile (NA)','Nelle tabelle, NA indica che il programma non ha potuto determinare il valore.'],
  ['en','Unavailable result (NA)','In the tables, NA means the program could not determine the value.'],
 ]){
  env.NipatI18n.setLanguage(language);
  app.state.catalogModule='dnp-call';app.state.catalogSearch='(NA)';app.render();
  const glossary=element('main').innerHTML;
  check(glossary.includes(`<h3>${label}</h3><p>${description}</p></div>`),'The DNP glossary explains the literal table marker once in '+language);
  check((glossary.match(/class="parameter-row"/g)||[]).length===1,'The literal marker can be searched in '+language);
 }
 env.NipatI18n.setLanguage('it');app.state.catalogModule='all';app.state.catalogSearch='';app.render();
 check(app.constantValue('cpi','population_frequencies',{}).includes('<mn>0</mn><mo>&lt;</mo><mi>p</mi><mo>≤</mo><mn>1</mn>'),'CPI domain excludes zero and includes one');
 check(app.choiceLabel('both')==='Entrambe le selezioni di siti'&&app.choiceLabel('other_allele')==='Siti con figlio eterozigote','Postnatal selection describes sites independently of caller markers');
 check(app.range({minimum:0,maximum:1,exclusive_minimum:true})==='> 0 · ≤ 1','Parameter bounds distinguish exclusive and inclusive limits');
 await app.navigate('new');app.onValue({dataset:{draft:'name'},type:'text',value:'My experiment'});dialogPaths=['/samples/Ion Sample.bam'];await app.action('add-samples',{});check(app.state.draft.samples[0].id==='Ion_Sample','Sample IDs derived safely');app.onValue({dataset:{draft:'caller'},type:'radio',value:'snp'});check(app.selectedModules().join(',')==='snp-call','Only requested SNP caller selected');app.onValue({dataset:{branch:'SNP|contamination'},type:'checkbox',checked:true});check(app.selectedModules().join(',')==='snp-call,contamination','Independent downstream analysis selection');app.onValue({dataset:{branch:'SNP|contamination'},type:'checkbox',checked:false});check(!app.selectedModules().includes('contamination'),'Unselected analysis removed');
 await app.action('step',{index:'3'});await app.action('validate-plan',{});const previewRequest=requests.find(r=>r.method==='plan.preview');check(previewRequest.params.draft.caller==='snp'&&previewRequest.params.draft.branches.SNP.length===0,'Preview passes exact independent plan');app.onValue({dataset:{parameter:'snp-call|max_depth|draft'},type:'number',value:'123'});check(!app.state.preview,'Changing a parameter invalidates reviewed plan');const previewOnStart=handlers['plan.preview'];
 handlers['plan.preview']=()=>Promise.reject(new Error('Missing panel.tsv'));
 await assert.rejects(app.action('start-analysis',{}),/Missing panel.tsv/);
 check(!requests.some(r=>r.method==='analysis.start')&&!app.renderNew().includes('aria-busy="true"'),'Invalid inputs prevent launch and allow retry');
 let passPreflight;handlers['plan.preview']=params=>new Promise(resolve=>{passPreflight=()=>resolve(previewOnStart(params))});
 const beforeStart=requests.length,launch=app.action('start-analysis',{});await tick();
 check(app.renderNew().includes('aria-busy="true"')&&app.renderNew().includes('check-spinner'),'Single-click start immediately shows its pending check');
 await app.action('start-analysis',{});passPreflight();await launch;handlers['plan.preview']=previewOnStart;
 check(requests.slice(beforeStart).map(r=>r.method).filter(m=>m==='plan.preview'||m==='analysis.start').join(',')==='plan.preview,analysis.start','Repeated clicks share one validated launch');
 check(app.state.view==='activity'&&requests.some(r=>r.method==='analysis.start'&&r.params.preview_id==='preview-1'),'Execution requires reviewed preview token');check(app.jobProgress(jobs[0])===50,'Observed phase progress, no fabricated overall completion');
 check(app.renderNew().includes('condividono CPU, memoria e disco')&&app.renderNew().includes('Il calcolo attende'),'Additional launches explain shared resources and waiting');
 const previousJobs=app.state.jobs;
 app.state.jobs=[...Array.from({length:5},(_,i)=>({id:'queued-'+i,name:'Pending '+i,status:'queued'})),
  {id:'capacity',name:'Waiting for capacity',status:'running',progress:{phase:'waiting-for-resources'}},jobs[0]];
 const activityWithQueue=app.renderActivity();
 check((activityWithQueue.match(/data-job-status="queued"/g)||[]).length===6&&activityWithQueue.includes('Esperimenti in attesa'),'Activity groups queued experiments and capacity waiters');
 check((activityWithQueue.match(/role="progressbar"/g)||[]).length===1&&activityWithQueue.includes('In attesa della verifica degli input'),'Only calculating experiments show a progress bar');
 check((activityWithQueue.match(/data-action="cancel-job"/g)||[]).length===7,'Every queued or running experiment has its own stop control');
 app.state.jobs=previousJobs;
 await app.action('confirm-cancel-job',{id:'job-1'});check(jobs[0].status==='interrupted','Cancel reaches actual job service');
 check(app.renderActivity().includes('Terminati in questa sessione')&&app.renderActivity().includes('data-action="remove-job"')&&!app.renderActivity().includes('data-action="cancel-job"'),'Interrupted card is dismissible in finished activity');
 await app.loadRun('run-1');check(element('main').innerHTML.includes('Analisi non eseguita'),'Unexecuted modules explicitly identified');await app.action('result-module',{module:'snp-call|SNP'});check(element('main').innerHTML.includes('Non disponibile')&&element('main').innerHTML.includes('0'),'NA and zero remain distinct');check(app.metricValue({value:'0.025',scale:100,unit:'%'})==='2,5 %','Percent conversion occurs once');check(app.metricValue({value:'0.0353553390593274',scale:100,unit:'punti %'}).includes('punti %'),'SD carries percentage-point unit');check(app.metricValue({value:null,scale:100})==='Non disponibile','Missing metric not coerced to zero');
 await app.action('result-module',{module:'cpi|DNP'});check(element('main').innerHTML.includes('log₁₀(CPI) alla soglia mediana di letture fetali')&&element('main').innerHTML.includes('0,602'),'Prenatal CPI field remains logarithmic');await app.action('result-module',{module:'cpin|DNP'});check((element('main').innerHTML.match(/class="curve-line"/g)||[]).length===3,'Postnatal CPI curve has original three inclusive intervals');check(element('main').innerHTML.includes('Genotipo paterno non assegnato'),'Site exclusion reasons human-readable');
 app.state.tableSearch='father_unassigned';await app.loadTable(0);check(app.state.table.matched===1&&app.state.table.row_numbers[0]===1,'Search pagination preserves original row identity');await app.action('row-details',{file:'sites',row:'1'});check(element('modal-root').innerHTML.includes('Genotipo paterno non assegnato'),'Row details use original row offset');await app.action('open-file',{id:'plot'});check(element('modal-root').innerHTML.includes('<iframe class="pdf-preview"'),'PDF stays inside app dialog');await app.action('export-file',{id:'plot'});check(requests.at(-1).method==='files.export','Export handled by native scoped service');await app.action('export-run',{});check(requests.at(-1).method==='runs.export','Complete original output export available');
 handlers['igv.about']=()=>({opened:true});
 await app.navigate('igv');
 check(/class="igv-title"><h1>Visualizzatore IGV<\/h1><button[^>]+data-action="igv-about"/.test(element('main').innerHTML),'IGV guide button sits next to viewer heading');
 await app.action('igv-about',{});
 check(app.state.view==='igv'&&requests.some(r=>r.method==='igv.about'&&Object.keys(r.params).length===0),'Guide action sends no file or session parameters and preserves the viewer');
 handlers['igv.about']=()=>({opened:false});
 await assert.rejects(app.action('igv-about',{}),/browser predefinito/);
 await app.changeLanguage('en');check(env.NipatI18n.language==='en'&&requests.some(r=>r.method==='ui.save'&&r.params.preferences.language==='en'),'Language choice persisted');await app.navigate('new');check(element('main').innerHTML.includes('Add samples')&&!element('main').innerHTML.includes('Aggiungi campioni'),'Main workflow translated to English');
 check(app.choiceLabel('both')==='Both site selections'&&env.NipatI18n.t('frequencyDomain').includes('zero is excluded'),'English scientific labels carry the same meaning');
 app.onValue({dataset:{field:'source'},type:'select-one',value:'tables'});check(app.state.draft.caller==='tables'&&app.state.draft.samples.length===0,'Tables path excludes raw input calling');app.state.sampleKind='dnp-table';dialogPaths=['/counts/A.txt'];await app.action('add-samples',{});app.onValue({dataset:{branch:'DNP|cpin'},type:'checkbox',checked:true});check(app.selectedModules().join(',')==='cpin','Tables-only CPIN does not run DNP or SNP');
 await app.navigate('settings');await app.action('save-preferences',{});check(requests.some(r=>r.method==='preferences.save'&&r.params.baseline),'Preferences save uses concurrency baseline');await app.navigate('environment');app.state.runtimeMemory=4096;app.state.runtimeCpus=2;await app.action('preview-resources',{});check(!requests.some(r=>r.method==='resources.apply'),'Resource preview makes no mutation');await app.action('apply-resources',{});check(requests.at(-2).method==='resources.apply'&&requests.at(-2).params.confirmed,'Resources apply only confirmed preview');await app.action('check-updates',{});await app.action('download-update',{});await app.action('confirm-install-update',{});check(requests.at(-1).method==='app.close','Successful install handoff requests native close');
 const previousCheck=handlers['updates.check'],previousDownload=handlers['updates.download'],previousLanguage=env.NipatI18n.language;
 for(const [language,architecture,caption] of [['it','arm64','Mostra nel Finder'],['en','x86_64','Show in Finder']]){
  env.NipatI18n.setLanguage(language);
  handlers['updates.check']=()=>({status:'available',offer_id:architecture,offer:{version:'0.9.11',channel:'stable',asset:{platform:'darwin-'+architecture}}});
  handlers['updates.download']=()=>({status:'verified',path:'/Users/A & B/Library/Caches/NewPat-'+architecture+'.pkg'});
  handlers['updates.reveal']=()=>({status:'revealed'});
  const before=requests.length;
  await app.action('check-updates',{});await app.action('download-update',{});
  const update=element('main').innerHTML;
  check(update.includes('A &amp; B/Library/Caches/NewPat-'+architecture+'.pkg')&&update.includes(caption)&&!update.includes('data-action="install-update"'),'Verified Mac package and manual action in '+language);
  await app.action('reveal-update',{});
  check(requests.at(-1).method==='updates.reveal'&&requests.at(-1).params.offer_id===architecture,'Finder receives only the selected offer');
  check(!requests.slice(before).some(r=>r.method==='updates.install'||r.method==='app.close'),'Mac manual installation keeps the application open');
 }
 handlers['updates.check']=previousCheck;handlers['updates.download']=previousDownload;delete handlers['updates.reveal'];env.NipatI18n.setLanguage(previousLanguage);
 await app.navigate('igv');app.state.igv.reference={fasta:'/ref.fa',index:'/ref.fa.fai'};app.state.igv.tracks=[{name:'Sample',path:'/a.bam',index:'/a.bam.bai'}];await app.action('igv-load',{});check(env.viewer&&requests.some(r=>r.method==='igv.prepare'&&r.params.reference.fasta==='/ref.fa'),'IGV registers real local source paths');app.state.igv.locus='chr1:100-200';await app.action('igv-search',{});check(env.locus==='chr1:100-200','Locus search reaches embedded IGV');app.state.igv.reference.fasta='/unapplied.fa';await app.action('igv-save',{});check(!JSON.stringify(requests.at(-1).params).includes('/token/'),'Saved IGV session contains no ephemeral capability URL');check(requests.at(-1).params.session.reference.fasta==='/ref.fa','IGV session saves the displayed sources, not unapplied form edits');

 // Regression coverage for real service contracts and stale asynchronous responses.
 check(document.documentElement.dataset.nipatReady==='true','Native readiness set only after successful boot');
 const sparse=app.normalizeDraft({caller:'snp',samples:[{id:'A',path:'/a.pileup',kind:'snp-pileup'}],branches:{SNP:[]},scientific_settings:{'snp-call':{max_depth:7}}});
 check(Array.isArray(sparse.branches.DNP)&&sparse.scientific_settings.cpin.min_child_reads!==undefined&&sparse.scientific_settings['snp-call'].max_depth===7,'Legacy reuse normalized without losing recorded overrides');
 app.state.draft=sparse;app.state.draft.reference='/hidden.fa';app.state.draft.branches.DNP=['cpin'];app.state.draft.families.cpin=[{id:'hidden'}];const clean=app.submittedDraft();check(clean.reference===null&&clean.branches.DNP.length===0&&clean.families.cpin.length===0,'Hidden reference branches and families omitted from submitted plan');
 check(app.resultCell('123456789',{key:'pos'})==='123456789'&&app.resultCell('00123',{key:'sample_id'})==='00123','Genomic coordinates and identifiers retain exact original digits');
 const malformed={...tables.curve,rows:[{Min_child_reads:'2',Through_min_child_reads:'</title><foreignObject>injected',Log10_CPI:'1'}]};check(!app.curveChart(malformed).includes('foreignObject'),'Malformed curve endpoint cannot inject SVG markup');
 const originalList=handlers['runs.list'];const manyRuns=Array.from({length:1003},(_,i)=>({...run,id:'archive-'+i,name:'Archived '+i}));handlers['runs.list']=p=>({runs:manyRuns.slice(p.offset,p.offset+p.limit),has_more:p.offset+p.limit<manyRuns.length,total:manyRuns.length});await app.loadRuns();check(app.state.runs.length===1003,'Archive retrieves entries beyond first server page');app.state.view='archive';app.state.run=null;app.state.archiveSearch='Archived 1002';app.render();check(element('main').innerHTML.includes('Archived 1002'),'Archive search reaches older records');app.state.archiveSearch='';app.render();check((element('main').innerHTML.match(/data-action="open-run"/g)||[]).length===25,'Archive renders bounded readable pages');handlers['runs.list']=originalList;await app.loadRuns();
 await app.loadRun('run-1');await app.action('result-module',{module:'snp-call|SNP'});const originalTable=handlers['runs.table'];let resolveOld;handlers['runs.table']=p=>p.query==='delayed'?new Promise(resolve=>{resolveOld=()=>resolve(originalTable({...p,query:''}))}):originalTable(p);app.state.tableSearch='delayed';const oldTable=app.loadTable(0);await tick();await app.action('result-module',{module:'cpin|DNP'});resolveOld();await oldTable;check(app.state.table.file.id==='sites','Delayed previous sample table cannot overwrite current module');handlers['runs.table']=originalTable;
 const originalReuse=handlers['run.reuse'];handlers['run.reuse']=()=>({name:'Historical',caller:'snp',samples:[{id:'A',path:'/a.pileup',kind:'snp-pileup'}],branches:{SNP:[]},scientific_settings:{'snp-call':{max_depth:7}}});await app.action('reuse-run',{});check(app.state.draft.branches.DNP.length===0&&app.state.draft.scientific_settings.cpin.min_child_reads!==undefined,'Reuse action normalizes sparse actual legacy response');handlers['run.reuse']=originalReuse;

 const savedRun=app.state.run,savedOverview=app.state.overview;app.state.run={...run,execution:{cpus:2,memory_mb:4096,execution_mode:'serial'},settings:[{module:'snp-call',marker:'SNP',document:{parameters:{excluded_flags:1796,max_depth:0},constants:{ploidy:3,phred_error_probability:settings.workflows['snp-call'].constants.phred_error_probability.value}}}]};app.state.runTab='parameters';const recorded=app.renderRun();check(recorded.includes('Unmapped')&&recorded.includes('Secondary alignments')&&!recorded.includes('1796'),'Historical excluded read categories are human-readable');check(recorded.includes('4096')&&recorded.includes('Memory limit')&&recorded.includes('>3</div>'),'Archived execution and historical constant values displayed unchanged');check(recorded.includes('<math'),'Unchanged historical scientific formula uses mathematical typesetting');
 app.state.runTab='results';app.state.module=null;app.state.overview={modules:[{module:'cpin',marker:'DNP',status:'running',entries:[],files:[]}]};const pending=app.renderRun();check(!pending.includes('Results available')&&pending.includes('Running'),'Pending declared module does not imply available results');app.state.run=savedRun;app.state.overview=savedOverview;
 check(app.curveChart({...tables.curve,has_more:true,total:2000}).includes('first 3'),'Partial scientific chart explicitly identifies truncation');
 const originalPreview=handlers['plan.preview'];let resolvePreview;handlers['plan.preview']=p=>new Promise(resolve=>{resolvePreview=()=>resolve(originalPreview(p))});const stalePreview=app.action('validate-plan',{});await tick();app.onValue({dataset:{draft:'name'},type:'text',value:'Changed while checking'});resolvePreview();await stalePreview;check(app.state.preview===null,'Editing during validation cannot activate a stale plan');handlers['plan.preview']=originalPreview;

 handlers['run.prepare']=p=>({name:'Additional analysis',caller:'tables',samples:[{id:'A',path:'/completed/counts.txt',kind:'dnp-table'}],branches:{DNP:[p.module]},families:{cpin:[{id:'F',mother:'A',father:'B',child:'C'}]},scientific_settings:{cpin:{min_child_reads:6}}});await app.action('prepare-module',{module:'cpin'});check(app.state.draft.caller==='tables'&&app.selectedModules().join(',')==='cpin'&&app.state.step===1,'Additional analysis consumes existing counts without rerunning callers or prior modules');check(app.state.draft.scientific_settings.cpin.min_child_reads===6&&app.state.source==='tables','Additional analysis preserves recorded settings and exposes family assignments');

 // 0.9.1 usability and lifecycle regressions.
 const noProgress={id:'initial',name:'Initial',status:'running',created_at:'2026-11-15T12:00:00Z',finished_at:'2026-11-15T12:02:03Z',progress:null,logs:[]};
 app.state.jobs=[noProgress];const initialProgress=app.renderActivity();
 check(/progress-track indeterminate/.test(initialProgress)&&!/<span style="width:0%"><\/span>/.test(initialProgress),'Unknown progress renders a visible indeterminate band without inline zero width');
 check((initialProgress.match(/class="dna-rung"/g)||[]).length===10,'Activity uses a recognizable multi-rung DNA helix');
 check(app.elapsedTime(noProgress).includes('2 min 3 s'),'Elapsed time uses recorded timestamps');
 app.state.motion=false;check(app.renderActivity().includes('helix paused'),'Application reduced-motion preference pauses DNA');app.state.motion=true;
 const nodes={},dna={classList:{toggle(){}}};
 const domNode=key=>nodes[key]??=(key==='.dna-loader'?dna:{textContent:'',dataset:{eventRevision:'0'},style:{width:'0%',removeProperty(key){delete this[key]}},classList:{toggle(){}},setAttribute(){},removeAttribute(){},querySelector:selector=>domNode(selector),scrollHeight:100,scrollTop:0,clientHeight:100});
 const card={dataset:{jobCard:'initial',jobStatus:'running',jobRun:''},querySelector:domNode};
 const queryBefore=document.querySelectorAll;document.querySelectorAll=selector=>selector==='[data-job-card]'?[card]:[];
 check(app.updateActivity()&&card.querySelector('.dna-loader')===dna&&domNode('span').style.width===undefined,'Polling preserves the existing DNA node and clears zero-width inline progress');
 noProgress.progress={phase:'pileup',completed:1,total:4};check(app.updateActivity()&&domNode('span').style.width==='25%','Same progress card receives measured phase progress without remounting');
 document.querySelectorAll=queryBefore;
 app.state.view='activity';
 const savedJobList=handlers['jobs.list'],logCursors=[];
 handlers['jobs.list']=()=>[noProgress];
 handlers['jobs.logs']=p=>{
  logCursors.push(p.after);
  return {limit:250,revision:noProgress.log_revision,reset:false,lines:p.after===0?['first']:['second']};
 };
 noProgress.log_revision=1;
 await app.poll();
 check(!logCursors.length&&!app.renderActivity().includes('first'),'Collapsed technical logs are not transferred by status polling');
 await app.action('job-log',{id:'initial'});await app.poll();
 noProgress.log_revision=2;await app.poll();
 check(logCursors.join(',')==='0,1'&&element('job-log-initial').textContent==='first\nsecond','Open technical logs get only newly observed lines');
 await app.action('job-log',{id:'initial'});noProgress.log_revision=3;await app.poll();
 check(logCursors.length===2,'Closing the technical log stops detail requests');
 check(requests.filter(r=>r.method==='jobs.list').every(r=>r.params.include_logs===false),'Regular activity requests always exclude buffered logs');
 handlers['jobs.list']=savedJobList;
 check(app.rowLocus({chr:'chr1',pos1:'100',pos2:'102'})==='chr1:100-102','DNP site keeps both exact one-based positions before reference-aware display padding');
 check(app.rowLocus({chr:'1',start:'0',end:'100'})===null&&app.rowLocus({chr:'1',pos:'0'})===null,'Unknown coordinate conventions and invalid zero positions are not guessed');
 await app.loadRun('run-1');check(element('main').innerHTML.includes('Run again')&&element('main').innerHTML.includes('Remove from list'),'Run actions are immediately visible');
 await app.action('result-module',{module:'snp-call|SNP'});check(element('main').innerHTML.includes('data-action="run-igv"'),'Coordinate-bearing result rows link to IGV when source inputs are recorded');
 handlers['jobs.result_id']=params=>{check(params.job_id==='old-job','Activity resolves the selected session job');return {run_id:'imported-original'}};
 await app.action('open-run',{job:'old-job',id:'same-basename'});
 check(requests.some(r=>r.method==='runs.get'&&r.params.run_id==='imported-original')&&!requests.some(r=>r.method==='runs.get'&&r.params.run_id==='same-basename'),'Opening an Activity card uses its registered archive ID after switching result folders');
 await app.loadRun('run-1');
 const originalGet=handlers['runs.get'],originalOverview=handlers['runs.overview'];app.state.run={...run,status:'running'};app.state.runTab='provenance';app.state.module=null;
 handlers['runs.get']=()=>({...run,status:'interrupted',status_note:'Previous process ended.'});handlers['runs.overview']=()=>({...overview});await app.refreshOpenedRun();
 check(app.state.run.status==='interrupted'&&app.state.runTab==='provenance'&&element('main').innerHTML.includes('Previous process ended.'),'Open result view refreshes stale status without resetting its selected tab');
 app.state.run={...run,status:'running'};app.render();
 await app.action('row-details',{file:'sites',row:'1'});
 const openDetails=element('modal-root').innerHTML;
 await app.poll();
 check(openDetails.includes('role="dialog"')&&element('modal-root').innerHTML===openDetails,'The live result dialog stays open when its experiment finishes');
 await app.action('close-modal',{});await app.poll();
 check(app.state.run.status==='interrupted'&&app.state.runTab==='provenance'&&element('main').innerHTML.includes('Previous process ended.'),'Closing details after completion shows the terminal result in the selected tab');handlers['runs.get']=originalGet;handlers['runs.overview']=originalOverview;
 await app.action('remove-run',{id:'run-1'});check(element('modal-root').innerHTML.includes('input files will remain'),'Removal confirmation clearly preserves results and source files');await app.action('confirm-remove-run',{id:'run-1'});check(requests.some(r=>r.method==='runs.remove'&&r.params.run_id==='run-1')&&app.state.run===null,'Confirmed removal reaches backend and clears selected experiment');
 await app.loadRun('run-1');await app.action('run-igv',{locus:'chr1:100-102'});check(app.state.view==='igv'&&app.state.igv.loaded&&requests.some(r=>r.method==='run.igv'&&r.params.locus==='chr1:100-102'),'Result action opens existing reference/sample in embedded viewer');
 check(env.viewer.config.locus==='chr1:50-152','Result display margin is applied after reference coordinates are validated');
 check(app.state.igv.reference.index==='/ref.fa.fai'&&app.state.igv.tracks[0].index==='/a.bam.bai','Discovered FASTA and BAM indices are reflected in the visible file selection');
 await app.action('igv-all',{});check(app.state.igv.locus==='all'&&app.state.igv.navigation.wholeGenome,'Whole-genome button synchronizes actual navigation state');await app.action('igv-back',{});check(app.state.igv.locus==='chr1:100-200','Previous-region control synchronizes the displayed locus');await app.action('igv-zoom-in',{});check(app.state.igv.locus==='chr1:125-175','Zoom updates the same region control');
 dialogPaths=['/correct.fa.fai'];await app.action('choose-path',{key:'igv-reference.index',filter:'fai'});check(requests.at(-1).params.filters[0].extensions.join(',')==='fai','FASTA index picker excludes binary BAM indices');
 dialogPaths=['/sample.bam.bai'];await app.action('choose-path',{key:'igv-track.0.index',filter:'bai'});check(requests.at(-1).params.filters[0].extensions.join(',')==='bai,csi','BAM index picker offers only BAM index formats');
 const html=fs.readFileSync(path.join(web,'index.html'),'utf8');check(!/(?:src|href)=["']https?:/.test(html),'All frontend scripts/styles packaged offline');check(!fs.readFileSync(path.join(web,'app.js'),'utf8').includes('window.open('),'No external-browser launch in frontend');

 // NewPat 0.9.5: explicit fresh starts, scoped diagnostics and honest viewer guidance.
 const savedPreferences=JSON.parse(JSON.stringify(app.state.preferences)),savedBaseline=JSON.parse(JSON.stringify(app.state.baseline));
 app.state.preferences.scientific_settings={'snp-call':{max_depth:250}};app.state.preferences.execution={max_workers:2};await app.action('save-preferences',{});
 app.state.preferences.scientific_settings['snp-call'].max_depth=999;app.state.preferences.execution.max_workers=7;
 for(const status of ['succeeded','failed','interrupted']){
  app.state.jobs=[{id:'previous-'+status,status}];app.state.draft={...app.blankDraft(),name:'Previous '+status,caller:'tables',samples:[{id:'Previous',path:'/old/counts.txt',kind:'dnp-table'}],reference:'/old/ref.fa',branches:{DNP:['cpin'],SNP:['contamination']},resources:{DNP:{panel:'/old/panel.txt'},SNP:{panel:'/old/snps.txt'}},families:{cpin:[{id:'F',mother:'Previous',father:'Other',child:'Child'}],cpi:[]}};
  app.state.draft.scientific_settings['snp-call'].max_depth=42;app.state.draft.execution.max_workers=8;
  app.state.step=3;app.state.source='tables';app.state.sampleKind='dnp-table';app.state.preview={preview_id:'old'};app.state.error='old error';element('modal-root').innerHTML='old modal';
  await app.action('navigate',{view:'new'});
  check(app.state.view==='new'&&JSON.stringify(app.state.draft)===JSON.stringify(app.blankDraft()),'New experiment clears all experiment inputs after '+status);
  check(app.state.step===0&&app.state.source==='bam'&&app.state.sampleKind==='bam'&&app.state.preview===null&&app.state.error===''&&element('modal-root').innerHTML==='','New experiment clears wizard and modal state after '+status);
  check(app.state.draft.scientific_settings['snp-call'].max_depth===250&&app.state.draft.execution.max_workers===2,'New experiment retains saved defaults, not last run or unsaved overrides after '+status);
 }
 app.state.preferences=savedPreferences;app.state.baseline=savedBaseline;await app.action('navigate',{view:'new'});
 // Named profiles contain scientific and execution settings, and never the experiment inputs.
 const personalDepth=app.state.draft.scientific_settings['snp-call'].max_depth;
 const profileName='Profilo <A>';
 app.state.preferences.runs_dir='/unsaved';
 app.state.draft.samples=[{id:'P',kind:'bam',path:'/private/P.bam'}];
 app.state.draft.scientific_settings['snp-call'].max_depth=117;
 app.state.draft.execution.performance_diagnostics=true;
 await app.action('new-profile',{});element('profile-name').value=profileName;
 await app.action('save-profile',{});
 let profile=app.state.baseline.parameter_profiles[profileName];
 check(profile.scientific_settings['snp-call'].max_depth===117&&!('performance_diagnostics' in profile.execution)&&!JSON.stringify(profile).includes('/private'),'Profile saves only scientific and execution settings');
 check(app.state.preferences.runs_dir==='/unsaved'&&app.state.baseline.runs_dir!=='/unsaved','Saving a profile preserves unrelated unsaved preferences without persisting them');
 app.state.draft.scientific_settings['snp-call'].max_depth=200;
 await app.action('apply-profile',{});
 check(app.state.draft.scientific_settings['snp-call'].max_depth===117&&app.state.draft.execution.performance_diagnostics&&app.state.draft.samples[0].id==='P','Applying a profile preserves the current experiment and resets its parameters');
 app.state.draft.scientific_settings['snp-call'].max_depth=201;
 await app.action('new-profile',{});element('profile-name').value=profileName;
 await app.action('save-profile',{});
 check(element('modal-root').innerHTML.includes('confirm-save-profile')&&profile.scientific_settings['snp-call'].max_depth===117,'Saving an existing name requires confirmation before replacement');
 await app.action('confirm-save-profile',{name:profileName});
 app.onValue({dataset:{preference:'default_profile'},type:'select-one',value:profileName});
 await app.action('save-preferences',{});await app.action('new-experiment',{});
 check(app.state.draft.scientific_settings['snp-call'].max_depth===201&&!app.state.draft.execution.performance_diagnostics&&!app.state.draft.samples.length,'New experiment uses the designated profile without old samples');
 check(app.normalizeDraft({scientific_settings:{}}).scientific_settings['snp-call'].max_depth===personalDepth,'Reopening a legacy draft does not apply a subsequently designated profile');
 await app.action('remove-profile',{name:profileName});
 check(element('modal-root').innerHTML.includes('confirm-remove-profile')&&element('modal-root').innerHTML.includes('&lt;A&gt;'),'Deletion confirmation escapes the profile name');
 await app.action('confirm-remove-profile',{name:profileName});
 check(!app.state.baseline.default_profile&&app.blankDraft().scientific_settings['snp-call'].max_depth===personalDepth&&app.state.draft.scientific_settings['snp-call'].max_depth===201,'Deleting the default profile restores personal defaults for future experiments only');
 const defer=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return{promise,resolve,reject}};
 const originalDialog=handlers['dialog.open'];
 for(const picker of ['samples','reference','resource.DNP.panel']){
  const pending=defer();handlers['dialog.open']=()=>pending.promise;
  const choosing=app.action(picker==='samples'?'add-samples':'choose-path',picker==='samples'?{}:{key:picker,filter:'fasta'});await tick();
  await app.action('navigate',{view:'new'});const fresh=app.state.draft;pending.resolve({paths:['/old/late.bam']});await choosing;
  check(app.state.draft===fresh&&JSON.stringify(fresh)===JSON.stringify(app.blankDraft()),'Late '+picker+' picker cannot repopulate a new experiment');
 }
 const cancelledDialog=defer();handlers['dialog.open']=()=>cancelledDialog.promise;const choosingCancelled=app.action('add-samples',{});await tick();await app.action('navigate',{view:'new'});cancelledDialog.reject(new Error('Old picker failed'));await choosingCancelled;check(app.state.error==='','Late dialog failure does not contaminate the new experiment');handlers['dialog.open']=originalDialog;
 for(const fails of [false,true]){
  const pending=defer();handlers['plan.preview']=()=>pending.promise;const validating=app.action('validate-plan',{});await tick();await app.action('navigate',{view:'new'});
  if(fails)pending.reject(new Error('Old validation failed'));else pending.resolve({preview_id:'old-preview'});await validating;
  check(app.state.preview===null&&app.state.error==='','Late validation '+(fails?'failure':'success')+' is discarded after a new experiment');
 }
 handlers['plan.preview']=originalPreview;
 for(const operation of ['reuse-run','prepare-module']){
  const method=operation==='reuse-run'?'run.reuse':'run.prepare',previousHandler=handlers[method],pending=defer();handlers[method]=()=>pending.promise;
  const loading=app.action(operation,{id:'run-1',module:'cpin'});await tick();await app.action('navigate',{view:'new'});pending.resolve({name:'Old restored run',samples:[{id:'Old',path:'/old.bam',kind:'bam'}]});await loading;
  check(app.state.view==='new'&&app.state.draft.name===''&&app.state.draft.samples.length===0,'Late '+operation+' cannot replace an explicitly new experiment');handlers[method]=previousHandler;
 }
 const originalStart=handlers['analysis.start'],pendingStart=defer();handlers['analysis.start']=()=>pendingStart.promise;app.state.preview={preview_id:'starting'};const starting=app.action('start-analysis',{});await tick();await app.action('navigate',{view:'new'});pendingStart.resolve({id:'accepted-old',status:'running',run_id:'run-1'});await starting;
 check(app.state.view==='new'&&app.state.draft.name===''&&app.state.jobs.some(job=>job.id==='accepted-old'),'Late accepted start records the job without replacing the new experiment');handlers['analysis.start']=originalStart;
 await app.action('reuse-run',{id:'run-1'});check(app.state.draft.name==='Copy'&&app.state.draft.reference==='/ref.fa'&&app.state.draft.samples[0].id==='A','Deliberate rerun still retains the recorded configuration');
 await app.action('prepare-module',{module:'cpin'});check(app.state.draft.name==='Additional analysis'&&app.state.draft.families.cpin[0].id==='F'&&app.state.step===1,'Deliberate additional analysis still retains input and family configuration');
 handlers['runs.open_directory']=()=>({opened:true});handlers['diagnostics.export']=()=>({path:'/exports/diagnostics.zip',files:4,omitted:[]});
 await app.loadRun('run-1');check(element('main').innerHTML.includes('data-action="open-run-directory"')&&element('main').innerHTML.includes('data-action="export-diagnostics"'),'Run folder and diagnostic export are visible from the experiment');
 await app.action('open-run-directory',{id:'run-1'});check(requests.at(-1).method==='runs.open_directory'&&requests.at(-1).params.run_id==='run-1','Open folder passes the selected run identity');
 await app.action('export-diagnostics',{id:'run-1'});check(requests.at(-1).params.run_id==='run-1'&&element('toast').textContent==='Diagnostic archive saved.','Run diagnostics are scoped to the selected experiment');
 await app.navigate('environment');check(element('main').innerHTML.includes('data-action="export-diagnostics"'),'Environment offers diagnostic export before any experiment');await app.action('export-diagnostics',{});check(requests.at(-1).method==='diagnostics.export'&&Object.keys(requests.at(-1).params).length===0,'Environment diagnostic export cannot accidentally attach a previously selected run');
 handlers['diagnostics.export']=()=>({cancelled:true});element('toast').textContent='unchanged';await app.action('export-diagnostics',{});check(element('toast').textContent==='unchanged','Cancelled diagnostic save does not claim success');
 await app.navigate('igv');app.state.igv={reference:{fasta:'',index:''},tracks:[],loaded:false,locus:'all'};
 check(app.renderIgvNavigation().includes('Select the FASTA genome'),'Empty IGV guidance identifies the missing reference');app.state.igv.reference.fasta='/ref.fa';check(app.renderIgvNavigation().includes('Open the files'),'Selected reference must be opened before navigation');
 await app.action('igv-load',{});check(app.state.igv.loaded&&app.renderIgvNavigation().includes('The reference is open'),'Reference-only viewing remains valid and explains how to add sample reads');
 app.state.igv.tracks=[{path:'/new.bam'}];check(app.renderIgvNavigation().includes('The reference is open'),'Unapplied BAM selection cannot masquerade as loaded reads');
 await app.action('igv-load',{});app.state.igv.navigation={wholeGenome:true};check(app.renderIgvNavigation().includes('under 100,000 bases'),'Loaded alignment at whole-genome scale shows zoom instructions');app.state.igv.navigation={start:1,end:100,wholeGenome:false};check(app.renderIgvNavigation().includes('If no reads appear'),'Narrow region guidance does not invent absent coverage');
 app.state.igv.loadedSources.tracks=[{path:'/sample.CRAM'}];check(!app.renderIgvNavigation().includes('The reference is open'),'CRAM is recognised as an alignment');
 check(html.includes('<title>NewPat</title>')&&element('breadcrumb').textContent.startsWith('NewPat / '),'Visible shell and breadcrumb use the NewPat name');
 check(Object.values(env.NipatI18n.strings).every(pair=>pair.every(value=>!value.includes('NIPAT'))),'All UI translations use the new product name');
 app.state.run={...run,version:'0.8.99'};app.state.runTab='provenance';check(app.renderRun().includes('Application version</dt><dd>0.8.99'),'Historical provenance keeps its recorded version without assigning a new historical brand');
 // Interactive scientific curves use original rows, offline, with mouse and keyboard details.
 const prenatal={file:{id:'prenatal',name:'family_panel_A.csv',kind:'table',cutoff:'A'},columns:[{key:'Iteration',label:'Minimum fetal reads'},{key:'log_CPI',label:'log₁₀(CPI)'},{key:'CPI',label:'CPI'},{key:'NotMismatch',label:'Matching sites'},{key:'Mismatch',label:'Mismatching sites'}],rows:[{Iteration:'2',log_CPI:'-3.123456789012345',CPI:'0.0007525631256789',NotMismatch:'12',Mismatch:'2'},{Iteration:'3',log_CPI:'0',CPI:'1',NotMismatch:'10',Mismatch:'0'},{Iteration:'4',log_CPI:'NA',CPI:'Inf',NotMismatch:'8',Mismatch:'1'}],total:3,has_more:false};
 const prenatalMarkup=app.curveChart(prenatal);
 check((prenatalMarkup.match(/data-curve-chart=/g)||[]).length===2&&prenatalMarkup.includes('Minimum fetal reads')&&prenatalMarkup.includes('Site counts'),'Prenatal CPI separates logarithmic evidence and site counts with correct threshold meaning');
 check(!prenatalMarkup.includes('class="curve-line"')&&!prenatalMarkup.includes('class="site-curve-line"'),'Prenatal points do not interpolate between recorded thresholds');
 check(prenatalMarkup.includes('aria-describedby=')&&prenatalMarkup.includes('tabindex="0"')&&prenatalMarkup.includes('arrow keys'),'Curve detail has keyboard guidance and accessible focus targets');
 check(prenatalMarkup.includes('Missing, non-finite values')&&!prenatalMarkup.includes('cy="NaN"'),'Missing and infinite plot values are omitted with an explicit explanation');
 const exact=app.curvePointDetails(prenatal,prenatal.rows[0],app.curveDefinition(prenatal));check(exact.includes('-3.123456789012345')&&exact.includes('0.0007525631256789'),'HTML detail preserves original precision without recalculating CPI');
 const chartId=/data-curve-chart="([^"]+)"/.exec(prenatalMarkup)[1],focusPoints=[];
 const curveContainer={dataset:{curveChart:chartId},querySelectorAll:()=>focusPoints,getBoundingClientRect:()=>({left:0,top:0,width:740}),closest:()=>curveContainer};
 for(let index=0;index<2;index++)focusPoints.push({dataset:{curvePoint:String(index)},attributes:{},classList:{toggle(){}},setAttribute(key,value){this.attributes[key]=value},getBoundingClientRect:()=>({left:100+index*20,bottom:100}),closest(selector){return selector==='[data-curve-point]'?this:selector==='[data-curve-chart]'?curveContainer:null},focus(){document.activeElement=this;events.focusin.forEach(callback=>callback({target:this}))},contains:()=>false});
 events.mouseover.forEach(callback=>callback({target:focusPoints[0],clientX:110,clientY:95}));
 check(element(chartId+'-tooltip').hidden===false&&element(chartId+'-tooltip').innerHTML.includes('-3.123456789012345'),'Mouse hover opens an actual HTML tooltip with exact prenatal values');
 let keyPrevented=false;events.keydown.forEach(callback=>callback({target:focusPoints[0],key:'ArrowRight',preventDefault(){keyPrevented=true}}));
 check(keyPrevented&&document.activeElement===focusPoints[1]&&element(chartId+'-tooltip').innerHTML.includes('Minimum fetal reads: 3'),'Arrow navigation focuses the next recorded threshold and updates details');
 check(focusPoints[0].attributes.tabindex==='-1'&&focusPoints[1].attributes.tabindex==='0','Chart has one tab stop while all recorded points remain keyboard-accessible');
 events.keydown.forEach(callback=>callback({target:focusPoints[1],key:'Home',preventDefault(){}}));check(document.activeElement===focusPoints[0],'Home returns to the first recorded point');
 events.keydown.forEach(callback=>callback({target:focusPoints[0],key:'End',preventDefault(){}}));check(document.activeElement===focusPoints[1],'End reaches the last recorded point');
 events.keydown.forEach(callback=>callback({target:focusPoints[1],key:'Escape',preventDefault(){}}));check(element(chartId+'-tooltip').hidden===true,'Escape closes the chart tooltip');
 const postnatal={...tables.curve,file:{id:'postnatal',name:'family_curve.tsv'},columns:[...tables.curve.columns,{key:'Matching_sites',label:'Matching sites'},{key:'Mismatching_sites',label:'Mismatching sites'}],rows:tables.curve.rows.map(row=>({...row,Matching_sites:'2',Mismatching_sites:'1'})),total:3,has_more:false};
 const postnatalMarkup=app.curveChart(postnatal);check((postnatalMarkup.match(/class="curve-line"/g)||[]).length===3&&postnatalMarkup.includes('Interval endpoints are inclusive.'),'Postnatal CPI renders each exact inclusive plateau without connecting gaps');
 check((postnatalMarkup.match(/class="site-curve-line"/g)||[]).length===9&&postnatalMarkup.includes('Minimum child reads'),'Postnatal site counts preserve matching, mismatching and total-site series');
 const intervalDetail=app.curvePointDetails(postnatal,postnatal.rows[0],app.curveDefinition(postnatal));check(intervalDetail.includes('2–5')&&intervalDetail.includes('-3.33278849686833'),'Postnatal hover retains inclusive endpoints and original log CPI precision');
 check(app.curveChart({columns:[{key:'x'},{key:'y'}],rows:[{x:'1',y:'2'}]}).includes('does not contain a recognised CPI curve'),'Unknown scientific schemas are not guessed');
 const corrupt={...postnatal,rows:[{Min_child_reads:'4',Through_min_child_reads:'2',Log10_CPI:'10'},{Min_child_reads:'2.5',Through_min_child_reads:'3',Log10_CPI:'0'},{Min_child_reads:'<script>',Through_min_child_reads:'3',Log10_CPI:'1'}]};const corruptMarkup=app.curveChart(corrupt);check(!corruptMarkup.includes('data-curve-point=')&&!corruptMarkup.includes('<script>')&&corruptMarkup.includes('not plotted'),'Invalid thresholds cannot fabricate points or inject chart markup');
 const combinedPrenatal=app.curveChart(prenatal,'combined'),prenatalScale=app.combinedCurveScale(prenatal,app.curveDefinition(prenatal));
 check((combinedPrenatal.match(/data-curve-chart=/g)||[]).length===1&&combinedPrenatal.includes('curve-right-label')&&combinedPrenatal.includes('share a numeric scale'),'Combined prenatal view has labelled left/right axes with original identity scaling');
 check(prenatalScale.scale===1&&prenatalScale.offset===0&&prenatalScale.low<0,'Negative prenatal log CPI remains on the original shared numeric scale');
 check(combinedPrenatal.includes('fill:#000000')&&combinedPrenatal.includes('fill:#008A38')&&combinedPrenatal.includes('fill:#C46B00')&&combinedPrenatal.includes('stroke-dasharray="5 3"'),'Combined view preserves black log CPI, green matching and dashed orange mismatching series');
 check([...new Set([...combinedPrenatal.matchAll(/data-curve-series="([^"]+)"/g)].map(match=>match[1]))].sort().join(',')==='Mismatch,NotMismatch,log_CPI','Combined prenatal plot contains exactly the three source series');
 const withGap={...prenatal,rows:[prenatal.rows[0],{...prenatal.rows[1],Iteration:'8'}]};check(!app.curveChart(withGap,'combined').includes('class="curve-connector"'),'Combined prenatal connections never bridge unrecorded integer thresholds');
 const previousCurveRun=app.state.run;app.state.run={settings:[{module:'cpin',step_id:'other',document:{parameters:{log_cpi_lower:-8,log_cpi_upper:8}}},{module:'cpin',step_id:'chosen',document:{parameters:{log_cpi_lower:-4,log_cpi_upper:4}}}]};
 const scopedPostnatal={...postnatal,file:{...postnatal.file,step_id:'chosen'}},postnatalScale=app.combinedCurveScale(scopedPostnatal,app.curveDefinition(scopedPostnatal));
 check(postnatalScale.scale===4&&postnatalScale.offset===-4&&postnatalScale.guidesKnown&&(2*postnatalScale.scale+postnatalScale.offset-postnatalScale.offset)/postnatalScale.scale===2,'CPIN count transformation is exactly invertible and uses the selected step recorded guides');
 const combinedPostnatal=app.curveChart(scopedPostnatal,'combined');check((combinedPostnatal.match(/class="curve-line"/g)||[]).length===3&&(combinedPostnatal.match(/class="site-curve-line"/g)||[]).length===6&&!combinedPostnatal.includes('data-curve-series="N_sites"'),'Combined CPIN renders exactly three series on inclusive intervals, without a fourth total-count curve');
 app.state.run={settings:[]};const fallbackScale=app.combinedCurveScale(postnatal,app.curveDefinition(postnatal));check(!fallbackScale.guidesKnown&&fallbackScale.low===-3.42969850987639&&fallbackScale.high===0.221848749616356&&app.curveChart(postnatal,'combined').includes('Archived guides are unavailable'),'Missing archived guides use observed values and explicitly identified display scaling');app.state.run=previousCurveRun;
 const originalCurves=handlers['runs.curve'],originalCpiCurveIds=overview.modules[1].entries[0].curve_file_ids;
 overview.modules[1].entries[0].curve_file_ids=['prenatal'];const manyCurveRows=Array.from({length:1005},(_,index)=>({...prenatal.rows[0],Iteration:String(index+1),log_CPI:String(index/10)}));
 handlers['runs.curve']=params=>params.file_id==='prenatal'?{...prenatal,rows:manyCurveRows,total:1005}:originalCurves(params);
 await app.loadRun('run-1');await app.action('result-module',{module:'cpi|DNP'});
 check(requests.some(request=>request.method==='runs.curve'&&request.params.run_id==='run-1'&&request.params.file_id==='prenatal'),'CPI entry loads the scoped complete curve endpoint');
 await app.action('curve-mode',{id:'prenatal',mode:'combined'});check((element('main').innerHTML.match(/data-curve-chart=/g)||[]).length===1&&app.state.curveModes.prenatal==='combined','Combined-view action switches the real result page without modifying source rows');await app.action('curve-mode',{id:'prenatal',mode:'separate'});check((element('main').innerHTML.match(/data-curve-chart=/g)||[]).length===2,'Separate views remain selectable after using the combined plot');
 check(app.state.curves[0].rows.length===1005&&element('main').innerHTML.includes('1–1,000 / 1,005'),'Curve page reports its exact displayed range without downsampling');
 await app.action('curve-page',{id:'prenatal',page:'1'});check(element('main').innerHTML.includes('1,001–1,005 / 1,005')&&(element('main').innerHTML.match(/data-curve-point=/g)||[]).length===10,'Remaining thresholds are available on the next page for both plots');
 check(element('main').innerHTML.includes('data-action="export-file"')&&element('main').innerHTML.includes('data-action="open-file"'),'Interactive plots retain original table access and exports');
 handlers['runs.curve']=()=>Promise.reject(new Error('Curve exceeds the display limit; open original PDF.'));await app.action('result-module',{module:'cpi|DNP'});
 check(element('main').innerHTML.includes('Curve exceeds the display limit')&&element('main').innerHTML.includes('log₁₀(CPI) alla soglia mediana di letture fetali')&&element('main').innerHTML.includes('0.6'),'Unavailable interactive curve shows its reason while the summary remains accessible');
 handlers['runs.curve']=originalCurves;overview.modules[1].entries[0].curve_file_ids=originalCpiCurveIds;
 // Page navigation is independent of IGV's genomic region history.
 await app.navigate('home');check(element('page-back').hidden,'Back control hidden at the workspace root');
 await app.navigate('archive');await app.loadRun('run-1');
 const snpGroup=overview.modules[0];app.state.overview={modules:[snpGroup]};app.render();
 check((element('main').innerHTML.match(/class="module-card"/g)||[]).length===1&&element('main').innerHTML.includes('data-module="snp-call|SNP"'),'Only the executed SNP caller is a result card');
 await app.action('result-module',{module:'snp-call|SNP'});app.state.tableSearch='0/1';await app.loadTable(0);
 await app.changeLanguage('it');
 check(app.state.module==='snp-call|SNP'&&app.state.tableSearch==='0/1'&&app.state.table.matched===1,'Changing language preserves the exact filtered SNP result');
 await app.action('open-file',{id:'calling'});await app.action('row-details',{file:'calling',row:'1'});
 check(element('modal-root').innerHTML.includes('data-action="back-to-table"'),'Site opened from original table has a route back to that table');
 await app.action('back-to-table',{});check(app.state.modalTable.file.id==='calling'&&element('modal-root').innerHTML.includes('class="table result-table"'),'Original table remains open at the same page');
 await app.action('run-igv',{locus:'chr1:100-100'});await app.action('page-back',{});
 check(app.state.view==='archive'&&app.state.module==='snp-call|SNP'&&app.state.tableSearch==='0/1'&&app.state.table.matched===1&&app.state.modalTable.file.id==='calling','Back from IGV restores the selected SNP module, filtered sites and source table');
 await app.action('close-modal',{});await app.action('page-back',{});check(app.state.run?.id==='run-1'&&app.state.module===null,'Back from module returns to this experiment overview');
 await app.action('page-back',{});check(app.state.view==='archive'&&!app.state.run,'Back from overview returns to the archive list');
 await app.action('page-back',{});check(app.state.view==='home','Back from archive returns to workspace');
 await app.action('navigate',{view:'new'});const wizard=app.state.draft;wizard.name='Draft to keep';wizard.samples=[{id:'A',kind:'snp-pileup',path:'/reads.txt'}];wizard.caller='snp';await app.action('step',{index:2});
 await app.navigate('settings');await app.action('edit-defaults',{});app.state.catalogSearch='deliberately unmatched';await app.action('page-back',{});await app.action('page-back',{});
 check(app.renderNew().includes('data-parameter="snp-call|other_fraction_max|draft"'),'Catalog search leaves wizard parameters visible');
 check(app.state.draft===wizard&&app.state.step===2&&!app.renderNew().includes('data-execution="dnp_block_mib|draft"'),'Returning to the wizard preserves its SNP draft and omits inapplicable DNP-only execution settings');
 await app.action('page-back',{});check(app.state.step===1&&app.state.draft.name==='Draft to keep','Back within the wizard keeps sample inputs intact');
 for(const [key,pair] of Object.entries(env.NipatI18n.strings))check(pair.length===2&&pair.every(x=>typeof x==='string'&&x.length),'Translation pair '+key);
 const listBeforeFailure=handlers['runs.list'];handlers['runs.list']=()=>{throw new Error('Archive unavailable')};await app.boot();check(!document.documentElement.dataset.nipatReady&&element('main').innerHTML.includes('Impossibile caricare'),'Failed initial archive load cannot report native app readiness');handlers['runs.list']=listBeforeFailure;await app.boot();check(document.documentElement.dataset.nipatReady==='true','Retry bootstrap restores readiness only after successful render');
 await app.navigate('environment');
 for(const lang of ['it','en']){
  await app.changeLanguage(lang);
  const it=lang==='it';
  check(element('main').innerHTML.includes(it?'Salva dati di esempio':'Save example data'),'Offline example action in '+lang);
  handlers['examples.save']=()=>({path:'/output/<folder>/synthetic-trio'});
  await app.action('save-example-data',{});
  check(requests.at(-1).method==='examples.save'&&requests.at(-1).params.language===lang&&element('modal-root').innerHTML.includes('/output/&lt;folder&gt;/synthetic-trio'),'Example extraction reports the escaped destination in '+lang);
  await app.action('close-modal',{});
  handlers['examples.save']=()=>({cancelled:true});await app.action('save-example-data',{});
  check(!element('modal-root').innerHTML,'Cancel leaves the chooser without a success message in '+lang);
  const describe=(key,value,label=key,extra={})=>({key,value,label,available:value!=null,...extra});
  const selectOutcome=(module,kind,metrics,extra={})=>{
   const marker=module==='snp-call'?'SNP':'DNP';
   const entry={label:'Family <1>',summary:{kind,step_status:'succeeded',metrics,...extra}};
   app.state.run=run;app.state.runTab='results';app.state.entry=0;app.state.table=null;app.state.curves=[];
   app.state.overview={modules:[{module,marker,status:'succeeded',files:[],entries:[entry]}]};
   app.state.module=module+'|'+marker;
   return app.renderRun();
  };
  const gt=app.resultCell('0/1',{key:'GT'},true),expectedLabel=it?'Eterozigote':'Heterozygous';
  check(gt.includes('class="locus-genotype"')&&gt.includes('>0/1</span> '+expectedLabel),'Site detail shows the recorded genotype and meaning '+lang);
  check(!app.resultCell('NA',{key:'GT'}).includes('locus-genotype'),'Missing site call cannot look assigned '+lang);
  const precise=selectOutcome('cpi','prenatal_cpi',[describe('CPI_medianFF','4.0001')],{guide_band:{lower:'-4',upper:'4',position:'above'}});
  check(precise.includes(it?'>4,0001<':'>4.0001<')&&precise.includes('data-band="above"'),'Preserve additional precision in historical summaries '+lang);
  const bounds={lower:'-2',upper:'7'};
  for(const [value,position] of [['-2.001','below'],['-2','at_lower'],['0','between'],['7','at_upper'],['7.001','above']]){
   const html=selectOutcome('cpi','prenatal_cpi',[describe('CPI_medianFF',value)],{guide_band:{...bounds,position}});
   check(html.includes('data-band="'+position+'"')&&html.includes('(-2, 7)'),'Prenatal band and archived custom limits '+lang+' '+position);
   const rounded=position==='at_lower'||position==='at_upper';
   check(html.includes(it?'arrotonda a tre decimali':'rounds to three decimal places')===rounded,'Rounding caveat only for a reported boundary '+lang+' '+position);
   if(value==='0')check(html.includes(it?'>0,000<':'>0.000<'),'Prenatal zero remains numeric '+lang);
  }
  const noBand=selectOutcome('cpi','prenatal_cpi',[describe('CPI_medianFF','4')],{guide_band:null});
  check(!noBand.includes('data-band=')&&noBand.includes(it?'>4,000<':'>4.000<'),'Historical result without archived limits keeps only its numeric value '+lang);
  const none=it?'Non disponibile':'Not available';
  const missing=selectOutcome('cpi','prenatal_cpi',[describe('CPI_medianFF',null)]);
  check(missing.toLowerCase().includes(none.toLowerCase())&&!missing.includes('data-band='),'Missing prenatal output is distinct from zero '+lang);
  for(const module of ['dnp-call','snp-call']){
   const metrics=[describe('assigned','3'),describe('site_count','5'),describe('unassigned','2')];
   const caller=selectOutcome(module,'genotypes',metrics);
   check(caller.includes('>3 / 5<')&&caller.includes(it?'Siti con genotipo assegnato':'Sites with an assigned genotype')&&!caller.includes('data-band='),'Caller identifies per-sample genotypes '+lang+' '+module);
   const partial=selectOutcome(module,'genotypes',metrics,{step_status:'interrupted'});
   check(partial.includes(it?'Analisi incompleta':'Analysis incomplete')&&!partial.includes('>3 / 5<'),'Interrupted table cannot look complete '+lang+' '+module);
  }
  const postnatal=selectOutcome('cpin','postnatal_cpi',[describe('CPI','0.00355037213631891'),describe('Log10_CPI','-2.45')]);
  check(postnatal.includes(it?'0,00355037213631891':'0.00355037213631891')&&!postnatal.includes('data-band='),'Preserve postnatal linear index precision without prenatal guides '+lang);
  const mean=describe('mean_contamination','0.025',it?'Contaminazione media':'Mean contamination',{unit:'%',scale:100});
  const contamination=selectOutcome('contamination','contamination',[mean,describe('informative_sites','12')]);
  check(contamination.includes(it?'Contaminazione media':'Mean contamination')&&contamination.includes(it?'>2,5 %<':'>2.5 %<'),'Contamination is a mean displayed as a percentage '+lang);
  const entries=app.state.overview.modules[0].entries;
  for(const label of ['Family 2','Family 3','Family 4'])entries.push({...entries[0],label});
  app.state.module=null;
  const cards=app.renderRun();
  check((cards.match(/class="outcome-preview"/g)||[]).length===3&&cards.includes('Family &lt;1&gt;')&&cards.includes('Family 3')&&!cards.includes('Family 4')&&cards.includes(it?'Altri risultati nella scheda di analisi':'More results in the analysis tab'),'Module cards show named subjects and link to additional entries '+lang);
 }
 // Verify the plan that crosses the RPC boundary when the user starts a family analysis.
 const pair = {id: 'pair', mother: 'M', father: 'F'};
 const trio = {id: 'trio', mother: 'M', father: 'F', child: 'C'};
 const resources = marker => ({
  panel: marker+'.tsv', popfreq: marker+'-freq.tsv', contamination_panel: marker+'-contamination.tsv',
  cpi_cutoffs: [{label: 'cutoff', path: marker+'-cutoff.tsv'}], cpin_panel: marker+'-post.tsv'
 });
 for (const caller of ['both', 'snp']) {
  await app.action('navigate', {view: 'new'});
  Object.assign(app.state.draft, {
   name: 'Families', caller, samples: ['M','F','C'].map(id=>({id, kind:'bam', path:'/bam/'+id+'.bam'})),
   reference: '/ref/family.fa', reference_id: 'registered-fasta',
   families: {cpi:[pair], cpin:[trio]}, branches: {DNP:['cpi'], SNP:['cpin','contamination']},
   resources: {DNP:resources('DNP'), SNP:resources('SNP')}
  });
  handlers['plan.preview'] = params => ({...originalPreview(params), preview_id:'families-'+caller});
  const offset = requests.length;
  await app.action('start-analysis', {});
  const familyCalls = requests.slice(offset).filter(r=>['plan.preview','analysis.start'].includes(r.method));
  assert.deepEqual(familyCalls.map(r=>r.method), ['plan.preview', 'analysis.start']);
  assert.deepEqual(familyCalls[1].params, {preview_id:'families-'+caller});
  const sent = familyCalls[0].params.draft;
  const dnpIncluded = caller === 'both';
  assert.deepEqual(sent.families, {cpi:dnpIncluded?[pair]:[], cpin:[trio]});
  assert.deepEqual(sent.branches, {DNP:dnpIncluded?['cpi']:[], SNP:['cpin','contamination']});
  assert.deepEqual(sent.resources.DNP, dnpIncluded ? {
   panel:'DNP.tsv', popfreq:'DNP-freq.tsv', cpi_cutoffs:[{label:'cutoff', path:'DNP-cutoff.tsv'}]
  } : {});
  assert.deepEqual(sent.resources.SNP, {
   panel:'SNP.tsv', popfreq:'SNP-freq.tsv', contamination_panel:'SNP-contamination.tsv', cpin_panel:'SNP-post.tsv'
  });
  check(sent.reference === '/ref/family.fa' && sent.reference_id === 'registered-fasta',
        'Family analysis submits its registered FASTA and selected resources for '+caller);
 }
 handlers['plan.preview'] = originalPreview;
 // A reviewable demo uses the real preview/start boundary and explicit factory settings.
 const scientificDefaults=Object.fromEntries(Object.entries(settings.workflows).map(([module,workflow])=>
  [module,Object.fromEntries(Object.entries(workflow.parameters).map(([key,param])=>[key,param.default]))]));
 const demoDraft={
  name:'DNP and SNP demo',caller:'both',reference:'/demo/reference/synthetic.fa',
  samples:['mother','father','child'].map(id=>({id,kind:'bam',path:'/demo/alignments/'+id+'.bam'})),
  branches:{DNP:[],SNP:[]},resources:{DNP:{panel:'/demo/panels/dnp.tsv'},SNP:{panel:'/demo/panels/snp.tsv'}},
  families:{cpi:[],cpin:[]},scientific_settings:scientificDefaults,
  execution:{execution_mode:'auto',max_workers:null,cpus:null,memory_mb:null,pids_limit:null,dnp_block_mib:32,dnp_block_loci:64,input_hashes:'auto',performance_diagnostics:false}
 };
 app.state.baseline.execution={max_workers:11,performance_diagnostics:true};
 app.state.baseline.scientific_settings={'snp-call':{max_depth:17}};
 const personalDefaults=JSON.stringify(app.state.baseline);
 handlers['examples.demo']=()=>({draft:demoDraft});
 handlers['plan.preview']=p=>({preview_id:'demo-validated',steps:[],samples:p.draft.samples});
 for(const lang of ['it','en']){
  await app.changeLanguage(lang);
  await app.action('new-experiment',{});
  const personal=app.state.draft;
  app.onValue({dataset:{draft:'name'},type:'text',value:'Keep my draft'});
  await app.navigate('environment');
  const expected=lang==='it'?'Risultati attesi della demo':'Expected demo results';
  const section=element('main').innerHTML;
  check(section.includes(lang==='it'?'Apri demo':'Open demo')&&section.includes(expected)&&section.includes('96')&&section.includes('50'),'Demo entry and reference counts are available outside the experiment '+lang);
  const reqStart=requests.length;
  await app.action('open-demo',{});
  check(requests.length===reqStart&&element('modal-root').innerHTML.includes('confirm-open-demo'),'Opening demo asks before replacing a personal draft '+lang);
  await app.action('close-modal',{});
  check(app.state.draft===personal&&personal.name==='Keep my draft','Cancelling keeps the draft '+lang);
  await app.action('open-demo',{});
  await app.action('confirm-open-demo',{});
  const opened=requests.slice(reqStart);
  check(opened.some(r=>r.method==='examples.demo'&&r.params.language===lang)&&opened.some(r=>r.method==='plan.preview')&&!opened.some(r=>r.method==='analysis.start'),'Demo validates and awaits explicit Start '+lang);
  check(app.state.view==='new'&&app.state.step===3&&app.state.preview.preview_id==='demo-validated'&&element('main').innerHTML.includes(expected),'Demo opens the ordinary reviewed wizard '+lang);
  check(app.submittedDraft().samples.map(s=>s.id).join(',')==='mother,father,child'&&app.activeMarkers().join(',')==='DNP,SNP'&&JSON.stringify(app.state.baseline)===personalDefaults,'Demo settings and synthetic files leave saved preferences untouched '+lang);
  check(app.state.draft.scientific_settings['snp-call'].max_depth===scientificDefaults['snp-call'].max_depth&&app.state.draft.execution.max_workers===null&&!app.state.draft.execution.performance_diagnostics,'Demo bypasses personal overrides '+lang);
  if(lang==='it'){
   await app.action('start-analysis',{});
   check(requests.some(r=>r.method==='analysis.start'&&r.params.preview_id==='demo-validated'),'Explicit Start submits the approved demo plan');
  }else{
   app.onValue({dataset:{draft:'caller'},type:'select-one',value:'snp'});
   check(app.state.preview===null&&!app.renderNew().includes(expected),'Changing the template invalidates its preview and expected-count panel');
  }
 }
 await app.action('new-experiment',{});
 const pristine=app.state.draft;
 await app.navigate('environment');
 handlers['plan.preview']=()=>Promise.reject(new Error('Demo reference unavailable'));
 await assert.rejects(app.action('open-demo',{}),/Demo reference unavailable/);
 check(app.state.draft===pristine&&app.state.view==='environment','Failed demo preparation preserves the existing draft and page');
 const demoWait=defer();
 handlers['plan.preview']=()=>demoWait.promise;
 const lateDemo=app.action('open-demo',{});await tick();await app.navigate('home');
 demoWait.resolve({preview_id:'late'});await lateDemo;
 check(app.state.view==='home'&&app.state.draft===pristine&&app.state.preview===null,'Late demo validation cannot redirect a user who navigated away');
 console.log(JSON.stringify({status:'passed',assertions:checks.length,rpcCalls:requests.length,scope:'Frontend state/RPC/markup; native rendering tested separately'}));
})().catch(error=>{console.error(error);process.exitCode=1});
