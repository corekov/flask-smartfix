"""core/kb_api.py — CRUD база знаний."""
from core.database import get_db


# Characteristics
def list_chars():
    with get_db() as db:
        return [dict(r) for r in db.execute("SELECT * FROM characteristics ORDER BY name")]

# Parts
def list_parts():
    with get_db() as db:
        return [dict(r) for r in db.execute("SELECT * FROM parts ORDER BY name")]

def add_part(name):
    with get_db() as db:
        db.execute("INSERT INTO parts(name) VALUES(?)", (name,))

def delete_part(pid):
    with get_db() as db:
        db.execute("DELETE FROM parts WHERE id=?", (pid,))

def get_part_chars(pid):
    with get_db() as db:
        return [dict(r) for r in db.execute("""
            SELECT c.* FROM characteristics c
            JOIN part_characteristics pc ON pc.characteristic_id=c.id
            WHERE pc.part_id=?""", (pid,))]

def add_part_char(pid, char_id):
    with get_db() as db:
        db.execute("INSERT OR IGNORE INTO part_characteristics VALUES(?,?)", (pid, char_id))

def remove_part_char(pid, char_id):
    with get_db() as db:
        db.execute("DELETE FROM part_characteristics WHERE part_id=? AND characteristic_id=?",
                   (pid, char_id))

# Repairs
def list_repairs():
    with get_db() as db:
        return [dict(r) for r in db.execute("SELECT * FROM repairs ORDER BY name")]

def get_repair_steps(rid):
    with get_db() as db:
        return [dict(r) for r in db.execute(
            "SELECT * FROM repair_steps WHERE repair_id=? ORDER BY step_order", (rid,))]

def add_repair(name):
    with get_db() as db:
        db.execute("INSERT INTO repairs(name) VALUES(?)", (name,))
        return db.execute("SELECT id FROM repairs WHERE name=?", (name,)).fetchone()[0]

def delete_repair(rid):
    with get_db() as db:
        db.execute("DELETE FROM repairs WHERE id=?", (rid,))

def add_repair_step(rid, order, desc):
    with get_db() as db:
        db.execute("INSERT INTO repair_steps(repair_id,step_order,description) VALUES(?,?,?)",
                   (rid, order, desc))

def delete_repair_step(step_id):
    with get_db() as db:
        db.execute("DELETE FROM repair_steps WHERE id=?", (step_id,))

def update_repair_step(step_id, desc):
    with get_db() as db:
        db.execute("UPDATE repair_steps SET description=? WHERE id=?", (desc, step_id))

# Diagnoses
def list_diagnoses():
    with get_db() as db:
        return [dict(r) for r in db.execute("""
            SELECT d.id, d.name, d.repair_id, r.name as repair_name
            FROM diagnoses d LEFT JOIN repairs r ON r.id=d.repair_id ORDER BY d.name""")]

def add_diagnosis(name, repair_id=None):
    with get_db() as db:
        db.execute("INSERT INTO diagnoses(name,repair_id) VALUES(?,?)", (name, repair_id))

def delete_diagnosis(did):
    with get_db() as db:
        db.execute("DELETE FROM diagnoses WHERE id=?", (did,))

def update_diagnosis_repair(did, repair_id):
    with get_db() as db:
        db.execute("UPDATE diagnoses SET repair_id=? WHERE id=?", (repair_id, did))

def get_diag_chars(did):
    with get_db() as db:
        return [dict(r) for r in db.execute("""
            SELECT dc.*, c.name as char_name, c.unit, c.type
            FROM diagnosis_characteristics dc
            JOIN characteristics c ON c.id=dc.characteristic_id
            WHERE dc.diagnosis_id=?""", (did,))]

def add_diag_char(did, payload):
    with get_db() as db:
        db.execute("""INSERT INTO diagnosis_characteristics
            (diagnosis_id,characteristic_id,val_min,val_max,include_min,include_max,exact_value)
            VALUES(?,?,?,?,?,?,?)""",
            (did, payload["characteristic_id"],
             payload.get("val_min"), payload.get("val_max"),
             payload.get("include_min", 1), payload.get("include_max", 1),
             payload.get("exact_value")))

def delete_diag_char(dc_id, did):
    with get_db() as db:
        db.execute("DELETE FROM diagnosis_characteristics WHERE id=? AND diagnosis_id=?",
                   (dc_id, did))

# Validation
def validate():
    problems = []
    with get_db() as db:
        for r in db.execute("""
            SELECT name FROM diagnoses d WHERE NOT EXISTS
            (SELECT 1 FROM diagnosis_characteristics dc WHERE dc.diagnosis_id=d.id)"""):
            problems.append(f"Диагноз «{r['name']}» не имеет характеристик")
        for r in db.execute("SELECT name FROM diagnoses WHERE repair_id IS NULL"):
            problems.append(f"Диагноз «{r['name']}» не привязан к ремонту")
    return {"ok": len(problems) == 0, "problems": problems}
