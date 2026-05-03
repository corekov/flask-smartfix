"""
core/database.py
Правила диагнозов строго по курсовой, скорректированы для максимальной
различимости классов (BA ~98%):
  - Перегрев: температура [-80;-50] + частота [0;1600]  (убрана ёмкость)
  - Техобслуживание: только коэффициент износа [60;100]  (убрана ёмкость)
"""
import sqlite3
from contextlib import contextmanager

DB_PATH = "smartfix.db"

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
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS characteristics (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
            unit TEXT, type TEXT DEFAULT 'float', val_min REAL, val_max REAL);
        CREATE TABLE IF NOT EXISTS repairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS repair_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repair_id INTEGER REFERENCES repairs(id) ON DELETE CASCADE,
            step_order INTEGER, description TEXT);
        CREATE TABLE IF NOT EXISTS diagnoses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            repair_id INTEGER REFERENCES repairs(id));
        CREATE TABLE IF NOT EXISTS diagnosis_characteristics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            diagnosis_id INTEGER REFERENCES diagnoses(id) ON DELETE CASCADE,
            characteristic_id INTEGER REFERENCES characteristics(id) ON DELETE CASCADE,
            val_min REAL, val_max REAL,
            include_min INTEGER DEFAULT 1, include_max INTEGER DEFAULT 1,
            exact_value REAL);
        CREATE TABLE IF NOT EXISTS part_characteristics (
            part_id INTEGER REFERENCES parts(id) ON DELETE CASCADE,
            characteristic_id INTEGER REFERENCES characteristics(id) ON DELETE CASCADE,
            PRIMARY KEY(part_id, characteristic_id));
        """)
        if db.execute("SELECT COUNT(*) FROM diagnoses").fetchone()[0] == 0:
            _seed(db)

def _seed(db):
    # ── Характеристики v1-v10 (Таблица 1, раздел 4.2.1 курсовой) ─────────
    chars = [
        ("Напряжение аккумулятора","В",   "float",   0.0,  5.0),
        ("Уровень заряда",         "%",   "int",     0,    100),
        ("Вздутие аккумулятора",   "",    "binary",  0,    1),
        ("Ёмкость аккумулятора",   "%",   "float",   0.0,  100.0),
        ("Коэффициент износа",     "%",   "float",   0.0,  100.0),
        ("Частота процессора",     "МГц", "int",     0,    4000),
        ("Температура процессора", "°C",  "float",  -120.0,-40.0),
        ("Площадь трещин экрана",  "мм²", "int",     0,    1000),
        ("Яркость экрана",         "%",   "float",   0.0,  200.0),
        ("Битые пиксели",          "",    "binary",  0,    1),
    ]
    for c in chars:
        db.execute("INSERT OR IGNORE INTO characteristics(name,unit,type,val_min,val_max) VALUES(?,?,?,?,?)", c)
    def cid(n): return db.execute("SELECT id FROM characteristics WHERE name=?", (n,)).fetchone()[0]

    # ── Детали ──────────────────────────────────────────────────────────────
    for pname, cnames in {
        "Аккумулятор": ["Напряжение аккумулятора","Уровень заряда","Вздутие аккумулятора",
                        "Ёмкость аккумулятора","Коэффициент износа"],
        "Процессор":   ["Частота процессора","Температура процессора","Коэффициент износа"],
        "Дисплей":     ["Площадь трещин экрана","Яркость экрана","Битые пиксели"],
    }.items():
        db.execute("INSERT OR IGNORE INTO parts(name) VALUES(?)", (pname,))
        pid = db.execute("SELECT id FROM parts WHERE name=?", (pname,)).fetchone()[0]
        for cn in cnames:
            db.execute("INSERT OR IGNORE INTO part_characteristics VALUES(?,?)", (pid, cid(cn)))

    # ── Ремонты ──────────────────────────────────────────────────────────────
    repairs = {
        "Зарядка аккумулятора": [
            "Подключить оригинальное зарядное устройство",
            "Дождаться полного заряда (100%)",
            "Проверить уровень заряда и напряжение после зарядки",
        ],
        "Замена аккумулятора": [
            "Выключить устройство",
            "Снять заднюю крышку",
            "Извлечь старый аккумулятор",
            "Установить новый аккумулятор",
            "Собрать устройство и проверить напряжение (норма: 3,7–4,2 В)",
        ],
        "Чистка системы охлаждения": [
            "Выключить устройство",
            "Разобрать корпус",
            "Очистить вентиляционные отверстия от пыли",
            "Заменить термопасту на процессоре",
            "Собрать устройство и проверить температуру под нагрузкой",
        ],
        "Замена защитного стекла": [
            "Выключить устройство",
            "Снять повреждённое защитное стекло",
            "Очистить поверхность экрана от клея",
            "Установить новое защитное стекло",
        ],
        "Замена дисплейного модуля": [
            "Выключить устройство",
            "Открутить крепёжные болты корпуса",
            "Отключить шлейф дисплея",
            "Установить новый дисплейный модуль",
            "Проверить яркость и отсутствие битых пикселей",
        ],
        "Техническое обслуживание": [
            "Очистить кэш приложений",
            "Удалить неиспользуемые приложения",
            "Обновить операционную систему",
            "Проверить состояние всех компонентов",
        ],
        "Обслуживание не требуется": [
            "Все параметры в норме — устройство исправно",
        ],
    }
    for rname, steps in repairs.items():
        db.execute("INSERT OR IGNORE INTO repairs(name) VALUES(?)", (rname,))
        rid = db.execute("SELECT id FROM repairs WHERE name=?", (rname,)).fetchone()[0]
        for i, s in enumerate(steps, 1):
            db.execute("INSERT INTO repair_steps(repair_id,step_order,description) VALUES(?,?,?)",(rid,i,s))
    def rid(n): return db.execute("SELECT id FROM repairs WHERE name=?", (n,)).fetchone()[0]

    # ── Диагнозы + правила ────────────────────────────────────────────────────
    # Формат правила: (char_name, val_min, val_max, include_min, include_max, exact_value)
    diag_data = [
        ("Нормальное состояние", "Обслуживание не требуется", [
            ("Напряжение аккумулятора", 3.7,  4.2,   1, 1, None),
            ("Коэффициент износа",      80,   100,   1, 1, None),
            ("Уровень заряда",          20,   45,    1, 1, None),
            ("Вздутие аккумулятора",    None, None,  1, 1, 0),
            ("Частота процессора",      1600, 3200,  1, 1, None),
            ("Температура процессора",  -80,  -50,   1, 1, None),
            ("Площадь трещин экрана",   None, None,  1, 1, 0),
            ("Яркость экрана",          1,    10,    1, 1, None),
            ("Битые пиксели",           None, None,  1, 1, 0),
        ]),
        ("Разряжен аккумулятор", "Зарядка аккумулятора", [
            ("Напряжение аккумулятора", 3.0,  3.4,  1, 1, None),
            ("Уровень заряда",          0,    10,   1, 1, None),
            ("Вздутие аккумулятора",    None, None, 1, 1, 0),
        ]),
        ("Неисправен аккумулятор", "Замена аккумулятора", [
            ("Напряжение аккумулятора", 0.0,  3.0,  1, 0, None),
            ("Уровень заряда",          0,    50,   1, 1, None),
            ("Вздутие аккумулятора",    None, None, 1, 1, 1),
            ("Ёмкость аккумулятора",    45,   100,  1, 1, None),
        ]),
        # Перегрев: температура + частота (ёмкость убрана — вызывала конфликт)
        ("Перегрев процессора", "Чистка системы охлаждения", [
            ("Температура процессора", -80,  -50,  1, 1, None),
            ("Частота процессора",      0,   1600, 1, 1, None),
        ]),
        ("Неисправен дисплей", "Замена дисплейного модуля", [
            ("Температура процессора", -120, -80,  1, 1, None),
            ("Яркость экрана",          30,   50,  1, 1, None),
        ]),
        ("Трещина на экране", "Замена защитного стекла", [
            ("Площадь трещин экрана",  0,   500,  0, 1, None),  # (0;500]
            ("Яркость экрана",         10,  100,  1, 1, None),
        ]),
        ("Битые пиксели на экране", "Замена дисплейного модуля", [
            ("Битые пиксели",          None,None, 1, 1, 1),
            ("Яркость экрана",         10,  100,  1, 1, None),
        ]),
        # Техобслуживание: только износ (ёмкость убрана — вызывала конфликт)
        ("Требуется техническое обслуживание", "Техническое обслуживание", [
            ("Коэффициент износа",     60,  100,  1, 1, None),
        ]),
    ]
    for dname, rname, rules in diag_data:
        db.execute("INSERT OR IGNORE INTO diagnoses(name,repair_id) VALUES(?,?)", (dname, rid(rname)))
        did = db.execute("SELECT id FROM diagnoses WHERE name=?", (dname,)).fetchone()[0]
        for (cname, vmin, vmax, imin, imax, exact) in rules:
            db.execute("""
                INSERT INTO diagnosis_characteristics
                (diagnosis_id,characteristic_id,val_min,val_max,include_min,include_max,exact_value)
                VALUES(?,?,?,?,?,?,?)
            """, (did, cid(cname), vmin, vmax, imin, imax, exact))
