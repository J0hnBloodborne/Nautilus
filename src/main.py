from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from src.database import get_db
import src.models as models
from pydantic import BaseModel
from typing import List, Optional
import os
import time
import requests
from dotenv import load_dotenv
load_dotenv()
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

app = FastAPI(title="Nautilus | MLOps Media Engine")

# 1. Mount the Static Frontend files (CSS, JS)
app.mount("/static", StaticFiles(directory="src/static"), name="static")

# 2. Serve the UI at the Root URL
@app.get("/")
async def read_index():
    # This makes http://localhost:8000 open your HTML file
    return FileResponse('src/static/index.html')

# --- API ENDPOINTS ---

@app.get("/movies")
def get_movies(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return db.query(models.Movie).offset(skip).limit(limit).all()

@app.get("/movies/{movie_id}")
def get_movie(movie_id: int, db: Session = Depends(get_db)):
    movie = db.query(models.Movie).filter(models.Movie.id == movie_id).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie

@app.get("/shows")
def get_shows(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    return db.query(models.TVShow).offset(skip).limit(limit).all()

class EpisodeSchema(BaseModel):
    id: int
    episode_number: Optional[int]
    title: Optional[str]
    overview: Optional[str]
    stream_url: Optional[str]

    class Config:
        orm_mode = True

class SeasonSchema(BaseModel):
    id: int
    season_number: Optional[int]
    name: Optional[str]
    episodes: List[EpisodeSchema] = []

    class Config:
        orm_mode = True

class ShowSeasonsResponse(BaseModel):
    show_id: int
    title: str
    seasons: List[SeasonSchema]

@app.get("/shows/{show_id}/seasons", response_model=ShowSeasonsResponse)
def get_seasons(show_id: int, db: Session = Depends(get_db)):
    """Return all seasons for a TV show including nested episodes.
    If not present in DB, fetch from TMDB, insert, then return.
    404 if the show does not exist.
    """
    show = db.query(models.TVShow).filter(models.TVShow.id == show_id).first()
    if not show:
        raise HTTPException(status_code=404, detail="Show not found")

    # If no seasons, fetch from TMDB and insert
    if not show.seasons or len(show.seasons) == 0:
        # Fetch from TMDB
        if not TMDB_API_KEY:
            raise HTTPException(status_code=500, detail="TMDB_API_KEY not configured")
        BASE_URL = "https://api.themoviedb.org/3"
        def tmdb_get(path):
            url = f"{BASE_URL}{path}?api_key={TMDB_API_KEY}&language=en-US"
            r = requests.get(url)
            r.raise_for_status()
            return r.json()
        show_data = tmdb_get(f"/tv/{show.tmdb_id}")
        for season_meta in show_data.get("seasons", []):
            snum = season_meta.get("season_number")
            if snum is None or snum == 0:
                continue
            time.sleep(0.3)
            season_detail = tmdb_get(f"/tv/{show.tmdb_id}/season/{snum}")
            season = models.Season(
                show_id=show.id,
                season_number=snum,
                name=season_meta.get("name") or f"Season {snum}",
                air_date=season_meta.get("air_date"),
            )
            db.add(season)
            db.flush()
            for ep in season_detail.get("episodes", []):
                episode = models.Episode(
                    season_id=season.id,
                    episode_number=ep.get("episode_number"),
                    title=ep.get("name"),
                    overview=ep.get("overview"),
                    runtime_minutes=ep.get("runtime"),
                    air_date=ep.get("air_date"),
                    still_path=ep.get("still_path"),
                )
                db.add(episode)
            db.commit()
        # Refresh show object
        db.refresh(show)

    return ShowSeasonsResponse(
        show_id=show.id,
        title=show.title,
        seasons=[
            SeasonSchema(
                id=season.id,
                season_number=season.season_number,
                name=season.name,
                episodes=[
                    EpisodeSchema(
                        id=ep.id,
                        episode_number=ep.episode_number,
                        title=ep.title,
                        overview=ep.overview,
                        stream_url=ep.stream_url,
                    )
                    for ep in season.episodes
                ],
            )
            for season in show.seasons
        ],
    )

# --------------------------------------
# Admin Seeding Utilities (TV Shows)
# --------------------------------------
class TVSeedRequest(BaseModel):
    ids: List[int]
    overwrite: bool = False  # If True, purges existing show/seasons for those IDs

class SeedResult(BaseModel):
    inserted: int
    skipped: int
    details: List[str]

def tmdb_get(path: str):
    if not TMDB_API_KEY:
        raise HTTPException(status_code=500, detail="TMDB_API_KEY not configured")
    url = f"https://api.themoviedb.org/3{path}"
    r = requests.get(url, params={"api_key": TMDB_API_KEY})
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"TMDB API error {r.status_code}: {r.text[:120]}")
    return r.json()

def seed_single_show(db: Session, tv_id: int, overwrite: bool, sleep_s: float = 0.3):
    details = []
    show_data = tmdb_get(f"/tv/{tv_id}")
    existing = db.query(models.TVShow).filter(models.TVShow.tmdb_id == show_data["id"]).first()
    if existing and overwrite:
        # Delete cascade
        db.delete(existing)
        db.flush()
        details.append(f"Purged existing show {existing.title}")
    elif existing and not overwrite:
        details.append(f"Skipped existing show {existing.title}")
        return False, details

    show = models.TVShow(
        title=show_data.get("name"),
        tmdb_id=show_data.get("id"),
        overview=show_data.get("overview"),
        genres=[g.get("name") for g in show_data.get("genres", [])],
        poster_path=show_data.get("poster_path"),
        popularity_score=show_data.get("popularity"),
    )
    db.add(show)
    db.flush()
    details.append(f"Inserted show {show.title}")

    for season_meta in show_data.get("seasons", []):
        snum = season_meta.get("season_number")
        # Skip specials (season 0) optionally
        if snum is None or snum == 0:
            continue
        time.sleep(sleep_s)
        season_detail = tmdb_get(f"/tv/{tv_id}/season/{snum}")
        season = models.Season(
            show_id=show.id,
            season_number=snum,
            name=season_meta.get("name") or f"Season {snum}",
            air_date=season_meta.get("air_date"),
        )
        db.add(season)
        db.flush()
        ep_count = 0
        for ep in season_detail.get("episodes", []):
            episode = models.Episode(
                season_id=season.id,
                episode_number=ep.get("episode_number"),
                title=ep.get("name"),
                overview=ep.get("overview"),
                runtime_minutes=ep.get("runtime"),
                air_date=ep.get("air_date"),
                still_path=ep.get("still_path"),
            )
            db.add(episode)
            ep_count += 1
        details.append(f"  Season {snum}: {ep_count} episodes")
    return True, details

@app.post("/admin/seed/tv", response_model=SeedResult)
def seed_tv(request: TVSeedRequest, db: Session = Depends(get_db)):
    inserted = 0
    skipped = 0
    all_details: List[str] = []
    for tv_id in request.ids:
        try:
            created, details = seed_single_show(db, tv_id, request.overwrite)
            if created:
                inserted += 1
            else:
                skipped += 1
            all_details.extend(details)
        except HTTPException as e:
            all_details.append(f"Error {tv_id}: {e.detail}")
        except Exception as e:
            all_details.append(f"Unhandled {tv_id}: {str(e)[:120]}")
    db.commit()
    return SeedResult(inserted=inserted, skipped=skipped, details=all_details)

@app.post("/admin/seed/tv/popular", response_model=SeedResult)
def seed_popular(count: int = 5, page: int = 1, overwrite: bool = False, db: Session = Depends(get_db)):
    data = tmdb_get(f"/tv/popular?page={page}")
    ids = [r["id"] for r in data.get("results", [])][:count]
    req = TVSeedRequest(ids=ids, overwrite=overwrite)
    return seed_tv(req, db)

@app.post("/admin/seed/tv/bulk", response_model=SeedResult)
def seed_tv_bulk(category: str = "popular", start_page: int = 1, max_pages: int = 5, overwrite: bool = False, sleep_s: float = 0.3, commit_interval: int = 5, db: Session = Depends(get_db)):
    """Bulk paginate through TMDB categories and seed many shows.

    category: popular | top_rated | on_the_air | airing_today
    Pages iterate from start_page to start_page+max_pages-1.
    """
    categories = {
        "popular": "/tv/popular",
        "top_rated": "/tv/top_rated",
        "on_the_air": "/tv/on_the_air",
        "airing_today": "/tv/airing_today",
    }
    if category not in categories:
        raise HTTPException(status_code=400, detail=f"Invalid category '{category}'")
    path = categories[category]
    inserted = 0
    skipped = 0
    details: List[str] = []
    page_end = start_page + max_pages - 1
    for page in range(start_page, page_end + 1):
        try:
            data = tmdb_get(f"{path}", params={"page": page})
        except HTTPException as e:
            details.append(f"Page {page} error: {e.detail}")
            continue
        results = data.get("results", [])
        if not results:
            details.append(f"Page {page} empty; stopping")
            break
        for r in results:
            tv_id = r.get("id")
            if not tv_id:
                continue
            created, show_details = seed_single_show(db, tv_id, overwrite)
            details.extend(show_details)
            if created:
                inserted += 1
            else:
                skipped += 1
            if inserted % commit_interval == 0:
                db.commit()
                details.append(f"-- interim commit after {inserted} inserted --")
            time.sleep(sleep_s)
    db.commit()
    details.append("Bulk seed complete")
    return SeedResult(inserted=inserted, skipped=skipped, details=details)

@app.post("/admin/reset")
def admin_reset(db: Session = Depends(get_db)):
    """Dangerous: Drops and recreates all tables."""
    engine = db.get_bind()
    models.Base.metadata.drop_all(engine)
    models.Base.metadata.create_all(engine)
    return {"status": "reset-complete"}