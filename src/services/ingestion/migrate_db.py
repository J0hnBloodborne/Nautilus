from sqlalchemy import create_engine, text, inspect
import os
from dotenv import load_dotenv
import sys

sys.path.append(os.getcwd())
from src.core.models import Base 

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)

def run_migration():
    print("Starting Safe Schema Migration...")
    inspector = inspect(engine)
    
    with engine.connect() as conn:
        # 1. Create New Tables (like MLModel)
        Base.metadata.create_all(engine)
        
        # 2. Patch 'movies'
        cols = [c['name'] for c in inspector.get_columns('movies')]
        if 'embedding' not in cols:
            print("Injecting 'embedding' column...")
            conn.execute(text("ALTER TABLE movies ADD COLUMN embedding JSON;"))
        
        # 3. Patch 'interactions'
        cols = [c['name'] for c in inspector.get_columns('interactions')]
        if 'tv_show_id' not in cols:
            print("Injecting 'tv_show_id' column...")
            conn.execute(text("ALTER TABLE interactions ADD COLUMN tv_show_id INTEGER REFERENCES tv_shows(id);"))
            
        conn.commit()
        print("Migration Complete. Cargo is safe.")

if __name__ == "__main__":
    run_migration()