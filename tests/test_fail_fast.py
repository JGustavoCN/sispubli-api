"""
Testes de Fail Fast na inicialização da aplicação (Lifespan).

Verifica se a API impede subir em produção ao identificar falta de
Segredos fundamentais (Privacy By Design).
"""

import pytest
from fastapi import FastAPI

from src.core.config import Config
from src.main import lifespan


@pytest.mark.asyncio
async def test_environment_dev_nao_crasha(monkeypatch):
    """Em Development a subida sem variáveis é perdoada (exceto se a ferramenta exigir)."""
    # Modifica o singleton para o teste
    original_env = Config.ENVIRONMENT
    Config.ENVIRONMENT = "development"

    app = FastAPI()

    try:
        # Testa subida e descida sem estourar RuntimeError
        async with lifespan(app):
            pass
    finally:
        Config.ENVIRONMENT = original_env


@pytest.mark.asyncio
async def test_environment_prod_falha_sem_variaveis(monkeypatch):
    """Garante que em Production a subida quebra com chaves ausentes."""
    original_env = Config.ENVIRONMENT
    original_key = Config.FERNET_SECRET_KEY

    # Forçamos a classe a entender que está em produção e sem chaves
    Config.ENVIRONMENT = "production"
    Config.FERNET_SECRET_KEY = ""

    app = FastAPI()

    try:
        # Tem que levantar RuntimeError com a mensagem de variáveis ausentes
        with pytest.raises(
            RuntimeError, match="FALHA CRITICA: ENVIRONMENT=production mas variáveis ausentes:"
        ):
            async with lifespan(app):
                pass
    finally:
        # Restaura estado original para não quebrar outros testes
        Config.ENVIRONMENT = original_env
        Config.FERNET_SECRET_KEY = original_key


@pytest.mark.asyncio
async def test_environment_prod_sucesso_com_variaveis(monkeypatch):
    """Garante que em Production a subida é concretizada se as chaves existirem."""
    original_env = Config.ENVIRONMENT
    original_key = Config.FERNET_SECRET_KEY

    Config.ENVIRONMENT = "production"
    Config.FERNET_SECRET_KEY = "ABCDEFGHIJLMNOPQRSTUVWXYZ1234567"  # pragma: allowlist secret

    app = FastAPI()

    try:
        # Valida sucesso
        async with lifespan(app):
            pass
    finally:
        Config.ENVIRONMENT = original_env
        Config.FERNET_SECRET_KEY = original_key
