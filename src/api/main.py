from fastapi import FastAPI, Depends, Request, UploadFile, File, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.sql import func
from src.core.database import get_db
from src.core import models
from src.services.scrapers.universal import UniversalScraper
import httpx
import os
import requests
import shutil
import numpy as np
import glob
import ctypes
import sys
from datetime import datetime
from datetime import timedelta
import threading
import json
from pathlib import Path
from dotenv import load_dotenv
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from typing import List
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"


TMDB_GENRE_MAP = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Sci-Fi", 10770: "TV Movie",
    53: "Thriller", 10752: "War", 37: "Western"
}

load_dotenv()
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

app = FastAPI(title="Nautilus | Deep Dive")

# MOUNT STATIC ASSETS
app.mount("/static", StaticFiles(directory="src/frontend/static"), name="static")
# MOUNT GENERATED GRAPHS (Crucial for Admin Dashboard)
# Mount reports to match the HTML path
app.mount("/reports/figures", StaticFiles(directory="reports/figures"), name="reports_figures")

@app.get("/")
async def read_index():
    return FileResponse('src/frontend/static/index.html')

@app.get("/admin")
async def read_admin():
    return FileResponse('src/frontend/static/admin.html')

# --- 1. ML INFERENCE & STATS ---

@app.get("/admin/stats")
def get_admin_stats(db: Session = Depends(get_db)):
    """
    Returns system vitals and ML metrics history.
    """
    user_count = db.query(models.User).count()
    movie_count = db.query(models.Movie).count()
    show_count = db.query(models.TVShow).count()
    
    # Fetch all models to plot performance history
    models_list = db.query(models.MLModel).order_by(models.MLModel.created_at.desc()).all()

    # Leaderboard: top movies by popularity_score (top 5)
    top_movies = db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).limit(5).all()
    leaderboard = [{"title": m.title, "tmdb_id": m.tmdb_id, "popularity": m.popularity_score} for m in top_movies]

    # New Releases (by release_date descending) - movies
    try:
        new_releases_movies = db.query(models.Movie).order_by(models.Movie.release_date.desc()).limit(5).all()
        new_releases_movies = [{"title": m.title, "tmdb_id": m.tmdb_id, "release_date": m.release_date} for m in new_releases_movies]
    except Exception:
        new_releases_movies = []

    # Top Rated Movies (by average rating if available, otherwise fallback to popularity)
    try:
        avg_ratings = db.query(
            models.Movie.id,
            models.Movie.title,
            models.Movie.tmdb_id,
            func.avg(models.Interaction.rating_value).label('avg_rating')
        ).join(models.Interaction, models.Interaction.movie_id == models.Movie.id).group_by(models.Movie.id).order_by(func.avg(models.Interaction.rating_value).desc()).limit(5).all()

        if avg_ratings:
            top_rated_movies = [{"title": row.title, "tmdb_id": row.tmdb_id, "avg_rating": float(row.avg_rating)} for row in avg_ratings]
        else:
            # Fallback to popularity
            top_pop = db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).limit(5).all()
            top_rated_movies = [{"title": m.title, "tmdb_id": m.tmdb_id, "popularity": m.popularity_score} for m in top_pop]
    except Exception:
        top_rated_movies = []

    # Repeat for TV Shows
    try:
        # TVShow doesn't have a release_date field in the model; use popularity as a proxy for recent/interesting
        new_releases_shows = db.query(models.TVShow).order_by(models.TVShow.popularity_score.desc()).limit(5).all()
        new_releases_shows = [{"title": s.title, "tmdb_id": s.tmdb_id, "popularity": s.popularity_score} for s in new_releases_shows]
    except Exception:
        new_releases_shows = []

    try:
        avg_ratings_shows = db.query(
            models.TVShow.id,
            models.TVShow.title,
            models.TVShow.tmdb_id,
            func.avg(models.Interaction.rating_value).label('avg_rating')
        ).join(models.Interaction, models.Interaction.tv_show_id == models.TVShow.id).group_by(models.TVShow.id).order_by(func.avg(models.Interaction.rating_value).desc()).limit(5).all()

        if avg_ratings_shows:
            top_rated_shows = [{"title": row.title, "tmdb_id": row.tmdb_id, "avg_rating": float(row.avg_rating)} for row in avg_ratings_shows]
        else:
            top_pop_shows = db.query(models.TVShow).order_by(models.TVShow.popularity_score.desc()).limit(5).all()
            top_rated_shows = [{"title": s.title, "tmdb_id": s.tmdb_id, "popularity": s.popularity_score} for s in top_pop_shows]
    except Exception:
        top_rated_shows = []

    return {
        "users": user_count,
        "movies": movie_count,
        "shows": show_count,
        "models": models_list,
        "leaderboard": leaderboard,
        "new_releases_movies": new_releases_movies,
        "top_rated_movies": top_rated_movies,
        "new_releases_shows": new_releases_shows,
        "top_rated_shows": top_rated_shows
    }

# --- Periodic ingestion helper (simple file-backed last-fetch marker)
LAST_FETCH_PATH = Path("reports") / "last_fetch.json"

def _read_last_fetch():
    try:
        if LAST_FETCH_PATH.exists():
            data = json.loads(LAST_FETCH_PATH.read_text())
            return data
    except Exception as e:
        print(f"read_last_fetch error: {e}")
    return {}

def _write_last_fetch(dct: dict):
    try:
        LAST_FETCH_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_FETCH_PATH.write_text(json.dumps(dct))
    except Exception as e:
        print(f"write_last_fetch error: {e}")

def should_refetch(kind: str):
    data = _read_last_fetch()
    key = f"last_fetch_{kind}"
    if key not in data:
        return True
    try:
        last = datetime.fromisoformat(data[key])
        return (datetime.utcnow() - last) >= timedelta(days=2)
    except Exception:
        return True

def mark_fetched(kind: str):
    data = _read_last_fetch()
    data[f"last_fetch_{kind}"] = datetime.utcnow().isoformat()
    _write_last_fetch(data)

def run_fetch(kind: str = 'movies', pages: int = 2):
    try:
        print(f"Starting fetch job for: {kind}")
        if kind in ('movies', 'all'):
            from src.services.ingestion.ingest_movies import fetch_movies
            fetch_movies(pages=pages)
            mark_fetched('movies')
        if kind in ('shows', 'all'):
            from src.services.ingestion.ingest_shows import fetch_shows
            fetch_shows(pages=pages)
            mark_fetched('shows')
        print(f"Fetch job for {kind} completed.")
    except Exception as e:
        print(f"run_fetch error ({kind}): {e}")

