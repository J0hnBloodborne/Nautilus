import os
import time
import requests
import argparse
from tqdm import tqdm
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from src.core.models import Movie 
from typing import Dict, List

load_dotenv()
API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

BASE_URL = "https://api.themoviedb.org/3"

# --- GENRE HELPERS ---
_MOVIE_GENRE_MAP: Dict[int, str] | None = None

def load_genre_map() -> Dict[int, str]:
    """Fetch TMDB movie genre map once and cache."""
    global _MOVIE_GENRE_MAP
    if _MOVIE_GENRE_MAP is not None:
        return _MOVIE_GENRE_MAP
    try:
        url = f"{BASE_URL}/genre/movie/list?api_key={API_KEY}&language=en-US"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        _MOVIE_GENRE_MAP = {g["id"]: g["name"] for g in data.get("genres", [])}
    except Exception:
        _MOVIE_GENRE_MAP = {}
    return _MOVIE_GENRE_MAP

def format_genres(genre_ids: List[int]) -> List[dict]:
    """Return list of {id,name} dicts from TMDB genre ids."""
    genre_map = load_genre_map()
    out = []
    for gid in genre_ids or []:
        name = genre_map.get(gid)
        if name:
            out.append({"id": gid, "name": name})
    return out

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
                
            genre_map = load_genre_map()
            for item in response.json().get('results', []):
                if not session.query(Movie).filter_by(tmdb_id=item['id']).first():
                    genres = format_genres(item.get('genre_ids', []))
                    movie = Movie(
                        title=item['title'],
                        tmdb_id=item['id'],
                        overview=item['overview'],
                        release_date=item.get('release_date'),
                        poster_path=item['poster_path'],
                        popularity_score=item['popularity'],
                        genres=genres,
                        is_downloaded=False
                    )
                    session.add(movie)
            
            session.commit()
            time.sleep(0.1) 
            
        except Exception as e:
            print(f"❌ Error on page {page}: {e}")
            session.rollback()
            time.sleep(2) # Wait a bit before retrying

def backfill_missing_genres(batch_size: int = 200):
    """Fetch genres from TMDB for movies missing genres."""
    genre_map = load_genre_map()
    qs = session.query(Movie).filter((Movie.genres.is_(None)) | (Movie.genres == [])).limit(batch_size).all()
    if not qs:
        print("No movies missing genres.")
        return
    updated = 0
    for movie in qs:
        try:
            url = f"{BASE_URL}/movie/{movie.tmdb_id}?api_key={API_KEY}&language=en-US"
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            g_ids = [g.get('id') for g in data.get('genres', []) if g.get('id') is not None]
            formatted = format_genres(g_ids)
            if formatted:
                movie.genres = formatted
                session.add(movie)
                updated += 1
                if updated % 50 == 0:
                    session.commit()
        except Exception:
            session.rollback()
            continue
    session.commit()
    print(f"Backfilled genres for {updated} movies.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", type=int, default=5)
    parser.add_argument("--all", action="store_true")
    # ADDED START FLAG
    parser.add_argument("--start", type=int, default=1, help="Page to start from")
    parser.add_argument("--backfill-genres", action="store_true", help="Backfill missing genres for existing movies")
    
    args = parser.parse_args()
    
    try:
        if args.backfill_genres:
            backfill_missing_genres()
        else:
            fetch_movies(pages=args.pages, fetch_all=args.all, start_page=args.start)
            print("🎉 Movie Ingestion Complete.")
    except KeyboardInterrupt:
        print("\n🛑 Stopped by user.")