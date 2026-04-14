# --- Build Stage ---
FROM python:3.13-slim AS base

# Metadata
LABEL maintainer="sispubli-api"
LABEL description="API REST para extracao de certificados do Sispubli/IFS"

# Variáveis de ambiente para Python otimizado
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar uv no container
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copiar arquivos de dependência primeiro (cache de camadas)
COPY pyproject.toml uv.lock ./

# Instalar dependências (sem dev, sem editable)
RUN uv sync --frozen --no-dev

# Copiar código-fonte
COPY scraper.py api.py logger.py ./

# Porta da API
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

# Comando de inicialização
CMD ["uv", "run", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
