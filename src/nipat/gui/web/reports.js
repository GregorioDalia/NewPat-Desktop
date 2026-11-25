/* PDF exports for one selected analysis result. All assets are bundled with the desktop app. */
(() => {
  'use strict';

  const ink = '#193E35', accent = '#285B4C', muted = '#4A655D', line = '#C6D6CD', pale = '#EFF5F1';
  const copy = {
    it: {
      summary: 'Sintesi dei risultati', detailed: 'Relazione dettagliata', result: 'Risultato',
      facts: 'Dati principali', metrics: 'Valori dell’analisi', context: 'Esperimento e campioni',
      source: 'Origine dei dati', notes: 'Note di lettura', run: 'Esperimento', id: 'ID esperimento',
      caseId: 'Riferimento risultato', date: 'Data registrata', subject: 'Campione o famiglia',
      selection: 'Selezione dei siti', marker: 'Marcatori', version: 'Versione NewPat',
      abbreviated: 'I nomi abbreviati sono riportati per esteso nella relazione dettagliata.',
      more: 'Valore completo nella relazione dettagliata', research: 'Analisi per uso di ricerca',
      page: 'Pagina', of: 'di', unavailable: 'Non disponibile', failure: 'Impossibile caricare il generatore PDF.',
      overflow: 'Il risultato supera lo spazio disponibile per la sintesi. Esporta la relazione dettagliata.',
    },
    en: {
      summary: 'Results summary', detailed: 'Detailed report', result: 'Result',
      facts: 'Key findings', metrics: 'Analysis values', context: 'Experiment and samples',
      source: 'Data sources', notes: 'Reading notes', run: 'Experiment', id: 'Experiment ID',
      caseId: 'Result reference', date: 'Recorded date', subject: 'Sample or family',
      selection: 'Site selection', marker: 'Markers', version: 'NewPat version',
      abbreviated: 'Abbreviated names are shown in full in the detailed report.',
      more: 'Full value in the detailed report', research: 'Research use',
      page: 'Page', of: 'of', unavailable: 'Not available', failure: 'Could not load the PDF renderer.',
      overflow: 'This result exceeds the summary page. Export the detailed report.',
    },
  };

  let assets;
  function loadScript(path) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = path;
      script.onload = resolve;
      script.onerror = () => { script.remove(); reject(new Error(path)); };
      document.head.append(script);
    });
  }
  function loadAssets() {
    if (!assets) {
      assets = (async () => {
        const response = await fetch('newpat-wordmark.svg');
        if (!response.ok) throw new Error('wordmark');
        const logo = await response.text();
        if (!window.pdfMake) await loadScript('vendor/pdfmake/pdfmake.min.js');
        await loadScript('vendor/pdfmake/vfs_fonts.js');
        return logo;
      })().catch(error => { assets = null; throw error; });
    }
    return assets;
  }

  function plain(value) {
    return String(value == null ? '' : value).replace(/[\u0000-\u001f\u007f]/g, ' ').trim();
  }
  function recordedDate(value, language) {
    const date = plain(value);
    if (!/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/i.test(date) || !Number.isFinite(Date.parse(date))) return date;
    return new Intl.DateTimeFormat(language === 'en' ? 'en-GB' : 'it-IT', {
      dateStyle: 'long', timeStyle: 'short', timeZone: 'UTC',
    }).format(new Date(date)) + ' UTC';
  }
  function shorten(value, limit) {
    const letters = Array.from(plain(value));
    return letters.length <= limit ? letters.join('') : letters.slice(0, limit - 1).join('') + '…';
  }
  const rules = {
    hLineWidth: i => i === 0 ? 0 : 0.5,
    vLineWidth: () => 0,
    hLineColor: () => line,
    paddingLeft: () => 7, paddingRight: () => 7,
    paddingTop: () => 5, paddingBottom: () => 5,
  };

  function cell(value, style = {}) {
    const text = plain(value);
    return {text, ...(/\S{19,}/u.test(text) ? {wordBreak: 'break-all'} : {}), ...style};
  }
  function section(text) {
    return {text, fontSize: 14, color: ink, bold: true, margin: [0, 17, 0, 5], headlineLevel: 1};
  }
  function keyValues(rows) {
    return {layout: rules, table: {widths: ['39%', '*'], body: rows.map(row => [
      cell(row.label, {color: muted}), cell(row.value, {bold: true}),
    ])}};
  }
  function resultCard(model, lang, short) {
    // Very long native decimal strings belong in the detailed table. Never abbreviate a number.
    const headline = plain(model.headline) || lang.unavailable;
    const explanation = plain(model.explanation);
    return {
      layout: {hLineWidth: () => 0, vLineWidth: () => 0,
        paddingLeft: () => 15, paddingRight: () => 15, paddingTop: () => 13, paddingBottom: () => 13},
      table: {widths: ['*'], body: [[{fillColor: pale, stack: [
        {text: lang.result, fontSize: 10, bold: true, color: accent, margin: [0, 0, 0, 6]},
        cell(short && headline.length > 130 ? lang.more : headline, {fontSize: 19, bold: true, color: ink}),
        cell(short && explanation.length > 370 ? lang.more : explanation, {fontSize: 11, lineHeight: 1.2, margin: [0, 6, 0, 0]}),
      ]}]]},
    };
  }

  function tableSection(table) {
    const columns = table.columns;
    if (!columns.length) return [];
    const head = columns.map(value => cell(value, {bold: true, fillColor: pale, color: accent}));
    return [section(table.title), {fontSize: columns.length > 5 ? 8 : 9.5, layout: rules, table: {
      headerRows: 1, widths: columns.map(() => '*'), body: [
        head, ...table.rows.map(row => columns.map((_, i) => cell(row[i]))),
      ],
    }}, ...(table.note ? [{text: plain(table.note), color: muted, fontSize: 9, margin: [0, 5, 0, 0]}] : [])];
  }

  // Scale in normalised coordinates so a finite range spanning -1e308 to 1e308 also plots correctly.
  function axis(values) {
    const min = Math.min(...values), max = Math.max(...values), scale = Math.max(Math.abs(min), Math.abs(max)) || 1;
    return {min, max, position(v) {
      if (min === max) return 0.5;
      if (Number.isFinite(max - min)) return (v - min) / (max - min);
      return (v / scale - min / scale) / (max / scale - min / scale);
    }};
  }
  function tick(number, language) {
    if (number === 0) return '0';
    const size = Math.abs(number);
    return new Intl.NumberFormat(language, {
      maximumSignificantDigits: 5, notation: size && (size < 0.001 || size >= 1000000) ? 'scientific' : 'standard',
    }).format(number);
  }
  function chartSection(chart, language) {
    const points = chart.points.filter(p => Number.isFinite(p.x) && Number.isFinite(p.y));
    if (!points.length) return [];
    const out = [section(chart.title)];
    if (chart.kind === 'bar') {
      const y = axis([0, ...points.map(p => p.y)]), width = 136, base = width * y.position(0);
      out.push({text: plain(chart.y_label), fontSize: 9, color: muted, margin: [0, 0, 0, 4]});
      out.push({layout: rules, table: {widths: ['*', width + 2, 82], body: points.map(p => {
        const end = width * y.position(p.y);
        return [cell(p.label), {canvas: [
          {type: 'line', x1: base, y1: 0, x2: base, y2: 10, lineWidth: 0.6, lineColor: muted},
          {type: 'rect', x: Math.min(base, end), y: 2, w: Math.abs(end - base), h: 6, color: accent},
        ]}, {text: tick(p.y, language), alignment: 'right'}];
      })}});
      return out;
    }
    if (chart.kind !== 'line') return [];
    const width = 391, height = 102, x = axis(points.map(p => p.x)), y = axis(points.map(p => p.y));
    const xy = points.map(p => ({x: 1 + width * x.position(p.x), y: 2 + height * (1 - y.position(p.y))}));
    const shapes = [2, 2 + height / 2, 2 + height].map(at => ({
      type: 'line', x1: 0, y1: at, x2: width + 2, y2: at, lineWidth: 0.5, lineColor: line,
    }));
    // Points and their positions are the observations reported for the selected curve.
    shapes.push({type: 'polyline', points: xy, lineWidth: 1.7, lineColor: accent});
    for (const p of xy) shapes.push({type: 'ellipse', x: p.x, y: p.y, r1: 1.6, r2: 1.6, color: accent});
    const yLabels = y.min === y.max ? ['', tick(y.min, language), ''] :
      [tick(y.max, language), '', tick(y.min, language)];
    out.push({unbreakable: true, stack: [
      {text: plain(chart.y_label), fontSize: 9.5, color: muted, margin: [0, 0, 0, 5]},
      {columns: [{width: 60, stack: yLabels.map(label => ({text: label || ' ', fontSize: 8.5,
        margin: [0, 0, 4, height / 2 - 10], alignment: 'right'}))},
        {width: width + 2, stack: [{canvas: shapes}, x.min === x.max ?
          {text: tick(x.min, language), alignment: 'center', fontSize: 8.5} :
          {columns: [{text: tick(x.min, language)}, {text: tick(x.max, language), alignment: 'right'}], fontSize: 8.5},
        {text: plain(chart.x_label), alignment: 'center', fontSize: 9.5, color: muted, margin: [0, 3, 0, 0]}]}]},
    ]});
    return out;
  }

  function definition(model, kind, logo) {
    const short = kind === 'summary', l = copy[model.language] || copy.it;
    const title = short ? l.summary : l.detailed;
    let abbreviated = false;
    function identity(value, limit) {
      if (!short) return plain(value);
      const part = shorten(value, limit);
      if (part !== plain(value)) abbreviated = true;
      return part;
    }
    const idRows = [
      [l.selection, model.selection, 42], ...(model.subjects || []).map(row => [row.label, row.value, 38]),
      [l.run, model.run_name, 55], ...(short ? [] : [[l.id, model.run_id, 74]]), [l.date, recordedDate(model.date, model.language), 44],
    ].filter(row => plain(row[1])).map(([label, value, limit]) => ({label, value: identity(value, limit)}));
    const subject = identity(model.subject, 72);
    if (model.case_id && !short) idRows.push({label: l.caseId, value: plain(model.case_id)});
    const content = [
      {text: title, fontSize: 12, bold: true, color: accent, margin: [0, 2, 0, 5]},
      {text: plain(model.module), fontSize: 26, bold: true, color: ink},
      cell([plain(model.marker), subject].filter(Boolean).join('  ·  '),
        {fontSize: 12, color: muted, margin: [0, 5, 0, 18]}),
      resultCard(model, l, short),
    ];
    if (short && model.facts.length) {
      const facts = model.facts.map(row => ({
        label: plain(row.label), value: Array.from(plain(row.value)).length > 65 ? l.more : plain(row.value),
      }));
      content.push(section(l.facts), keyValues(facts));
    }
    content.push(section(l.context), keyValues(idRows));
    if (short && abbreviated) content.push({text: l.abbreviated, fontSize: 9, color: muted, margin: [0, 4, 0, 0]});
    if (!short) {
      if (model.chart) content.push(...chartSection(model.chart, model.language));
      if (model.metrics.length) content.push(section(l.metrics), keyValues(model.metrics));
      if (model.table) content.push(...tableSection(model.table));
      if (model.provenance.length) content.push({unbreakable: model.provenance.length <= 8,
        stack: [section(l.source), keyValues(model.provenance)]});
    }
    if (model.notes.length) {
      if (!short) content.push(section(l.notes));
      for (const note of model.notes) content.push({text: plain(note), fontSize: short ? 9 : 10,
        color: muted, margin: [0, short ? 5 : 3, 0, 0]});
    }
    return {
      info: {title, author: 'NewPat', subject: plain(model.module)}, language: model.language,
      pageSize: 'A4', pageMargins: [47, 83, 47, 58], defaultStyle: {font: 'Roboto', fontSize: 10.5, color: ink},
      header: () => ({margin: [47, 31, 47, 0], stack: [
        {columns: [{svg: logo, width: 99}, {width: '*', text: l.research, alignment: 'right', fontSize: 10, color: muted}]},
        {canvas: [{type: 'line', x1: 0, y1: 9, x2: 501, y2: 9, lineWidth: 0.65, lineColor: line}]},
      ]}),
      footer: (page, pages) => {
        if (short && pages !== 1) throw new Error(l.overflow);
        const version = plain(model.version);
        return {margin: [47, 6, 47, 0], stack: [
          {canvas: [{type: 'line', x1: 0, y1: 0, x2: 501, y2: 0, lineWidth: 0.65, lineColor: line}]},
          {columns: [{width: '*', text: 'NewPat' + (version ? '  ·  ' + shorten(version, 30) : '')},
            ...(short && model.case_id ? [{width: 'auto', text: l.caseId + '  ' + plain(model.case_id).slice(0, 12)}] : []),
            {width: '*', text: l.page + ' ' + page + ' ' + l.of + ' ' + pages, alignment: 'right'}],
            fontSize: 9, color: muted, margin: [0, 8, 0, 0]},
        ]};
      },
      pageBreakBefore: (node, following) => node.headlineLevel === 1 && following.getFollowingNodesOnPage().length === 0,
      content,
    };
  }

  async function render(model, kind) {
    if (kind !== 'summary' && kind !== 'detailed') throw new Error('Invalid PDF report kind.');
    let logo;
    try { logo = await loadAssets(); }
    catch { throw new Error((copy[model.language] || copy.it).failure); }
    return window.pdfMake.createPdf(definition(model, kind, logo)).getBase64();
  }

  window.NewPatReports = {render};
})();
