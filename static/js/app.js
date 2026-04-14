
// ==================== API HELPERS ====================
const api = {
  async get(url) {
    const r = await fetch(url); if (!r.ok) throw await r.json(); return r.json();
  },
  async post(url, data) {
    const r = await fetch(url, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(data) });
    if (!r.ok) throw await r.json(); return r.json();
  },
  async delete(url) {
    const r = await fetch(url, { method: 'DELETE' });
    if (!r.ok) throw await r.json(); return r.json();
  }
};

// ==================== STATE ====================
let KB = { characteristics: {}, diagnoses: [], repairs: [], parts: [] };
let lastDiagResult = null; // хранит результат для Ollama

// ==================== INIT ====================
document.addEventListener('DOMContentLoaded', async () => {
  await loadKB();
  checkOllamaStatus();
  renderKBPage();
  populateDiagSelect();
});

async function loadKB() {
  try {
    KB = await api.get('/api/kb');
  } catch(e) { showToast('Ошибка загрузки БД: ' + (e.error || e), 'error'); }
}

// ==================== NAVIGATION ====================
function showPage(id, btn) {
  document.querySelectorAll('main > section').forEach(s => s.hidden = true);
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + id).hidden = false;
  btn.classList.add('active');
  if (id === 'kb') renderKBPage();
  if (id === 'solver') populateDiagSelect();
  if (id === 'editor') renderEditor();
}

// ==================== OLLAMA STATUS ====================
async function checkOllamaStatus() {
  const dot = document.getElementById('ollama-dot');
  const label = document.getElementById('ollama-label');
  try {
    const r = await fetch('/api/ollama/status');
    const d = await r.json();
    if (d.online) {
      dot.className = 'dot'; label.textContent = 'Ollama: ' + (d.model || 'подключена');
    } else {
      dot.className = 'dot offline'; label.textContent = 'Ollama: недоступна';
    }
  } catch { dot.className = 'dot offline'; label.textContent = 'Ollama: недоступна'; }
}

// ==================== SOLVER PAGE ====================
function populateDiagSelect() {
  const sel = document.getElementById('sel-diagnosis');
  if (!sel) return;
  const prev = sel.value;
  sel.innerHTML = '<option value="">-- Выберите диагноз --</option>';
  (KB.diagnoses || []).forEach(d => {
    sel.innerHTML += `<option value="${d.id}" ${d.id==prev?'selected':''}>${d.name}</option>`;
  });
}

function onDiagnosisChange() {
  const diagId = parseInt(document.getElementById('sel-diagnosis').value);
  const cardChars = document.getElementById('card-chars');
  const resArea = document.getElementById('result-area');
  resArea.innerHTML = ''; lastDiagResult = null;

  if (!diagId) { cardChars.hidden = true; return; }

  const diag = KB.diagnoses.find(d => d.id === diagId);
  if (!diag) return;

  if (diag.name === 'Исправен') {
    resArea.innerHTML = `<div class="alert alert-success"><h3>✅ Устройство исправно</h3>Ремонт не требуется. Все характеристики в норме.</div>`;
    cardChars.hidden = true; return;
  }

  cardChars.hidden = false;
  const fields = document.getElementById('char-fields');
  fields.innerHTML = '';

  (diag.characteristics || []).forEach(dc => {
    const meta = KB.characteristics[dc.char_name] || {};
    let rangeStr = formatRange(dc);
    fields.innerHTML += `
      <div>
        <label>${dc.char_name} <span style="color:#999;font-weight:400">${meta.unit||''}</span></label>
        <p class="hint">Допустимо: [${meta.min_val ?? '?'}; ${meta.max_val ?? '?'}] | Для диагноза: ${rangeStr}</p>
        <input type="number" id="f-${dc.char_name}" step="any"
          min="${meta.min_val ?? ''}" max="${meta.max_val ?? ''}"
          placeholder="${meta.min_val ?? ''} ... ${meta.max_val ?? ''}">
      </div>`;
  });
}

function formatRange(dc) {
  if (dc.exact_val !== null && dc.exact_val !== undefined) return `= ${dc.exact_val}`;
  const lo = dc.exclusive_min ? '(' : '[';
  const hi = dc.exclusive_max ? ')' : ']';
  return `${lo}${dc.range_min}; ${dc.range_max}${hi}`;
}

