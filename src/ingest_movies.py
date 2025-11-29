import os
import time
import requests
import argparse
from tqdm import tqdm
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from src.models import Movie  # Absolute import assuming running as module

load_dotenv()
API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

BASE_URL = "https://api.themoviedb.org/3"

def fetch_movies(pages=None, fetch_all=False):
    # 1. Get Total Pages first
    init_url = f"{BASE_URL}/movie/popular?api_key={API_KEY}&language=en-US&page=1"
    init_data = requests.get(init_url).json()
    total_available = init_data['total_pages']
    
    # Cap at 500 because TMDB popular list usually caps there for public API
    limit = min(total_available, 500) 
    
    if not fetch_all and pages:
        limit = min(pages, limit)
        
    print(f"Starting Movie Ingestion: Target {limit} pages...")
    
    for page in tqdm(range(1, limit + 1), desc="Fetching Movies"):
        try:
            url = f"{BASE_URL}/movie/popular?api_key={API_KEY}&language=en-US&page={page}"
            response = requests.get(url)
            
            if response.status_code != 200:
                print(f"⚠️ Error on page {page}: {response.status_code}")
                continue
                
            for item in response.json().get('results', []):
                # Upsert Logic (Check if exists)
                if not session.query(Movie).filter_by(tmdb_id=item['id']).first():
                    movie = Movie(
                        title=item['title'],
                        tmdb_id=item['id'],
                        overview=item['overview'],
                        release_date=item.get('release_date'),
                        poster_path=item['poster_path'],
                        popularity_score=item['popularity'],
                        is_downloaded=False
                    )
                    session.add(movie)
            
            session.commit()
            time.sleep(0.1) # Respect Rate Limit
            
        except Exception as e:
            print(f"Critical Error on page {page}: {e}")
            session.rollback()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Movies from TMDB")
    parser.add_argument("--pages", type=int, default=5, help="Number of pages to fetch")
    parser.add_argument("--all", action="store_true", help="Fetch MAXIMUM allowed pages (usually 500)")
    
    args = parser.parse_args()
    
    try:
        fetch_movies(pages=args.pages, fetch_all=args.all)
        print("Movie Ingestion Complete.")
    except KeyboardInterrupt:
        print("\nStopped by user.")