"""
SmartFix — Flask backend
Зависимости: pip install flask flask-cors requests
"""
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import sqlite3, json, requests, os

app = Flask(__name__)
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), 'smartfix.db')
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3')

# ==================== DATABASE ====================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS characteristics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            unit TEXT DEFAULT '',
            min_val REAL NOT NULL,
            max_val REAL NOT NULL,
            normal_min REAL NOT NULL,
            normal_max REAL NOT NULL,
            value_type TEXT DEFAULT 'float'
        );
        CREATE TABLE IF NOT EXISTS part_characteristics (
            part_id INTEGER REFERENCES parts(id) ON DELETE CASCADE,
            char_id INTEGER REFERENCES characteristics(id) ON DELETE CASCADE,
            PRIMARY KEY (part_id, char_id)
        );
        CREATE TABLE IF NOT EXISTS repairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS repair_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repair_id INTEGER REFERENCES repairs(id) ON DELETE CASCADE,
            step_order INTEGER NOT NULL,
            description TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS diagnoses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            repair_id INTEGER REFERENCES repairs(id)
        );
        CREATE TABLE IF NOT EXISTS diagnosis_characteristics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            diagnosis_id INTEGER REFERENCES diagnoses(id) ON DELETE CASCADE,
            char_id INTEGER REFERENCES characteristics(id) ON DELETE CASCADE,
            range_min REAL,
            range_max REAL,
            exclusive_min INTEGER DEFAULT 0,
            exclusive_max INTEGER DEFAULT 0,
            exact_val REAL
        );
        """)
        db.commit()
    seed_initial_data()

def seed_initial_data():
    """Заполнить БД начальными знаниями из курсовой, если таблицы пустые."""
    with get_db() as db:
        if db.execute("SELECT COUNT(*) FROM parts").fetchone()[0] > 0:
            return  # уже заполнено

        # ---- Детали ----
        parts = ['Аккумулятор', 'Материнская плата', 'Дисплейный модуль']
        for p in parts:
            db.execute("INSERT INTO parts(name) VALUES(?)", (p,))

        # ---- Характеристики ----
        chars = [
            ('напряжение аккумулятора',             'В',    0,    5,    3.7,  4.2,  'float'),
            ('уровень заряда аккумулятора',          '%',    0,    100,  80,   100,  'int'),
            ('наличие вздутия аккумулятора',         '0/1',  0,    1,    0,    0,    'int'),
            ('температура аккумулятора при зарядке', '°C',   0,    100,  20,   45,   'float'),
            ('температура процессора',               '°C',   0,    100,  30,   50,   'float'),
            ('скорость оперативной памяти',          'МГц',  0,    4000, 1600, 3200, 'int'),
            ('уровень сигнала модема',               'дБм',  -120, -40,  -80,  -50,  'float'),
            ('площадь трещин на стекле',             'мм²',  0,    1000, 0,    0,    'int'),
            ('отклик дисплейной матрицы',            'мс',   0,    200,  1,    10,   'float'),
            ('наличие артефактов на экране',         '0/1',  0,    1,    0,    0,    'int'),
        ]
        for c in chars:
            db.execute(
                "INSERT INTO characteristics(name,unit,min_val,max_val,normal_min,normal_max,value_type) VALUES(?,?,?,?,?,?,?)", c)

        # ---- Связи деталь-характеристика ----
        def pid(name): return db.execute("SELECT id FROM parts WHERE name=?", (name,)).fetchone()[0]
        def cid(name): return db.execute("SELECT id FROM characteristics WHERE name=?", (name,)).fetchone()[0]

        pc = {
            'Аккумулятор': ['напряжение аккумулятора','уровень заряда аккумулятора',
                             'наличие вздутия аккумулятора','температура аккумулятора при зарядке'],
            'Материнская плата': ['температура процессора','скорость оперативной памяти','уровень сигнала модема'],
            'Дисплейный модуль': ['площадь трещин на стекле','отклик дисплейной матрицы','наличие артефактов на экране'],
        }
        for part, clist in pc.items():
            for ch in clist:
                db.execute("INSERT INTO part_characteristics VALUES(?,?)", (pid(part), cid(ch)))

        # ---- Ремонты ----
        repairs = {
            'Ремонт не требуется': [],
            'Зарядить аккумулятор': [
                'Подключить зарядное устройство',
                'Проверить напряжение и ёмкость после зарядки',
            ],
            'Заменить аккумулятор': [
                'Выключить смартфон',
                'Разобрать корпус смартфона',
                'Извлечь старый аккумулятор',
                'Установить новый аккумулятор',
                'Собрать корпус',
                'Выполнить калибровку аккумулятора',
                'Включить смартфон и протестировать',
            ],
            'Устранить перегрев процессора': [
                'Перезагрузить телефон',
                'Охладить устройство и проверить под нагрузкой',
                'Переустановить ПО при необходимости',
                'Вскрыть корпус и заменить термоинтерфейсы (термопаста/прокладки)',
                'Провести тестирование под высокой нагрузкой',
            ],
            'Устранить слабый сигнал модема': [
                'Переместиться в зону лучшего покрытия',
                'Перезагрузить телефон',
                'Обновить ПО модема',
                'При необходимости заменить модем',
            ],
            'Устранить трещины на стекле': [
                'Выключить смартфон',
                'Очистить поверхность экрана',
                'Если трещин ≤ 100 мм²: нанести защитную плёнку или клей для мелких трещин',
                'Если трещин > 100 мм²: разобрать корпус, заменить стекло, собрать дисплейный модуль',
                'Включить смартфон и протестировать',
            ],
            'Устранить артефакты дисплея': [
                'Перезагрузить телефон',
                'Обновить драйверы дисплея',
                'Разобрать и заменить матрицу дисплея',
                'Собрать модуль',
                'Протестировать экран',
            ],
        }
        for rname, steps in repairs.items():
            db.execute("INSERT INTO repairs(name) VALUES(?)", (rname,))
            rid = db.execute("SELECT id FROM repairs WHERE name=?", (rname,)).fetchone()[0]
            for i, step in enumerate(steps, 1):
                db.execute("INSERT INTO repair_steps(repair_id,step_order,description) VALUES(?,?,?)", (rid, i, step))

        # ---- Вспомогательная функция ----
        def rid(name): return db.execute("SELECT id FROM repairs WHERE name=?", (name,)).fetchone()[0]

        # ---- Диагнозы ----
        diagnoses = [
            ('Исправен',                   rid('Ремонт не требуется')),
            ('Разряжен аккумулятор',       rid('Зарядить аккумулятор')),
            ('Неисправен аккумулятор',     rid('Заменить аккумулятор')),
            ('Перегрев процессора',        rid('Устранить перегрев процессора')),
            ('Слабый сигнал модема',       rid('Устранить слабый сигнал модема')),
            ('Трещины на стекле',          rid('Устранить трещины на стекле')),
            ('Артефакты на матрице дисплея', rid('Устранить артефакты дисплея')),
        ]
        for dname, r_id in diagnoses:
            db.execute("INSERT INTO diagnoses(name,repair_id) VALUES(?,?)", (dname, r_id))

        def did(name): return db.execute("SELECT id FROM diagnoses WHERE name=?", (name,)).fetchone()[0]

        # ---- Характеристики диагнозов (ЛОГИКА ИЗ КУРСОВОЙ) ----
        # ВАЖНО: диапазоны строго соответствуют курсовой работе
        # exclusive_min/max: 1 = скобка (, 0 = скобка [
        dc = [
            # Разряжен аккумулятор
            ('Разряжен аккумулятор', 'напряжение аккумулятора',          3.0,  3.4,  0, 1, None),
            ('Разряжен аккумулятор', 'уровень заряда аккумулятора',      0,    10,   0, 1, None),
            ('Разряжен аккумулятор', 'наличие вздутия аккумулятора',     None, None, 0, 0, 0),
            # Неисправен аккумулятор
            ('Неисправен аккумулятор', 'напряжение аккумулятора',        0,    3.0,  0, 1, None),
            ('Неисправен аккумулятор', 'уровень заряда аккумулятора',    0,    50,   0, 1, None),
            ('Неисправен аккумулятор', 'наличие вздутия аккумулятора',   0,    1,    0, 0, None),  # может быть 0 или 1
            ('Неисправен аккумулятор', 'температура аккумулятора при зарядке', 45, 100, 1, 0, None),
            # Перегрев процессора
            ('Перегрев процессора', 'температура процессора',            50,   100,  1, 0, None),
            ('Перегрев процессора', 'скорость оперативной памяти',       0,    1600, 0, 1, None),
            # Слабый сигнал модема
            ('Слабый сигнал модема', 'уровень сигнала модема',           -120, -80,  0, 1, None),
            ('Слабый сигнал модема', 'температура процессора',           30,   50,   0, 0, None),
            # Трещины на стекле
            ('Трещины на стекле', 'площадь трещин на стекле',            0,    500,  1, 0, None),
            ('Трещины на стекле', 'отклик дисплейной матрицы',           10,   100,  1, 0, None),
            # Артефакты на матрице дисплея
            ('Артефакты на матрице дисплея', 'наличие артефактов на экране', None, None, 0, 0, 1),
            ('Артефакты на матрице дисплея', 'отклик дисплейной матрицы', 10,  100,  1, 0, None),
        ]
        for dname, cname, rmin, rmax, exc_min, exc_max, exact in dc:
            d_id = did(dname)
            c_id = cid(cname)
            db.execute(
                "INSERT INTO diagnosis_characteristics(diagnosis_id,char_id,range_min,range_max,exclusive_min,exclusive_max,exact_val) VALUES(?,?,?,?,?,?,?)",
                (d_id, c_id, rmin, rmax, exc_min, exc_max, exact)
            )
        db.commit()

# ==================== HELPERS ====================
def get_kb_data():
    with get_db() as db:
        # Characteristics dict
        chars_rows = db.execute("SELECT * FROM characteristics").fetchall()
        chars = {r['name']: dict(r) for r in chars_rows}

        # Parts
        parts_rows = db.execute("SELECT p.*, GROUP_CONCAT(c.name, '||') as char_names FROM parts p "
                                "LEFT JOIN part_characteristics pc ON pc.part_id=p.id "
                                "LEFT JOIN characteristics c ON c.id=pc.char_id "
                                "GROUP BY p.id").fetchall()
        parts = []
        for p in parts_rows:
            parts.append({'id': p['id'], 'name': p['name'],
                          'characteristics': [x for x in (p['char_names'] or '').split('||') if x]})

        # Repairs with steps
        repairs_rows = db.execute("SELECT r.id, r.name, GROUP_CONCAT(rs.description, '||') as steps "
                                  "FROM repairs r LEFT JOIN repair_steps rs ON rs.repair_id=r.id "
                                  "GROUP BY r.id ORDER BY rs.step_order").fetchall()
        repairs = []
        for r in repairs_rows:
            repairs.append({'id': r['id'], 'name': r['name'],
                            'steps': [s for s in (r['steps'] or '').split('||') if s]})

        # Diagnoses with characteristics
        diag_rows = db.execute("SELECT d.id, d.name, rep.name as repair_name FROM diagnoses d "
                               "LEFT JOIN repairs rep ON rep.id=d.repair_id").fetchall()
        diagnoses = []
        for d in diag_rows:
            dc_rows = db.execute(
                "SELECT c.name as char_name, dc.range_min, dc.range_max, dc.exclusive_min, dc.exclusive_max, dc.exact_val "
                "FROM diagnosis_characteristics dc JOIN characteristics c ON c.id=dc.char_id "
                "WHERE dc.diagnosis_id=?", (d['id'],)).fetchall()
            diagnoses.append({
                'id': d['id'], 'name': d['name'], 'repair_name': d['repair_name'],
                'characteristics': [dict(r) for r in dc_rows]
            })

        return {'characteristics': chars, 'parts': parts, 'repairs': repairs, 'diagnoses': diagnoses}

# ==================== ROUTES ====================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/kb')
def api_kb():
    return jsonify(get_kb_data())

# --- Solve ---
@app.route('/api/solve', methods=['POST'])
def api_solve():
    data = request.json
    diag_id = data.get('diagnosis_id')
    values = data.get('values', {})

    with get_db() as db:
        diag = db.execute("SELECT d.*, r.name as repair_name FROM diagnoses d LEFT JOIN repairs r ON r.id=d.repair_id WHERE d.id=?", (diag_id,)).fetchone()
        if not diag:
            return jsonify({'error': 'Диагноз не найден'}), 404

        dc_rows = db.execute(
            "SELECT c.name as char_name, c.unit, dc.range_min, dc.range_max, dc.exclusive_min, dc.exclusive_max, dc.exact_val "
            "FROM diagnosis_characteristics dc JOIN characteristics c ON c.id=dc.char_id WHERE dc.diagnosis_id=?", (diag_id,)).fetchall()

        steps_rows = db.execute(
            "SELECT rs.description FROM repair_steps rs JOIN repairs r ON r.id=rs.repair_id "
            "WHERE r.name=? ORDER BY rs.step_order", (diag['repair_name'],)).fetchall()

    steps = [r['description'] for r in steps_rows]
    checks = []

    for dc in dc_rows:
        val = values.get(dc['char_name'])
        if val is None:
            continue
        val = float(val)

        # Проверка попадания в диапазон диагноза
        if dc['exact_val'] is not None:
            ok = abs(val - dc['exact_val']) < 0.0001
            expected = f"= {dc['exact_val']}"
        else:
            lo = '(' if dc['exclusive_min'] else '['
            hi = ')' if dc['exclusive_max'] else ']'
            ok_min = val > dc['range_min'] if dc['exclusive_min'] else val >= dc['range_min']
            ok_max = val < dc['range_max'] if dc['exclusive_max'] else val <= dc['range_max']
            ok = ok_min and ok_max
            expected = f"{lo}{dc['range_min']}; {dc['range_max']}{hi}"

        checks.append({'name': dc['char_name'], 'value': val, 'unit': dc['unit'], 'expected': expected, 'ok': ok})

    matched = sum(1 for c in checks if c['ok'])
    match_pct = round(matched / len(checks) * 100) if checks else 100

    result = {
        'diagnosis': diag['name'],
        'repair': diag['repair_name'],
        'steps': steps,
        'checks': checks,
        'match_pct': match_pct,
        'values': values,
    }
    return jsonify(result)

# --- Ollama ---
@app.route('/api/ollama/status')
def ollama_status():
    try:
        r = requests.get(f'{OLLAMA_URL}/api/tags', timeout=3)
        models = r.json().get('models', [])
        model = next((m['name'] for m in models if OLLAMA_MODEL in m['name']), (models[0]['name'] if models else None))
        return jsonify({'online': True, 'model': model})
    except Exception as e:
        return jsonify({'online': False, 'error': str(e)})

@app.route('/api/ollama/check', methods=['POST'])
def ollama_check():
    data = request.json
    diagnosis = data.get('diagnosis', '')
    repair = data.get('repair', '')
    checks = data.get('checks', [])
    steps = data.get('steps', [])
    match_pct = data.get('match_pct', 0)

    checks_str = "\n".join(
        f"  - {c['name']}: {c['value']} {c.get('unit','')} (ожидалось {c['expected']}) — {'✓' if c['ok'] else '✗'}"
        for c in checks
    )
    steps_str = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps))

    prompt = f"""Ты — эксперт по ремонту смартфонов. Проверь результат автоматической диагностики и дай профессиональный отзыв на русском языке.

