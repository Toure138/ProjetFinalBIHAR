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

BASE_DIR  = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
API_URL   = "http://api:8000"

_DAYS_SHORT  = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
_DAYS_LONG   = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
_MONTHS_FR   = ["", "Jan", "Fév", "Mar", "Avr", "Mai", "Jun", "Jul", "Aoû", "Sep", "Oct", "Nov", "Déc"]


def _get_hour(target_time: str) -> int:
    try:
        return int(target_time[11:13])
    except (ValueError, IndexError):
        return 12


def _temp_class(t: float) -> str:
    if t < 25: return "cold"
    if t < 29: return "mild"
    if t < 32: return "warm"
    return "hot"


def _temp_icon(t: float, hour: int) -> str:
    if 0 <= hour < 6:
        return "🌙"
    if hour == 6:
        return "🌅"
    if hour >= 18:
        return "🌆" if hour < 21 else "🌃"
    # Daytime icon based on temperature
    if t < 25: return "⛅"
    if t < 29: return "🌤️"
    if t < 32: return "☀️"
    return "🔆"


def _period_icon(period_name: str, avg_temp: float) -> str:
    if period_name == "Nuit":        return "🌙"
    if period_name == "Matin":       return _temp_icon(avg_temp, 9)
    if period_name == "Après-midi":  return _temp_icon(avg_temp, 14)
    return "🌆"  # Soir


def _group_predictions(predictions: list) -> list:
    # Group by date
    raw: dict = {}
    for p in predictions:
        dt_str = p["target_time"][:10]
        raw.setdefault(dt_str, []).append(p)

    result = []
    for date_str, slots in raw.items():
        dt    = datetime.strptime(date_str, "%Y-%m-%d")
        temps = [float(s["predicted"]) for s in slots]
        t_min = min(temps)
        t_max = max(temps)
        t_avg = sum(temps) / len(temps)
        span  = (t_max - t_min) or 1.0

        # Enrich each slot
        for s in slots:
            t    = float(s["predicted"])
            hour = _get_hour(s["target_time"])
            s["cls"]     = _temp_class(t)
            s["icon"]    = _temp_icon(t, hour)
            # Bar width: 10% baseline + up to 80% proportional
            s["bar_pct"] = round(10 + (t - t_min) / span * 80)

        # Build 4-period summary
        PERIOD_DEFS = [
            ("Nuit",        lambda h: h < 6),
            ("Matin",       lambda h: 6  <= h < 12),
            ("Après-midi",  lambda h: 12 <= h < 18),
            ("Soir",        lambda h: h >= 18),
        ]
        periods = []
        for pname, hfilter in PERIOD_DEFS:
            pslots = [s for s in slots if hfilter(_get_hour(s["target_time"]))]
            if not pslots:
                continue
            pavg = sum(float(s["predicted"]) for s in pslots) / len(pslots)
            periods.append({
                "name":  pname,
                "avg":   pavg,
                "cls":   _temp_class(pavg),
                "icon":  _period_icon(pname, pavg),
                "slots": pslots,
            })

        result.append({
            "date":        date_str,
            "day_short":   _DAYS_SHORT[dt.weekday()],
            "day_long":    _DAYS_LONG[dt.weekday()],
            "day_num":     dt.strftime("%d"),
            "month_short": _MONTHS_FR[dt.month],
            "t_min":       t_min,
            "t_max":       t_max,
            "t_avg":       t_avg,
            "t_amp":       t_max - t_min,
            "icon":        _temp_icon(t_avg, 12),
            "cls":         _temp_class(t_avg),
            "slots":       slots,
            "periods":     periods,
        })

    return result


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    today     = datetime.utcnow().strftime("%Y-%m-%d")
    days      = []
    error_msg = None

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{API_URL}/predictions?date={today}")
            if resp.status_code == 200:
                data = resp.json()
                days = _group_predictions(data.get("predictions", []))
            else:
                error_msg = "Aucune prévision disponible pour aujourd'hui."
    except Exception as exc:
        error_msg = f"Impossible de joindre l'API : {exc}"

    return templates.TemplateResponse("index.html", {
        "request":   request,
        "today":     today,
        "days":      days,
        "error_msg": error_msg,
    })


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}
