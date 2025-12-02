import random
from faker import Faker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, User, Interaction, Movie, TVShow
from passlib.context import CryptContext
import os
from dotenv import load_dotenv

# Setup
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()
fake = Faker()
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def reset_interactions_table():
    """
    Safe Reset: Drops only the interactions table to apply schema changes
    without deleting your Movies/Shows.
    """
    print("Rebuilding Interactions Table (Schema Update)...")
    try:
        # Drop the table to clear old schema
        Interaction.__table__.drop(engine)
        # Recreate it with new columns
        Interaction.__table__.create(engine)
        print("Schema updated.")
    except Exception as e:
        print(f"Note: {e}")

def create_fake_users(n=50):
    print(f"Cloning {n} synthetic users...")
    users = []
    for _ in range(n):
        profile = fake.simple_profile()
        username = profile['username']
        email = profile['mail']
        
        if session.query(User).filter_by(username=username).first():
            continue

        user = User(
            username=username,
            email=email,
            password_hash=pwd_context.hash("password123")
        )
        session.add(user)
        users.append(user)
    
    session.commit()
    print("Users online.")
    return session.query(User).all()

def seed_ratings(users, min_r=5, max_r=20):
    print("Generating synthetic viewing habits...")
    
    movies = session.query(Movie).all()
    shows = session.query(TVShow).all()
    
    if not movies and not shows:
        print("No content found! Run ingest.py first.")
        return

    count = 0
    for user in users:
        # 1. Rate Movies
        if movies:
            k = random.randint(min_r, max_r)
            watched_movies = random.sample(movies, min(len(movies), k))
            for m in watched_movies:
                rating = random.choices([3, 4, 5], weights=[20, 40, 40])[0]
                interaction = Interaction(
                    user_id=user.id,
                    movie_id=m.id,
                    interaction_type="rating",
                    rating_value=float(rating)
                )
                session.add(interaction)
                count += 1

        # 2. Rate Shows
        if shows:
            k = random.randint(min_r, max_r)
            watched_shows = random.sample(shows, min(len(shows), k))
            for s in watched_shows:
                rating = random.choices([3, 4, 5], weights=[20, 40, 40])[0]
                interaction = Interaction(
                    user_id=user.id,
                    tv_show_id=s.id, # NEW COLUMN
                    interaction_type="rating",
                    rating_value=float(rating)
                )
                session.add(interaction)
                count += 1
            
    session.commit()
    print(f"Generated {count} interactions (Movies + TV).")

if __name__ == "__main__":
    print("INITIATING SEED SEQUENCE...")
    
    # Optional: Uncomment this line if you get a "column tv_show_id does not exist" error
    # reset_interactions_table() 
    
    # Or just verify schema is up to date
    Base.metadata.create_all(engine)
    
    users = create_fake_users(50)
    seed_ratings(users)
    print("POPULATION COMPLETE.")