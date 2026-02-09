import torch
import torch.nn as nn
import torch.optim as optim
import pandas as pd
import numpy as np
import csv
import glob
import os
from pathlib import Path
from sqlalchemy.orm import Session
from src.core.database import engine
from src.core.models import Interaction, MLModel

class RecommenderNet(nn.Module):
    def __init__(self, num_users, num_items, embedding_dim=32):
        super().__init__()
        self.user_embedding = nn.Embedding(num_users, embedding_dim)
        self.item_embedding = nn.Embedding(num_items, embedding_dim)
        self.fc = nn.Sequential(
            nn.Linear(embedding_dim * 2, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, 32),
            nn.ReLU(),
            nn.Linear(32, 1),
            nn.Sigmoid()
        )

    def forward(self, user_indices, item_indices):
        user_embed = self.user_embedding(user_indices)
        item_embed = self.item_embedding(item_indices)
        x = torch.cat([user_embed, item_embed], dim=1)
        return self.fc(x)


def _load_movielens_ratings(max_rows=200000):
    """Load MovieLens ratings as fallback training data."""
    ratings_paths = glob.glob('data/raw/**/ratings.csv', recursive=True)
    if not ratings_paths:
        return None
    
    # Prefer ml-25m (larger), fall back to archive
    path = ratings_paths[0]
    for p in ratings_paths:
        if 'ml-25m' in p:
            path = p
            break
    
    print(f"Loading MovieLens ratings from {path}...")
    rows = []
    try:
        with open(path, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= max_rows:
                    break
                try:
                    uid = int(row.get('userId', 0))
                    mid = int(row.get('movieId', 0))
                    rating = float(row.get('rating', 0))
                    if uid and mid and rating > 0:
                        rows.append({'user_id': uid, 'movie_id': mid, 'rating_value': rating})
                except (ValueError, TypeError):
                    continue
    except Exception as e:
        print(f"Error reading MovieLens: {e}")
        return None
    
    if not rows:
        return None
    
    df = pd.DataFrame(rows)
    print(f"Loaded {len(df)} MovieLens ratings ({df['user_id'].nunique()} users, {df['movie_id'].nunique()} movies)")
    return df


def train_recommender(epochs=15):
    """Train the NCF recommender. Uses DB interactions if available, falls back to MovieLens."""
    print("Training PyTorch Recommender...")
    
    # 1. Try DB interactions first
    df = None
    source = "db"
    try:
        query = """
            SELECT user_id, movie_id, 
                   CASE 
                       WHEN interaction_type = 'like' THEN 4.5
                       WHEN interaction_type = 'watchlist' THEN 3.5
                       WHEN interaction_type = 'watch' THEN 3.0
                       ELSE COALESCE(rating_value, 3.0)
                   END as rating_value
            FROM interactions 
            WHERE movie_id IS NOT NULL AND user_id IS NOT NULL
        """
        df = pd.read_sql(query, engine)
        print(f"DB interactions: {len(df)} rows")
    except Exception as e:
        print(f"DB query error: {e}")
        df = pd.DataFrame()
    
    # 2. If DB is too sparse, fall back to MovieLens
    if df is None or len(df) < 50:
        print("DB interactions too sparse. Falling back to MovieLens data...")
        df = _load_movielens_ratings(max_rows=200000)
        source = "movielens"
        if df is None or len(df) < 50:
            print("No training data available. Please ingest some movies and interact with them first.")
            return
    
    # 3. Map IDs to contiguous indices
    user_ids = df['user_id'].unique().tolist()
    movie_ids = df['movie_id'].unique().tolist()
    
    user_to_idx = {u: i for i, u in enumerate(user_ids)}
    movie_to_idx = {m: i for i, m in enumerate(movie_ids)}
    
    num_users = len(user_ids)
    num_movies = len(movie_ids)
    
    print(f"Training on {len(df)} interactions | {num_users} users | {num_movies} items | source={source}")
    
    # 4. Prepare Tensors
    users_t = torch.tensor([user_to_idx[u] for u in df['user_id']], dtype=torch.long)
    movies_t = torch.tensor([movie_to_idx[m] for m in df['movie_id']], dtype=torch.long)
    ratings_t = torch.tensor([r / 5.0 for r in df['rating_value']], dtype=torch.float32)
    
    # 5. Train/Val split (90/10)
    n = len(df)
    perm = torch.randperm(n)
    split = int(n * 0.9)
    train_idx, val_idx = perm[:split], perm[split:]
    
    # 6. Build model
    embedding_dim = 32 if num_users < 10000 else 64
    model = RecommenderNet(num_users, num_movies, embedding_dim=embedding_dim)
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-5)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=5, gamma=0.5)
    
    # 7. Training loop
    best_val_loss = float('inf')
    batch_size = min(2048, len(train_idx))
    
    model.train()
    for epoch in range(epochs):
        # Mini-batch training
        epoch_loss = 0.0
        num_batches = 0
        shuffled = train_idx[torch.randperm(len(train_idx))]
        
        for start in range(0, len(shuffled), batch_size):
            batch = shuffled[start:start+batch_size]
            optimizer.zero_grad()
            outputs = model(users_t[batch], movies_t[batch]).squeeze()
            loss = criterion(outputs, ratings_t[batch])
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
            num_batches += 1
        
        avg_train_loss = epoch_loss / max(num_batches, 1)
        
        # Validation
        model.eval()
        with torch.no_grad():
            val_out = model(users_t[val_idx], movies_t[val_idx]).squeeze()
            val_loss = criterion(val_out, ratings_t[val_idx]).item()
        model.train()
        
        scheduler.step()
        
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), "src/models/recommender_torch.pth")
        
        if (epoch + 1) % 3 == 0 or epoch == 0:
            print(f"  Epoch {epoch+1}/{epochs} | Train Loss: {avg_train_loss:.4f} | Val Loss: {val_loss:.4f}")
    
    # 8. Final metrics
    model.eval()
    with torch.no_grad():
        all_out = model(users_t, movies_t).squeeze()
        all_preds = (all_out * 5.0).numpy()
        all_true = (ratings_t * 5.0).numpy()
        mae = np.mean(np.abs(all_preds - all_true))
        rmse = np.sqrt(np.mean((all_preds - all_true) ** 2))
    
    print(f"  Final MAE: {mae:.4f} | RMSE: {rmse:.4f} | Best Val Loss: {best_val_loss:.4f}")
    
    # 9. Save model and log to DB
    save_path = "src/models/recommender_torch.pth"
    torch.save(model.state_dict(), save_path)
    
    # Log to ml_models table
    try:
        from sqlalchemy import create_engine as _ce
        from sqlalchemy.orm import sessionmaker as _sm
        from src.core.database import DATABASE_URL
        _eng = _ce(DATABASE_URL)
        _Session = _sm(bind=_eng)
        sess = _Session()
        
        # Deactivate previous recommender models
        sess.query(MLModel).filter(MLModel.model_type == 'recommender').update({'is_active': False})
        
        record = MLModel(
            name='Recommender NCF',
            version=f'v{pd.Timestamp.now().strftime("%Y%m%d_%H%M")}',
            model_type='recommender',
            file_path=save_path,
            metrics={
                'mae': round(float(mae), 4),
                'rmse': round(float(rmse), 4),
                'val_loss': round(float(best_val_loss), 4),
                'train_samples': int(len(train_idx)),
                'val_samples': int(len(val_idx)),
                'num_users': num_users,
                'num_items': num_movies,
                'epochs': epochs,
                'source': source
            },
            is_active=True
        )
        sess.add(record)
        sess.commit()
        sess.close()
        print(f"Model logged to ml_models table.")
    except Exception as e:
        print(f"Warning: Could not log model to DB: {e}")
    
    print(f"Training complete. Model saved to {save_path}")
