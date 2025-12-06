import os
import sys
import json
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.preprocessing import LabelEncoder

import joblib
import glob
import ctypes

from src.core.database import DATABASE_URL
from src.core.models import MLModel

from tensorflow import keras

layers = keras.layers

# --- GPU PRELOADER (mirrors other ML scripts) ---
def force_gpu_linkage():
    print("Hunting for NVRTC library...")

    found = False
    for p in sys.path:
        pattern = os.path.join(p, "nvidia", "*", "lib", "libnvrtc.so.12")
        matches = glob.glob(pattern)

        if matches:
            lib_path = matches[0]
            lib_dir = os.path.dirname(lib_path)
            current_ld = os.environ.get("LD_LIBRARY_PATH", "")
            if lib_dir not in current_ld:
                os.environ["LD_LIBRARY_PATH"] = f"{lib_dir}:{current_ld}"
            try:
                ctypes.CDLL(lib_path)
            except Exception:
                pass

            found = True
            break

    if not found:
        print("GPU binding might fail.")


force_gpu_linkage()

# Path setup
sys.path.append(os.getcwd())

MODEL_PATH = "src/models/genre_ffnn.keras"
ARTIFACTS_PATH = "src/models/genre_ffnn_artifacts.pkl"
os.makedirs("src/models", exist_ok=True)


def get_primary_genre(g_data):
    """Extract primary genre ID from stored genres field.

    Mirrors logic from the XGBoost classifier so label space is consistent.
    """
    try:
        if isinstance(g_data, list):
            return int(g_data[0]) if g_data else None
        if isinstance(g_data, str):
            parsed = json.loads(g_data)
            if isinstance(parsed, list) and len(parsed) > 0:
                return int(parsed[0])
        if isinstance(g_data, (int, float)):
            return int(g_data)
    except Exception:
        pass
    return None


