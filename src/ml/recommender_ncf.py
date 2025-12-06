import os
import sys
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Ensure project root on path
sys.path.append(os.getcwd())

from src.core.database import DATABASE_URL  # type: ignore
from src.core.models import MLModel  # type: ignore

from tensorflow import keras


MODEL_PATH = "src/models/recommender_ncf.keras"
ARTIFACTS_PATH = "src/models/recommender_ncf_artifacts.pkl"
MIN_INTERACTIONS = 50
GLOBAL_USER_ID = 1
NEGATIVE_RATIO = 4


def fetch_interactions(engine):
    """Load user-movie interactions; fall back will synthesize later if too small."""
    query = """
        SELECT user_id, movie_id, rating_value, interaction_type
        FROM interactions
        WHERE movie_id IS NOT NULL
    """
    try:
        df = pd.read_sql(query, engine)
        print(f"Loaded {len(df)} interactions from DB.")
        return df
    except Exception as e:
        print(f"Error loading interactions: {e}")
        return pd.DataFrame(columns=["user_id", "movie_id", "rating_value", "interaction_type"])


def synthesize_global_interactions(engine):
    """Create synthetic positives/negatives for a global pseudo-user based on popularity."""
    q = """
        SELECT id AS movie_id, popularity_score
        FROM movies
        WHERE popularity_score IS NOT NULL
    """
    try:
        movies = pd.read_sql(q, engine)
    except Exception as e:
        print(f"Error loading movies for synthetic interactions: {e}")
        return pd.DataFrame(columns=["user_id", "movie_id", "label"])

    if movies.empty:
        print("No movies available to synthesize interactions.")
        return pd.DataFrame(columns=["user_id", "movie_id", "label"])

    movies = movies.sort_values("popularity_score", ascending=False)
    n_pos = max(10, int(0.2 * len(movies)))
    pos = movies.head(n_pos)
    neg = movies.tail(min(len(movies) - n_pos, n_pos * NEGATIVE_RATIO))

    pos_df = pd.DataFrame({
        "user_id": GLOBAL_USER_ID,
        "movie_id": pos["movie_id"],
        "label": 1.0,
    })
    neg_df = pd.DataFrame({
        "user_id": GLOBAL_USER_ID,
        "movie_id": neg["movie_id"],
        "label": 0.0,
    })
    df = pd.concat([pos_df, neg_df], ignore_index=True)
    print(f"Synthesized {len(df)} interactions for global user.")
    return df


def build_dataset(engine):
    """Return user_ids, movie_ids, labels arrays plus id-index mappings and metadata."""
    df = fetch_interactions(engine)

    if len(df) < MIN_INTERACTIONS:
        print("Not enough real interactions; using synthetic global interactions.")
        df2 = synthesize_global_interactions(engine)
        if df2.empty:
            return None
        df = df2
    else:
        # Basic implicit feedback: rating >= 3 is positive, others negative via sampling
        df = df.dropna(subset=["user_id", "movie_id"])  # safety
        df["label"] = (df["rating_value"] >= 3.0).astype(float)
        df = df[[("label" in df) and (df["label"] == 1.0)].pop()]

    # ID mappings
    unique_users = sorted(df["user_id"].unique())
    unique_movies = sorted(df["movie_id"].unique())

    user_id_to_idx = {uid: i for i, uid in enumerate(unique_users)}
    movie_id_to_idx = {mid: i for i, mid in enumerate(unique_movies)}
    idx_to_movie_id = {i: mid for mid, i in movie_id_to_idx.items()}

    user_idxs = df["user_id"].map(user_id_to_idx).astype("int32").values
    movie_idxs = df["movie_id"].map(movie_id_to_idx).astype("int32").values
    labels = df["label"].astype("float32").values

    print(f"Dataset: {len(labels)} samples, {len(unique_users)} users, {len(unique_movies)} movies.")

    return {
        "user_idxs": user_idxs,
        "movie_idxs": movie_idxs,
        "labels": labels,
        "user_id_to_idx": user_id_to_idx,
        "movie_id_to_idx": movie_id_to_idx,
        "idx_to_movie_id": idx_to_movie_id,
    }


