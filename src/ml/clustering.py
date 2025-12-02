import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score
import matplotlib.pyplot as plt
import seaborn as sns
import os
import sys
import joblib
import glob
import ctypes
from src.database import DATABASE_URL
from src.models import MLModel

plt.switch_backend('Agg')

# --- GPU PRELOADER ---
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

# Hybrid Import
try:
    from cuml.cluster import KMeans
    from cuml.decomposition import PCA
    print("GPU ACCELERATION: ONLINE")
    USING_GPU = True
except ImportError:
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    print("GPU NOT FOUND: USING CPU")
    USING_GPU = False

sys.path.append(os.getcwd())


OUTPUT_DIR = "reports/figures"
MODEL_PATH = "src/models/clustering_kmeans.pkl"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs("src/models", exist_ok=True)

def run_clustering():
    print("Fetching movie plots...")
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        df = pd.read_sql("SELECT id, title, overview FROM movies", engine)
        df = df.dropna(subset=['overview'])
        
        if len(df) < 50:
            print("Not enough data.")
            return

        # CPU Vectorization (Reliable)
        tfidf = TfidfVectorizer(stop_words='english', max_features=1000)
        matrix = tfidf.fit_transform(df['overview'])
        dense_matrix = matrix.toarray().astype(np.float32)
        
        print("Running K-Means...")
        # Increase clusters to find more niche genres
        kmeans = KMeans(n_clusters=8, random_state=42)
        
        if USING_GPU:
            kmeans.fit(dense_matrix)
            clusters = kmeans.predict(dense_matrix)
            # Convert to numpy for plotting
            try: 
                clusters = clusters.to_numpy()
            except Exception:
                pass
        else:
            clusters = kmeans.fit_predict(dense_matrix)
            
        df['cluster'] = clusters
        
        # METRICS (Silhouette Score - CPU only)
        # We use a subset to calculate score fast
        sample_size = min(len(dense_matrix), 5000)
        score = silhouette_score(dense_matrix[:sample_size], clusters[:sample_size])
        metrics = {"silhouette_score": float(score), "n_clusters": 8}
        print(f"Metrics: {metrics}")

        # PCA for Visualization
        print("Running PCA...")
        pca = PCA(n_components=2)
        reduced = pca.fit_transform(dense_matrix)
        
        if USING_GPU:
            try: 
                reduced = reduced.to_numpy()
            except Exception:
                pass
            
        df['x'] = reduced[:, 0]
        df['y'] = reduced[:, 1]
        
        # Plot
        plt.figure(figsize=(10, 8))
        sns.scatterplot(x='x', y='y', hue='cluster', data=df, palette='viridis', alpha=0.7, legend=False)
        plt.title(f"Movie Content Clusters (Silhouette: {score:.2f})")
        plt.savefig(os.path.join(OUTPUT_DIR, "clustering_pca.png"))
        print("Graph saved.")
        
        # Save Model
        joblib.dump({'model': kmeans, 'vectorizer': tfidf}, MODEL_PATH)
        
        # Register to DB
        try:
            session.query(MLModel).filter(MLModel.model_type == "clustering").update({MLModel.is_active: False})
            entry = MLModel(
                name="Genre_Discovery_KMeans",
                version="1.0.0",
                model_type="clustering",
                file_path=MODEL_PATH,
                metrics=metrics,
                is_active=True
            )
            session.add(entry)
            session.commit()
            print("Model registered to Database.")
        except Exception as e:
            session.rollback()
            print(f"DB Error: {e}")
        
    except Exception as e:
        print(f"Clustering Failed: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    run_clustering()