/* Tests the NewPat/IGV boundary, not an emulated genomic renderer. */
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync(process.argv[2], 'utf8');
let active = [], lastConfig, removed = [], failCreation = false, pendingResolve;
function viewer(config) {
  const tracks = config.tracks.map(t => ({...t})), events = new Map();
  return {
    config,
    trackViews: [{track: {menuItemList: () => [{label:'Reverse'}, {label:'BLAT visible sequence'}],
      alignmentTrack: {contextMenuItemList: () => [{label:'View mate'}, {label:'BLAT read'}]}}}],
    loadTrackList: async list => { tracks.push(...list); return list; },
    on(name, callback) { if(!events.has(name))events.set(name, []);events.get(name).push(callback); },
    emit(name) { for(const callback of events.get(name)||[])callback(); },
    search: async function(locus) { config.locus=locus;this.emit('locuschange'); },
    visibilityChange: async () => {},
    toJSON: () => ({reference:config.reference,locus:config.locus || 'chr1:1-100',tracks}),
    toSVG: () => '<svg xmlns="http://www.w3.org/2000/svg"></svg>'
  };
}
const environment = {
  URL, console,
  location: new URL('http://127.0.0.1:40123/app/index.html'),
  igv: {
    createBrowser: async (_container, config) => {
      lastConfig=config;
      const browser=viewer(config);active.push(browser);
      if(failCreation)throw new Error('bad index');
      if(pendingResolve)await new Promise(resolve=>{pendingResolve=resolve;});
      return browser;
    },
    removeBrowser: browser=>{removed.push(browser);active=active.filter(b=>b!==browser);},
    getAllBrowsers: ()=>active
  }
};
environment.window=environment;
vm.createContext(environment);
vm.runInContext(source, environment);
const api=environment.NewPatIGV;
const container={replaceChildren(){this.resets=(this.resets||0)+1;}};
const config={reference:{id:'reference',name:'GRCh38 locale',fastaURL:'/files/secret1/ref.fa',indexURL:'/files/secret2/ref.fa.fai'},
 tracks:[{id:'sample1',name:'Campione 1',format:'bam',url:'/files/secret3/a.bam',indexURL:'/files/secret4/a.bam.bai'}],locus:'chr1:100-200'};
