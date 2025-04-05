import pytest
from app import create_app
from flask import json

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_user_registration_success(client):
    response = client.post('/api/register', json={
        "username": "testuser",
        "email": "testuser@example.com",
        "password": "securepassword"
    })
    assert response.status_code == 201
    data = response.get_json()
    assert "message" in data
    assert data["message"] == "User registered successfully."

def test_user_registration_duplicate(client):
    # First registration should succeed
    client.post('/api/register', json={
        "username": "duplicateuser",
        "email": "dup@example.com",
        "password": "abc123"
    })

    # Second registration with same email should fail
    response = client.post('/api/register', json={
        "username": "duplicateuser2",
        "email": "dup@example.com",
        "password": "xyz789"
    })

    assert response.status_code == 400
    data = response.get_json()
    assert "error" in data