РЕЗУЛЬТАТ ДИАГНОСТИКИ:
- Диагноз: {diagnosis}
- Ремонт: {repair}
- Совпадение характеристик с диагнозом: {match_pct}%

ВВЕДЁННЫЕ ХАРАКТЕРИСТИКИ:
{checks_str}

ПРЕДЛОЖЕННЫЕ ШАГИ РЕМОНТА:
{steps_str}

Ответь на следующие вопросы:
1. Верен ли диагноз с учётом введённых значений характеристик? Есть ли противоречия?
2. Полна ли предложенная последовательность ремонта? Что можно добавить?
3. Есть ли риски при выполнении данного ремонта, о которых стоит предупредить?
4. Итоговая рекомендация.

Отвечай структурированно и кратко."""

    try:
        r = requests.post(f'{OLLAMA_URL}/api/generate',
            json={'model': OLLAMA_MODEL, 'prompt': prompt, 'stream': False},
            timeout=120)
        result = r.json()
        return jsonify({'response': result.get('response', 'Нет ответа от модели')})
    except requests.exceptions.ConnectionError:
        return jsonify({'error': f'Ollama недоступна по адресу {OLLAMA_URL}. Запустите: ollama serve'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# --- CRUD Parts ---
@app.route('/api/parts', methods=['POST'])
def add_part():
    d = request.json
    with get_db() as db:
        db.execute("INSERT INTO parts(name) VALUES(?)", (d['name'],))
        db.commit()
    return jsonify({'ok': True})

@app.route('/api/parts/<int:pid>', methods=['DELETE'])
def del_part(pid):
    with get_db() as db:
        db.execute("DELETE FROM parts WHERE id=?", (pid,)); db.commit()
    return jsonify({'ok': True})

# --- CRUD Characteristics ---
@app.route('/api/characteristics', methods=['POST'])
def add_char():
    d = request.json
    with get_db() as db:
        db.execute("INSERT INTO characteristics(name,unit,min_val,max_val,normal_min,normal_max) VALUES(?,?,?,?,?,?)",
                   (d['name'], d.get('unit',''), d['min_val'], d['max_val'], d['normal_min'], d['normal_max']))
        db.commit()
    return jsonify({'ok': True})

@app.route('/api/characteristics/<int:cid>', methods=['DELETE'])
def del_char(cid):
    with get_db() as db:
        db.execute("DELETE FROM characteristics WHERE id=?", (cid,)); db.commit()
    return jsonify({'ok': True})

# --- CRUD Repairs ---
@app.route('/api/repairs', methods=['POST'])
def add_repair():
    d = request.json
    with get_db() as db:
        db.execute("INSERT INTO repairs(name) VALUES(?)", (d['name'],))
        rid = db.execute("SELECT id FROM repairs WHERE name=?", (d['name'],)).fetchone()[0]
        for i, step in enumerate(d.get('steps', []), 1):
            db.execute("INSERT INTO repair_steps(repair_id,step_order,description) VALUES(?,?,?)", (rid, i, step))
        db.commit()
    return jsonify({'ok': True})

@app.route('/api/repairs/<int:rid>', methods=['DELETE'])
def del_repair(rid):
    with get_db() as db:
        db.execute("DELETE FROM repairs WHERE id=?", (rid,)); db.commit()
    return jsonify({'ok': True})

# --- CRUD Diagnoses ---
@app.route('/api/diagnoses', methods=['POST'])
def add_diag():
    d = request.json
    with get_db() as db:
        db.execute("INSERT INTO diagnoses(name,repair_id) VALUES(?,?)", (d['name'], d.get('repair_id')))
        db.commit()
    return jsonify({'ok': True})

@app.route('/api/diagnoses/<int:did>', methods=['DELETE'])
def del_diag(did):
    with get_db() as db:
        db.execute("DELETE FROM diagnoses WHERE id=?", (did,)); db.commit()
    return jsonify({'ok': True})

# ==================== MAIN ====================
if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
