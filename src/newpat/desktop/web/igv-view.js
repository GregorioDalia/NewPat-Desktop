/* NewPat local IGV adapter. The upstream bundle remains unmodified. */
(function (global) {
  'use strict';
  const VERSION = '3.8.9';
  const FORMATS = Object.freeze({
    bam: 'alignment', cram: 'alignment', vcf: 'variant',
    bed: 'annotation', gff: 'annotation', gff3: 'annotation', gtf: 'annotation',
    bigwig: 'wig', bw: 'wig', wig: 'wig', bedgraph: 'wig', seg: 'seg',
    bigbed: 'annotation', bb: 'annotation'
  });
  const TEXT = {
    runtime: ['Il visualizzatore IGV non è disponibile. Ripara l’installazione di NewPat.', 'IGV is unavailable. Repair the NewPat installation.'],
    container: ['L’area del visualizzatore non è disponibile.', 'The viewer area is unavailable.'],
    reference: ['Seleziona un riferimento FASTA e il relativo indice FAI.', 'Select a FASTA reference and its FAI index.'],
    local: ['IGV può aprire soltanto file locali selezionati in NewPat.', 'IGV can only open local files selected in NewPat.'],
    track: ['Il formato della traccia non è supportato.', 'This track format is not supported.'],
    index: ['La traccia richiede il relativo indice.', 'The track requires its index.'],
    locus: ['Inserisci un cromosoma o una regione, ad esempio chr1:100000-110000.', 'Enter a chromosome or region, for example chr1:100000-110000.'],
    notMounted: ['Apri prima un riferimento nel visualizzatore.', 'Open a reference in the viewer first.'],
    load: ['Non è stato possibile aprire i file. Verifica che riferimento e indici corrispondano ai dati.', 'The files could not be opened. Check that the reference and indexes match the data.'],
    search: ['La regione non è disponibile nel riferimento selezionato.', 'The region is unavailable in the selected reference.']
  };
  let language = 'it';
  let browser = null;
  let generation = 0;
  let mountQueue = Promise.resolve();
  let navigationQueue = Promise.resolve();
  let currentSources = new Map();
  let currentReference = null;
  let chromosomes = [];
  let history = [];
  let restoringHistory = false;
  let wasDragging = false;
  const navigationListeners = new Set();

  function navigationChromosomes(instance, supplied) {
    const values = Array.isArray(supplied) && supplied.length ? supplied :
      (instance.genome?.chromosomeNames || []).map(name => ({name, length: instance.genome.getChromosome(name)?.bpLength}));
    return values.map(value => typeof value === 'string' ? {name: value, length: instance.genome?.getChromosome(value)?.bpLength} : value)
      .filter(value => value && typeof value.name === 'string' && value.name.toLowerCase() !== 'all')
      .map(value => ({name: value.name, length: Number(value.length) || null}))
      .sort((a, b) => a.name.localeCompare(b.name, undefined, {numeric: true}));
  }
  function visibleLoci(instance) {
    const frames = instance.referenceFrameList;
    if (frames?.length) return frames.map(frame => {
      if (frame.chr.toLowerCase() === 'all') return 'all';
      return `${frame.chr}:${Math.floor(frame.start) + 1}-${Math.round(frame.end)}`;
    });
    const raw = instance.toJSON().locus;
    return Array.isArray(raw) ? raw : String(raw || 'all').split(/\s+/);
  }
  function navigationState() {
    const loci = browser ? visibleLoci(browser) : [];
    const locus = loci.join(' '), first = loci.length === 1 ? loci[0] : '';
    const match = /^([^:]+)(?::([\d,]+)-([\d,]+))?$/.exec(first);
    const chromosome = match?.[1] || '';
    const wholeGenome = chromosome.toLowerCase() === 'all';
    return {locus, chromosome, start: match?.[2] ? Number(match[2].replaceAll(',', '')) : null,
      end: match?.[3] ? Number(match[3].replaceAll(',', '')) : null,
      chromosomes: chromosomes.map(value => ({...value})), canBack: history.length > 1,
      canZoom: !!browser && loci.length === 1 && !wholeGenome,
      wholeGenome};
  }
  function notifyNavigation() {
    const value = navigationState();
    for (const callback of navigationListeners) {
      try { callback(value); } catch (error) { global.console?.error('NewPat navigation listener:', error); }
    }
  }
  function recordNavigation(instance) {
    if (browser !== instance) return;
    const locus = visibleLoci(instance).join(' ');
    if (locus && !restoringHistory && history[history.length - 1] !== locus) {
      // Continuous dragging is one move in history, rather than one per pixel.
      if (instance.dragObject && wasDragging && history.length > 1) history[history.length - 1] = locus;
      else history.push(locus);
      if (history.length > 50) history.shift();
    }
    wasDragging = !!instance.dragObject;
    notifyNavigation();
  }
  function getNavigation() { return navigationState(); }
  function onNavigation(callback) {
    if (typeof callback !== 'function') throw new TypeError('A navigation callback is required');
    navigationListeners.add(callback);
    callback(navigationState());
    return () => navigationListeners.delete(callback);
  }
  function validateReferenceLocus(value) {
    const values = Array.isArray(value) ? value : [value];
    if (!chromosomes.length) return value;
    const normalized = values.map(locus => {
      const [name, coordinates] = locus.split(':');
      if (name.toLowerCase() === 'all') {
        if (coordinates) throw fail('locus');
        return 'all';
      }
      const aliases = [name, name.startsWith('chr') ? name.slice(3) : 'chr' + name];
      const chromosome = chromosomes.find(item => aliases.includes(item.name));
      if (!chromosome) throw fail('search');
      if (coordinates && chromosome.length) {
        const positions = coordinates.replaceAll(',', '').split('-').map(Number);
        if (positions.some(position => position > chromosome.length)) throw fail('search');
      }
      return chromosome.name + (coordinates ? ':' + coordinates : '');
    });
    return Array.isArray(value) ? normalized : normalized[0];
  }

  function message(code) { return TEXT[code][language === 'en' ? 1 : 0]; }
  function fail(code, cause) {
    const error = new Error(message(code));
    error.code = 'igv_' + code;
    if (cause) error.cause = cause;
    return error;
  }
  function label(value, fallback) {
    return String(value || fallback).replace(/[\u0000-\u001f\u007f]/g, '')
      .replace(/</g, '‹').replace(/>/g, '›').slice(0, 240);
  }
  function localURL(value) {
    if (typeof value !== 'string' || !value) throw fail('local');
    let url;
    try { url = new URL(value, global.location.href); } catch (_) { throw fail('local'); }
    const allowedHosts = ['127.0.0.1', 'localhost', '[::1]'];
    if (!['http:', 'https:'].includes(url.protocol) ||
        url.origin !== global.location.origin ||
        !allowedHosts.includes(url.hostname) || url.username || url.password || url.hash) {
      throw fail('local');
    }
    return url.href;
  }
  function normalizeLocus(value) {
    if (Array.isArray(value)) {
      if (!value.length || value.length > 12) throw fail('locus');
      return value.map(normalizeLocus);
    }
    if (typeof value !== 'string') throw fail('locus');
    const text = value.trim().replace(/[–—]/g, '-');
    // IGV handles reference aliases and bounds. Exclude URLs/HGVS/web-service input.
    if (!text || text.length > 300 || /[\s<>/\\?#=&]/.test(text) ||
        !/^[A-Za-z0-9_.-]+(?::[0-9,]+(?:-[0-9,]+)?)?$/.test(text)) throw fail('locus');
    if (text.includes(':')) {
      const coords = text.split(':')[1].replaceAll(',', '').split('-').map(Number);
      if (coords.some(n => !Number.isSafeInteger(n) || n < 1) ||
          (coords.length === 2 && coords[1] < coords[0])) throw fail('locus');
    }
    return text;
  }
  function normalizeReference(value) {
    if (!value || typeof value !== 'object' || !value.fastaURL || !value.indexURL) throw fail('reference');
    const result = {
      id: label(value.id, 'newpat-local'), name: label(value.name, language === 'en' ? 'Local reference' : 'Riferimento locale'),
      fastaURL: localURL(value.fastaURL), indexURL: localURL(value.indexURL)
    };
    if (value.compressedIndexURL) result.compressedIndexURL = localURL(value.compressedIndexURL);
    return result;
  }
  function numberOption(value, min, max) {
    const number = Number(value);
    return Number.isFinite(number) && number >= min && number <= max ? number : undefined;
  }
  function displayOptions(value) {
    const result = {};
    for (const key of ['autoscale', 'viewAsPairs', 'showCoverage', 'showAlignments', 'showSoftClips', 'showMismatches', 'showAllBases']) {
      if (typeof value[key] === 'boolean') result[key] = value[key];
    }
    for (const [key, min, max] of [['height', 50, 1500], ['order', 0, 10000], ['visibilityWindow', 1, 10000000], ['min', -1e12, 1e12], ['max', -1e12, 1e12]]) {
      if (value[key] !== undefined) {
        const parsed = numberOption(value[key], min, max);
        if (parsed !== undefined) result[key] = parsed;
      }
    }
    if (typeof value.color === 'string' && /^(#[a-f\d]{3,8}|rgba?\([\d\s,.%]+\)|[a-z]{3,24})$/i.test(value.color)) result.color = value.color;
    if (['EXPANDED', 'SQUISHED', 'COLLAPSED'].includes(value.displayMode)) result.displayMode = value.displayMode;
    if (['strand', 'firstOfPairStrand', 'pairOrientation', 'tlen', 'none'].includes(value.colorBy)) result.colorBy = value.colorBy;
    return result;
  }
  function normalizeTrack(value, index) {
    if (!value || typeof value !== 'object') throw fail('track');
    const format = String(value.format || '').toLowerCase();
    if (!Object.hasOwn(FORMATS, format)) throw fail('track');
    if (['bam', 'cram'].includes(format) && !value.indexURL) throw fail('index');
    const result = {
      id: label(value.id, 'newpat-track-' + index), name: label(value.name, 'Traccia ' + (index + 1)),
      format, type: FORMATS[format], url: localURL(value.url),
      height: FORMATS[format] === 'alignment' ? 260 : 140,
      ...displayOptions(value)
    };
    if (value.indexURL) result.indexURL = localURL(value.indexURL);
    if (typeof value.indexed === 'boolean') result.indexed = value.indexed;
    if (['bam', 'cram'].includes(format)) {
      result.indexed = true;
      result.visibilityWindow = result.visibilityWindow || 100000;
    }
    return result;
  }
  function filterRemoteMenuActions(items) {
    if (!Array.isArray(items)) return items;
    return items.filter(item => {
      if (!item || typeof item === 'string') return true;
      const text = String(item.label || item.name || item.element?.textContent || '');
      return !/\bBLAT\b|\bNCBI\b|\bUCSC\b|opencravat/i.test(text);
    });
  }
  function localMenus(track) {
    if (!track || track.__newpatLocalMenus) return;
    Object.defineProperty(track, '__newpatLocalMenus', {value: true});
    for (const key of ['contextMenuItemList', 'menuItemList']) {
      if (typeof track[key] !== 'function') continue;
      const original = track[key];
      track[key] = function (...args) {
        const result = original.apply(this, args);
        return result && typeof result.then === 'function'
          ? result.then(filterRemoteMenuActions) : filterRemoteMenuActions(result);
      };
    }
    localMenus(track.alignmentTrack);
    localMenus(track.coverageTrack);
  }
  function refreshMenus(instance) {
    for (const view of instance.trackViews || []) localMenus(view.track);
  }
  function configureNavigation(container) {
    // IGV 3.8.9 owns an open shadow root: document styles cannot reach its toolbar.
    // Keep track controls, but give genomic navigation one synchronized UI.
    const root = container.shadowRoot || container;
    const document = container.ownerDocument;
    if (!document?.createElement || !root.querySelector) return;
    let style = root.querySelector('style[data-newpat-navigation]');
    if (!style) {
      style = document.createElement('style');
      style.setAttribute('data-newpat-navigation', '');
      root.appendChild(style);
    }
    style.textContent = '.igv-navbar-genomic-location,.igv-zoom-widget,.igv-zoom-widget-900,.igv-zoom-widget-hidden{display:none!important}';
  }
  function requireBrowser() { if (!browser) throw fail('notMounted'); return browser; }

  function mount(container, options) {
    const ticket = ++generation;
    if (!container || typeof container.replaceChildren !== 'function') return Promise.reject(fail('container'));
    if (!global.igv || typeof global.igv.createBrowser !== 'function') return Promise.reject(fail('runtime'));
    let reference, tracks, locus;
    try {
      reference = normalizeReference(options?.reference);
      if (options.tracks !== undefined && !Array.isArray(options.tracks)) throw fail('track');
      tracks = (options.tracks || []).map(normalizeTrack);
      if (new Set(tracks.map(track => track.id)).size !== tracks.length) throw fail('track');
      if (options.locus) locus = normalizeLocus(options.locus);
    } catch (error) { return Promise.reject(error); }
    const work = async () => {
      if (ticket !== generation) return null;
      if (browser) { global.igv.removeBrowser(browser); browser = null; }
      chromosomes = []; history = []; wasDragging = false; restoringHistory = false;
      navigationQueue = Promise.resolve();
      currentReference = null; currentSources.clear(); notifyNavigation();
      container.replaceChildren();
      const before = new Set(global.igv.getAllBrowsers ? global.igv.getAllBrowsers() : []);
      try {
        const instance = await global.igv.createBrowser(container, {
          reference, tracks, ...(locus ? {locus} : {}),
          loadDefaultGenomes: false, genomeList: [], search: false,
          queryParametersSupported: false, enableWebSocket: false,
          showIdeogram: false, showCircularView: false, showCircularViewButton: false,
          showControls: true, showNavigation: true, showChromosomeWidget: false, showRuler: true,
          showSVGButton: false, showTrackLabels: true, showCenterGuide: true,
          minimumBases: 10, flanking: 100, showSampleNames: false
        });
        if (ticket !== generation) { global.igv.removeBrowser(instance); return null; }
        browser = instance;
        configureNavigation(container);
        currentReference = {id: reference.id, name: reference.name};
        currentSources = new Map(tracks.map(track => [track.id, {id: track.id, name: track.name, type: track.type, format: track.format}]));
        refreshMenus(instance);
        chromosomes = navigationChromosomes(instance, options.chromosomes);
        if (typeof instance.on === 'function') {
          instance.on('trackremoved', track => {
            if (browser === instance && track && track.id) currentSources.delete(track.id);
          });
          instance.on('locuschange', () => recordNavigation(instance));
        }
        recordNavigation(instance);
        return instance;
      } catch (error) {
        // createBrowser registers its instance before reading FASTA/indices.
        // Dispose that half-created instance so failed files leave no stale view.
        if (global.igv.getAllBrowsers) for (const instance of global.igv.getAllBrowsers()) {
          if (!before.has(instance)) global.igv.removeBrowser(instance);
        }
        container.replaceChildren();
        throw fail('load', error);
      }
    };
    const result = mountQueue.catch(() => {}).then(work);
    mountQueue = result.catch(() => {});
    return result;
  }
  async function loadTracks(values) {
    const instance = requireBrowser();
    if (!Array.isArray(values)) throw fail('track');
    const tracks = values.map((value, i) => normalizeTrack(value, currentSources.size + i));
    const ids = tracks.map(track => track.id);
    if (new Set(ids).size !== ids.length || ids.some(id => currentSources.has(id))) throw fail('track');
    try {
      const loaded = await instance.loadTrackList(tracks);
      if (!loaded || loaded.some(track => !track)) throw fail('track');
      for (const track of tracks) currentSources.set(track.id, {id: track.id, name: track.name, type: track.type, format: track.format});
      refreshMenus(instance);
      return loaded;
    } catch (error) { throw fail('load', error); }
  }
  function enqueueNavigation(action) {
    const instance = requireBrowser(), ticket = generation;
    const work = async () => {
      if (browser !== instance || ticket !== generation) return null;
      try {
        await action(instance);
        if (browser !== instance || ticket !== generation) return null;
        recordNavigation(instance);
        return exportSession();
      } catch (error) {
        if (browser !== instance || ticket !== generation) return null;
        if (error.code?.startsWith('igv_')) throw error;
        throw fail('search', error);
      }
    };
    const result = navigationQueue.catch(() => {}).then(work);
    navigationQueue = result.catch(() => {});
    return result;
  }
  async function search(value) {
    // Validate before queueing so malformed input never reaches the renderer.
    requireBrowser();
    const locus = normalizeLocus(value);
    return enqueueNavigation(instance => {
      const checked = validateReferenceLocus(locus);
      return instance.search(Array.isArray(checked) ? checked.join(' ') : checked);
    });
  }
  async function back() {
    return enqueueNavigation(async instance => {
      if (history.length < 2) return;
      const previous = history[history.length - 2], ticket = generation;
      restoringHistory = true;
      try {
        await instance.search(previous);
        if (browser === instance && ticket === generation) {
          history.pop();
          history[history.length - 1] = visibleLoci(instance).join(' ');
        }
      } finally {
        if (browser === instance && ticket === generation) restoringHistory = false;
      }
    });
  }
  async function zoom(factor) {
    return enqueueNavigation(async instance => {
      const navigation = getNavigation();
      if (!navigation.canZoom) return;
      const chromosome = chromosomes.find(value => value.name === navigation.chromosome);
      const length = chromosome?.length;
      const start = navigation.start || 1, end = navigation.end || length;
      if (!end) throw fail('search');
      const minimum = length ? Math.min(length, 10) : 10;
      const width = Math.min(length || Number.MAX_SAFE_INTEGER, Math.max(minimum, Math.round((end - start + 1) * factor)));
      const first = Math.max(1, Math.min(Math.round((start + end - width + 1) / 2), length ? length - width + 1 : Number.MAX_SAFE_INTEGER));
      await instance.search(`${navigation.chromosome}:${first}-${first + width - 1}`);
    });
  }
  function wholeGenome() { return search('all'); }
  function zoomIn() { return zoom(0.5); }
  function zoomOut() { return zoom(2); }
  function exportSession() {
    const instance = requireBrowser();
    const raw = instance.toJSON();
    // Capability URLs expire with the desktop session and must never become saved source paths.
    const tracks = (raw.tracks || []).filter(track => currentSources.has(track.id)).map(track => ({
      ...currentSources.get(track.id), ...displayOptions(track)
    }));
    return {schema_version: 1, application: 'NewPat', igv_version: VERSION,
      reference: {...currentReference}, locus: raw.locus, tracks};
  }
  function exportSVG() { return requireBrowser().toSVG(); }
  async function resize() { if (browser) await browser.visibilityChange(); }
  function dispose() {
    generation++;
    if (browser) global.igv.removeBrowser(browser);
    browser = null; currentReference = null; currentSources.clear();
    chromosomes = []; history = []; restoringHistory = false; wasDragging = false;
    navigationQueue = Promise.resolve(); notifyNavigation();
  }
  global.NewPatIGV = Object.freeze({version: VERSION, mount, loadTracks, search,
    getNavigation, onNavigation, back, wholeGenome, zoomIn, zoomOut,
    exportSession, snapshot: exportSession, exportSVG, resize, dispose,
    setLanguage(value) { language = value === 'en' ? 'en' : 'it'; }});
})(window);
