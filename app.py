"""
SmartFix — Flask backend
pip install flask flask-cors requests
"""
from flask import Flask, jsonify, request, render_template
from flask_cors import CORS
import sqlite3, requests, os

app = Flask(__name__)
CORS(app)

DB_PATH = os.path.join(os.path.dirname(__file__), 'smartfix.db')
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://localhost:11434')


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
    """Заполняет БД начальными данными только при первом запуске."""
    with get_db() as db:
        if db.execute("SELECT COUNT(*) FROM parts").fetchone()[0] > 0:
            return

        # --- Детали ---
        for p in ['Аккумулятор', 'Материнская плата', 'Дисплейный модуль']:
            db.execute("INSERT INTO parts(name) VALUES(?)", (p,))

        # --- Характеристики ---
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

        def pid(n): return db.execute("SELECT id FROM parts WHERE name=?", (n,)).fetchone()[0]
        def cid(n): return db.execute("SELECT id FROM characteristics WHERE name=?", (n,)).fetchone()[0]

        # --- Связи деталь → характеристики ---
        pc = {
            'Аккумулятор': ['напряжение аккумулятора', 'уровень заряда аккумулятора',
                             'наличие вздутия аккумулятора', 'температура аккумулятора при зарядке'],
            'Материнская плата': ['температура процессора', 'скорость оперативной памяти', 'уровень сигнала модема'],
            'Дисплейный модуль': ['площадь трещин на стекле', 'отклик дисплейной матрицы', 'наличие артефактов на экране'],
        }
        for part, clist in pc.items():
            for ch in clist:
                db.execute("INSERT INTO part_characteristics VALUES(?,?)", (pid(part), cid(ch)))

        # --- Ремонты ---
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
                'Если трещин ≤ 100 мм²: нанести защитную плёнку или клей',
                'Если трещин > 100 мм²: разобрать корпус, заменить стекло, собрать модуль',
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

        def rid(n): return db.execute("SELECT id FROM repairs WHERE name=?", (n,)).fetchone()[0]

        # --- Диагнозы ---
        for dname, rname in [
            ('Исправен',                     'Ремонт не требуется'),
            ('Разряжен аккумулятор',         'Зарядить аккумулятор'),
            ('Неисправен аккумулятор',       'Заменить аккумулятор'),
            ('Перегрев процессора',          'Устранить перегрев процессора'),
            ('Слабый сигнал модема',         'Устранить слабый сигнал модема'),
            ('Трещины на стекле',            'Устранить трещины на стекле'),
            ('Артефакты на матрице дисплея', 'Устранить артефакты дисплея'),
        ]:
            db.execute("INSERT INTO diagnoses(name,repair_id) VALUES(?,?)", (dname, rid(rname)))

        def did(n): return db.execute("SELECT id FROM diagnoses WHERE name=?", (n,)).fetchone()[0]

        # --- Характеристики диагнозов (точно по курсовой) ---
        # exclusive_min=1 означает скобку ( , exclusive_max=1 означает скобку )
        # FIX #5: "Разряжен аккумулятор" → вздутие строго = 0
        #         "Неисправен аккумулятор" → вздутие [0;1] (любое)
        dc = [
            # Разряжен аккумулятор
            ('Разряжен аккумулятор', 'напряжение аккумулятора',          3.0,  3.4,  0, 1, None),
            ('Разряжен аккумулятор', 'уровень заряда аккумулятора',      0,    10,   0, 1, None),
            ('Разряжен аккумулятор', 'наличие вздутия аккумулятора',     None, None, 0, 0, 0),    # = 0 строго
            # Неисправен аккумулятор
            ('Неисправен аккумулятор', 'напряжение аккумулятора',        0,    3.0,  0, 1, None),
            ('Неисправен аккумулятор', 'уровень заряда аккумулятора',    0,    50,   0, 1, None),
            ('Неисправен аккумулятор', 'наличие вздутия аккумулятора',   0,    1,    0, 0, None),  # 0 или 1
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
            # Артефакты
            ('Артефакты на матрице дисплея', 'наличие артефактов на экране', None, None, 0, 0, 1),
            ('Артефакты на матрице дисплея', 'отклик дисплейной матрицы', 10,  100,  1, 0, None),
        ]
        for dname, cname, rmin, rmax, exc_min, exc_max, exact in dc:
            db.execute(
                "INSERT INTO diagnosis_characteristics"
                "(diagnosis_id,char_id,range_min,range_max,exclusive_min,exclusive_max,exact_val)"
                " VALUES(?,?,?,?,?,?,?)",
                (did(dname), cid(cname), rmin, rmax, exc_min, exc_max, exact))
        db.commit()