function inRange(val, dc) {
  if (dc.exact_val !== null && dc.exact_val !== undefined) return Math.abs(val - dc.exact_val) < 0.0001;
  const okMin = dc.exclusive_min ? val > dc.range_min : val >= dc.range_min;
  const okMax = dc.exclusive_max ? val < dc.range_max : val <= dc.range_max;
  return okMin && okMax;
}

async function solve() {
  const diagId = parseInt(document.getElementById('sel-diagnosis').value);
  if (!diagId) return;
  const diag = KB.diagnoses.find(d => d.id === diagId);
  if (!diag) return;

  const inputVals = {};
  let errors = [];

  (diag.characteristics || []).forEach(dc => {
    const el = document.getElementById('f-' + dc.char_name);
    if (!el) return;
    const v = parseFloat(el.value);
    const meta = KB.characteristics[dc.char_name] || {};
    if (el.value === '' || isNaN(v)) { errors.push(`"${dc.char_name}": обязательное поле`); return; }
    if (meta.min_val !== undefined && v < meta.min_val) errors.push(`"${dc.char_name}": ${v} < мин. допустимого ${meta.min_val}`);
    if (meta.max_val !== undefined && v > meta.max_val) errors.push(`"${dc.char_name}": ${v} > макс. допустимого ${meta.max_val}`);
    inputVals[dc.char_name] = v;
  });

  const resArea = document.getElementById('result-area');
  if (errors.length) {
    resArea.innerHTML = `<div class="alert alert-error"><h3>⚠️ Ошибки ввода</h3><ul style="padding-left:18px;margin-top:6px">${errors.map(e=>`<li>${e}</li>`).join('')}</ul></div>`;
    return;
  }

  // Отправить на сервер для диагностики
  try {
    const result = await api.post('/api/solve', { diagnosis_id: diagId, values: inputVals });
    lastDiagResult = result;
    renderResult(result, diag, inputVals);
  } catch(e) {
    resArea.innerHTML = `<div class="alert alert-error">Ошибка: ${e.error || JSON.stringify(e)}</div>`;
  }
}

function renderResult(result, diag, inputVals) {
  const resArea = document.getElementById('result-area');
  const repair = result.repair;
  const steps = result.steps || [];
  const checks = result.checks || [];
  const mismatches = checks.filter(c => !c.ok);

  let warnHtml = '';
  if (mismatches.length) {
    warnHtml = `<div class="alert alert-warning">
      <b>⚠️ ${mismatches.length} из ${checks.length} характеристик не соответствуют диагнозу «${diag.name}»:</b>
      <div class="tag-list" style="margin-top:6px">${mismatches.map(c=>`<span class="badge badge-orange">${c.name}</span>`).join('')}</div>
      <small style="color:#777;display:block;margin-top:6px">Ремонт выбран по указанному диагнозу. Рекомендуется уточнить диагноз.</small>
    </div>`;
  }

  const stepsHtml = steps.length
    ? `<ol class="steps-list">${steps.map(s=>`<li>${s}</li>`).join('')}</ol>`
    : `<p style="color:#777">Ремонт не требуется.</p>`;

  // Таблица объяснения
  const explRows = checks.map(c => {
    const cls = c.ok ? 'ok-row' : 'fail-row';
    return `<tr class="${cls}"><td>${c.ok?'✅':'❌'}</td><td>${c.name}</td>
      <td><b>${c.value}</b> ${c.unit||''}</td><td>${c.expected}</td></tr>`;
  }).join('');

  resArea.innerHTML = `
    <div class="card">
      ${warnHtml}
      <div class="alert alert-success" style="margin-bottom:16px">
        <div class="result-diagnosis">🔧 Диагноз: ${diag.name}</div>
        <div style="margin-bottom:14px">Ремонт: <span class="badge badge-green">${repair}</span></div>
        <b>Последовательность действий:</b>
        ${stepsHtml}
      </div>
      <details style="margin-top:8px">
        <summary style="cursor:pointer;font-size:.9rem;font-weight:600;color:#555">📋 Объяснение вывода</summary>
        <table style="margin-top:10px">
          <thead><tr><th></th><th>Характеристика</th><th>Введено</th><th>Норма для диагноза</th></tr></thead>
          <tbody>${explRows}</tbody>
        </table>
      </details>
      <div class="ai-panel" id="ai-panel">
        <h3>🤖 Проверка ИИ (Ollama)</h3>
        <p style="font-size:.85rem;color:#666;margin-bottom:10px">
          Локальная ИИ-модель проанализирует результат диагностики и даст дополнительные рекомендации.
        </p>
        <button class="btn btn-ai" onclick="runOllamaCheck()">▶ Запустить проверку ИИ</button>
        <div id="ai-result"></div>
      </div>
    </div>`;
}

