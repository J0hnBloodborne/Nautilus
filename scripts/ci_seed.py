import sys

from src.core import models
from src.core.database import engine, SessionLocal


def main():
    # engine is created from DATABASE_URL in src/core/database
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Ensure a small, diverse seed dataset so DeepChecks has multiple values to validate
        seeds = [
            {'tmdb_id': 999997, 'title': 'CI Seed A', 'overview': 'Seed A', 'popularity_score': 1.0},
            {'tmdb_id': 999998, 'title': 'CI Seed B', 'overview': 'Seed B', 'popularity_score': 5.0},
            {'tmdb_id': 999999, 'title': 'CI Seed C', 'overview': 'Seed C', 'popularity_score': 10.0},
        ]

        added = 0
        for s in seeds:
            exists = db.query(models.Movie).filter_by(tmdb_id=s['tmdb_id']).first()
            if not exists:
                m = models.Movie(title=s['title'], tmdb_id=s['tmdb_id'], overview=s['overview'], popularity_score=s['popularity_score'])
                db.add(m)
                added += 1

        if added > 0:
            db.commit()
            print(f'Seeded {added} test Movie(s).')
        else:
            print('Seeds already present.')
    finally:
        db.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print('CI seed failed:', e, file=sys.stderr)
        sys.exit(2)
