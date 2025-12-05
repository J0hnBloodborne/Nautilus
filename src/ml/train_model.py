import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sklearn.decomposition import TruncatedSVD
from sklearn.metrics import mean_squared_error
import joblib
import os
import sys
import glob
import ctypes
from datetime import datetime
from dotenv import load_dotenv
from src.core.models import MLModel
from src.core.database import DATABASE_URL 

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

# Ensure import path
sys.path.append(os.getcwd())


# Hybrid Import
try:
    from cuml.decomposition import TruncatedSVD
    print("GPU ACCELERATION: ONLINE (cuML SVD)")
    USING_GPU = True
except ImportError:
    from sklearn.decomposition import TruncatedSVD
    print("GPU NOT FOUND: Using CPU SVD")
    USING_GPU = False

load_dotenv()
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()

os.makedirs("src/models", exist_ok=True)
MODEL_PATH = "src/models/recommender_v1.pkl"

def fetch_data():
    print("Fetching interaction data...")
    # Read only valid ratings
    query = "SELECT user_id, movie_id, rating_value FROM interactions WHERE interaction_type = 'rating'"
    try:
        df = pd.read_sql(query, engine)
        print(f"Loaded {len(df)} ratings.")
        return df
    except Exception:
        return pd.DataFrame()

def train_svd(df):
    if df.empty:
        return None, None, 0.0

    # CRITICAL FIX: Remove duplicates before pivoting
    # If a user rated a movie twice, keep the last one
    df = df.drop_duplicates(subset=['user_id', 'movie_id'], keep='last')

    # Pivot
    matrix = df.pivot(index='user_id', columns='movie_id', values='rating_value').fillna(0)
    
    # GPU loves float32
    data = matrix.values.astype(np.float32)
    
    print("Training SVD Matrix Factorization...")
    svd = TruncatedSVD(n_components=50, random_state=42)
    
    # Fit
    matrix_reduced = svd.fit_transform(data)
    matrix_reconstructed = svd.inverse_transform(matrix_reduced)
    
    # Evaluate (RMSE)
    if USING_GPU:
        try:
            matrix_reconstructed = matrix_reconstructed.to_numpy()
        except Exception:
            pass
        
    original_flat = matrix.values.flatten()
    pred_flat = matrix_reconstructed.flatten()
    mask = original_flat > 0
    rmse = np.sqrt(mean_squared_error(original_flat[mask], pred_flat[mask]))
    
    print(f"Model RMSE: {rmse:.4f}")
    
    # Save Artifact
    artifact = {
        "model": svd,
        "movie_ids": matrix.columns,
        "user_ids": matrix.index,
        "matrix_reduced": matrix_reduced
    }
    if os.path.exists(MODEL_PATH):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = f"{MODEL_PATH}_{timestamp}.bak"
        os.rename(MODEL_PATH, archive_path)
        print(f"Archived previous model to {archive_path}")  
    joblib.dump(artifact, MODEL_PATH)
    print(f"Saved to {MODEL_PATH}")
    
    return svd, matrix.columns, rmse

def register_model(rmse):
    print("Registering Model...")
    try:
        # Deactivate old models
        session.query(MLModel).filter(MLModel.model_type == "collaborative_filtering").update({MLModel.is_active: False})
        
        metrics = {"rmse": float(rmse)}
        
        model_entry = MLModel(
            name="Nautilus_SVD",
            version="1.0.0",
            model_type="collaborative_filtering",
            file_path=MODEL_PATH,
            metrics=metrics,
            is_active=True
        )
        session.add(model_entry)
        session.commit()
        print(f"Model registered (RMSE: {rmse:.4f}).")
    except Exception as e:
        session.rollback()
        print(e)
    finally:
        session.close()

if __name__ == "__main__":
    df = fetch_data()
    if len(df) > 10:
        model, cols, rmse = train_svd(df)
        if model:
            register_model(rmse)
    else:
        print("Not enough data! Run 'python src/seed_data.py' first.")