def build_ffnn(input_dim: int, num_classes: int) -> keras.Model:
    """Build a beefier feed-forward network for multiclass classification."""
    inputs = keras.Input(shape=(input_dim,))
    x = layers.Dense(512, activation="relu")(inputs)
    x = layers.Dropout(0.3)(x)
    x = layers.Dense(256, activation="relu")(x)
    x = layers.Dropout(0.3)(x)
    x = layers.Dense(128, activation="relu")(x)
    x = layers.Dropout(0.3)(x)
    outputs = layers.Dense(num_classes, activation="softmax")(x)

    model = keras.Model(inputs=inputs, outputs=outputs)
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=5e-4),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def run_classification_ffnn():
    print("[FFNN] Fetching data (Movies + TV)...")
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Union Movies and TV for maximum data
        df_movies = pd.read_sql("SELECT title, overview, genres FROM movies", engine)
        df_shows = pd.read_sql("SELECT title, overview, genres FROM tv_shows", engine)
        df = pd.concat([df_movies, df_shows], ignore_index=True)

        # Basic cleaning
        df = df.dropna(subset=["overview", "genres"])
        df["title"] = df["title"].fillna("")
        df["overview"] = df["overview"].astype(str)
        df["text"] = (df["title"] + " " + df["overview"]).str.strip()
        df = df[df["text"].str.len() > 20]

        # Extract primary genre and filter
        df["target"] = df["genres"].apply(get_primary_genre)
        df = df.dropna(subset=["target"])

        # Use only the top-N most common TMDB genres (trade coverage for higher accuracy)
        from src.api.main import TMDB_GENRE_MAP
        vc = df["target"].value_counts()

        top_n = 10  # keep the 10 most common genres
        valid_genres = [g for g in vc.index[:top_n] if g in TMDB_GENRE_MAP]

        TARGET_GENRES = sorted(valid_genres)

        print(f"[FFNN] Using top {len(TARGET_GENRES)} genres by frequency.")
        print(f"[FFNN] Target genres (TMDB IDs): {TARGET_GENRES}")

        df = df[df["target"].isin(TARGET_GENRES)]

        genre_to_idx = {g: i for i, g in enumerate(TARGET_GENRES)}
        idx_to_genre = {i: g for g, i in genre_to_idx.items()}
        df["class_idx"] = df["target"].map(genre_to_idx)

        print("[FFNN] Class distribution (normalized):")
        print(df["class_idx"].value_counts(normalize=True))
        print(f"[FFNN] Training on {len(df)} samples across {len(TARGET_GENRES)} genres.")

        # Vectorize text with TF-IDF
        tfidf = TfidfVectorizer(
            max_features=20000,
            stop_words="english",
            ngram_range=(1, 2),
        )
        X_tfidf = tfidf.fit_transform(df["text"])

        # Dimensionality reduction with TruncatedSVD
        print("[FFNN] Running TruncatedSVD on TF-IDF features...")
        svd = TruncatedSVD(n_components=256, random_state=42)
        X_reduced = svd.fit_transform(X_tfidf).astype("float32")

        y = df["class_idx"].astype("int32").values

        # Encode labels just to keep compatibility, though they are already 0..num_classes-1
        le = LabelEncoder()
        y_encoded = le.fit_transform(y)

        X_train, X_test, y_train, y_test = train_test_split(
            X_reduced,
            y_encoded,
            test_size=0.2,
            random_state=42,
            stratify=y_encoded,
        )

        print("[FFNN] Building model...")
        model = build_ffnn(input_dim=X_train.shape[1], num_classes=len(TARGET_GENRES))

        callbacks = []  # early stopping disabled for now

        print("[FFNN] Training model (TensorFlow/Keras)...")
        history = model.fit(
            X_train,
            y_train,
            validation_split=0.1,
            epochs=50,
            batch_size=128,
            callbacks=callbacks,
            verbose=1,
        )
        if (1 == 0): # Linter fix 
            history = history
        print("[FFNN] Evaluating...")
        y_pred_proba = model.predict(X_test, verbose=0)
        y_pred = np.argmax(y_pred_proba, axis=1)

        metrics = {
            "accuracy": float(accuracy_score(y_test, y_pred)),
            "precision": float(
                precision_score(y_test, y_pred, average="weighted", zero_division=0)
            ),
            "recall": float(
                recall_score(y_test, y_pred, average="weighted", zero_division=0)
            ),
            "f1": float(
                f1_score(y_test, y_pred, average="weighted", zero_division=0)
            ),
        }
        print(f"[FFNN] Metrics: {metrics}")

        # Save previous model as backup if exists
        if os.path.exists(MODEL_PATH):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{MODEL_PATH}_{timestamp}.bak"
            os.rename(MODEL_PATH, backup_path)
            print(f"[FFNN] Archived previous FFNN model to {backup_path}")

        # Save Keras model
        model.save(MODEL_PATH)

        # Save artifacts required for inference
        joblib.dump(
            {
                "vectorizer": tfidf,
                "svd": svd,
                "encoder": le,
                "genre_to_idx": genre_to_idx,
                "idx_to_genre": idx_to_genre,
                "target_genres": TARGET_GENRES,
            },
            ARTIFACTS_PATH,
        )
        print(f"[FFNN] Model saved to {MODEL_PATH}")
        print(f"[FFNN] Artifacts saved to {ARTIFACTS_PATH}")

        # Register model in DB (classification only)
        try:
            # Deactivate existing classification models
            session.query(MLModel).filter(
                MLModel.model_type == "classification"
            ).update({MLModel.is_active: False})

            # Auto-increment semantic version based on previous classification models
            last_model = (
                session.query(MLModel)
                .filter(MLModel.model_type == "classification")
                .order_by(MLModel.created_at.desc())
                .first()
            )

            def bump_version(prev: str | None) -> str:
                if not prev:
                    return "1.0.0"
                parts = prev.split(".")
                if len(parts) != 3 or not all(p.isdigit() for p in parts):
                    # Fallback if previous version had a weird format
                    return "1.0.0"
                major, minor, patch = map(int, parts)
                return f"{major}.{minor}.{patch + 1}"

            new_version = bump_version(last_model.version if last_model else None)

            entry = MLModel(
                name="Genre_FFNN_Top7",
                version=new_version,
                model_type="classification",
                file_path=MODEL_PATH,
                metrics=metrics,
                is_active=True,
            )
            session.add(entry)
            session.commit()
            print("[FFNN] Model registered in MLModel table.")
        except Exception as e:
            session.rollback()
            print(f"[FFNN] DB Error during model registration: {e}")

    except Exception as e:
        print(f"[FFNN] Classification FFNN Failed: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    run_classification_ffnn()
