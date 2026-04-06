# AI Project — Multimodal Classification & Time Series Forecasting

MSc BIHAR, ESTIA 2025-2026 — Projet final de mise en situation professionnelle.

Two sub-projects:
1. **Multimodal classification** — multi-label classification on images and text, with fusion
2. **Time series forecasting** — 3-day temperature forecast with full MLOps pipeline

---

## Sub-project 1 — Multimodal Classification

### Dataset

Kaggle: [Multi-label Classification Competition 2023 (Linwei Tao)](https://www.kaggle.com/datasets/linweicao/multi-label-classification-competition-2023)

Download and extract to `data/multimodal/`:

```bash
pip install kaggle
kaggle datasets download -d linweicao/multi-label-classification-competition-2023
unzip multi-label-classification-competition-2023.zip -d data/multimodal/
```

Expected layout:
```
data/multimodal/
├── images/        # *.jpg
├── train.csv      # ImageID, Caption, Labels
└── test.csv       # ImageID, Caption
```

### Notebooks

| Notebook | Description |
|----------|-------------|
| `notebooks/exploration_multimodale.ipynb` | EDA — distribution des labels, word cloud, co-occurrences, split 70/15/15 |
| `notebooks/classification_images.ipynb` | CNN baseline → EfficientNetB0 feature extractor → fine-tuning, Grad-CAM |
| `notebooks/classification_textes.ipynb` | TF-IDF + LR (baseline) → MLP → Bi-LSTM, LIME |
| `notebooks/fusion_multimodale.ipynb` | Early fusion (concat features) + Joint fusion end-to-end (gate attention) |

**Run order**: EDA → Images → Textes → Fusion (the EDA notebook saves the train/val/test splits used by all other notebooks).

### Architecture multimodale

```
Images (224×224)                    Captions (texte)
       │                                   │
EfficientNetB0                         Bi-LSTM
(3 derniers blocs fine-tunés)      (embeddings appris)
       │ 1280-dim                          │ 256-dim
       └─────────────┬────────────────────┘
                     │
              Early Fusion              Joint Fusion
         (concat + MLP gelé)      (gate attention end-to-end)
                     │                        │
              Classifieur              Classifieur
              (18 classes)             (18 classes)
                  sigmoid                 sigmoid
```

### Résultats classification

| Modèle | F1 (micro) |
|--------|-----------|
| CNN Baseline | 0.2873 |
| EfficientNet Feature Extractor | 0.4544 |
| EfficientNet Fine-tuning | 0.6665 |
| **Early Fusion (retenu)** | **0.7383** |
| Joint Fusion | 0.6761 |

---

## Sub-project 2 — Time Series Forecasting (MLOps)

3-day temperature forecast (72h, step 3h = 24 steps) for Côte d'Ivoire, using **LSTM (PyTorch)**.

### Architecture microservices

```
Airflow (01:00 UTC)
  └─► POST /pipeline/fetch   ──► src/data/fetch_data.py   ──► weather.db
  └─► POST /pipeline/predict ──► src/inference/predict.py ──► weather.db
                                                                    │
                                               ┌────────────────────┤
                                               ▼                    ▼
                                        api/main.py           web/app.py
                                   GET /predictions       GET /  (HTML)
                                   GET /metrics      Prometheus ──► Grafana
```

### Data flow

```
Open-Meteo API
     │ (données horaires)
     ▼
src/data/fetch_data.py  (agrégation 3h → SQLite)
     │
     ▼
data/weather.db
     │                        │
     ▼                        ▼
src/training/train.py   src/inference/predict.py
  (LSTM + MLflow)         (batch 24 pas)
     │                        │
model/registry/         data/weather.db
  lstm_model.pth          (table: predictions)
  scaler.pkl                   │
  lstm_config.pkl       src/monitoring/report.py
                              + Prometheus gauges
                              + Grafana dashboard
```

### SQLite schema (`data/weather.db`)

| Table | Key columns | Description |
|-------|-------------|-------------|
| `weather_data` | timestamp, temperature_2m | Historical 3h aggregated data |
| `predictions` | model_id, generated_at, horizon_step, target_time, predicted | Batch predictions |

### LSTM model

| Parameter | Value |
|-----------|-------|
| Sequence length | 24 steps (3 days) |
| Forecast horizon | 24 steps (3 days) |
| LSTM layers | 3 (128 → 64 → 32 units) |
| Dense layers | 2 (64 → 32 units) |
| Dropout | 0.2 |
| Features | 49 (lags 1-48, rolling stats, cyclical, diff) |
| Loss | MSE |
| Optimizer | Adam (lr=1e-3) |
| Early stopping | patience=10 |

### Résultats séries temporelles

| Modèle | MAE |
|--------|-----|
| Prophet | ~1.5 |
| TFT | 1.5763 |
| **LSTM (retenu)** | **0.0516** |

---

## Installation (développement local)

```bash
# 1. Clone the repo
git clone <url>
cd Projet_final

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Usage — Pipeline manuel (local)

### Step 1 — Download weather data

```bash
python -m src.data.fetch_data --start 2023-01-01 --end 2025-01-31
```

### Step 2 — Train the model

```bash
python -m src.training.train --start 2023-01-01 --end 2025-01-31
```

### Step 3 — Generate predictions

```bash
python -m src.inference.predict --date 2025-01-15
```

### Step 4 — Monitoring report (CLI)

```bash
python -m src.monitoring.report --start 2024-12-01 --end 2024-12-31
```

### Step 5 — Start the API

```bash
uvicorn api.main:app --reload --port 8000
```

Interactive docs: http://localhost:8000/docs

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/predictions?date=YYYY-MM-DD` | GET | 24 predictions for a given date |
| `/predictions/combined?start=...&end=...` | GET | Predictions + actuals |
| `/monitoring/data?days=7` | GET | Raw data for Grafana (time_ms, predicted, actual, error) |
| `/monitoring/refresh` | GET | Force Prometheus gauge recalculation |
| `/pipeline/fetch` | POST | Trigger fetch_data (called by Airflow) |
| `/pipeline/predict` | POST | Trigger predict (called by Airflow) |
| `/version` | GET | Software + model version |
| `/health` | GET | Health check |
| `/metrics` | GET | Prometheus metrics |

---

## Stack complète — Docker Compose

```bash
docker compose down && docker compose up --build
```

| Service | URL | Identifiants | Rôle |
|---------|-----|-------------|------|
| **Web météo** | http://localhost:8080 | — | Interface 3 jours (HTML) |
| **Airflow UI** | http://localhost:8081 | admin / admin | Orchestration DAG |
| API FastAPI | http://localhost:8000 | — | REST + Prometheus |
| Grafana | http://localhost:3000 | admin / admin | Dashboard monitoring |
| Prometheus | http://localhost:9090 | — | Métriques |

### Services Docker

```
api            ← FastAPI (LSTM, SQLite, métriques)
web            ← Interface météo HTML (Dockerfile léger)
airflow-webserver  ← UI Airflow
airflow-scheduler  ← Exécution des DAGs
postgres       ← Base de métadonnées Airflow
prometheus     ← Scrape /metrics toutes les 15s
grafana        ← Dashboard auto-provisionné
```

### Automatisation Airflow

Le DAG `weather_forecast_pipeline` s'exécute chaque jour à **01:00 UTC** :

```
fetch_data  →  predict
  (POST /pipeline/fetch)   (POST /pipeline/predict)
```

- Gestion des retries (2 tentatives, délai 5 min)
- Logs visibles dans l'UI Airflow
- Déclenchement manuel possible via le bouton ▶ dans l'UI

---

## Monitoring — Grafana

Le dashboard **Temperature Forecast API** est provisionné automatiquement.

**Section Monitoring modèle :**
- MAE / RMSE / Biais (jauges colorées vert/jaune/rouge)
- Courbe Predicted vs Actual (orange pointillé vs bleu)
- Courbe Erreur (Predicted − Actual)
- Rafraîchissement automatique toutes les heures

**Section Monitoring API :**
- Requêtes/seconde par endpoint
- Latence p50 / p95 / p99
- Taux d'erreurs 4xx/5xx
- Status UP/DOWN

---

## Tests

```bash
pytest tests/ -v
pytest tests/ -v --cov=src --cov=api --cov-report=term-missing
```

---

## Docker (image API seule)

```bash
docker build -t temperature-forecast .
docker run -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/model:/app/model \
  temperature-forecast
```

---

## CI/CD Pipeline (GitHub Actions)

```
git push
   └─► [test] ──► [build & push GHCR] ──► [integration-test]
       pytest        docker build             /health /version
                     push ghcr.io             /predictions (404)
```

---

## Project structure

```
Projet_final/
├── notebooks/
│   ├── exploration_multimodale.ipynb
│   ├── classification_images.ipynb
│   ├── classification_textes.ipynb
│   ├── fusion_multimodale.ipynb
│   ├── model_lstm_prophete_serie_temporelle.ipynb
│   └── model_tft_serie_temporelle.ipynb
├── api/
│   └── main.py              # FastAPI — REST + Prometheus + pipeline triggers
├── web/
│   ├── Dockerfile           # Image légère (sans torch)
│   ├── app.py               # Interface météo HTML (port 8080)
│   └── templates/index.html # Page prévisions 3 jours
├── dags/
│   └── weather_forecast_dag.py  # DAG Airflow (fetch >> predict, 01:00 UTC)
├── src/
│   ├── common/
│   │   ├── config.py
│   │   ├── database.py
│   │   └── logger.py
│   ├── data/
│   │   └── fetch_data.py
│   ├── training/
│   │   └── train.py
│   ├── inference/
│   │   └── predict.py
│   └── monitoring/
│       ├── report.py
│       ├── prometheus/prometheus.yml
│       └── grafana/
│           ├── dashboards/temperature_api.json
│           └── provisioning/
├── tests/
│   └── test_api.py
├── data/
│   ├── weather.db
│   └── multimodal/
├── model/
│   └── registry/            # lstm_model.pth + scalers
├── monitoring/
│   └── output/              # PNG reports (CLI)
├── mlruns/
├── .github/
│   └── workflows/ci.yml
├── docker-compose.yml       # 7 microservices
├── Dockerfile               # Image API principale
└── requirements.txt
```
