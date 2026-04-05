# Support de Présentation — Projet Final MLOps
**MSc BIHAR 2025-2026 — ESTIA**  
**TOURE Abdoul Aziz**

---

## PLAN

1. Sous-projet 1 — Classification Multimodale
2. Sous-projet 2 — Prévision de Série Temporelle
3. Partie MLOps/DevOps — Architecture & Pipeline

---

# PARTIE 1 — CLASSIFICATION MULTIMODALE

---

## 1.1 Spécifications et Objectifs

**Dataset :** Kaggle Multi-label Classification Competition 2023 (Linwei Tao)  
- Images + descriptions textuelles (captions)
- **18 classes** (labels 1–19, label 12 absent)
- Chaque image peut appartenir à **plusieurs classes simultanément**

**Objectif :** Prédire l'ensemble des labels associés à chaque image/texte

**Métriques choisies :**
| Métrique | Formule | Pourquoi |
|----------|---------|----------|
| **F1 micro** | TP / (TP + ½(FP+FN)) sur toutes classes | Pondère les classes fréquentes — métrique principale |
| **F1 macro** | Moyenne des F1 par classe | Sensible aux classes rares |
| **Précision** | TP / (TP + FP) | Qualité des prédictions positives |
| **Rappel** | TP / (TP + FN) | Capacité à détecter tous les labels |

**Seuil de décision :** sigmoid(logits) > 0.5 → label prédit positif

---

## 1.2 Analyse Exploratoire (EDA)

**Split des données :** 70% train / 15% val / 15% test (chronologique/stratifié)

**Déséquilibre des classes :**
- Classes fréquentes (label 1, 3, 8) : > 2000 occurrences
- Classes rares (label 12 absent, label 15, 2) : < 500 occurrences
- Rapport max/min ≈ 10:1 → nécessite `pos_weight` dans la loss

**Distribution des captions :**
- Longueur moyenne : ~8 mots par caption
- Vocabulaire riche mais bruité (virgules → lignes mal formées → `on_bad_lines='skip'`)

**Co-occurrences :** certains labels apparaissent systématiquement ensemble (visualisé par heatmap)

---

## 1.3 Prétraitement

### Images
| Étape | Détail | Justification |
|-------|--------|---------------|
| Resize | 224×224 px | Taille standard EfficientNet/ImageNet |
| Normalisation | mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225] | Statistiques ImageNet pour transfer learning |
| Augmentation (train) | RandomHFlip, RandomCrop, ColorJitter | Réduire le surapprentissage |
| Pas d'augmentation (val/test) | CenterCrop uniquement | Évaluation reproductible |

### Textes
| Étape | Détail | Justification |
|-------|--------|---------------|
| Nettoyage | Minuscules, suppression ponctuation | Normalisation |
| TF-IDF | max_features=10 000, n-gram (1,2) | Représentation sparse pour baseline |
| Tokenisation | Vocabulaire top-5000 mots | Pour le Bi-LSTM |
| Padding | Longueur fixe 64 tokens | Batch uniforme |

### Labels
- `MultiLabelBinarizer` → vecteur binaire de taille 18
- `pos_weight` = (N_neg / N_pos) par classe → corrige le déséquilibre

---

## 1.4 Expérimentations

### Sous-projet Images — 3 modèles comparés

```
Baseline CNN
  Conv(32)→BN→Pool → Conv(64)→BN→Pool → Conv(128)→BN→Pool
  → GAP → Dense(256) → Dropout(0.5) → Dense(18, sigmoid)
  622 866 paramètres

EfficientNetB0 Feature Extractor (FE)
  EfficientNetB0 gelé (4 007 548 params figés)
  → tête entraînable : Dense(512) → Dropout(0.3) → Dense(18, sigmoid)
  23 058 paramètres entraînables

EfficientNetB0 Fine-tuning (FT)
  3 derniers blocs dégelés + nouvelle tête
  3 178 798 paramètres entraînables / 4 030 606 total
```

**Paramètres communs :** Adam lr=1e-3, BCEWithLogitsLoss + pos_weight, batch=32, epochs=20, EarlyStopping patience=5

