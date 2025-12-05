import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import os
import sys

# Add root to path
sys.path.append(os.getcwd())
from src.core.models import Movie

load_dotenv()
API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

def repair():
    print("Starting Genre Repair...")
    
    # Find movies with no genres
    movies = session.query(Movie).filter(Movie.genres is None).all()
    print(f"   Found {len(movies)} movies with missing genres.")
    
    if len(movies) == 0:
        print("   Nothing to fix!")
        return

    count = 0
    for movie in movies:
        try:
            url = f"https://api.themoviedb.org/3/movie/{movie.tmdb_id}?api_key={API_KEY}"
            data = requests.get(url, timeout=5).json()
            
            if 'genres' in data:
                # TMDB details endpoint returns [{'id': 28, 'name': 'Action'}...]
                # We just want the IDs: [28, 12]
                genre_ids = [g['id'] for g in data['genres']]
                movie.genres = genre_ids # SQLAlchemy handles JSON conversion
                session.add(movie)
                count += 1
                
            if count % 50 == 0:
                session.commit()
                print(f"   Fixed {count} movies...")
                
        except Exception as e:
            print(f"   Failed on {movie.title}: {e}")
            
    session.commit()
    print("Repair Complete.")

if __name__ == "__main__":
    repair()