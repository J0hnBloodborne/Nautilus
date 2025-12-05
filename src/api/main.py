from fastapi import FastAPI, Depends, Request, UploadFile, File
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
import joblib
import numpy as np
import glob
import ctypes
import sys
from dotenv import load_dotenv

TMDB_GENRE_MAP = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Sci-Fi", 10770: "TV Movie",
    53: "Thriller", 10752: "War", 37: "Western"
}

try:
    import cuml
    from cuml.ensemble import RandomForestRegressor
    from cuml.linear_model import LogisticRegression
    from cuml.ensemble import RandomForestClassifier 
    w = cuml.RandomForestRegressor()
    x = RandomForestRegressor()
    y = LogisticRegression()
    z = RandomForestClassifier()
    print("GPU MODULES: Pre-loaded successfully.")
except ImportError:
    print("GPU MODULES: Not found (Running on CPU mode).")
except Exception as e:
    print(f"GPU MODULES: Pre-load error: {e}")

# Dummy references to avoid linter errors

def force_gpu_linkage():
    print("Hunting for NVRTC library...")
    found = False
    for p in sys.path:
        pattern = os.path.join(p, "nvidia", "*", "lib", "libnvrtc.so.12")
        matches = glob.glob(pattern)
        if matches:
            lib_path = matches[0]
            lib_dir = os.path.dirname(lib_path)
            current_ld = os.environ.get('LD_LIBRARY_PATH', '')
            if lib_dir not in current_ld:
                os.environ['LD_LIBRARY_PATH'] = f"{lib_dir}:{current_ld}"
            try:
                ctypes.CDLL(lib_path)
                found = True
                break
            except Exception:
                pass
    if not found: 
        print("GPU binding might fail.")

force_gpu_linkage()

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
    
    return {
        "users": user_count,
        "movies": movie_count,
        "shows": show_count,
        "models": models_list
    }

@app.get("/recommend/personal/{user_id}")
def get_personal_recs(user_id: int, db: Session = Depends(get_db)):
    """RecSys: SVD Inference"""
    model_path = "src/models/recommender_v1.pkl"
    if not os.path.exists(model_path):
        # Fallback random
        return db.query(models.Movie).order_by(func.random()).limit(10).all()
    
    try:
        # In production we'd load user vector. Here we simulate personalization.
        return db.query(models.Movie).order_by(func.random()).limit(12).all()
    except Exception:
        return []

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
    item, type = get_media_item(db, tmdb_id)
    
    if not item:
        return {"prediction": "N/A"}
    
    # Regression model was trained on Movies only (Budget/Revenue).
    # TV Shows don't fit this model well.
    if type == 'tv':
        return {"label": "TV SERIES", "value": "N/A"}

    model_path = "src/models/revenue_regressor.pkl"
    if not os.path.exists(model_path): 
        return {"prediction": "N/A"}
        
    try:
        model = joblib.load(model_path)
        features = np.array([[100000000, 120, item.popularity_score or 5.0]], dtype=np.float32)
        prediction = model.predict(features)[0]
        label = "BLOCKBUSTER" if prediction > 100000000 else "INDIE"
        return {"label": label, "value": f"${prediction/1000000:.0f}M"}
    except Exception:
        return {"label": "UNKNOWN", "value": "N/A"}

@app.get("/predict/genre/{tmdb_id}")
def get_genre_prediction(tmdb_id: int, db: Session = Depends(get_db)):
    """
    Predicts genre from plot. Handles both Movies and TV.
    """
    item, type_ = get_media_item(db, tmdb_id)
    
    if not item or not item.overview:
        return {"genre": "Unknown (No Data)"}

    model_path = "src/models/genre_classifier.pkl"
    if not os.path.exists(model_path):
        return {"genre": "Unknown (No Model)"}

    try:
        artifact = joblib.load(model_path)
        model = artifact['model']
        vectorizer = artifact['vectorizer']
        idx_to_genre = artifact.get('idx_to_genre')  # NEW

        # Vectorize
        vec = vectorizer.transform([item.overview])

        # Handle GPU (Convert sparse matrix to dense float32)
        if 'cuml' in str(type(model)):
            vec = vec.toarray().astype(np.float32)

        # Predict class index (0..N-1)
        pred = model.predict(vec)
        if hasattr(pred, 'get'):
            pred = pred.get()
        class_idx = int(pred[0])

        # Map class index -> TMDB genre ID
        if idx_to_genre is not None:
            genre_id = int(idx_to_genre.get(class_idx, -1))
        else:
            # Fallback: old behavior using encoder (shouldn't really happen now)
            le = artifact['encoder']
            genre_id = int(le.inverse_transform([class_idx])[0])

        genre_name = TMDB_GENRE_MAP.get(genre_id, "Unknown")
        return {"genre": genre_name}
    except Exception as e:
        print(f"Genre Error: {e}")
        return {"genre": "Unknown"}
    
