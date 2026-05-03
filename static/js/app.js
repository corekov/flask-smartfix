/* ─────────────────────────────────────────────────
   SmartFix — клиентская логика (app.js)
   Структура:
   1. Утилиты
   2. Инициализация и навигация
   3. Страница диагностики
   4. Редактор базы знаний (детали / диагнозы / ремонты)
   5. Модальные окна
   6. ML-обучение
───────────────────────────────────────────────── */

"use strict";

// ═══════════════════════ 1. УТИЛИТЫ ═══════════════════════

const $ = id => document.getElementById(id);
const show = el => el && el.classList.remove("hidden");
const hide = el => el && el.classList.add("hidden");

function toast(msg, type = "info") {
  const div = document.createElement("div");
  div.className = `toast ${type}`;
  div.textContent = msg;
  $("toastContainer").appendChild(div);
  setTimeout(() => div.remove(), 3800);
}

async function api(path, method = "GET", body = null) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(path, opts);
  return res.json();
}

// ═══════════════════════ 2. НАВИГАЦИЯ ═══════════════════════

let currentTab = "diagnose";

function initNav() {
  document.querySelectorAll(".nav-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentTab = tab;
      if (tab === "diagnose") {
        show($("tabDiagnose")); hide($("tabEditor"));
      } else {
        hide($("tabDiagnose")); show($("tabEditor"));
        refreshEditor();
      }
    });
  });

  // Редактор вкладки
  document.querySelectorAll(".editor-nav-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".editor-nav-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const etab = btn.dataset.etab;
      document.querySelectorAll(".etab").forEach(e => e.classList.add("hidden"));
      $(`etab${etab.charAt(0).toUpperCase() + etab.slice(1)}`).classList.remove("hidden");
    });
  });

  // Закрытие модалок
  document.querySelectorAll("[data-close]").forEach(btn => {
    btn.addEventListener("click", () => closeModal(btn.dataset.close));
  });
  document.querySelectorAll(".modal-overlay").forEach(overlay => {
    overlay.addEventListener("click", e => {
      if (e.target === overlay) closeModal(overlay.id);
    });
  });

  // Тема
  (function() {
    const btn = document.querySelector("[data-theme-toggle]");
    const html = document.documentElement;
    let dark = matchMedia("(prefers-color-scheme: dark)").matches;
    html.setAttribute("data-theme", dark ? "dark" : "light");
    if (btn) btn.addEventListener("click", () => {
      dark = !dark;
      html.setAttribute("data-theme", dark ? "dark" : "light");
    });
  })();
}

// ══════════════════ 3. СТРАНИЦА ДИАГНОСТИКИ ══════════════════

let allCharacteristics = [];  // [{id, name, unit, value_type, part_name}]

async function loadDiagnoseTab() {
  const chars = await api("/api/characteristics");
  allCharacteristics = chars;
  renderCharsForm(chars);
  checkOllama();
}

/** Группирует характеристики по деталям и рендерит форму ввода */
function renderCharsForm(chars) {
  const form = $("charsForm");
  form.innerHTML = "";

  // Группировка
  const groups = {};
  chars.forEach(c => {
    if (!groups[c.part_name]) groups[c.part_name] = [];
    groups[c.part_name].push(c);
  });

  Object.entries(groups).forEach(([partName, partChars]) => {
    const group = document.createElement("div");
    group.className = "part-group";
    group.innerHTML = `<div class="part-group-label">${partName}</div>`;

    partChars.forEach(c => {
      const field = document.createElement("div");
      field.className = "char-field";

      const unitBadge = c.unit ? `<span class="char-unit">${c.unit}</span>` : "";
      field.innerHTML = `
        <label class="char-label">
          ${c.name} ${unitBadge}
        </label>`;

      if (c.value_type === "binary") {
        // Бинарный — три состояния: не указано / 0 / 1
        const wrap = document.createElement("div");
        wrap.className = "binary-toggle";
        wrap.innerHTML = `
          <button type="button" data-val="" class="active">— не указано</button>
          <button type="button" data-val="0">0 (нет)</button>
          <button type="button" data-val="1">1 (есть)</button>`;
        wrap.dataset.charId = c.id;
        wrap.dataset.charName = c.name;
        wrap.dataset.value = "";  // пусто = не указано
        wrap.querySelectorAll("button").forEach(btn => {
          btn.addEventListener("click", () => {
            wrap.querySelectorAll("button").forEach(b => b.classList.remove("active"));
            btn.classList.add("active");
            wrap.dataset.value = btn.dataset.val;
          });
        });
        field.appendChild(wrap);
      } else {
        // Числовой ввод
        const hint = getCharHint(c.name);
        const wrap = document.createElement("div");
        wrap.className = "char-input-wrap";
        const inp = document.createElement("input");
        inp.type = "number";
        inp.className = "char-input";
        inp.dataset.charId = c.id;
        inp.dataset.charName = c.name;
        inp.placeholder = hint.placeholder;
        inp.step = c.value_type === "real" ? "0.01" : "1";
        if (hint.min !== null) inp.min = hint.min;
        if (hint.max !== null) inp.max = hint.max;
        wrap.appendChild(inp);
        field.appendChild(wrap);
        if (hint.desc) {
          const h = document.createElement("div");
          h.className = "char-hint";
          h.textContent = hint.desc;
          field.appendChild(h);
        }
      }
      group.appendChild(field);
    });

    form.appendChild(group);
  });
}

