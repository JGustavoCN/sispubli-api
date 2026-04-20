"""
Teste E2E — Sispubli Real.

Este teste bate no sistema Sispubli REAL usando o CPF_TESTE do .env.
NAO roda por padrao (requer: make test-e2e ou pytest -m e2e).

ATENCAO: Este teste depende de:
    1. Conectividade com http://intranet.ifs.edu.br
    2. CPF_TESTE valido no arquivo .env
    3. Sispubli estar online e respondendo
"""

import pytest


@pytest.mark.e2e
class TestSispubliReal:
    """Testes E2E que acessam o Sispubli real."""

    def test_listagem_certificados_real_fluxo_completo(self, real_client, token_real, cpf_teste):
        """Busca certificados reais usando o fluxo de autenticacao seguro.

        Valida:
            - Login (POST /api/auth/token) - Via fixture token_real
            - Listagem (GET /api/certificados com Bearer Token)
            - Estrutura da resposta e mascaramento de CPF
        """
        # 2. Listagem Segura
        response = real_client.get(
            "/api/certificados",
            headers={"Authorization": f"Bearer {token_real}"},
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
        assert cpf_teste not in response.text

        # Total deve ser coerente
        assert result["total"] == len(result["certificados"])

    def test_estrutura_certificados_reais_com_auth(self, real_client, token_real, cpf_teste):
        """Valida a estrutura de cada certificado retornado do Sispubli real via Auth."""
        response = real_client.get(
            "/api/certificados",
            headers={"Authorization": f"Bearer {token_real}"},
        )

        assert response.status_code == 200
        certificados = response.json()["data"]["certificados"]

        if len(certificados) == 0:
            pytest.skip(f"Nenhum certificado encontrado para o CPF ***{cpf_teste[3:6]}***")

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
                assert cpf_teste not in cert["url_download"]
