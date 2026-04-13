# Makefile para automação do Scraper Sispubli (Ambiente Windows)

# Variáveis
VENV = venv
PYTHON = $(VENV)\Scripts\python.exe
PIP = $(VENV)\Scripts\pip.exe
PYTEST = $(VENV)\Scripts\pytest.exe
BLACK = $(VENV)\Scripts\black.exe
FLAKE8 = $(VENV)\Scripts\flake8.exe

.PHONY: help setup install run serve test test-v lint format clean

# Alvo padrão: exibe o help
all: help

help:
	@echo "===================================================="
	@echo "       AUTOMAÇÃO SCRAPER SISPUBLI - COMANDOS        "
	@echo "===================================================="
	@echo "  make setup   - Cria venv e instala dependências"
	@echo "  make install - Instala/Atualiza pacotes (pip install)"
	@echo "  make run     - Executa o scraper principal"
	@echo "  make serve   - Sobe a API REST (uvicorn)"
	@echo "  make test    - Executa todos os testes (pytest)"
	@echo "  make test-v  - Testes verbose com logs (pytest -v)"
	@echo "  make lint    - Analise estatica de codigo (flake8)"
	@echo "  make format  - Formatacao automatica (black)"
	@echo "  make clean   - Limpa cache e arquivos temporarios"
	@echo "===================================================="

setup:
	python -m venv $(VENV)
	$(PIP) install -r requirements.txt

install:
	$(PIP) install -r requirements.txt

run:
	$(PYTHON) scraper.py

serve:
	$(PYTHON) -m uvicorn api:app --reload --host 0.0.0.0 --port 8000

test:
	$(PYTHON) -m pytest tests/ -v --tb=short

test-v:
	$(PYTHON) -m pytest tests/ -v --tb=short --log-cli-level=INFO

lint:
	$(FLAKE8) scraper.py api.py logger.py tests/

format:
	$(BLACK) scraper.py api.py logger.py tests/

clean:
	@if exist .pytest_cache rmdir /s /q .pytest_cache
	@if exist .ipynb_checkpoints rmdir /s /q .ipynb_checkpoints
	@for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
	@echo Limpeza concluída.
