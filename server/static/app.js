/* Model Router Dashboard -- vanilla JS, no build step */

const API = '';  // same origin

// ── Navigation ──────────────────────────────────────────────────────────────
const pages = document.querySelectorAll('.page');
const navItems = document.querySelectorAll('.nav-item');

function showPage(id) {
  pages.forEach(p => p.classList.toggle('active', p.id === id));
  navItems.forEach(n => n.classList.toggle('active', n.dataset.page === id));
  if (id === 'page-models') loadModels();
  if (id === 'page-history') loadHistory();
  if (id === 'page-settings') loadSettings();
}

navItems.forEach(n => n.addEventListener('click', () => showPage(n.dataset.page)));

// ── Toast ────────────────────────────────────────────────────────────────────
const toast = document.getElementById('toast');
let toastTimer;
function showToast(msg, type = 'ok') {
  toast.textContent = msg;
  toast.className = `show ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.className = '', 3000);
}

// ── Live stats via SSE ───────────────────────────────────────────────────────
function startSSE() {
  const es = new EventSource(`${API}/api/stats/live`);
  es.onmessage = e => {
    try { updateLiveStats(JSON.parse(e.data)); } catch (_) {}
  };
  es.onerror = () => {
    // Fallback poll every 5s if SSE fails
    setTimeout(() => fetchOnce(), 5000);
  };
}

async function fetchOnce() {
  try {
    const r = await fetch(`${API}/api/stats/live`);
    if (r.ok) updateLiveStats(await r.json());
  } catch (_) {}
}

function updateLiveStats(data) {
  setText('stat-today-cost',    `$${(data.today_cost_usd || 0).toFixed(4)}`);
  setText('stat-today-tokens',  fmtNum(data.today_tokens  || 0));
  setText('stat-today-calls',   fmtNum(data.today_calls   || 0));
  setText('stat-session-cost',  `$${(data.session_cost_usd || 0).toFixed(4)}`);
  setText('stat-session-tokens', fmtNum(data.session_tokens || 0));
  updateModelChart(data.calls_per_model || {});
}

// ── Model bar chart ──────────────────────────────────────────────────────────
const MODEL_COLORS = {
  'claude-opus-4-6':    'opus',
  'claude-opus-4-5':    'opus',
  'claude-sonnet-4-6':  'sonnet',
  'claude-sonnet-4-5':  'sonnet',
  'claude-haiku-4-5':   'haiku',
};
const MODEL_SHORT = {
  'claude-opus-4-6':   'Opus 4.6',
  'claude-opus-4-5':   'Opus 4.5',
  'claude-sonnet-4-6': 'Sonnet 4.6',
  'claude-sonnet-4-5': 'Sonnet 4.5',
  'claude-haiku-4-5':  'Haiku 4.5',
};

function updateModelChart(perModel) {
  const container = document.getElementById('model-bars');
  if (!container) return;
  const entries = Object.entries(perModel);
  if (!entries.length) { container.innerHTML = '<p style="color:var(--muted);font-size:12px;">No calls yet today.</p>'; return; }

  const maxCalls = Math.max(...entries.map(([,v]) => v.calls));
  container.innerHTML = entries.map(([model, v]) => {
    const pct = maxCalls ? Math.max((v.calls / maxCalls) * 100, 3) : 3;
    const cls = MODEL_COLORS[model] || 'other';
    const label = MODEL_SHORT[model] || model;
    return `
      <div class="bar-row">
        <div class="bar-label" title="${model}">${label}</div>
        <div class="bar-track">
          <div class="bar-fill ${cls}" style="width:${pct}%">
            <span class="bar-val">${v.calls} calls &nbsp;$${(v.cost||0).toFixed(4)}</span>
          </div>
        </div>
      </div>`;
  }).join('');
}

// ── History ──────────────────────────────────────────────────────────────────
let historyOffset = 0;
const HISTORY_PAGE = 50;

async function loadHistory(reset = true) {
  if (reset) historyOffset = 0;
  const r = await fetch(`${API}/api/history?limit=${HISTORY_PAGE}&offset=${historyOffset}`);
  const rows = await r.json();
  renderHistory(rows, reset);
}

function renderHistory(rows, reset) {
  const tbody = document.getElementById('history-tbody');
  if (!tbody) return;
  if (reset) tbody.innerHTML = '';
  if (!rows.length && reset) {
    tbody.innerHTML = '<tr><td colspan="8"><div class="empty-state"><div class="empty-icon">📭</div>No tasks recorded yet.</div></td></tr>';
    return;
  }
  rows.forEach(r => {
    const tr = document.createElement('tr');
    const ts = new Date(r.timestamp * 1000).toLocaleTimeString();
    const modelShort = MODEL_SHORT[r.model] || r.model;
    const successBadge = r.success ? '<span class="badge badge-green">OK</span>' : '<span class="badge badge-red">ERR</span>';
    const decomposedBadge = r.decomposed ? '<span class="badge badge-purple">split</span>' : '';
    tr.innerHTML = `
      <td class="mono">${ts}</td>
      <td>${modelBadge(r.model)}</td>
      <td><span class="badge ${taskBadgeClass(r.task_type)}">${r.task_type}</span></td>
      <td class="mono">${fmtNum(r.input_tokens + r.output_tokens)}</td>
      <td class="mono">$${(r.cost_usd||0).toFixed(5)}</td>
      <td class="mono">${r.latency_ms}ms</td>
      <td>${successBadge} ${decomposedBadge}</td>
      <td class="mono" style="color:var(--muted);font-size:10px">${(r.complexity_score||0).toFixed(2)}</td>`;
    tbody.appendChild(tr);
  });
  historyOffset += rows.length;
}

function modelBadge(model) {
  const cls = MODEL_COLORS[model] === 'opus' ? 'badge-blue' :
              MODEL_COLORS[model] === 'sonnet' ? 'badge-green' :
              MODEL_COLORS[model] === 'haiku' ? 'badge-yellow' : 'badge-gray';
  return `<span class="badge ${cls}">${MODEL_SHORT[model] || model}</span>`;
}
function taskBadgeClass(t) {
  return {coding:'badge-blue',review:'badge-purple',docs:'badge-green',reasoning:'badge-blue',chat:'badge-gray'}[t] || 'badge-gray';
}

// ── Models page ───────────────────────────────────────────────────────────────
async function loadModels() {
  const r = await fetch(`${API}/api/models`);
  const models = await r.json();
  const container = document.getElementById('model-cards-container');
  if (!container) return;
  container.innerHTML = models.map(m => `
    <div class="model-card">
      <div class="model-card-header">
        <div>
          <div class="model-name">${m.display_name}</div>
          <div class="model-provider">${m.provider}</div>
        </div>
        <div class="model-rank">#${m.capability_rank}</div>
      </div>
      <div class="model-meta">
        <div class="model-meta-item"><div class="model-meta-label">Input</div><div class="model-meta-value">$${m.cost_input_per_1k}/1K</div></div>
        <div class="model-meta-item"><div class="model-meta-label">Output</div><div class="model-meta-value">$${m.cost_output_per_1k}/1K</div></div>
        <div class="model-meta-item"><div class="model-meta-label">Context</div><div class="model-meta-value">${fmtNum(m.context_tokens)}</div></div>
        <div class="model-meta-item"><div class="model-meta-label">Max out</div><div class="model-meta-value">${fmtNum(m.max_output_tokens)}</div></div>
      </div>
      <div class="strength-tags">${(m.strengths||[]).map(s=>`<span class="strength-tag">${s}</span>`).join('')}</div>
    </div>`).join('');
}

// ── Router Preview ────────────────────────────────────────────────────────────
document.getElementById('preview-btn')?.addEventListener('click', async () => {
  const prompt   = document.getElementById('preview-prompt')?.value?.trim();
  const quality  = parseFloat(document.getElementById('preview-quality')?.value || '0.5');
  const budget   = parseFloat(document.getElementById('preview-budget')?.value || '0') || null;
  const taskType = document.getElementById('preview-task-type')?.value || null;
  if (!prompt) { showToast('Enter a prompt first', 'err'); return; }

  const btn = document.getElementById('preview-btn');
  btn.innerHTML = '<span class="spinner"></span>Analysing...';
  btn.disabled = true;

  try {
    const r = await fetch(`${API}/api/route`, {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ prompt, quality_requirement: quality, cost_budget_usd: budget, task_type: taskType || undefined }),
    });
    const d = await r.json();
    renderPreviewResult(d);
  } catch (e) {
    showToast('Request failed: ' + e.message, 'err');
  } finally {
    btn.innerHTML = 'Analyse Task';
    btn.disabled = false;
  }
});

function renderPreviewResult(d) {
  const box = document.getElementById('preview-result');
  if (!box) return;
  const scoreClass = d.complexity_score >= 0.72 ? 'score-high' : d.complexity_score >= 0.38 ? 'score-mid' : 'score-low';
  box.innerHTML = [
    `<span class="key">model</span>         <span class="val">${d.selected_model}</span>`,
    `<span class="key">sdk_string</span>    <span class="val">${d.selected_model_string}</span>`,
    `<span class="key">complexity</span>    <span class="${scoreClass}">${d.complexity_score}</span>`,
    `<span class="key">task_type</span>     <span class="val">${d.task_type}</span>`,
    `<span class="key">est_tokens</span>    <span class="val">${fmtNum(d.estimated_tokens)}</span>`,
    `<span class="key">decomposed</span>    <span class="val">${d.decomposed} ${d.decomposed ? '('+d.subtask_count+' subtasks)' : ''}</span>`,
    ``,
    `<span class="key">reasoning:</span>`,
    `  ${d.reasoning}`,
  ].join('\n');
}

// Update quality label
document.getElementById('preview-quality')?.addEventListener('input', e => {
  document.getElementById('quality-val').textContent = parseFloat(e.target.value).toFixed(1);
});

// ── Settings ─────────────────────────────────────────────────────────────────
async function loadSettings() {
  const r = await fetch(`${API}/api/health`);
  const h = await r.json();
  setText('settings-session', h.session_id?.slice(0,16) + '...');
  setText('settings-uptime', `${Math.floor(h.uptime_s / 60)}m ${Math.floor(h.uptime_s % 60)}s`);
  setText('settings-version', h.version);
}

document.getElementById('reload-models-btn')?.addEventListener('click', async () => {
  const r = await fetch(`${API}/api/models/reload`, { method: 'POST' });
  const d = await r.json();
  showToast(d.message, d.status === 'ok' ? 'ok' : 'err');
  if (d.status === 'ok') loadModels();
});

// ── History load more ────────────────────────────────────────────────────────
document.getElementById('history-more-btn')?.addEventListener('click', () => loadHistory(false));

// ── Utilities ────────────────────────────────────────────────────────────────
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
function fmtNum(n) {
  if (n >= 1_000_000) return (n/1_000_000).toFixed(1) + 'M';
  if (n >= 1_000)     return (n/1_000).toFixed(1) + 'K';
  return String(n);
}

// ── Init ─────────────────────────────────────────────────────────────────────
showPage('page-dashboard');
startSSE();
