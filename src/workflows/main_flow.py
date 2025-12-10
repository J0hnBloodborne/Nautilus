from prefect import flow, task
import sys
import os
import requests
from datetime import datetime

# Ensure we can import from src (add root to path)
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

# Import your existing logic
from src.services.ingestion.ingest_movies import fetch_movies
from src.services.ingestion.ingest_shows import fetch_shows
from src.ml.train_model import fetch_data, train_svd, register_model

# Import other ML modules
from src.ml.classification_multilabel_ffnn import train_multilabel_classifier
from src.ml.regression import run_regression
from src.ml.clustering import run_clustering
from src.ml.association import run_association_rules
from src.ml.time_series import run_analysis as run_time_series
from src.ml.recommender_ncf import train_ncf

# --- CONFIG ---
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1315708367736635463/u_g-u_g-u_g"  # Placeholder

# --- TASKS ---

@task(name="Notify Discord", retries=3)
def notify_discord(message: str, status: str = "info"):
    """Sends a notification to Discord."""
    if "u_g" in DISCORD_WEBHOOK_URL:
        print(f"[Mock Discord] {status.upper()}: {message}")
        return

    color = 0x00ff00 if status == "success" else 0xff0000
    if status == "info":
        color = 0x3498db
    
    payload = {
        "embeds": [{
            "title": "Nautilus ML Pipeline",
            "description": message,
            "color": color,
            "timestamp": datetime.utcnow().isoformat()
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    except Exception as e:
        print(f"Failed to send Discord notification: {e}")

@task(name="Ingest Movies", retries=2, retry_delay_seconds=5)
def task_ingest_movies():
    print("Starting Movie Ingestion Task...")
    # Fetch just 1 page for the daily update loop (fast)
    fetch_movies(pages=1) 

@task(name="Ingest TV Shows", retries=2, retry_delay_seconds=5)
def task_ingest_shows():
    print("Starting TV Show Ingestion Task...")
    fetch_shows(pages=1)

@task(name="Train SVD (Legacy)")
def task_train_svd():
    print("Starting SVD Retraining Task...")
    df = fetch_data()
    if len(df) < 10:
        print("Not enough data to train SVD. Skipping.")
        return 0.0
    model, movie_ids, rmse = train_svd(df)
    print(f"New SVD Model RMSE: {rmse:.4f}")
    register_model(rmse)
    return rmse

@task(name="Train Classification (FFNN)")
def task_train_classification():
    print("Starting Classification Task...")
    try:
        train_multilabel_classifier()
        return "Success"
    except Exception as e:
        print(f"Classification failed: {e}")
        return "Failed"

@task(name="Train Regression")
def task_train_regression():
    print("Starting Regression Task...")
    try:
        run_regression()
        return "Success"
    except Exception as e:
        print(f"Regression failed: {e}")
        return "Failed"

@task(name="Train Clustering")
def task_train_clustering():
    print("Starting Clustering Task...")
    try:
        run_clustering()
        return "Success"
    except Exception as e:
        print(f"Clustering failed: {e}")
        return "Failed"

@task(name="Train Association Rules")
def task_train_association():
    print("Starting Association Rules Task...")
    try:
        run_association_rules()
        return "Success"
    except Exception as e:
        print(f"Association rules failed: {e}")
        return "Failed"

@task(name="Train Time Series")
def task_train_time_series():
    print("Starting Time Series Task...")
    try:
        run_time_series()
        return "Success"
    except Exception as e:
        print(f"Time series failed: {e}")
        return "Failed"

@task(name="Train Recommender (NCF)")
def task_train_recommender():
    print("Starting NCF Recommender Task...")
    try:
        train_ncf()
        return "Success"
    except Exception as e:
        print(f"NCF Recommender failed: {e}")
        return "Failed"

# --- THE FLOW ---

@flow(name="Nautilus Daily Harvest", log_prints=True)
def main_flow():
    """
    Orchestrates the entire MLOps pipeline.
    1. Ingest New Content
    2. Retrain All AI Models
    3. Notify Status
    """
    notify_discord("Pipeline Started: Ingesting Data...", "info")
    
    try:
        # 1. Ingestion
        task_ingest_movies()
        task_ingest_shows()
        
        # 2. Training (Parallelizable in theory, sequential here for safety)
        task_train_svd()
        task_train_classification()
        task_train_regression()
        task_train_clustering()
        task_train_association()
        task_train_time_series()
        task_train_recommender()
        
        notify_discord("Pipeline Completed Successfully. All models updated.", "success")
        
    except Exception as e:
        notify_discord(f"Pipeline Failed: {str(e)}", "error")
        raise e

if __name__ == "__main__":
    main_flow()
    # Run the flow locally
    main_flow()