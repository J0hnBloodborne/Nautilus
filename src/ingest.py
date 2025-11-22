import os
import time
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from models import Base, Movie, TVShow, Season, Episode

load_dotenv()
API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

BASE_URL = "https://api.themoviedb.org/3"

def fetch_movies(pages=5):
    print(f"Starting Movie Ingestion ({pages} pages)...")
    for page in range(1, pages + 1):
        url = f"{BASE_URL}/movie/popular?api_key={API_KEY}&language=en-US&page={page}"
        response = requests.get(url).json()
        for item in response.get('results', []):
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
        print(f"Movie Page {page} processed.")
        time.sleep(0.2)

def fetch_shows_and_episodes(pages=2):
    print(f"Starting TV Show & Episode Ingestion ({pages} pages)...")
    for page in range(1, pages + 1):
        url = f"{BASE_URL}/tv/popular?api_key={API_KEY}&language=en-US&page={page}"
        data = requests.get(url).json()
        
        for item in data.get('results', []):
            # 1. Create Show
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
                session.commit() # Commit to generate ID
                
                # 2. Fetch Seasons for this Show
                print(f"      Processing Show: {show.title}...")
                _fetch_seasons(show)
                
        time.sleep(0.2)

def _fetch_seasons(show):
    # Get show details to find season numbers
    url = f"{BASE_URL}/tv/{show.tmdb_id}?api_key={API_KEY}&language=en-US"
    details = requests.get(url).json()
    
    for s_data in details.get('seasons', []):
        season_num = s_data['season_number']
        if season_num == 0: continue # Skip "Specials" for now

        season = Season(
            show_id=show.id,
            season_number=season_num,
            name=s_data['name']
        )
        session.add(season)
        session.commit()

        # 3. Fetch Episodes for this Season
        _fetch_episodes(show.tmdb_id, season)

def _fetch_episodes(tmdb_show_id, season):
    url = f"{BASE_URL}/tv/{tmdb_show_id}/season/{season.season_number}?api_key={API_KEY}&language=en-US"
    ep_data = requests.get(url).json()
    
    for ep in ep_data.get('episodes', []):
        episode = Episode(
            season_id=season.id,
            episode_number=ep['episode_number'],
            title=ep['name'],
            overview=ep['overview'],
            is_downloaded=False
        )
        session.add(episode)
    session.commit()
    print(f"         > S{season.season_number} fetched ({len(ep_data.get('episodes', []))} eps)")

if __name__ == "__main__":
    try:
        fetch_movies()
        fetch_shows_and_episodes()
        print("INGESTION COMPLETE.")
    except Exception as e:
        print(f"ERROR: {e}")