def get_kb_data():
    with get_db() as db:
        chars = {r['name']: dict(r) for r in db.execute("SELECT * FROM characteristics").fetchall()}

        parts = []
        for p in db.execute("SELECT p.id, p.name, GROUP_CONCAT(c.name,'||') as cn FROM parts p "
                             "LEFT JOIN part_characteristics pc ON pc.part_id=p.id "
                             "LEFT JOIN characteristics c ON c.id=pc.char_id GROUP BY p.id").fetchall():
            parts.append({'id': p['id'], 'name': p['name'],
                          'characteristics': [x for x in (p['cn'] or '').split('||') if x]})

        repairs = []
        for r in db.execute("SELECT r.id, r.name, GROUP_CONCAT(rs.description,'||') as steps "
                             "FROM repairs r LEFT JOIN repair_steps rs ON rs.repair_id=r.id "
                             "GROUP BY r.id ORDER BY rs.step_order").fetchall():
            repairs.append({'id': r['id'], 'name': r['name'],
                            'steps': [s for s in (r['steps'] or '').split('||') if s]})

        diagnoses = []
        for d in db.execute("SELECT d.id, d.name, rep.name as repair_name, d.repair_id "
                             "FROM diagnoses d LEFT JOIN repairs rep ON rep.id=d.repair_id").fetchall():
            dc_rows = db.execute(
                "SELECT c.name as char_name, c.unit, dc.range_min, dc.range_max, "
                "dc.exclusive_min, dc.exclusive_max, dc.exact_val "
                "FROM diagnosis_characteristics dc JOIN characteristics c ON c.id=dc.char_id "
                "WHERE dc.diagnosis_id=?", (d['id'],)).fetchall()
            diagnoses.append({'id': d['id'], 'name': d['name'],
                               'repair_name': d['repair_name'], 'repair_id': d['repair_id'],
                               'characteristics': [dict(r) for r in dc_rows]})

        return {'characteristics': chars, 'parts': parts, 'repairs': repairs, 'diagnoses': diagnoses}


# ===================== ROUTES =====================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/kb')
def api_kb():
    return jsonify(get_kb_data())


@app.route('/api/solve', methods=['POST'])
def api_solve():
    data = request.json
    diag_id = data.get('diagnosis_id')
    values  = data.get('values', {})

    with get_db() as db:
        diag = db.execute(
            "SELECT d.*, r.name as repair_name FROM diagnoses d "
            "LEFT JOIN repairs r ON r.id=d.repair_id WHERE d.id=?", (diag_id,)).fetchone()
        if not diag:
            return jsonify({'error': 'Диагноз не найден'}), 404

        # FIX #5: вздутие = 1 при диагнозе "Разряжен аккумулятор" → автопереключение
        override_msg = None
        if diag['name'] == 'Разряжен аккумулятор' and                 float(values.get('наличие вздутия аккумулятора', 0)) == 1:
            new_diag = db.execute(
                "SELECT d.*, r.name as repair_name FROM diagnoses d "
                "LEFT JOIN repairs r ON r.id=d.repair_id WHERE d.name='Неисправен аккумулятор'").fetchone()
            if new_diag:
                override_msg = ('Обнаружено вздутие аккумулятора! Диагноз автоматически изменён '
                                'с «Разряжен аккумулятор» на «Неисправен аккумулятор».')
                diag    = new_diag
                diag_id = new_diag['id']

        dc_rows = db.execute(
            "SELECT c.name as char_name, c.unit, dc.range_min, dc.range_max, "
            "dc.exclusive_min, dc.exclusive_max, dc.exact_val "
            "FROM diagnosis_characteristics dc JOIN characteristics c ON c.id=dc.char_id "
            "WHERE dc.diagnosis_id=?", (diag_id,)).fetchall()

        steps = [r['description'] for r in db.execute(
            "SELECT rs.description FROM repair_steps rs JOIN repairs r ON r.id=rs.repair_id "
            "WHERE r.name=? ORDER BY rs.step_order", (diag['repair_name'],)).fetchall()]

    checks = []
    for dc in dc_rows:
        val = values.get(dc['char_name'])
        if val is None:
            continue
        val = float(val)
        if dc['exact_val'] is not None:
            ok = abs(val - dc['exact_val']) < 0.0001
            expected = f"= {dc['exact_val']}"
        else:
            lo = '(' if dc['exclusive_min'] else '['
            hi = ')' if dc['exclusive_max'] else ']'
            ok = (val > dc['range_min'] if dc['exclusive_min'] else val >= dc['range_min']) and                  (val < dc['range_max'] if dc['exclusive_max'] else val <= dc['range_max'])
            expected = f"{lo}{dc['range_min']}; {dc['range_max']}{hi}"
        checks.append({'name': dc['char_name'], 'value': val,
                       'unit': dc['unit'], 'expected': expected, 'ok': ok})

    matched   = sum(1 for c in checks if c['ok'])
    match_pct = round(matched / len(checks) * 100) if checks else 100

    return jsonify({'diagnosis': diag['name'], 'repair': diag['repair_name'],
                    'steps': steps, 'checks': checks,
                    'match_pct': match_pct, 'values': values,
                    'override_msg': override_msg})


