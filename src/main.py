from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles # Import this
from fastapi.responses import FileResponse # Import this
from sqlalchemy.orm import Session
from database import get_db
import models

app = FastAPI(
    title="Nautilus AI321 Media Streaming MLOps System",
    description="End-to-End MLOps Pipeline for Media Streaming",
    version="1.0.0"
)
app.mount("/static", StaticFiles(directory="src/static"), name="static")

@app.get("/")
def read_root():
    return {"status": "online", "message": "AI321 System is Operational"}

@app.get("/movies")
def get_movies(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    movies = db.query(models.Movie).offset(skip).limit(limit).all()
    return movies

@app.get("/movies/{movie_id}")
def get_movie(movie_id: int, db: Session = Depends(get_db)):
    movie = db.query(models.Movie).filter(models.Movie.id == movie_id).first()
    if not movie: raise HTTPException(status_code=404, detail="Movie not found")
    return movie

@app.get("/shows")
def get_shows(skip: int = 0, limit: int = 20, db: Session = Depends(get_db)):
    shows = db.query(models.TVShow).offset(skip).limit(limit).all()
    return shows