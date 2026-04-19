# Makefile — Sispubli API
# Gerenciador: uv | Linter/Formatter: ruff | Testes: pytest + coverage

.PHONY: help install format lint lint-fix test test-v test-e2e test-tunnel update-mocks monitor \
        cov-html serve run pre-commit docker-build docker-run clean check audit docs-check \
        secrets-scan secrets-baseline

# Alvo padrão
all: help

help:
	@echo "===================================================="
	@echo "       SISPUBLI API - COMANDOS                      "
	@echo "===================================================="
	@echo "  make install      - Instala dependencias (uv sync)"
	@echo "  make format       - Formata codigo (ruff format)"
	@echo "  make lint         - Analise estatica (ruff check)"
	@echo "  make lint-fix     - Corrige erros de lint automaticamente"
	@echo "  make test         - Testes + cobertura (pytest-cov)"
	@echo "  make test-v       - Testes verbose com logs"
	@echo "  make test-tunnel  - Testes especificos do tunel de PDF"
	@echo "  make test-e2e     - Testes E2E (Mocks Offline / Cassettes)"
	@echo "  make update-mocks - Regrava cassettes HTTP (requer rede e .env)"
	@echo "  make monitor      - Health check real (Sentinela) contra o Sispubli"
	@echo "  make cov-html     - Gera relatorio de cobertura em HTML"
	@echo "  make serve        - Sobe API REST (uvicorn --reload)"
	@echo "  make run          - Executa scraper no terminal"
	@echo "  make pre-commit   - Instala hooks de pre-commit"
	@echo "  make docker-build - Build da imagem Docker"
	@echo "  make docker-run   - Roda container Docker"
	@echo "  make clean        - Limpa cache e temporarios"
	@echo "  make check        - Roda lint + test de uma vez"
	@echo "  make audit        - Auditoria LGPD (procura CPFs reais no codigo)"
	@echo "  make secrets-scan  - Procura segredos hardcoded (detect-secrets)"
	@echo "  make secrets-baseline - Gera/Atualiza o baseline de segredos"
	@echo "  make docs-check   - Verifica integridade da documentacao"
	@echo "===================================================="

install:
	uv sync

format:
	uv run ruff format src/ api.py

lint:
	uv run ruff check src/ api.py

lint-fix:
	uv run ruff check src/ api.py --fix

test:
	uv run pytest -v -m "not e2e"

test-v:
	uv run pytest -v --tb=long --log-cli-level=DEBUG

test-tunnel:
	uv run pytest tests/test_tunnel.py tests/test_tunnel_e2e.py -v

test-e2e:
	@echo "Rodando testes E2E em modo Playback (Offline)..."
	uv run pytest -v --tb=short -m e2e --no-header --record-mode=none

update-mocks:
	@echo "⚠️  REGRAVANDO CASSETTES: Isso requer CPF_TESTE e NOME_TESTE no .env ⚠️"
	uv run pytest -v -m e2e --record-mode=rewrite

monitor:
	@echo "🕵️  Sentinela: Verificando integridade real do Sispubli IFS..."
	uv run python scripts/monitor_sispubli.py

cov-html:
	uv run pytest --cov=src --cov=. --cov-report=html

serve:
	uv run uvicorn api:app --reload --host 0.0.0.0 --port 8000

run:
	uv run python scraper.py

pre-commit:
	uv run pre-commit install
	uv run pre-commit install --hook-type commit-msg
	uv run pre-commit install --hook-type pre-push
	@echo "Hooks instalados com sucesso."

docker-build:
	docker build -t sispubli-api .

docker-run:
	docker run -p 8000:8000 --env-file .env sispubli-api

check: lint-fix test audit

audit:
	@echo "Iniciando varredura LGPD em busca de CPFs..."
	uv run python scripts/audit_pii.py

secrets-scan:
	uv run detect-secrets scan --baseline .secrets.baseline

secrets-baseline:
	uv run detect-secrets scan . --exclude-files "uv.lock" > .secrets.baseline

docs-check:
	@echo "Verificando existencia de documentos obrigatorios..."
	@if not exist docs\SPEC_CONTRA_LOG_CPF.md echo [ERRO] SPEC_CONTRA_LOG_CPF.md ausente && exit 1
	@if not exist docs\API_CONTRACT.md echo [ERRO] API_CONTRACT.md ausente && exit 1
	@echo "✅ Documentacao basica OK."

clean:
	@if exist .pytest_cache rmdir /s /q .pytest_cache
	@if exist .ruff_cache rmdir /s /q .ruff_cache
	@if exist htmlcov rmdir /s /q htmlcov
	@for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
	@echo Limpeza concluida.
