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
from datetime import datetime
from dotenv import load_dotenv
from tensorflow import keras as _keras
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
    item, type_ = get_media_item(db, tmdb_id)
    
    if not item:
        return {"prediction": "N/A"}
    
    # Regression model was trained on Movies only (Budget/Revenue).
    # TV Shows don't fit this model well.
    if type_ == 'tv':
        return {"label": "TV SERIES", "value": "N/A"}

    model_path = "src/models/revenue_regressor.pkl"
    if not os.path.exists(model_path): 
        return {"prediction": "N/A"}
        
    try:
        # Fetch real details from TMDB to get Budget/Runtime/Genres
        # The DB might lack these specific fields or they might be outdated
        api_key = os.getenv("TMDB_API_KEY")
        budget = 0
        runtime = 0
        release_month = 0
        genres = []
        
        # Try to get data from item first if available (future proofing)
        if hasattr(item, 'budget') and item.budget: 
            budget = item.budget
        if hasattr(item, 'runtime') and item.runtime:
            runtime = item.runtime
        
        # Fetch from TMDB if missing
        if (budget == 0 or runtime == 0) and api_key:
            try:
                url = f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={api_key}"
                resp = requests.get(url, timeout=2)
                if resp.status_code == 200:
                    data = resp.json()
                    budget = data.get('budget', 0)
                    runtime = data.get('runtime', 0)
                    genres = [g['name'] for g in data.get('genres', [])]
                    rd = data.get('release_date', '')
                    if rd:
                        try:
                            release_month = datetime.strptime(rd, "%Y-%m-%d").month
                        except Exception:
                            pass
            except Exception as e:
                print(f"TMDB Fetch Error: {e}")

        # Fallback defaults
        if budget == 0: 
            budget = 1000000 # Default 1M (True Indie)
        if runtime == 0: 
            runtime = 90 
        
        # Feature Vector Construction
        # Model expects: ['budget', 'runtime', 'release_month'] + [Action, Adventure, ..., Sci-Fi]
        top_genres = ['Action', 'Adventure', 'Animation', 'Comedy', 'Crime', 'Drama', 'Family', 'Fantasy', 'Horror', 'Science Fiction']
        
        features = [budget, runtime, release_month]
        for g in top_genres:
            features.append(1 if g in genres else 0)
            
        vector = np.array([features], dtype=np.float32)
        
        model = joblib.load(model_path)
        prediction = model.predict(vector)[0]
        
        print(f"PREDICTION DEBUG: ID={tmdb_id} Budget=${budget} Runtime={runtime} Pred=${prediction:,.0f}")

        # Dynamic Labeling
        if prediction > 500000000:
            label = "MEGA-HIT"
        elif prediction > 100000000:
            label = "BLOCKBUSTER"
        elif prediction > 25000000:
            label = "MAINSTREAM"
        else:
            label = "INDIE"
            
        return {"label": label, "value": f"${prediction/1000000:.1f}M"}
    except Exception as e:
        print(f"Prediction Error: {e}")
        return {"label": "UNKNOWN", "value": "N/A"}

@app.get("/predict/genre/{tmdb_id}")
def get_genre_prediction(tmdb_id: int, db: Session = Depends(get_db)):
    """Predict genres from plot using the multi-label FFNN model.

    Returns multiple genres with scores plus a primary genre for legacy UI.
    """
    item, type_ = get_media_item(db, tmdb_id)

    if not item or not item.overview:
        return {"genres": [], "primary": None}

    model_path = "src/models/genre_multilabel_ffnn.keras"
    artifacts_path = "src/models/genre_multilabel_ffnn_artifacts.pkl"
    if not os.path.exists(model_path) or not os.path.exists(artifacts_path):
        # Fallback: old behavior using single-label classifier
        legacy_path = "src/models/genre_classifier.pkl"
        if not os.path.exists(legacy_path):
            return {"genres": [], "primary": None}
        try:
            artifact = joblib.load(legacy_path)
            model = artifact['model']
            vectorizer = artifact['vectorizer']
            idx_to_genre = artifact.get('idx_to_genre')

            vec = vectorizer.transform([item.overview])
            if 'cuml' in str(type(model)):
                vec = vec.toarray().astype(np.float32)

            pred = model.predict(vec)
            if hasattr(pred, 'get'):
                pred = pred.get()
            class_idx = int(pred[0])

            if idx_to_genre is not None:
                genre_id = int(idx_to_genre.get(class_idx, -1))
            else:
                le = artifact['encoder']
                genre_id = int(le.inverse_transform([class_idx])[0])

            name = TMDB_GENRE_MAP.get(genre_id, "Unknown")
            primary = {"id": genre_id, "name": name, "score": 1.0}
            return {"genres": [primary], "primary": primary}
        except Exception as e:
            print(f"Legacy Genre Error: {e}")
            return {"genres": [], "primary": None}

    try:
        artifact = joblib.load(artifacts_path)
        vectorizer = artifact["vectorizer"]
        svd = artifact["svd"]
        idx_to_genre = artifact["idx_to_genre"]

        # Lazy-load and cache model in process-global variable
        global _MULTI_LABEL_MODEL
        try:
            _MULTI_LABEL_MODEL
        except NameError:
            _MULTI_LABEL_MODEL = None

        if _MULTI_LABEL_MODEL is None:
            _MULTI_LABEL_MODEL = _keras.models.load_model(model_path)

        # Use title + overview for richer signal
        title = item.title or ""
        overview = item.overview or ""
        text = f"{title} {overview}".strip()

        vec = vectorizer.transform([text])
        X = svd.transform(vec).astype("float32")

        proba = _MULTI_LABEL_MODEL.predict(X, verbose=0)[0]

        threshold = 0.5
        genres = []
        for idx, score in enumerate(proba):
            if score < threshold:
                continue
            tmdb_genre_id = int(idx_to_genre.get(idx, -1))
            name = TMDB_GENRE_MAP.get(tmdb_genre_id)
            if not name:
                continue
            genres.append({
                "id": tmdb_genre_id,
                "name": name,
                "score": float(score),
            })

        genres.sort(key=lambda g: g["score"], reverse=True)

        if not genres:
            best_idx = int(proba.argmax())
            tmdb_genre_id = int(idx_to_genre.get(best_idx, -1))
            name = TMDB_GENRE_MAP.get(tmdb_genre_id, "Unknown")
            genres = [{
                "id": tmdb_genre_id,
                "name": name,
                "score": float(proba[best_idx]),
            }]

        primary = genres[0] if genres else None
        return {"genres": genres, "primary": primary}
    except Exception as e:
        print(f"Multi-label Genre Error: {e}")
        return {"genres": [], "primary": None}
    
