#!/usr/bin/env python3
"""
SmartFix — система диагностики и ремонта смартфонов
Глава 4: реализация на Python 3.10 + Flask + SQLite + scikit-learn
"""

import os, json, random, joblib, numpy as np
from flask import Flask, render_template, request, jsonify
import sqlite3
from contextlib import contextmanager

# scikit-learn компоненты (Глава 4.1)
from sklearn.tree import DecisionTreeClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.metrics import balanced_accuracy_score, classification_report

app = Flask(__name__)
DB_PATH = "smartfix.db"
MODEL_PATH = "model.joblib"
ENC_PATH   = "encoder.joblib"

# ─────────────────────────── DB ───────────────────────────

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    """Создаёт таблицы и заполняет начальными данными из курсовой."""
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS characteristics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            unit TEXT,
            value_type TEXT NOT NULL DEFAULT 'real',
            part_id INTEGER NOT NULL,
            FOREIGN KEY (part_id) REFERENCES parts(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS diagnoses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS diagnosis_characteristics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            diagnosis_id INTEGER NOT NULL,
            characteristic_id INTEGER NOT NULL,
            min_val REAL,
            max_val REAL,
            fixed_val REAL,
            FOREIGN KEY (diagnosis_id) REFERENCES diagnoses(id) ON DELETE CASCADE,
            FOREIGN KEY (characteristic_id) REFERENCES characteristics(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS repairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS repair_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repair_id INTEGER NOT NULL,
            step_order INTEGER NOT NULL,
            description TEXT NOT NULL,
            condition TEXT,
            FOREIGN KEY (repair_id) REFERENCES repairs(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS diagnosis_repairs (
            diagnosis_id INTEGER NOT NULL,
            repair_id INTEGER NOT NULL,
            PRIMARY KEY (diagnosis_id, repair_id),
            FOREIGN KEY (diagnosis_id) REFERENCES diagnoses(id) ON DELETE CASCADE,
            FOREIGN KEY (repair_id) REFERENCES repairs(id) ON DELETE CASCADE
        );
        """)

        # Заполнение только если пусто
        count = db.execute("SELECT COUNT(*) FROM parts").fetchone()[0]
        if count > 0:
            return

        # ── Детали (из курсовой) ──
        parts = [
            "Аккумулятор",
            "Процессор",
            "Оперативная память",
            "Модем связи",
            "Стекло дисплейного модуля",
            "Дисплейная матрица"
        ]
        for p in parts:
            db.execute("INSERT INTO parts (name) VALUES (?)", (p,))

        def pid(name):
            return db.execute("SELECT id FROM parts WHERE name=?", (name,)).fetchone()[0]

        # ── Характеристики (из курсовой, с правильными типами) ──
        chars = [
            # name, unit, value_type, part_name
            ("Напряжение аккумулятора",          "В",    "real",    "Аккумулятор"),
            ("Уровень заряда аккумулятора",       "%",    "int",     "Аккумулятор"),
            ("Температура аккумулятора при зарядке","°C", "int",     "Аккумулятор"),
            ("Наличие вздутия аккумулятора",      "",     "binary",  "Аккумулятор"),
            ("Температура процессора",            "°C",   "int",     "Процессор"),
            ("Скорость оперативной памяти",       "МГц",  "int",     "Оперативная память"),
            ("Уровень сигнала модема",            "дБм",  "int",     "Модем связи"),
            ("Площадь трещин на стекле",          "мм²",  "int",     "Стекло дисплейного модуля"),
            ("Отклик дисплейной матрицы",         "мс",   "int",     "Дисплейная матрица"),
            ("Наличие артефактов на экране",      "",     "binary",  "Дисплейная матрица"),
        ]
        for name, unit, vtype, part_name in chars:
            db.execute(
                "INSERT INTO characteristics (name, unit, value_type, part_id) VALUES (?,?,?,?)",
                (name, unit, vtype, pid(part_name))
            )

        def cid(name):
            return db.execute("SELECT id FROM characteristics WHERE name=?", (name,)).fetchone()[0]

        # ── Диагнозы ──
        diagnoses = [
            "Исправен",
            "Разряжен аккумулятор",
            "Неисправен аккумулятор",
            "Перегрев процессора",
            "Слабый сигнал модема",
            "Трещины на стекле",
            "Артефакты на матрице дисплея",
        ]
        for d in diagnoses:
            db.execute("INSERT INTO diagnoses (name) VALUES (?)", (d,))

        def did(name):
            return db.execute("SELECT id FROM diagnoses WHERE name=?", (name,)).fetchone()[0]

        # ── Правила диагнозов (из курсовой, раздел 1.1) ──
        rules = {
            "Исправен": [
                ("Напряжение аккумулятора",          3.7,  4.2,  None),
                ("Уровень заряда аккумулятора",       80,   100,  None),
                ("Температура аккумулятора при зарядке", 20, 45, None),
                ("Наличие вздутия аккумулятора",      None, None, 0),
                ("Температура процессора",            30,   50,   None),
                ("Скорость оперативной памяти",       1600, 3200, None),
                ("Уровень сигнала модема",            -80,  -50,  None),
                ("Площадь трещин на стекле",          None, None, 0),
                ("Отклик дисплейной матрицы",         1,    10,   None),
                ("Наличие артефактов на экране",      None, None, 0),
            ],
            "Разряжен аккумулятор": [
                ("Напряжение аккумулятора",           3.0,  3.4,  None),
                ("Уровень заряда аккумулятора",       0,    10,   None),
                ("Наличие вздутия аккумулятора",      None, None, 0),
            ],
            "Неисправен аккумулятор": [
                ("Напряжение аккумулятора",           0,    3.0,  None),
                ("Уровень заряда аккумулятора",       0,    50,   None),
                ("Наличие вздутия аккумулятора",      0,    1,    None),
                ("Температура аккумулятора при зарядке", 45, 100, None),
            ],
            "Перегрев процессора": [
                ("Температура процессора",            50,   100,  None),
                ("Скорость оперативной памяти",       0,    1600, None),
            ],
            "Слабый сигнал модема": [
                ("Уровень сигнала модема",            -120, -80,  None),
                ("Температура процессора",            30,   50,   None),
            ],
            "Трещины на стекле": [
                ("Площадь трещин на стекле",          0,    500,  None),
                ("Отклик дисплейной матрицы",         10,   100,  None),
            ],
            "Артефакты на матрице дисплея": [
                ("Наличие артефактов на экране",      None, None, 1),
                ("Отклик дисплейной матрицы",         10,   100,  None),
            ],
        }
        for diag_name, char_rules in rules.items():
            d_id = did(diag_name)
            for char_name, min_v, max_v, fixed_v in char_rules:
                c_id = cid(char_name)
                db.execute(
                    "INSERT INTO diagnosis_characteristics (diagnosis_id,characteristic_id,min_val,max_val,fixed_val) VALUES (?,?,?,?,?)",
                    (d_id, c_id, min_v, max_v, fixed_v)
                )

        # ── Ремонты (из курсовой) ──
        repair_data = {
            "Подзарядка аккумулятора": [
                (1, "Подключить зарядное устройство", None),
                (2, "Проверить напряжение и ёмкость", None),
            ],
            "Ремонт перегрева процессора": [
                (1, "Перезагрузить телефон", None),
                (2, "Охладить и проверить под высокой нагрузкой", None),
                (3, "Если перезагрузка не помогла — переустановить ПО и повторить тест", None),
                (4, "Если всё вышеперечисленное не помогло: выключить смартфон, вскрыть, заменить термоинтерфейсы (термопаста и термопрокладки), протестировать под высокой нагрузкой", None),
            ],
            "Ремонт слабого сигнала модема": [
                (1, "Переместиться в зону с лучшим покрытием", None),
                (2, "Перезагрузить телефон", None),
                (3, "Обновить ПО модема", None),
                (4, "Если не помогает — заменить модем", None),
            ],
            "Ремонт трещин на стекле (S ≤ 100 мм²)": [
                (1, "Выключить смартфон", None),
                (2, "Очистить поверхность", None),
                (3, "Нанести защитную плёнку или клей для мелких трещин", "Площадь ≤ 100 мм²"),
                (4, "Включить смартфон", None),
            ],
            "Ремонт трещин на стекле (S > 100 мм²)": [
                (1, "Выключить смартфон", None),
                (2, "Разобрать корпус", None),
                (3, "Заменить стекло", "Площадь > 100 мм²"),
                (4, "Собрать дисплейный модуль", None),
                (5, "Включить смартфон", None),
            ],
            "Ремонт артефактов на матрице дисплея": [
                (1, "Перезагрузить телефон", None),
                (2, "Обновить драйверы дисплея", None),
                (3, "Если не помогает — разобрать и заменить матрицу", None),
                (4, "Собрать модуль", None),
                (5, "Протестировать экран", None),
            ],
            "Замена аккумулятора (без вздутия)": [
                (1, "Выключить смартфон", None),
                (2, "Подключить к зарядному устройству на 1 час", None),
                (3, "Проверить температуру при зарядке, напряжение и ёмкость", None),
                (4, "Если признак выявляет неисправность — перейти к замене аккумулятора", None),
                (5, "Выполнить калибровку аккумулятора", None),
                (6, "Включить смартфон и протестировать", None),
            ],
            "Замена аккумулятора (со вздутием)": [
                (1, "Выключить смартфон", None),
                (2, "Разобрать корпус смартфона", None),
                (3, "Извлечь старый аккумулятор", None),
                (4, "Установить новый аккумулятор", None),
                (5, "Собрать корпус", None),
                (6, "Выполнить калибровку аккумулятора", None),
                (7, "Включить смартфон и протестировать", None),
            ],
        }
        for repair_name, steps in repair_data.items():
            db.execute("INSERT INTO repairs (name) VALUES (?)", (repair_name,))
            r_id = db.execute("SELECT id FROM repairs WHERE name=?", (repair_name,)).fetchone()[0]
            for order, desc, cond in steps:
                db.execute(
                    "INSERT INTO repair_steps (repair_id,step_order,description,condition) VALUES (?,?,?,?)",
                    (r_id, order, desc, cond)
                )

        # ── Связи диагноз ↔ ремонт ──
        links = [
            ("Разряжен аккумулятор",        "Подзарядка аккумулятора"),
            ("Неисправен аккумулятор",      "Замена аккумулятора (без вздутия)"),
            ("Неисправен аккумулятор",      "Замена аккумулятора (со вздутием)"),
            ("Перегрев процессора",         "Ремонт перегрева процессора"),
            ("Слабый сигнал модема",        "Ремонт слабого сигнала модема"),
            ("Трещины на стекле",           "Ремонт трещин на стекле (S ≤ 100 мм²)"),
            ("Трещины на стекле",           "Ремонт трещин на стекле (S > 100 мм²)"),
            ("Артефакты на матрице дисплея","Ремонт артефактов на матрице дисплея"),
        ]
        for diag_name, repair_name in links:
            d_id = did(diag_name)
            r_id = db.execute("SELECT id FROM repairs WHERE name=?", (repair_name,)).fetchone()[0]
            db.execute("INSERT OR IGNORE INTO diagnosis_repairs VALUES (?,?)", (d_id, r_id))

# ─────────────────────── ML (Глава 4.2) ───────────────────────

FEATURE_ORDER = [
    "Напряжение аккумулятора",
    "Уровень заряда аккумулятора",
    "Температура аккумулятора при зарядке",
    "Наличие вздутия аккумулятора",
    "Температура процессора",
    "Скорость оперативной памяти",
    "Уровень сигнала модема",
    "Площадь трещин на стекле",
    "Отклик дисплейной матрицы",
    "Наличие артефактов на экране",
]

# Глобальные границы для генерации датасета (нормальные значения)
FEATURE_GLOBAL_RANGE = {
    "Напряжение аккумулятора":            (0.0,    4.2),
    "Уровень заряда аккумулятора":        (0,      100),
    "Температура аккумулятора при зарядке":(0,     100),
    "Наличие вздутия аккумулятора":       (0,      1),
    "Температура процессора":             (0,      100),
    "Скорость оперативной памяти":        (0,      3200),
    "Уровень сигнала модема":             (-120,   0),
    "Площадь трещин на стекле":           (0,      500),
    "Отклик дисплейной матрицы":          (1,      100),
    "Наличие артефактов на экране":       (0,      1),
}

def load_diagnosis_rules():
    """Загружает правила всех диагнозов из БД."""
    with get_db() as db:
        diagnoses = db.execute("SELECT id, name FROM diagnoses").fetchall()
        result = {}
        for diag in diagnoses:
            rules = db.execute("""
                SELECT c.name, dc.min_val, dc.max_val, dc.fixed_val
                FROM diagnosis_characteristics dc
                JOIN characteristics c ON c.id = dc.characteristic_id
                WHERE dc.diagnosis_id = ?
            """, (diag["id"],)).fetchall()
            result[diag["name"]] = [dict(r) for r in rules]
    return result

def generate_dataset(n_per_class=500):
    """
    Генерирует синтетический датасет на основе правил из БД.
    Формула: x_i ~ U(a_{i,c}, b_{i,c}) — Глава 4.2.1
    """
    rules = load_diagnosis_rules()
    X, y = [], []

    for diag_name, char_rules in rules.items():
        # Собираем диапазоны для каждого признака
        rule_map = {}
        for r in char_rules:
            rule_map[r["name"]] = r

        for _ in range(n_per_class):
            row = []
            for feat in FEATURE_ORDER:
                g_min, g_max = FEATURE_GLOBAL_RANGE.get(feat, (0, 100))
                if feat in rule_map:
                    r = rule_map[feat]
                    if r["fixed_val"] is not None:
                        val = float(r["fixed_val"])
                    else:
                        lo = r["min_val"] if r["min_val"] is not None else g_min
                        hi = r["max_val"] if r["max_val"] is not None else g_max
                        val = round(random.uniform(lo, hi), 3)
                else:
                    # Признак не участвует в этом диагнозе — нормальное значение
                    normal = get_normal_range(feat)
                    val = round(random.uniform(normal[0], normal[1]), 3)
                row.append(val)
            X.append(row)
            y.append(diag_name)

    return np.array(X), np.array(y)

def get_normal_range(feat_name):
    """Нормальные (исправные) диапазоны для генерации признаков вне диагноза."""
    normals = {
        "Напряжение аккумулятора":            (3.7,   4.2),
        "Уровень заряда аккумулятора":        (80,    100),
        "Температура аккумулятора при зарядке":(20,   45),
        "Наличие вздутия аккумулятора":       (0,     0),
        "Температура процессора":             (30,    50),
        "Скорость оперативной памяти":        (1600,  3200),
        "Уровень сигнала модема":             (-80,   -50),
        "Площадь трещин на стекле":           (0,     0),
        "Отклик дисплейной матрицы":          (1,     10),
        "Наличие артефактов на экране":       (0,     0),
    }
    return normals.get(feat_name, (0, 100))

def train_model():
    """
    Обучает DecisionTreeClassifier с GridSearchCV (Глава 4.2.2).
    Возвращает словарь с метриками.
    """
    X, y = generate_dataset(n_per_class=500)

    enc = LabelEncoder()
    y_enc = enc.fit_transform(y)

    # Разбивка 80/20, стратифицированная (Глава 4.2)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y_enc, test_size=0.2, random_state=42, stratify=y_enc
    )

    # Пространство гиперпараметров (Таблица 2, Глава 4.2)
    param_grid = {
        "max_depth":         [5, 10, 15, 20, None],
        "min_samples_split": [2, 3, 5, 10],
        "min_samples_leaf":  [1, 2, 3, 5],
        "criterion":         ["gini", "entropy"],
        "max_features":      ["sqrt", "log2", None],
        "class_weight":      ["balanced", None],
    }

    base_clf = DecisionTreeClassifier(random_state=42)
    grid = GridSearchCV(
        base_clf, param_grid,
        cv=5, scoring="balanced_accuracy",
        n_jobs=-1, verbose=0
    )
    grid.fit(X_train, y_train)

    best_clf = grid.best_estimator_
    y_pred = best_clf.predict(X_test)

    ba = balanced_accuracy_score(y_test, y_pred)
    report = classification_report(
        y_test, y_pred,
        target_names=enc.classes_,
        output_dict=True
    )

    joblib.dump(best_clf, MODEL_PATH)
    joblib.dump(enc, ENC_PATH)

    # Сохраняем хэш состояния БЗ на момент обучения
    kb_hash = get_kb_hash()
    joblib.dump(kb_hash, "kb_hash.joblib")

    return {
        "balanced_accuracy": round(ba, 4),
        "best_params": grid.best_params_,
        "report": report,
        "n_train": len(X_train),
        "n_test": len(X_test),
    }

def get_kb_hash():
    """Хэш текущего состояния базы знаний (для проверки актуальности модели)."""
    import hashlib
    rules = load_diagnosis_rules()
    s = str(sorted([(k, str(sorted(str(v) for v in vals))) for k, vals in rules.items()]))
    return hashlib.md5(s.encode()).hexdigest()

def load_ml_model():
    if os.path.exists(MODEL_PATH) and os.path.exists(ENC_PATH):
        return joblib.load(MODEL_PATH), joblib.load(ENC_PATH)
    return None, None

# Средние нормальные значения для заполнения пропущенных признаков при инференсе
FEATURE_NORMAL_DEFAULTS = {
    "Напряжение аккумулятора":             3.95,   # середина [3.7; 4.2]
    "Уровень заряда аккумулятора":         90,     # середина [80; 100]
    "Температура аккумулятора при зарядке": 32,    # середина [20; 45]
    "Наличие вздутия аккумулятора":        0,      # норма = 0
    "Температура процессора":              40,     # середина [30; 50]
    "Скорость оперативной памяти":         2400,   # середина [1600; 3200]
    "Уровень сигнала модема":              -65,    # середина [-80; -50]
    "Площадь трещин на стекле":            0,      # норма = 0
    "Отклик дисплейной матрицы":           5,      # середина [1; 10]
    "Наличие артефактов на экране":        0,      # норма = 0
}

def ml_predict(values_dict):
    """
    Возвращает список (diag_name, probability) отсортированный по убыванию.

    Пропущенные признаки заполняются нормальными значениями (середина исправного
    диапазона), а не нулями — иначе модель будет видеть аномалии там, где их нет.
    """
    clf, enc = load_ml_model()
    if clf is None:
        return []
    row = []
    for feat in FEATURE_ORDER:
        if feat in values_dict and values_dict[feat] is not None and values_dict[feat] != "":
            row.append(float(values_dict[feat]))
        else:
            # Заполняем нормальным значением, чтобы не смещать предсказание
            row.append(float(FEATURE_NORMAL_DEFAULTS.get(feat, 0)))
    X = np.array([row])
    proba = clf.predict_proba(X)[0]
    classes = enc.classes_
    result = sorted(zip(classes, proba), key=lambda x: -x[1])
    return [(cls, round(float(p), 4)) for cls, p in result]

# ───────────────────── Экспертная система ─────────────────────

def expert_diagnose(values_dict):
    """
    Прямое сопоставление с правилами БД (экспертная система).

    Логика:
    - Учитываются только ВВЕДЁННЫЕ пользователем характеристики.
    - Если хотя бы одно фиксированное правило (fixed_val) нарушено → диагноз исключается.
    - match_pct = доля введённых характеристик, удовлетворяющих правилам диагноза.
    - Диагнозы с match_pct >= 0.5 попадают в кандидаты.
    """
    rules = load_diagnosis_rules()
    results = []

    for diag_name, char_rules in rules.items():
        if not char_rules:
            continue

        matched = 0
        total = 0
        hard_fail = False  # жёсткое нарушение фиксированного правила

        for r in char_rules:
            feat = r["name"]
            # Пропускаем признаки, которые пользователь не вводил
            if feat not in values_dict or values_dict[feat] is None or values_dict[feat] == "":
                continue

            val = float(values_dict[feat])
            total += 1

            if r["fixed_val"] is not None:
                # Фиксированное правило: точное совпадение обязательно
                if abs(val - r["fixed_val"]) < 1e-9:
                    matched += 1
                else:
                    # Нарушение фиксированного правила — диагноз исключается
                    hard_fail = True
                    break
            else:
                lo = r["min_val"] if r["min_val"] is not None else -1e18
                hi = r["max_val"] if r["max_val"] is not None else 1e18
                if lo <= val <= hi:
                    matched += 1

        if hard_fail:
            continue  # этот диагноз полностью исключён

        if total > 0:
            pct = matched / total
            if pct >= 0.5:
                results.append((diag_name, round(pct, 4), matched, total))

    results.sort(key=lambda x: -x[1])
    return results

# ─────────────────────── Гибридная диагностика ────────────────────────

def hybrid_diagnose(values_dict):
    """
    Вариант 2: гибридный приоритетный механизм (Глава 4 курсовой).
    1. Экспертная система → список кандидатов
    2. Если кандидат один → используется напрямую
    3. Если кандидатов несколько → ML ранжирует, выбирается наиболее вероятный
    4. Если экспертная система ничего не нашла → только ML
    """
    expert_candidates = expert_diagnose(values_dict)
    ml_results = ml_predict(values_dict)

    if len(expert_candidates) == 1:
        final = expert_candidates[0][0]
        method = "expert"
    elif len(expert_candidates) > 1:
        # ML выбирает из кандидатов экспертной системы
        expert_names = {c[0] for c in expert_candidates}
        ml_filtered = [(n, p) for n, p in ml_results if n in expert_names]
        if ml_filtered:
            final = ml_filtered[0][0]
        else:
            final = expert_candidates[0][0]
        method = "hybrid"
    else:
        # Только ML
        final = ml_results[0][0] if ml_results else None
        method = "ml_only"

    return {
        "final_diagnosis": final,
        "method": method,
        "expert_candidates": [
            {"name": n, "match_pct": p, "matched": m, "total": t}
            for n, p, m, t in expert_candidates
        ],
        "ml_ranking": [{"name": n, "probability": p} for n, p in ml_results[:5]],
    }

# ─────────────────────── API Routes ──────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/characteristics")
def api_characteristics():
    with get_db() as db:
        rows = db.execute("""
            SELECT c.id, c.name, c.unit, c.value_type, p.name AS part_name
            FROM characteristics c
            JOIN parts p ON p.id = c.part_id
            ORDER BY p.id, c.id
        """).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/parts")
def api_parts():
    with get_db() as db:
        rows = db.execute("SELECT * FROM parts ORDER BY id").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/parts", methods=["POST"])
def add_part():
    data = request.json
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Название не может быть пустым"}), 400
    try:
        with get_db() as db:
            db.execute("INSERT INTO parts (name) VALUES (?)", (name,))
        return jsonify({"ok": True})
    except:
        return jsonify({"error": "Деталь с таким названием уже существует"}), 400

@app.route("/api/parts/<int:pid>", methods=["DELETE"])
def delete_part(pid):
    with get_db() as db:
        db.execute("DELETE FROM parts WHERE id=?", (pid,))
    return jsonify({"ok": True})

@app.route("/api/characteristics", methods=["POST"])
def add_characteristic():
    data = request.json
    name     = data.get("name", "").strip()
    unit     = data.get("unit", "").strip()
    vtype    = data.get("value_type", "real")
    part_id  = data.get("part_id")
    if not name or not part_id:
        return jsonify({"error": "Название и деталь обязательны"}), 400
    # Проверка дубликата в рамках детали
    with get_db() as db:
        exists = db.execute(
            "SELECT id FROM characteristics WHERE name=? AND part_id=?", (name, part_id)
        ).fetchone()
        if exists:
            return jsonify({"error": "Характеристика с таким названием уже есть у этой детали"}), 400
        db.execute(
            "INSERT INTO characteristics (name, unit, value_type, part_id) VALUES (?,?,?,?)",
            (name, unit, vtype, part_id)
        )
    return jsonify({"ok": True})

@app.route("/api/characteristics/<int:cid>", methods=["DELETE"])
def delete_characteristic(cid):
    with get_db() as db:
        db.execute("DELETE FROM characteristics WHERE id=?", (cid,))
    return jsonify({"ok": True})

@app.route("/api/diagnoses")
def api_diagnoses():
    with get_db() as db:
        rows = db.execute("SELECT * FROM diagnoses ORDER BY id").fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/diagnoses", methods=["POST"])
def add_diagnosis():
    data = request.json
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Название не может быть пустым"}), 400
    try:
        with get_db() as db:
            db.execute("INSERT INTO diagnoses (name) VALUES (?)", (name,))
        return jsonify({"ok": True})
    except:
        return jsonify({"error": "Диагноз с таким названием уже существует"}), 400

@app.route("/api/diagnoses/<int:did>", methods=["DELETE"])
def delete_diagnosis(did):
    with get_db() as db:
        db.execute("DELETE FROM diagnoses WHERE id=?", (did,))
    return jsonify({"ok": True})

@app.route("/api/diagnoses/<int:did>/characteristics")
def get_diag_chars(did):
    with get_db() as db:
        rows = db.execute("""
            SELECT dc.id, c.name, c.unit, dc.min_val, dc.max_val, dc.fixed_val
            FROM diagnosis_characteristics dc
            JOIN characteristics c ON c.id = dc.characteristic_id
            WHERE dc.diagnosis_id = ?
        """, (did,)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/diagnoses/<int:did>/characteristics", methods=["POST"])
def add_diag_char(did):
    data = request.json
    char_id   = data.get("characteristic_id")
    min_val   = data.get("min_val")
    max_val   = data.get("max_val")
    fixed_val = data.get("fixed_val")

    # Валидация диапазона
    if min_val is not None and max_val is not None:
        if float(min_val) >= float(max_val):
            return jsonify({"error": "Минимальное значение должно быть меньше максимального"}), 400

    with get_db() as db:
        exists = db.execute(
            "SELECT id FROM diagnosis_characteristics WHERE diagnosis_id=? AND characteristic_id=?",
            (did, char_id)
        ).fetchone()
        if exists:
            return jsonify({"error": "Характеристика уже добавлена к этому диагнозу"}), 400
        db.execute(
            "INSERT INTO diagnosis_characteristics (diagnosis_id,characteristic_id,min_val,max_val,fixed_val) VALUES (?,?,?,?,?)",
            (did, char_id, min_val, max_val, fixed_val)
        )
    return jsonify({"ok": True})

@app.route("/api/diagnoses/<int:did>/characteristics/<int:dcid>", methods=["DELETE"])
def delete_diag_char(did, dcid):
    with get_db() as db:
        db.execute("DELETE FROM diagnosis_characteristics WHERE id=? AND diagnosis_id=?", (dcid, did))
    return jsonify({"ok": True})

@app.route("/api/repairs")
def api_repairs():
    with get_db() as db:
        repairs = db.execute("SELECT * FROM repairs ORDER BY id").fetchall()
        result = []
        for rep in repairs:
            steps = db.execute(
                "SELECT * FROM repair_steps WHERE repair_id=? ORDER BY step_order",
                (rep["id"],)
            ).fetchall()
            result.append({**dict(rep), "steps": [dict(s) for s in steps]})
    return jsonify(result)

@app.route("/api/repairs", methods=["POST"])
def add_repair():
    data = request.json
    name = data.get("name", "").strip()
    steps = data.get("steps", [])
    if not name:
        return jsonify({"error": "Название не может быть пустым"}), 400
    try:
        with get_db() as db:
            db.execute("INSERT INTO repairs (name) VALUES (?)", (name,))
            r_id = db.execute("SELECT id FROM repairs WHERE name=?", (name,)).fetchone()[0]
            for i, step in enumerate(steps, 1):
                db.execute(
                    "INSERT INTO repair_steps (repair_id,step_order,description,condition) VALUES (?,?,?,?)",
                    (r_id, i, step.get("description",""), step.get("condition"))
                )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route("/api/repairs/<int:rid>", methods=["DELETE"])
def delete_repair(rid):
    with get_db() as db:
        db.execute("DELETE FROM repair_steps WHERE repair_id=?", (rid,))
        db.execute("DELETE FROM diagnosis_repairs WHERE repair_id=?", (rid,))
        db.execute("DELETE FROM repairs WHERE id=?", (rid,))
    return jsonify({"ok": True})

@app.route("/api/repairs/<int:rid>", methods=["PUT"])
def update_repair(rid):
    """Редактирование названия и шагов ремонта."""
    data = request.json
    name  = data.get("name", "").strip()
    steps = data.get("steps", [])
    if not name:
        return jsonify({"error": "Название не может быть пустым"}), 400
    with get_db() as db:
        # Проверяем дубликат названия (исключая текущий ремонт)
        dup = db.execute("SELECT id FROM repairs WHERE name=? AND id!=?", (name, rid)).fetchone()
        if dup:
            return jsonify({"error": "Ремонт с таким названием уже существует"}), 400
        db.execute("UPDATE repairs SET name=? WHERE id=?", (name, rid))
        db.execute("DELETE FROM repair_steps WHERE repair_id=?", (rid,))
        for i, step in enumerate(steps, 1):
            db.execute(
                "INSERT INTO repair_steps (repair_id,step_order,description,condition) VALUES (?,?,?,?)",
                (rid, i, step.get("description", ""), step.get("condition"))
            )
    return jsonify({"ok": True})

@app.route("/api/diagnoses/<int:did>/repairs")
def get_diag_repairs(did):
    with get_db() as db:
        rows = db.execute("""
            SELECT r.id, r.name FROM diagnosis_repairs dr
            JOIN repairs r ON r.id = dr.repair_id
            WHERE dr.diagnosis_id = ?
        """, (did,)).fetchall()
    return jsonify([dict(r) for r in rows])

@app.route("/api/diagnoses/<int:did>/repairs", methods=["POST"])
def add_diag_repair(did):
    data = request.json
    rid = data.get("repair_id")
    if not rid:
        return jsonify({"error": "Не указан ремонт"}), 400
    with get_db() as db:
        db.execute("INSERT OR IGNORE INTO diagnosis_repairs VALUES (?,?)", (did, rid))
    return jsonify({"ok": True})

@app.route("/api/diagnoses/<int:did>/repairs/<int:rid>", methods=["DELETE"])
def delete_diag_repair(did, rid):
    with get_db() as db:
        db.execute("DELETE FROM diagnosis_repairs WHERE diagnosis_id=? AND repair_id=?", (did, rid))
    return jsonify({"ok": True})

@app.route("/api/diagnose", methods=["POST"])
def api_diagnose():
    """Основной эндпоинт гибридной диагностики."""
    values = request.json  # {char_name: value, ...}
    result = hybrid_diagnose(values)

    # Подгружаем ремонты для финального диагноза
    if result["final_diagnosis"]:
        with get_db() as db:
            diag = db.execute(
                "SELECT id FROM diagnoses WHERE name=?", (result["final_diagnosis"],)
            ).fetchone()
            if diag:
                repairs = db.execute("""
                    SELECT r.id, r.name FROM diagnosis_repairs dr
                    JOIN repairs r ON r.id = dr.repair_id
                    WHERE dr.diagnosis_id = ?
                """, (diag["id"],)).fetchall()
                result["repairs"] = []
                for rep in repairs:
                    steps = db.execute(
                        "SELECT * FROM repair_steps WHERE repair_id=? ORDER BY step_order",
                        (rep["id"],)
                    ).fetchall()
                    result["repairs"].append({
                        "id": rep["id"],
                        "name": rep["name"],
                        "steps": [dict(s) for s in steps]
                    })

    return jsonify(result)

@app.route("/api/train", methods=["POST"])
def api_train():
    """Запуск обучения ML-модели."""
    try:
        metrics = train_model()
        return jsonify({"ok": True, **metrics})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/model/status")
def api_model_status():
    clf, enc = load_ml_model()
    if clf is None:
        return jsonify({"trained": False, "stale": False})
    # Проверяем актуальность: сравниваем хэш БЗ
    stale = False
    try:
        if os.path.exists("kb_hash.joblib"):
            saved_hash = joblib.load("kb_hash.joblib")
            stale = (saved_hash != get_kb_hash())
        else:
            stale = True  # хэш не сохранён — считаем устаревшей
    except:
        stale = True
    return jsonify({"trained": True, "stale": stale})

@app.route("/api/validate_kb")
def validate_kb():
    """Проверка целостности базы знаний."""
    with get_db() as db:
        diagnoses = db.execute("SELECT id, name FROM diagnoses").fetchall()
        issues = []
        for d in diagnoses:
            chars = db.execute(
                "SELECT id FROM diagnosis_characteristics WHERE diagnosis_id=?", (d["id"],)
            ).fetchall()
            if not chars:
                issues.append(f"Диагноз «{d['name']}» не имеет ни одной характеристики")
        if issues:
            return jsonify({"ok": False, "issues": issues})
    return jsonify({"ok": True, "message": "База знаний корректна!"})

# ─────────────────── Ollama API (Глава 4.1) ────────────────────

@app.route("/api/ollama/models")
def ollama_models():
    import urllib.request
    try:
        req = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
        data = json.loads(req.read())
        return jsonify({"models": [m["name"] for m in data.get("models", [])]})
    except:
        return jsonify({"models": [], "error": "Ollama недоступна"})

@app.route("/api/ollama/verify", methods=["POST"])
def ollama_verify():
    import urllib.request
    data = request.json
    model    = data.get("model")
    diagnosis = data.get("diagnosis")
    values   = data.get("values", {})
    steps    = data.get("steps", [])

    prompt = f"""Проверь диагноз смартфона:
Диагноз: {diagnosis}
Введённые характеристики: {json.dumps(values, ensure_ascii=False)}
Шаги ремонта: {json.dumps(steps, ensure_ascii=False)}

Дай заключение по четырём пунктам:
1. Корректность диагноза
2. Полнота шагов ремонта
3. Возможные риски
4. Итоговая рекомендация"""

    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        resp = urllib.request.urlopen(req, timeout=60)
        result = json.loads(resp.read())
        return jsonify({"response": result.get("response", "")})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    init_db()
    # Обучаем модель при первом запуске
    clf, _ = load_ml_model()
    if clf is None:
        print("⚙️  Первый запуск: обучение ML-модели...")
        metrics = train_model()
        print(f"✅ Модель обучена. Balanced accuracy: {metrics['balanced_accuracy']}")
    app.run(debug=True, port=5000)
