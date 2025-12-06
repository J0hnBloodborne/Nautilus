import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, classification_report
from sklearn.preprocessing import LabelEncoder
from sklearn.utils.class_weight import compute_sample_weight
import xgboost as xgb
import os
import sys
import joblib
import json
from datetime import datetime

# Path setup
sys.path.append(os.getcwd())
from src.core.database import DATABASE_URL
from src.core.models import MLModel

MODEL_PATH = "src/models/genre_classifier.pkl"
os.makedirs("src/models", exist_ok=True)

# GPU Check
try:
    import pynvml
    pynvml.nvmlInit()
    print("⚡ GPU DETECTED: Enabling XGBoost CUDA acceleration.")
    DEVICE = "cuda"
except Exception:
    print("GPU NOT FOUND: Using CPU.")
    DEVICE = "cpu"

def run_classification():
    print("Fetching data (Movies + TV)...")
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Union Movies and TV for maximum data
        df_movies = pd.read_sql("SELECT overview, genres FROM movies", engine)
        df_shows = pd.read_sql("SELECT overview, genres FROM tv_shows", engine)
        df = pd.concat([df_movies, df_shows], ignore_index=True)
        df = df.dropna(subset=['overview', 'genres'])

        # Basic cleaning: strip and drop very short overviews (likely junk)
        df['overview'] = (
            df['overview']
            .astype(str)
            .str.strip()
            .str.lower()
        )
        df = df[df['overview'].str.len() > 20]
        
        # Extract Primary Genre ID
        def get_primary_genre(g_data):
            try:
                if isinstance(g_data, list):
                    return int(g_data[0])
                if isinstance(g_data, str):
                    parsed = json.loads(g_data)
                    if isinstance(parsed, list) and len(parsed) > 0:
                        return int(parsed[0])
                if isinstance(g_data, (int, float)):
                    return int(g_data)
            except Exception:
                pass
            return None

        df['target'] = df['genres'].apply(get_primary_genre)
        df = df.dropna(subset=['target'])

        # Filter for selected genres only (to make it easier for the model)
        # 28=Action, 12=Adventure, 16=Animation, 35=Comedy, 18=Drama, 878=Sci-Fi, 27=Horror
        TARGET_GENRES = [28, 12, 16, 35, 18, 878, 27]
        df = df[df['target'].isin(TARGET_GENRES)]

        # Explicit mapping: genre ID -> class index 0..N-1
        genre_to_idx = {g: i for i, g in enumerate(TARGET_GENRES)}
        idx_to_genre = {i: g for g, i in genre_to_idx.items()}
        df['class_idx'] = df['target'].map(genre_to_idx)

        print("Class distribution (normalized):")
        print(df['class_idx'].value_counts(normalize=True))
        print(f"Training on {len(df)} samples across {len(TARGET_GENRES)} genres.")

        # Vectorize (TF-IDF) - stronger text features
        tfidf = TfidfVectorizer(max_features=50000, stop_words='english', ngram_range=(1, 2))
        X_vec = tfidf.fit_transform(df['overview'])
        y = df['class_idx'].astype(int).values

        # Encode Labels (0..num_class-1) for compatibility
        le = LabelEncoder()
        y_encoded = le.fit_transform(y)

        # Split
        X_train, X_test, y_train, y_test = train_test_split(
            X_vec, y_encoded, test_size=0.2, random_state=42, stratify=y_encoded
        )

        # Handle Imbalance
        sample_weights = compute_sample_weight(
            class_weight='balanced',
            y=y_train
        )

        print(f"Training XGBoost ({DEVICE})...")
        model = xgb.XGBClassifier(
            n_estimators=1200,       # was 800
            max_depth=7,            # was 8
            learning_rate=0.03,     # slower learning
            objective='multi:softmax',
            num_class=len(TARGET_GENRES),
            tree_method="hist",
            device=DEVICE,
            eval_metric='mlogloss',
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=2.0,         # more L2
            reg_alpha=0.5,          # some L1
        )

        model.fit(X_train, y_train, sample_weight=sample_weights)

        preds = model.predict(X_test)
        print(classification_report(y_test, preds))

        # Metrics
        metrics = {
            "accuracy": float(accuracy_score(y_test, preds)),
            "precision": float(precision_score(y_test, preds, average='weighted', zero_division=0)),
            "recall": float(recall_score(y_test, preds, average='weighted', zero_division=0)),
            "f1": float(f1_score(y_test, preds, average='weighted', zero_division=0))
        }
        print(f"Metrics: {metrics}")

        # Simple overfit check
        train_preds = model.predict(X_train)
        train_acc = accuracy_score(y_train, train_preds)
        print(f"Train accuracy: {train_acc}")

        # Logistic Regression baseline for comparison
        try:
            from sklearn.linear_model import LogisticRegression
            logreg = LogisticRegression(
                max_iter=2000,
                n_jobs=-1,
                class_weight='balanced',
                C=2.0,
                multi_class='multinomial'
            )
            logreg.fit(X_train, y_train)
            lr_preds = logreg.predict(X_test)
            lr_acc = accuracy_score(y_test, lr_preds)
            print(f"LogReg accuracy: {lr_acc}")
        except Exception as e:
            print(f"LogReg baseline failed: {e}")

        # Archive & Save
        if os.path.exists(MODEL_PATH):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            os.rename(MODEL_PATH, f"{MODEL_PATH}_{timestamp}.bak")
            print(f"Archived previous model to {MODEL_PATH}_{timestamp}.bak")

        # Save model and supporting artifacts
        joblib.dump(
            {
                'model': model,
                'vectorizer': tfidf,
                'encoder': le,
                'genre_to_idx': genre_to_idx,
                'idx_to_genre': idx_to_genre,
                'target_genres': TARGET_GENRES,
            },
            MODEL_PATH
        )
        print(f"Model saved to {MODEL_PATH}")

        # Register to DB
        try:
            session.query(MLModel).filter(MLModel.model_type == "classification").update({MLModel.is_active: False})
            entry = MLModel(
                name="Genre_XGBoost_Top5",
                version="3.0.0",
                model_type="classification",
                file_path=MODEL_PATH,
                metrics=metrics,
                is_active=True
            )
            session.add(entry)
            session.commit()
            print("Model registered.")
        except Exception as e:
            session.rollback()
            print(f"DB Error: {e}")
            
    except Exception as e:
        print(f"Classification Failed: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    run_classification()