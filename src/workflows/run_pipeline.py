import sys
import os
import requests
from datetime import datetime
import argparse

# Ensure we can import from src (add root to path)
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

# Import your existing logic
from src.services.ingestion.ingest_movies import fetch_movies
from src.services.ingestion.ingest_shows import fetch_shows
from src.ml.recommender_torch import train_recommender

# --- CONFIG ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# --- TASKS ---

def notify_discord(message: str, status: str = "info"):
    """Sends a notification to Discord."""
    if not DISCORD_WEBHOOK_URL or "u_g" in DISCORD_WEBHOOK_URL:
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

def task_ingest_movies(pages=1, fetch_all=False, start_page=1):
    if fetch_all:
        print("Starting Movie Ingestion Task (ALL Pages)...")
    else:
        print(f"Starting Movie Ingestion Task (Pages={pages}, start={start_page})...")
    fetch_movies(pages=pages, fetch_all=fetch_all, start_page=start_page)

def task_ingest_shows(pages=1, fetch_all=False, start_page=1):
    if fetch_all:
        print("Starting TV Show Ingestion Task (ALL Pages)...")
    else:
        print(f"Starting TV Show Ingestion Task (Pages={pages}, start={start_page})...")
    fetch_shows(pages=pages, fetch_all=fetch_all, start_page=start_page)

def task_train_recommender():
    print("Starting Recommender Task...")
    try:
        train_recommender()
        return "Success"
    except Exception as e:
        print(f"Recommender training failed: {e}")
        return "Failed"

# --- THE FLOW ---

def main_flow(pages=1, fetch_all=False, skip_movies=False, skip_shows=False, start_page=1):
    """
    Orchestrates the entire MLOps pipeline.
    1. Ingest New Content
    2. Retrain Recommender
    3. Notify Status
    """
    msg = "Pipeline Started: Ingesting Data (ALL)" if fetch_all else f"Pipeline Started: Ingesting Data ({pages} pages)"
    notify_discord(msg, "info")
    
    try:
        # 1. Ingestion
        if not skip_movies:
            task_ingest_movies(pages=pages, fetch_all=fetch_all, start_page=start_page)
        else:
            print("Skipping movie ingestion (flag --skip-movies)")

        if not skip_shows:
            task_ingest_shows(pages=pages, fetch_all=fetch_all, start_page=start_page)
        else:
            print("Skipping show ingestion (flag --skip-shows)")
        
        # 2. Training
        task_train_recommender()
        
        notify_discord("Pipeline Completed Successfully. Recommender updated.", "success")
        
    except Exception as e:
        notify_discord(f"Pipeline Failed: {str(e)}", "error")
        raise e

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=1, help="Number of pages to ingest")
    parser.add_argument("--all", action="store_true", help="Ingest ALL pages (capped at 500)")
    parser.add_argument("--start", type=int, default=1, help="Start page for ingestion")
    parser.add_argument("--skip-movies", action="store_true", help="Skip movie ingestion")
    parser.add_argument("--skip-shows", action="store_true", help="Skip show ingestion")
    args = parser.parse_args()
    
    if args.all:
        print("Running pipeline with ALL pages of ingestion...")
    else:
        print(f"Running pipeline with {args.pages} pages of ingestion starting at page {args.start}...")
        
    main_flow(
        pages=args.pages,
        fetch_all=args.all,
        skip_movies=args.skip_movies,
        skip_shows=args.skip_shows,
        start_page=args.start,
    )