### Résultats Images
| Modèle | F1 micro | F1 macro | Précision | Rappel |
|--------|----------|----------|-----------|--------|
| Baseline CNN | 0.2873 | 0.2072 | 0.1770 | 0.7621 |
| EfficientNetB0 FE | 0.4544 | 0.3484 | 0.3177 | 0.7974 |
| **EfficientNetB0 FT** | **0.6665** | **0.5553** | **0.5748** | **0.7930** |

**→ Modèle retenu : EfficientNetB0 Fine-tuned** (+37.9 pts F1 micro vs baseline)

**Interprétabilité : Grad-CAM** — zones activées sur les images pour les prédictions

---

### Sous-projet Textes — 3 modèles comparés

```
TF-IDF + LogReg (baseline)
  TfidfVectorizer(max_features=10000, ngram=(1,2))
  + OneVsRestClassifier(LogisticRegression(C=1.0))

TF-IDF + MLP
  Input(10000) → Dense(512,relu) → Dropout(0.3) → Dense(256,relu) → Dense(18,sigmoid)

Bi-LSTM
  Embedding(5000, 128) → BiLSTM(128, bidirectionnel) → BiLSTM(64)
  → Dense(128,relu) → Dropout(0.3) → Dense(18,sigmoid)
  ~2.3M paramètres
```

**Résultats Textes** *(sélectif — voir notebook pour détails complets)*
- Baseline TF-IDF+LogReg : F1 micro ≈ 0.45
- TF-IDF+MLP : F1 micro ≈ 0.55
- **Bi-LSTM : F1 micro ≈ 0.66** (modèle retenu)

**Interprétabilité : LIME** — mots les plus influents par prédiction

---

### Sous-projet Fusion Multimodale — 2 architectures

```
Early Fusion (concaténation)
  Image → EfficientNetB0 gelé → vecteur 1280-dim
  Texte  → Bi-LSTM gelé       → vecteur  256-dim
  Concat(1536) → Dense(512,relu) → Dropout(0.3) → Dense(18,sigmoid)
  5 962 510 paramètres entraînables (tête seulement)

Joint Fusion (end-to-end + attention)
  Image → EfficientNetB0 partiellement dégelé → 1280-dim
  Texte  → Bi-LSTM partiellement dégelé        →  256-dim
  gate = softmax(Linear(1536, 2))
  fused = gate[0]*img_proj + gate[1]*text_proj → Dense(18,sigmoid)
  5 012 016 / 5 863 824 paramètres entraînables
```

### Résultats Fusion
| Modèle | F1 micro | F1 macro | Gain vs image | Gain vs texte |
|--------|----------|----------|---------------|---------------|
| Image seule | 0.6531 | 0.5461 | — | — |
| Texte seul | 0.6575 | 0.5926 | — | — |
| **Early Fusion** | **0.7383** | **0.6665** | **+13.1%** | **+12.3%** |
| Joint Fusion | 0.6761 | 0.5760 | +3.5% | +2.8% |

**→ Modèle retenu : Early Fusion**

**Analyse du Joint Fusion :** attention collapse observé — poids image = 1.000, poids texte = 0.000 → le modèle ignore la modalité textuelle. Cause probable : gradient dominé par la branche image plus riche.

---

# PARTIE 2 — PRÉVISION DE SÉRIE TEMPORELLE

---

## 2.1 Spécifications et Objectifs

**Données :** Température à 2m, Côte d'Ivoire (6.82°N, 5.28°W), API Open-Meteo  
**Période :** 2023-01-01 → 2025-12-31 (~9 500 observations à 3h)  
**Fréquence :** 3h (agrégation : moyenne de 00h–02h, 03h–05h, etc.)  
**Horizon :** **3 jours = 24 pas × 3h**

**Métriques :**
| Métrique | Formule | Horizon évalué |
|----------|---------|----------------|
| MAE | mean(|y - ŷ|) | +3h, +24h, +48h, +72h + global |
| RMSE | √mean((y - ŷ)²) | idem |

---

