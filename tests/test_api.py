from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_read_main():
    """Check if the UI loads (Status 200)"""
    response = client.get("/")
    assert response.status_code == 200

def test_read_movies():
    """Check if the /movies endpoint returns a list"""
    response = client.get("/movies")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_docs_reachable():
    """Check if Swagger UI is up"""
    response = client.get("/docs")
    assert response.status_code == 200