# FIX #1 + #2: список моделей и передача модели с фронта
@app.route('/api/ollama/status')
def ollama_status():
    try:
        r = requests.get(f'{OLLAMA_URL}/api/tags', timeout=3)
        models = [m['name'] for m in r.json().get('models', [])]
        return jsonify({'online': True, 'models': models})
    except Exception as e:
        return jsonify({'online': False, 'models': [], 'error': str(e)})


@app.route('/api/ollama/check', methods=['POST'])
def ollama_check():
    data      = request.json
    model     = data.get('model', 'llama3')   # FIX #2: модель приходит с фронта
    diagnosis = data.get('diagnosis', '')
    repair    = data.get('repair', '')
    checks    = data.get('checks', [])
    steps     = data.get('steps', [])
    match_pct = data.get('match_pct', 0)

    checks_str = "".join(
        f"  - {c['name']}: {c['value']} {c.get('unit','')} "
        f"(ожидалось {c['expected']}) — {'соответствует' if c['ok'] else 'НЕ соответствует'}"
        for c in checks)
    steps_str = "".join(f"  {i+1}. {s}" for i, s in enumerate(steps))

    prompt = f"""Ты — эксперт по ремонту смартфонов. Отвечай только на русском языке.

Результат диагностики смартфона:
- Диагноз: {diagnosis}
- Назначенный ремонт: {repair}
- Совпадение характеристик с диагнозом: {match_pct}%

Значения характеристик:
{checks_str}

Шаги ремонта:
{steps_str}

Ответь строго по пунктам:
1. Корректность диагноза — верен ли он исходя из значений характеристик?
2. Полнота ремонта — все ли шаги указаны, что можно добавить?
3. Риски — предупреди о возможных опасностях при выполнении ремонта.
4. Итоговая рекомендация."""

    try:
        r = requests.post(
            f'{OLLAMA_URL}/api/generate',
            json={'model': model, 'prompt': prompt, 'stream': False},
            timeout=180)
        r.raise_for_status()
        resp_json = r.json()
        # FIX #2: Ollama может вернуть 'response' или 'message.content'
        text = resp_json.get('response') or resp_json.get('message', {}).get('content', '')
        if not text:
            return jsonify({'error': f'Пустой ответ. Тело: {str(resp_json)[:300]}'}), 500
        return jsonify({'response': text})
    except requests.exceptions.ConnectionError:
        return jsonify({'error': f'Ollama недоступна ({OLLAMA_URL}). Запустите: ollama serve'}), 503
    except requests.exceptions.Timeout:
        return jsonify({'error': 'Ollama не ответила за 180 сек. Попробуйте более быструю модель.'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ===================== CRUD =====================

@app.route('/api/parts', methods=['POST'])
def add_part():
    with get_db() as db:
        db.execute("INSERT INTO parts(name) VALUES(?)", (request.json['name'],))
        db.commit()
    return jsonify({'ok': True})

@app.route('/api/parts/<int:pid>', methods=['DELETE'])
def del_part(pid):
    with get_db() as db:
        db.execute("DELETE FROM parts WHERE id=?", (pid,)); db.commit()
    return jsonify({'ok': True})

# FIX #3: управление хар-ками детали
@app.route('/api/parts/<int:pid>/characteristics', methods=['POST'])
def add_part_char(pid):
    with get_db() as db:
        try:
            db.execute("INSERT INTO part_characteristics VALUES(?,?)",
                       (pid, request.json['char_id'])); db.commit()
        except Exception as e:
            return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True})

