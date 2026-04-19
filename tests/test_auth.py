"""
Testes da Rota de Autenticacao — POST /api/auth/token.

Cobertura TDD:
    - Happy path: CPF valido retorna access_token + session_hash
    - Validacao de CPF: letras, curto, longo → 400
    - Metodo incorreto: GET → 405
    - Body vazio → 422
    - Rate limit: 429 anti-enumeracao
    - Normalizacao de CPF com pontuacao
    - Token muito longo no header Authorization → 400
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from rate_limit import auth_limiter
from src.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_auth_limiter():
    """Reseta o rate limiter de auth antes de cada teste."""
    auth_limiter._requests.clear()
    yield
    auth_limiter._requests.clear()


# ===================================================================
# TESTES: Happy Path
# ===================================================================


class TestAuthHappyPath:
    """Testes para login com CPF valido."""

    def test_login_cpf_valido_retorna_200(self):
        """POST /api/auth/token com CPF valido retorna 200."""
        response = client.post("/api/auth/token", json={"cpf": "74839210055"})
        assert response.status_code == 200

    def test_login_resposta_contem_access_token(self):
        """Resposta deve conter campo access_token."""
        response = client.post("/api/auth/token", json={"cpf": "74839210055"})
        data = response.json()
        assert "access_token" in data
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0

    def test_login_resposta_contem_session_hash(self):
        """Resposta deve conter campo session_hash (64 chars hex)."""
        response = client.post("/api/auth/token", json={"cpf": "74839210055"})
        data = response.json()
        assert "session_hash" in data
        assert isinstance(data["session_hash"], str)
        assert len(data["session_hash"]) == 64

    def test_login_normaliza_cpf_com_pontuacao(self):
        """CPF com pontuacao deve ser aceito e normalizado."""
        # Usamos um CPF matematicamente valido para garantir o 200
        response = client.post("/api/auth/token", json={"cpf": "748.392.100-55"})
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data


# ===================================================================
# TESTES: Validacao de CPF
# ===================================================================


class TestAuthCpfValidation:
    """Testes para rejeicao de CPFs invalidos."""

    def test_cpf_com_letras_retorna_422(self):
        """CPF com caracteres nao numericos (apos normalizacao) retorna 422."""
        response = client.post("/api/auth/token", json={"cpf": "abc"})
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "invalid_cpf"

    def test_cpf_curto_retorna_422(self):
        """CPF com menos de 11 digitos retorna 422."""
        response = client.post("/api/auth/token", json={"cpf": "1234567890"})
        assert response.status_code == 422

    def test_cpf_longo_retorna_422(self):
        """CPF com mais de 11 digitos retorna 422."""
        response = client.post("/api/auth/token", json={"cpf": "748392100551"})
        assert response.status_code == 422

    def test_cpf_vazio_retorna_422(self):
        """CPF vazio retorna 422."""
        response = client.post("/api/auth/token", json={"cpf": ""})
        assert response.status_code == 422

    def test_cpf_matematicamente_invalido_retorna_422(self):
        """CPF com 11 digitos mas invalido no Modulo 11 retorna 422."""
        response = client.post("/api/auth/token", json={"cpf": "11111111111"})
        assert response.status_code == 422


# ===================================================================
# TESTES: Metodo e Body incorretos
# ===================================================================


class TestAuthMethodValidation:
    """Testes para metodos HTTP e body invalidos."""

    def test_get_retorna_405(self):
        """GET /api/auth/token deve retornar 405 Method Not Allowed."""
        response = client.get("/api/auth/token")
        assert response.status_code == 405

    def test_body_vazio_retorna_422(self):
        """Request sem body JSON retorna 422 Unprocessable Entity."""
        response = client.post("/api/auth/token")
        assert response.status_code == 422

    def test_body_sem_campo_cpf_retorna_422(self):
        """Body JSON sem campo 'cpf' retorna 422."""
        response = client.post("/api/auth/token", json={"nome": "teste"})
        assert response.status_code == 422


# ===================================================================
# TESTES: Rate Limit
# ===================================================================


class TestAuthRateLimit:
    """Testes para rate limit anti-enumeracao na rota de auth."""

    @patch("src.main.auth_limiter")
    def test_rate_limit_retorna_429(self, mock_limiter):
        """Exceder limite de auth deve retornar 429."""
        mock_limiter.check = AsyncMock(return_value=False)

        response = client.post("/api/auth/token", json={"cpf": "74839210055"})
        assert response.status_code == 429
        data = response.json()
        assert data["error"]["code"] == "rate_limit_exceeded"
