FROM python:3.11-slim
WORKDIR /app

# Dépendances légères uniquement (pas de torch)
RUN pip install --no-cache-dir fastapi==0.115.0 uvicorn[standard]==0.30.6 httpx==0.27.0 jinja2==3.1.6

COPY web/ ./web/

EXPOSE 8080
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8080"]