## 2.2 Analyse Exploratoire

**Patterns identifiés :**
- **Saisonnalité journalière forte** : pic à 14h–15h, minimum à 06h (amplitude ≈ 8°C)
- **Saisonnalité annuelle** : saison sèche (DJF) plus fraîche, saison humide (MAM/SON) plus chaude
- **Tendance** : légère hausse sur 2023–2025 (+0.2°C/an)
- **Autocorrélation** : forte à lag 1 (ρ≈0.97), pic à lag 8 (24h) et lag 56 (7 jours)
- **Anomalies** : quelques outliers (z-score > 3σ) traités par interpolation

**Hypothèses pour la modélisation :**
- Les lags courts (1–8) et les encodages cycliques de l'heure/mois sont les features les plus importantes
- L'horizon de 3 jours reste dans la zone de forte autocorrélation → prédictible

---

## 2.3 Prétraitement

| Étape | Détail | Justification |
|-------|--------|---------------|
| Agrégation 3h | resample("3h").mean() | Requis par le sujet, réduit le bruit |
| Split temporel | 70% train / 15% val / 15% test | Chronologique — pas de fuite de données |
| Normalisation | StandardScaler (fit sur train uniquement) | Évite la fuite val→train |
| Feature engineering | 49 features (lags, rolling, cycliques) | Explicite les patterns pour le LSTM |
| Séquences | Fenêtre glissante 24 pas → 24 pas à prédire | Format multi-step |

**49 features :** 6 cycliques + 4 temporelles + 26 lags (1–24, 36, 48) + 10 rolling (mean/std × 5 fenêtres) + 3 diff

---

## 2.4 Expérimentations

### 3 modèles comparés

**Prophet (baseline statistique)**
- Modèle additif tendance + saisonnalité journalière/hebdomadaire/annuelle
- Évaluation rolling (fenêtre 24h)
- Aucun feature engineering requis

**LSTM multi-step (modèle principal)**
```
Input (24 pas × 49 features)
→ LSTM(128) → Dropout(0.2)
→ LSTM(64)  → Dropout(0.2)
→ LSTM(32)  → Dropout(0.2)
→ Dense(64, ReLU) → Dropout(0.2)
→ Dense(32, ReLU)
→ Dense(24)   ← 24 pas de prévision
```
Adam lr=1e-3, MSELoss, batch=32, max_epochs=100, EarlyStopping(patience=10), ReduceLROnPlateau(factor=0.5)

**TFT — Temporal Fusion Transformer (exploratoire)**
- Hidden size=64, LSTM layers=2, Attention heads=4, Dropout=0.1
- QuantileLoss [q10, q25, q50, q75, q90]
- Avantage : intervalles de confiance + interprétabilité native (VSN, attention)

---

## 2.5 Résultats

### MAE par horizon (jeu de test)
| Horizon | Prophet | LSTM | TFT (q50) | Meilleur |
|---------|---------|------|-----------|----------|
| +3h  (pas 1) | 1.3770 | **0.0434** | 1.9465 | LSTM |
| +24h (J+1)   | 1.4100 | **0.0506** | 3.4261 | LSTM |
| +48h (J+2)   | 1.4137 | **0.0537** | 0.4167 | LSTM |
| +72h (J+3)   | 1.4200 | **0.0503** | 1.0303 | LSTM |
| **Moyenne**  | 1.4107 | **0.0516** | 1.5763 | **LSTM** |

### RMSE global
| Prophet | LSTM | TFT |
|---------|------|-----|
| 1.8695 | **0.0652** | 1.8644 |

**→ LSTM est le meilleur modèle** : MAE 27× inférieur au Prophet, 30× inférieur au TFT

**Pourquoi LSTM > TFT ici ?** Le feature engineering explicite (74 features dans le notebook) fournit au LSTM toute l'information que le TFT doit découvrir seul. Avec plus de données ou moins d'ingénierie, le TFT rattraperait son retard.

**Avantage unique du TFT :** intervalles de confiance (q10–q90) + importance des variables (Variable Selection Networks)

---

# PARTIE 3 — MLOps / DevOps

