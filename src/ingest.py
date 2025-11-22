import os
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
            exists = session.query(Movie).filter_by(tmdb_id=item['id']).first()
            if not exists:
                movie = Movie(
                    title=item['title'],
                    tmdb_id=item['id'],
                    overview=item['overview'],
                    release_date=item.get('release_date'),
                    genres=item.get('genre_ids'),  # Storing generic IDs for now
                    poster_path=item['poster_path'],
                    popularity_score=item['popularity'],
                    is_downloaded=False 
                )
                session.add(movie)
        
        session.commit()
        print(f"Page {page} processed.")

def fetch_shows(pages=2):
    print(f"📺 Starting TV Show Ingestion ({pages} pages)...")
    for page in range(1, pages + 1):
        url = f"{BASE_URL}/tv/popular?api_key={API_KEY}&language=en-US&page={page}"
        response = requests.get(url).json()
        
        for item in response.get('results', []):
            exists = session.query(TVShow).filter_by(tmdb_id=item['id']).first()
            if not exists:
                show = TVShow(
                    title=item['name'],
                    tmdb_id=item['id'],
                    overview=item['overview'],
                    poster_path=item['poster_path'],
                    popularity_score=item['popularity']
                )
                session.add(show)
                session.commit() # Commit show first to get ID
                
                # Optional: Fetch Seasons (Keep lightweight for now)
                # We can add deep season fetching later if needed
    
    print("TV Shows processed.")

if __name__ == "__main__":
    print("Connecting to AI321 Database...")
    try:
        fetch_movies()
        fetch_shows()
        print("\n INGESTION COMPLETE. Your database is now populated.")
    except Exception as e:
        print(f"ERROR: {e}")
        print("Tip: Check if your VPN is blocking the API or if the Key is correct.")