@app.get("/related/{tmdb_id}")
def get_related_movies(tmdb_id: int, db: Session = Depends(get_db)):
    """Association Rules: Related Movies"""
    # For demo, we fallback to content filtering if exact rules missing
    movie = db.query(models.Movie).filter(models.Movie.tmdb_id == tmdb_id).first()
    if movie:
        return db.query(models.Movie).filter(models.Movie.id != movie.id).order_by(func.random()).limit(4).all()
    return []

@app.get("/collections/ai")
def get_ai_clusters(db: Session = Depends(get_db)):
    """Clustering: Hidden Genres"""
    # Simulate clusters for UI
    c1 = db.query(models.Movie).filter(models.Movie.popularity_score > 100).limit(15).all()
    c2 = db.query(models.Movie).filter(models.Movie.popularity_score < 50).limit(15).all()
    return {"cluster_1": c1, "cluster_2": c2}

# --- 2. CORE FEATURES ---

@app.get("/search")
def search_content(query: str, db: Session = Depends(get_db)):
    local_movies = db.query(models.Movie).filter(models.Movie.title.ilike(f"%{query}%")).limit(5).all()
    local_shows = db.query(models.TVShow).filter(models.TVShow.title.ilike(f"%{query}%")).limit(5).all()
    
    if len(local_movies) + len(local_shows) > 0:
        return local_movies + local_shows
    
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
                results.append(movie)
        elif item['media_type'] == 'tv':
            if not db.query(models.TVShow).filter_by(tmdb_id=item['id']).first():
                show = models.TVShow(
                    title=item.get('name'), tmdb_id=item.get('id'), overview=item.get('overview'),
                    poster_path=item.get('poster_path'), popularity_score=item.get('popularity')
                )
                db.add(show)
                results.append(show)
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

@app.get("/shows")
def get_shows(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return db.query(models.TVShow).order_by(models.TVShow.popularity_score.desc()).offset(skip).limit(limit).all()

@app.get("/shows/{show_id}/seasons")
def get_seasons(show_id: int, db: Session = Depends(get_db)):
    show = db.query(models.TVShow).options(
        joinedload(models.TVShow.seasons).joinedload(models.Season.episodes)
    ).filter(models.TVShow.id == show_id).first()
    
    if show and show.seasons:
        sorted_seasons = sorted(show.seasons, key=lambda s: s.season_number)
        for season in sorted_seasons:
            season.episodes.sort(key=lambda e: e.episode_number)
        return sorted_seasons

    if show and TMDB_API_KEY:
        url = f"https://api.themoviedb.org/3/tv/{show.tmdb_id}?api_key={TMDB_API_KEY}&language=en-US"
        data = requests.get(url).json()
        for season_meta in data.get("seasons", []):
            season = models.Season(
                show_id=show.id, season_number=season_meta['season_number'],
                name=season_meta['name'], air_date=season_meta['air_date']
            )
            db.add(season)
            db.commit()
            s_url = f"https://api.themoviedb.org/3/tv/{show.tmdb_id}/season/{season.season_number}?api_key={TMDB_API_KEY}&language=en-US"
            s_data = requests.get(s_url).json()
            for ep in s_data.get("episodes", []):
                episode = models.Episode(
                    season_id=season.id, episode_number=ep['episode_number'],
                    title=ep['name'], overview=ep['overview'],
                    air_date=ep.get('air_date'), still_path=ep.get('still_path')
                )
                db.add(episode)
            db.commit()
        db.refresh(show)
        return sorted(show.seasons, key=lambda s: s.season_number)
    return []