_ASSOC_RULES = None


def load_association_rules():
    """Lazy-load association rules lookup if available.

    The model is a dict mapping TMDB movie IDs to lists of related TMDB IDs.
    """
    global _ASSOC_RULES
    if _ASSOC_RULES is not None:
        return _ASSOC_RULES

    path = "src/models/association_rules.pkl"
    if not os.path.exists(path):
        return None

    try:
        _ASSOC_RULES = joblib.load(path)
        print("Association rules loaded.")
    except Exception as e:
        print(f"Error loading association rules: {e}")
        _ASSOC_RULES = None
    return _ASSOC_RULES


@app.get("/related/{tmdb_id}")
def get_related_movies(tmdb_id: int, db: Session = Depends(get_db)):
    """Association- and genre-based related items.

    Movies:
      * Prefer association_rules.pkl (TMDB -> [TMDB ...]) to fetch related
        movies.
      * If rules are missing/empty, fall back to sampling movies that share
        at least one genre with the source movie (when genres are present),
        otherwise popularity-based.
    TV shows:
      * Recommend other popular TV shows only.
    """
    rules = load_association_rules()

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
    genres: List[str] = []

@app.post("/predict/revenue")
def predict_revenue_manual(input_data: RevenueInput):
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
        
        return {"prediction": f"${prediction:,.0f}", "raw_value": float(prediction)}
            
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

    # Ensure movie or TV show exists in DB, insert if missing
    if input_data.media_type == 'movie':
        movie = db.query(models.Movie).filter(models.Movie.id == input_data.item_id).first()
        if not movie:
            # Check by tmdb_id first to avoid duplicates
            movie_by_tmdb = db.query(models.Movie).filter(models.Movie.tmdb_id == input_data.item_id).first()
            if movie_by_tmdb:
                movie = movie_by_tmdb
            else:
                movie_data = fetch_movie_details(input_data.item_id)
                if not movie_data:
                    from fastapi import HTTPException
                    raise HTTPException(status_code=400, detail="Movie not found in external source.")
                movie = models.Movie(
                    id=movie_data['id'],
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
    elif input_data.media_type == 'tv':
        tv_show = db.query(models.TVShow).filter(models.TVShow.id == input_data.item_id).first()
        if not tv_show:
            tv_by_tmdb = db.query(models.TVShow).filter(models.TVShow.tmdb_id == input_data.item_id).first()
            if tv_by_tmdb:
                tv_show = tv_by_tmdb
            else:
                tv_data = fetch_tv_details(input_data.item_id)
                if not tv_data:
                    from fastapi import HTTPException
                    raise HTTPException(status_code=400, detail="TV Show not found in external source.")
                tv_show = models.TVShow(
                    id=tv_data['id'],
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

    # Handle 'dislike' (Un-Like)
    if input_data.action == 'dislike':
        existing_like = db.query(models.Interaction).filter(
            models.Interaction.user_id == user.id,
            models.Interaction.movie_id == (input_data.item_id if input_data.media_type == 'movie' else None),
            models.Interaction.tv_show_id == (input_data.item_id if input_data.media_type == 'tv' else None),
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
        models.Interaction.movie_id == (input_data.item_id if input_data.media_type == 'movie' else None),
        models.Interaction.tv_show_id == (input_data.item_id if input_data.media_type == 'tv' else None),
        models.Interaction.interaction_type == input_data.action
    ).first()
    
    if not existing:
        interaction = models.Interaction(
            user_id=user.id,
            movie_id=input_data.item_id if input_data.media_type == 'movie' else None,
            tv_show_id=input_data.item_id if input_data.media_type == 'tv' else None,
            interaction_type=input_data.action,
            rating_value=1.0 # Implicit positive feedback
        )
        db.add(interaction)
        db.commit()
        return {"status": "recorded", "user_id": user.id}
    
    return {"status": "exists", "user_id": user.id}

@app.get("/recommend/guest/{guest_id}")
def get_guest_recommendations(guest_id: str, db: Session = Depends(get_db)):
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

    if not target_genres:
        return db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).limit(12).all()

    # Find candidates that share at least one genre, excluding already liked
    # Note: This is a simple heuristic. For production, use vector similarity.
    candidates = db.query(models.Movie).filter(
        models.Movie.id.notin_(liked_movie_ids),
        models.Movie.popularity_score.isnot(None)
    ).order_by(models.Movie.popularity_score.desc()).limit(200).all()

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
    
    # Return top 12
    return [x[0] for x in scored_candidates[:12]]