def background_periodic_worker(interval_hours: int = 24):
    try:
        while True:
            try:
                # Movies
                if should_refetch('movies'):
                    print("Periodic worker: movies need refresh")
                    run_fetch('movies', pages=2)
                else:
                    print("Periodic worker: movies up-to-date")

                # Shows
                if should_refetch('shows'):
                    print("Periodic worker: shows need refresh")
                    run_fetch('shows', pages=2)
                else:
                    print("Periodic worker: shows up-to-date")
            except Exception as inner:
                print(f"background_periodic_worker inner error: {inner}")

            import time as _time
            _time.sleep(interval_hours * 3600)
    except Exception as e:
        print(f"background_periodic_worker error: {e}")


@app.on_event("startup")
def startup_periodic_fetch():
    # Start a daemon thread that periodically checks and fetches
    try:
        t = threading.Thread(target=background_periodic_worker, kwargs={'interval_hours': 24}, daemon=True)
        t.start()
    except Exception as e:
        print(f"startup_periodic_fetch error: {e}")


@app.post("/admin/refresh_movies")
def refresh_movies(request: Request, background_tasks: BackgroundTasks, kind: str = 'movies', pages: int = 2):
    """Manual trigger to refresh movies/shows ingestion. Protected by ADMIN_TRIGGER_TOKEN if set."""
    # If ADMIN_TRIGGER_TOKEN is configured, require it in X-ADMIN-TOKEN header
    token = os.getenv('ADMIN_TRIGGER_TOKEN')
    if token:
        header = request.headers.get('X-ADMIN-TOKEN')
        if not header or header != token:
            return {"ok": False, "reason": "forbidden"}

    if not TMDB_API_KEY:
        return {"ok": False, "reason": "No TMDB API key configured"}

    if kind not in ('movies', 'shows', 'all'):
        return {"ok": False, "reason": "invalid kind"}

    background_tasks.add_task(run_fetch, kind, pages)
    return {"ok": True, "scheduled": True, "kind": kind}

def get_media_item(db, tmdb_id):
    # Helper to find item in either table
    movie = db.query(models.Movie).filter(models.Movie.tmdb_id == tmdb_id).first()
    if movie: 
        return movie, 'movie'
    
    show = db.query(models.TVShow).filter(models.TVShow.tmdb_id == tmdb_id).first()
    if show: 
        return show, 'tv'
    
    return None, None

@app.get("/movie/{tmdb_id}/prediction")
def get_revenue_prediction(tmdb_id: int, db: Session = Depends(get_db)):
    # ML model removed in favor of lightweight deployment
    return {"label": "N/A", "value": "N/A"}

@app.get("/predict/genre/{tmdb_id}")
def get_genre_prediction(tmdb_id: int, db: Session = Depends(get_db)):
    """Predict genres from plot (Replaced with DB lookup)."""
    item, type_ = get_media_item(db, tmdb_id)

    if not item or not item.genres:
        return {"genres": [], "primary": None}

    # Format DB genres to match expected API output
    # DB genres is likely a list of dicts or strings. Assuming list of dicts from TMDB ingestion: {'id': 12, 'name': 'Adventure'}
    genres = []
    if isinstance(item.genres, list):
         for g in item.genres:
             if isinstance(g, dict) and 'id' in g and 'name' in g:
                 genres.append({"id": g['id'], "name": g['name'], "score": 1.0})
             elif isinstance(g, str):
                 # Try to map name back to ID if possible or generate fake ID
                 genres.append({"id": 0, "name": g, "score": 1.0})

    primary = genres[0] if genres else None
    return {"genres": genres, "primary": primary}
    
@app.get("/related/{tmdb_id}")
def get_related_movies(tmdb_id: int, db: Session = Depends(get_db)):
    """Association- and genre-based related items."""
    # Simplified legacy fallback: Just find movies with similar genres if possible, or return popular
    # For now, simply returning popular movies as widely applicable recommendations
    popular = db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).limit(10).all()
    return popular

    movie = db.query(models.Movie).filter(models.Movie.tmdb_id == tmdb_id).first()
    show = db.query(models.TVShow).filter(models.TVShow.tmdb_id == tmdb_id).first()

    # 1) If this is a TV show, only suggest TV shows
    if show and not movie:
        base_shows = db.query(models.TVShow).filter(models.TVShow.id != show.id)
        related_shows = (
            base_shows
            .filter(models.TVShow.popularity_score.isnot(None))
            .order_by(models.TVShow.popularity_score.desc())
            .limit(5)
            .all()
        )
        # Attach media_type tag for frontend
        return [dict(jsonable_encoder(s), media_type="tv") for s in related_shows]

    related_items: list = []

    # 2) Movie path: try association-based related movies first
    if movie and rules is not None and tmdb_id in rules:
        related_tmdb_ids = rules.get(tmdb_id, [])
        if related_tmdb_ids:
            q = db.query(models.Movie).filter(models.Movie.tmdb_id.in_(related_tmdb_ids))
            q = q.filter(models.Movie.id != movie.id)
            related_items = q.order_by(models.Movie.popularity_score.desc()).limit(5).all()

    # 3) Genre-based fallback when association rules are missing/empty
    if movie and not related_items:
        # Movie.genres is stored as JSON; expect a list of TMDB genre IDs
        source_genres = movie.genres or []
        if isinstance(source_genres, dict):
            source_genres = list(source_genres.keys())

        candidates_q = (
            db.query(models.Movie)
            .filter(models.Movie.id != movie.id)
            .filter(models.Movie.genres.isnot(None))
            .filter(models.Movie.popularity_score.isnot(None))
        )
        candidates = candidates_q.limit(200).all()

        if source_genres:
            source_set = set(source_genres)
            filtered = []
            for cand in candidates:
                g = cand.genres or []
                if isinstance(g, dict):
                    g = list(g.keys())
                if source_set.intersection(set(g)):
                    filtered.append(cand)
        else:
            filtered = candidates

        # Shuffle for diversity and pick up to 5
        import random
        random.shuffle(filtered)
        related_items = filtered[:5]

    # 4) Final fallback: popular movies if still empty
    if movie and not related_items:
        related_items = (
            db.query(models.Movie)
            .filter(models.Movie.id != movie.id)
            .filter(models.Movie.popularity_score.isnot(None))
            .order_by(models.Movie.popularity_score.desc())
            .limit(5)
            .all()
        )

    # Attach media_type tag so frontend can tell these are movies
    return [dict(jsonable_encoder(m), media_type="movie") for m in related_items]

# --- 2. CORE FEATURES ---

