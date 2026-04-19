"""
Testes de Integracao — API REST do Sispubli.

Valida o fluxo completo da API usando TestClient + mock do scraper.
Foco na serializacao Pydantic, formatacao de dados e tratamento de erros.

Diferente dos testes unitarios em test_api.py, estes testes validam:
    - Serializacao Pydantic dos campos do certificado
    - Tipos e formatos dos valores retornados
    - Cenarios com lista vazia
    - Multiplos certificados com tipos variados
    - Formato de erro padronizado para todos os cenarios de falha
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from src.core.security import gerar_token_sessao
from src.main import app

client = TestClient(app)


def _obter_token(cpf: str = "74839210055") -> str:
    """Gera um token de sessao para testes de integracao."""
    return gerar_token_sessao(cpf)


# ===================================================================
# TESTES: Serializacao Pydantic
# ===================================================================


class TestPydanticSerialization:
    """Valida que a API serializa os dados via Pydantic corretamente."""

    @patch("src.certificates.router.fetch_all_certificates")
    def test_campos_certificado_tipados_corretamente(self, mock_fetch):
        """Cada campo do certificado deve ter o tipo correto."""
        mock_fetch.return_value = {
            "usuario_id": "***.392.100-**",
            "total": 1,
            "certificados": [
                {
                    "id_unico": "a" * 64,  # 64 chars SHA-256
                    "titulo": "Participacao no(a) Evento Teste 2024",
                    "url_download": "http://intranet.ifs.edu.br/publicacoes/relat/cert.wsp?tmp.tx_cpf={cpf}&x=1",
                    "ano": 2024,
                    "tipo_codigo": 1,
                    "tipo_descricao": "Participacao",
                }
            ],
        }

        token = _obter_token()
        response = client.get("/api/certificados", headers={"Authorization": f"Bearer {token}"})
        data = response.json()

        assert response.status_code == 200
        cert = data["data"]["certificados"][0]
        assert isinstance(cert["id_unico"], str)
        assert isinstance(cert["titulo"], str)
        assert isinstance(cert["url_download"], str)
        assert isinstance(cert["ano"], int)
        assert isinstance(cert["tipo_codigo"], int)
        assert isinstance(cert["tipo_descricao"], str)
        assert len(cert["id_unico"]) == 64  # SHA-256 hex

    @patch("src.certificates.router.fetch_all_certificates")
    def test_url_nula_serializada_corretamente(self, mock_fetch):
        """Certificado com url_download=None deve serializar como null no JSON."""
        mock_fetch.return_value = {
            "usuario_id": "***.392.100-**",
            "total": 1,
            "certificados": [
                {
                    "id_unico": "d" * 64,
                    "titulo": "Certificado Sem URL",
                    "url_download": None,
                    "ano": 2021,
                    "tipo_codigo": 6,
                    "tipo_descricao": "Certificado Interno",
                }
            ],
        }

        token = _obter_token()
        response = client.get("/api/certificados", headers={"Authorization": f"Bearer {token}"})
        data = response.json()

        cert = data["data"]["certificados"][0]
        assert cert["url_download"] is None

    @patch("src.certificates.router.fetch_all_certificates")
    def test_lista_vazia_de_certificados(self, mock_fetch):
        """Busca sem certificados deve retornar lista vazia e total=0."""
        mock_fetch.return_value = {
            "usuario_id": "***.392.100-**",
            "total": 0,
            "certificados": [],
        }

        token = _obter_token()
        response = client.get("/api/certificados", headers={"Authorization": f"Bearer {token}"})
        data = response.json()

        assert response.status_code == 200
        assert data["data"]["total"] == 0
        assert data["data"]["certificados"] == []
        assert isinstance(data["data"]["certificados"], list)

    @patch("src.certificates.router.fetch_all_certificates")
    def test_multiplos_certificados_tipos_variados(self, mock_fetch):
        """Resposta com multiplos certificados de tipos diferentes."""
        mock_fetch.return_value = {
            "usuario_id": "***.392.100-**",
            "total": 3,
            "certificados": [
                {
                    "id_unico": "a" * 64,
                    "titulo": "Participacao no(a) Evento A",
                    "url_download": "http://example.com/cert1?tmp.tx_cpf={cpf}",
                    "ano": 2023,
                    "tipo_codigo": 1,
                    "tipo_descricao": "Participacao",
                },
                {
                    "id_unico": "b" * 64,
                    "titulo": "Autor no(a) Evento B",
                    "url_download": "http://example.com/cert2?tmp.tx_cpf={cpf}",
                    "ano": 2023,
                    "tipo_codigo": 2,
                    "tipo_descricao": "Autor",
                },
                {
                    "id_unico": "c" * 64,
                    "titulo": "Avaliador no(a) Programa C",
                    "url_download": None,
                    "ano": 2022,
                    "tipo_codigo": 6,
                    "tipo_descricao": "Certificado Interno",
                },
            ],
        }

        token = _obter_token()
        response = client.get("/api/certificados", headers={"Authorization": f"Bearer {token}"})
        data = response.json()

        assert response.status_code == 200
        assert data["data"]["total"] == 3
        assert len(data["data"]["certificados"]) == 3

        # Verificar que cada certificado tem todas as chaves esperadas
        chaves_esperadas = {
            "id_unico",
            "titulo",
            "url_download",
            "ano",
            "tipo_codigo",
            "tipo_descricao",
        }
        for cert in data["data"]["certificados"]:
            assert set(cert.keys()) == chaves_esperadas


class TestErrorFormat:
    """Valida que todos os erros seguem o padrao {error: {code, message}}."""

    def test_acesso_negado_sem_token(self):
        """Acesso sem token ou com token invalido deve retornar 401."""
        # 422 Unprocessable Entity devido a validacao Pydantic (TokenRequest) no /api/auth/token
        # Ou 401 se tentar direto no certificados.
        # Aqui testamos a rota de listagem sem token para garantir erro de seguranca.
        response = client.get("/api/certificados", headers={"Authorization": "Bearer LIXO"})
        data = response.json()

        assert response.status_code == 401
        assert "error" in data
        assert data["error"]["code"] == "invalid_token"

    @patch("src.certificates.router.fetch_all_certificates")
    def test_erro_502_formato_padronizado(self, mock_fetch):
        """Erro 502 deve seguir {error: {code: 'upstream_error', message: '...'}}."""
        # Na nova rota, simulamos ConnectionError que mapeia para 502
        mock_fetch.side_effect = ConnectionError("Sispubli timeout")

        token = _obter_token()
        response = client.get("/api/certificados", headers={"Authorization": f"Bearer {token}"})
        data = response.json()

        assert response.status_code == 502
        assert data["error"]["code"] == "upstream_error"
        assert "Sispubli" in data["error"]["message"]

    @patch("src.certificates.router.fetch_all_certificates")
    def test_erro_500_formato_padronizado(self, mock_fetch):
        """Erro 500 deve seguir {error: {code: 'internal_error', message: '...'}}."""
        mock_fetch.side_effect = ValueError("Erro inesperado")

        token = _obter_token()
        response = client.get("/api/certificados", headers={"Authorization": f"Bearer {token}"})
        data = response.json()

        assert response.status_code == 500
        assert data["error"]["code"] == "internal_error"
