from app.app import app


def test_home():
    """Test home endpoint."""
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
