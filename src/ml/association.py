import pandas as pd
from mlxtend.frequent_patterns import fpgrowth, association_rules
from mlxtend.preprocessing import TransactionEncoder
import joblib
import os
import sys
from src.core.database import DATABASE_URL
from src.core.models import MLModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# ABSOLUTE PATHS
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(BASE_DIR, '..', '..')
RATINGS_PATH = os.path.join(PROJECT_ROOT, "data/raw/ml-25m/ratings.csv")
LINKS_PATH = os.path.join(PROJECT_ROOT, "data/raw/ml-25m/links.csv")
MODEL_PATH = os.path.join(PROJECT_ROOT, "src/models/association_rules.pkl")
sys.path.append(PROJECT_ROOT)



def run_association_rules():
    print("Loading Mapping (Links)...")
    if not os.path.exists(LINKS_PATH):
        print("links.csv not found.")
        return
        
    # 1. Build Map: MovieLens ID -> TMDB ID
    links = pd.read_csv(LINKS_PATH)
    # Drop rows without TMDB ID
    links = links.dropna(subset=['tmdbId'])
    # Create dictionary: {ml_id: tmdb_id}
    ml_to_tmdb = dict(zip(links['movieId'], links['tmdbId'].astype(int)))
    
    print("Loading Ratings...")
    # Load larger chunk for better rules
    df = pd.read_csv(RATINGS_PATH, nrows=500000)
    
    # Filter Top 500 Movies for density
    top_movies = df['movieId'].value_counts().head(500).index
    df = df[df['movieId'].isin(top_movies)]
    
    print(f"Data density: {len(df)} interactions.")

    print("Grouping...")
    transactions = df.groupby('userId')['movieId'].apply(list).tolist()
    
    print("Encoding...")
    te = TransactionEncoder()
    te_ary = te.fit(transactions).transform(transactions)
    df_transformed = pd.DataFrame(te_ary, columns=te.columns_)
    
    print("Running FP-Growth...")
    frequent_itemsets = fpgrowth(df_transformed, min_support=0.1, use_colnames=True, max_len=2)
    
    if frequent_itemsets.empty:
        print("No patterns found.")
        return

    print("Generating Rules...")
    rules = association_rules(frequent_itemsets, metric="lift", min_threshold=1.5)
    
    # 2. TRANSLATE RULES TO TMDB IDs
    print("Translating rules to TMDB IDs...")
    lookup = {}
    rule_count = 0
    
    for _, row in rules.iterrows():
        input_ml_ids = list(row['antecedents'])
        output_ml_ids = list(row['consequents'])
        
        # Convert input (antecedent) to TMDB ID (taking first item for simple lookup)
        # In a real app we'd handle sets, but Key-Value lookup is faster for API
        for ml_id in input_ml_ids:
            tmdb_id = ml_to_tmdb.get(ml_id)
            if not tmdb_id:
                continue
            
            if tmdb_id not in lookup:
                lookup[tmdb_id] = []
                
            for out_ml in output_ml_ids:
                out_tmdb = ml_to_tmdb.get(out_ml)
                if out_tmdb and out_tmdb not in lookup[tmdb_id]:
                    lookup[tmdb_id].append(out_tmdb)
                    rule_count += 1

    if os.path.exists(MODEL_PATH):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = f"{MODEL_PATH}_{timestamp}.bak"
        os.rename(MODEL_PATH, archive_path)
        print(f"Archived previous model to {archive_path}")        
    joblib.dump(lookup, MODEL_PATH)
    print(f"Saved {rule_count} translated rules to {MODEL_PATH}")
    
    # Register Stats
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        avg_lift = rules['lift'].mean()
        metrics = {"rule_count": rule_count, "avg_lift": float(avg_lift), "rmse": 0.0}
        
        session.query(MLModel).filter(MLModel.model_type == "association").update({MLModel.is_active: False})
        entry = MLModel(
            name="MarketBasket_MovieLens_Real",
            version="2.0.0",
            model_type="association",
            file_path=MODEL_PATH,
            metrics=metrics,
            is_active=True
        )
        session.add(entry)
        session.commit()
        print("Registered to DB.")
    except Exception as e:
        session.rollback()
        print(e)
    finally:
        session.close()

if __name__ == "__main__":
    run_association_rules()