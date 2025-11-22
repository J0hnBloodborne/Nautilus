from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Text, JSON, DateTime, Boolean
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func

# DATABASE CONNECTION
DATABASE_URL = "postgresql://admin:password123@localhost:5432/ai321_db"

Base = declarative_base()

# --- CONTENT TABLES ---
class Movie(Base):
    __tablename__ = 'movies'
    
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    tmdb_id = Column(Integer, unique=True, index=True)
    overview = Column(Text)
    release_date = Column(String)
    genres = Column(JSON)           # Feature: Classification
    poster_path = Column(String)
    popularity_score = Column(Float) # Feature: Regression
    embedding = Column(JSON)        # Feature: Clustering/Dim Reduction
    
    # File Management
    stream_url = Column(String)
    is_downloaded = Column(Boolean, default=False)
    file_path = Column(String)      # MinIO path

    ratings = relationship("Interaction", back_populates="movie")

class TVShow(Base):
    __tablename__ = 'tv_shows'
    
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    tmdb_id = Column(Integer, unique=True, index=True)
    overview = Column(Text)
    genres = Column(JSON)
    poster_path = Column(String)
    popularity_score = Column(Float)
    
    seasons = relationship("Season", back_populates="show", cascade="all, delete-orphan")

class Season(Base):
    __tablename__ = 'seasons'
    id = Column(Integer, primary_key=True)
    show_id = Column(Integer, ForeignKey('tv_shows.id'))
    season_number = Column(Integer)
    name = Column(String)
    
    show = relationship("TVShow", back_populates="seasons")
    episodes = relationship("Episode", back_populates="season", cascade="all, delete-orphan")

class Episode(Base):
    __tablename__ = 'episodes'
    id = Column(Integer, primary_key=True)
    season_id = Column(Integer, ForeignKey('seasons.id'))
    episode_number = Column(Integer)
    title = Column(String)
    overview = Column(Text)
    
    # File Management
    stream_url = Column(String)
    is_downloaded = Column(Boolean, default=False)
    file_path = Column(String)
    
    season = relationship("Season", back_populates="episodes")

# --- USER & ANALYTICS ---
class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True)
    password_hash = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    interactions = relationship("Interaction", back_populates="user")

class Interaction(Base):
    __tablename__ = 'interactions'
    # Tracks 'likes', 'views', 'ratings' for RecSys
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    movie_id = Column(Integer, ForeignKey('movies.id'))
    interaction_type = Column(String) # 'view', 'rating'
    rating_value = Column(Float)      # 1-5
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    
    user = relationship("User", back_populates="interactions")
    movie = relationship("Movie", back_populates="ratings")

# --- MLOPS & LOGGING ---
class SystemLog(Base):
    __tablename__ = 'system_logs'
    # For Time Series & Drift Detection
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    metric_name = Column(String) # e.g., 'api_latency', 'daily_active_users'
    metric_value = Column(Float)

class MLModel(Base):
    __tablename__ = 'ml_models'
    # Model Registry: Tracks versions and performance
    id = Column(Integer, primary_key=True)
    name = Column(String)           # e.g., 'recommender_v1'
    version = Column(String)        # e.g., '1.0.0'
    model_type = Column(String)     # 'classification', 'regression', 'recommender'
    file_path = Column(String)      # Path in MinIO (e.g., 'models/rec_v1.pkl')
    metrics = Column(JSON)          # {'accuracy': 0.85, 'rmse': 1.2}
    is_active = Column(Boolean, default=False) # Is this the one currently live?
    created_at = Column(DateTime(timezone=True), server_default=func.now())

def init_db():
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    print("Database initialized.")

if __name__ == "__main__":
    init_db()