/** Подсказки/диапазоны для каждой характеристики */
function getCharHint(name) {
  const hints = {
    "Напряжение аккумулятора":             { placeholder: "3.7 – 4.2", desc: "Норма: 3.7–4.2 В", min: 0, max: 5 },
    "Уровень заряда аккумулятора":         { placeholder: "0 – 100", desc: "Норма: 80–100 %", min: 0, max: 100 },
    "Температура аккумулятора при зарядке":{ placeholder: "20 – 45", desc: "Норма: 20–45 °C", min: 0, max: 100 },
    "Наличие вздутия аккумулятора":        { placeholder: "0 / 1", desc: "", min: 0, max: 1 },
    "Температура процессора":              { placeholder: "30 – 50", desc: "Норма: 30–50 °C", min: 0, max: 120 },
    "Скорость оперативной памяти":         { placeholder: "1600 – 3200", desc: "Норма: 1600–3200 МГц", min: 0, max: 6400 },
    "Уровень сигнала модема":              { placeholder: "-80 – -50", desc: "Норма: -80 – -50 дБм", min: -120, max: 0 },
    "Площадь трещин на стекле":            { placeholder: "0 – 500", desc: "Норма: 0 мм²", min: 0, max: 1000 },
    "Отклик дисплейной матрицы":           { placeholder: "1 – 10", desc: "Норма: 1–10 мс", min: 1, max: 500 },
    "Наличие артефактов на экране":        { placeholder: "0 / 1", desc: "", min: 0, max: 1 },
  };
  return hints[name] || { placeholder: "", desc: "", min: null, max: null };
}

/** Собирает значения из формы */
function collectInputValues() {
  const vals = {};
  // Числовые поля
  $("charsForm").querySelectorAll("input[data-char-name]").forEach(inp => {
    const v = inp.value.trim();
    if (v !== "") vals[inp.dataset.charName] = parseFloat(v);
  });
  // Бинарные — отправляем ТОЛЬКО если пользователь явно выбрал 0 или 1
  $("charsForm").querySelectorAll("[data-char-name]").forEach(wrap => {
    if (wrap.dataset.charName && wrap.dataset.value !== undefined && wrap.dataset.value !== "") {
      vals[wrap.dataset.charName] = parseFloat(wrap.dataset.value);
    }
  });
  return vals;
}

/** Кнопка «Запустить диагностику» */
async function runDiagnose() {
  const btn = $("runDiagnoseBtn");
  btn.disabled = true;
  btn.innerHTML = `<div class="spinner"></div> Анализ...`;

  const values = collectInputValues();
  if (Object.keys(values).length === 0) {
    toast("Введите хотя бы один параметр", "warning");
    btn.disabled = false;
    btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polygon points="5,3 19,12 5,21"/></svg> Запустить диагностику`;
    return;
  }

  try {
    const result = await api("/api/diagnose", "POST", values);
    renderDiagResults(result);
  } catch (e) {
    toast("Ошибка диагностики: " + e.message, "error");
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><polygon points="5,3 19,12 5,21"/></svg> Запустить диагностику`;
  }
}

