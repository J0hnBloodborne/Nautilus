import random
from faker import Faker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import User, Interaction, Movie
from passlib.context import CryptContext
import os
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

fake = Faker()
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def create_fake_users(n=50):
    print(f"Cloning {n} synthetic users...")
    users = []
    for _ in range(n):
        # Create a fake profile
        profile = fake.simple_profile()
        username = profile['username']
        email = profile['mail']
        
        # Ensure uniqueness (simple check)
        if session.query(User).filter_by(username=username).first():
            continue

        user = User(
            username=username,
            email=email,
            password_hash=pwd_context.hash("password123") # Default password
        )
        session.add(user)
        users.append(user)
    
    session.commit()
    print("Users created.")
    return session.query(User).all()

def create_fake_interactions(users, min_ratings=5, max_ratings=20):
    print("Generating synthetic viewing habits...")
    movies = session.query(Movie).all()
    
    if not movies:
        print("No movies found! Run ingest.py first.")
        return

    count = 0
    for user in users:
        # Each user rates a random number of movies
        num_ratings = random.randint(min_ratings, max_ratings)
        rated_movies = random.sample(movies, min(len(movies), num_ratings))
        
        for movie in rated_movies:
            # Simulate a rating (weighted towards positive, because people watch what they like)
            rating = random.choices([1, 2, 3, 4, 5], weights=[5, 10, 20, 35, 30])[0]
            
            interaction = Interaction(
                user_id=user.id,
                movie_id=movie.id,
                interaction_type="rating",
                rating_value=float(rating)
            )
            session.add(interaction)
            count += 1
            
    session.commit()
    print(f"Generated {count} interactions.")

if __name__ == "__main__":
    print("INITIATING SYNTHETIC DATA GENERATION...")
    users = create_fake_users(50)
    create_fake_interactions(users)
    print("POPULATION COMPLETE. The matrix is populated.")