"""
Configuracao compartilhada de testes — sispubli-api.

Garante que ENVIRONMENT=test em todos os testes,
desabilitando os logs do Loguru para silencio total.
"""

import pytest


@pytest.fixture(autouse=True)
def _set_test_environment(monkeypatch):
    """Define ENVIRONMENT=test para silenciar o Loguru durante testes.

    Esta fixture roda automaticamente antes de cada teste.
    O Loguru so configura os sinks na importacao do modulo logger.py,
    entao precisamos garantir que a variavel esteja setada ANTES
    de qualquer import do logger.
    """
    monkeypatch.setenv("ENVIRONMENT", "test")
