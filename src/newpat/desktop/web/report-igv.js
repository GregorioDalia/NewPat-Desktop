/* Export one offline IGV view from the indexed alignments verified for this case. */
(() => {
  'use strict';

  const maxWindow = 1000, maxImageLength = 750000, timeoutMs = 12000;

  function interval(value) {
    const match = /^([\w.-]+):(\d+)(?:-(\d+))?$/.exec(String(value || ''));
    if (!match) return null;
    const start = Number(match[2]), end = Number(match[3] || match[2]);
    return Number.isSafeInteger(start) && Number.isSafeInteger(end) && start > 0 && end >= start
      ? {chr: match[1], start, end} : null;
  }

  function capability(value) {
    if (!value) return false;
    const url = new URL(value, document.baseURI);
    const resources = new URL('../resources/', document.baseURI);
    return url.origin === resources.origin && !url.username && !url.password && !url.search && !url.hash &&
      url.pathname.startsWith(resources.pathname) && /^[\w-]+$/.test(url.pathname.slice(resources.pathname.length));
  }

  function configuration(prepared) {
    if (!prepared?.available) return null;
    const site = interval(prepared.reference_site || prepared.site), region = interval(prepared.locus);
    const ref = prepared.reference, tracks = prepared.tracks;
    if (!site || !region || site.chr !== region.chr || site.start < region.start || site.end > region.end ||
        region.end - region.start >= maxWindow || !ref || !capability(ref.fastaURL) || !capability(ref.indexURL) ||
        (ref.compressedIndexURL && !capability(ref.compressedIndexURL))) return null;
    if (!Array.isArray(tracks) || !tracks.length || tracks.length > 3 ||
        tracks.some(track => track?.format !== 'bam' || !capability(track.url) || !capability(track.indexURL))) return null;
    const names = tracks.map(track => String(track.name || '').trim());
    if (names.some(name => !name || /[\\/\u0000-\u001f]/.test(name)) || new Set(names).size !== names.length) return null;
    return {site, region, options: {
      reference: ref, locus: prepared.locus, tracks: tracks.map((track, i) => ({
        id: 'report-' + i, name: names[i], format: 'bam', url: track.url, indexURL: track.indexURL,
        indexed: true, height: 116, visibilityWindow: maxWindow, showCoverage: true, showAlignments: true,
        showSoftClips: false, viewAsPairs: false,
      })),
    }};
  }

  function hasReadAt(view, site) {
    // IGV 3.8.9 reads and CIGAR blocks use zero-based, half-open reference coordinates.
    const cache = view.viewports?.[0]?.featureCache;
    if (cache?.chr !== site.chr) return false;
    const reads = cache.features?.allAlignments?.();
    return Array.isArray(reads) && reads.some(read => {
      const aligned = pos => read.blocks?.some(block => ['M', '=', 'X'].includes(block.type) &&
        block.start <= pos && pos < block.start + block.len);
      return !read.hidden && read.chr === site.chr && aligned(site.start - 1) && aligned(site.end - 1);
    });
  }

  async function snapshot(frame, config, prepared, language) {
    const local = frame.contentWindow;
    const browser = await local.NewPatIGV.mount(local.document.getElementById('viewer'), config.options);
    if (!frame.isConnected) return null;
    const views = browser.trackViews.filter(view => view.track.type === 'alignment');
    const actual = browser.referenceFrameList[0];
    if (views.length !== config.options.tracks.length || views.some(view => !hasReadAt(view, config.site)) ||
        !actual || actual.chr !== config.site.chr || Math.floor(actual.start) + 1 > config.site.start ||
        Math.round(actual.end) < config.site.end) return null;
    // The bundled IGV renderer draws its own scale, reference, coverage, reads and track labels.
    const svg = browser.toSVG();
    if (typeof svg !== 'string' || !svg.length || svg.length > 2000000) return null;
    const uri = URL.createObjectURL(new Blob([svg], {type: 'image/svg+xml'}));
    try {
      const image = new Image();
      const loaded = new Promise((resolve, reject) => { image.onload = resolve; image.onerror = reject; });
      image.src = uri;
      await loaded;
      if (!frame.isConnected || !image.naturalWidth || !image.naturalHeight ||
          image.naturalWidth > 1024 || image.naturalHeight > 750) return null;
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(image.naturalWidth * 1.5);
      canvas.height = Math.round(image.naturalHeight * 1.5);
      const graphics = canvas.getContext('2d');
      graphics.fillStyle = 'white';
      graphics.fillRect(0, 0, canvas.width, canvas.height);
      graphics.drawImage(image, 0, 0, canvas.width, canvas.height);
      const png = canvas.toDataURL('image/png');
      if (png.length > maxImageLength) return null;
      const locus = actual.chr + ':' + (Math.floor(actual.start) + 1) + '-' + Math.round(actual.end);
      return {image: png, locus, site: prepared.site, build: prepared.build || '',
        tracks: config.options.tracks.map(track => track.name),
        caption: language === 'en' ?
          'For each sample, the height of the upper track shows how many reads cover each position. Some of the aligned reads appear below.' :
          'Per ogni campione, l’altezza del grafico indica quante letture coprono ciascuna posizione. Sotto il grafico sono visibili alcune delle letture allineate.'};
    } finally {
      URL.revokeObjectURL(uri);
    }
  }

  async function capture(prepared, {language = document.documentElement.lang, signal} = {}) {
    let config;
    try { config = configuration(prepared); } catch { return null; }
    if (!config || signal?.aborted) return null;
    // A separate document owns IGV's requests, listeners, timers and genome state.
    // Removing it also cancels an in-flight mount without disturbing the interactive viewer.
    const frame = document.createElement('iframe');
    frame.tabIndex = -1;
    frame.setAttribute('aria-hidden', 'true');
    frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:800px;height:650px;border:0;pointer-events:none';
    return new Promise(resolve => {
      let settled = false;
      function finish(value) {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        signal?.removeEventListener('abort', cancel);
        frame.onload = null;
        frame.onerror = null;
        try { frame.contentWindow?.NewPatIGV?.dispose(); } catch { /* The frame may already be unloading. */ }
        frame.remove();
        resolve(value);
      }
      const cancel = () => finish(null);
      const timer = setTimeout(cancel, timeoutMs);
      signal?.addEventListener('abort', cancel, {once: true});
      frame.onload = async () => {
        try { finish(await snapshot(frame, config, prepared, language)); } catch { finish(null); }
      };
      frame.onerror = cancel;
      frame.src = 'report-igv.html';
      document.body.appendChild(frame);
    });
  }

  window.NewPatReportIGV = Object.freeze({capture});
})();
