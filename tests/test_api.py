"""
Testes da API REST do Sispubli.

Cobertura:
    - GET /             : Health check
    - GET /api/certificados/{cpf}  : Busca de certificados (happy path)
    - GET /api/certificados/{cpf}  : CPF invalido (400)
    - GET /api/certificados/{cpf}  : Sispubli fora do ar (502)
    - GET /api/certificados/{cpf}  : Erro inesperado (500)

Usa httpx.AsyncClient com ASGITransport para testar a app FastAPI
sem subir o servidor.
"""

import logging
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import app

log = logging.getLogger(__name__)


# ===================================================================
# TESTES: Health Check
# ===================================================================


class TestHealthCheck:
    """Testes para a rota de health check."""

    def test_health_check_status_200(self):
        """GET / deve retornar 200."""
        log.info("Testando health check: GET /")
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200
        log.info("Status: %d", response.status_code)

    def test_health_check_body(self):
        """GET / deve retornar JSON com chave 'status'."""
        log.info("Testando corpo do health check")
        client = TestClient(app)
        response = client.get("/")
        data = response.json()
        assert "status" in data
        log.info("Resposta: %s", data)


# ===================================================================
# TESTES: Busca de Certificados — Happy Path
# ===================================================================


class TestCertificadosHappyPath:
    """Testes para busca de certificados com sucesso."""

    @patch("api.fetch_all_certificates")
    def test_busca_certificados_sucesso(self, mock_fetch):
        """GET /api/certificados/{cpf} deve retornar os certificados."""
        log.info("--- INICIO: teste de busca de certificados ---")

        mock_fetch.return_value = {
            "usuario_id": "***.456.789-**",
            "total": 1,
            "certificados": [
                {
                    "id_unico": "abc123def456abc123def456abc123de",
                    "titulo": "Participacao no(a) Evento Teste 2024",
                    "url": "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?x=1",
                }
            ],
        }

        client = TestClient(app)
        response = client.get("/api/certificados/12345678900")

        assert response.status_code == 200
        data = response.json()
        assert data["data"]["usuario_id"] == "***.456.789-**"
        assert data["data"]["total"] == 1
        assert len(data["data"]["certificados"]) == 1
        log.info("Certificados retornados: %d", data["data"]["total"])

        mock_fetch.assert_called_once_with("12345678900")
        log.info("--- FIM: teste de busca de certificados ---")

    @patch("api.fetch_all_certificates")
    def test_resposta_contem_estrutura_correta(self, mock_fetch):
        """Resposta deve seguir padrao {data: {...}}."""
        log.info("Testando estrutura da resposta")

        mock_fetch.return_value = {
            "usuario_id": "***.456.789-**",
            "total": 0,
            "certificados": [],
        }

        client = TestClient(app)
        response = client.get("/api/certificados/12345678900")

        data = response.json()
        assert "data" in data
        assert "usuario_id" in data["data"]
        assert "total" in data["data"]
        assert "certificados" in data["data"]
        log.info("Estrutura da resposta validada: OK")


# ===================================================================
# TESTES: Validacao de CPF
# ===================================================================


class TestCpfValidation:
    """Testes para validacao do CPF na rota."""

    def test_cpf_curto_retorna_400(self):
        """CPF com menos de 11 digitos deve retornar 400."""
        log.info("Testando CPF curto: 123")
        client = TestClient(app)
        response = client.get("/api/certificados/123")
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        log.info("Erro retornado: %s", data["error"])

    def test_cpf_com_letras_retorna_400(self):
        """CPF com caracteres nao numericos deve retornar 400."""
        log.info("Testando CPF com letras: abc12345678")
        client = TestClient(app)
        response = client.get("/api/certificados/abc12345678")
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        log.info("Erro retornado: %s", data["error"])

    def test_cpf_longo_retorna_400(self):
        """CPF com mais de 11 digitos deve retornar 400."""
        log.info("Testando CPF longo: 123456789001")
        client = TestClient(app)
        response = client.get("/api/certificados/123456789001")
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        log.info("Erro retornado: %s", data["error"])


# ===================================================================
# TESTES: Erros do Scraper / Sispubli
# ===================================================================


class TestScraperErrors:
    """Testes para quando o scraper/Sispubli falha."""

    @patch("api.fetch_all_certificates")
    def test_sispubli_fora_do_ar_retorna_502(self, mock_fetch):
        """Se o Sispubli retornar erro HTTP, a API deve retornar 502."""
        log.info("Testando Sispubli fora do ar (502)")

        mock_fetch.side_effect = Exception(
            "Erro ao acessar pagina inicial: 503"
        )

        client = TestClient(app)
        response = client.get("/api/certificados/12345678900")

        assert response.status_code == 502
        data = response.json()
        assert "error" in data
        assert "code" in data["error"]
        assert data["error"]["code"] == "upstream_error"
        log.info("Erro 502 retornado: %s", data["error"]["message"])

    @patch("api.fetch_all_certificates")
    def test_erro_inesperado_retorna_500(self, mock_fetch):
        """Erro generico/inesperado deve retornar 500."""
        log.info("Testando erro inesperado (500)")

        mock_fetch.side_effect = RuntimeError("Algo deu muito errado")

        client = TestClient(app)
        response = client.get("/api/certificados/12345678900")

        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "internal_error"
        log.info("Erro 500 retornado: %s", data["error"]["message"])

    @patch("api.fetch_all_certificates")
    def test_token_nao_encontrado_retorna_502(self, mock_fetch):
        """Token ausente indica problema no Sispubli -> 502."""
        log.info("Testando token nao encontrado (502)")

        mock_fetch.side_effect = Exception(
            "Token nao encontrado na pagina inicial"
        )

        client = TestClient(app)
        response = client.get("/api/certificados/12345678900")

        assert response.status_code == 502
        data = response.json()
        assert data["error"]["code"] == "upstream_error"
        log.info("Erro 502 retornado: %s", data["error"]["message"])
