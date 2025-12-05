import os
import time
import requests
import argparse
from tqdm import tqdm
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from src.core.models import Movie 

load_dotenv()
API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

BASE_URL = "https://api.themoviedb.org/3"

def fetch_movies(pages=None, fetch_all=False, start_page=1):
    # 1. Get Total Pages
    try:
        init_url = f"{BASE_URL}/movie/popular?api_key={API_KEY}&language=en-US&page=1"
        init_data = requests.get(init_url, timeout=10).json()
        total_available = init_data['total_pages']
    except Exception as e:
        print(f"❌ Connection failed init: {e}")
        return

    limit = min(total_available, 500) 
    if not fetch_all and pages:
        limit = min(pages, limit)
        
    print(f"🎬 Resuming Movie Ingestion: Page {start_page} to {limit}...")
    
    for page in tqdm(range(start_page, limit + 1), desc="Fetching Movies", initial=start_page, total=limit):
        try:
            url = f"{BASE_URL}/movie/popular?api_key={API_KEY}&language=en-US&page={page}"
            # ADDED TIMEOUT
            response = requests.get(url, timeout=10)
            
            if response.status_code != 200:
                print(f"⚠️ Error on page {page}: {response.status_code}")
                time.sleep(1)
                continue
                
            for item in response.json().get('results', []):
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
            time.sleep(0.1) 
            
        except Exception as e:
            print(f"❌ Error on page {page}: {e}")
            session.rollback()
            time.sleep(2) # Wait a bit before retrying

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=5)
    parser.add_argument("--all", action="store_true")
    # ADDED START FLAG
    parser.add_argument("--start", type=int, default=1, help="Page to start from")
    
    args = parser.parse_args()
    
    try:
        fetch_movies(pages=args.pages, fetch_all=args.all, start_page=args.start)
        print("🎉 Movie Ingestion Complete.")
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")