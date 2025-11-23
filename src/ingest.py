import os
import time
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from models import Movie, TVShow

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

def fetch_shows(pages=2):
    print(f"Starting TV Show Ingestion ({pages} pages)...")
    for page in range(1, pages + 1):
        url = f"{BASE_URL}/tv/popular?api_key={API_KEY}&language=en-US&page={page}"
        data = requests.get(url).json()
        for item in data.get('results', []):
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
        print(f"Show Page {page} processed.")
        time.sleep(0.2)

if __name__ == "__main__":
    try:
        fetch_movies()
        fetch_shows()
        print("INGESTION COMPLETE.")
    except Exception as e:
        print(f"ERROR: {e}")