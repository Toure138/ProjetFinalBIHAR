# ─────────────────────────────────────────────────────────────────────────────
# Dockerfile — API de prévision de température
#
# Stratégie de layers optimisée :
#   Layer 1 : image de base Python (change rarement)
#   Layer 2 : dépendances pip (change si requirements.txt change)
#   Layer 3 : code source (change souvent)
#
# Résultat : si seul le code change, pip n'est PAS réinstallé (cache Docker).
# ─────────────────────────────────────────────────────────────────────────────

# ── Layer 1 : image de base ───────────────────────────────────────────────────
FROM python:3.11-slim

# Définir le répertoire de travail dans le conteneur
WORKDIR /app

# ── Layer 2 : dépendances (copier UNIQUEMENT requirements.txt d'abord) ────────
# Si requirements.txt ne change pas, Docker réutilise le cache → pip plus rapide
COPY requirements.txt .

# Préinstaller torch CPU-only AVANT requirements.txt.
# Sans cette étape, pip résout torch>=2.3.0 vers la dernière version (2.11+)
# qui tire 2 Go de librairies CUDA inutiles dans le conteneur.
# Comme torch==2.3.0 est déjà satisfait, requirements.txt ne le réinstalle pas.
RUN pip install --no-cache-dir \
    torch==2.3.0 \
    torchvision==0.18.0 \
    --index-url https://download.pytorch.org/whl/cpu

RUN pip install --no-cache-dir -r requirements.txt

# ── Layer 3 : code source ─────────────────────────────────────────────────────
# Copié en dernier car c'est la partie qui change le plus souvent.
# model/ et data/ sont intentionnellement exclus : ils sont montés en volumes
# par docker-compose.yml (évite de gonfler l'image avec les fichiers lourds).
COPY src/    ./src/
COPY api/    ./api/

# Variable d'environnement : version logicielle (injectée par CI/CD)
# En local → "0.0.0" ; en CI → commit SHA via --build-arg
ARG GIT_COMMIT_ID=0.0.0
ENV GIT_COMMIT_ID=${GIT_COMMIT_ID}

# ── Exposition du port ────────────────────────────────────────────────────────
EXPOSE 8000

# ── Commande de démarrage ─────────────────────────────────────────────────────
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
