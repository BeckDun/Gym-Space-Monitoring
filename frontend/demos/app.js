'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
let currentDemo = null;
let currentTable = 'alert_logs';
let dbState = {};
let eventSource = null;

// ── DOM refs ──────────────────────────────────────────────────────────────────
const logArea      = document.getElementById('log-area');
const logSpinner   = document.getElementById('log-spinner');
const spinnerLabel = document.getElementById('spinner-label');
const demoTitle    = document.getElementById('demo-title');
const demoBadge    = document.getElementById('demo-badge');
const dbArea       = document.getElementById('db-area');
const apiStatus    = document.getElementById('api-status');
const demoVideo    = document.getElementById('demo-video');
const videoArea    = document.getElementById('video-area');
const videoPlaceholder = videoArea.querySelector('.video-placeholder');

// ── API helpers ────────────────────────────────────────────────────────────────
async function apiFetch(path, opts = {}) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

async function checkHealth() {
  try {
    await apiFetch('/health');
    apiStatus.textContent = '● Backend connected';
    apiStatus.className = 'api-status ok';
  } catch {
    apiStatus.textContent = '● Backend unreachable';
    apiStatus.className = 'api-status err';
  }
}

// ── Demo buttons ──────────────────────────────────────────────────────────────
document.querySelectorAll('.demo-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    if (eventSource) { eventSource.close(); eventSource = null; }
    const demo = btn.dataset.demo;
    const hasVideo = btn.dataset.video === 'true';
    startDemo(demo, btn.querySelector('.label').textContent, hasVideo);
    document.querySelectorAll('.demo-btn').forEach(b => b.classList.remove('active', 'running'));
    btn.classList.add('active');
  });
});

// ── Log rendering ─────────────────────────────────────────────────────────────
function clearLog() {
  logArea.innerHTML = '';
}

function appendLogEntry(entry) {
  // Remove placeholder
  const ph = logArea.querySelector('.log-placeholder');
  if (ph) ph.remove();

  const div = document.createElement('div');
  div.className = `log-entry type-${entry.type || 'info'}`;

  const ts = entry.ts ? new Date(entry.ts).toLocaleTimeString() : '';

  div.innerHTML = `
    ${entry.arrow ? `<div class="log-arrow">→ ${entry.arrow}</div>` : ''}
    ${entry.step && !entry.arrow ? `<div class="log-step">${entry.step}</div>` : ''}
    ${entry.msg ? `<div class="log-msg">${escHtml(entry.msg)}</div>` : ''}
    ${ts ? `<div class="log-ts">${ts}</div>` : ''}
  `;
  logArea.appendChild(div);
  logArea.scrollTop = logArea.scrollHeight;
}

function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Video helper ──────────────────────────────────────────────────────────────
function showVideo(show) {
  if (show) {
    videoPlaceholder.classList.add('hidden');
    demoVideo.classList.remove('hidden');
    demoVideo.currentTime = 0;
    demoVideo.play().catch(() => {});
  } else {
    demoVideo.pause();
    demoVideo.classList.add('hidden');
    videoPlaceholder.classList.remove('hidden');
  }
}

// ── Run demo via SSE ──────────────────────────────────────────────────────────
function startDemo(demoName, label, hasVideo) {
  currentDemo = demoName;
  clearLog();
  demoBadge.textContent = 'Running';
  demoBadge.className = 'badge running';
  demoBadge.classList.remove('hidden');
  demoTitle.textContent = label;
  spinnerLabel.textContent = 'Running demo...';
  logSpinner.classList.remove('hidden');

  showVideo(hasVideo);

  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/api/demos/stream/${demoName}`);

  eventSource.onmessage = (e) => {
    const entry = JSON.parse(e.data);

    if (entry.type === 'done') {
      eventSource.close();
      eventSource = null;
      logSpinner.classList.add('hidden');
      demoBadge.textContent = 'Complete';
      demoBadge.className = 'badge done';
      document.querySelectorAll('.demo-btn').forEach(b => b.classList.remove('running'));
      // Refresh DB view
      loadDbState();
      return;
    }

    if (entry.type === 'error') {
      logSpinner.classList.add('hidden');
      demoBadge.textContent = 'Error';
      demoBadge.className = 'badge error';
    }

    appendLogEntry(entry);
  };

  eventSource.onerror = () => {
    logSpinner.classList.add('hidden');
    demoBadge.textContent = 'Error';
    demoBadge.className = 'badge error';
    appendLogEntry({ type: 'error', msg: 'Stream connection lost.', arrow: '' });
    eventSource.close();
    eventSource = null;
  };

  // Mark button running
  document.querySelectorAll('.demo-btn').forEach(b => {
    if (b.dataset.demo === demoName) b.classList.add('running');
  });
}

// ── Database viewer ───────────────────────────────────────────────────────────
async function loadDbState() {
  try {
    dbState = await apiFetch('/api/demos/db-state');
    renderDbTable(currentTable);
  } catch (e) {
    dbArea.innerHTML = `<div class="db-placeholder">Failed to load DB: ${e.message}</div>`;
  }
}

function renderDbTable(tableName) {
  currentTable = tableName;
  document.querySelectorAll('.db-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.table === tableName);
  });

  const rows = dbState[tableName] || [];
  if (!rows.length) {
    dbArea.innerHTML = '<div class="db-placeholder">No records yet — run a demo first.</div>';
    return;
  }

  const cols = Object.keys(rows[0]);
  let html = '<table><thead><tr>' + cols.map(c => `<th>${c}</th>`).join('') + '</tr></thead><tbody>';

  for (const row of rows) {
    html += '<tr>' + cols.map(col => {
      let val = row[col];
      let cls = '';
      if (col === 'severity' && val) cls = `class="sev-${val}"`;
      if (col === 'resolved') {
        cls = val ? 'class="resolved-yes"' : 'class="resolved-no"';
        val = val ? 'Yes' : 'No';
      }
      if (typeof val === 'string' && val.length > 60) val = val.slice(0, 60) + '…';
      return `<td ${cls}>${val === null || val === undefined ? '—' : escHtml(String(val))}</td>`;
    }).join('') + '</tr>';
  }

  html += '</tbody></table>';
  dbArea.innerHTML = html;
}

document.querySelectorAll('.db-tab').forEach(tab => {
  tab.addEventListener('click', () => renderDbTable(tab.dataset.table));
});

// ── Sidebar actions ───────────────────────────────────────────────────────────
document.getElementById('btn-reset').addEventListener('click', async () => {
  if (!confirm('Reset all demo data? This will clear alerts, equipment, biometrics, and occupancy logs.')) return;
  try {
    await apiFetch('/api/demos/reset', { method: 'POST' });
    clearLog();
    appendLogEntry({ type: 'info', arrow: 'System', msg: 'Database reset — seed members restored.', ts: new Date().toISOString() });
    await loadDbState();
  } catch (e) {
    alert('Reset failed: ' + e.message);
  }
});

document.getElementById('btn-refresh-db').addEventListener('click', loadDbState);
document.getElementById('btn-clear-log').addEventListener('click', () => {
  logArea.innerHTML = '<div class="log-placeholder">Log cleared.</div>';
});

// ── Init ──────────────────────────────────────────────────────────────────────
checkHealth();
loadDbState();
setInterval(checkHealth, 10000);