@app.get("/search")
def search_content(query: str, db: Session = Depends(get_db)):
    local_movies = db.query(models.Movie).filter(models.Movie.title.ilike(f"%{query}%")).limit(5).all()
    local_shows = db.query(models.TVShow).filter(models.TVShow.title.ilike(f"%{query}%")).limit(5).all()
    
    if len(local_movies) + len(local_shows) > 0:
        results = []
        for m in local_movies:
            payload = jsonable_encoder(m)
            payload["media_type"] = "movie"
            results.append(payload)
        for s in local_shows:
            payload = jsonable_encoder(s)
            payload["media_type"] = "tv"
            results.append(payload)
        return results
    
    if not TMDB_API_KEY: 
        return []
    
    url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={query}&include_adult=false"
    data = requests.get(url).json()
    
    results = []
    for item in data.get('results', []):
        if item['media_type'] == 'movie':
            if not db.query(models.Movie).filter_by(tmdb_id=item['id']).first():
                movie = models.Movie(
                    title=item.get('title'), tmdb_id=item.get('id'), overview=item.get('overview'),
                    poster_path=item.get('poster_path'), popularity_score=item.get('popularity'),
                    release_date=item.get('release_date')
                )
                db.add(movie)
                results.append(jsonable_encoder(movie) | {"media_type": "movie"})
        elif item['media_type'] == 'tv':
            if not db.query(models.TVShow).filter_by(tmdb_id=item['id']).first():
                show = models.TVShow(
                    title=item.get('name'), tmdb_id=item.get('id'), overview=item.get('overview'),
                    poster_path=item.get('poster_path'), popularity_score=item.get('popularity')
                )
                db.add(show)
                results.append(jsonable_encoder(show) | {"media_type": "tv"})
    try:
        db.commit()
    except Exception: 
        db.rollback()
    return results

@app.get("/play/{media_type}/{tmdb_id}")
async def play_content(media_type: str, tmdb_id: int, season: int = 1, episode: int = 1, provider: str = None):
    scraper = UniversalScraper()
    target_provider = None if provider == "auto" else provider
    result = await scraper.get_stream(tmdb_id, media_type, season, episode, target_provider)
    if not result:
        return {"url": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8", "type": "direct", "source": "Test Stream"}
    return result

@app.get("/proxy_stream")
async def proxy_stream(url: str, request: Request):
    client = httpx.AsyncClient()
    headers = { "User-Agent": "Mozilla/5.0" }
    req = client.build_request("GET", url, headers=headers)
    r = await client.send(req, stream=True)
    return StreamingResponse(
        r.aiter_bytes(), status_code=r.status_code, media_type=r.headers.get("content-type"), background=client.aclose
    )

@app.post("/users/avatar")
async def upload_avatar(file: UploadFile = File(...)):
    os.makedirs("src/static/avatars", exist_ok=True)
    file_location = f"src/static/avatars/{file.filename}"
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"info": f"Avatar updated: {file.filename}"}

@app.get("/movies")
def get_movies(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).offset(skip).limit(limit).all()


@app.get("/movies/new_releases")
def api_movies_new_releases(days: int = 60, limit: int = 50, db: Session = Depends(get_db)):
    """Return movies released within the last `days`. No hard cap on returned count except `limit`."""
    from datetime import datetime as _dt
    cutoff = (_dt.utcnow() - timedelta(days=days)).date()
    # Fetch recent movies by release_date descending (strings expected 'YYYY-MM-DD')
    candidates = db.query(models.Movie).filter(models.Movie.release_date.isnot(None)).order_by(models.Movie.release_date.desc()).limit(2000).all()
    out = []
    for m in candidates:
        try:
            rd = m.release_date
            if not rd:
                continue
            d = _dt.fromisoformat(rd).date()
            if d <= _dt.utcnow().date() and d >= cutoff:
                out.append(m)
        except Exception:
            continue
        if len(out) >= limit:
            break
    return out


@app.get("/movies/top_rated_alltime")
def api_movies_top_rated(limit: int = 50, min_votes: int = 5, db: Session = Depends(get_db)):
    """Return all-time top rated movies. Prefer DB Interaction averages; fallback to MovieLens raw ratings files if needed."""
    # 1) Try DB interactions
    q = db.query(
        models.Movie.id,
        models.Movie.title,
        models.Movie.tmdb_id,
        func.avg(models.Interaction.rating_value).label('avg_rating'),
        func.count(models.Interaction.id).label('vote_count')
    ).join(models.Interaction, models.Interaction.movie_id == models.Movie.id).group_by(models.Movie.id).having(func.count(models.Interaction.id) >= min_votes).order_by(func.avg(models.Interaction.rating_value).desc()).limit(limit).all()

    # If DB has a healthy number of rated movies, prefer that (site-specific ratings)
    MIN_ACCEPTABLE_DB_RESULTS = 10
    if q and len(q) >= MIN_ACCEPTABLE_DB_RESULTS:
        # Return Movie objects joined with stats
        out = []
        for row in q:
            m = db.query(models.Movie).filter(models.Movie.id == row.id).first()
            data = {
                'title': row.title,
                'tmdb_id': row.tmdb_id,
                'avg_rating': float(row.avg_rating),
                'vote_count': int(row.vote_count),
                'poster_path': m.poster_path if m else None,
                'release_date': m.release_date if m else None,
                'popularity_score': m.popularity_score if m else None,
                'overview': m.overview if m else None
            }
            out.append(data)
        return out

    # If DB ratings are sparse (few movies), fall back to MovieLens historical ratings
    # so we can surface all-time classics rather than site-specific popular items.

    # 1.5) Check for a precomputed MovieLens cache to avoid streaming large CSVs
    try:
        cache_path = Path('data/processed/top_rated_movies.json')
        if cache_path.exists():
            try:
                payload = json.loads(cache_path.read_text(encoding='utf-8'))
                items = payload.get('items', [])[:limit]
                cached_out = []
                for it in items:
                    tmdb = it.get('tmdb_id')
                    avg = it.get('avg_rating')
                    cnt = it.get('vote_count')
                    title = it.get('title')
                    m = None
                    if tmdb:
                        # tmdb ids in cache may be strings; try to coerce
                        try:
                            tid = int(tmdb)
                        except Exception:
                            tid = tmdb
                        m = db.query(models.Movie).filter(models.Movie.tmdb_id == tid).first()

                    rec = {
                        'title': title if title else (m.title if m else None),
                        'tmdb_id': int(tmdb) if tmdb is not None else None,
                        'avg_rating': float(avg) if avg is not None else None,
                        'vote_count': int(cnt) if cnt is not None else None,
                        'poster_path': m.poster_path if m else None,
                        'release_date': m.release_date if m else None,
                        'popularity_score': m.popularity_score if m else None,
                        'overview': m.overview if m else None
                    }
                    cached_out.append(rec)
                if cached_out:
                    return cached_out
            except Exception as e:
                print(f"cache read error: {e}")
    except Exception:
        pass

    # 2) Fallback to MovieLens ratings files (streaming CSV) if present
    import csv
    import glob
    links_paths = glob.glob('data/raw/**/links.csv', recursive=True)
    ratings_paths = glob.glob('data/raw/**/ratings.csv', recursive=True)
    if not links_paths or not ratings_paths:
        # No fallback available, use popularity as last resort
        movies = db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).limit(limit).all()
        return [{ 'title': m.title, 'tmdb_id': m.tmdb_id, 'popularity': m.popularity_score, 'movie': m } for m in movies]

    links_path = links_paths[0]
    ratings_path = ratings_paths[0]

    # Build mapping ml_movieId -> tmdbId
    ml_to_tmdb = {}
    try:
        with open(links_path, newline='', encoding='utf-8') as f:
            r = csv.DictReader(f)
            for row in r:
                try:
                    mlid = int(row.get('movieId') or row.get('movieId'))
                    tmdb = row.get('tmdbId') or row.get('tmdbId')
                    if mlid and tmdb:
                        ml_to_tmdb[mlid] = int(tmdb)
                except Exception:
                    continue
    except Exception as e:
        print(f"links file read error: {e}")

    # Aggregate ratings by ml movie id
    sums = {}
    counts = {}
    try:
        with open(ratings_path, newline='', encoding='utf-8') as f:
            r = csv.DictReader(f)
            for row in r:
                try:
                    mid = int(row.get('movieId'))
                    rating = float(row.get('rating'))
                except Exception:
                    continue
                counts[mid] = counts.get(mid, 0) + 1
                sums[mid] = sums.get(mid, 0.0) + rating
    except Exception as e:
        print(f"ratings file read error: {e}")

    # Compute averages and map to tmdb ids
    avg_list = []
    for mid, cnt in counts.items():
        if cnt < min_votes:
            continue
        tmdb = ml_to_tmdb.get(mid)
        if not tmdb:
            continue
        avg = sums[mid] / cnt
        avg_list.append((tmdb, avg, cnt))

    # Sort by avg desc
    avg_list.sort(key=lambda x: x[1], reverse=True)


    out = []
    for tmdb, avg, cnt in avg_list[:limit]:
        m = db.query(models.Movie).filter(models.Movie.tmdb_id == tmdb).first()
        if m:
            out.append({'title': m.title, 'tmdb_id': tmdb, 'avg_rating': float(avg), 'vote_count': int(cnt), 'poster_path': m.poster_path, 'release_date': m.release_date, 'popularity_score': m.popularity_score, 'overview': m.overview})

    if out:
        return out

    # Final fallback: popularity
    movies = db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).limit(limit).all()
    return [{ 'title': m.title, 'tmdb_id': m.tmdb_id, 'popularity': m.popularity_score, 'poster_path': m.poster_path, 'release_date': m.release_date, 'overview': m.overview } for m in movies]



