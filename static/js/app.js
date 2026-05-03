/* ════════════════════════════════════════════════════════════
   app.js — SmartFix v4
   Разделение по модулям:
     STATE      — глобальное состояние
     API        — запросы к серверу
     UI PAGES   — переключение страниц
     DIAGNOSIS  — логика диагностики
     KB EDITOR  — редактор базы знаний
     MODALS     — модальные окна
     INIT       — инициализация
════════════════════════════════════════════════════════════ */

// ══════════════════════════════════════════════
// STATE
// ══════════════════════════════════════════════
const STATE = {
  chars: [],       // все характеристики из БД
  lastResult: null // последний результат диагностики
};

// Порядок ввода характеристик для формы (совпадает с FEATURE_ORDER в ml_model.py)
const CHAR_DISPLAY = [
  { name: "Напряжение аккумулятора", unit: "В",    type: "float",  min: 0,    max: 5,    step: 0.01 },
  { name: "Уровень заряда",          unit: "%",    type: "int",    min: 0,    max: 100,  step: 1    },
  { name: "Вздутие аккумулятора",    unit: "",     type: "binary", min: 0,    max: 1,    step: 1    },
  { name: "Ёмкость аккумулятора",    unit: "%",    type: "float",  min: 0,    max: 100,  step: 0.1  },
  { name: "Коэффициент износа",      unit: "%",    type: "float",  min: 0,    max: 100,  step: 0.1  },
  { name: "Частота процессора",      unit: "МГц",  type: "int",    min: 0,    max: 4000, step: 1    },
  { name: "Температура процессора",  unit: "°C",   type: "float",  min: -120, max: -40,  step: 0.1  },
  { name: "Площадь трещин экрана",   unit: "мм²",  type: "int",    min: 0,    max: 1000, step: 1    },
  { name: "Яркость экрана",          unit: "%",    type: "float",  min: 0,    max: 200,  step: 0.1  },
  { name: "Битые пиксели",           unit: "",     type: "binary", min: 0,    max: 1,    step: 1    },
];

// ══════════════════════════════════════════════
// API helpers
// ══════════════════════════════════════════════
async function api(method, url, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch(url, opts);
  return r.json();
}
const GET  = url        => api("GET",    url);
const POST = (url, b)   => api("POST",   url, b);
const PUT  = (url, b)   => api("PUT",    url, b);
const DEL  = url        => api("DELETE", url);

// ══════════════════════════════════════════════
// UI — страницы
// ══════════════════════════════════════════════
function showPage(name) {
  document.querySelectorAll(".main-content").forEach(el => el.classList.remove("visible"));
  document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
  document.getElementById(`page-${name}`).classList.add("visible");
  document.querySelector(`.nav-btn[onclick="showPage('${name}')"]`).classList.add("active");
  if (name === "kb") loadKBSection("parts");
}

// ══════════════════════════════════════════════
// STATUS BAR
// ══════════════════════════════════════════════
async function refreshStatus() {
  // Ollama
  const os = await GET("/api/ollama/status");
  const odot = document.getElementById("ollama-dot");
  const olbl = document.getElementById("ollama-label");
  if (os.ok) {
    odot.className = "dot ok"; olbl.textContent = "Ollama";
    const sel = document.getElementById("ollama-model");
    sel.innerHTML = os.models.map(m => `<option>${m}</option>`).join("");
  } else {
    odot.className = "dot err"; olbl.textContent = "Ollama: недоступна";
  }
  // ML
  const ms = await GET("/api/ml/status");
  const mdot = document.getElementById("ml-dot");
  mdot.className = ms.loaded ? "dot ok" : "dot err";
  document.getElementById("ml-label").textContent = ms.loaded
    ? `ML (${ms.n_classes} кл.)` : "ML: не обучена";
}

// ══════════════════════════════════════════════
// DIAGNOSIS — форма ввода
// ══════════════════════════════════════════════
function buildInputForm() {
  const grid = document.getElementById("char-inputs");
  grid.innerHTML = CHAR_DISPLAY.map(c => {
    if (c.type === "binary") {
      return `<div class="form-group">
        <label class="form-label">${c.name}</label>
        <select class="form-select" data-char="${c.name}">
          <option value="">— не задано —</option>
          <option value="0">0 — Нет</option>
          <option value="1">1 — Да</option>
        </select>
      </div>`;
    }
    return `<div class="form-group">
      <label class="form-label">${c.name} <small>${c.unit}</small></label>
      <input class="form-input" type="number" data-char="${c.name}"
        min="${c.min}" max="${c.max}" step="${c.step}"
        placeholder="${c.min} – ${c.max}">
    </div>`;
  }).join("");
}

