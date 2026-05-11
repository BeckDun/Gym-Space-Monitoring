'use strict';

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

let _alertRecords = [];

async function generateReport() {
  const schedule = document.getElementById('schedule-select').value;
  const btn = document.getElementById('btn-generate');
  btn.disabled = true;
  btn.textContent = 'Generating…';

  try {
    const report = await fetch(`/api/report/${schedule}`).then(r => r.json());
    if (report.error) { alert('Report error: ' + report.error); return; }
    renderReport(report);
    const mockLabel = report.is_mock ? ' — Demo Data (no API key)' : '';
    document.getElementById('report-ts').textContent =
      `Generated: ${new Date(report.generated_at).toLocaleString()} | Period: last ${schedule}${mockLabel}`;
  } catch (e) {
    alert('Failed to generate report: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Generate Report';
  }
}

function renderReport(report) {
  const eq = report.equipment_summary || {};
  const occ = report.occupancy_summary || {};
  const al = report.alert_summary || {};

  document.getElementById('stat-sessions').textContent  = eq.total_sessions ?? '0';
  document.getElementById('stat-peak').textContent      = occ.peak_count ?? '0';
  document.getElementById('stat-avg').textContent       = occ.average_count ?? '0';
  document.getElementById('stat-critical').textContent  = al.critical ?? '0';
  document.getElementById('stat-warnings').textContent  = al.warning ?? '0';
  document.getElementById('stat-unresolved').textContent = al.unresolved ?? '0';

  renderEquipmentTable(eq.usage_ranking || []);
  renderZoneTable(occ.smart_machine_zonereakdown || {});
  renderAlertTable(al);
}

function renderEquipmentTable(ranking) {
  const wrap = document.getElementById('equipment-table');
  if (!ranking.length) { wrap.innerHTML = '<div class="empty">No equipment sessions in this period.</div>'; return; }
  let html = `<table><thead><tr><th>#</th><th>Machine</th><th>Sessions</th><th>Total Reps</th></tr></thead><tbody>`;
  ranking.forEach((r, i) => {
    html += `<tr>
      <td class="rank">${i + 1}</td>
      <td>${esc(r.machine_id)}</td>
      <td>${r.sessions}</td>
      <td>${r.total_reps}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  wrap.innerHTML = html;
}

function renderZoneTable(zones) {
  const wrap = document.getElementById('zone-table');
  const entries = Object.entries(zones);
  if (!entries.length) { wrap.innerHTML = '<div class="empty">No occupancy data in this period.</div>'; return; }
  let html = `<table><thead><tr><th>Zone</th><th>Peak</th><th>Average</th></tr></thead><tbody>`;
  entries.forEach(([zone, data]) => {
    html += `<tr>
      <td>${esc(zone)}</td>
      <td>${data.peak}</td>
      <td>${data.average}</td>
    </tr>`;
  });
  html += '</tbody></table>';
  wrap.innerHTML = html;
}

function renderAlertTable(al) {
  const wrap = document.getElementById('alert-table');
  const records = al.records || [];
  _alertRecords = records;

  if (!al.total) {
    wrap.innerHTML = '<div class="empty">No alerts in this period.</div>';
    return;
  }

  if (!records.length) {
    // Fall back to summary-only view
    wrap.innerHTML = `
      <table><thead><tr><th>Severity</th><th>Count</th></tr></thead><tbody>
        <tr><td class="sev-CRITICAL">CRITICAL</td><td>${al.critical || 0}</td></tr>
        <tr><td class="sev-WARNING">WARNING</td><td>${al.warning || 0}</td></tr>
        <tr><td class="sev-INFO">INFO</td><td>${al.info || 0}</td></tr>
        <tr><td>Resolved</td><td>${al.resolved || 0}</td></tr>
        <tr><td>Unresolved</td><td>${al.unresolved || 0}</td></tr>
        <tr><td><strong>Total</strong></td><td><strong>${al.total}</strong></td></tr>
      </tbody></table>
    `;
    return;
  }

  // Sort: CRITICAL first, then WARNING, then INFO; unresolved before resolved
  const SEV_ORDER = { CRITICAL: 0, WARNING: 1, INFO: 2 };
  const sorted = [...records].sort((a, b) => {
    const sevDiff = (SEV_ORDER[a.severity] ?? 3) - (SEV_ORDER[b.severity] ?? 3);
    if (sevDiff !== 0) return sevDiff;
    return (a.resolved ? 1 : 0) - (b.resolved ? 1 : 0);
  });

  let html = `<table><thead><tr>
    <th>Sev</th><th>Zone</th><th>Member</th><th>Description</th><th>Status</th>
  </tr></thead><tbody>`;

  sorted.forEach((r, i) => {
    const origIdx = records.indexOf(r);
    const desc = (r.description || '').slice(0, 45) + ((r.description || '').length > 45 ? '…' : '');
    const statusCls = r.resolved ? 'status-resolved' : 'status-active';
    const status = r.resolved ? 'Resolved' : 'Active';
    html += `<tr class="alert-row clickable" data-idx="${origIdx}" title="Click for details">
      <td class="sev-${esc(r.severity)}">${esc(r.severity)}</td>
      <td>${esc(r.zone_id || '—')}</td>
      <td>${esc(r.member_id || '—')}</td>
      <td>${esc(desc)}</td>
      <td class="${statusCls}">${status}</td>
    </tr>`;
  });

  html += '</tbody></table>';
  wrap.innerHTML = html;

  // Attach click listeners after render
  wrap.querySelectorAll('.alert-row.clickable').forEach(row => {
    row.addEventListener('click', () => showAlertModal(parseInt(row.dataset.idx, 10)));
  });
}

// ── Alert detail modal ────────────────────────────────────────────────────────

let _currentModalAlertId = null;
let _currentModalIdx = null;

function showAlertModal(idx) {
  const r = _alertRecords[idx];
  if (!r) return;

  _currentModalIdx = idx;
  _currentModalAlertId = r.alert_id || null;

  const modal = document.getElementById('alert-modal');
  const badge = document.getElementById('modal-severity-badge');
  badge.textContent = r.severity;
  badge.className = `modal-sev-badge sev-badge-${r.severity}`;
  document.getElementById('modal-zone').textContent    = r.zone_id || '—';
  document.getElementById('modal-member').textContent  = r.member_id || '—';
  document.getElementById('modal-ts').textContent      = r.created_at ? new Date(r.created_at).toLocaleString() : '—';
  document.getElementById('modal-status').textContent  = r.resolved ? 'Resolved' : 'Active';
  document.getElementById('modal-status').className    = r.resolved ? 'status-resolved' : 'status-active';
  document.getElementById('modal-desc').textContent    = r.description || '—';

  const resolveBtn = document.getElementById('modal-resolve-btn');
  // Only show resolve for unresolved, non-mock alerts
  if (!r.resolved && r.alert_id && !r.alert_id.startsWith('mock_')) {
    resolveBtn.classList.remove('hidden');
  } else {
    resolveBtn.classList.add('hidden');
  }

  modal.classList.remove('hidden');
}

async function resolveFromModal() {
  if (!_currentModalAlertId) return;
  try {
    await fetch(`/api/resolve/${_currentModalAlertId}`, { method: 'POST' });
    // Update the record in place
    if (_currentModalIdx !== null && _alertRecords[_currentModalIdx]) {
      _alertRecords[_currentModalIdx].resolved = true;
    }
    document.getElementById('modal-status').textContent = 'Resolved';
    document.getElementById('modal-status').className = 'status-resolved';
    document.getElementById('modal-resolve-btn').classList.add('hidden');
    // Re-render the table
    renderAlertTable({ records: _alertRecords, total: _alertRecords.length,
      critical: _alertRecords.filter(r => r.severity === 'CRITICAL').length,
      warning: _alertRecords.filter(r => r.severity === 'WARNING').length,
      info: _alertRecords.filter(r => r.severity === 'INFO').length,
      resolved: _alertRecords.filter(r => r.resolved).length,
      unresolved: _alertRecords.filter(r => !r.resolved).length,
    });
  } catch (e) { alert('Resolve failed: ' + e.message); }
}
window.resolveFromModal = resolveFromModal;

function closeAlertModal(e) {
  if (e && e.target !== document.getElementById('alert-modal')) return;
  document.getElementById('alert-modal').classList.add('hidden');
}
window.closeAlertModal = closeAlertModal;

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') document.getElementById('alert-modal').classList.add('hidden');
});

// ── Live member count ─────────────────────────────────────────────────────────
async function loadLiveMemberCount() {
  try {
    const data = await fetch('/api/members/status').then(r => r.json());
    const count = (data.members || []).filter(m => m.in_gym).length;
    document.getElementById('live-member-count').textContent = count;
  } catch { /* ignore */ }
}

document.getElementById('btn-generate').addEventListener('click', generateReport);

// Auto-generate on load
generateReport();
loadLiveMemberCount();
setInterval(loadLiveMemberCount, 5000);
