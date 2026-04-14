"""
Testes da API REST do Sispubli.

Cobertura:
    - GET /             : Health check
    - GET /api/certificados/{cpf}  : Busca de certificados (happy path)
    - GET /api/certificados/{cpf}  : CPF invalido (400)
    - GET /api/certificados/{cpf}  : Sispubli fora do ar (502)
    - GET /api/certificados/{cpf}  : Erro inesperado (500)

Usa fastapi.testclient.TestClient para testar a app FastAPI
sem subir o servidor.
"""

from unittest.mock import patch

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


# ===================================================================
# TESTES: Busca de Certificados — Happy Path
# ===================================================================


class TestCertificadosHappyPath:
    """Testes para busca de certificados com sucesso."""

    @patch("api.fetch_all_certificates")
    def test_busca_certificados_sucesso(self, mock_fetch):
        """GET /api/certificados/{cpf} deve retornar os certificados."""
        mock_fetch.return_value = {
            "usuario_id": "***.456.789-**",
            "total": 1,
            "certificados": [
                {
                    "id_unico": "abc123def456abc123def456abc123de" * 2,  # 64 chars SHA-256
                    "titulo": "Participacao no(a) Evento Teste 2024",
                    "url_download": "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?tmp.tx_cpf={cpf}&x=1",
                    "ano": 2024,
                    "tipo_codigo": 1,
                    "tipo_descricao": "Participacao",
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

        mock_fetch.assert_called_once_with("12345678900")

    @patch("api.fetch_all_certificates")
    def test_resposta_contem_estrutura_correta(self, mock_fetch):
        """Resposta deve seguir padrao {data: {...}}."""
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


# ===================================================================
# TESTES: Validacao de CPF
# ===================================================================


class TestCpfValidation:
    """Testes para validacao do CPF na rota."""

    def test_cpf_curto_retorna_400(self):
        """CPF com menos de 11 digitos deve retornar 400."""
        client = TestClient(app)
        response = client.get("/api/certificados/123")
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_cpf_com_letras_retorna_400(self):
        """CPF com caracteres nao numericos deve retornar 400."""
        client = TestClient(app)
        response = client.get("/api/certificados/abc12345678")
        assert response.status_code == 400
        data = response.json()
        assert "error" in data

    def test_cpf_longo_retorna_400(self):
        """CPF com mais de 11 digitos deve retornar 400."""
        client = TestClient(app)
        response = client.get("/api/certificados/123456789001")
        assert response.status_code == 400
        data = response.json()
        assert "error" in data


# ===================================================================
# TESTES: Erros do Scraper / Sispubli
# ===================================================================


class TestScraperErrors:
    """Testes para quando o scraper/Sispubli falha."""

    @patch("api.fetch_all_certificates")
    def test_sispubli_fora_do_ar_retorna_502(self, mock_fetch):
        """Se o Sispubli retornar erro HTTP, a API deve retornar 502."""
        mock_fetch.side_effect = Exception("Erro ao acessar pagina inicial: 503")

        client = TestClient(app)
        response = client.get("/api/certificados/12345678900")

        assert response.status_code == 502
        data = response.json()
        assert "error" in data
        assert "code" in data["error"]
        assert data["error"]["code"] == "upstream_error"

    @patch("api.fetch_all_certificates")
    def test_erro_inesperado_retorna_500(self, mock_fetch):
        """Erro generico/inesperado deve retornar 500."""
        mock_fetch.side_effect = RuntimeError("Algo deu muito errado")

        client = TestClient(app)
        response = client.get("/api/certificados/12345678900")

        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "internal_error"

    @patch("api.fetch_all_certificates")
    def test_token_nao_encontrado_retorna_502(self, mock_fetch):
        """Token ausente indica problema no Sispubli -> 502."""
        mock_fetch.side_effect = Exception("Token nao encontrado na pagina inicial")

        client = TestClient(app)
        response = client.get("/api/certificados/12345678900")

        assert response.status_code == 502
        data = response.json()
        assert data["error"]["code"] == "upstream_error"