async function runOllamaCheck() {
  if (!lastDiagResult) return;
  const btn = document.querySelector('.btn-ai');
  const aiDiv = document.getElementById('ai-result');
  btn.disabled = true;
  aiDiv.innerHTML = `<div class="ai-thinking" style="margin-top:12px"><span class="spinner"></span> ИИ анализирует результат...</div>`;

  try {
    const result = await api.post('/api/ollama/check', lastDiagResult);
    aiDiv.innerHTML = `<div class="ai-response">${escHtml(result.response)}</div>`;
  } catch(e) {
    aiDiv.innerHTML = `<div class="alert alert-error" style="margin-top:10px">
      Ошибка Ollama: ${e.error || 'Сервис недоступен. Убедитесь, что Ollama запущена (ollama serve).'}</div>`;
  } finally { btn.disabled = false; }
}

// ==================== EDITOR PAGE ====================
function renderEditor() {
  renderPartsEditor();
  renderCharsEditor();
  renderDiagEditor();
  renderRepairsEditor();
}

function renderPartsEditor() {
  const tb = document.getElementById('parts-tbody');
  if (!tb) return;
  tb.innerHTML = (KB.parts || []).map(p => `
    <tr><td><b>${p.name}</b></td>
    <td><div class="tag-list">${(p.characteristics||[]).map(c=>`<span class="tag">${c}</span>`).join('')}</div></td>
    <td><button class="btn btn-danger" onclick="deletePart(${p.id})">✕</button></td></tr>`).join('');
}

function renderCharsEditor() {
  const tb = document.getElementById('chars-tbody');
  if (!tb) return;
  tb.innerHTML = Object.values(KB.characteristics || {}).map(c => `
    <tr><td>${c.name} <span class="badge badge-blue">${c.unit||''}</span></td>
    <td>[${c.min_val}; ${c.max_val}]</td><td>[${c.normal_min}; ${c.normal_max}]</td>
    <td><button class="btn btn-danger" onclick="deleteChar(${c.id})">✕</button></td></tr>`).join('');
}

function renderDiagEditor() {
  const tb = document.getElementById('diag-tbody');
  if (!tb) return;
  tb.innerHTML = (KB.diagnoses || []).map(d => `
    <tr><td><b>${d.name}</b></td>
    <td><span class="badge badge-orange">${(d.characteristics||[]).length} хар-к</span></td>
    <td><span class="badge badge-green">${d.repair_name||'—'}</span></td>
    <td><button class="btn btn-danger" onclick="deleteDiag(${d.id})">✕</button></td></tr>`).join('');
}

function renderRepairsEditor() {
  const tb = document.getElementById('repairs-tbody');
  if (!tb) return;
  tb.innerHTML = (KB.repairs || []).map(r => `
    <tr><td>${r.name}</td>
    <td style="font-size:.82rem;color:#555">${(r.steps||[]).slice(0,2).join('; ')}${(r.steps||[]).length>2?'...':''}</td>
    <td><button class="btn btn-danger" onclick="deleteRepair(${r.id})">✕</button></td></tr>`).join('');
}

// Editor actions
async function addPart() {
  const n = document.getElementById('new-part').value.trim(); if (!n) return;
  await api.post('/api/parts', {name: n});
  await loadKB(); renderPartsEditor();
  document.getElementById('new-part').value = '';
  showToast('Деталь добавлена');
}
async function deletePart(id) {
  if (!confirm('Удалить деталь?')) return;
  await api.delete('/api/parts/' + id); await loadKB(); renderPartsEditor();
}

