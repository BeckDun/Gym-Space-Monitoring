'use strict';

const ZONE_CAPS = { cardio_zone: 5, smart_machine_zone: 5, cycling_zone: 5, functional_zone: 5 };
const alertList      = document.getElementById('alert-list');
const criticalSection = document.getElementById('critical-section');
const criticalList   = document.getElementById('critical-list');
const alertCount     = document.getElementById('alert-count');
const wsStatus       = document.getElementById('ws-status');
const dbAlerts       = document.getElementById('db-alerts');

let alerts = {};  // alert_id → alert object

// ── WebSocket ─────────────────────────────────────────────────────────────────
function connectWS() {
  const ws = new WebSocket(`ws://${location.host}/ws/alerts`);

  ws.onopen = () => {
    wsStatus.textContent = '● Live';
    wsStatus.className = 'ws-status connected';
  };

  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'member_update') {
      updateMemberCount(msg.in_gym_count);
      return;
    }
    if (msg.type === 'zone_update') {
      updateZonesLive(msg.zones || {}, msg.alert_states || {});
      return;
    }
    if (!msg.resolved) {
      alerts[msg.alert_id] = msg;
    } else {
      delete alerts[msg.alert_id];
    }
    renderAlerts();
  };

  ws.onclose = () => {
    wsStatus.textContent = '● Disconnected';
    wsStatus.className = 'ws-status error';
    setTimeout(connectWS, 3000);
  };

  ws.onerror = () => ws.close();
}

// ── Build alert card HTML ─────────────────────────────────────────────────────
function buildAlertCard(a) {
  const card = document.createElement('div');
  card.className = `alert-card ${a.severity}`;
  card.dataset.id = a.alert_id;
  const ts = a.timestamp ? new Date(a.timestamp).toLocaleTimeString() : '';
  card.innerHTML = `
    <div class="alert-top">
      <span class="sev-badge">${a.severity}</span>
      <span class="alert-zone">${a.zone_id || ''}</span>
      <span class="alert-ts">${ts}</span>
    </div>
    <div class="alert-desc">${esc(a.description || '')}</div>
    ${a.member_id ? `<div class="alert-member">Member: ${esc(a.member_id)}</div>` : ''}
    <button class="resolve-btn" onclick="resolveAlert('${a.alert_id}')">Resolved</button>
  `;
  return card;
}

// ── Render active alerts — CRITICAL pinned, others scrollable ─────────────────
function renderAlerts() {
  const list = Object.values(alerts).filter(a => !a.resolved);
  alertCount.textContent = list.length;
  alertCount.classList.toggle('visible', list.length > 0);

  const criticals = list.filter(a => a.severity === 'CRITICAL');
  const others    = list.filter(a => a.severity !== 'CRITICAL').sort((a, b) => {
    const sev = { WARNING: 0, INFO: 1 };
    return (sev[a.severity] ?? 2) - (sev[b.severity] ?? 2);
  });

  // Pinned critical section
  if (criticals.length) {
    criticalSection.classList.remove('hidden');
    criticalList.innerHTML = '';
    criticals.forEach(a => criticalList.appendChild(buildAlertCard(a)));
  } else {
    criticalSection.classList.add('hidden');
    criticalList.innerHTML = '';
  }

  // Scrollable warning / info list
  if (!others.length) {
    alertList.innerHTML = criticals.length
      ? '<div class="empty-state">No additional alerts.</div>'
      : '<div class="empty-state">No active alerts.</div>';
    return;
  }

  alertList.innerHTML = '';
  others.forEach(a => alertList.appendChild(buildAlertCard(a)));
}

// ── Resolve alert ─────────────────────────────────────────────────────────────
async function resolveAlert(alertId) {
  try {
    await fetch(`/api/resolve/${alertId}`, { method: 'POST' });
    delete alerts[alertId];
    renderAlerts();
    await loadDbAlerts();
  } catch (e) {
    console.error('Resolve failed:', e);
  }
}
window.resolveAlert = resolveAlert;