---

## 3.1 Architecture de l'Application

```
┌─────────────────────────────────────────────────────────────┐
│                     FLUX DE DONNÉES                         │
│                                                             │
│  Open-Meteo API                                             │
│       │                                                     │
│       ▼                                                     │
│  fetch_data.py ──► aggregate_3h() ──► weather.db           │
│                                         │                   │
│                                         ▼                   │
│                                    train.py                 │
│                                    (LSTM PyTorch)           │
│                                         │                   │
│                                    ┌────┴────┐              │
│                                    │  MLflow │              │
│                                    │ registry│              │
│                                    └────┬────┘              │
│                                         │                   │
│                                   model/registry/           │
│                                    lstm_model.pth           │
│                                    scaler.pkl               │
│                                         │                   │
│                                         ▼                   │
│                                    predict.py               │
│                                    (batch inference)        │
│                                         │                   │
│                                         ▼                   │
│                                    predictions table        │
│                                    (weather.db)             │
│                                         │                   │
│                                         ▼                   │
│                              ┌─────────────────┐            │
│                              │   FastAPI        │            │
│                              │  api/main.py     │            │
│                              │                  │            │
│                              │ GET /predictions │            │
│                              │ GET /predictions │            │
│                              │     /combined    │            │
│                              │ GET /version     │            │
│                              │ GET /health      │            │
│                              └────────┬─────────┘            │
│                                       │                     │
│                              report.py (monitoring)         │
│                              monitoring/output/*.png        │
└─────────────────────────────────────────────────────────────┘
```

---

## 3.2 Endpoints API (FastAPI)

### GET /predictions?date=YYYY-MM-DD
Retourne les 24 prédictions (72h) générées pour une date.
```json
{
  "date": "2026-03-31",
  "model_id": "2a3aedadbb6748d6a58d8d2ec3b78e97",
  "n_steps": 24,
  "predictions": [
    {"horizon_step": 1, "target_time": "2026-03-31T03:00", "predicted": 27.4},
    ...
  ]
}
```

### GET /predictions/combined?start=...&end=...
Prédictions + observations réelles (monitoring).
```json
{
  "summary": {"n_points_with_actual": 48, "mae": 0.89, "bias": -0.12},
  "data": [
    {"target_time": "...", "predicted": 27.4, "actual": 27.1, "error": 0.3},
    ...
  ]
}
```

### GET /version
```json
{
  "software_version": "0.0.0",     // commit SHA en CI/CD
  "model_version": "2a3aedad..."   // MLflow run_id
}
```

### GET /health
```json
{"status": "ok"}
```

---

## 3.3 Pipeline CI/CD (GitHub Actions)

```
Push sur main
     │
     ▼
┌─────────────────────────────────────────────┐
│  Job 1 : test                                │
│  ─────────────────────────────────────────  │
│  1. Checkout code                            │
│  2. Setup Python 3.11 (cache pip)            │
│  3. pip install -r requirements.txt          │
│  4. mkdir data/ model/registry/ monitoring/  │
│  5. pytest tests/ -v --tb=short              │
│     → 7 tests unitaires + intégration        │
└──────────────────┬──────────────────────────┘
                   │ succès
                   ▼
┌─────────────────────────────────────────────┐
│  Job 2 : build (push uniquement)             │
│  ─────────────────────────────────────────  │
│  1. Checkout code                            │
│  2. Login ghcr.io (GITHUB_TOKEN)             │
│  3. docker build --build-arg                 │
│       GIT_COMMIT_ID=${{ github.sha }}        │
│  4. Push image :latest + :sha               │
│     ghcr.io/[owner]/temperature-forecast    │
└──────────────────┬──────────────────────────┘
                   │ succès
                   ▼
┌─────────────────────────────────────────────┐
│  Job 3 : integration-test (push uniquement)  │
│  ─────────────────────────────────────────  │
│  1. Pull image depuis GHCR                   │
│  2. docker run -d -p 8000:8000               │
│  3. wait (max 30s) jusqu'à /health=ok        │
│  4. Test /health        → "ok"               │
│  5. Test /version       → contient SHA       │
│  6. Test /predictions   → 404 (pas de data)  │
│  7. docker stop (always)                     │
└─────────────────────────────────────────────┘
```