function renderDiagResults(result) {
  hide($("emptyState"));
  show($("diagResults"));

  const method = result.method;  // "expert" | "hybrid" | "ml_only"
  const methodLabels = {
    expert:   ["expert",  "Экспертная система"],
    hybrid:   ["hybrid",  "Гибридный (ЭС + МО)"],
    ml_only:  ["ml_only", "Только ML"],
  };
  const [cls, label] = methodLabels[method] || ["expert", method];

  // Метод-бейдж
  $("methodRow").innerHTML = `<span class="method-badge ${cls}">${label}</span>`;
  $("methodTag").textContent = label;

  // Финальный диагноз
  $("finalDiagnosis").textContent = result.final_diagnosis || "Не определён";

  // Кандидаты экспертной системы
  const candidates = result.expert_candidates || [];
  $("expertCount").textContent = candidates.length > 0 ? `${candidates.length} кандидатов` : "";
  const cList = $("expertCandidates");
  cList.innerHTML = "";
  if (candidates.length === 0) {
    cList.innerHTML = `<div style="font-size:var(--text-xs);color:var(--color-text-faint);padding:var(--space-2)">Нет совпадений с правилами</div>`;
  } else {
    candidates.forEach((c, i) => {
      const pct = Math.round(c.match_pct * 100);
      const winner = c.name === result.final_diagnosis ? "winner" : "";
      cList.innerHTML += `
        <div class="candidate-item ${winner}">
          <span class="candidate-name">${c.name}</span>
          <div class="candidate-bar-wrap">
            <div class="candidate-bar" style="width:${pct}%"></div>
          </div>
          <span class="candidate-pct">${c.matched}/${c.total} = ${pct}%</span>
        </div>`;
    });
  }

  // ML-ранжирование
  const mlRanking = result.ml_ranking || [];
  const mlList = $("mlRanking");
  mlList.innerHTML = "";
  mlRanking.forEach((m, i) => {
    const pct = Math.round(m.probability * 100);
    const cls2 = i === 0 ? "top" : "";
    mlList.innerHTML += `
      <div class="ml-item">
        <div class="ml-rank ${cls2}">${i + 1}</div>
        <span class="ml-name">${m.name}</span>
        <div class="ml-prob-bar-wrap">
          <div class="ml-prob-bar" style="width:${pct}%"></div>
        </div>
        <span class="ml-prob">${pct}%</span>
      </div>`;
  });

  // Ремонт
  const repairs = result.repairs || [];
  if (repairs.length > 0) {
    show($("repairBlock"));
    const rc = $("repairContent");
    rc.innerHTML = "";
    repairs.forEach(rep => {
      const sect = document.createElement("div");
      sect.className = "repair-section";
      sect.innerHTML = `<div class="repair-name">${rep.name}</div>
        <div class="repair-steps">${
          rep.steps.map(s => `
            <div class="repair-step">
              <div class="step-num">${s.step_order}</div>
              <div>
                <div class="step-desc">${s.description}</div>
                ${s.condition ? `<div class="step-cond">Условие: ${s.condition}</div>` : ""}
              </div>
            </div>`).join("")
        }</div>`;
      rc.appendChild(sect);
    });
  } else {
    hide($("repairBlock"));
  }

  // Показать Ollama блок
  show($("ollamaBlock"));
  window._lastDiagResult = result;
  window._lastValues = collectInputValues();
}

// ──────────── Ollama ────────────
async function checkOllama() {
  const data = await api("/api/ollama/models");
  const dot = $("ollamaStatus").querySelector(".status-dot");
  const sel = $("ollamaModelSelect");
  if (data.models && data.models.length > 0) {
    dot.classList.add("online");
    sel.innerHTML = `<option value="">Выбрать модель...</option>` +
      data.models.map(m => `<option value="${m}">${m}</option>`).join("");
  } else {
    dot.classList.add("offline");
    $("ollamaStatus").querySelector(".status-label").textContent = "Ollama недоступна";
  }
  sel.addEventListener("change", () => {
    $("runOllamaBtn").disabled = !sel.value;
  });
  $("runOllamaBtn").addEventListener("click", runOllamaVerify);
}