// ── Poll active alerts (REST fallback if WS drops) ───────────────────────────
async function pollAlerts() {
  try {
    const data = await fetch('/api/alerts').then(r => r.json());
    alerts = {};
    (data.alerts || []).forEach(a => { alerts[a.alert_id] = a; });
    renderAlerts();
  } catch { /* ignore */ }
}

// ── Zone occupancy (from DB state) ───────────────────────────────────────────
async function loadDbState() {
  try {
    const state = await fetch('/api/demos/db-state').then(r => r.json());
    updateZones(state.occupancy_snapshots || []);
    await loadDbAlerts(state.alert_logs || []);
  } catch { /* ignore */ }
}

function updateZones(snapshots) {
  const latest = {};
  for (const s of snapshots) {
    if (!latest[s.zone_id] || s.timestamp > latest[s.zone_id].timestamp) {
      latest[s.zone_id] = s;
    }
  }
  document.querySelectorAll('.zone-card').forEach(card => {
    const zone = card.dataset.zone;
    const snap = latest[zone];
    const count = snap ? snap.count : 0;
    const cap   = ZONE_CAPS[zone] || 20;
    const pct   = Math.min(100, Math.round((count / cap) * 100));
    card.querySelector('.zone-count').textContent = count;
    card.querySelector('.zone-fill').style.width = pct + '%';
    card.classList.remove('overcrowded', 'near-capacity');
    if (count >= cap) card.classList.add('overcrowded');
    else if (count >= cap * 0.8) card.classList.add('near-capacity');
  });
}

// Live zone update pushed via WebSocket — includes demo alert_states so the
// zone card shows overcrowded/near-capacity even before the real cap is reached.
function updateZonesLive(counts, alertStates) {
  document.querySelectorAll('.zone-card').forEach(card => {
    const zone  = card.dataset.zone;
    if (!(zone in counts)) return;
    const count = counts[zone] || 0;
    const cap   = ZONE_CAPS[zone] || 20;
    const pct   = Math.min(100, Math.round((count / cap) * 100));
    card.querySelector('.zone-count').textContent = count;
    card.querySelector('.zone-fill').style.width  = pct + '%';
    card.classList.remove('overcrowded', 'near-capacity');
    const state = alertStates[zone];
    if (state === 'overcrowded'   || count >= cap)       card.classList.add('overcrowded');
    else if (state === 'near-capacity' || count >= cap * 0.8) card.classList.add('near-capacity');
  });
}

async function loadDbAlerts(rows) {
  if (!rows) {
    try {
      const state = await fetch('/api/demos/db-state').then(r => r.json());
      rows = state.alert_logs || [];
    } catch { return; }
  }
  dbAlerts.innerHTML = '';
  if (!rows.length) {
    dbAlerts.innerHTML = '<div style="color:#8890aa;font-size:11px;font-style:italic;padding:4px 0">No logged alerts yet.</div>';
    return;
  }
  rows.slice(0, 10).forEach(r => {
    const div = document.createElement('div');
    div.className = 'db-alert-row';
    div.innerHTML = `
      <span class="sev ${r.severity}">${r.severity}</span>
      <span style="color:#8890aa">${r.zone_id || '—'}</span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc((r.description || '').slice(0, 60))}</span>
      <span style="color:${r.resolved ? '#3ecf8e' : '#8890aa'}">${r.resolved ? 'Resolved' : 'Active'}</span>
    `;
    dbAlerts.appendChild(div);
  });
}

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

// ── Member count ──────────────────────────────────────────────────────────────
function updateMemberCount(count) {
  const el = document.getElementById('member-count');
  if (el) el.textContent = `${count} in gym`;
}

async function loadMemberCount() {
  try {
    const data = await fetch('/api/members/status').then(r => r.json());
    const count = (data.members || []).filter(m => m.in_gym).length;
    updateMemberCount(count);
  } catch { /* ignore */ }
}

// ── Init ──────────────────────────────────────────────────────────────────────
connectWS();
pollAlerts();
loadDbState();
loadMemberCount();
setInterval(loadDbState, 5000);
setInterval(pollAlerts, 3000);
setInterval(loadMemberCount, 10000);
