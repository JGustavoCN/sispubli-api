# Makefile — Sispubli API
# Gerenciador: uv | Linter/Formatter: ruff | Testes: pytest

.PHONY: help install format lint test test-v serve run \
        pre-commit docker-build docker-run clean check

# Alvo padrão
all: help

help:
	@echo "===================================================="
	@echo "       SISPUBLI API - COMANDOS                      "
	@echo "===================================================="
	@echo "  make install      - Instala dependencias (uv sync)"
	@echo "  make format       - Formata codigo (ruff format)"
	@echo "  make lint         - Analise estatica (ruff check)"
	@echo "  make test         - Executa testes (pytest)"
	@echo "  make test-v       - Testes verbose com logs"
	@echo "  make serve        - Sobe API REST (uvicorn --reload)"
	@echo "  make run          - Executa scraper no terminal"
	@echo "  make pre-commit   - Instala hooks de pre-commit"
	@echo "  make docker-build - Build da imagem Docker"
	@echo "  make docker-run   - Roda container Docker"
	@echo "  make clean        - Limpa cache e temporarios"
	@echo "  make check        - Roda lint + test de uma vez"
	@echo "===================================================="

install:
	uv sync

format:
	uv run ruff format .

lint:
	uv run ruff check . --fix

test:
	uv run pytest -v --tb=short

test-v:
	uv run pytest -v --tb=short --log-cli-level=INFO

serve:
	uv run uvicorn api:app --reload --host 0.0.0.0 --port 8000

run:
	uv run python scraper.py

pre-commit:
	uv run pre-commit install
	uv run pre-commit install --hook-type commit-msg
	@echo "Hooks instalados com sucesso."

docker-build:
	docker build -t sispubli-api .

docker-run:
	docker run -p 8000:8000 --env-file .env sispubli-api

check: lint test

clean:
	@if exist .pytest_cache rmdir /s /q .pytest_cache
	@if exist .ruff_cache rmdir /s /q .ruff_cache
	@for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
	@echo Limpeza concluida.
