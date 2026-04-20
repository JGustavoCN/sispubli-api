import os

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture(scope="module")
def real_client():
    """Retorna um TestClient para a aplicação real."""
    return TestClient(app)


@pytest.fixture(scope="module")
def cpf_teste():
    """Obtém o CPF de teste do .env ou pula o teste."""
    cpf = os.getenv("CPF_TESTE")
    if not cpf:
        pytest.skip("CPF_TESTE não definido no .env — pulando teste E2E")
    return cpf


@pytest.fixture(scope="module")
def token_real(real_client, cpf_teste):
    """Realiza o login real e retorna o access_token."""
    response = real_client.post("/api/auth/token", json={"cpf": cpf_teste})
    assert response.status_code == 200, f"Falha na autenticação E2E: {response.text}"
    return response.json()["access_token"]