**Sécurité :** aucun secret en clair — GITHUB_TOKEN auto-généré par GitHub Actions

---

## 3.4 Docker

**Optimisation des couches :**
```dockerfile
FROM python:3.11-slim          # Layer 1 : base légère

WORKDIR /app

COPY requirements.txt .        # Layer 2 : dépendances
RUN pip install --no-cache-dir -r requirements.txt
# ↑ Rebuild UNIQUEMENT si requirements.txt change

COPY src/ api/ model/ data/ ./ # Layer 3 : code + artefacts
# ↑ Rebuild uniquement si le code change (sans réinstaller les deps)

ARG GIT_COMMIT_ID=0.0.0
ENV GIT_COMMIT_ID=${GIT_COMMIT_ID}

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 3.5 Logging et Monitoring

**Logging (chaque endpoint) :**
```
2026-04-01 09:15:32 | INFO | api.main | GET /predictions → 200 (12.3 ms)
2026-04-01 09:15:45 | INFO | api.main | GET /version → 200 (1.1 ms)
2026-04-01 09:16:02 | WARNING | api.main | GET /predictions → 404 (2.4 ms)
```
- Format : `timestamp | level | module | méthode path → status (latence ms)`
- Niveaux : INFO (succès), WARNING (404), ERROR (500)

**Monitoring :**
- `src/monitoring/report.py` : compare prédictions vs réel (MAE, RMSE, biais)
- Génère un graphique PNG dans `monitoring/output/`
- Accessible via `GET /predictions/combined`

---

## 3.6 Tests (7 tests — tous passent ✅)

```
pytest tests/ -v
✅ test_health                  — GET /health → 200, status=ok
✅ test_version_structure       — GET /version → champs software_version + model_version
✅ test_predictions_not_found   — GET /predictions date inconnue → 404
✅ test_predictions_ok          — Insertion DB + GET /predictions → 200 + 24 steps
✅ test_combined_not_found      — GET /combined période vide → 404
✅ test_combined_ok             — Données insérées → GET /combined → MAE calculé
✅ test_predictions_date_format — Date invalide → 404 ou 422

7 passed in 3.09s
```

**Isolation :** chaque test utilise une base SQLite temporaire (`tempfile.mkdtemp()`) — aucun impact sur la prod.

---

## 3.7 Workflow de Reproduction

```bash
# 1. Installation
pip install -r requirements.txt

# 2. Récupération des données
python -m src.data.fetch_data --start 2023-01-01 --end 2025-12-31

# 3. Entraînement
python -m src.training.train --start 2023-01-01 --end 2025-12-31

# 4. Génération des prédictions
python -m src.inference.predict --date 2026-04-01

# 5. Démarrage de l'API
uvicorn api.main:app --host 0.0.0.0 --port 8000

# 6. Tests
pytest tests/ -v

# 7. Monitoring
python -m src.monitoring.report --start 2026-03-25 --end 2026-04-01
```

---

## Points Durs Rencontrés

| Problème | Cause | Solution |
|----------|-------|----------|
| `torch c10.dll` ne charge pas | torch 2.11.0 (nightly) nécessite CUDA | Réinstallation torch 2.3.0+cpu |
| `TensorFlow DLL` idem | TF nécessite MSVC runtimes | Migration LSTM vers PyTorch pur |
| MLflow URI invalide sur Windows | `C:\...` non reconnu comme scheme | `.as_uri()` → `file:///C:/...` |
| pytorch-forecasting `predict()` → namedtuple | API changée en v1.0 | Accès via `.output['prediction']` |
| CSV mal formé | Captions contiennent des virgules | `on_bad_lines='skip'` |
| `numpy 2.4.3` incompatible torch 2.3.0 | Version trop récente | Downgrade `numpy==1.26.4` |

---

*Support généré le 2026-04-05 — TOURE Abdoul Aziz — MSc BIHAR ESTIA*
