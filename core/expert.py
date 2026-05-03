"""
core/expert.py — Экспертная система прямого вывода.

Правила:
 - Диагноз рассматривается только если хотя бы одна его характеристика введена.
 - Счёт = matched / applicable (только введённые признаки).
 - Если признак введён, но не совпал с правилом -> он снижает счёт.
 - Если признак не введён -> не участвует в счёте вообще.
"""

from core.database import get_db


def match(feature_values: dict) -> list[dict]:
    introduced = set(feature_values.keys())

    with get_db() as db:
        diagnoses = db.execute("SELECT id, name, repair_id FROM diagnoses").fetchall()
        results   = []

        for diag in diagnoses:
            rules = db.execute("""
                SELECT c.name, dc.val_min, dc.val_max,
                       dc.include_min, dc.include_max, dc.exact_value
                FROM diagnosis_characteristics dc
                JOIN characteristics c ON c.id = dc.characteristic_id
                WHERE dc.diagnosis_id = ?
            """, (diag["id"],)).fetchall()

            if not rules:
                continue

            applicable = [r for r in rules if r["name"] in introduced]
            if not applicable:
                continue  # ни одна характеристика этого диагноза не введена -> пропуск

            matched = 0
            reasons = []
            for r in applicable:
                val = feature_values[r["name"]]
                if r["exact_value"] is not None:
                    ok = abs(float(val) - float(r["exact_value"])) < 1e-9
                else:
                    lo, hi = r["val_min"], r["val_max"]
                    ok_lo  = (val >= lo) if r["include_min"] else (val > lo)
                    ok_hi  = (val <= hi) if r["include_max"] else (val < hi)
                    ok     = ok_lo and ok_hi
                matched += 1 if ok else 0
                reasons.append(f"{r['name']}: {'v' if ok else 'x'}")

            pct = (matched / len(applicable)) * 100
            if pct >= 50:
                results.append({
                    "id":        diag["id"],
                    "name":      diag["name"],
                    "pct":       round(pct, 1),
                    "matched":   matched,
                    "total":     len(applicable),
                    "reasons":   reasons,
                    "repair_id": diag["repair_id"],
                })

    results.sort(key=lambda x: -x["pct"])
    return results