@app.get("/shows")
def get_shows(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return db.query(models.TVShow).order_by(models.TVShow.popularity_score.desc()).offset(skip).limit(limit).all()

@app.get("/shows/{show_id}/seasons")
def get_seasons(show_id: int, db: Session = Depends(get_db)):
    """Return seasons with episodes.

    Accepts either internal DB show id or a TMDB id. If the show exists in the DB
    but seasons are not yet ingested, try to fetch them from TMDB and persist.
    If the show is not present in the DB, fetch seasons/episodes directly from
    TMDB and return them (no DB writes).
    """
    # Try DB lookup by internal id
    show = db.query(models.TVShow).options(
        joinedload(models.TVShow.seasons).joinedload(models.Season.episodes)
    ).filter(models.TVShow.id == show_id).first()

    # If not found, try TMDB id lookup
    if not show:
        try:
            show = db.query(models.TVShow).options(
                joinedload(models.TVShow.seasons).joinedload(models.Season.episodes)
            ).filter(models.TVShow.tmdb_id == int(show_id)).first()
        except Exception:
            show = None

    # If present in DB and has seasons, return them (sorted)
    if show and show.seasons:
        sorted_seasons = sorted(show.seasons, key=lambda s: s.season_number)
        for season in sorted_seasons:
            season.episodes.sort(key=lambda e: e.episode_number)
        return sorted_seasons

    # If present in DB but no seasons ingested, fetch from TMDB and persist
    if show and TMDB_API_KEY:
        try:
            url = f"{TMDB_BASE_URL}/tv/{show.tmdb_id}?api_key={TMDB_API_KEY}&language=en-US"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
            else:
                data = {}
        except Exception:
            data = {}

        for season_meta in data.get("seasons", []):
            s_num = season_meta.get('season_number')
            if s_num is None:
                continue
            season = models.Season(
                show_id=show.id,
                season_number=s_num,
                name=season_meta.get('name'),
                air_date=season_meta.get('air_date')
            )
            db.add(season)
            try:
                db.commit()
                db.refresh(season)
            except Exception:
                db.rollback()
                continue

            # Fetch episodes for this season
            try:
                s_url = f"{TMDB_BASE_URL}/tv/{show.tmdb_id}/season/{s_num}?api_key={TMDB_API_KEY}&language=en-US"
                s_resp = requests.get(s_url, timeout=5)
                if s_resp.status_code == 200:
                    s_data = s_resp.json()
                else:
                    s_data = {}
            except Exception:
                s_data = {}

            for ep in s_data.get('episodes', []):
                try:
                    episode = models.Episode(
                        season_id=season.id,
                        episode_number=ep.get('episode_number'),
                        title=ep.get('name'),
                        overview=ep.get('overview'),
                        air_date=ep.get('air_date'),
                        still_path=ep.get('still_path'),
                        runtime_minutes=ep.get('runtime')
                    )
                    db.add(episode)
                except Exception:
                    continue
            try:
                db.commit()
            except Exception:
                db.rollback()

        try:
            db.refresh(show)
        except Exception:
            pass

        if show.seasons:
            return sorted(show.seasons, key=lambda s: s.season_number)

    # If show not in DB, fetch directly from TMDB and return structured seasons (no DB writes)
    if TMDB_API_KEY:
        try:
            tmdb_url = f"{TMDB_BASE_URL}/tv/{show_id}?api_key={TMDB_API_KEY}&language=en-US"
            tmdb_resp = requests.get(tmdb_url, timeout=5)
            if tmdb_resp.status_code != 200:
                return []
            tmdb_data = tmdb_resp.json()
            seasons_out = []
            for season_meta in tmdb_data.get('seasons', []):
                s_num = season_meta.get('season_number')
                if s_num is None:
                    continue
                season_entry = {
                    'season_number': s_num,
                    'name': season_meta.get('name'),
                    'air_date': season_meta.get('air_date'),
                    'episodes': []
                }
                try:
                    s_url = f"{TMDB_BASE_URL}/tv/{show_id}/season/{s_num}?api_key={TMDB_API_KEY}&language=en-US"
                    s_resp = requests.get(s_url, timeout=5)
                    if s_resp.status_code == 200:
                        s_data = s_resp.json()
                    else:
                        s_data = {}
                except Exception:
                    s_data = {}

                for ep in s_data.get('episodes', []):
                    season_entry['episodes'].append({
                        'episode_number': ep.get('episode_number'),
                        'title': ep.get('name'),
                        'overview': ep.get('overview'),
                        'air_date': ep.get('air_date'),
                        'runtime_minutes': ep.get('runtime'),
                        'still_path': ep.get('still_path')
                    })

                seasons_out.append(season_entry)

            return seasons_out
        except Exception:
            return []

    # No DB record path fell through; return empty
    return []


@app.get("/shows/new_releases")
def api_shows_new_releases(days: int = 60, limit: int = 50, db: Session = Depends(get_db)):
    """Return shows with episodes aired within the last `days`."""
    from datetime import datetime as _dt
    try:
        cutoff = (_dt.utcnow() - timedelta(days=days)).date().isoformat()
        rows = db.query(models.Season.show_id).join(models.Episode, models.Episode.season_id == models.Season.id).filter(models.Episode.air_date >= cutoff).distinct().all()
        show_ids = [r[0] for r in rows]
        if not show_ids:
            return []
        shows = db.query(models.TVShow).filter(models.TVShow.id.in_(show_ids)).all()
        return shows[:limit]
    except Exception as e:
        print(f"api_shows_new_releases error: {e}")
        return []


@app.get("/shows/top_rated_alltime")
def api_shows_top_rated(limit: int = 50, min_votes: int = 5, db: Session = Depends(get_db)):
    """Top rated shows by user interactions (fallback to popularity)."""
    q = db.query(
        models.TVShow.id,
        models.TVShow.title,
        models.TVShow.tmdb_id,
        func.avg(models.Interaction.rating_value).label('avg_rating'),
        func.count(models.Interaction.id).label('vote_count')
    ).join(models.Interaction, models.Interaction.tv_show_id == models.TVShow.id).group_by(models.TVShow.id).having(func.count(models.Interaction.id) >= min_votes).order_by(func.avg(models.Interaction.rating_value).desc()).limit(limit).all()

    if q and len(q) > 0:
        out = []
        for row in q:
            s = db.query(models.TVShow).filter(models.TVShow.id == row.id).first()
        out.append({'title': row.title, 'tmdb_id': row.tmdb_id, 'avg_rating': float(row.avg_rating), 'vote_count': int(row.vote_count), 'poster_path': s.poster_path if s else None, 'popularity_score': s.popularity_score if s else None})
        return out

    # Fallback: popularity
    shows = db.query(models.TVShow).order_by(models.TVShow.popularity_score.desc()).limit(limit).all()
    return [{'title': s.title, 'tmdb_id': s.tmdb_id, 'popularity': s.popularity_score, 'poster_path': s.poster_path} for s in shows]

_NCF_MODEL = None
_NCF_ARTIFACTS = None


def load_recommender_ncf():
    """Lazy-load NCF recommender model and artifacts if available."""
    global _NCF_MODEL, _NCF_ARTIFACTS
    if _NCF_MODEL is not None and _NCF_ARTIFACTS is not None:
        return _NCF_MODEL, _NCF_ARTIFACTS

    model_path = "src/models/recommender_ncf.keras"
    artifacts_path = "src/models/recommender_ncf_artifacts.pkl"
    if not (os.path.exists(model_path) and os.path.exists(artifacts_path)):
        return None, None

    try:
        _NCF_MODEL = _keras.models.load_model(model_path)
        _NCF_ARTIFACTS = joblib.load(artifacts_path)
        print("NCF recommender loaded.")
    except Exception as e:
        print(f"Error loading NCF recommender: {e}")
        _NCF_MODEL, _NCF_ARTIFACTS = None, None
    return _NCF_MODEL, _NCF_ARTIFACTS


@app.get("/recommend/personal/{user_id}")
def get_personal_recs(user_id: int, db: Session = Depends(get_db)):
    """RecSys: NCF Inference with popularity fallback."""
    model, artifacts = load_recommender_ncf()
    if model is None or artifacts is None:
        return db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).limit(12).all()

    try:
        user_id_to_idx = artifacts.get("user_id_to_idx", {})
        movie_id_to_idx = artifacts.get("movie_id_to_idx", {})

        if not movie_id_to_idx:
            return db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).limit(12).all()

        # Resolve user index; default to first known user for now
        if user_id in user_id_to_idx:
            user_idx = user_id_to_idx[user_id]
        elif user_id_to_idx:
            user_idx = next(iter(user_id_to_idx.values()))
        else:
            return db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).limit(12).all()

        # Candidate movies: those we have embeddings for (cast to plain ints for psycopg2)
        candidate_ids = [int(mid) for mid in movie_id_to_idx.keys()]
        if not candidate_ids:
            return db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).limit(12).all()

        # Optionally restrict to a subset by popularity so NCF can deviate from pure top-popular
        movies_q = (
            db.query(models.Movie.id, models.Movie.popularity_score)
            .filter(models.Movie.id.in_(candidate_ids))
            .order_by(models.Movie.popularity_score.desc())
        )
        movies_rows = movies_q.limit(500).all()
        if not movies_rows:
            return db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).limit(12).all()

        movie_ids_ordered = [int(m.id) for m in movies_rows]
        movie_idxs = [movie_id_to_idx[mid] for mid in movie_ids_ordered if mid in movie_id_to_idx]
        if not movie_idxs:
            return db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).limit(12).all()

        import numpy as _np

        user_arr = _np.full(len(movie_idxs), user_idx, dtype=_np.int32)
        item_arr = _np.array(movie_idxs, dtype=_np.int32)

        scores = model.predict([user_arr, item_arr], verbose=0).reshape(-1)
        if scores.size == 0:
            return db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).limit(12).all()

        # Rank by score within this candidate band
        top_k = 12
        order = _np.argsort(-scores)[:top_k]
        top_movie_ids = [movie_ids_ordered[i] for i in order]

        # Fetch and preserve order
        movies = db.query(models.Movie).filter(models.Movie.id.in_(top_movie_ids)).all()
        by_id = {m.id: m for m in movies}
        ordered = [by_id[mid] for mid in top_movie_ids if mid in by_id]
        return ordered
    except Exception as e:
        print(f"NCF inference error: {e}")
        return db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).limit(12).all()

