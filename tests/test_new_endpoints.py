from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_random_movies():
    response = client.get("/movies/random?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Note: might be empty if DB is empty, but status should be 200

def test_genre_movies():
    # Animation is 16
    response = client.get("/movies/genre/16?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

def test_desi_movies():
    # This hits TMDB, might fail if no key or network
    # We just check it doesn't crash
    response = client.get("/movies/desi?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)

def test_clustering_endpoint():
    response = client.get("/collections/ai")
    assert response.status_code == 200
    data = response.json()
    assert "cluster_1" in data
    assert "cluster_2" in data
