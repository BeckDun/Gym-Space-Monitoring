'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
let currentDemo = null;
let currentTable = 'alert_logs';
let dbState = {};
let eventSource = null;

// Selected clip path (backend path) per MLLM demo
const selectedClip = {
  fall_detection:     'assets/fall_obvious.mp4',
  conflict_detection: 'assets/conflict_fight.mp4',
};

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

// ── Clip picker buttons ───────────────────────────────────────────────────────
document.querySelectorAll('.clip-opt').forEach(opt => {
  opt.addEventListener('click', () => {
    const demo = opt.dataset.demo;
    // Update selection state
    document.querySelectorAll(`.clip-opt[data-demo="${demo}"]`).forEach(o => o.classList.remove('active'));
    opt.classList.add('active');
    selectedClip[demo] = opt.dataset.clip;
  });
});

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
function showVideo(show, assetUrl = null) {
  if (show) {
    if (assetUrl) {
      // Swap source and reload before playing
      const src = demoVideo.querySelector('source');
      if (src) src.src = assetUrl;
      else demoVideo.src = assetUrl;
      demoVideo.load();
    }
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

  // For MLLM demos, pick the active clip and pass it to both the player and backend
  const clip      = selectedClip[demoName] || null;
  const activeOpt = clip
    ? document.querySelector(`.clip-opt[data-demo="${demoName}"][data-clip="${clip}"]`)
    : null;
  const assetUrl = activeOpt ? activeOpt.dataset.asset : null;

  showVideo(hasVideo, assetUrl);

  if (eventSource) eventSource.close();
  const url = clip
    ? `/api/demos/stream/${demoName}?video=${encodeURIComponent(clip)}`
    : `/api/demos/stream/${demoName}`;
  eventSource = new EventSource(url);

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

// ── Member status ─────────────────────────────────────────────────────────────
async function loadMemberStatus() {
  try {
    const data = await apiFetch('/api/members/status');
    renderMemberStatus(data.members || []);
    populateTapInSelect(data.members || []);
  } catch { /* ignore */ }
}

function renderMemberStatus(members) {
  const inCount = members.filter(m => m.in_gym).length;
  const counts = document.getElementById('member-status-counts');
  if (counts) counts.textContent = `${inCount} in · ${members.length - inCount} out`;

  const list = document.getElementById('member-list');
  if (!list) return;

  if (!members.length) {
    list.innerHTML = '<div class="db-placeholder">No members registered.</div>';
    return;
  }

  const sorted = [...members].sort((a, b) => (b.in_gym ? 1 : 0) - (a.in_gym ? 1 : 0));
  list.innerHTML = sorted.map(m => {
    const avgHr = Math.round((m.hr_low + m.hr_high) / 2);
    return `
    <div class="member-card ${m.in_gym ? 'in-gym' : 'not-gym'}">
      <div class="status-dot ${m.in_gym ? 'in-gym' : 'not-gym'}"></div>
      <div class="member-info">
        <span class="member-name">${escHtml(m.name)}</span>
        <span class="member-hr">♥ avg <span class="hr-val">${avgHr} bpm</span> &nbsp;·&nbsp; ${m.hr_low}–${m.hr_high} range</span>
      </div>
      <span class="member-badge ${m.in_gym ? 'in-gym' : 'not-gym'}">${m.in_gym ? 'In Gym' : 'Out'}</span>
    </div>`;
  }).join('');
}

function populateTapInSelect(members) {
  const sel = document.getElementById('tap-in-select');
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = '<option value="">— select member —</option>';
  members.forEach(m => {
    const opt = document.createElement('option');
    opt.value = m.id;
    opt.textContent = `${m.name} (${m.id})${m.in_gym ? ' ✓' : ''}`;
    if (m.in_gym) opt.disabled = true;
    sel.appendChild(opt);
  });
  if (current) sel.value = current;
}

// ── Sidebar actions ───────────────────────────────────────────────────────────
document.getElementById('btn-reset').addEventListener('click', async () => {
  if (!confirm('Reset all demo data? This will clear alerts, equipment, biometrics, and occupancy logs.')) return;
  try {
    await apiFetch('/api/demos/reset', { method: 'POST' });
    clearLog();
    appendLogEntry({ type: 'info', arrow: 'System', msg: 'Database reset — seed members restored.', ts: new Date().toISOString() });
    await loadDbState();
    await loadMemberStatus();
  } catch (e) {
    alert('Reset failed: ' + e.message);
  }
});

document.getElementById('btn-add-member').addEventListener('click', async () => {
  const btn = document.getElementById('btn-add-member');
  btn.disabled = true; btn.textContent = 'Registering…';
  try {
    appendLogEntry({ type: 'info', arrow: 'System → DatabaseController',
      msg: 'add_member() — generating health profile and inserting new Member record',
      ts: new Date().toISOString() });
    const res = await apiFetch('/api/members/add', { method: 'POST' });
    if (res.success) {
      const m = res.member;
      appendLogEntry({ type: 'result', arrow: 'DatabaseController → Data Store',
        msg: `New member registered: ${m.name} (${m.id}) — Age: ${m.age}, Activity: ${m.activity_level}, HR thresholds: ${m.hr_low}–${m.hr_high} bpm`,
        ts: new Date().toISOString() });
      currentTable = 'members';
      await loadDbState();
      await loadMemberStatus();
    } else {
      appendLogEntry({ type: 'error', arrow: 'DatabaseController', msg: `Registration failed: ${res.error}`, ts: new Date().toISOString() });
    }
  } catch (e) {
    alert('Add member failed: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = '➕ Register New Member';
  }
});

document.getElementById('btn-tap-in').addEventListener('click', async () => {
  const memberId = document.getElementById('tap-in-select').value;
  if (!memberId) { alert('Select a member first.'); return; }
  const btn = document.getElementById('btn-tap-in');
  btn.disabled = true; btn.textContent = 'Tapping…';
  try {
    // Log the flow to the log panel
    appendLogEntry({ type: 'info', arrow: 'EntranceDriver → SensorInterface',
      msg: `read() — member_id='${memberId}', action='entry' (NFC tap at entrance)`,
      ts: new Date().toISOString() });
    appendLogEntry({ type: 'info', arrow: 'SensorInterface → DatabaseController',
      msg: `normalize_signal(RawSignal) → Event(type='session', action='entry')`,
      ts: new Date().toISOString() });

    const res = await apiFetch(`/api/tap-in/${memberId}`, { method: 'POST' });
    if (res.success) {
      appendLogEntry({ type: 'result', arrow: 'DatabaseController → Data Store',
        msg: `log_session() → GymSession created: ${res.name} (${res.member_id}) tapped in at ${new Date(res.entry_time).toLocaleTimeString()}`,
        ts: new Date().toISOString() });
      await loadMemberStatus();
      await loadDbState();
    } else {
      appendLogEntry({ type: 'error', arrow: 'System', msg: `Tap-in failed: ${res.error}`, ts: new Date().toISOString() });
    }
  } catch (e) {
    appendLogEntry({ type: 'error', arrow: 'System', msg: `Tap-in error: ${e.message}`, ts: new Date().toISOString() });
  } finally {
    btn.disabled = false; btn.textContent = 'Tap In';
  }
});

document.getElementById('btn-refresh-db').addEventListener('click', loadDbState);
document.getElementById('btn-clear-log').addEventListener('click', () => {
  logArea.innerHTML = '<div class="log-placeholder">Log cleared.</div>';
});

// ── Init ──────────────────────────────────────────────────────────────────────
checkHealth();
loadDbState();
loadMemberStatus();
setInterval(checkHealth, 10000);
setInterval(loadMemberStatus, 5000);
