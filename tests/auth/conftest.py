import pytest

from src.core.rate_limit import auth_limiter


@pytest.fixture(autouse=True)
def _reset_auth_limiter():
    """
    Reseta o rate limiter de auth antes de cada teste de autenticação.

    Isso garante que bloqueios temporários gerados em um teste não
    afetem a execução dos testes subsequentes na mesma suíte.
    """
    auth_limiter._requests.clear()
    yield
    auth_limiter._requests.clear()
