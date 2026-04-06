"""
weather_forecast_dag.py — DAG Airflow pour le pipeline météo quotidien.

Exécution : chaque jour à 01:00 UTC
  Task 1 — fetch_data  : POST http://api:8000/pipeline/fetch
  Task 2 — predict     : POST http://api:8000/pipeline/predict

La connexion Airflow 'temperature_api' est configurée via la variable
d'environnement AIRFLOW_CONN_TEMPERATURE_API=http://api:8000
dans docker-compose.yml.

UI Airflow : http://localhost:8081  (admin / admin)
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.http.operators.http import SimpleHttpOperator

default_args = {
    "owner":         "bihar2026",
    "retries":       2,
    "retry_delay":   timedelta(minutes=5),
    "email_on_failure": False,
}

with DAG(
    dag_id="weather_forecast_pipeline",
    description="Fetch données Open-Meteo + prédictions LSTM — quotidien 01:00 UTC",
    schedule_interval="0 1 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["meteo", "lstm", "bihar2026"],
    default_args=default_args,
) as dag:

    fetch_data = SimpleHttpOperator(
        task_id="fetch_data",
        http_conn_id="temperature_api",
        endpoint="/pipeline/fetch",
        method="POST",
        response_check=lambda response: response.status_code == 200,
        log_response=True,
        doc_md="Télécharge les dernières données météo depuis Open-Meteo et les insère dans SQLite.",
    )

    predict = SimpleHttpOperator(
        task_id="predict",
        http_conn_id="temperature_api",
        endpoint="/pipeline/predict",
        method="POST",
        response_check=lambda response: response.status_code == 200,
        log_response=True,
        doc_md="Génère les prévisions LSTM pour les 72h suivantes et les sauvegarde dans SQLite.",
    )

    # Dépendance : fetch d'abord, puis prédiction
    fetch_data >> predict