def build_model(num_users: int, num_items: int) -> keras.Model:
    user_input = keras.Input(shape=(), dtype="int32", name="user_idx")
    item_input = keras.Input(shape=(), dtype="int32", name="item_idx")

    user_emb = keras.layers.Embedding(num_users, 64, name="user_embedding")(user_input)
    item_emb = keras.layers.Embedding(num_items, 64, name="item_embedding")(item_input)

    x = keras.layers.Concatenate()([user_emb, item_emb])
    x = keras.layers.Flatten()(x)
    x = keras.layers.Dense(128, activation="relu")(x)
    x = keras.layers.Dense(64, activation="relu")(x)
    x = keras.layers.Dense(32, activation="relu")(x)
    output = keras.layers.Dense(1, activation="sigmoid")(x)

    model = keras.Model(inputs=[user_input, item_input], outputs=output)
    model.compile(
        optimizer=keras.optimizers.Adam(learning_rate=1e-3),
        loss="binary_crossentropy",
        metrics=["accuracy", keras.metrics.AUC(name="auc")],
    )
    return model


def train_ncf(engine):
    data = build_dataset(engine)
    if data is None:
        print("No data available for recommender NCF training.")
        return None, None

    user_idxs = data["user_idxs"]
    movie_idxs = data["movie_idxs"]
    labels = data["labels"]

    num_users = len(data["user_id_to_idx"])
    num_items = len(data["movie_id_to_idx"])

    model = build_model(num_users, num_items)

    # Simple train/val split
    n = len(labels)
    idx = np.arange(n)
    np.random.shuffle(idx)
    split = int(0.8 * n)
    train_idx, val_idx = idx[:split], idx[split:]

    x_train = [user_idxs[train_idx], movie_idxs[train_idx]]
    y_train = labels[train_idx]
    x_val = [user_idxs[val_idx], movie_idxs[val_idx]]
    y_val = labels[val_idx]

    callbacks = [
        keras.callbacks.EarlyStopping(
            monitor="val_auc", patience=3, mode="max", restore_best_weights=True
        )
    ]

    history = model.fit(
        x_train,
        y_train,
        validation_data=(x_val, y_val),
        epochs=30,
        batch_size=256,
        callbacks=callbacks,
        verbose=2,
    )

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    model.save(MODEL_PATH)
    print(f"Saved NCF model to {MODEL_PATH}")

    metrics = {
        "loss": float(history.history.get("loss", [0])[-1]),
        "val_loss": float(history.history.get("val_loss", [0])[-1]),
        "auc": float(history.history.get("auc", [0])[-1]) if "auc" in history.history else 0.0,
        "val_auc": float(history.history.get("val_auc", [0])[-1]) if "val_auc" in history.history else 0.0,
    }

    artifacts = {
        "user_id_to_idx": data["user_id_to_idx"],
        "movie_id_to_idx": data["movie_id_to_idx"],
        "idx_to_movie_id": data["idx_to_movie_id"],
        "num_users": num_users,
        "num_items": num_items,
        "negative_sampling_ratio": NEGATIVE_RATIO,
        "train_timestamp": datetime.utcnow().isoformat(),
        "metrics": metrics,
    }

    joblib.dump(artifacts, ARTIFACTS_PATH)
    print(f"Saved NCF artifacts to {ARTIFACTS_PATH}")

    return model, metrics


def auto_bump_version(session, model_type: str) -> str:
    last = (
        session.query(MLModel)
        .filter(MLModel.model_type == model_type)
        .order_by(MLModel.created_at.desc())
        .first()
    )
    if not last or not last.version:
        return "1.0.0"
    try:
        major, minor, patch = map(int, last.version.split("."))
        patch += 1
        return f"{major}.{minor}.{patch}"
    except Exception:
        return last.version


def register_model(engine, metrics):
    print("Registering NCF recommender model...")
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        session.query(MLModel).filter(MLModel.model_type == "recommender_ncf").update(
            {MLModel.is_active: False}
        )
        version = auto_bump_version(session, "recommender_ncf")
        entry = MLModel(
            name="Nautilus_NCF",
            version=version,
            model_type="recommender_ncf",
            file_path=MODEL_PATH,
            metrics=metrics,
            is_active=True,
        )
        session.add(entry)
        session.commit()
        print(f"Registered NCF model v{version} with metrics: {metrics}")
    except Exception as e:
        session.rollback()
        print(f"Error registering NCF model: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    load_dotenv()
    engine = create_engine(DATABASE_URL)
    model, metrics = train_ncf(engine)
    if model is not None:
        register_model(engine, metrics)
