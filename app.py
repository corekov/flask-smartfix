"""app.py — Flask routes. Вся логика в модулях core/."""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from core.database import init_db
from core import ml_model, engine, kb_api, ollama_api

app = Flask(__name__)
CORS(app)

@app.route("/")
def index(): return render_template("index.html")

# ── Diagnostics ───────────────────────────────
@app.route("/api/diagnose", methods=["POST"])
def api_diagnose():
    data     = request.get_json(force=True)
    features = {k: float(v) for k, v in data.items() if v != "" and v is not None}
    return jsonify(engine.diagnose(features))

# ── ML ────────────────────────────────────────
@app.route("/api/ml/train", methods=["POST"])
def api_train():
    try:
        ba, params, report = ml_model.train(verbose=True)
        return jsonify({"ok": True, "balanced_accuracy": round(ba*100, 2),
                        "best_params": params, "report": report})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/ml/status")
def api_ml_status():
    return jsonify({"loaded": ml_model.is_loaded(),
                    "n_classes": ml_model.n_classes(),
                    "classes": ml_model.class_names()})

# ── Characteristics ───────────────────────────
@app.route("/api/characteristics")
def api_chars(): return jsonify(kb_api.list_chars())

# ── Parts ─────────────────────────────────────
@app.route("/api/parts", methods=["GET","POST"])
def api_parts():
    if request.method == "POST":
        kb_api.add_part(request.get_json()["name"]); return jsonify({"ok": True})
    return jsonify(kb_api.list_parts())

@app.route("/api/parts/<int:pid>", methods=["DELETE"])
def api_del_part(pid):
    kb_api.delete_part(pid); return jsonify({"ok": True})

@app.route("/api/parts/<int:pid>/characteristics", methods=["GET","POST"])
def api_part_chars(pid):
    if request.method == "POST":
        kb_api.add_part_char(pid, request.get_json()["characteristic_id"])
        return jsonify({"ok": True})
    return jsonify(kb_api.get_part_chars(pid))

@app.route("/api/parts/<int:pid>/characteristics/<int:cid>", methods=["DELETE"])
def api_remove_part_char(pid, cid):
    kb_api.remove_part_char(pid, cid); return jsonify({"ok": True})

# ── Repairs ───────────────────────────────────
@app.route("/api/repairs", methods=["GET","POST"])
def api_repairs():
    if request.method == "POST":
        rid = kb_api.add_repair(request.get_json()["name"])
        return jsonify({"ok": True, "id": rid})
    return jsonify(kb_api.list_repairs())

@app.route("/api/repairs/<int:rid>", methods=["DELETE"])
def api_del_repair(rid):
    kb_api.delete_repair(rid); return jsonify({"ok": True})

@app.route("/api/repairs/<int:rid>/steps", methods=["GET","POST"])
def api_repair_steps(rid):
    if request.method == "POST":
        d = request.get_json()
        kb_api.add_repair_step(rid, d["order"], d["description"])
        return jsonify({"ok": True})
    return jsonify(kb_api.get_repair_steps(rid))

@app.route("/api/repair_steps/<int:sid>", methods=["DELETE","PUT"])
def api_repair_step(sid):
    if request.method == "DELETE":
        kb_api.delete_repair_step(sid); return jsonify({"ok": True})
    kb_api.update_repair_step(sid, request.get_json()["description"])
    return jsonify({"ok": True})

# ── Diagnoses ─────────────────────────────────
@app.route("/api/diagnoses", methods=["GET","POST"])
def api_diagnoses():
    if request.method == "POST":
        d = request.get_json()
        try:
            kb_api.add_diagnosis(d["name"], d.get("repair_id"))
            return jsonify({"ok": True})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify(kb_api.list_diagnoses())

@app.route("/api/diagnoses/<int:did>", methods=["DELETE"])
def api_del_diag(did):
    kb_api.delete_diagnosis(did); return jsonify({"ok": True})

@app.route("/api/diagnoses/<int:did>/repair", methods=["PUT"])
def api_update_diag_repair(did):
    kb_api.update_diagnosis_repair(did, request.get_json().get("repair_id"))
    return jsonify({"ok": True})

@app.route("/api/diagnoses/<int:did>/characteristics", methods=["GET","POST"])
def api_diag_chars(did):
    if request.method == "POST":
        kb_api.add_diag_char(did, request.get_json()); return jsonify({"ok": True})
    return jsonify(kb_api.get_diag_chars(did))

@app.route("/api/diagnoses/<int:did>/characteristics/<int:dc_id>", methods=["DELETE"])
def api_del_diag_char(did, dc_id):
    kb_api.delete_diag_char(dc_id, did); return jsonify({"ok": True})

# ── KB Validation ─────────────────────────────
@app.route("/api/kb/validate")
def api_kb_validate(): return jsonify(kb_api.validate())

# ── Ollama ────────────────────────────────────
@app.route("/api/ollama/status")
def api_ollama_status(): return jsonify(ollama_api.status())

@app.route("/api/ollama/verify", methods=["POST"])
def api_ollama_verify():
    d = request.get_json(force=True)
    return jsonify(ollama_api.verify(
        d.get("model","llama3"), d.get("diagnosis",""),
        d.get("features",{}), d.get("repair",{}),
        d.get("ml_ranking",[]), d.get("selection_method","")))


if __name__ == "__main__":
    init_db()
    if not ml_model.load():
        print("Обучение модели (первый запуск)...")
        ba, _, _ = ml_model.train(verbose=True)
        print(f"Модель обучена. Balanced accuracy: {ba:.2%}")
    else:
        print("Модель загружена")
    app.run(debug=True, port=5000)