async function runOllamaVerify() {
  const model = $("ollamaModelSelect").value;
  const result = window._lastDiagResult;
  if (!model || !result) return;

  const out = $("ollamaOutput");
  out.innerHTML = `<div class="ollama-loading"><div class="spinner"></div> Запрос к модели ${model}...</div>`;

  const steps = (result.repairs || []).flatMap(r => r.steps.map(s => s.description));
  const data = await api("/api/ollama/verify", "POST", {
    model,
    diagnosis: result.final_diagnosis,
    values: window._lastValues || {},
    steps,
  });

  if (data.error) {
    out.innerHTML = `<div class="ollama-placeholder" style="color:var(--color-error)">${data.error}</div>`;
  } else {
    out.innerHTML = `<div class="ollama-text">${data.response}</div>`;
  }
}

// Кнопка очистки
$("clearInputsBtn").addEventListener("click", () => {
  $("charsForm").querySelectorAll("input[data-char-name]").forEach(i => i.value = "");
  $("charsForm").querySelectorAll(".binary-toggle").forEach(wrap => {
    wrap.dataset.value = "";
    wrap.querySelectorAll("button").forEach(b => b.classList.remove("active"));
    wrap.querySelector('[data-val=""]').classList.add("active");
  });
  hide($("diagResults"));
  show($("emptyState"));
});

$("runDiagnoseBtn").addEventListener("click", runDiagnose);

// ══════════════════ 4. РЕДАКТОР ══════════════════

let allParts = [];
let allRepairs = [];
let allDiagnoses = [];
let currentEditDiagId = null;

async function refreshEditor() {
  await Promise.all([loadParts(), loadDiagnoses(), loadRepairs()]);
  updateModelStatus();
}

// ──────── Детали ────────

async function loadParts() {
  allParts = await api("/api/parts");
  const allChars = await api("/api/characteristics");
  renderParts(allParts, allChars);
}

function renderParts(parts, chars) {
  const list = $("partsList");
  list.innerHTML = "";
  if (parts.length === 0) {
    list.innerHTML = `<div style="color:var(--color-text-faint);font-size:var(--text-sm);padding:var(--space-4)">Детали не добавлены</div>`;
    return;
  }
  parts.forEach(part => {
    const partChars = chars.filter(c => c.part_name === part.name);
    const card = document.createElement("div");
    card.className = "part-card";
    card.innerHTML = `
      <div class="part-card-header">
        <span class="part-card-name">${part.name}</span>
        <div class="part-card-actions">
          <button class="btn btn-ghost btn-sm" onclick="openAddChar(${part.id}, '${part.name}')">+ Характеристика</button>
          <button class="btn btn-danger btn-sm" onclick="deletePart(${part.id})">Удалить</button>
        </div>
      </div>
      <div class="part-chars" id="partChars${part.id}">
        ${partChars.length === 0
          ? `<div style="font-size:var(--text-xs);color:var(--color-text-faint)">Характеристики не добавлены</div>`
          : partChars.map(c => `
            <div class="char-tag">
              <span class="char-tag-name">${c.name}</span>
              <span class="char-tag-meta">${typeLabel(c.value_type)}${c.unit ? " · " + c.unit : ""}</span>
              <button class="char-tag-del" onclick="deleteChar(${c.id})" title="Удалить характеристику">✕</button>
            </div>`).join("")}
      </div>`;
    list.appendChild(card);
  });
}

function typeLabel(t) {
  return { real: "R", int: "I", binary: "{0,1}" }[t] || t;
}

$("addPartBtn").addEventListener("click", () => openModal("modalAddPart"));
$("savePartBtn").addEventListener("click", async () => {
  const name = $("newPartName").value.trim();
  if (!name) return;
  const r = await api("/api/parts", "POST", { name });
  if (r.error) { toast(r.error, "error"); return; }
  toast("Деталь добавлена", "success");
  closeModal("modalAddPart");
  $("newPartName").value = "";
  loadParts();
});

window.deletePart = async (id) => {
  if (!confirm("Удалить деталь и все её характеристики?")) return;
  await api(`/api/parts/${id}`, "DELETE");
  toast("Деталь удалена", "info");
  loadParts();
};

// ──────── Характеристики ────────

window.openAddChar = (partId, partName) => {
  $("newCharPartId").value = partId;
  $("newCharName").value = "";
  $("newCharUnit").value = "";
  $("newCharType").value = "real";
  document.querySelector("#modalAddChar .modal-header h4").textContent = `Характеристика — ${partName}`;
  openModal("modalAddChar");
};

