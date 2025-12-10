from prefect import flow, task
import sys
import os

# Ensure we can import from src
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.services.ingestion.ingest_movies import fetch_movies
from src.services.ingestion.ingest_shows import fetch_shows

@task(name="Fetch New Movies")
def task_fetch_movies():
    # Fetch top 5 pages of popular movies to catch new releases
    print("Fetching new popular movies...")
    fetch_movies(pages=5)

@task(name="Fetch New Shows")
def task_fetch_shows():
    # Fetch top 5 pages of popular shows
    print("Fetching new popular shows...")
    fetch_shows(pages=5)

@flow(name="Daily Content Update", log_prints=True)
def update_content_flow():
    """
    Lightweight flow to fetch new popular movies and TV shows.
    Designed to run daily.
    """
    task_fetch_movies()
    task_fetch_shows()

if __name__ == "__main__":
    # Run immediately if executed as script
    update_content_flow()
