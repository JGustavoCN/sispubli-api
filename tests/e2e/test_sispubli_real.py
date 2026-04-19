"""
Teste E2E — Sispubli Real.

Este teste bate no sistema Sispubli REAL usando o CPF_TESTE do .env.
NAO roda por padrao (requer: make test-e2e ou pytest -m e2e).

ATENCAO: Este teste depende de:
    1. Conectividade com http://intranet.ifs.edu.br
    2. CPF_TESTE valido no arquivo .env
    3. Sispubli estar online e respondendo
"""

import os

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from src.main import app

# Carregar variaveis de ambiente do .env
load_dotenv()


@pytest.mark.e2e
class TestSispubliReal:
    """Testes E2E que acessam o Sispubli real."""

    def _get_cpf_teste(self) -> str:
        """Obtem o CPF de teste do .env ou pula o teste."""
        cpf = os.getenv("CPF_TESTE")
        if not cpf:
            pytest.skip("CPF_TESTE nao definido no .env — pulando teste E2E")
        return cpf

    def _obter_token(self, client: TestClient, cpf: str) -> str:
        """Helper para realizar o login e obter o access_token."""
        response = client.post("/api/auth/token", json={"cpf": cpf})
        assert response.status_code == 200, f"Falha na autenticacao E2E: {response.text}"
        return response.json()["access_token"]

    def test_listagem_certificados_real_fluxo_completo(self):
        """Busca certificados reais usando o fluxo de autenticacao seguro.

        Valida:
            - Login (POST /api/auth/token)
            - Listagem (GET /api/certificados com Bearer Token)
            - Estrutura da resposta e mascaramento de CPF
        """
        cpf = self._get_cpf_teste()
        client = TestClient(app)

        # 1. Obter Token
        token = self._obter_token(client, cpf)

        # 2. Listagem Segura
        response = client.get(
            "/api/certificados",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200, (
            f"Esperado 200, recebido {response.status_code}: {response.text}"
        )

        data = response.json()
        assert "data" in data
        result = data["data"]

        # Campos obrigatorios e tipos
        assert "usuario_id" in result
        assert isinstance(result["certificados"], list)

        # CPF deve estar mascarado na resposta JSON
        assert "***" in result["usuario_id"]
        # Seguranca extra: o CPF real nunca deve aparecer no corpo da resposta
        assert cpf not in response.text

        # Total deve ser coerente
        assert result["total"] == len(result["certificados"])

    def test_estrutura_certificados_reais_com_auth(self):
        """Valida a estrutura de cada certificado retornado do Sispubli real via Auth."""
        cpf = self._get_cpf_teste()
        client = TestClient(app)

        token = self._obter_token(client, cpf)
        response = client.get(
            "/api/certificados",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        certificados = response.json()["data"]["certificados"]

        if len(certificados) == 0:
            pytest.skip(f"Nenhum certificado encontrado para o CPF ***{cpf[3:6]}***")

        for cert in certificados:
            # Chaves obrigatorias
            assert "id_unico" in cert
            assert "titulo" in cert
            assert "url_download" in cert

            # Validação de Hash e Tickets
            assert len(cert["id_unico"]) == 64  # SHA-256
            if cert["url_download"] is not None:
                assert cert["url_download"].startswith("/api/pdf/")
                # O CPF real nao deve estar injetado na URL do ticket de forma visível
                assert cpf not in cert["url_download"]
