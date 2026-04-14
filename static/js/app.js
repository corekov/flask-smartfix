// ==================== API ====================
const api = {
  async get(url) {
    const r = await fetch(url);
    if (!r.ok) throw await r.json();
    return r.json();
  },
  async post(url, data) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!r.ok) throw await r.json();
    return r.json();
  },
  async patch(url, data) {
    const r = await fetch(url, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data)
    });
    if (!r.ok) throw await r.json();
    return r.json();
  },
  async delete(url) {
    const r = await fetch(url, { method: 'DELETE' });
    if (!r.ok) throw await r.json();
    return r.json();
  }
};

// ==================== STATE ====================
let KB = { characteristics: {}, diagnoses: [], repairs: [], parts: [] };
let lastDiagResult = null;
let selectedOllamaModel = null;

// ==================== INIT ====================
document.addEventListener('DOMContentLoaded', async () => {
  await loadKB();
  await checkOllamaStatus(); // FIX #1: загружаем список моделей
  renderKBPage();
  populateDiagSelect();
});

async function loadKB() {
  try {
    KB = await api.get('/api/kb');
  } catch (e) {
    showToast('Ошибка загрузки БД: ' + (e.error || e), 'error');
  }
}

// ==================== NAVIGATION ====================
function showPage(id, btn) {
  document.querySelectorAll('main > section').forEach(s => (s.hidden = true));
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + id).hidden = false;
  btn.classList.add('active');
  if (id === 'kb') renderKBPage();
  if (id === 'solver') populateDiagSelect();
  if (id === 'editor') renderEditor();
}

// ==================== OLLAMA ====================
// FIX #1: получаем список моделей, рендерим <select>
async function checkOllamaStatus() {
  const dot   = document.getElementById('ollama-dot');
  const label = document.getElementById('ollama-label');
  try {
    const d = await api.get('/api/ollama/status');
    if (d.online && d.models && d.models.length > 0) {
      dot.className = 'dot';
      selectedOllamaModel = d.models[0];
      label.textContent   = 'Ollama: онлайн';
      renderModelSelectNav(d.models);
    } else {
      dot.className     = 'dot offline';
      label.textContent = d.online
        ? 'Ollama: нет моделей — выполните: ollama pull llama3'
        : 'Ollama: недоступна';
    }
  } catch {
    dot.className     = 'dot offline';
    label.textContent = 'Ollama: недоступна';
  }
}

function renderModelSelectNav(models) {
  const wrap = document.getElementById('model-select-wrap');
  if (!wrap) return;
  wrap.innerHTML = `<select
    style="padding:3px 8px;border-radius:6px;border:1px solid #c4b5fd;
           font-size:.8rem;background:#fff;color:#5b21b6"
    onchange="selectedOllamaModel=this.value">
    ${models.map(m => `<option value="${m}">${m}</option>`).join('')}
  </select>`;
}

// ==================== SOLVER ====================
function populateDiagSelect() {
  const sel = document.getElementById('sel-diagnosis');
  if (!sel) return;
  const prev = sel.value;
  sel.innerHTML = '<option value="">-- Выберите диагноз --</option>';
  (KB.diagnoses || []).forEach(d => {
    sel.innerHTML += `<option value="${d.id}" ${d.id == prev ? 'selected' : ''}>${d.name}</option>`;
  });
}

