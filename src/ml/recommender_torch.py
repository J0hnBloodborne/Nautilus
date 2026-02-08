import torch
import torch.nn as nn
import torch.optim as optim
import pandas as pd
import numpy as np
from sqlalchemy.orm import Session
from src.core.database import engine
from src.core.models import Interaction

class RecommenderNet(nn.Module):
    def __init__(self, num_users, num_items, embedding_dim=32):
        super().__init__()
        self.user_embedding = nn.Embedding(num_users, embedding_dim)
        self.item_embedding = nn.Embedding(num_items, embedding_dim)
        self.fc = nn.Sequential(
            nn.Linear(embedding_dim * 2, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid()
        )

    def forward(self, user_indices, item_indices):
        user_embed = self.user_embedding(user_indices)
        item_embed = self.item_embedding(item_indices)
        x = torch.cat([user_embed, item_embed], dim=1)
        return self.fc(x)

def train_recommender():
    print("Training PyTorch Recommender...")
    # 1. Fetch data
    query = "SELECT user_id, movie_id, rating_value FROM interactions WHERE movie_id IS NOT NULL"
    df = pd.read_sql(query, engine)
    
    if len(df) < 10:
        print("Not enough data to train.")
        return

    # 2. Map IDs to indices
    user_ids = df['user_id'].unique().tolist()
    movie_ids = df['movie_id'].unique().tolist()
    
    user_to_idx = {u: i for i, u in enumerate(user_ids)}
    movie_to_idx = {m: i for i, m in enumerate(movie_ids)}
    
    num_users = len(user_ids)
    num_movies = len(movie_ids)
    
    # 3. Prepare Tensors
    users = torch.tensor([user_to_idx[u] for u in df['user_id']], dtype=torch.long)
    movies = torch.tensor([movie_to_idx[m] for m in df['movie_id']], dtype=torch.long)
    ratings = torch.tensor([r / 5.0 for r in df['rating_value']], dtype=torch.float32) # Normalize 0-1

    # 4. Train
    model = RecommenderNet(num_users, num_movies)
    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=0.01)

    model.train()
    for epoch in range(5): # Short training for example
        optimizer.zero_grad()
        outputs = model(users, movies).squeeze()
        loss = criterion(outputs, ratings)
        loss.backward()
        optimizer.step()
        print(f"Epoch {epoch+1}, Loss: {loss.item():.4f}")

    # 5. Save Model (Simplified)
    torch.save(model.state_dict(), "src/models/recommender_torch.pth")
    print("Model saved.")