const copy=()=>JSON.parse(JSON.stringify(config));
const rejects=(call,code)=>assert.rejects(call, e=>e.code===code);
(async()=>{
  await rejects(()=>api.search('chr1'), 'igv_notMounted');
  await api.mount(container,copy());
  assert.equal(lastConfig.loadDefaultGenomes,false);
  assert.equal(lastConfig.search,false);
  assert.equal(lastConfig.enableWebSocket,false);
  assert.equal(lastConfig.queryParametersSupported,false);
  assert.equal(lastConfig.showSVGButton,false);
  assert.equal(lastConfig.showNavigation,true);
  assert.equal(lastConfig.showChromosomeWidget,false);
  assert.equal(lastConfig.reference.fastaURL,'http://127.0.0.1:40123/files/secret1/ref.fa');
  assert.equal(lastConfig.tracks[0].type,'alignment');
  assert.equal(lastConfig.tracks[0].indexed,true);
  assert.equal(lastConfig.tracks[0].visibilityWindow,100000);
  assert.equal(active[0].trackViews[0].track.menuItemList().length,1);
  assert.equal(active[0].trackViews[0].track.alignmentTrack.contextMenuItemList().length,1);
  assert.equal(api.version,'3.8.9');
  const snapshot=api.exportSession();
  assert.equal(snapshot.application,'NewPat');
  assert.equal(snapshot.tracks[0].id,'sample1');
  assert.equal(snapshot.reference.name,'GRCh38 locale');
  assert.ok(!JSON.stringify(snapshot).includes('secret'));
  assert.ok(!JSON.stringify(snapshot).includes('http'));
  assert.match(api.exportSVG(),/^<svg/);
  await api.search('chr1:1,000–2,000');
  assert.equal(api.exportSession().locus,'chr1:1,000-2,000');
  await api.search(['chr1:10-20','chr2:30-40']);
  assert.equal(api.exportSession().locus,'chr1:10-20 chr2:30-40');
  for(const locus of ['https://example.com','chr1:0-1','chr1:20-10','chr1:1-9007199254740992','chr1:1-2?name=x','NM_123:c.42T>C']) {
    await rejects(()=>api.search(locus),'igv_locus');
  }
  for(const url of ['https://igv.org/ref.fa','http://localhost:40123/ref.fa','http://127.0.0.1:40124/ref.fa','file:///tmp/ref.fa','data:text/plain,A','http://u:p@127.0.0.1:40123/ref.fa']) {
    const c=copy();c.reference.fastaURL=url;await rejects(()=>api.mount(container,c),'igv_local');
  }
  const noRef=copy();delete noRef.reference.indexURL;await rejects(()=>api.mount(container,noRef),'igv_reference');
  const noIndex=copy();delete noIndex.tracks[0].indexURL;await rejects(()=>api.mount(container,noIndex),'igv_index');
  const badTrack=copy();badTrack.tracks[0].format='service';await rejects(()=>api.mount(container,badTrack),'igv_track');
  const duplicate=copy();duplicate.tracks.push({...duplicate.tracks[0]});await rejects(()=>api.mount(container,duplicate),'igv_track');
  const extra=copy();extra.reference.maneBbURL='https://example.org/data';extra.reference.tracks=[{url:'https://x'}];extra.search={url:'https://example.org'};extra.tracks[0].urlTemplate='https://x';extra.tracks[0].color='url(https://x)';
  await api.mount(container,extra);
  assert.equal(lastConfig.reference.maneBbURL,undefined);
  assert.equal(lastConfig.reference.tracks,undefined);
  assert.equal(lastConfig.tracks[0].urlTemplate,undefined);
  assert.equal(lastConfig.tracks[0].color,undefined);
  assert.equal(lastConfig.search,false);
  await api.loadTracks([{id:'annotation',name:'Annotation',format:'bed',url:'/files/secret5/a.bed',color:'#456c63'}]);
  assert.equal(api.exportSession().tracks.length,2);
  assert.equal(api.exportSession().tracks[1].color,'#456c63');
  await rejects(()=>api.loadTracks([{id:'annotation',format:'bed',url:'/files/second'}]),'igv_track');
  const safeName=copy();safeName.tracks[0].name='<img onerror=bad()>';
  await api.mount(container,safeName);assert.ok(!lastConfig.tracks[0].name.includes('<'));
  // One navigation source: native panning updates the custom UI and history.
  const navigation = [], unsubscribe = api.onNavigation(value => navigation.push(value));
  const guided = copy();
  guided.locus='all';
  guided.chromosomes=[{name:'1',length:100000},{name:'10',length:50000},{name:'2',length:200000},{name:'X',length:80000}];
  await api.mount(container,guided);
  assert.equal(api.getNavigation().wholeGenome,true);
  assert.equal(api.getNavigation().canZoom,false);
  assert.equal(api.getNavigation().canBack,false);
  assert.equal(api.getNavigation().chromosomes.map(c=>c.name).join(','),'1,2,10,X');
  const overview = api.getNavigation().locus;
  await api.zoomIn();
  assert.equal(api.getNavigation().locus,overview); // No arbitrary chromosome chosen.
  await rejects(()=>api.search('23'),'igv_search');
  await rejects(()=>api.search('X:1-80001'),'igv_search');
  await rejects(()=>api.search('all:10-20'),'igv_locus');
  assert.equal(api.getNavigation().locus,'all');
  assert.equal(api.getNavigation().canBack,false);
  await api.search('chr1:101-200');
  assert.equal(api.getNavigation().locus,'1:101-200');
  assert.equal(api.getNavigation().chromosome,'1');
  assert.equal(api.getNavigation().start,101);
  assert.equal(api.getNavigation().canBack,true);
  await api.zoomIn();
  assert.equal(api.getNavigation().locus,'1:126-175');
  await api.back();
  assert.equal(api.getNavigation().locus,'1:101-200');
  await api.back();
  assert.equal(api.getNavigation().locus,'all');
  assert.equal(api.getNavigation().canBack,false);
  await api.search('1:1-20');
  await api.zoomOut();
  assert.equal(api.getNavigation().locus,'1:1-40');
  active[0].config.locus='1:900-950';
  active[0].emit('locuschange');
  assert.equal(navigation.at(-1).locus,'1:900-950');
  active[0].dragObject={};
  active[0].config.locus='1:901-951';active[0].emit('locuschange');
  active[0].config.locus='1:902-952';active[0].emit('locuschange');
  active[0].dragObject=null;
  await api.back();
  assert.equal(api.getNavigation().locus,'1:900-950');
  await api.search('1:1001-1400');
  await Promise.all([api.zoomIn(),api.zoomIn()]);
  assert.equal(api.getNavigation().end-api.getNavigation().start+1,100);
  await api.wholeGenome();
  assert.equal(api.getNavigation().wholeGenome,true);
  const stale=active[0];
  api.dispose();
  const notifications=navigation.length;
  stale.config.locus='1:1-10';stale.emit('locuschange');
  assert.equal(navigation.length,notifications);
  assert.equal(api.getNavigation().locus,'');
  assert.equal(api.getNavigation().chromosomes.length,0);
  unsubscribe();
  await api.mount(container,copy());
  assert.equal(navigation.length,notifications);
  // Disposing a slow search cannot overwrite a newer viewer or its history.
  const pendingBrowser=active[0];
  let finishSearch;
  pendingBrowser.search=async function(locus) {
    await new Promise(resolve=>{finishSearch=resolve;});
    this.config.locus=locus;this.emit('locuschange');
  };
  const slowSearch=api.search('chr1:300-400');
  await new Promise(resolve=>setImmediate(resolve));
  api.dispose();
  await api.mount(container,guided);
  await api.search('X:100-200');
  finishSearch();
  assert.equal(await slowSearch,null);
  assert.equal(api.getNavigation().locus,'X:100-200');
  await api.back();
  assert.equal(api.getNavigation().locus,'all');
  failCreation=true;
  await rejects(()=>api.mount(container,copy()),'igv_load');
  assert.equal(active.length,0);
  failCreation=false;
  api.setLanguage('en');
  await assert.rejects(()=>api.mount(container,{reference:{}}),/Select a FASTA/);
  api.setLanguage('it');
  // Disposing during async creation must not resurrect a stale viewer.
  pendingResolve=true;
  const operation=api.mount(container,copy());
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(typeof pendingResolve,'function');
  api.dispose();pendingResolve();pendingResolve=null;
  assert.equal(await operation,null);
  assert.equal(active.length,0);
  await api.mount(container,copy());await api.resize();api.dispose();
  assert.equal(active.length,0);
  assert.throws(()=>api.exportSession(),e=>e.code==='igv_notMounted');
  console.log('IGV adapter: local-only URLs, explicit indices, offline configuration, synchronized navigation/history/zoom, session lifetime and exports passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
