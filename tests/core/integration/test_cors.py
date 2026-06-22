from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_cors_preflight_on_token_route():
    """OPTIONS /api/auth/token com headers CORS deve retornar 200 e os headers de CORS correspondentes."""
    headers = {
        "Origin": "http://localhost:5000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    response = client.options("/api/auth/token", headers=headers)
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] in ["*", "http://localhost:5000"]
    assert "access-control-allow-methods" in response.headers
    assert (
        "POST" in response.headers["access-control-allow-methods"]
        or "*" in response.headers["access-control-allow-methods"]
    )


def test_cors_header_on_get_request():
    """GET / com Origin header deve retornar cabeçalhos de CORS."""
    headers = {
        "Origin": "http://localhost:5000",
    }
    response = client.get("/", headers=headers)
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
    assert response.headers["access-control-allow-origin"] in ["*", "http://localhost:5000"]
