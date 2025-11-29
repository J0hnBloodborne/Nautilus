import os
import time
import requests
import argparse
from tqdm import tqdm
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from src.models import TVShow, Season, Episode

load_dotenv()
API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

BASE_URL = "https://api.themoviedb.org/3"

def fetch_shows(pages=None, fetch_all=False):
    init_url = f"{BASE_URL}/tv/popular?api_key={API_KEY}&language=en-US&page=1"
    init_data = requests.get(init_url).json()
    total_available = init_data['total_pages']
    
    limit = min(total_available, 500)
    if not fetch_all and pages:
        limit = min(pages, limit)

    print(f"Starting TV Show Ingestion: Target {limit} pages...")
    
    for page in tqdm(range(1, limit + 1), desc="Fetching Pages"):
        url = f"{BASE_URL}/tv/popular?api_key={API_KEY}&language=en-US&page={page}"
        data = requests.get(url).json()
        
        for item in data.get('results', []):
            try:
                # 1. Check/Create Show
                show = session.query(TVShow).filter_by(tmdb_id=item['id']).first()
                if not show:
                    show = TVShow(
                        title=item['name'],
                        tmdb_id=item['id'],
                        overview=item['overview'],
                        poster_path=item['poster_path'],
                        popularity_score=item['popularity']
                    )
                    session.add(show)
                    session.commit()
                    
                    # 2. Deep Fetch Seasons (Only for new shows)
                    _fetch_details(show)
            except Exception as e:
                print(f"Skipping show {item.get('name')}: {e}")
                session.rollback()
                
        time.sleep(0.2)

def _fetch_details(show):
    # Fetch Show Details
    url = f"{BASE_URL}/tv/{show.tmdb_id}?api_key={API_KEY}&language=en-US"
    details = requests.get(url).json()
    
    for s_meta in details.get('seasons', []):
        s_num = s_meta['season_number']
        
        # Create Season
        season = Season(
            show_id=show.id,
            season_number=s_num,
            name=s_meta['name'],
            air_date=s_meta['air_date']
        )
        session.add(season)
        session.commit()
        
        # Fetch Episodes
        ep_url = f"{BASE_URL}/tv/{show.tmdb_id}/season/{s_num}?api_key={API_KEY}&language=en-US"
        ep_data = requests.get(ep_url).json()
        
        for ep in ep_data.get('episodes', []):
            episode = Episode(
                season_id=season.id,
                episode_number=ep['episode_number'],
                title=ep['name'],
                overview=ep['overview'],
                air_date=ep.get('air_date'),
                still_path=ep.get('still_path')
            )
            session.add(episode)
        session.commit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest TV Shows")
    parser.add_argument("--pages", type=int, default=2, help="Number of pages")
    parser.add_argument("--all", action="store_true", help="Fetch MAX pages (Very Slow)")
    
    args = parser.parse_args()
    try:
        fetch_shows(pages=args.pages, fetch_all=args.all)
        print("TV Ingestion Complete.")
    except KeyboardInterrupt:
        print("\nStopped.")