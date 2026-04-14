# SmartFix — Система диагностики смартфонов

## Структура проекта
```
smartfix/
├── app.py                 # Flask бэкенд + SQLite + Ollama API
├── requirements.txt
├── smartfix.db            # SQLite БД (создаётся автоматически)
├── templates/
│   └── index.html         # Основной HTML шаблон
└── static/
    ├── css/style.css      # Стили
    └── js/app.js          # Логика фронтенда
```

## Запуск

### 1. Установить зависимости
```bash
pip install -r requirements.txt
```

### 2. Запустить Flask
```bash
python app.py
```
Открыть: http://localhost:5000

### 3. Ollama (опционально)
```bash
# Установить Ollama: https://ollama.com
ollama pull llama3        # или mistral, gemma2 и др.
ollama serve              # запустить сервис
```

Переменные окружения:
- `OLLAMA_URL` — адрес Ollama (по умолчанию: http://localhost:11434)
- `OLLAMA_MODEL` — модель (по умолчанию: llama3)

## База данных SQLite
При первом запуске автоматически создаётся `smartfix.db` и заполняется
начальными знаниями из курсовой работы (все 7 диагнозов, 10 характеристик, 6 ремонтов).