$("saveCharBtn").addEventListener("click", async () => {
  const name = $("newCharName").value.trim();
  const unit = $("newCharUnit").value.trim();
  const vtype = $("newCharType").value;
  const partId = parseInt($("newCharPartId").value);
  if (!name) { toast("Введите название", "warning"); return; }
  const r = await api("/api/characteristics", "POST", { name, unit, value_type: vtype, part_id: partId });
  if (r.error) { toast(r.error, "error"); return; }
  toast("Характеристика добавлена", "success");
  closeModal("modalAddChar");
  loadParts();
  loadDiagnoseTab(); // обновляем форму диагностики
});

window.deleteChar = async (id) => {
  if (!confirm("Удалить характеристику?")) return;
  await api(`/api/characteristics/${id}`, "DELETE");
  toast("Характеристика удалена", "info");
  loadParts();
  loadDiagnoseTab();
};

// ──────── Диагнозы ────────

async function loadDiagnoses() {
  allDiagnoses = await api("/api/diagnoses");
  renderDiagnoses(allDiagnoses);
}

function renderDiagnoses(diagnoses) {
  const list = $("diagListEditor");
  list.innerHTML = "";
  if (diagnoses.length === 0) {
    list.innerHTML = `<div style="color:var(--color-text-faint);font-size:var(--text-sm);padding:var(--space-4)">Диагнозы не добавлены</div>`;
    return;
  }
  diagnoses.forEach(d => {
    const card = document.createElement("div");
    card.className = "diag-card";
    card.innerHTML = `
      <div class="diag-card-header">
        <span class="diag-card-name">${d.name}</span>
        <div class="card-actions">
          <button class="btn btn-ghost btn-sm" onclick="openEditDiag(${d.id}, '${d.name.replace(/'/g, "\\'")}')">Редактировать</button>
          <button class="btn btn-danger btn-sm" onclick="deleteDiag(${d.id})">Удалить</button>
        </div>
      </div>`;
    list.appendChild(card);
  });
}

$("addDiagBtn").addEventListener("click", () => openModal("modalAddDiag"));
$("saveDiagBtn").addEventListener("click", async () => {
  const name = $("newDiagName").value.trim();
  if (!name) return;
  const r = await api("/api/diagnoses", "POST", { name });
  if (r.error) { toast(r.error, "error"); return; }
  toast("Диагноз добавлен", "success");
  closeModal("modalAddDiag");
  $("newDiagName").value = "";
  loadDiagnoses();
});

window.deleteDiag = async (id) => {
  if (!confirm("Удалить диагноз и все его связи?")) return;
  await api(`/api/diagnoses/${id}`, "DELETE");
  toast("Диагноз удалён", "info");
  loadDiagnoses();
};

// ──── Редактирование диагноза ────

window.openEditDiag = async (id, name) => {
  currentEditDiagId = id;
  $("editDiagTitle").textContent = `Диагноз: ${name}`;
  await Promise.all([loadDiagChars(id), loadDiagRepairs(id)]);
  openModal("modalEditDiag");
};

async function loadDiagChars(id) {
  const chars = await api(`/api/diagnoses/${id}/characteristics`);
  const list = $("diagCharList");
  list.innerHTML = "";
  if (chars.length === 0) {
    list.innerHTML = `<div style="font-size:var(--text-xs);color:var(--color-text-faint)">Характеристики не добавлены</div>`;
    return;
  }
  chars.forEach(c => {
    let rangeStr = "";
    if (c.fixed_val !== null) rangeStr = `= ${c.fixed_val}`;
    else rangeStr = `[${c.min_val ?? "−∞"}; ${c.max_val ?? "+∞"}]`;
    const item = document.createElement("div");
    item.className = "modal-item";
    item.innerHTML = `
      <span class="modal-item-name">${c.name}</span>
      <span class="modal-item-range">${rangeStr}</span>
      <button class="modal-item-del" onclick="deleteDiagChar(${currentEditDiagId},${c.id})">✕</button>`;
    list.appendChild(item);
  });
}

async function loadDiagRepairs(id) {
  const repairs = await api(`/api/diagnoses/${id}/repairs`);
  const list = $("diagRepairList");
  list.innerHTML = "";
  if (repairs.length === 0) {
    list.innerHTML = `<div style="font-size:var(--text-xs);color:var(--color-text-faint)">Ремонты не привязаны</div>`;
    return;
  }
  repairs.forEach(r => {
    const item = document.createElement("div");
    item.className = "modal-item";
    item.innerHTML = `
      <span class="modal-item-name">${r.name}</span>
      <button class="modal-item-del" onclick="deleteDiagRepair(${id},${r.id})">✕</button>`;
    list.appendChild(item);
  });
}

