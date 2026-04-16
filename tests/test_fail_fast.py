"""
Testes de Fail Fast na inicialização da aplicação (Lifespan).

Verifica se a API impede subir em produção ao identificar falta de
Segredos fundamentais (Privacy By Design).
"""

import pytest
from fastapi import FastAPI

from api import lifespan


@pytest.mark.asyncio
async def test_environment_dev_nao_crasha(monkeypatch):
    """Em Development a subida sem variáveis é perdoada (exceto se a ferramenta exigir)."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    app = FastAPI()

    # Testa subida e descida sem estourar RuntimeError
    async with lifespan(app):
        pass


@pytest.mark.asyncio
async def test_environment_prod_falha_sem_variaveis(monkeypatch):
    """Garante que em Production a subida quebra com chaves ausentes."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("SECRET_PEPPER", raising=False)
    monkeypatch.delenv("HASH_SALT", raising=False)
    monkeypatch.delenv("FERNET_SECRET_KEY", raising=False)

    app = FastAPI()

    # Tem que levantar RuntimeError impedindo o servidor de subir
    with pytest.raises(RuntimeError, match="Variaveis obrigatorias ausentes"):
        async with lifespan(app):
            pass


@pytest.mark.asyncio
async def test_environment_prod_sucesso_com_variaveis(monkeypatch):
    """Garante que em Production a subida é concretizada se as chaves existirem."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_PEPPER", "abcd")
    monkeypatch.setenv("HASH_SALT", "efgh")
    monkeypatch.setenv("FERNET_SECRET_KEY", "ABCDEFGHIJLMNOPQRSTUVWXYZ1234567")

    app = FastAPI()

    # Valida sucesso
    async with lifespan(app):
        pass
