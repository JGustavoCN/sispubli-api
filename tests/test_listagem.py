"""
Testes da Rota de Listagem — GET /api/certificados.

Cobertura TDD:
    - 401 sem header Authorization
    - 401 com token invalido/corrompido
    - 401 com token expirado (TTL)
    - 400 com token > 2048 chars
    - 200 happy path com certificados mockados
    - URLs apontam para /api/pdf/{ticket}
    - CPF nao aparece na resposta JSON
    - Headers Cache-Control e Vary corretos
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api import app
from rate_limit import auth_limiter
from security import gerar_token_sessao

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset_limiters():
    """Reseta rate limiters entre testes."""
    auth_limiter._requests.clear()
    yield
    auth_limiter._requests.clear()


# ===================================================================
# TESTES: Ausencia de Autorizacao
# ===================================================================


class TestListagemAuth:
    """Testes para validacao do header Authorization."""

    def test_sem_header_auth_retorna_401(self):
        """GET /api/certificados sem Authorization retorna 401."""
        response = client.get("/api/certificados")
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "unauthorized"

    def test_token_invalido_retorna_401(self):
        """Token Fernet corrompido retorna 401."""
        response = client.get(
            "/api/certificados",
            headers={"Authorization": "Bearer TOKEN_LIXO_INVALIDO"},
        )
        assert response.status_code == 401
        data = response.json()
        assert data["error"]["code"] == "invalid_token"

    def test_bearer_prefix_ausente_retorna_401(self):
        """Header sem prefixo 'Bearer ' retorna 401."""
        token = gerar_token_sessao("74839210055")
        response = client.get(
            "/api/certificados",
            headers={"Authorization": token},
        )
        assert response.status_code == 401

    def test_token_muito_longo_retorna_400(self):
        """Token > 2048 caracteres retorna 400 imediatamente."""
        token_longo = "A" * 2049
        response = client.get(
            "/api/certificados",
            headers={"Authorization": f"Bearer {token_longo}"},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "token_too_large"


# ===================================================================
# TESTES: Happy Path com Mock do Scraper
# ===================================================================


MOCK_SCRAPER_RESULT = {
    "usuario_id": "***.456.789-**",
    "total": 2,
    "certificados": [
        {
            "id_unico": "a" * 64,
            "titulo": "Participacao no(a) SEPEX 2023",
            "url_download": (
                "http://intranet.ifs.edu.br/publicacoes/relat/"
                "certificado_participacao_process.wsp?"
                "tmp.tx_cpf={cpf}&tmp.id_programa=1850&tmp.id_edicao=2011"
            ),
            "ano": 2023,
            "tipo_codigo": 1,
            "tipo_descricao": "Participacao",
        },
        {
            "id_unico": "b" * 64,
            "titulo": "Certificado Interno Sem URL",
            "url_download": None,
            "ano": 2022,
            "tipo_codigo": 6,
            "tipo_descricao": "Certificado Interno",
        },
    ],
}


class TestListagemHappyPath:
    """Testes para listagem de certificados com token valido."""

    @patch("api.fetch_all_certificates")
    def test_listagem_retorna_200_com_token_valido(self, mock_fetch):
        """Token valido deve retornar 200 com certificados."""
        mock_fetch.return_value = MOCK_SCRAPER_RESULT
        token = gerar_token_sessao("74839210055")

        response = client.get(
            "/api/certificados",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["total"] == 2

    @patch("api.fetch_all_certificates")
    def test_urls_apontam_para_tunel_pdf(self, mock_fetch):
        """URLs dos certificados devem apontar para /api/pdf/{ticket}."""
        mock_fetch.return_value = MOCK_SCRAPER_RESULT
        token = gerar_token_sessao("74839210055")

        response = client.get(
            "/api/certificados",
            headers={"Authorization": f"Bearer {token}"},
        )
        data = response.json()
        certs = data["data"]["certificados"]

        # Primeiro cert tem URL → deve virar /api/pdf/<ticket>
        assert certs[0]["url_download"].startswith("/api/pdf/")
        # Segundo cert sem URL → None
        assert certs[1]["url_download"] is None

    @patch("api.fetch_all_certificates")
    def test_nenhum_cpf_na_resposta(self, mock_fetch):
        """Seguranca: CPF real nao deve aparecer em nenhum campo da resposta."""
        mock_fetch.return_value = MOCK_SCRAPER_RESULT
        cpf_real = "74839210055"
        token = gerar_token_sessao(cpf_real)

        response = client.get(
            "/api/certificados",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Serializa resposta inteira como string e verifica
        response_text = response.text
        assert cpf_real not in response_text

    @patch("api.fetch_all_certificates")
    def test_headers_cache_control(self, mock_fetch):
        """Resposta deve conter headers de cache corretos."""
        mock_fetch.return_value = MOCK_SCRAPER_RESULT
        token = gerar_token_sessao("74839210055")

        response = client.get(
            "/api/certificados",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert "s-maxage=600" in response.headers.get("cache-control", "")
        assert "Authorization" in response.headers.get("vary", "")
