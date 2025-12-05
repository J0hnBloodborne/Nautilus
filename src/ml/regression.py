import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import matplotlib.pyplot as plt
import os
import joblib
import sys
import glob
import ctypes
from datetime import datetime
from src.core.database import DATABASE_URL
from src.core.models import MLModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

plt.switch_backend('Agg')

def force_gpu_linkage():
    print("Hunting for NVRTC library...")

    found = False
    for p in sys.path:
        pattern = os.path.join(p, "nvidia", "*", "lib", "libnvrtc.so.12")
        matches = glob.glob(pattern)
        
        if matches:
            lib_path = matches[0]
            lib_dir = os.path.dirname(lib_path)
            print(f"Found: {lib_path}")
            current_ld = os.environ.get('LD_LIBRARY_PATH', '')
            if lib_dir not in current_ld:
                os.environ['LD_LIBRARY_PATH'] = f"{lib_dir}:{current_ld}"
                print(f"Injected {lib_dir} into LD_LIBRARY_PATH")
            try:
                ctypes.CDLL(lib_path)
                print("Pre-loaded library into memory.")
            except Exception as e:
                print(f"Pre-load failed: {e}")
            
            found = True
            break
    
    if not found:
        print("Could not locate libnvrtc.so.12. GPU will likely crash.")

force_gpu_linkage()
# Path setup
sys.path.append(os.getcwd())

# Hybrid Import
try:
    from cuml.ensemble import RandomForestRegressor
    print("GPU ACCELERATION: ONLINE")
    USING_GPU = True
except ImportError:
    from sklearn.ensemble import RandomForestRegressor
    print("GPU NOT FOUND: USING CPU")
    USING_GPU = False

RAW_DATA_PATH = "data/raw/archive/movies_metadata.csv"
OUTPUT_DIR = "reports/figures"
MODEL_PATH = "src/models/revenue_regressor.pkl"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs("src/models", exist_ok=True)

def run_regression():
    print("Loading Metadata...")
    if not os.path.exists(RAW_DATA_PATH):
        print("File not found.")
        return

    try:
        df = pd.read_csv(RAW_DATA_PATH, low_memory=False)
        df = df[['budget', 'runtime', 'revenue', 'vote_average']].dropna()
        df['budget'] = pd.to_numeric(df['budget'], errors='coerce')
        df['revenue'] = pd.to_numeric(df['revenue'], errors='coerce')
        df = df.dropna()
        df = df[df['budget'] > 1000] # Filter junk
        
        if df.empty:
            print("No valid data.")
            return

        X = df[['budget', 'runtime', 'vote_average']].astype(np.float32)
        y = df['revenue'].astype(np.float32)
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        print("Training Random Forest...")
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        
        # Predictions
        predictions = model.predict(X_test)
        
        # METRICS CALCULATION
        rmse = np.sqrt(mean_squared_error(y_test, predictions))
        mae = mean_absolute_error(y_test, predictions)
        r2 = r2_score(y_test, predictions)
        
        metrics = {
            "rmse": float(rmse),
            "mae": float(mae),
            "r2": float(r2)
        }
        print(f"Metrics: {metrics}")
        
        # Save Model
        if os.path.exists(MODEL_PATH):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_path = f"{MODEL_PATH}_{timestamp}.bak"
            os.rename(MODEL_PATH, archive_path)
            print(f"Archived previous model to {archive_path}")  
        joblib.dump(model, MODEL_PATH)
        
        # Register to DB
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Deactivate old versions
        try:
            session.query(MLModel).filter(MLModel.model_type == "regression").update({MLModel.is_active: False})
            
            entry = MLModel(
                name="Revenue_Forest_v1",
                version="1.0.0",
                model_type="regression",
                file_path=MODEL_PATH,
                metrics=metrics,
                is_active=True
            )
            session.add(entry)
            session.commit()
            print("Model registered to Database.")
        except Exception as e:
            print(f"DB Error: {e}")
            session.rollback()
        finally:
            session.close()

        # Plot Importance
        if hasattr(model, 'feature_importances_'):
            importances = model.feature_importances_
            if USING_GPU and not isinstance(importances, np.ndarray):
                importances = importances.to_numpy()
                
            plt.figure(figsize=(8, 5))
            plt.bar(X.columns, importances)
            plt.title("Feature Importance (Revenue)")
            plt.savefig(os.path.join(OUTPUT_DIR, "regression_features.png"))
            
    except Exception as e:
        print(f"Regression Failed: {e}")

if __name__ == "__main__":
    run_regression()