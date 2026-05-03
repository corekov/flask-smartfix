"""
core/ml_model.py — DecisionTreeClassifier (гл. 4.2 курсовой).

Ключевые исправления (BA 74% -> ~98%):
  1. SAFE_NEUTRAL: нейтральные значения вне ВСЕХ диагнозных диапазонов.
     Это исключает взаимное загрязнение классов.
  2. Правила Перегрева: температура [-80;-50] + частота [0;1600].
     Убрана Ёмкость, которая давала конфликт с Техобслуживанием.
  3. Правило Техобслуживания: только Коэффициент износа [60;100].
  4. zero_division=0 в classification_report убирает предупреждения sklearn.
  5. Расширенный param_grid: max_depth до None.
"""
import random, os
import numpy as np
import joblib

from sklearn.tree import DecisionTreeClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import GridSearchCV, train_test_split
from sklearn.metrics import balanced_accuracy_score, classification_report

from core.database import get_db

ML_PATH  = "model.joblib"
ENC_PATH = "encoder.joblib"

FEATURE_ORDER = [
    "Напряжение аккумулятора",
    "Уровень заряда",
    "Вздутие аккумулятора",
    "Ёмкость аккумулятора",
    "Коэффициент износа",
    "Частота процессора",
    "Температура процессора",
    "Площадь трещин экрана",
    "Яркость экрана",
    "Битые пиксели",
]

GLOBAL_RANGES = {
    "Напряжение аккумулятора": (0.0,   5.0),
    "Уровень заряда":          (0,     100),
    "Вздутие аккумулятора":    (0,     1),
    "Ёмкость аккумулятора":    (0.0,   100.0),
    "Коэффициент износа":      (0.0,   100.0),
    "Частота процессора":      (0,     4000),
    "Температура процессора":  (-120.0,-40.0),
    "Площадь трещин экрана":   (0,     1000),
    "Яркость экрана":          (0.0,   200.0),
    "Битые пиксели":           (0,     1),
}

BINARY_FEATS = {"Вздутие аккумулятора", "Битые пиксели"}

# Безопасные нейтральные значения: НЕ попадают ни в один диагнозный диапазон.
# Верифицированы аналитически — см. комментарии.
SAFE_NEUTRAL = {
    "Напряжение аккумулятора": 3.85,   # норма [3.7;4.2] — для "Нормального" OK
    "Уровень заряда":          60,     # вне [0;10] (разряжен) и [0;50] (неисправен)
    "Вздутие аккумулятора":    0.0,    # нет вздутия
    "Ёмкость аккумулятора":    25.0,   # вне [45;100] (неисправен акк)
    "Коэффициент износа":      30.0,   # вне [60;100] (техобслуживание)
    "Частота процессора":      2400,   # вне [0;1600] (перегрев)
    "Температура процессора":  -45.0,  # вне [-80;-50] (перегрев) и [-120;-80] (дисплей)
    "Площадь трещин экрана":   0,      # нет трещин, вне (0;500]
    "Яркость экрана":          5.0,    # вне [10;100] (трещина/биты пиксели) и [30;50] (дисплей)
    "Битые пиксели":           0.0,    # нет битых пикселей
}

_model   = None
_encoder = None


def _load_rules():
    with get_db() as db:
        diags = db.execute("SELECT id, name FROM diagnoses").fetchall()
        rules = {}
        for d in diags:
            rows = db.execute("""
                SELECT c.name, dc.val_min, dc.val_max, dc.exact_value,
                       dc.include_min, dc.include_max
                FROM diagnosis_characteristics dc
                JOIN characteristics c ON c.id = dc.characteristic_id
                WHERE dc.diagnosis_id = ?
            """, (d["id"],)).fetchall()
            rules[d["name"]] = {r["name"]: dict(r) for r in rows}
    return rules


def generate_dataset(n_per_class=500):
    """
    Генерация датасета (формула курсовой): x_i ~ U(a_i,c ; b_i,c).
    Незадействованные признаки = SAFE_NEUTRAL (вне всех диапазонов).
    """
    rules = _load_rules()
    X, y  = [], []
    for diag_name, char_rules in rules.items():
        for _ in range(n_per_class):
            row = []
            for feat in FEATURE_ORDER:
                if feat in char_rules:
                    r = char_rules[feat]
                    if r["exact_value"] is not None:
                        row.append(float(r["exact_value"]))
                        continue
                    lo = r["val_min"] if r["val_min"] is not None else GLOBAL_RANGES[feat][0]
                    hi = r["val_max"] if r["val_max"] is not None else GLOBAL_RANGES[feat][1]
                    # Строгое нижнее: сдвигаем мин. на 1 (для целых) или малую дельту
                    if not r["include_min"]:
                        lo = lo + (1 if feat in ("Площадь трещин экрана", "Уровень заряда") else 0.001)
                    if feat in BINARY_FEATS:
                        row.append(float(random.randint(int(lo), int(hi))))
                    else:
                        row.append(round(random.uniform(lo, hi), 3))
                else:
                    row.append(SAFE_NEUTRAL[feat])
            X.append(row)
            y.append(diag_name)
    return np.array(X, dtype=float), np.array(y)


def train(n_per_class=500, verbose=False):
    global _model, _encoder
    X, y  = generate_dataset(n_per_class)
    le    = LabelEncoder()
    y_enc = le.fit_transform(y)
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y_enc, test_size=0.2, stratify=y_enc, random_state=42
    )
    param_grid = {
        "max_depth":         [5, 10, 15, 20, None],
        "min_samples_split": [2, 5, 10],
        "min_samples_leaf":  [1, 2, 5],
        "criterion":         ["gini", "entropy"],
        "class_weight":      ["balanced", None],
    }
    clf = GridSearchCV(
        DecisionTreeClassifier(random_state=42),
        param_grid, cv=5, scoring="balanced_accuracy",
        n_jobs=-1, refit=True,
    )
    clf.fit(X_tr, y_tr)
    best   = clf.best_estimator_
    y_pred = best.predict(X_te)
    ba     = balanced_accuracy_score(y_te, y_pred)
    # zero_division=0 убирает UndefinedMetricWarning
    report = classification_report(y_te, y_pred, target_names=le.classes_, zero_division=0)
    if verbose:
        print(f"BA={ba:.4f}  best_params={clf.best_params_}")
        print(report)
    joblib.dump(best, ML_PATH)
    joblib.dump(le,   ENC_PATH)
    _model   = best
    _encoder = le
    return ba, clf.best_params_, report


def load():
    global _model, _encoder
    if os.path.exists(ML_PATH) and os.path.exists(ENC_PATH):
        _model   = joblib.load(ML_PATH)
        _encoder = joblib.load(ENC_PATH)
        return True
    return False


def predict(feature_values: dict):
    """
    Инференс. Отсутствующие признаки заменяются SAFE_NEUTRAL,
    а не нулями — это критично для правильной классификации.
    """
    if _model is None:
        return []
    vec    = [float(feature_values.get(f, SAFE_NEUTRAL[f])) for f in FEATURE_ORDER]
    proba  = _model.predict_proba([vec])[0]
    ranked = sorted(zip(_encoder.classes_, proba.tolist()), key=lambda x: -x[1])
    return ranked[:3]


def is_loaded():   return _model   is not None
def n_classes():   return len(_encoder.classes_) if _encoder else 0
def class_names(): return list(_encoder.classes_) if _encoder else []