def load_clustering_artifacts():
    path_map = "src/models/clustering_artifacts.pkl"
    path_meta = "src/models/clustering_metadata.pkl"
    
    if os.path.exists(path_map) and os.path.exists(path_meta):
        try:
            return joblib.load(path_map), joblib.load(path_meta)
        except Exception as e:
            print(f"Error loading clustering artifacts: {e}")
    return None, None

@app.get("/collections/ai")
def get_ai_clusters(db: Session = Depends(get_db)):
    """AI genre collections for home rows.
    
    Uses K-Means clusters if available, otherwise falls back to popularity bands.
    """
    cluster_map, cluster_meta = load_clustering_artifacts()
    
    if cluster_map and cluster_meta:
        # Group movie IDs by cluster
        clusters = {}
        for mid, cluster in cluster_map.items():
            if cluster not in clusters:
                clusters[cluster] = []
            clusters[cluster].append(mid)
            
        # Pick two largest clusters
        sorted_clusters = sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)
        
        response = {}
        
        # Return top 2 clusters with dynamic names
        for i in range(min(2, len(sorted_clusters))):
            c_id = sorted_clusters[i][0]
            c_ids = sorted_clusters[i][1][:40] # Limit to 40 items
            
            meta = cluster_meta.get(c_id, {"name": f"AI Cluster {i+1}"})
            movies = db.query(models.Movie).filter(models.Movie.id.in_(c_ids)).all()
            
            response[f"cluster_{i+1}"] = {
                "name": f"AI Cluster: {meta['name']}",
                "items": movies
            }
            
        return response

    # Fallback: Old logic
    # Top band: more "mainstream" / blockbuster-like titles
    cluster_1 = (
        db.query(models.Movie)
        .filter(models.Movie.popularity_score.isnot(None))
        .order_by(models.Movie.popularity_score.desc())
        .limit(40)
        .all()
    )

    # Lower band: deeper cuts (less popular but still with overviews/posters)
    cluster_2 = (
        db.query(models.Movie)
        .filter(models.Movie.popularity_score.isnot(None))
        .order_by(models.Movie.popularity_score.asc())
        .limit(40)
        .all()
    )

    return {
        "cluster_1": {"name": "AI Cluster: High Voltage", "items": cluster_1},
        "cluster_2": {"name": "AI Cluster: Deep Cuts", "items": cluster_2}
    }

