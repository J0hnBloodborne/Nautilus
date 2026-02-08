from src.core.database import SessionLocal
from src.core.models import Movie, TVShow

def main():
    db = SessionLocal()
    try:
        movie_count = db.query(Movie).count()
        tvshow_count = db.query(TVShow).count()
        print(f"Movies: {movie_count}")
        print(f"TV Shows: {tvshow_count}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
