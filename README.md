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

---

## Sub-project 2 — Time Series Forecasting (MLOps)

3-day temperature forecast (72h, step 3h = 24 steps) for Côte d'Ivoire, using **Temporal Fusion Transformer (TFT)**.

### Data flow

```
Open-Meteo API
     │ (hourly data)
     ▼
src/data/fetch_data.py
     │ (aggregate 3h → SQLite)
     ▼
data/weather.db ──────────────────────┐
     │                                │
     ▼                                ▼
src/training/train.py         src/inference/predict.py
     │ (TFT + MLflow)                │ (batch, q50)
     ▼                               ▼
model/tft_model.ckpt          data/weather.db
mlruns/ (registry)            (table: predictions)
                                      │
                             src/monitoring/report.py
                                      │
                             monitoring/output/*.png

         api/main.py  (FastAPI)
  GET /predictions          GET /version
  GET /predictions/combined GET /health
```

### SQLite schema (`data/weather.db`)

| Table | Key columns | Description |
|-------|-------------|-------------|
| `weather_data` | timestamp, temperature_2m | Historical 3h aggregated data |
| `predictions` | model_id, generated_at, horizon_step, target_time, predicted | Batch predictions |

### TFT model

| Parameter | Value |
|-----------|-------|
| Encoder length | 24 steps (3 days) |
| Forecast horizon | 24 steps (3 days) |
| Hidden size | 64 |
| LSTM layers | 2 |
| Attention heads | 4 |
| Loss | QuantileLoss [q10, q25, **q50**, q75, q90] |
| Known future features | hour/day/month sin+cos (calendar) |
| Observed features | lag_1/2/3/6/8, rolling_mean_8 |

---

## Installation

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

## Usage — Time Series Pipeline

### Step 1 — Download weather data

```bash
python -m src.data.fetch_data --start 2023-01-01 --end 2025-01-31
```

### Step 2 — Train the model

```bash
python -m src.training.train --start 2023-01-01 --end 2025-01-31
```

Saves `model/tft_model.ckpt`, `model/tft_train_dataset.pkl`, `model/scaler_y.pkl`, and logs to MLflow (`mlruns/`).

### Step 3 — Generate predictions (batch)

```bash
python -m src.inference.predict --date 2025-01-15
```

### Step 4 — Monitoring report

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
| `/predictions/combined?start=...&end=...` | GET | Predictions + actuals (monitoring) |
| `/version` | GET | Software version + model version |
| `/health` | GET | API health check |

```bash
curl "http://localhost:8000/predictions?date=2025-01-15"
curl "http://localhost:8000/predictions/combined?start=2024-12-01&end=2024-12-31"
curl "http://localhost:8000/version"
curl "http://localhost:8000/health"
```

**Version endpoint behaviour**: returns `0.0.0` when running locally, returns the Git commit SHA when built via CI/CD (`GIT_COMMIT_ID` build arg).

---

## Tests

```bash
# Run all tests
pytest tests/ -v

# With coverage report
pytest tests/ -v --cov=src --cov=api --cov-report=term-missing
```

Tests use a temporary SQLite database (full isolation — no impact on `data/weather.db`).

---

## Docker

```bash
# Build
docker build -t temperature-forecast .

# Build with commit ID (as in CI/CD)
docker build --build-arg GIT_COMMIT_ID=$(git rev-parse --short HEAD) \
  -t temperature-forecast .

# Run
docker run -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/model:/app/model \
  temperature-forecast
```

**Layer optimisation**: `requirements.txt` is copied and installed before source code, so the pip layer is cached and not reinstalled when only the code changes.

---

## CI/CD Pipeline (GitHub Actions)

```
git push
   └─► [test] ──────► [build & push GHCR] ──────► [integration-test]
       pytest              docker build                /health
       tests/ -v           push ghcr.io                /version
                           tag: SHA                    /predictions (404)
```

| Job | Description | Depends on |
|-----|-------------|------------|
| `test` | `pytest tests/ -v` | — |
| `build` | Build image + push to `ghcr.io` with SHA tag | `test` |
| `integration-test` | Start container, test `/health`, `/version`, `/predictions` | `build` |

No secrets in plain text: `GITHUB_TOKEN` is used automatically for GHCR authentication.

---

## Project structure

```
Projet_final/
├── notebooks/
│   ├── exploration_multimodale.ipynb    # EDA multimodal
│   ├── classification_images.ipynb      # CNN multi-label
│   ├── classification_textes.ipynb      # NLP multi-label (Bi-LSTM)
│   ├── fusion_multimodale.ipynb         # Early + Joint fusion
│   ├── model_lstm_prophete_serie_temporelle.ipynb  # LSTM/Prophet baseline
│   └── model_tft_serie_temporelle.ipynb            # TFT (modèle retenu)
├── api/
│   └── main.py              # FastAPI — 4 endpoints + logging middleware
├── src/
│   ├── common/
│   │   ├── config.py        # Centralised parameters
│   │   ├── database.py      # SQLite CRUD helpers
│   │   └── logger.py        # Structured logging
│   ├── data/
│   │   └── fetch_data.py    # Open-Meteo download + 3h aggregation
│   ├── training/
│   │   └── train.py         # TFT training pipeline + MLflow
│   ├── inference/
│   │   └── predict.py       # Batch inference (q50) + SQLite save
│   └── monitoring/
│       └── report.py        # Predictions vs actuals report
├── tests/
│   └── test_api.py          # 7 unit + integration tests
├── data/
│   ├── weather.db           # SQLite (weather_data + predictions)
│   └── multimodal/          # Kaggle dataset (images + CSVs)
├── model/
│   ├── tft_model.ckpt       # TFT checkpoint (pytorch-lightning)
│   ├── tft_train_dataset.pkl  # Dataset template for inference
│   ├── scaler_y.pkl         # Target scaler
│   └── registry/            # MLflow model registry
├── monitoring/
│   └── output/              # Generated plots (PNG)
├── mlruns/                  # MLflow experiment tracking
├── .github/
│   └── workflows/ci.yml     # GitHub Actions CI/CD
├── Dockerfile
└── requirements.txt
```