class RevenueInput(BaseModel):
    budget: float
    runtime: float
    release_month: int
    release_year: int | None = None
    genres: List[str] = []


_CPI_INDEX = {
    # Approximate CPI-U annual averages (used to compute multiplier). Add/adjust values as needed.
    2000: 172.2, 2001: 177.1, 2002: 179.9, 2003: 184.0, 2004: 188.9,
    2005: 195.3, 2006: 201.6, 2007: 207.3, 2008: 215.3, 2009: 214.5,
    2010: 218.1, 2011: 224.9, 2012: 229.6, 2013: 233.0, 2014: 236.7,
    2015: 237.0, 2016: 240.0, 2017: 245.1, 2018: 251.1, 2019: 255.7,
    2020: 258.8, 2021: 271.0, 2022: 292.7, 2023: 305.1, 2024: 313.0, 2025: 315.0
}


@app.post("/predict/revenue")
def predict_revenue_manual(input_data: RevenueInput, inflation_multiplier: float = 1.0, use_cpi: bool = False):
    """
    Predict revenue based on manual JSON input.
    """
    model_path = "src/models/revenue_regressor.pkl"
    if not os.path.exists(model_path): 
        return {"prediction": "N/A", "error": "Model not found"}
        
    try:
        # Feature Vector Construction
        # Model expects: ['budget', 'runtime', 'release_month'] + [Action, Adventure, ..., Sci-Fi]
        top_genres = ['Action', 'Adventure', 'Animation', 'Comedy', 'Crime', 'Drama', 'Family', 'Fantasy', 'Horror', 'Science Fiction']
        
        features = [input_data.budget, input_data.runtime, input_data.release_month]
        for g in top_genres:
            features.append(1 if g in input_data.genres else 0)
            
        vector = np.array([features], dtype=np.float32)
        
        model = joblib.load(model_path)
        prediction = model.predict(vector)[0]
        raw_value = float(prediction)
        # Optionally compute inflation multiplier using CPI index if requested
        final_multiplier = float(inflation_multiplier)
        try:
            if use_cpi and input_data.release_year:
                current_year = max(_CPI_INDEX.keys())
                cpi_current = _CPI_INDEX.get(current_year)
                cpi_release = _CPI_INDEX.get(int(input_data.release_year))
                if cpi_current and cpi_release:
                    final_multiplier = float(cpi_current) / float(cpi_release)
        except Exception:
            pass

        try:
            adjusted = float(raw_value) * final_multiplier
        except Exception:
            adjusted = raw_value

        return {"prediction": f"${adjusted:,.0f}", "raw_value": raw_value, "inflation_multiplier": final_multiplier}
            
    except Exception as e:
        print(f"Prediction Error: {e}")
        return {"prediction": "Error", "details": str(e)}

@app.get("/movies/random")
def get_random_movies(limit: int = 20, db: Session = Depends(get_db)):
    return db.query(models.Movie).order_by(func.random()).limit(limit).all()

@app.get("/movies/genre/{genre_id}")
def get_movies_by_genre(genre_id: int, limit: int = 20, db: Session = Depends(get_db)):
    # Fetch popular movies and filter by genre in Python
    # This avoids DB-specific JSON query syntax issues
    candidates = db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).limit(500).all()
    filtered = []
    for movie in candidates:
        if movie.genres and isinstance(movie.genres, list):
            if genre_id in movie.genres:
                filtered.append(movie)
        if len(filtered) >= limit:
            break
    return filtered

@app.get("/movies/desi")
def get_desi_movies(limit: int = 20):
    """Fetches popular Indian movies (Hindi, Tamil, Telugu, Malayalam) from TMDB."""
    if not TMDB_API_KEY:
        return []
        
    url = f"https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&with_original_language=hi|ta|te|ml&sort_by=popularity.desc&page=1"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            results = response.json().get('results', [])
            # Map TMDB result keys to our frontend expectations if needed
            # Frontend expects: id, title, poster_path, overview, etc.
            # TMDB returns 'id', 'title', 'poster_path', 'overview', 'genre_ids', 'vote_average'
            # This matches well enough.
            return results[:limit]
    except Exception as e:
        print(f"Error fetching Desi movies: {e}")
    return []

class InteractionInput(BaseModel):
    guest_id: str
    item_id: int
    media_type: str  # 'movie' or 'tv'
    action: str      # 'like', 'watch'


