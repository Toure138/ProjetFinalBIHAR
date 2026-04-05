"""
make_pptx.py — Génère le support de présentation PowerPoint du Projet Final MLOps.
Usage : python make_pptx.py
"""
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Cm
import os

# ─── Couleurs ────────────────────────────────────────────────────────────────
C_DARK   = RGBColor(0x1A, 0x1A, 0x2E)   # fond titre
C_BLUE   = RGBColor(0x16, 0x21, 0x3E)   # fond section
C_ACCENT = RGBColor(0x0F, 0x3C, 0x78)   # accent
C_TEAL   = RGBColor(0x0E, 0x86, 0xD4)   # highlight
C_WHITE  = RGBColor(0xFF, 0xFF, 0xFF)
C_LIGHT  = RGBColor(0xF0, 0xF4, 0xF8)
C_GREEN  = RGBColor(0x27, 0xAE, 0x60)
C_ORANGE = RGBColor(0xE6, 0x7E, 0x22)
C_RED    = RGBColor(0xC0, 0x39, 0x2B)

OUT_DIR = "monitoring/output"

prs = Presentation()
prs.slide_width  = Inches(13.33)
prs.slide_height = Inches(7.5)

BLANK = prs.slide_layouts[6]   # layout vide

def add_rect(slide, l, t, w, h, color, alpha=None):
    shape = slide.shapes.add_shape(1, Inches(l), Inches(t), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape

def add_text(slide, text, l, t, w, h, size=18, bold=False, color=C_WHITE,
             align=PP_ALIGN.LEFT, wrap=True, italic=False):
    txb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf  = txb.text_frame
    tf.word_wrap = wrap
    p   = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.size  = Pt(size)
    run.font.bold  = bold
    run.font.color.rgb = color
    run.font.italic = italic
    return txb

def add_image(slide, path, l, t, w, h=None):
    if not os.path.exists(path):
        return
    if h:
        slide.shapes.add_picture(path, Inches(l), Inches(t), Inches(w), Inches(h))
    else:
        slide.shapes.add_picture(path, Inches(l), Inches(t), Inches(w))

def title_slide():
    s = prs.slides.add_slide(BLANK)
    add_rect(s, 0, 0, 13.33, 7.5, C_DARK)
    add_rect(s, 0, 5.2, 13.33, 2.3, C_ACCENT)
    add_text(s, "Projet Final MLOps", 0.6, 1.0, 12, 1.2, size=44, bold=True, align=PP_ALIGN.CENTER)
    add_text(s, "Prévision de Série Temporelle  •  Classification Multimodale",
             0.6, 2.3, 12, 0.7, size=22, color=C_TEAL, align=PP_ALIGN.CENTER)
    add_text(s, "MSc BIHAR 2025-2026  —  ESTIA", 0.6, 3.2, 12, 0.6, size=18,
             color=C_WHITE, align=PP_ALIGN.CENTER)
    add_text(s, "TOURE Abdoul Aziz", 0.6, 3.9, 12, 0.6, size=20, bold=True,
             color=C_WHITE, align=PP_ALIGN.CENTER)
    add_text(s, "M32 Machine Learning II  •  M33 Deep Learning II  •  M27 DevOps",
             0.6, 5.6, 12, 0.6, size=15, color=C_LIGHT, align=PP_ALIGN.CENTER)

def section_slide(title, subtitle=""):
    s = prs.slides.add_slide(BLANK)
    add_rect(s, 0, 0, 13.33, 7.5, C_BLUE)
    add_rect(s, 0, 2.8, 13.33, 0.08, C_TEAL)
    add_text(s, title, 0.6, 2.0, 12, 1.1, size=36, bold=True, align=PP_ALIGN.CENTER)
    if subtitle:
        add_text(s, subtitle, 0.6, 3.3, 12, 0.8, size=20, color=C_TEAL, align=PP_ALIGN.CENTER)
    return s

def content_slide(title, bullets, img_path=None, img_right=True):
    s = prs.slides.add_slide(BLANK)
    add_rect(s, 0, 0, 13.33, 7.5, C_DARK)
    add_rect(s, 0, 0, 13.33, 0.9, C_ACCENT)
    add_text(s, title, 0.3, 0.1, 12.7, 0.75, size=22, bold=True, align=PP_ALIGN.LEFT)

    txt_w = 7.2 if img_path and os.path.exists(img_path) else 12.5
    y = 1.1
    for b in bullets:
        if b.startswith("##"):
            add_text(s, b[2:].strip(), 0.4, y, txt_w, 0.45, size=15, bold=True, color=C_TEAL)
            y += 0.45
        elif b.startswith("#"):
            add_text(s, b[1:].strip(), 0.4, y, txt_w, 0.5, size=17, bold=True, color=C_ORANGE)
            y += 0.5
        elif b == "":
            y += 0.15
        else:
            add_text(s, "  •  " + b, 0.4, y, txt_w, 0.42, size=13, color=C_WHITE)
            y += 0.42

    if img_path and os.path.exists(img_path):
        add_image(s, img_path, 7.7, 1.0, 5.3, 5.8)
    return s

def table_slide(title, headers, rows, note=""):
    from pptx.util import Inches, Pt
    s = prs.slides.add_slide(BLANK)
    add_rect(s, 0, 0, 13.33, 7.5, C_DARK)
    add_rect(s, 0, 0, 13.33, 0.9, C_ACCENT)
    add_text(s, title, 0.3, 0.1, 12.7, 0.75, size=22, bold=True)

    n_cols = len(headers)
    n_rows = len(rows) + 1
    col_w  = [Inches(12.5 / n_cols)] * n_cols
    tbl    = s.shapes.add_table(n_rows, n_cols,
                                Inches(0.4), Inches(1.0),
                                Inches(12.5), Inches(0.5 * n_rows)).table

    for j, h in enumerate(headers):
        cell = tbl.cell(0, j)
        cell.text = h
        cell.fill.solid(); cell.fill.fore_color.rgb = C_ACCENT
        p = cell.text_frame.paragraphs[0]
        p.runs[0].font.bold  = True
        p.runs[0].font.size  = Pt(13)
        p.runs[0].font.color.rgb = C_WHITE
        p.alignment = PP_ALIGN.CENTER
        tbl.columns[j].width = col_w[j]

    for i, row in enumerate(rows):
        bg = RGBColor(0x1E, 0x2A, 0x3A) if i % 2 == 0 else RGBColor(0x16, 0x21, 0x2E)
        for j, val in enumerate(row):
            cell = tbl.cell(i + 1, j)
            cell.text = str(val)
            cell.fill.solid(); cell.fill.fore_color.rgb = bg
            p = cell.text_frame.paragraphs[0]
            p.runs[0].font.size  = Pt(12)
            p.runs[0].font.color.rgb = C_WHITE
            p.alignment = PP_ALIGN.CENTER

    if note:
        add_text(s, note, 0.4, 1.0 + 0.5 * n_rows + 0.1, 12.5, 0.5,
                 size=12, color=C_TEAL, italic=True)
    return s

def image_slide(title, img_path, caption=""):
    s = prs.slides.add_slide(BLANK)
    add_rect(s, 0, 0, 13.33, 7.5, C_DARK)
    add_rect(s, 0, 0, 13.33, 0.9, C_ACCENT)
    add_text(s, title, 0.3, 0.1, 12.7, 0.75, size=22, bold=True)
    if os.path.exists(img_path):
        add_image(s, img_path, 0.5, 1.0, 12.3, 5.6)
    if caption:
        add_text(s, caption, 0.4, 6.75, 12.5, 0.5, size=12, color=C_TEAL, italic=True)
    return s

def two_images_slide(title, img1, img2, cap1="", cap2=""):
    s = prs.slides.add_slide(BLANK)
    add_rect(s, 0, 0, 13.33, 7.5, C_DARK)
    add_rect(s, 0, 0, 13.33, 0.9, C_ACCENT)
    add_text(s, title, 0.3, 0.1, 12.7, 0.75, size=22, bold=True)
    if os.path.exists(img1):
        add_image(s, img1, 0.3, 1.0, 6.1, 5.3)
    if os.path.exists(img2):
        add_image(s, img2, 6.9, 1.0, 6.1, 5.3)
    if cap1:
        add_text(s, cap1, 0.3, 6.4, 6.1, 0.5, size=11, color=C_TEAL, italic=True, align=PP_ALIGN.CENTER)
    if cap2:
        add_text(s, cap2, 6.9, 6.4, 6.1, 0.5, size=11, color=C_TEAL, italic=True, align=PP_ALIGN.CENTER)
    return s

# ════════════════════════════════════════════════════════════════════
# SLIDES
# ════════════════════════════════════════════════════════════════════

# ── SLIDE 1 : Titre ──────────────────────────────────────────────────
title_slide()

# ── SLIDE 2 : Plan ───────────────────────────────────────────────────
content_slide("Plan de la présentation", [
    "#Sous-projet 1 — Classification Multimodale",
    "EDA, prétraitement, modèles images, textes, fusion",
    "",
    "#Sous-projet 2 — Prévision de Série Temporelle",
    "Données météo Côte d'Ivoire, LSTM vs Prophet vs TFT",
    "",
    "#Partie MLOps / DevOps",
    "Architecture, API FastAPI, CI/CD GitHub Actions, Docker, Tests",
    "",
    "#Démonstration API",
])

# ════════════════════════════════════════════════════════════════════
# PARTIE 1 — MULTIMODAL
# ════════════════════════════════════════════════════════════════════

section_slide("PARTIE 1", "Classification Multimodale")

# Spécifications
content_slide("Spécifications & Objectifs — Multimodal", [
    "#Dataset : Kaggle Multi-label Classification Competition 2023",
    "Images + descriptions textuelles (captions)",
    "18 classes (labels 1–19, label 12 absent)",
    "Tâche : prédire PLUSIEURS labels par image (multi-label)",
    "",
    "#Métriques d'évaluation",
    "F1 micro — métrique principale (pondère les classes fréquentes)",
    "F1 macro — sensible aux classes rares",
    "Précision & Rappel — analyse du compromis",
    "Seuil de décision : sigmoid(logits) > 0.5",
    "",
    "#Split : 70% train / 15% val / 15% test",
])

# EDA
image_slide("EDA — Distribution des labels",
    f"{OUT_DIR}/eda_label_distribution.png",
    "Déséquilibre marqué : classes fréquentes > 2000 occ., classes rares < 500 → pos_weight dans BCELoss")

image_slide("EDA — Exemples d'images par label",
    f"{OUT_DIR}/eda_label_5_examples.png",
    "Visualisation de 5 exemples par label pour comprendre la sémantique des classes")

two_images_slide("EDA — Texte & Co-occurrences",
    f"{OUT_DIR}/eda_wordcloud.png",
    f"{OUT_DIR}/eda_cooccurrence.png",
    "Mots fréquents dans les captions",
    "Labels qui co-apparaissent souvent ensemble")

# Prétraitement
content_slide("Prétraitement — Images & Textes", [
    "#Images",
    "Resize 224×224 — taille standard EfficientNet/ImageNet",
    "Normalisation : mean=[0.485,0.456,0.406], std=[0.229,0.224,0.225]",
    "Augmentation (train) : RandomHFlip, RandomCrop, ColorJitter",
    "Val/Test : CenterCrop uniquement (évaluation reproductible)",
    "",
    "#Textes",
    "Nettoyage : minuscules, suppression ponctuation",
    "TF-IDF : max_features=10 000, n-gram (1,2) — pour baseline",
    "Tokenisation vocabulaire top-5000 — pour Bi-LSTM",
    "Padding longueur fixe 64 tokens",
    "",
    "#Labels",
    "MultiLabelBinarizer → vecteur binaire taille 18",
    "pos_weight = N_neg / N_pos par classe — corrige déséquilibre",
])

# Modèles images
content_slide("Modèles Images — 3 architectures", [
    "#1. Baseline CNN  (622 866 params)",
    "Conv(32)→BN→Pool → Conv(64)→BN→Pool → Conv(128)→BN→Pool",
    "→ GAP → Dense(256) → Dropout(0.5) → Dense(18, sigmoid)",
    "",
    "#2. EfficientNetB0 Feature Extractor  (23 058 params entraînables)",
    "EfficientNetB0 pré-entraîné ImageNet GELÉ",
    "Nouvelle tête : Dense(512) → Dropout(0.3) → Dense(18)",
    "",
    "#3. EfficientNetB0 Fine-tuning  (3 178 798 / 4 030 606 params)",
    "3 derniers blocs dégelés — adaptation au domaine",
    "Même tête que FE",
    "",
    "##Paramètres communs",
    "Adam lr=1e-3 | BCEWithLogitsLoss + pos_weight | batch=32 | epochs=20",
])

table_slide("Résultats — Classification Images",
    ["Modèle", "F1 micro", "F1 macro", "Précision", "Rappel"],
    [
        ["Baseline CNN",          "0.2873", "0.2072", "0.1770", "0.7621"],
        ["EfficientNetB0 FE",     "0.4544", "0.3484", "0.3177", "0.7974"],
        ["EfficientNetB0 FT ★",  "0.6665", "0.5553", "0.5748", "0.7930"],
    ],
    "★ Modèle retenu — Gain +37.9 pts F1 micro vs baseline")

two_images_slide("Courbes d'entraînement — Images",
    f"{OUT_DIR}/img_Baseline_CNN_curves.png",
    f"{OUT_DIR}/img_EfficientNetB0_Fine-tuning_curves.png",
    "Baseline CNN — convergence lente",
    "EfficientNetB0 Fine-tuning — meilleure convergence")

image_slide("Comparaison & Grad-CAM",
    f"{OUT_DIR}/img_model_comparison.png",
    "Comparaison F1 micro des 3 modèles")

image_slide("Interprétabilité — Grad-CAM",
    f"{OUT_DIR}/img_gradcam.png",
    "Zones activées par le modèle pour chaque prédiction — visualise ce que le modèle 'regarde'")

# Textes
content_slide("Modèles Textes — 3 architectures", [
    "#1. TF-IDF + LogReg (baseline)",
    "TfidfVectorizer(max_features=10 000, ngram=(1,2))",
    "OneVsRestClassifier(LogisticRegression(C=1.0))",
    "",
    "#2. TF-IDF + MLP",
    "Input(10 000) → Dense(512,relu) → Dropout → Dense(256) → Dense(18)",
    "",
    "#3. Bi-LSTM  (modèle retenu)",
    "Embedding(5000, 128)",
    "→ BiLSTM(128, bidirectionnel) → BiLSTM(64)",
    "→ Dense(128, relu) → Dropout(0.3) → Dense(18, sigmoid)",
    "~2.3M paramètres",
    "",
    "#Interprétabilité : LIME",
    "Mots les plus influents pour chaque prédiction",
])

two_images_slide("Courbes & LIME — Textes",
    f"{OUT_DIR}/text_bilstm_curves.png",
    f"{OUT_DIR}/text_lime_explanation.png",
    "Bi-LSTM — courbes d'entraînement",
    "LIME — mots les plus influents")

# Fusion
section_slide("Fusion Multimodale", "Early Fusion vs Joint Fusion")

content_slide("Architectures de Fusion", [
    "#Early Fusion (concaténation)",
    "Image → EfficientNetB0 gelé → 1280-dim",
    "Texte  → Bi-LSTM gelé       → 256-dim",
    "Concat(1536) → Dense(512) → Dropout → Dense(18)",
    "5 962 510 params entraînables (tête seulement)",
    "",
    "#Joint Fusion (end-to-end + gate attention)",
    "Image → EfficientNetB0 partiellement dégelé",
    "Texte → Bi-LSTM partiellement dégelé",
    "gate = softmax(Linear(1536, 2))",
    "fused = gate[0]×img + gate[1]×text → Dense(18)",
    "5 012 016 / 5 863 824 params entraînables",
])

table_slide("Résultats — Fusion Multimodale",
    ["Modèle", "F1 micro", "F1 macro", "Gain vs image", "Gain vs texte"],
    [
        ["Image seule (EfficientNetB0 FT)", "0.6531", "0.5461", "—", "—"],
        ["Texte seul (Bi-LSTM)",            "0.6575", "0.5926", "—", "—"],
        ["Early Fusion ★",                  "0.7383", "0.6665", "+13.1%", "+12.3%"],
        ["Joint Fusion",                    "0.6761", "0.5760", "+3.5%",  "+2.8%"],
    ],
    "★ Modèle retenu — Early Fusion")

two_images_slide("Analyse Fusion",
    f"{OUT_DIR}/fusion_final_comparison.png",
    f"{OUT_DIR}/fusion_attention_weights.png",
    "Comparaison F1 micro des modèles de fusion",
    "Poids d'attention Joint Fusion — image=1.00, texte=0.00 (collapse)")

image_slide("Exemples de prédictions — Fusion",
    f"{OUT_DIR}/fusion_predictions_examples.png",
    "Exemples de prédictions multi-label sur des images du jeu de test")

# ════════════════════════════════════════════════════════════════════
# PARTIE 2 — SÉRIE TEMPORELLE
# ════════════════════════════════════════════════════════════════════

section_slide("PARTIE 2", "Prévision de Série Temporelle")

content_slide("Spécifications & Objectifs — Série Temporelle", [
    "#Données",
    "Température à 2m, Côte d'Ivoire (6.82°N, 5.28°W)",
    "Source : API Open-Meteo | Période : 2023-01-01 → 2025-12-31",
    "~9 500 observations | Fréquence : 3h (agrégation de 3 valeurs horaires)",
    "",
    "#Objectif",
    "Prévision multi-step : 24 pas × 3h = 3 jours en avance",
    "",
    "#Métriques",
    "MAE (Mean Absolute Error) — métrique principale",
    "RMSE (Root Mean Squared Error)",
    "Évaluation aux 4 horizons : +3h, +24h, +48h, +72h",
    "",
    "#Split : 70% train / 15% val / 15% test (chronologique)",
    "Aucune fuite de données — fit StandardScaler sur train uniquement",
])

content_slide("Feature Engineering — 49 features", [
    "#Features cycliques (6) — connues dans le futur",
    "hour_sin/cos, day_sin/cos, month_sin/cos",
    "Encodage sinusoïdal pour capturer la périodicité sans discontinuité",
    "",
    "#Features temporelles brutes (4)",
    "hour, dayofweek, month, is_weekend",
    "",
    "#Lag features (26)",
    "Lags 1 à 24 (72h), lag 36 (108h), lag 48 (144h)",
    "Capturent l'autocorrélation forte aux pas récents",
    "",
    "#Rolling statistics (10)",
    "Moyenne et écart-type sur fenêtres 3, 6, 8, 12, 24 pas",
    "",
    "#Différences (3)",
    "diff_1, diff_2, diff_8 — taux de variation",
])

content_slide("Architecture LSTM (modèle principal)", [
    "#Architecture",
    "Input : (batch, 24 pas, 49 features)",
    "→ LSTM(128) → Dropout(0.2)",
    "→ LSTM(64)  → Dropout(0.2)",
    "→ LSTM(32)  → Dropout(0.2)",
    "→ Dense(64, ReLU) → Dropout(0.2)",
    "→ Dense(32, ReLU)",
    "→ Dense(24)  ← 24 pas de prévision",
    "",
    "#Entraînement",
    "Optimiseur : Adam (lr=1e-3)",
    "Loss : MSELoss",
    "Batch=32 | max_epochs=100 | EarlyStopping(patience=10)",
    "ReduceLROnPlateau : factor=0.5, patience=5",
    "",
    "#Baseline : Prophet (additif : tendance + saisonnalité)",
    "#Exploratoire : TFT (quantiles 10–90%, attention, VSN)",
])

table_slide("Résultats — MAE par horizon",
    ["Horizon", "Prophet", "LSTM ★", "TFT (q50)"],
    [
        ["+3h  (pas 1)", "1.3770", "0.0434", "1.9465"],
        ["+24h (J+1)",   "1.4100", "0.0506", "3.4261"],
        ["+48h (J+2)",   "1.4137", "0.0537", "0.4167"],
        ["+72h (J+3)",   "1.4200", "0.0503", "1.0303"],
        ["Moyenne",      "1.4107", "0.0516", "1.5763"],
    ],
    "★ LSTM meilleur modèle — MAE 27× inférieur à Prophet et TFT")

image_slide("Monitoring — Prédictions vs Réel",
    f"{OUT_DIR}/report_2026-03-25_2026-03-31.png",
    "Comparaison prédictions LSTM vs températures réelles observées — MAE calculé automatiquement")

# ════════════════════════════════════════════════════════════════════
# PARTIE 3 — MLOps
# ════════════════════════════════════════════════════════════════════

section_slide("PARTIE 3", "Architecture MLOps & DevOps")

content_slide("Architecture de l'Application", [
    "#Flux de données",
    "1. fetch_data.py  → Open-Meteo API → agrégation 3h → weather.db",
    "2. train.py       → LSTM PyTorch → model/registry/ + MLflow",
    "3. predict.py     → batch inference → predictions table (SQLite)",
    "4. api/main.py    → FastAPI → expose les prédictions via REST",
    "5. report.py      → monitoring prédictions vs réel → PNG",
    "",
    "#Base de données SQLite (weather.db)",
    "Table weather_data  : timestamp, temperature_2m",
    "Table predictions   : model_id, generated_at, horizon_step, target_time, predicted",
    "",
    "#MLflow",
    "Tracking URI : mlruns/ (local)",
    "Log params, métriques, artefacts, datasets used",
    "Registered model : lstm_temperature",
])

content_slide("API REST — FastAPI (4 endpoints)", [
    "#GET /predictions?date=YYYY-MM-DD",
    "Retourne les 24 prédictions (72h) pour une date",
    "Réponse : {date, model_id, n_steps, predictions[{horizon_step, target_time, predicted}]}",
    "",
    "#GET /predictions/combined?start=...&end=...",
    "Prédictions + observations réelles (monitoring)",
    "Calcule MAE et biais sur la période",
    "",
    "#GET /version",
    "software_version : '0.0.0' local | commit SHA en CI/CD",
    "model_version : MLflow run_id du dernier modèle",
    "",
    "#GET /health",
    "Retourne {status: ok} — health check Docker/CI",
    "",
    "##Logging automatique : méthode + path + status + latence (ms)",
])

content_slide("Pipeline CI/CD — GitHub Actions", [
    "#Job 1 : test (déclenché sur push + PR)",
    "Setup Python 3.11 + pip cache",
    "pip install -r requirements.txt",
    "pytest tests/ -v --tb=short  → 7 tests",
    "",
    "#Job 2 : build  (push uniquement, dépend de test)",
    "Login ghcr.io avec GITHUB_TOKEN (pas de secret)",
    "docker build --build-arg GIT_COMMIT_ID=${{ github.sha }}",
    "Push :latest + :sha → ghcr.io/[owner]/temperature-forecast",
    "",
    "#Job 3 : integration-test  (dépend de build)",
    "Pull image + docker run -p 8000:8000",
    "Wait 30s jusqu'à /health=ok",
    "Test /health, /version (vérifie SHA), /predictions (→ 404)",
    "docker stop (always — cleanup garanti)",
])

content_slide("Docker — Couches optimisées", [
    "#Base : python:3.11-slim",
    "",
    "#Layer 2 — Dépendances (cachée si requirements.txt inchangé)",
    "COPY requirements.txt .",
    "RUN pip install --no-cache-dir -r requirements.txt",
    "→ Rebuilt UNIQUEMENT si requirements.txt change",
    "",
    "#Layer 3 — Code (rebuild rapide)",
    "COPY src/ api/ model/ data/ ./",
    "→ Rebuild code sans réinstaller les dépendances",
    "",
    "#Runtime",
    "ARG GIT_COMMIT_ID=0.0.0",
    "ENV GIT_COMMIT_ID=${GIT_COMMIT_ID}",
    "EXPOSE 8000",
    'CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]',
])

content_slide("Tests — 7 tests (tous ✅)", [
    "#Tests unitaires",
    "test_health              — GET /health → 200, status=ok",
    "test_version_structure   — champs software_version + model_version présents",
    "test_predictions_date_format — date invalide → 404 ou 422",
    "",
    "#Tests d'intégration",
    "test_predictions_not_found  — date inconnue → 404",
    "test_predictions_ok         — insert DB → GET → 200 + 24 steps corrects",
    "test_combined_not_found     — période vide → 404",
    "test_combined_ok            — prédictions + réel → MAE calculé",
    "",
    "##Isolation : DB SQLite temporaire (tempfile.mkdtemp())",
    "##Résultat : 7 passed in 3.09s",
    "",
    "#Lancer les tests :",
    "pytest tests/ -v",
])

content_slide("Points Durs Rencontrés", [
    "#DLL PyTorch/TensorFlow sur Windows",
    "torch 2.11.0 nightly + TensorFlow nécessitent CUDA/MSVC",
    "→ Réinstallation torch 2.3.0+cpu | Migration LSTM → PyTorch pur",
    "",
    "#MLflow URI invalide sur Windows",
    "C:\\... non reconnu comme scheme valide par MLflow",
    "→ MLFLOW_DIR.as_uri() génère file:///C:/...",
    "",
    "#pytorch-forecasting API changée v1.0",
    "predict() retourne un namedtuple à 5 champs (pas un dict)",
    "→ Accès via .output['prediction']",
    "",
    "#CSV mal formé (captions avec virgules)",
    "ParserError: Expected 3 fields, saw 4",
    "→ on_bad_lines='skip' sur tous les pd.read_csv()",
    "",
    "#numpy 2.4.3 incompatible torch 2.3.0",
    "RuntimeError: Numpy is not available",
    "→ Downgrade numpy==1.26.4",
])

# ── SLIDE FINAL ──────────────────────────────────────────────────────
s = prs.slides.add_slide(BLANK)
add_rect(s, 0, 0, 13.33, 7.5, C_DARK)
add_rect(s, 0, 2.8, 13.33, 0.08, C_TEAL)
add_text(s, "Merci", 0, 1.5, 13.33, 1.5, size=60, bold=True,
         color=C_WHITE, align=PP_ALIGN.CENTER)
add_text(s, "Démonstration API", 0, 3.3, 13.33, 0.8, size=26,
         color=C_TEAL, align=PP_ALIGN.CENTER)
add_text(s, "uvicorn api.main:app  —  http://localhost:8000/docs",
         0, 4.2, 13.33, 0.6, size=16, color=C_LIGHT, align=PP_ALIGN.CENTER, italic=True)
add_text(s, "TOURE Abdoul Aziz  —  MSc BIHAR 2025-2026  —  ESTIA",
         0, 6.5, 13.33, 0.6, size=14, color=C_LIGHT, align=PP_ALIGN.CENTER)

# ════════════════════════════════════════════════════════════════════
prs.save("PRESENTATION_BIHAR2026_TOURE.pptx")
print("OK - Presentation generated: PRESENTATION_BIHAR2026_TOURE.pptx")
print(f"   {len(prs.slides)} slides")
