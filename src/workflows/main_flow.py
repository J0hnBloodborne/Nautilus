from prefect import flow, task
import sys
import os

# Ensure we can import from src (add root to path)
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

# Import your existing logic
from src.ingest_movies import fetch_movies
from src.ingest_shows import fetch_shows
from src.ml.train_model import fetch_data, train_svd, register_model

# --- TASKS ---

@task(name="Ingest Movies", retries=2, retry_delay_seconds=5)
def task_ingest_movies():
    print("Starting Movie Ingestion Task...")
    # Fetch just 1 page for the daily update loop (fast)
    fetch_movies(pages=1) 

@task(name="Ingest TV Shows", retries=2, retry_delay_seconds=5)
def task_ingest_shows():
    print("Starting TV Show Ingestion Task...")
    fetch_shows(pages=1)

@task(name="Retrain Model")
def task_train_model():
    print("Starting SVD Retraining Task...")
    df = fetch_data()
    
    if len(df) < 10:
        print("Not enough data to train. Skipping.")
        return 0.0
        
    model, movie_ids, rmse = train_svd(df)
    
    # Log the metric (Requirement: "Log results")
    print(f"New Model RMSE: {rmse:.4f}")
    
    register_model(rmse)
    return rmse

# --- THE FLOW ---

@flow(name="Nautilus Daily Harvest", log_prints=True)
def main_flow():
    """
    Orchestrates the entire MLOps pipeline.
    1. Ingest New Content
    2. Retrain AI
    3. Report Status
    """
    print("Initiating Daily Harvest Protocol...")
    
    # 1. Ingest Data (Parallel execution possible, but sequential is safer for DB)
    task_ingest_movies()
    task_ingest_shows()
    
    # 2. Train Model
    rmse = task_train_model()
    
    print(f"Workflow Complete. System optimized. RMSE: {rmse:.4f}")

if __name__ == "__main__":
    # Run the flow locally
    main_flow()