def fetch_movie_details(tmdb_id):
    url = f"{TMDB_BASE_URL}/movie/{tmdb_id}?api_key={TMDB_API_KEY}&language=en-US"
    response = requests.get(url, timeout=10)
    if response.status_code != 200:
        return None
    data = response.json()
    return {
        'id': None,  # Let SQLAlchemy autogenerate if needed
        'title': data.get('title'),
        'tmdb_id': data.get('id'),
        'overview': data.get('overview'),
        'release_date': data.get('release_date'),
        'genres': [g['name'] for g in data.get('genres', [])],
        'poster_path': data.get('poster_path'),
        'popularity_score': data.get('popularity'),
        'stream_url': None
    }

def fetch_tv_details(tmdb_id):
    url = f"{TMDB_BASE_URL}/tv/{tmdb_id}?api_key={TMDB_API_KEY}&language=en-US"
    response = requests.get(url, timeout=10)
    if response.status_code != 200:
        return None
    data = response.json()
    return {
        'id': None,
        'title': data.get('name'),
        'tmdb_id': data.get('id'),
        'overview': data.get('overview'),
        'genres': [g['name'] for g in data.get('genres', [])],
        'poster_path': data.get('poster_path'),
        'popularity_score': data.get('popularity')
    }


@app.get("/media/{tmdb_id}")
def get_media_details(tmdb_id: int, db: Session = Depends(get_db)):
    """Return lightweight media details (overview, poster, release/first_air_date).

    This is intended for non-blocking modal enrichment on the frontend. It will
    try the DB first and fall back to TMDB (movie then tv) when an API key is
    configured.
    """
    item, type_ = get_media_item(db, tmdb_id)
    if item:
        if type_ == 'movie':
            return {
                'tmdb_id': item.tmdb_id,
                'media_type': 'movie',
                'title': item.title,
                'overview': item.overview,
                'poster_path': item.poster_path,
                'release_date': item.release_date
            }
        else:
            # TV show
            return {
                'tmdb_id': item.tmdb_id,
                'media_type': 'tv',
                'title': item.title,
                'overview': item.overview,
                'poster_path': item.poster_path,
                'first_air_date': getattr(item, 'first_air_date', None)
            }

    # Not in DB: try TMDB (movie first, then tv)
    if not TMDB_API_KEY:
        return {}

    try:
        m_url = f"{TMDB_BASE_URL}/movie/{tmdb_id}?api_key={TMDB_API_KEY}&language=en-US"
        m_resp = requests.get(m_url, timeout=5)
        if m_resp.status_code == 200:
            md = m_resp.json()
            return {
                'tmdb_id': md.get('id'),
                'media_type': 'movie',
                'title': md.get('title'),
                'overview': md.get('overview'),
                'poster_path': md.get('poster_path'),
                'release_date': md.get('release_date')
            }
    except Exception:
        pass

    try:
        t_url = f"{TMDB_BASE_URL}/tv/{tmdb_id}?api_key={TMDB_API_KEY}&language=en-US"
        t_resp = requests.get(t_url, timeout=5)
        if t_resp.status_code == 200:
            td = t_resp.json()
            return {
                'tmdb_id': td.get('id'),
                'media_type': 'tv',
                'title': td.get('name'),
                'overview': td.get('overview'),
                'poster_path': td.get('poster_path'),
                'first_air_date': td.get('first_air_date')
            }
    except Exception:
        pass

    return {}

@app.post("/interact")
def record_interaction(input_data: InteractionInput, db: Session = Depends(get_db)):
    """
    Records a user interaction (Like/Watch) for a guest user.
    Creates a shadow user account if one doesn't exist.
    """
    # 1. Find or Create User
    user = db.query(models.User).filter(models.User.username == input_data.guest_id).first()
    if not user:
        user = models.User(username=input_data.guest_id, email=f"{input_data.guest_id}@guest.nautilus.local")
        db.add(user)
        db.commit()
        db.refresh(user)
    
    # 2. Record Interaction

    # Ensure movie or TV show exists in DB, insert if missing, always use DB id for interaction
    if input_data.media_type == 'movie':
        # Try to find by tmdb_id first (since item_id may be tmdb_id from frontend)
        movie = db.query(models.Movie).filter(models.Movie.tmdb_id == input_data.item_id).first()
        if not movie:
            # Fetch from TMDB and insert
            movie_data = fetch_movie_details(input_data.item_id)
            if not movie_data:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="Movie not found in external source.")
            movie = models.Movie(
                title=movie_data['title'],
                tmdb_id=movie_data.get('tmdb_id'),
                overview=movie_data.get('overview'),
                release_date=movie_data.get('release_date'),
                genres=movie_data.get('genres'),
                poster_path=movie_data.get('poster_path'),
                popularity_score=movie_data.get('popularity_score'),
                stream_url=movie_data.get('stream_url'),
                is_downloaded=False,
                file_path=None
            )
            db.add(movie)
            db.commit()
            db.refresh(movie)
        # Always use the DB id for the interaction
        item_db_id = movie.id
    elif input_data.media_type == 'tv':
        tv_show = db.query(models.TVShow).filter(models.TVShow.tmdb_id == input_data.item_id).first()
        if not tv_show:
            tv_data = fetch_tv_details(input_data.item_id)
            if not tv_data:
                from fastapi import HTTPException
                raise HTTPException(status_code=400, detail="TV Show not found in external source.")
            tv_show = models.TVShow(
                title=tv_data['title'],
                tmdb_id=tv_data.get('tmdb_id'),
                overview=tv_data.get('overview'),
                genres=tv_data.get('genres'),
                poster_path=tv_data.get('poster_path'),
                popularity_score=tv_data.get('popularity_score')
            )
            db.add(tv_show)
            db.commit()
            db.refresh(tv_show)
        item_db_id = tv_show.id
    else:
        item_db_id = input_data.item_id

    # Handle 'dislike' (Un-Like)
    if input_data.action == 'dislike':
        existing_like = db.query(models.Interaction).filter(
            models.Interaction.user_id == user.id,
            models.Interaction.movie_id == (item_db_id if input_data.media_type == 'movie' else None),
            models.Interaction.tv_show_id == (item_db_id if input_data.media_type == 'tv' else None),
            models.Interaction.interaction_type == 'like'
        ).first()
        if existing_like:
            db.delete(existing_like)
            db.commit()
            return {"status": "unliked", "user_id": user.id}
        return {"status": "nothing_to_unlike", "user_id": user.id}

    # Check if already exists
    existing = db.query(models.Interaction).filter(
        models.Interaction.user_id == user.id,
        models.Interaction.movie_id == (item_db_id if input_data.media_type == 'movie' else None),
        models.Interaction.tv_show_id == (item_db_id if input_data.media_type == 'tv' else None),
        models.Interaction.interaction_type == input_data.action
    ).first()
    if not existing:
        interaction = models.Interaction(
            user_id=user.id,
            movie_id=item_db_id if input_data.media_type == 'movie' else None,
            tv_show_id=item_db_id if input_data.media_type == 'tv' else None,
            interaction_type=input_data.action,
            rating_value=1.0 # Implicit positive feedback
        )
        db.add(interaction)
        db.commit()
        return {"status": "recorded", "user_id": user.id}
    return {"status": "exists", "user_id": user.id}

