import os
import time
import requests
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from models import TVShow, Season, Episode

load_dotenv()
API_KEY = os.getenv("TMDB_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

BASE_URL = "https://api.themoviedb.org/3"
SLEEP_S = 0.3

def tmdb_get(path):
    url = f"{BASE_URL}{path}?api_key={API_KEY}&language=en-US"
    r = requests.get(url)
    r.raise_for_status()
    return r.json()

def seed_seasons_episodes_for_show(show_id):
    show = session.query(TVShow).filter_by(id=show_id).first()
    if not show:
        print(f"Show with id {show_id} not found.")
        return
    print(f"Fetching seasons/episodes for: {show.title} (TMDB ID: {show.tmdb_id})")
    show_data = tmdb_get(f"/tv/{show.tmdb_id}")
    for season_meta in show_data.get("seasons", []):
        snum = season_meta.get("season_number")
        if snum is None or snum == 0:
            continue
        time.sleep(SLEEP_S)
        season_detail = tmdb_get(f"/tv/{show.tmdb_id}/season/{snum}")
        season = Season(
            show_id=show.id,
            season_number=snum,
            name=season_meta.get("name") or f"Season {snum}",
            air_date=season_meta.get("air_date"),
        )
        session.add(season)
        session.flush()
        ep_count = 0
        for ep in season_detail.get("episodes", []):
            episode = Episode(
                season_id=season.id,
                episode_number=ep.get("episode_number"),
                title=ep.get("name"),
                overview=ep.get("overview"),
                runtime_minutes=ep.get("runtime"),
                air_date=ep.get("air_date"),
                still_path=ep.get("still_path"),
            )
            session.add(episode)
            ep_count += 1
        print(f"  Season {snum}: {ep_count} episodes")
    session.commit()
    print("Done.")

if __name__ == "__main__":
    # Example usage: seed all shows
    shows = session.query(TVShow).all()
    for show in shows:
        seed_seasons_episodes_for_show(show.id)
    session.close()