function onDiagnosisChange() {
  const diagId    = parseInt(document.getElementById('sel-diagnosis').value);
  const cardChars = document.getElementById('card-chars');
  const resArea   = document.getElementById('result-area');
  resArea.innerHTML = '';
  lastDiagResult    = null;

  if (!diagId) { cardChars.hidden = true; return; }
  const diag = KB.diagnoses.find(d => d.id === diagId);
  if (!diag) return;

  if (diag.name === 'Исправен') {
    resArea.innerHTML = `<div class="alert alert-success">
      <h3>✅ Устройство исправно</h3>Ремонт не требуется. Все характеристики в норме.</div>`;
    cardChars.hidden = true;
    return;
  }

  cardChars.hidden = false;
  const fields = document.getElementById('char-fields');
  fields.innerHTML = '';

  (diag.characteristics || []).forEach(dc => {
    const meta     = KB.characteristics[dc.char_name] || {};
    const rangeStr = formatRange(dc);
    fields.innerHTML += `<div>
      <label>${dc.char_name}
        <span style="color:#999;font-weight:400">${meta.unit || ''}</span>
      </label>
      <p class="hint">
        Допустимо: [${meta.min_val ?? '?'}; ${meta.max_val ?? '?'}]
        &nbsp;|&nbsp; Норма диагноза: ${rangeStr}
      </p>
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

async function solve() {
  const diagId = parseInt(document.getElementById('sel-diagnosis').value);
  if (!diagId) return;
  const diag = KB.diagnoses.find(d => d.id === diagId);
  if (!diag) return;

  const inputVals = {};
  const errors    = [];

  (diag.characteristics || []).forEach(dc => {
    const el   = document.getElementById('f-' + dc.char_name);
    if (!el) return;
    const v    = parseFloat(el.value);
    const meta = KB.characteristics[dc.char_name] || {};
    if (el.value === '' || isNaN(v)) {
      errors.push(`"${dc.char_name}": обязательное поле`);
      return;
    }
    if (meta.min_val !== undefined && v < meta.min_val)
      errors.push(`"${dc.char_name}": ${v} < мин. допустимого (${meta.min_val})`);
    if (meta.max_val !== undefined && v > meta.max_val)
      errors.push(`"${dc.char_name}": ${v} > макс. допустимого (${meta.max_val})`);
    inputVals[dc.char_name] = v;
  });

  const resArea = document.getElementById('result-area');
  if (errors.length) {
    resArea.innerHTML = `<div class="alert alert-error">
      <h3>⚠️ Ошибки ввода</h3>
      <ul style="padding-left:18px;margin-top:6px">
        ${errors.map(e => `<li>${e}</li>`).join('')}
      </ul></div>`;
    return;
  }

  try {
    const result = await api.post('/api/solve', { diagnosis_id: diagId, values: inputVals });
    lastDiagResult = result;
    renderResult(result, diag);
  } catch (e) {
    resArea.innerHTML = `<div class="alert alert-error">Ошибка: ${e.error || JSON.stringify(e)}</div>`;
  }
}

function renderResult(result, diag) {
  const resArea    = document.getElementById('result-area');
  const checks     = result.checks || [];
  const mismatches = checks.filter(c => !c.ok);

  const stepsHtml = (result.steps || []).length
    ? `<ol class="steps-list">${result.steps.map(s => `<li>${s}</li>`).join('')}</ol>`
    : `<p style="color:#777">Ремонт не требуется.</p>`;

  const explRows = checks.map(c => `
    <tr class="${c.ok ? 'ok-row' : 'fail-row'}">
      <td>${c.ok ? '✅' : '❌'}</td>
      <td>${c.name}</td>
      <td><b>${c.value}</b> ${c.unit || ''}</td>
      <td>${c.expected}</td>
    </tr>`).join('');

  // FIX #5: показать сообщение об автоматическом переключении диагноза
  const overrideHtml = result.override_msg
    ? `<div class="alert alert-warning"><b>🔄 ${result.override_msg}</b></div>` : '';

  const warnHtml = mismatches.length && !result.override_msg
    ? `<div class="alert alert-warning">
        <b>⚠️ ${mismatches.length} из ${checks.length} хар-к не соответствуют диагнозу:</b>
        <div class="tag-list" style="margin-top:6px">
          ${mismatches.map(c => `<span class="badge badge-orange">${c.name}</span>`).join('')}
        </div>
        <small style="color:#777;display:block;margin-top:4px">
          Ремонт выбран по указанному диагнозу. Рекомендуется уточнить диагноз.
        </small>
      </div>` : '';

  // FIX #1: select модели прямо в панели ИИ
  const modelOpts = selectedOllamaModel
    ? `<select id="model-select-result"
         style="padding:4px 10px;border-radius:6px;border:1px solid #c4b5fd;
                font-size:.85rem;background:#fff;color:#5b21b6"
         onchange="selectedOllamaModel=this.value">
         <option>${selectedOllamaModel}</option>
       </select>` : '';

  const ollamaSection = selectedOllamaModel
    ? `<div class="ai-panel" id="ai-panel">
        <h3>🤖 Проверка ИИ (Ollama)</h3>
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap">
          <span style="font-size:.85rem;color:#6d28d9">Модель:</span>
          <div id="model-select-wrap-result">${modelOpts}</div>
          <button class="btn btn-ai" id="btn-ai-run" onclick="runOllamaCheck()">
            ▶ Запустить проверку
          </button>
        </div>
        <div id="ai-result"></div>
      </div>`
    : `<div class="alert alert-info" style="margin-top:12px">
        🤖 Ollama недоступна.
        Запустите <code>ollama serve</code> и <code>ollama pull llama3</code>.
      </div>`;

  resArea.innerHTML = `<div class="card">
    ${overrideHtml}${warnHtml}
    <div class="alert alert-success" style="margin-bottom:16px">
      <div class="result-diagnosis">🔧 Диагноз: ${result.diagnosis}</div>
      <div style="margin-bottom:14px">
        Ремонт: <span class="badge badge-green">${result.repair}</span>
        <span class="badge badge-blue" style="margin-left:8px">${result.match_pct}% совпадение</span>
      </div>
      <b>Последовательность действий:</b>
      ${stepsHtml}
    </div>
    <details>
      <summary style="cursor:pointer;font-size:.9rem;font-weight:600;color:#555;padding:4px 0">
        📋 Объяснение вывода
      </summary>
      <table style="margin-top:10px">
        <thead><tr><th></th><th>Характеристика</th><th>Введено</th><th>Норма для диагноза</th></tr></thead>
        <tbody>${explRows}</tbody>
      </table>
    </details>
    ${ollamaSection}
  </div>`;

  // Подгружаем актуальный список моделей в select внутри результата
  if (selectedOllamaModel) {
    api.get('/api/ollama/status').then(d => {
      const w = document.getElementById('model-select-wrap-result');
      if (w && d.models && d.models.length) {
        w.innerHTML = `<select id="model-select-result"
          style="padding:4px 10px;border-radius:6px;border:1px solid #c4b5fd;
                 font-size:.85rem;background:#fff;color:#5b21b6"
          onchange="selectedOllamaModel=this.value">
          ${d.models.map(m =>
            `<option value="${m}" ${m === selectedOllamaModel ? 'selected' : ''}>${m}</option>`
          ).join('')}
        </select>`;
      }
    });
  }
}

async function runOllamaCheck() {
  if (!lastDiagResult) return;
  const btn    = document.getElementById('btn-ai-run');
  const aiDiv  = document.getElementById('ai-result');
  const selEl  = document.getElementById('model-select-result');
  const model  = selEl ? selEl.value : selectedOllamaModel;
  if (btn) btn.disabled = true;
  aiDiv.innerHTML = `<div class="ai-thinking" style="margin-top:12px">
    <span class="spinner"></span> ИИ анализирует результат...
  </div>`;
  try {
    // FIX #2: передаём выбранную модель
    const result = await api.post('/api/ollama/check', { ...lastDiagResult, model });
    aiDiv.innerHTML = `<div class="ai-response">${escHtml(result.response)}</div>`;
  } catch (e) {
    aiDiv.innerHTML = `<div class="alert alert-error" style="margin-top:10px">
      Ошибка Ollama: ${e.error || JSON.stringify(e)}
    </div>`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

// ==================== EDITOR ====================
function renderEditor() {
  renderPartsEditor();
  renderCharsEditor();
  renderRepairsEditor();
  renderDiagEditor();
  populateRepairSelectEditor(); // FIX #4
}

function renderPartsEditor() {
  const tb = document.getElementById('parts-tbody');
  if (!tb) return;
  tb.innerHTML = (KB.parts || []).map(p => `
    <tr>
      <td><b>${p.name}</b></td>
      <td>
        <div class="tag-list">
          ${(p.characteristics || []).map(c => `<span class="tag">${c}</span>`).join('')}
          <span class="tag"
            style="cursor:pointer;background:#e6f4ea;color:#2e7d32"
            onclick="openPartCharModal(${p.id}, '${escAttr(p.name)}')">+ добавить</span>
        </div>
      </td>
      <td><button class="btn btn-danger" onclick="deletePart(${p.id})">✕</button></td>
    </tr>`).join('');
}

function renderCharsEditor() {
  const tb = document.getElementById('chars-tbody');
  if (!tb) return;
  tb.innerHTML = Object.values(KB.characteristics || {}).map(c => `
    <tr>
      <td>${c.name} <span class="badge badge-blue">${c.unit || ''}</span></td>
      <td>[${c.min_val}; ${c.max_val}]</td>
      <td>[${c.normal_min}; ${c.normal_max}]</td>
      <td><button class="btn btn-danger" onclick="deleteChar(${c.id})">✕</button></td>
    </tr>`).join('');
}

function renderRepairsEditor() {
  const tb = document.getElementById('repairs-tbody');
  if (!tb) return;
  tb.innerHTML = (KB.repairs || []).map(r => `
    <tr>
      <td>${r.name}</td>
      <td style="font-size:.82rem;color:#555">
        ${(r.steps || []).slice(0, 2).join('; ')}${(r.steps || []).length > 2 ? '...' : ''}
      </td>
      <td><button class="btn btn-danger" onclick="deleteRepair(${r.id})">✕</button></td>
    </tr>`).join('');
}

function renderDiagEditor() {
  const tb = document.getElementById('diag-tbody');
  if (!tb) return;
  tb.innerHTML = (KB.diagnoses || []).map(d => `
    <tr>
      <td><b>${d.name}</b></td>
      <td>
        <span class="badge badge-orange">${(d.characteristics || []).length} хар-к</span>
        <span style="cursor:pointer;margin-left:6px;font-size:.85rem"
          onclick="openDiagCharModal(${d.id}, '${escAttr(d.name)}')">✏️ изменить</span>
      </td>
      <td><span class="badge badge-green">${d.repair_name || '—'}</span></td>
      <td><button class="btn btn-danger" onclick="deleteDiag(${d.id})">✕</button></td>
    </tr>`).join('');
}

// FIX #4: заполняем список ремонтов в форме добавления диагноза
function populateRepairSelectEditor() {
  const sel = document.getElementById('new-diag-repair');
  if (!sel) return;
  sel.innerHTML = '<option value="">-- Выберите ремонт --</option>';
  (KB.repairs || []).forEach(r => {
    sel.innerHTML += `<option value="${r.id}">${r.name}</option>`;
  });
}

// ==================== MODAL: хар-ки детали (FIX #3) ====================
function openPartCharModal(partId, partName) {
  const existing = (KB.parts.find(p => p.id === partId) || {}).characteristics || [];
  const available = Object.values(KB.characteristics || {}).filter(c => !existing.includes(c.name));
  const opts = available.map(c => `<option value="${c.id}">${c.name} (${c.unit})</option>`).join('');

  showModal(
    `Добавить характеристику к «${partName}»`,
    `<label>Характеристика</label>
     <select id="modal-char-sel">
       ${opts || '<option disabled>Все характеристики уже добавлены</option>'}
     </select>`,
    async () => {
      const cid = parseInt(document.getElementById('modal-char-sel').value);
      if (!cid) return;
      await api.post(`/api/parts/${partId}/characteristics`, { char_id: cid });
      await loadKB();
      renderPartsEditor();
      closeModal();
      showToast('Характеристика добавлена к детали');
    }
  );
}

// ==================== MODAL: хар-ки диагноза (FIX #3) ====================
function openDiagCharModal(diagId, diagName) {
  const diag         = KB.diagnoses.find(d => d.id === diagId) || {};
  const existNames   = (diag.characteristics || []).map(c => c.char_name);
  const available    = Object.values(KB.characteristics || {}).filter(c => !existNames.includes(c.name));

  const existRows = (diag.characteristics || []).map(c => `
    <tr>
      <td>${c.char_name}</td>
      <td>${formatRange(c)}</td>
      <td>${KB.characteristics[c.char_name]?.unit || ''}</td>
    </tr>`).join('');

  const availOpts = available.map(c =>
    `<option value="${c.id}">${c.name} (${c.unit})</option>`).join('');

  showModal(
    `Характеристики диагноза «${diagName}»`,
    `<b>Текущие:</b>
     <table style="margin:8px 0 16px">
       <thead><tr><th>Хар-ка</th><th>Диапазон</th><th>Ед.</th></tr></thead>
       <tbody>${existRows || '<tr><td colspan="3" style="color:#999">Нет характеристик</td></tr>'}</tbody>
     </table>
     <hr style="margin-bottom:14px">
     <b>Добавить новую:</b>
     <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px">
       <div>
         <label>Характеристика</label>
         <select id="modal-dc-char">
           ${availOpts || '<option disabled>Нет доступных</option>'}
         </select>
       </div>
       <div>
         <label>Тип значения</label>
         <select id="modal-dc-type" onchange="toggleModalDcFields()">
           <option value="range">Диапазон</option>
           <option value="exact">Точное значение</option>
         </select>
       </div>
     </div>
     <div id="modal-dc-range"
       style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:8px">
       <div><label>Мин</label><input type="number" id="modal-dc-min" step="any"></div>
       <div><label>Макс</label><input type="number" id="modal-dc-max" step="any"></div>
       <div><label>Скобка мин</label>
         <select id="modal-dc-exmin">
           <option value="0">[ включительно</option>
           <option value="1">( исключая</option>
         </select>
       </div>
       <div><label>Скобка макс</label>
         <select id="modal-dc-exmax">
           <option value="0">] включительно</option>
           <option value="1">) исключая</option>
         </select>
       </div>
     </div>
     <div id="modal-dc-exact" style="display:none">
       <label>Точное значение</label>
       <input type="number" id="modal-dc-exactval" step="any">
     </div>`,
    async () => {
      const cid  = parseInt(document.getElementById('modal-dc-char').value);
      if (!cid) return;
      const type = document.getElementById('modal-dc-type').value;
      const payload = { char_id: cid };
      if (type === 'exact') {
        payload.exact_val = parseFloat(document.getElementById('modal-dc-exactval').value);
      } else {
        payload.range_min      = parseFloat(document.getElementById('modal-dc-min').value);
        payload.range_max      = parseFloat(document.getElementById('modal-dc-max').value);
        payload.exclusive_min  = parseInt(document.getElementById('modal-dc-exmin').value);
        payload.exclusive_max  = parseInt(document.getElementById('modal-dc-exmax').value);
      }
      await api.post(`/api/diagnoses/${diagId}/characteristics`, payload);
      await loadKB();
      renderDiagEditor();
      closeModal();
      showToast('Характеристика добавлена к диагнозу');
    },
    'Добавить характеристику'
  );
}

function toggleModalDcFields() {
  const t = document.getElementById('modal-dc-type').value;
  document.getElementById('modal-dc-range').style.display  = t === 'range' ? 'grid'  : 'none';
  document.getElementById('modal-dc-exact').style.display  = t === 'exact' ? 'block' : 'none';
}

// ==================== MODAL ENGINE ====================
function showModal(title, bodyHtml, onConfirm, confirmLabel = 'Сохранить') {
  let m = document.getElementById('global-modal');
  if (!m) {
    m = document.createElement('div');
    m.id = 'global-modal';
    m.style.cssText =
      'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9999;' +
      'display:flex;align-items:center;justify-content:center';
    document.body.appendChild(m);
  }
  m.innerHTML = `
    <div style="background:#fff;border-radius:14px;padding:28px;max-width:580px;
                width:92%;max-height:85vh;overflow-y:auto;
                box-shadow:0 8px 32px rgba(0,0,0,.2)">
      <h2 style="margin-bottom:16px;font-size:1.05rem;color:#1a73e8">${title}</h2>
      ${bodyHtml}
      <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:20px">
        <button class="btn btn-outline" onclick="closeModal()">Отмена</button>
        <button class="btn btn-primary" onclick="modalConfirm()">${confirmLabel}</button>
      </div>
    </div>`;
  m._confirm      = onConfirm;
  m.style.display = 'flex';
  m.onclick = e => { if (e.target === m) closeModal(); };
}

async function modalConfirm() {
  const m = document.getElementById('global-modal');
  if (m && m._confirm) await m._confirm();
}
function closeModal() {
  const m = document.getElementById('global-modal');
  if (m) m.style.display = 'none';
}

// ==================== EDITOR ACTIONS ====================
async function addPart() {
  const n = document.getElementById('new-part').value.trim();
  if (!n) return;
  await api.post('/api/parts', { name: n });
  await loadKB(); renderPartsEditor();
  document.getElementById('new-part').value = '';
  showToast('Деталь добавлена');
}
async function deletePart(id) {
  if (!confirm('Удалить деталь?')) return;
  await api.delete('/api/parts/' + id);
  await loadKB(); renderPartsEditor();
}
async function addChar() {
  const data = {
    name:       document.getElementById('nc-name').value.trim(),
    unit:       document.getElementById('nc-unit').value.trim(),
    min_val:    parseFloat(document.getElementById('nc-min').value),
    max_val:    parseFloat(document.getElementById('nc-max').value),
    normal_min: parseFloat(document.getElementById('nc-nmin').value),
    normal_max: parseFloat(document.getElementById('nc-nmax').value),
  };
  if (!data.name) return;
  await api.post('/api/characteristics', data);
  await loadKB(); renderCharsEditor();
  showToast('Характеристика добавлена');
}
async function deleteChar(id) {
  if (!confirm('Удалить характеристику?')) return;
  await api.delete('/api/characteristics/' + id);
  await loadKB(); renderCharsEditor();
}
async function addRepair() {
  const name  = document.getElementById('new-repair-name').value.trim();
  const steps = document.getElementById('new-repair-steps').value
                  .trim().split('\n').map(s => s.trim()).filter(Boolean);
  if (!name) return;
  await api.post('/api/repairs', { name, steps });
  await loadKB(); renderRepairsEditor(); populateRepairSelectEditor();
  document.getElementById('new-repair-name').value  = '';
  document.getElementById('new-repair-steps').value = '';
  showToast('Ремонт добавлен');
}
async function deleteRepair(id) {
  if (!confirm('Удалить ремонт?')) return;
  await api.delete('/api/repairs/' + id);
  await loadKB(); renderRepairsEditor(); populateRepairSelectEditor();
}
async function addDiag() {
  const name     = document.getElementById('new-diag-name').value.trim();
  const repairId = parseInt(document.getElementById('new-diag-repair').value) || null;
  if (!name) return;
  await api.post('/api/diagnoses', { name, repair_id: repairId });
  await loadKB(); renderDiagEditor(); populateDiagSelect(); populateRepairSelectEditor();
  document.getElementById('new-diag-name').value = '';
  showToast('Диагноз добавлен');
}
async function deleteDiag(id) {
  if (!confirm('Удалить диагноз?')) return;
  await api.delete('/api/diagnoses/' + id);
  await loadKB(); renderDiagEditor(); populateDiagSelect();
}

// ==================== KB PAGE ====================
function renderKBPage() {
  const tb1 = document.getElementById('kb-parts-tbody');
  if (tb1) tb1.innerHTML = (KB.parts || []).map(p => `
    <tr>
      <td><b>${p.name}</b></td>
      <td><div class="tag-list">
        ${(p.characteristics || []).map(c => `<span class="tag">${c}</span>`).join('')}
      </div></td>
    </tr>`).join('');

  const tb2 = document.getElementById('kb-diag-tbody');
  if (tb2) {
    let rows = '';
    (KB.diagnoses || []).forEach(d => {
      const chars = d.characteristics || [];
      if (!chars.length) {
        rows += `<tr><td><b>${d.name}</b></td><td colspan="3" style="color:#999">—</td></tr>`;
        return;
      }
      chars.forEach((c, i) => {
        const meta = KB.characteristics[c.char_name] || {};
        rows += `<tr>
          ${i === 0 ? `<td rowspan="${chars.length}"><b>${d.name}</b></td>` : ''}
          <td>${c.char_name}</td>
          <td>${formatRange(c)}</td>
          <td>${meta.unit || ''}</td>
        </tr>`;
      });
    });
    tb2.innerHTML = rows;
  }

  const tb3 = document.getElementById('kb-repairs-tbody');
  if (tb3) tb3.innerHTML = (KB.diagnoses || []).map(d => {
    const r = KB.repairs.find(r => r.name === d.repair_name) || {};
    return `<tr>
      <td><b>${d.name}</b></td>
      <td><span class="badge badge-green">${d.repair_name || '—'}</span></td>
      <td><ol class="steps-list" style="font-size:.82rem">
        ${(r.steps || []).map(s => `<li>${s}</li>`).join('')}
      </ol></td>
    </tr>`;
  }).join('');
}

// ==================== UTILS ====================
function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function escAttr(s) {
  return String(s).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}
function showToast(msg, type = 'success') {
  const t = document.createElement('div');
  t.className = `alert alert-${type}`;
  t.style.cssText =
    'position:fixed;bottom:24px;right:24px;z-index:9999;' +
    'min-width:240px;box-shadow:0 4px 16px rgba(0,0,0,.15)';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}