function getFormValues() {
  const vals = {};
  document.querySelectorAll("[data-char]").forEach(el => {
    if (el.value !== "" && el.value !== null) {
      vals[el.dataset.char] = parseFloat(el.value);
    }
  });
  return vals;
}

function resetForm() {
  document.querySelectorAll("[data-char]").forEach(el => el.value = "");
  document.getElementById("diag-result").innerHTML = `
    <div class="empty-state">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <h3>Введите параметры</h3>
      <p>Заполните хотя бы одно поле и нажмите «Диагностировать»</p>
    </div>`;
  document.getElementById("ollama-section").style.display = "none";
  STATE.lastResult = null;
}

// ══════════════════════════════════════════════
// DIAGNOSIS — запуск
// ══════════════════════════════════════════════
async function runDiagnosis() {
  const values = getFormValues();
  if (Object.keys(values).length === 0) {
    showToast("Введите хотя бы одну характеристику", "err"); return;
  }
  const btn = document.getElementById("btn-diagnose");
  btn.disabled = true; btn.textContent = "Анализ...";
  try {
    const res = await POST("/api/diagnose", values);
    STATE.lastResult = { result: res, features: values };
    renderDiagResult(res);
    document.getElementById("ollama-section").style.display = "block";
  } catch(e) {
    showToast("Ошибка соединения с сервером", "err");
  } finally {
    btn.disabled = false; btn.textContent = "Диагностировать";
  }
}

function renderDiagResult(res) {
  const container = document.getElementById("diag-result");
  const { expert_candidates, ml_ranking, final_diagnosis, method_label, repair } = res;

  let html = `<div class="diag-result">`;

  // Финальный диагноз
  if (final_diagnosis) {
    const methodClass = res.selection_method === "ml_only" ? "ml-only"
                      : res.selection_method === "hybrid"  ? "hybrid" : "";
    html += `<div class="result-header">
      <div>
        <div style="font-size:.75rem;color:var(--color-text-muted);margin-bottom:.25rem">Итоговый диагноз</div>
        <div class="result-title">${final_diagnosis}</div>
      </div>
      <span class="method-tag ${methodClass}">${method_label}</span>
    </div>`;
  } else {
    html += `<div class="empty-state"><h3>Диагноз не определён</h3><p>Недостаточно данных для диагностики</p></div>`;
  }

  // Экспертная система — кандидаты
  if (expert_candidates && expert_candidates.length > 0) {
    html += `<div>
      <div style="font-size:.8125rem;font-weight:600;color:var(--color-text-muted);margin-bottom:.5rem;text-transform:uppercase;letter-spacing:.04em">
        Экспертная система — кандидаты
      </div>
      <div class="candidates-list">`;
    expert_candidates.forEach((c, i) => {
      html += `<div class="candidate-row ${i===0?'top':''}">
        <span class="cand-name">${c.name}</span>
        <span class="cand-pct">${c.pct}%</span>
        <div class="progress-track"><div class="progress-fill" style="width:${c.pct}%"></div></div>
      </div>`;
    });
    html += `</div></div>`;
  }

  // ML — топ-3
if (ml_ranking && ml_ranking.length > 0) {
  html += `<div>
    <div style="font-size:.8125rem;font-weight:600;color:var(--color-text-muted);
      margin-bottom:.5rem;text-transform:uppercase;letter-spacing:.04em">
      ML-классификатор (DecisionTree) — топ-3
    </div>
    <div class="ml-ranking">`;
  ml_ranking.forEach((item, i) => {
    // Защита: item может быть [name, pct] или {name, pct}
    const name = Array.isArray(item) ? item[0] : item.name;
    const pct  = Array.isArray(item) ? Number(item[1]) : Number(item.pct);
    html += `<div class="ml-row">
      <span class="ml-rank ${i===0 ? 'gold' : ''}">${i+1}</span>
      <span>${name}</span>
      <span class="cand-pct">${pct}%</span>
      <div class="progress-track">
        <div class="progress-fill" style="width:${Math.min(pct,100)}%;
          ${i>0 ? 'background:var(--color-text-faint)' : ''}"></div>
      </div>
    </div>`;
  });
  html += `</div></div>`;
}

  // Ремонт
  if (repair) {
    html += `<div>
      <div style="font-size:.8125rem;font-weight:600;color:var(--color-text-muted);margin-bottom:.75rem;text-transform:uppercase;letter-spacing:.04em">
        Рекомендуемый ремонт
      </div>
      <div class="repair-block">
        <div class="repair-title">${repair.name}</div>
        <ol class="repair-steps">
          ${repair.steps.map((s,i) => `<li><span class="step-num">${i+1}</span><span>${s}</span></li>`).join("")}
        </ol>
      </div>
    </div>`;
  }

  html += `</div>`;
  container.innerHTML = html;
}

