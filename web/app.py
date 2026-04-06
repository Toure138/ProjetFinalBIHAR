"""
web/app.py — Interface web de prévision météo.

Appelle l'API FastAPI interne et affiche les prévisions dans une page HTML.

Lancement :
    uvicorn web.app:app --port 8080
"""

from datetime import datetime
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="Météo Web", docs_url=None, redoc_url=None)

BASE_DIR   = Path(__file__).resolve().parent
templates  = Jinja2Templates(directory=str(BASE_DIR / "templates"))

API_URL = "http://api:8000"   # nom du service dans docker-compose


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    predictions = []
    error_msg   = None

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{API_URL}/predictions?date={today}")
            if resp.status_code == 200:
                data        = resp.json()
                predictions = data.get("predictions", [])
            else:
                error_msg = "Aucune prévision disponible pour aujourd'hui."
    except Exception as exc:
        error_msg = f"Impossible de joindre l'API : {exc}"

    return templates.TemplateResponse("index.html", {
        "request":     request,
        "today":       today,
        "predictions": predictions,
        "error_msg":   error_msg,
    })


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}
