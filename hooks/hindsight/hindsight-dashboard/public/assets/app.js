const els = {
  pathInput: document.querySelector('#pathInput'),
  openBtn: document.querySelector('#openBtn'),
  reloadBtn: document.querySelector('#reloadBtn'),
  applyBtn: document.querySelector('#applyBtn'),
  clearBtn: document.querySelector('#clearBtn'),
  eventsInput: document.querySelector('#eventsInput'),
  grepInput: document.querySelector('#grepInput'),
  limitInput: document.querySelector('#limitInput'),
  quickFilters: document.querySelector('#quickFilters'),
  metrics: document.querySelector('#metrics'),
  streamStatus: document.querySelector('#streamStatus'),
  logBody: document.querySelector('#logBody'),
  tableInfo: document.querySelector('#tableInfo'),
  tableWrap: document.querySelector('#tableWrap'),
  autoScroll: document.querySelector('#autoScroll'),
  newestFirst: document.querySelector('#newestFirst'),
  detailDialog: document.querySelector('#detailDialog'),
  detailTitle: document.querySelector('#detailTitle'),
  detailSubtitle: document.querySelector('#detailSubtitle'),
  detailBody: document.querySelector('#detailBody'),
  closeDialog: document.querySelector('#closeDialog')
};

const state = {
  events: [],
  eventSource: null,
  maxRows: 2000,
  path: '',
  tailOffset: 0,
  newestFirst: true,
  seenRaw: new Set()
};

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function truncate(value, n = 260) {
  const s = String(value ?? '');
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

function formatBytes(n) {
  n = Number(n || 0);
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KiB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MiB`;
  return `${(n / 1024 ** 3).toFixed(1)} GiB`;
}

function formatTime(tsRaw) {
  if (!tsRaw) return '';
  const date = new Date(tsRaw);
  if (Number.isNaN(date.getTime())) return tsRaw;

  const pad = (n, size = 2) => String(n).padStart(size, '0');
  return [
    date.getFullYear(), '-', pad(date.getMonth() + 1), '-', pad(date.getDate()), ' ',
    pad(date.getHours()), ':', pad(date.getMinutes()), ':', pad(date.getSeconds()), '.',
    pad(date.getMilliseconds(), 3)
  ].join('');
}

function qs() {
  const params = new URLSearchParams();
  params.set('limit', els.limitInput.value || '500');
  if (els.eventsInput.value.trim()) params.set('events', els.eventsInput.value.trim());
  if (els.grepInput.value.trim()) params.set('grep', els.grepInput.value.trim());
  return params;
}

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const text = await res.text();
  let payload = {};
  try { payload = text ? JSON.parse(text) : {}; } catch (_) { payload = { raw: text }; }
  if (!res.ok) throw new Error(payload.error || `HTTP ${res.status}`);
  return payload;
}

function setStatus(text, cls = '') {
  els.streamStatus.textContent = text;
  els.streamStatus.className = `status-pill ${cls}`.trim();
}

function metric(label, value, tiny = '') {
  return `<div class="metric-card"><div class="label">${escapeHtml(label)}</div><div class="value">${escapeHtml(value)}</div><div class="tiny" title="${escapeHtml(tiny)}">${escapeHtml(tiny)}</div></div>`;
}

function renderMetrics(payload) {
  const status = payload.status || payload;
  const counts = payload.counts || {};
  const levels = payload.level_counts || {};
  const eventSummary = Object.entries(counts).map(([k, v]) => `${k}:${v}`).join(' · ');
  const levelSummary = Object.entries(levels).map(([k, v]) => `${k}:${v}`).join(' · ');

  els.metrics.innerHTML = [
    metric('file', status.exists ? 'OK' : 'missing', status.path || state.path),
    metric('size', formatBytes(status.size), status.mtime ? `mtime ${formatTime(status.mtime)}` : ''),
    metric('righe', payload.total_lines ?? '-', `visibili ${payload.events?.length ?? state.events.length}`),
    metric('ultimo', payload.last_ts ? formatTime(payload.last_ts) : '-', `tail offset ${payload.tail_offset ?? state.tailOffset ?? 0}`),
    metric('eventi', Object.keys(counts).length || '-', eventSummary),
    metric('livelli', Object.keys(levels).length || '-', levelSummary)
  ].join('');
}

function levelBadge(level) {
  return `<span class="badge">${escapeHtml(level)}</span>`;
}

function rowHtml(event, index) {
  return `<tr class="${escapeHtml(event.css_class || '')}" data-index="${index}">
    <td class="time">${escapeHtml(formatTime(event.ts_raw))}</td>
    <td class="level">${levelBadge(event.level)}</td>
    <td class="event">${escapeHtml(event.event)}</td>
    <td class="status">${escapeHtml(event.status)}</td>
    <td class="cache">${escapeHtml(event.cache)}</td>
    <td class="n">${escapeHtml(event.n_results)}</td>
    <td class="mem">${escapeHtml(event.memories_count)}</td>
    <td class="doc" title="${escapeHtml(event.doc_id)}">${escapeHtml(event.doc_id)}</td>
    <td class="message" title="${escapeHtml(event.message)}">${escapeHtml(truncate(event.message))}</td>
  </tr>`;
}

function renderTable() {
  const rows = state.newestFirst
    ? state.events.map((event, index) => [event, index]).reverse()
    : state.events.map((event, index) => [event, index]);

  els.logBody.innerHTML = rows.map(([event, index]) => rowHtml(event, index)).join('');
  els.tableInfo.textContent = `${state.events.length} eventi caricati · ${state.newestFirst ? 'ultimi in alto' : 'ultimi in basso'}`;

  if (els.autoScroll.checked && !state.newestFirst) {
    els.tableWrap.scrollTop = els.tableWrap.scrollHeight;
  } else if (els.autoScroll.checked && state.newestFirst) {
    els.tableWrap.scrollTop = 0;
  }
}

function eventKey(event) {
  return event.raw || `${event.ts_raw}|${event.event}|${event.message}|${event.doc_id}`;
}

function appendEvent(event) {
  const key = eventKey(event);
  if (state.seenRaw.has(key)) return;

  state.seenRaw.add(key);
  state.events.push(event);

  while (state.events.length > state.maxRows) {
    const removed = state.events.shift();
    state.seenRaw.delete(eventKey(removed));
  }

  renderTable();
}

function clearTable() {
  state.events = [];
  state.seenRaw = new Set();
  renderTable();
}

function scalarClass(value) {
  if (typeof value === 'string') return 'json-string';
  if (typeof value === 'number') return 'json-number';
  if (typeof value === 'boolean') return 'json-bool';
  if (value === null) return 'json-null';
  return '';
}

function renderJson(value, label = 'root', open = true) {
  if (Array.isArray(value)) {
    const children = value.map((item, i) => renderJson(item, `[${i}]`, false)).join('');
    return `<details ${open ? 'open' : ''}><summary><span class="json-key">${escapeHtml(label)}</span> Array(${value.length})</summary><div class="children">${children}</div></details>`;
  }

  if (value && typeof value === 'object') {
    const entries = Object.entries(value).map(([k, v]) => renderJson(v, k, false)).join('');
    return `<details ${open ? 'open' : ''}><summary><span class="json-key">${escapeHtml(label)}</span> Object(${Object.keys(value).length})</summary><div class="children">${entries}</div></details>`;
  }

  return `<div><span class="json-key">${escapeHtml(label)}</span>: <span class="${scalarClass(value)}">${escapeHtml(value === null ? 'null' : value)}</span></div>`;
}

function renderMemories(memories) {
  if (!Array.isArray(memories) || memories.length === 0) {
    return '<section><h3>Memories</h3><p class="subtitle">Nessuna memory in questo evento.</p></section>';
  }

  const cards = memories.map((m, i) => {
    const type = m?.type ?? '';
    const text = m?.text ?? '';
    const entities = Array.isArray(m?.entities) ? m.entities : [];
    const chips = entities.map(e => `<span class="entity">${escapeHtml(e)}</span>`).join('');

    return `<details open>
      <summary>#${i + 1} ${escapeHtml(type || 'memory')}</summary>
      <div class="memory-card">
        <div class="summary-grid">
          <div class="summary-item"><div class="k">type</div><div class="v">${escapeHtml(type)}</div></div>
          <div class="summary-item"><div class="k">entities</div><div class="v">${escapeHtml(entities.length)}</div></div>
        </div>
        <h3 style="margin-top: .8rem; margin-bottom: .45rem;">text</h3>
        <div class="memory-text">${escapeHtml(text)}</div>
        <div class="entities">${chips}</div>
      </div>
    </details>`;
  }).join('');

  return `<section><h3>Memories (${memories.length})</h3><div class="memory-list">${cards}</div></section>`;
}

function openDetail(event) {
  const data = event.data || {};
  const memories = Array.isArray(data.memories) ? data.memories : [];

  els.detailTitle.textContent = `${event.event} · ${event.level}`;
  els.detailSubtitle.textContent = `${formatTime(event.ts_raw)} · line ${event.line ?? 'live'} · memories ${memories.length}`;

  els.detailBody.innerHTML = `
    <section class="summary-grid">
      <div class="summary-item"><div class="k">event</div><div class="v">${escapeHtml(event.event)}</div></div>
      <div class="summary-item"><div class="k">level</div><div class="v">${escapeHtml(event.level)}</div></div>
      <div class="summary-item"><div class="k">status</div><div class="v">${escapeHtml(event.status)}</div></div>
      <div class="summary-item"><div class="k">cache</div><div class="v">${escapeHtml(event.cache)}</div></div>
      <div class="summary-item"><div class="k">n_results</div><div class="v">${escapeHtml(event.n_results)}</div></div>
      <div class="summary-item"><div class="k">doc_id</div><div class="v">${escapeHtml(event.doc_id)}</div></div>
    </section>
    ${renderMemories(memories)}
    <section>
      <h3>JSON completo</h3>
      <div class="json-tree">${renderJson(data, 'event', true)}</div>
    </section>
    <section>
      <h3>Raw line</h3>
      <pre class="json-tree">${escapeHtml(event.raw)}</pre>
    </section>
  `;

  els.detailDialog.showModal();
}

async function loadInitial() {
  const payload = await api(`/api/events?${qs().toString()}`);
  state.path = payload.path;
  els.pathInput.value = payload.path;
  state.tailOffset = Number(payload.tail_offset || 0);
  state.events = payload.events || [];
  state.seenRaw = new Set(state.events.map(eventKey));
  renderMetrics(payload);
  renderTable();
}

function connectStream() {
  if (state.eventSource) state.eventSource.close();

  const params = qs();
  params.delete('limit');
  params.set('offset', String(state.tailOffset || 0));
  const suffix = params.toString() ? `?${params.toString()}` : '';
  const es = new EventSource(`/api/stream${suffix}`);
  state.eventSource = es;
  setStatus('connecting');

  es.addEventListener('ready', (ev) => {
    const payload = JSON.parse(ev.data);
    setStatus(`live · offset ${payload.offset ?? 0}`, 'online');
    if (payload.path) state.path = payload.path;
  });

  es.addEventListener('opened', (ev) => {
    const payload = JSON.parse(ev.data);
    state.path = payload.path;
    els.pathInput.value = payload.path;
    setStatus('live', 'online');
  });

  es.addEventListener('rotated', () => setStatus('rotated', 'online'));
  es.addEventListener('missing', () => setStatus('file missing', 'error'));
  es.addEventListener('tail_error', (ev) => {
    console.error('tail_error', ev.data);
    setStatus('tail error', 'error');
  });

  es.addEventListener('log', (ev) => {
    const event = JSON.parse(ev.data);
    appendEvent(event);
    setStatus('live · nuovo evento', 'online');
  });

  es.onerror = () => setStatus('reconnecting', 'error');
}

async function openPath() {
  const path = els.pathInput.value.trim();
  if (!path) return;

  const payload = await api('/api/open', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path })
  });

  state.path = payload.path;
  renderMetrics(payload);
  await loadInitial();
  connectStream();
}

els.logBody.addEventListener('click', (ev) => {
  const row = ev.target.closest('tr[data-index]');
  if (!row) return;
  const event = state.events[Number(row.dataset.index)];
  if (event) openDetail(event);
});

els.closeDialog.addEventListener('click', () => els.detailDialog.close());
els.openBtn.addEventListener('click', () => openPath().catch(err => alert(err.message)));
els.reloadBtn.addEventListener('click', async () => { await loadInitial(); connectStream(); });
els.applyBtn.addEventListener('click', async () => {
  await loadInitial();
  connectStream();
});
els.clearBtn.addEventListener('click', clearTable);
els.newestFirst.addEventListener('change', () => {
  state.newestFirst = els.newestFirst.checked;
  renderTable();
});
els.quickFilters.addEventListener('click', async (ev) => {
  const btn = ev.target.closest('button[data-events]');
  if (!btn) return;
  els.eventsInput.value = btn.dataset.events;
  await loadInitial();
  connectStream();
});

window.addEventListener('beforeunload', () => {
  if (state.eventSource) state.eventSource.close();
});

(async function boot() {
  try {
    const status = await api('/api/status');
    state.path = status.path;
    els.pathInput.value = status.path;
    renderMetrics(status);
    await loadInitial();
    connectStream();
  } catch (err) {
    setStatus('boot error', 'error');
    console.error(err);
  }
})();