window.deleteDiagChar = async (diagId, dcId) => {
  await api(`/api/diagnoses/${diagId}/characteristics/${dcId}`, "DELETE");
  loadDiagChars(diagId);
};

window.deleteDiagRepair = async (diagId, repairId) => {
  await api(`/api/diagnoses/${diagId}/repairs/${repairId}`, "DELETE");
  loadDiagRepairs(diagId);
};

// Добавить характеристику к диагнозу
$("addDiagCharBtn").addEventListener("click", async () => {
  const chars = await api("/api/characteristics");
  const sel = $("diagCharSelect");
  sel.innerHTML = chars.map(c => `<option value="${c.id}" data-type="${c.value_type}">${c.name} (${c.part_name})</option>`).join("");
  updateDiagCharFields();
  sel.addEventListener("change", updateDiagCharFields);
  openModal("modalAddDiagChar");
});

function updateDiagCharFields() {
  const sel = $("diagCharSelect");
  const opt = sel.options[sel.selectedIndex];
  const vtype = opt ? opt.dataset.type : "real";
  if (vtype === "binary") {
    hide($("diagCharRangeFields").querySelector(".form-row"));
    show($("fixedValRow"));
  } else {
    show($("diagCharRangeFields").querySelector(".form-row"));
    hide($("fixedValRow"));
  }
}

// Показываем/скрываем поля в зависимости от типа
function updateDiagCharFields() {
  const sel = $("diagCharSelect");
  if (!sel.options.length) return;
  const opt = sel.options[sel.selectedIndex];
  const vtype = opt ? opt.dataset.type : "real";
  const rangeRow = $("diagCharRangeFields").querySelector(".form-row");
  if (vtype === "binary") {
    if (rangeRow) rangeRow.style.display = "none";
    $("fixedValRow").classList.remove("hidden");
  } else {
    if (rangeRow) rangeRow.style.display = "";
    $("fixedValRow").classList.add("hidden");
  }
}

$("saveDiagCharBtn").addEventListener("click", async () => {
  const charId = parseInt($("diagCharSelect").value);
  const opt = $("diagCharSelect").options[$("diagCharSelect").selectedIndex];
  const vtype = opt ? opt.dataset.type : "real";
  let body = { characteristic_id: charId };

  if (vtype === "binary") {
    body.fixed_val = parseInt($("diagCharFixed").value);
  } else {
    const mn = $("diagCharMin").value;
    const mx = $("diagCharMax").value;
    if (mn !== "" && mx !== "" && parseFloat(mn) >= parseFloat(mx)) {
      toast("Минимум должен быть меньше максимума", "error"); return;
    }
    body.min_val = mn !== "" ? parseFloat(mn) : null;
    body.max_val = mx !== "" ? parseFloat(mx) : null;
  }

  const r = await api(`/api/diagnoses/${currentEditDiagId}/characteristics`, "POST", body);
  if (r.error) { toast(r.error, "error"); return; }
  toast("Характеристика добавлена", "success");
  closeModal("modalAddDiagChar");
  loadDiagChars(currentEditDiagId);
});

// Добавить ремонт к диагнозу
$("addDiagRepairBtn").addEventListener("click", async () => {
  allRepairs = await api("/api/repairs");
  const sel = document.createElement("select");
  sel.className = "field-input";
  sel.id = "_tempRepairSel";
  sel.innerHTML = allRepairs.map(r => `<option value="${r.id}">${r.name}</option>`).join("");

  const list = $("diagRepairList");
  if (!$("_tempRepairSel")) {
    const row = document.createElement("div");
    row.className = "modal-item";
    row.id = "_tempRepairRow";
    row.style.gap = "var(--space-2)";
    const saveBtn = document.createElement("button");
    saveBtn.className = "btn btn-primary btn-sm";
    saveBtn.textContent = "OK";
    saveBtn.onclick = async () => {
      const rid = parseInt(sel.value);
      const r = await api(`/api/diagnoses/${currentEditDiagId}/repairs`, "POST", { repair_id: rid });
      if (r.error) { toast(r.error, "error"); return; }
      toast("Ремонт привязан", "success");
      document.getElementById("_tempRepairRow")?.remove();
      loadDiagRepairs(currentEditDiagId);
    };
    row.appendChild(sel);
    row.appendChild(saveBtn);
    list.prepend(row);
  }
});

