from unittest.mock import patch

from fastapi.testclient import TestClient

from api import app

# ===================================================================
# TESTES: Health Check
# ===================================================================


class TestHealthCheck:
    """Testes para a rota de health check."""

    @patch("api._check_upstream_connectivity")
    def test_health_check_status_200(self, mock_check):
        """GET / deve retornar 200 independente do upstream."""
        mock_check.return_value = True
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200

    @patch("api._check_upstream_connectivity")
    def test_health_check_full_schema(self, mock_check):
        """GET / deve retornar JSON com todos os campos do modelo HealthResponse."""
        mock_check.return_value = True
        client = TestClient(app)
        response = client.get("/")
        data = response.json()

        assert data["status"] == "online"
        assert "environment" in data
        assert "version" in data
        assert "timestamp" in data
        assert "security_configured" in data
        assert data["sispubli_online"] is True

    @patch("api._check_upstream_connectivity")
    def test_health_check_upstream_offline(self, mock_check):
        """API deve continuar online (200) mesmo se o Sispubli (upstream) falhar."""
        mock_check.return_value = False
        client = TestClient(app)
        response = client.get("/")
        data = response.json()

        assert response.status_code == 200
        assert data["status"] == "online"
        assert data["sispubli_online"] is False
