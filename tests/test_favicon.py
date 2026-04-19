import os

from fastapi.testclient import TestClient

from api import app

client = TestClient(app)


def test_favicon_route_returns_200():
    """GET /favicon.ico deve retornar 200 se o arquivo existir."""
    response = client.get("/favicon.ico")
    # Se o arquivo existir na pasta static, deve ser 200.
    # Caso contrário, o fallback 204 é aceitável.
    if os.path.exists("static/favicon.ico"):
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/x-icon"
    else:
        assert response.status_code == 204


def test_static_files_accessible():
    """Arquivos na pasta /static devem estar acessíveis publicamente."""
    # Testar apple-touch-icon.png que verificamos que existe
    response = client.get("/static/apple-touch-icon.png")
    assert response.status_code == 200
    assert "image/png" in response.headers["content-type"]


def test_favicon_fallback_no_file(mocker):
    """Fallback: Retorna 204 se o arquivo não existir fisicamente."""
    # Mock do path.exists para simular ausência do arquivo
    mocker.patch("os.path.exists", return_value=False)
    response = client.get("/favicon.ico")
    assert response.status_code == 204


def test_docs_page_accessible():
    """Swagger UI (/docs) deve estar acessível."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Swagger UI" in response.text


def test_redoc_page_accessible():
    """ReDoc (/redoc) deve estar acessível."""
    response = client.get("/redoc")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "ReDoc" in response.text


def test_chrome_devtools_probe_returns_204():
    """Chrome DevTools probe deve retornar 204 para silenciar logs."""
    response = client.get("/.well-known/appspecific/com.chrome.devtools.json")
    assert response.status_code == 204
