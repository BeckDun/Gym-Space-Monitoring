'use strict';

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

async function generateReport() {
  const schedule = document.getElementById('schedule-select').value;
  const btn = document.getElementById('btn-generate');
  btn.disabled = true;
  btn.textContent = 'Generating…';

  try {
    const report = await fetch(`/api/report/${schedule}`).then(r => r.json());
    if (report.error) { alert('Report error: ' + report.error); return; }
    renderReport(report);
    document.getElementById('report-ts').textContent =
      `Generated: ${new Date(report.generated_at).toLocaleString()} | Period: last ${schedule}`;
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
  renderZoneTable(occ.zone_breakdown || {});
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
  if (!al.total) { wrap.innerHTML = '<div class="empty">No alerts in this period.</div>'; return; }
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
}

document.getElementById('btn-generate').addEventListener('click', generateReport);

// Auto-generate on load
generateReport();
