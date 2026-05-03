"""core/ollama_api.py — Ollama LLM integration."""
import os, json, requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

def status():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        return {"ok": True, "models": [m["name"] for m in r.json().get("models", [])]}
    except:
        return {"ok": False, "models": []}

def verify(model, diagnosis, features, repair, ml_ranking, method):
    prompt = f"""Ты — эксперт по ремонту смартфонов. Проверь результат диагностики.

ДИАГНОЗ: {diagnosis}
МЕТОД: {method}
ХАРАКТЕРИСТИКИ: {json.dumps(features, ensure_ascii=False)}
ML топ-3: {ml_ranking}
РЕМОНТ: {repair.get("name","")}
ШАГИ: {repair.get("steps",[])}

Заключение по 4 пунктам:
1. Корректность диагноза:
2. Полнота шагов ремонта:
3. Возможные риски:
4. Итоговая рекомендация:
"""
    try:
        resp = requests.post(f"{OLLAMA_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False}, timeout=180)
        data = resp.json()
        text = data.get("response") or data.get("message",{}).get("content","") or "Нет ответа"
        return {"ok": True, "text": text}
    except Exception as e:
        return {"ok": False, "error": str(e)}
