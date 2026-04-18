"""
Testes de Integridade da API REST do Sispubli.

Cobertura:
    - GET / : Health check
"""

from fastapi.testclient import TestClient

from api import app

# ===================================================================
# TESTES: Health Check
# ===================================================================


class TestHealthCheck:
    """Testes para a rota de health check."""

    def test_health_check_status_200(self):
        """GET / deve retornar 200."""
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200

    def test_health_check_body(self):
        """GET / deve retornar JSON com chave 'status'."""
        client = TestClient(app)
        response = client.get("/")
        data = response.json()
        assert "status" in data
