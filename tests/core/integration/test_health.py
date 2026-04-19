from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)

# ===================================================================
# TESTES: Health Check (Integração com Mocks de Rede)
# ===================================================================


class TestHealthCheck:
    """Testes para a rota de health check com mocks de rede reais."""

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_health_check_upstream_online(self, mock_get):
        """GET / deve mostrar sispubli_online: true quando o GET retorna 200."""
        # Simular resposta 200 para o GET
        mock_get.return_value = MagicMock(status_code=200)

        response = client.get("/")
        data = response.json()

        assert response.status_code == 200
        assert data["sispubli_online"] is True
        # Verifica se usamos o método GET agora (correção da bug)
        mock_get.assert_called_once()

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_health_check_upstream_offline(self, mock_get):
        """GET / deve mostrar sispubli_online: false quando o upstream falha."""
        # Simular erro 403 (ou qualquer erro >= 400)
        mock_get.return_value = MagicMock(status_code=403)

        response = client.get("/")
        data = response.json()

        assert response.status_code == 200  # Nossa API continua viva
        assert data["sispubli_online"] is False

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_health_check_upstream_timeout(self, mock_get):
        """GET / deve tratar timeouts do upstream sem quebrar."""
        mock_get.side_effect = httpx.TimeoutException("Timeout")

        response = client.get("/")
        data = response.json()

        assert response.status_code == 200
        assert data["sispubli_online"] is False