@app.get("/recommend/guest/{guest_id}")
def get_guest_recommendations(guest_id: str, request: Request, db: Session = Depends(get_db)):
    """
    Hybrid Recommender for Guest Users.
    1. Content-Based: Finds movies similar to what the user 'liked' OR 'watched'.
    2. Fallback: Popular movies.
    """
    user = db.query(models.User).filter(models.User.username == guest_id).first()
    
    target_genres = set()
    liked_movie_ids = []

    if user:
        # 1. Get Movie Interactions
        movie_interactions = db.query(models.Interaction).filter(
            models.Interaction.user_id == user.id,
            models.Interaction.interaction_type.in_(['like', 'watch']),
            models.Interaction.movie_id.isnot(None)
        ).all()
        liked_movie_ids = [i.movie_id for i in movie_interactions]
        if liked_movie_ids:
            movies = db.query(models.Movie).filter(models.Movie.id.in_(liked_movie_ids)).all()
            for m in movies:
                if m.genres and isinstance(m.genres, list):
                    target_genres.update(m.genres)
                elif m.genres and isinstance(m.genres, dict):
                    target_genres.update(m.genres.keys())

        # 2. Get TV Show Interactions (for genre signals)
        tv_interactions = db.query(models.Interaction).filter(
            models.Interaction.user_id == user.id,
            models.Interaction.interaction_type.in_(['like', 'watch']),
            models.Interaction.tv_show_id.isnot(None)
        ).all()
        tv_ids = [i.tv_show_id for i in tv_interactions]
        if tv_ids:
            shows = db.query(models.TVShow).filter(models.TVShow.id.in_(tv_ids)).all()
            for s in shows:
                if s.genres and isinstance(s.genres, list):
                    target_genres.update(s.genres)
                elif s.genres and isinstance(s.genres, dict):
                    target_genres.update(s.genres.keys())

    # Apply client-provided preferences (if any) via header X-User-Prefs: JSON string
    try:
        prefs_raw = request.headers.get('x-user-prefs')
        if prefs_raw:
            import json as _json
            prefs = _json.loads(prefs_raw)
            # Accept a simple structure: { "genres": ["Drama","Action"], "min_popularity": 5 }
            if isinstance(prefs, dict):
                genres_pref = prefs.get('genres') or prefs.get('preferred_genres')
                if genres_pref and isinstance(genres_pref, list):
                    for g in genres_pref:
                        try:
                            target_genres.add(g)
                        except Exception:
                            pass
                # Optional min_popularity can filter candidates later (handled below)
                min_pop_pref = prefs.get('min_popularity') if isinstance(prefs.get('min_popularity'), (int, float)) else None
            else:
                min_pop_pref = None
        else:
            min_pop_pref = None
    except Exception:
        min_pop_pref = None

    if not target_genres:
        return db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).limit(12).all()

    # Find candidates that share at least one genre, excluding already liked
    # Note: This is a simple heuristic. For production, use vector similarity.
    # Allow client preference to raise popularity floor if provided
    candidates_q = db.query(models.Movie).filter(models.Movie.id.notin_(liked_movie_ids), models.Movie.popularity_score.isnot(None)).order_by(models.Movie.popularity_score.desc())
    if min_pop_pref is not None:
        try:
            candidates_q = candidates_q.filter(models.Movie.popularity_score >= float(min_pop_pref))
        except Exception:
            pass
    candidates = candidates_q.limit(500).all()

    scored_candidates = []
    for cand in candidates:
        score = 0
        cand_genres = []
        if cand.genres and isinstance(cand.genres, list):
            cand_genres = cand.genres
        elif cand.genres and isinstance(cand.genres, dict):
            cand_genres = list(cand.genres.keys())
            
        # Jaccard Similarity for Genres
        intersection = len(set(cand_genres) & target_genres)
        if intersection > 0:
            score = intersection
            scored_candidates.append((cand, score))
            
    # Sort by score
    scored_candidates.sort(key=lambda x: x[1], reverse=True)
    
    # Before returning content-based results, try to use the NCF model if available
    try:
        model, artifacts = load_recommender_ncf()
        if model is not None and artifacts is not None:
            user_id_to_idx = artifacts.get('user_id_to_idx', {})
            movie_id_to_idx = artifacts.get('movie_id_to_idx', {})

            # If the guest has liked movies, try to find an existing similar user by overlap
            similar_user_idx = None
            if liked_movie_ids:
                # Find users who interacted with the same movies and pick the one with largest overlap
                rows = db.query(models.Interaction.user_id, func.count(models.Interaction.id).label('cnt'))\
                         .filter(models.Interaction.movie_id.in_(liked_movie_ids), models.Interaction.interaction_type.in_(['like','watch']))\
                         .group_by(models.Interaction.user_id).order_by(func.count(models.Interaction.id).desc()).limit(10).all()
                for r in rows:
                    uid = r[0]
                    if uid in user_id_to_idx:
                        similar_user_idx = user_id_to_idx[uid]
                        break

            # If we found a similar user index and have candidate item idxs, run NCF inference
            if similar_user_idx is not None:
                import numpy as _np
                # Build candidate list filtered to those present in artifacts
                candidate_item_ids = [int(c.id) for c in candidates if c.id in movie_id_to_idx]
                candidate_item_idxs = [movie_id_to_idx[cid] for cid in candidate_item_ids]
                if candidate_item_idxs:
                    user_arr = _np.full(len(candidate_item_idxs), similar_user_idx, dtype=_np.int32)
                    item_arr = _np.array(candidate_item_idxs, dtype=_np.int32)
                    scores = model.predict([user_arr, item_arr], verbose=0).reshape(-1)
                    if scores.size > 0:
                        order = _np.argsort(-scores)[:12]
                        top_movie_ids = [candidate_item_ids[i] for i in order]
                        movies = db.query(models.Movie).filter(models.Movie.id.in_(top_movie_ids)).all()
                        by_id = {m.id: m for m in movies}
                        ordered = [by_id[mid] for mid in top_movie_ids if mid in by_id]
                        if ordered:
                            return ordered
    except Exception as e:
        # NCF path failed; fall back to content-based
        print(f"Guest NCF attempt failed: {e}")

    # Return top 12 content-based candidates
    return [x[0] for x in scored_candidates[:12]]