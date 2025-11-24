from fastapi import FastAPI, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from src.database import get_db
import src.models as models
from src.scrapers.universal import UniversalScraper
import httpx
import os
import requests
from dotenv import load_dotenv

load_dotenv()
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

app = FastAPI(title="Nautilus | Deep Dive")

app.mount("/static", StaticFiles(directory="src/static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse('src/static/index.html')

# --- 1. SEARCH (Keep your existing logic) ---
@app.get("/search")
def search_content(query: str, db: Session = Depends(get_db)):
    # ... (Keep your search logic exactly as it was) ...
    # For brevity, assuming previous search logic remains here
    local_movies = db.query(models.Movie).filter(models.Movie.title.ilike(f"%{query}%")).limit(5).all()
    local_shows = db.query(models.TVShow).filter(models.TVShow.title.ilike(f"%{query}%")).limit(5).all()
    if len(local_movies) + len(local_shows) > 0: return local_movies + local_shows
    
    if not TMDB_API_KEY: return []
    
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
    db.commit()
    return results

# --- 2. THE AGGREGATOR (Updated) ---
@app.get("/play/{media_type}/{tmdb_id}")
async def play_content(media_type: str, tmdb_id: int, season: int = 1, episode: int = 1, provider: str = None):
    scraper = UniversalScraper()
    
    # If provider is "auto", we pass None to let the scraper cycle through all
    target_provider = None if provider == "auto" else provider
    
    result = await scraper.get_stream(tmdb_id, media_type, season, episode, target_provider)
    
    if not result:
        # Fallback to Bunny only for testing connectivity
        return {"url": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8", "type": "direct", "source": "Test Stream"}
        
    return result

# --- 3. PROXY ---
@app.get("/proxy_stream")
async def proxy_stream(url: str, request: Request):
    client = httpx.AsyncClient()
    headers = { "User-Agent": "Mozilla/5.0" }
    req = client.build_request("GET", url, headers=headers)
    r = await client.send(req, stream=True)
    return StreamingResponse(
        r.aiter_bytes(), 
        status_code=r.status_code,
        media_type=r.headers.get("content-type"),
        background=client.aclose
    )

# --- 4. STANDARD LISTS ---
@app.get("/movies")
def get_movies(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return db.query(models.Movie).order_by(models.Movie.popularity_score.desc()).offset(skip).limit(limit).all()

@app.get("/shows")
def get_shows(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return db.query(models.TVShow).order_by(models.TVShow.popularity_score.desc()).offset(skip).limit(limit).all()

@app.get("/shows/{show_id}/seasons")
def get_seasons(show_id: int, db: Session = Depends(get_db)):
    show = db.query(models.TVShow).filter(models.TVShow.id == show_id).first()
    return show.seasons if show else []