// ══════════════════════════════════════════════
// OLLAMA
// ══════════════════════════════════════════════
async function runOllama() {
  if (!STATE.lastResult) return;
  const model = document.getElementById("ollama-model").value;
  if (!model) { showToast("Модель Ollama не выбрана", "err"); return; }
  const btn = document.getElementById("btn-ollama");
  btn.disabled = true; btn.textContent = "Анализ ИИ...";
  const out = document.getElementById("ollama-output");
  out.innerHTML = `<div class="ollama-output" style="color:var(--color-text-muted)">Ожидание ответа от модели...</div>`;
  try {
    const r = await POST("/api/ollama/verify", {
      model, features: STATE.lastResult.features,
      diagnosis: STATE.lastResult.result.final_diagnosis,
      repair: STATE.lastResult.result.repair || {},
      ml_ranking: STATE.lastResult.result.ml_ranking,
      selection_method: STATE.lastResult.result.method_label,
    });
    out.innerHTML = r.ok
      ? `<div class="ollama-output">${escHtml(r.text)}</div>`
      : `<div class="ollama-output" style="color:var(--color-error)">Ошибка: ${escHtml(r.error)}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = "Запустить проверку";
  }
}

// ══════════════════════════════════════════════
// KB EDITOR — переключение разделов
// ══════════════════════════════════════════════
function showKBSection(name) {
  document.querySelectorAll(".kb-section").forEach(s => s.classList.remove("visible"));
  document.querySelectorAll(".kb-nav-btn").forEach(b => b.classList.remove("active"));
  document.getElementById(`kb-${name}`).classList.add("visible");
  document.querySelector(`.kb-nav-btn[onclick="showKBSection('${name}')"]`).classList.add("active");
  loadKBSection(name);
}

function loadKBSection(name) {
  const loaders = { parts: loadParts, chars: loadChars, repairs: loadRepairs, diagnoses: loadDiagnoses };
  if (loaders[name]) loaders[name]();
}

// ── Детали ────────────────────────────────────
async function loadParts() {
  const parts = await GET("/api/parts");
  const list  = document.getElementById("parts-list");
  if (!parts.length) { list.innerHTML = `<div class="empty-state"><p>Нет деталей. Добавьте первую.</p></div>`; return; }
  list.innerHTML = parts.map(p => `
    <div class="kb-item" id="part-${p.id}">
      <div class="kb-item-header" onclick="toggleItem('part-body-${p.id}')">
        <span class="kb-item-name">${p.name}</span>
        <div class="kb-item-actions" onclick="event.stopPropagation()">
          <button class="btn btn-sm btn-ghost" onclick="openAddPartChar(${p.id})">+ Характеристика</button>
          <button class="btn btn-sm btn-danger" onclick="deletePart(${p.id})">Удалить</button>
        </div>
      </div>
      <div class="kb-item-body" id="part-body-${p.id}">
        <div style="font-size:.8125rem;color:var(--color-text-muted);margin-bottom:.5rem">Характеристики:</div>
        <div class="tags-row" id="part-chars-${p.id}">Загрузка...</div>
      </div>
    </div>`).join("");
  // Загружаем характеристики каждой детали
  parts.forEach(async p => {
    const chars = await GET(`/api/parts/${p.id}/characteristics`);
    const el = document.getElementById(`part-chars-${p.id}`);
    el.innerHTML = chars.length
      ? chars.map(c => `<span class="char-tag">${c.name} <span class="del" onclick="removePartChar(${p.id},${c.id})">x</span></span>`).join("")
      : `<span style="font-size:.8125rem;color:var(--color-text-faint)">Нет характеристик</span>`;
  });
}

async function addPart() {
  const name = document.getElementById("input-part-name").value.trim();
  if (!name) return;
  await POST("/api/parts", { name });
  closeModal("modal-add-part");
  document.getElementById("input-part-name").value = "";
  loadParts(); showToast("Деталь добавлена");
}

async function deletePart(id) {
  if (!confirm("Удалить деталь?")) return;
  await DEL(`/api/parts/${id}`);
  loadParts(); showToast("Деталь удалена");
}

async function removePartChar(pid, cid) {
  await DEL(`/api/parts/${pid}/characteristics/${cid}`);
  loadParts();
}

function openAddPartChar(pid) {
  document.getElementById("cur-part-id").value = pid;
  GET("/api/characteristics").then(chars => {
    document.getElementById("input-pc-char").innerHTML =
      chars.map(c => `<option value="${c.id}">${c.name}</option>`).join("");
  });
  openModal("modal-add-part-char");
}

async function addPartChar() {
  const pid  = document.getElementById("cur-part-id").value;
  const cid  = document.getElementById("input-pc-char").value;
  await POST(`/api/parts/${pid}/characteristics`, { characteristic_id: cid });
  closeModal("modal-add-part-char");
  loadParts(); showToast("Характеристика добавлена");
}

// ── Характеристики ────────────────────────────
async function loadChars() {
  const chars = await GET("/api/characteristics");
  const list  = document.getElementById("chars-list");
  list.innerHTML = chars.map(c => `
    <div class="kb-item">
      <div class="kb-item-header">
        <span class="kb-item-name">${c.name}</span>
        <span class="kb-item-meta">${c.unit || ""} · ${c.type} · [${c.val_min};${c.val_max}]</span>
      </div>
    </div>`).join("");
}

// ── Ремонты ───────────────────────────────────
async function loadRepairs() {
  const repairs = await GET("/api/repairs");
  const list = document.getElementById("repairs-list");
  if (!repairs.length) { list.innerHTML = `<div class="empty-state"><p>Нет ремонтов.</p></div>`; return; }
  list.innerHTML = repairs.map(r => `
    <div class="kb-item" id="repair-${r.id}">
      <div class="kb-item-header" onclick="toggleItem('repair-body-${r.id}')">
        <span class="kb-item-name">${r.name}</span>
        <div class="kb-item-actions" onclick="event.stopPropagation()">
          <button class="btn btn-sm btn-ghost" onclick="openAddStep(${r.id})">+ Шаг</button>
          <button class="btn btn-sm btn-danger" onclick="deleteRepair(${r.id})">Удалить</button>
        </div>
      </div>
      <div class="kb-item-body" id="repair-body-${r.id}">
        <div id="steps-${r.id}">Загрузка...</div>
      </div>
    </div>`).join("");
  repairs.forEach(async r => {
    const steps = await GET(`/api/repairs/${r.id}/steps`);
    const el = document.getElementById(`steps-${r.id}`);
    el.innerHTML = steps.length
      ? steps.map(s => `
          <div class="step-item">
            <span class="step-order-num">${s.step_order}</span>
            <span class="step-text">${s.description}</span>
            <button class="btn btn-sm btn-danger" onclick="deleteStep(${s.id},${r.id})">x</button>
          </div>`).join("")
      : `<span style="font-size:.8125rem;color:var(--color-text-faint)">Нет шагов</span>`;
  });
}

async function addRepair() {
  const name = document.getElementById("input-repair-name").value.trim();
  if (!name) return;
  await POST("/api/repairs", { name });
  closeModal("modal-add-repair");
  document.getElementById("input-repair-name").value = "";
  loadRepairs(); showToast("Ремонт добавлен");
}

async function deleteRepair(id) {
  if (!confirm("Удалить ремонт?")) return;
  await DEL(`/api/repairs/${id}`);
  loadRepairs(); showToast("Ремонт удалён");
}

function openAddStep(rid) {
  document.getElementById("cur-repair-id").value = rid;
  document.getElementById("input-step-desc").value = "";
  openModal("modal-add-step");
}

async function addRepairStep() {
  const rid  = document.getElementById("cur-repair-id").value;
  const desc = document.getElementById("input-step-desc").value.trim();
  if (!desc) return;
  const steps = await GET(`/api/repairs/${rid}/steps`);
  await POST(`/api/repairs/${rid}/steps`, { order: steps.length + 1, description: desc });
  closeModal("modal-add-step");
  loadRepairs(); showToast("Шаг добавлен");
}

async function deleteStep(sid, rid) {
  await DEL(`/api/repair_steps/${sid}`);
  loadRepairs();
}

// ── Диагнозы ──────────────────────────────────
async function loadDiagnoses() {
  const diags = await GET("/api/diagnoses");
  const list  = document.getElementById("diagnoses-list");
  if (!diags.length) { list.innerHTML = `<div class="empty-state"><p>Нет диагнозов.</p></div>`; return; }
  list.innerHTML = diags.map(d => `
    <div class="kb-item" id="diag-${d.id}">
      <div class="kb-item-header" onclick="toggleItem('diag-body-${d.id}')">
        <span class="kb-item-name">${d.name}</span>
        <span class="kb-item-meta">${d.repair_name || 'Ремонт не задан'}</span>
        <div class="kb-item-actions" onclick="event.stopPropagation()">
          <button class="btn btn-sm btn-ghost" onclick="openAddDiagChar(${d.id})">+ Правило</button>
          <button class="btn btn-sm btn-danger" onclick="deleteDiagnosis(${d.id})">Удалить</button>
        </div>
      </div>
      <div class="kb-item-body" id="diag-body-${d.id}">
        <div style="font-size:.8125rem;margin-bottom:.75rem">
          <span style="color:var(--color-text-muted)">Ремонт: </span>
          <select class="form-select" style="display:inline-block;width:auto;padding:.125rem .5rem;font-size:.8125rem"
            onchange="updateDiagRepair(${d.id},this.value)" id="repair-sel-${d.id}">
          </select>
        </div>
        <div style="font-size:.8125rem;color:var(--color-text-muted);margin-bottom:.5rem">Правила характеристик:</div>
        <div id="diag-chars-${d.id}">Загрузка...</div>
      </div>
    </div>`).join("");

  // Заполняем select для ремонтов и характеристики
  const repairs = await GET("/api/repairs");
  diags.forEach(async d => {
    const sel = document.getElementById(`repair-sel-${d.id}`);
    if (sel) {
      sel.innerHTML = `<option value="">— не задан —</option>` +
        repairs.map(r => `<option value="${r.id}" ${r.id == d.repair_id ? "selected":""}>${r.name}</option>`).join("");
    }
    const chars = await GET(`/api/diagnoses/${d.id}/characteristics`);
    const el = document.getElementById(`diag-chars-${d.id}`);
    el.innerHTML = chars.length
      ? chars.map(c => {
          let rule = "";
          if (c.exact_value !== null && c.exact_value !== undefined) {
            rule = `= ${c.exact_value}`;
          } else {
            const lo = c.include_min ? "[" : "(";
            const hi = c.include_max ? "]" : ")";
            rule = `${lo}${c.val_min};${c.val_max}${hi}`;
          }
          return `<div class="rule-row">
            <span class="cand-name">${c.char_name} <span class="rule-desc">${c.unit||""} ${rule}</span></span>
            <button class="btn btn-sm btn-danger" onclick="deleteDiagChar(${d.id},${c.id})">x</button>
          </div>`;
        }).join("")
      : `<span style="font-size:.8125rem;color:var(--color-text-faint)">Нет правил</span>`;
  });
}

async function updateDiagRepair(did, rid) {
  await PUT(`/api/diagnoses/${did}/repair`, { repair_id: rid || null });
  showToast("Ремонт обновлён");
}

async function addDiagnosis() {
  const name = document.getElementById("input-diag-name").value.trim();
  const rid  = document.getElementById("input-diag-repair").value || null;
  if (!name) return;
  const res = await POST("/api/diagnoses", { name, repair_id: rid });
  if (!res.ok) { showToast(res.error || "Ошибка", "err"); return; }
  closeModal("modal-add-diag");
  document.getElementById("input-diag-name").value = "";
  loadDiagnoses(); showToast("Диагноз добавлен");
}

async function deleteDiagnosis(id) {
  if (!confirm("Удалить диагноз?")) return;
  await DEL(`/api/diagnoses/${id}`);
  loadDiagnoses(); showToast("Диагноз удалён");
}

function openAddDiagChar(did) {
  document.getElementById("cur-diag-id").value = did;
  GET("/api/characteristics").then(chars => {
    document.getElementById("input-dc-char").innerHTML =
      chars.map(c => `<option value="${c.id}" data-type="${c.type}">${c.name} (${c.unit||c.type})</option>`).join("");
    onDCCharChange();
  });
  openModal("modal-add-diag-char");
}

function onDCCharChange() {
  const sel     = document.getElementById("input-dc-char");
  const opt     = sel.options[sel.selectedIndex];
  const isBin   = opt && opt.dataset.type === "binary";
  document.getElementById("dc-range-fields").style.display = isBin ? "none" : "block";
  document.getElementById("dc-exact-field").style.display  = isBin ? "block" : "none";
}

async function addDiagChar() {
  const did    = document.getElementById("cur-diag-id").value;
  const charId = document.getElementById("input-dc-char").value;
  const sel    = document.getElementById("input-dc-char");
  const isBin  = sel.options[sel.selectedIndex]?.dataset.type === "binary";
  let payload  = { characteristic_id: charId };
  if (isBin) {
    payload.exact_value = parseFloat(document.getElementById("input-dc-exact").value);
  } else {
    payload.val_min     = parseFloat(document.getElementById("input-dc-min").value);
    payload.val_max     = parseFloat(document.getElementById("input-dc-max").value);
    payload.include_min = document.getElementById("input-dc-imin").checked ? 1 : 0;
    payload.include_max = document.getElementById("input-dc-imax").checked ? 1 : 0;
    if (isNaN(payload.val_min) || isNaN(payload.val_max)) {
      showToast("Укажите мин. и макс. значения", "err"); return;
    }
    if (payload.val_min >= payload.val_max) {
      showToast("Минимум должен быть меньше максимума", "err"); return;
    }
  }
  await POST(`/api/diagnoses/${did}/characteristics`, payload);
  closeModal("modal-add-diag-char");
  loadDiagnoses(); showToast("Правило добавлено");
}

async function deleteDiagChar(did, dcid) {
  await DEL(`/api/diagnoses/${did}/characteristics/${dcid}`);
  loadDiagnoses();
}

// ── KB прочее ──────────────────────────────────
async function validateKB() {
  const res = await GET("/api/kb/validate");
  if (res.ok) {
    showToast("База знаний корректна");
  } else {
    res.problems.forEach(p => showToast(p, "err"));
  }
}

async function trainModel() {
  const btn = document.getElementById("btn-train");
  btn.disabled = true; btn.textContent = "Обучение...";
  showToast("Переобучение модели — подождите...");
  try {
    const res = await POST("/api/ml/train", {});
    if (res.ok) {
      showToast(`Модель обучена. Balanced accuracy: ${res.balanced_accuracy}%`);
      refreshStatus();
    } else {
      showToast(res.error || "Ошибка обучения", "err");
    }
  } finally {
    btn.disabled = false; btn.textContent = "Переобучить ML-модель";
  }
}

// ══════════════════════════════════════════════
// MODALS
// ══════════════════════════════════════════════
function openModal(id) {
  if (id === "modal-add-diag") {
    GET("/api/repairs").then(repairs => {
      document.getElementById("input-diag-repair").innerHTML =
        `<option value="">— не задан —</option>` +
        repairs.map(r => `<option value="${r.id}">${r.name}</option>`).join("");
    });
  }
  document.getElementById(id).classList.add("open");
}
function closeModal(id) { document.getElementById(id).classList.remove("open"); }

// Закрыть по клику вне модала
document.querySelectorAll(".modal-overlay").forEach(o =>
  o.addEventListener("click", e => { if (e.target === o) o.classList.remove("open"); })
);

// ══════════════════════════════════════════════
// UTILS
// ══════════════════════════════════════════════
function toggleItem(id) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle("open");
}

function showToast(msg, type = "ok") {
  const c = document.getElementById("toasts");
  const t = document.createElement("div");
  t.className = `toast ${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3800);
}

function escHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

// Тема
(function(){
  const btn = document.querySelector("[data-theme-toggle]");
  const html = document.documentElement;
  let theme = matchMedia("(prefers-color-scheme:dark)").matches ? "dark" : "light";
  html.setAttribute("data-theme", theme);
  function updateIcon() {
    btn.innerHTML = theme === "dark"
      ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>`
      : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
  }
  updateIcon();
  btn.addEventListener("click", () => {
    theme = theme === "dark" ? "light" : "dark";
    html.setAttribute("data-theme", theme);
    updateIcon();
  });
})();

// ══════════════════════════════════════════════
// INIT
// ══════════════════════════════════════════════
document.addEventListener("DOMContentLoaded", () => {
  buildInputForm();
  refreshStatus();
});