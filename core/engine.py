"""
core/engine.py — Гибридный движок диагностики (Вариант 2 курсовой).
"""
from core import expert, ml_model
from core.database import get_db

METHOD_LABELS = {
    "expert":          "Экспертная система (единственный кандидат)",
    "hybrid":          "Гибридный: ML уточнил из нескольких кандидатов",
    "ml_only":         "ML-классификатор (эксперт не нашёл совпадений)",
    "expert_fallback": "Экспертная система (ML не пересёкся с кандидатами)",
}

def _repair(diagnosis_name):
    if not diagnosis_name:
        return None
    with get_db() as db:
        row = db.execute("""
            SELECT r.id, r.name FROM diagnoses d
            JOIN repairs r ON r.id = d.repair_id WHERE d.name=?
        """, (diagnosis_name,)).fetchone()
        if not row:
            return None
        steps = db.execute("""
            SELECT description FROM repair_steps
            WHERE repair_id=? ORDER BY step_order
        """, (row["id"],)).fetchall()
        return {"name": row["name"], "steps": [s["description"] for s in steps]}


def diagnose(feature_values: dict) -> dict:
    candidates   = expert.match(feature_values)
    ml_raw       = ml_model.predict(feature_values)
    ml_ranking   = [(n, round(p*100, 1)) for n, p in ml_raw]
    method       = "expert"
    final_name   = None

    if len(candidates) == 0:
        final_name, method = (ml_ranking[0][0], "ml_only") if ml_ranking else (None, "ml_only")
    elif len(candidates) == 1:
        final_name = candidates[0]["name"]
    else:
        names = {c["name"] for c in candidates}
        for ml_name, _ in ml_ranking:
            if ml_name in names:
                final_name, method = ml_name, "hybrid"
                break
        if not final_name:
            final_name, method = candidates[0]["name"], "expert_fallback"

    return {
        "expert_candidates": candidates,
        "ml_ranking":        ml_ranking,
        "final_diagnosis":   final_name,
        "selection_method":  method,
        "method_label":      METHOD_LABELS.get(method, method),
        "repair":            _repair(final_name),
    }
