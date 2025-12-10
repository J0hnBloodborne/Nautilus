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
from sklearn.metrics import f1_score, precision_score, recall_score

import joblib
import glob
import ctypes

from src.core.database import DATABASE_URL
from src.core.models import MLModel

from tensorflow import keras

regularizers = keras.regularizers
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

MODEL_PATH = "src/models/genre_multilabel_ffnn.keras"
ARTIFACTS_PATH = "src/models/genre_multilabel_ffnn_artifacts.pkl"
os.makedirs("src/models", exist_ok=True)


def parse_genre_ids(raw):
    """Parse stored genres field into a list of TMDB genre IDs."""
    try:
        if isinstance(raw, list):
            return [int(g) for g in raw]
        if isinstance(raw, str):
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [int(g) for g in parsed]
        if isinstance(raw, (int, float)):
            return [int(raw)]
    except Exception:
        pass
    return []


def build_ffnn(input_dim: int, num_classes: int) -> keras.Model:
    """FFNN for multi-label genre classification."""
    inputs = keras.Input(shape=(input_dim,))

    x = layers.Dense(
        512, activation="relu", kernel_regularizer=regularizers.l2(1e-4)
    )(inputs)
    x = layers.Dropout(0.3)(x)
    x = layers.Dense(
        256, activation="relu", kernel_regularizer=regularizers.l2(1e-4)
    )(x)
    x = layers.Dropout(0.3)(x)
    x = layers.Dense(
        128, activation="relu", kernel_regularizer=regularizers.l2(1e-4)
    )(x)
    x = layers.Dropout(0.3)(x)

    # Multi-label: independent probability per genre
    outputs = layers.Dense(num_classes, activation="sigmoid")(x)

    model = keras.Model(inputs=inputs, outputs=outputs)
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=5e-4),
        loss="binary_crossentropy",
        metrics=["accuracy"],
    )
    return model