// ──────── Ремонты ────────

async function loadRepairs() {
  allRepairs = await api("/api/repairs");
  renderRepairs(allRepairs);
}

function renderRepairs(repairs) {
  const list = $("repairsList");
  list.innerHTML = "";
  if (repairs.length === 0) {
    list.innerHTML = `<div style="color:var(--color-text-faint);font-size:var(--text-sm);padding:var(--space-4)">Ремонты не добавлены</div>`;
    return;
  }
  repairs.forEach(rep => {
    const card = document.createElement("div");
    card.className = "repair-card";
    const stepsHtml = rep.steps.slice(0, 4).map(s =>
      `<div class="step-preview"><span class="step-preview-num">${s.step_order}.</span>${s.description}</div>`
    ).join("") + (rep.steps.length > 4 ? `<div class="step-preview" style="color:var(--color-text-faint)">+ ещё ${rep.steps.length - 4} шагов</div>` : "");
    card.innerHTML = `
      <div class="repair-card-header">
        <span class="repair-card-name">${rep.name}</span>
        <div class="card-actions">
          <button class="btn btn-ghost btn-sm" onclick="openEditRepair(${rep.id})">✏️ Редактировать</button>
          <button class="btn btn-danger btn-sm" onclick="deleteRepair(${rep.id})">Удалить</button>
        </div>
      </div>
      <div class="repair-steps-preview">${stepsHtml}</div>`;
    list.appendChild(card);
  });
}

$("addRepairBtn").addEventListener("click", () => {
  $("newRepairName").value = "";
  $("repairStepsList").innerHTML = "";
  addRepairStep();
  openModal("modalAddRepair");
});

$("addStepBtn").addEventListener("click", addRepairStep);

function addRepairStep(desc = "", cond = "") {
  const list = $("repairStepsList");
  const idx = list.children.length + 1;
  const row = document.createElement("div");
  row.className = "step-edit-row";
  row.innerHTML = `
    <div class="step-edit-num">${idx}</div>
    <div style="flex:1;display:flex;flex-direction:column;gap:var(--space-1)">
      <input class="step-edit-input step-edit-desc" placeholder="Описание шага ${idx}" type="text" value="${desc}">
      <input class="step-edit-input step-edit-cond" placeholder="Условие (необязательно)" type="text" value="${cond}" style="font-size:var(--text-xs);color:var(--color-text-muted)">
    </div>
    <button class="step-edit-del" onclick="this.parentElement.remove();renumberSteps()">✕</button>`;
  list.appendChild(row);
}

window.renumberSteps = () => {
  $("repairStepsList").querySelectorAll(".step-edit-num").forEach((n, i) => { n.textContent = i + 1; });
};

$("saveRepairBtn").addEventListener("click", async () => {
  const name = $("newRepairName").value.trim();
  if (!name) { toast("Введите название", "warning"); return; }
  const steps = [];
  $("repairStepsList").querySelectorAll(".step-edit-row").forEach((row, i) => {
    const desc = row.querySelector(".step-edit-desc")?.value.trim() || row.querySelector("input")?.value.trim();
    const cond = row.querySelector(".step-edit-cond")?.value.trim();
    if (desc) steps.push({ description: desc, condition: cond || null });
  });
  if (steps.length === 0) { toast("Добавьте хотя бы один шаг", "warning"); return; }
  const r = await api("/api/repairs", "POST", { name, steps });
  if (r.error) { toast(r.error, "error"); return; }
  toast("Ремонт добавлен", "success");
  closeModal("modalAddRepair");
  loadRepairs();
});

window.deleteRepair = async (id) => {
  if (!confirm("Удалить ремонт?")) return;
  const r = await api(`/api/repairs/${id}`, "DELETE");
  if (r.error) { toast(r.error, "error"); return; }
  toast("Ремонт удалён", "info");
  loadRepairs();
};

// ══════════════════ 5. СЛУЖЕБНЫЕ ══════════════════

function openModal(id) { show($(id)); }
function closeModal(id) { hide($(id)); }

