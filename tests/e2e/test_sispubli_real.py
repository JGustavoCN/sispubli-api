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

from api import app

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

    def test_busca_certificados_real(self):
        """Busca certificados reais de um CPF no Sispubli.

        Valida:
            - Status HTTP 200
            - Estrutura da resposta (data.usuario_id, data.total, data.certificados)
            - Tipos dos campos
            - Total >= 0
        """
        cpf = self._get_cpf_teste()

        client = TestClient(app)
        response = client.get(f"/api/certificados/{cpf}")

        assert response.status_code == 200, (
            f"Esperado 200, recebido {response.status_code}: {response.text}"
        )

        data = response.json()

        # Estrutura do envelope
        assert "data" in data
        result = data["data"]

        # Campos obrigatorios
        assert "usuario_id" in result
        assert "total" in result
        assert "certificados" in result

        # Tipos
        assert isinstance(result["usuario_id"], str)
        assert isinstance(result["total"], int)
        assert isinstance(result["certificados"], list)

        # CPF deve estar mascarado (nao exposto)
        assert "***" in result["usuario_id"]

        # Total deve ser coerente com a lista
        assert result["total"] == len(result["certificados"])
        assert result["total"] >= 0

    def test_estrutura_certificados_reais(self):
        """Valida a estrutura de cada certificado retornado do Sispubli real."""
        cpf = self._get_cpf_teste()

        client = TestClient(app)
        response = client.get(f"/api/certificados/{cpf}")

        assert response.status_code == 200
        certificados = response.json()["data"]["certificados"]

        if len(certificados) == 0:
            pytest.skip("Nenhum certificado encontrado para validar estrutura")

        for cert in certificados:
            # Chaves obrigatorias
            assert "id_unico" in cert, f"Campo 'id_unico' ausente em: {cert}"
            assert "titulo" in cert, f"Campo 'titulo' ausente em: {cert}"
            assert "url" in cert, f"Campo 'url' ausente em: {cert}"

            # Tipos
            assert isinstance(cert["id_unico"], str)
            assert len(cert["id_unico"]) == 32  # MD5 hex
            assert isinstance(cert["titulo"], str)
            assert len(cert["titulo"]) > 0

            # URL pode ser None ou string valida
            if cert["url"] is not None:
                assert isinstance(cert["url"], str)
                assert cert["url"].startswith("http")
