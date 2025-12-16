import sys

from src.core import models
from src.core.database import engine, SessionLocal


def main():
    # engine is created from DATABASE_URL in src/core/database
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(models.Movie).filter_by(tmdb_id=999999).first()
        if not existing:
            m = models.Movie(title='CI Test Movie', tmdb_id=999999, overview='CI seed', popularity_score=1.0)
            db.add(m)
            db.commit()
            print('Seeded test Movie.')
        else:
            print('Seed already present.')
    finally:
        db.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('CI seed failed:', e, file=sys.stderr)
        sys.exit(2)