// Валидация БЗ
$("validateKbBtn").addEventListener("click", async () => {
  const r = await api("/api/validate_kb");
  if (r.ok) toast(r.message, "success");
  else { r.issues.forEach(i => toast(i, "warning")); }
});

// ══════════════════ 6. ML-ОБУЧЕНИЕ ══════════════════

async function updateModelStatus() {
  const r = await api("/api/model/status");
  $("modelStatusVal").textContent = r.trained ? "Готова" : "Не обучена";
  $("modelStatusVal").style.color = r.trained ? "var(--color-success)" : "var(--color-warning)";
}

$("trainModelBtn").addEventListener("click", async () => {
  // Показываем оверлей
  const overlay = document.createElement("div");
  overlay.className = "train-overlay";
  overlay.innerHTML = `
    <div class="train-card">
      <div class="spinner" style="width:32px;height:32px;border-width:3px"></div>
      <div class="train-title">Обучение ML-модели...</div>
      <div class="train-sub">DecisionTreeClassifier + GridSearchCV (5-fold)<br>Генерация датасета из базы знаний</div>
    </div>`;
  document.body.appendChild(overlay);

  try {
    const r = await api("/api/train", "POST");
    overlay.remove();
    if (r.error) { toast(r.error, "error"); return; }
    toast(`✅ Balanced accuracy: ${(r.balanced_accuracy * 100).toFixed(1)}%`, "success");
    updateModelStatus();
  } catch (e) {
    overlay.remove();
    toast("Ошибка обучения: " + e.message, "error");
  }
});

// ══════════════════ РЕДАКТИРОВАНИЕ РЕМОНТА ══════════════════

let currentEditRepairId = null;

window.openEditRepair = async (id) => {
  currentEditRepairId = id;
  const repairs = await api("/api/repairs");
  const rep = repairs.find(r => r.id === id);
  if (!rep) return;

  $("editRepairName").value = rep.name;
  $("editRepairStepsList").innerHTML = "";
  rep.steps.forEach(s => addEditRepairStep(s.description, s.condition));
  if (rep.steps.length === 0) addEditRepairStep();
  openModal("modalEditRepair");
};

function addEditRepairStep(desc = "", cond = "") {
  const list = $("editRepairStepsList");
  const idx = list.children.length + 1;
  const row = document.createElement("div");
  row.className = "step-edit-row";
  row.innerHTML = `
    <div class="step-edit-num">${idx}</div>
    <div style="flex:1;display:flex;flex-direction:column;gap:var(--space-1)">
      <input class="step-edit-input step-edit-desc" placeholder="Описание шага ${idx}" type="text" value="${desc.replace(/"/g,'&quot;')}">
      <input class="step-edit-input step-edit-cond" placeholder="Условие (необязательно)" type="text" value="${(cond||'').replace(/"/g,'&quot;')}" style="font-size:var(--text-xs);color:var(--color-text-muted)">
    </div>
    <button class="step-edit-del" onclick="this.parentElement.remove();renumberEditSteps()">✕</button>`;
  list.appendChild(row);
}

window.renumberEditSteps = () => {
  $("editRepairStepsList").querySelectorAll(".step-edit-num").forEach((n, i) => { n.textContent = i + 1; });
};

$("addEditStepBtn").addEventListener("click", () => addEditRepairStep());

$("saveEditRepairBtn").addEventListener("click", async () => {
  const name = $("editRepairName").value.trim();
  if (!name) { toast("Введите название", "warning"); return; }
  const steps = [];
  $("editRepairStepsList").querySelectorAll(".step-edit-row").forEach(row => {
    const desc = row.querySelector(".step-edit-desc")?.value.trim();
    const cond = row.querySelector(".step-edit-cond")?.value.trim();
    if (desc) steps.push({ description: desc, condition: cond || null });
  });
  if (steps.length === 0) { toast("Добавьте хотя бы один шаг", "warning"); return; }

  const r = await api(`/api/repairs/${currentEditRepairId}`, "PUT", { name, steps });
  if (r.error) { toast(r.error, "error"); return; }
  toast("Ремонт обновлён", "success");
  closeModal("modalEditRepair");
  loadRepairs();
});

// ══════════════════ INIT ══════════════════

document.addEventListener("DOMContentLoaded", () => {
  initNav();
  loadDiagnoseTab();
});
