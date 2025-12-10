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
from datetime import datetime
from src.core.database import DATABASE_URL
from src.core.models import MLModel

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
        # 1. Fetch Data (Text + Genres)
        df = pd.read_sql("SELECT id, title, overview, genres FROM movies", engine)
        df = df.dropna(subset=['overview'])
        
        if len(df) < 50:
            print("Not enough data.")
            return

        # 2. Feature Engineering: TF-IDF on Overviews
        print("Vectorizing Text...")
        tfidf = TfidfVectorizer(stop_words='english', max_features=500)
        text_matrix = tfidf.fit_transform(df['overview']).toarray()

        # 3. Feature Engineering: One-Hot Encode Genres
        print("Encoding Genres...")
        import ast
        def get_genre_list(x):
            try:
                if isinstance(x, str):
                    return [g['name'] for g in ast.literal_eval(x)]
                return []
            except Exception:
                return []

        df['genre_list'] = df['genres'].apply(get_genre_list)
        
        # Get all unique genres
        all_genres = set([g for sublist in df['genre_list'] for g in sublist])
        # Filter to top 15 to avoid noise
        top_genres = list(all_genres)[:15] 
        
        genre_matrix = []
        for _, row in df.iterrows():
            row_genres = set(row['genre_list'])
            vec = [1 if g in row_genres else 0 for g in top_genres]
            genre_matrix.append(vec)
        
        genre_matrix = np.array(genre_matrix)

        # 4. Combine Features (Text + Genres)
        # We weight genres slightly higher (x2) because they are strong signals
        combined_matrix = np.hstack([text_matrix, genre_matrix * 2]).astype(np.float32)
        
        # 5. Dimensionality Reduction (PCA)
        # Reduce noise before clustering
        print("Reducing Dimensions (PCA)...")
        pca_reducer = PCA(n_components=50) # Keep 50 components
        reduced_matrix = pca_reducer.fit_transform(combined_matrix)
        
        if USING_GPU and hasattr(reduced_matrix, 'to_numpy'):
             reduced_matrix = reduced_matrix.to_numpy()

        # 6. Auto-Tune K (Find best K)
        print("Optimizing Clusters...")
        best_score = -1
        best_k = 8
        best_labels = None
        best_model = None
        
        # Test range of K
        k_range = [5, 8, 12, 15]
        
        for k in k_range:
            kmeans = KMeans(n_clusters=k, random_state=42)
            if USING_GPU:
                kmeans.fit(reduced_matrix)
                labels = kmeans.predict(reduced_matrix)
                if hasattr(labels, 'to_numpy'): 
                    labels = labels.to_numpy()
            else:
                labels = kmeans.fit_predict(reduced_matrix)
            
            # Calculate Silhouette Score (on subset for speed)
            sample_size = min(len(reduced_matrix), 2000)
            score = silhouette_score(reduced_matrix[:sample_size], labels[:sample_size])
            print(f"K={k}, Silhouette={score:.4f}")
            
            if score > best_score:
                best_score = score
                best_k = k
                best_labels = labels
                best_model = kmeans

        print(f"Winner: K={best_k} (Score: {best_score:.4f})")
        df['cluster'] = best_labels
        
        metrics = {"silhouette_score": float(best_score), "n_clusters": best_k}

        # 7. Visualization (2D PCA)
        print("Generating Graph...")
        pca_viz = PCA(n_components=2)
        viz_matrix = pca_viz.fit_transform(reduced_matrix)
        
        if USING_GPU and hasattr(viz_matrix, 'to_numpy'):
            viz_matrix = viz_matrix.to_numpy()
            
        df['x'] = viz_matrix[:, 0]
        df['y'] = viz_matrix[:, 1]
        
        plt.figure(figsize=(10, 8))
        sns.scatterplot(x='x', y='y', hue='cluster', data=df, palette='tab10', alpha=0.6, legend='full')
        plt.title(f"Hybrid Content Clusters (K={best_k}, Score={best_score:.2f})")
        plt.savefig(os.path.join(OUTPUT_DIR, "clustering_pca.png"))
        print("Graph saved.")
        
        # Save Model
        if os.path.exists(MODEL_PATH):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_path = f"{MODEL_PATH}_{timestamp}.bak"
            os.rename(MODEL_PATH, archive_path)
            print(f"Archived previous model to {archive_path}")  
        joblib.dump({'model': best_model, 'vectorizer': tfidf, 'pca': pca_reducer}, MODEL_PATH)
        
        # Register to DB
        try:
            session.query(MLModel).filter(MLModel.model_type == "clustering").update({MLModel.is_active: False})
            entry = MLModel(
                name=f"Hybrid_Cluster_AutoK{best_k}",
                version="2.0.0",
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