@app.route('/api/parts/<int:pid>/characteristics/<int:cid>', methods=['DELETE'])
def del_part_char(pid, cid):
    with get_db() as db:
        db.execute("DELETE FROM part_characteristics WHERE part_id=? AND char_id=?",
                   (pid, cid)); db.commit()
    return jsonify({'ok': True})

@app.route('/api/characteristics', methods=['POST'])
def add_char():
    d = request.json
    with get_db() as db:
        db.execute("INSERT INTO characteristics(name,unit,min_val,max_val,normal_min,normal_max) "
                   "VALUES(?,?,?,?,?,?)",
                   (d['name'], d.get('unit',''), d['min_val'], d['max_val'],
                    d['normal_min'], d['normal_max'])); db.commit()
    return jsonify({'ok': True})

@app.route('/api/characteristics/<int:cid>', methods=['DELETE'])
def del_char(cid):
    with get_db() as db:
        db.execute("DELETE FROM characteristics WHERE id=?", (cid,)); db.commit()
    return jsonify({'ok': True})

@app.route('/api/repairs', methods=['POST'])
def add_repair():
    d = request.json
    with get_db() as db:
        db.execute("INSERT INTO repairs(name) VALUES(?)", (d['name'],))
        rid = db.execute("SELECT id FROM repairs WHERE name=?", (d['name'],)).fetchone()[0]
        for i, step in enumerate(d.get('steps', []), 1):
            db.execute("INSERT INTO repair_steps(repair_id,step_order,description) VALUES(?,?,?)",
                       (rid, i, step))
        db.commit()
    return jsonify({'ok': True})

@app.route('/api/repairs/<int:rid>', methods=['DELETE'])
def del_repair(rid):
    with get_db() as db:
        db.execute("DELETE FROM repairs WHERE id=?", (rid,)); db.commit()
    return jsonify({'ok': True})

@app.route('/api/diagnoses', methods=['POST'])
def add_diag():
    d = request.json
    with get_db() as db:
        db.execute("INSERT INTO diagnoses(name,repair_id) VALUES(?,?)",
                   (d['name'], d.get('repair_id'))); db.commit()
    return jsonify({'ok': True})

@app.route('/api/diagnoses/<int:did>', methods=['DELETE'])
def del_diag(did):
    with get_db() as db:
        db.execute("DELETE FROM diagnoses WHERE id=?", (did,)); db.commit()
    return jsonify({'ok': True})

@app.route('/api/diagnoses/<int:did>', methods=['PATCH'])
def patch_diag(did):
    d = request.json
    with get_db() as db:
        if 'repair_id' in d:
            db.execute("UPDATE diagnoses SET repair_id=? WHERE id=?",
                       (d['repair_id'], did)); db.commit()
    return jsonify({'ok': True})

# FIX #3: добавление/удаление хар-ки диагноза
@app.route('/api/diagnoses/<int:did>/characteristics', methods=['POST'])
def add_diag_char(did):
    d = request.json
    with get_db() as db:
        db.execute(
            "INSERT INTO diagnosis_characteristics"
            "(diagnosis_id,char_id,range_min,range_max,exclusive_min,exclusive_max,exact_val)"
            " VALUES(?,?,?,?,?,?,?)",
            (did, d['char_id'], d.get('range_min'), d.get('range_max'),
             d.get('exclusive_min', 0), d.get('exclusive_max', 0), d.get('exact_val')))
        db.commit()
    return jsonify({'ok': True})

@app.route('/api/diagnoses/characteristics/<int:dcid>', methods=['DELETE'])
def del_diag_char(dcid):
    with get_db() as db:
        db.execute("DELETE FROM diagnosis_characteristics WHERE id=?", (dcid,)); db.commit()
    return jsonify({'ok': True})


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