async function addChar() {
  const data = {
    name: document.getElementById('nc-name').value.trim(),
    unit: document.getElementById('nc-unit').value.trim(),
    min_val: parseFloat(document.getElementById('nc-min').value),
    max_val: parseFloat(document.getElementById('nc-max').value),
    normal_min: parseFloat(document.getElementById('nc-nmin').value),
    normal_max: parseFloat(document.getElementById('nc-nmax').value),
  };
  if (!data.name) return;
  await api.post('/api/characteristics', data); await loadKB(); renderCharsEditor();
  showToast('Характеристика добавлена');
}
async function deleteChar(id) {
  if (!confirm('Удалить характеристику?')) return;
  await api.delete('/api/characteristics/' + id); await loadKB(); renderCharsEditor();
}

async function addRepair() {
  const name = document.getElementById('new-repair-name').value.trim();
  const stepsRaw = document.getElementById('new-repair-steps').value.trim();
  if (!name) return;
  const steps = stepsRaw.split('\n').map(s=>s.trim()).filter(Boolean);
  await api.post('/api/repairs', {name, steps}); await loadKB(); renderRepairsEditor();
  document.getElementById('new-repair-name').value = '';
  document.getElementById('new-repair-steps').value = '';
  showToast('Ремонт добавлен');
}
async function deleteRepair(id) {
  if (!confirm('Удалить ремонт?')) return;
  await api.delete('/api/repairs/' + id); await loadKB(); renderRepairsEditor();
}

async function addDiag() {
  const name = document.getElementById('new-diag-name').value.trim();
  const repairId = parseInt(document.getElementById('new-diag-repair').value);
  if (!name) return;
  await api.post('/api/diagnoses', {name, repair_id: repairId||null});
  await loadKB(); renderDiagEditor(); populateDiagSelect();
  document.getElementById('new-diag-name').value = '';
  showToast('Диагноз добавлен');
}
async function deleteDiag(id) {
  if (!confirm('Удалить диагноз?')) return;
  await api.delete('/api/diagnoses/' + id); await loadKB(); renderDiagEditor(); populateDiagSelect();
}

// ==================== KB PAGE ====================
function renderKBPage() {
  // Parts
  const tb1 = document.getElementById('kb-parts-tbody');
  if (tb1) tb1.innerHTML = (KB.parts||[]).map(p =>
    `<tr><td><b>${p.name}</b></td><td><div class="tag-list">${(p.characteristics||[]).map(c=>`<span class="tag">${c}</span>`).join('')}</div></td></tr>`).join('');

  // Diag ranges
  const tb2 = document.getElementById('kb-diag-tbody');
  if (tb2) {
    let rows = '';
    (KB.diagnoses||[]).forEach(d => {
      const chars = d.characteristics || [];
      if (!chars.length) {
        rows += `<tr><td><b>${d.name}</b></td><td colspan="3" style="color:#999">—</td></tr>`;
      } else {
        chars.forEach((c, i) => {
          const meta = KB.characteristics[c.char_name]||{};
          rows += `<tr>${i===0?`<td rowspan="${chars.length}"><b>${d.name}</b></td>`:''}
            <td>${c.char_name}</td><td>${formatRange(c)}</td><td>${meta.unit||''}</td></tr>`;
        });
      }
    });
    tb2.innerHTML = rows;
  }

  // Repairs
  const tb3 = document.getElementById('kb-repairs-tbody');
  if (tb3) tb3.innerHTML = (KB.diagnoses||[]).map(d => {
    const r = KB.repairs.find(r => r.name === d.repair_name) || {};
    const steps = r.steps || [];
    return `<tr><td><b>${d.name}</b></td><td><span class="badge badge-green">${d.repair_name||'—'}</span></td>
      <td><ol class="steps-list" style="font-size:.82rem">${steps.map(s=>`<li>${s}</li>`).join('')}</ol></td></tr>`;
  }).join('');
}

// ==================== UTILS ====================
function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function showToast(msg, type='success') {
  const t = document.createElement('div');
  t.className = `alert alert-${type}`;
  t.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:9999;min-width:220px;box-shadow:0 4px 16px rgba(0,0,0,.15)';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}
