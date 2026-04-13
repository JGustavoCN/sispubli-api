# Makefile para automação do Scraper Sispubli (Ambiente Windows)

# Variáveis
VENV = venv
PYTHON = $(VENV)\Scripts\python.exe
PIP = $(VENV)\Scripts\pip.exe
PYTEST = $(VENV)\Scripts\pytest.exe
BLACK = $(VENV)\Scripts\black.exe
FLAKE8 = $(VENV)\Scripts\flake8.exe

.PHONY: help setup install run test test-verbose lint format clean

# Alvo padrão: exibe o help
all: help

help:
	@echo "===================================================="
	@echo "       AUTOMAÇÃO SCRAPER SISPUBLI - COMANDOS        "
	@echo "===================================================="
	@echo "  make setup   - Cria venv e instala dependências"
	@echo "  make install - Instala/Atualiza pacotes (pip install)"
	@echo "  make run     - Executa o scraper principal"
	@echo "  make test    - Executa testes (pytest)"
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

test:
	$(PYTHON) -m pytest tests/test_scraper.py

test-v:
	$(PYTHON) -m pytest tests/test_scraper.py -v --tb=short --log-cli-level=INFO

lint:
	$(FLAKE8) scraper.py logger.py tests/test_scraper.py

format:
	$(BLACK) scraper.py logger.py tests/test_scraper.py

clean:
	@if exist .pytest_cache rmdir /s /q .pytest_cache
	@if exist .ipynb_checkpoints rmdir /s /q .ipynb_checkpoints
	@for /d /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
	@echo Limpeza concluída.