def run_classification_multilabel_ffnn(smoke_test=False):
    print("[ML-FFNN] Fetching data (Movies + TV)...")
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Union Movies and TV for maximum data
        limit_clause = "LIMIT 100" if smoke_test else ""
        df_movies = pd.read_sql(f"SELECT title, overview, genres FROM movies {limit_clause}", engine)
        df_shows = pd.read_sql(f"SELECT title, overview, genres FROM tv_shows {limit_clause}", engine)
        df = pd.concat([df_movies, df_shows], ignore_index=True)

        # Basic cleaning
        df = df.dropna(subset=["overview", "genres"])
        df["title"] = df["title"].fillna("")
        df["overview"] = df["overview"].astype(str)
        df["text"] = (df["title"] + " " + df["overview"]).str.strip()
        df = df[df["text"].str.len() > 20]

        # Parse full genre lists
        df["genre_ids_full"] = df["genres"].apply(parse_genre_ids)

        # Filter out rows with no valid genres
        df = df[df["genre_ids_full"].map(len) > 0]

        # Choose top-N TMDB genres by frequency
        from src.api.main import TMDB_GENRE_MAP

        all_ids = [g for ids in df["genre_ids_full"] for g in ids]
        vc = pd.Series(all_ids).value_counts()

        top_n = 10
        valid_genres = [g for g in vc.index[:top_n] if g in TMDB_GENRE_MAP]
        TARGET_GENRES = sorted(valid_genres)

        print(f"[ML-FFNN] Using top {len(TARGET_GENRES)} genres by frequency.")
        print(f"[ML-FFNN] Target genres (TMDB IDs): {TARGET_GENRES}")

        genre_to_idx = {g: i for i, g in enumerate(TARGET_GENRES)}
        idx_to_genre = {i: g for g, i in genre_to_idx.items()}

        # Build multi-hot vectors
        num_classes = len(TARGET_GENRES)

        def make_multi_hot(ids):
            vec = np.zeros(num_classes, dtype="float32")
            for g in ids:
                idx = genre_to_idx.get(g)
                if idx is not None:
                    vec[idx] = 1.0
            return vec

        df["multi_hot"] = df["genre_ids_full"].apply(make_multi_hot)

        # Filter to rows that hit at least one of the target genres
        df = df[df["multi_hot"].map(lambda v: v.sum() > 0)]

        Y = np.stack(df["multi_hot"].values)

        print("[ML-FFNN] Label distribution (per-genre positive rate):")
        print(Y.mean(axis=0))
        print(f"[ML-FFNN] Training on {len(df)} samples across {num_classes} genres.")

        # Vectorize text with TF-IDF
        tfidf = TfidfVectorizer(
            max_features=20000,
            stop_words="english",
            ngram_range=(1, 2),
        )
        X_tfidf = tfidf.fit_transform(df["text"])

        # Dimensionality reduction with TruncatedSVD
        print("[ML-FFNN] Running TruncatedSVD on TF-IDF features...")
        svd = TruncatedSVD(n_components=256, random_state=42)
        X_reduced = svd.fit_transform(X_tfidf).astype("float32")

        X_train, X_test, Y_train, Y_test = train_test_split(
            X_reduced,
            Y,
            test_size=0.2,
            random_state=42,
        )

        print("[ML-FFNN] Building model...")
        model = build_ffnn(input_dim=X_train.shape[1], num_classes=num_classes)

        epochs = 1 if smoke_test else 80

        callbacks = [
            keras.callbacks.EarlyStopping(
                monitor="val_loss", patience=8, restore_best_weights=True
            )
        ]

        print("[ML-FFNN] Training model (TensorFlow/Keras, multi-label)...")
        history = model.fit(
            X_train,
            Y_train,
            validation_split=0.1,
            epochs=epochs,
            batch_size=128,
            callbacks=callbacks,
            verbose=1,
        )
        if (1 == 0):
            history = history

        print("[ML-FFNN] Evaluating...")
        Y_pred_proba = model.predict(X_test, verbose=0)

        # Threshold-based predictions
        threshold = 0.5
        Y_pred_bin = (Y_pred_proba >= threshold).astype("int32")

        metrics = {
            "f1_micro": float(
                f1_score(Y_test, Y_pred_bin, average="micro", zero_division=0)
            ),
            "f1_macro": float(
                f1_score(Y_test, Y_pred_bin, average="macro", zero_division=0)
            ),
            "precision_micro": float(
                precision_score(
                    Y_test, Y_pred_bin, average="micro", zero_division=0
                )
            ),
            "recall_micro": float(
                recall_score(
                    Y_test, Y_pred_bin, average="micro", zero_division=0
                )
            ),
        }
        print(f"[ML-FFNN] Multi-label metrics: {metrics}")

        # Optional: Top-k multi-label accuracy (hit@k)
        k = 3
        topk_idx = np.argsort(-Y_pred_proba, axis=1)[:, :k]

        def hit_at_k(true_row, k_idx_row):
            true_labels = np.where(true_row == 1)[0]
            return any(lbl in k_idx_row for lbl in true_labels)

        topk_hits = [hit_at_k(Y_test[i], topk_idx[i]) for i in range(len(Y_test))]
        topk_acc = float(np.mean(topk_hits))
        print(f"[ML-FFNN] Top-{k} hit accuracy: {topk_acc:.3f}")

        if smoke_test:
            print("[Smoke Test] Skipping model save.")
            return

        # Save previous model as backup if exists
        if os.path.exists(MODEL_PATH):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{MODEL_PATH}_{timestamp}.bak"
            os.rename(MODEL_PATH, backup_path)
            print(f"[ML-FFNN] Archived previous multi-label FFNN model to {backup_path}")

        # Save Keras model
        model.save(MODEL_PATH)

        # Save artifacts required for inference
        joblib.dump(
            {
                "vectorizer": tfidf,
                "svd": svd,
                "genre_to_idx": genre_to_idx,
                "idx_to_genre": idx_to_genre,
                "target_genres": TARGET_GENRES,
            },
            ARTIFACTS_PATH,
        )
        print(f"[ML-FFNN] Model saved to {MODEL_PATH}")
        print(f"[ML-FFNN] Artifacts saved to {ARTIFACTS_PATH}")

        # Register model in DB (classification, multi-label)
        try:
            session.query(MLModel).filter(
                MLModel.model_type == "classification_multilabel"
            ).update({MLModel.is_active: False})

            last_model = (
                session.query(MLModel)
                .filter(MLModel.model_type == "classification_multilabel")
                .order_by(MLModel.created_at.desc())
                .first()
            )

            def bump_version(prev: str | None) -> str:
                if not prev:
                    return "1.0.0"
                parts = prev.split(".")
                if len(parts) != 3 or not all(p.isdigit() for p in parts):
                    return "1.0.0"
                major, minor, patch = map(int, parts)
                return f"{major}.{minor}.{patch + 1}"

            new_version = bump_version(last_model.version if last_model else None)

            entry = MLModel(
                name="Genre_MultiLabel_FFNN_TopN",
                version=new_version,
                model_type="classification_multilabel",
                file_path=MODEL_PATH,
                metrics=metrics,
                is_active=True,
            )
            session.add(entry)
            session.commit()
            print("[ML-FFNN] Model registered in MLModel table.")
        except Exception as e:
            session.rollback()
            print(f"[ML-FFNN] DB Error during model registration: {e}")

    except Exception as e:
        print(f"[ML-FFNN] Multi-label Classification FFNN Failed: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    run_classification_multilabel_ffnn()
