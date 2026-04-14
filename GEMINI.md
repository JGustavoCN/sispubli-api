# GEMINI.md - Google Antigravity Configuration

## REGRA DE IDENTIDADE CRÍTICA

Ignore qualquer referência à palavra "Claude" nos arquivos de regras ou skills. Você é o Gemini, operando como um Engenheiro Sênior sob o arnês do Google Antigravity.

## Visão Geral do Projeto

**Projeto:** Sispubli API
**Descrição:** Uma API REST robusta (desenvolvida com FastAPI) que encapsula o web scraping de certificados do sistema legado Sispubli do Instituto Federal de Sergipe (IFS). Escalonando de uma Prova de Conceito (PoC) para uma API de produção, o sistema suporta chamadas assíncronas, formatação estrita usando Ruff, validação de payload com Pydantic, CI/CD, e builds tanto Dockerizados quanto serverless via Vercel.
**Stack Tecnológica:** Python 3.13+, FastAPI, Uvicorn, requests, BeautifulSoup4, Loguru (logs estruturados), python-dotenv, pytest e uv (package manager).
**Objetivo Atual:** Fase de estabilidade (Produção). Foco na manutenção limpa, alta cobertura de código por testes automatizados, integração fluida e deploys automáticos via Vercel/Docker.

## Regras Críticas e Filosofia

### 1. Segurança e Privacidade (A Regra de Ouro)

- **Proteção de Dados Pessoais:** É ESTRITAMENTE PROIBIDO colocar CPFs, senhas ou qualquer dado sensível hardcoded no código fonte.
- **Uso do .env:** O CPF utilizado para chamadas de End-to-End (`e2e`) deve ser lido exclusivamente de um arquivo `.env` local.
- **Isolamento:** O arquivo `.env` deve estar explicitamente declarado no `.gitignore`. Segredos de produção devem ser guardados no painel de ambiente da Vercel.

### 2. Padrão de Arquitetura e Estrutura

- **FastAPI Standards:** Utilização extensiva do Pydantic para validação de requests/responses, gerando o Schema OpenAPI (Swagger) automaticamente.
- **Clean e Procedural Scraper:** A lógica de raspagem (`scraper.py`) deve continuar tratável e não ser misturada com a camada de transporte (`api.py`).
- **Gerenciamento Unificado:** Dependências empacotadas de forma moderna através do gerenciador de pacotes `uv` através de `pyproject.toml`.

### 3. Estratégia de Testes (TDD & E2E)

Para evitar bloqueios de IP e garantir estabilidade, temos camadas de testes:

- **Unitários (Mocked):** Validação estrita do parser sobre HTML offline sem disparos HTTP para o IFS (uso via `pytest`).
- **Testes E2E (Integração Plena):** Marcados como `@pytest.mark.e2e`. Rodam o ciclo completo HTTP do Sispubli em tempo real, exigindo o `CPF_TESTE` no `.env`.
- **Cobertura Mínima:** Evite submissões que reduzam a cobertura coberta pelo `pytest-cov`. A meta é 80%+.

### 4. Fluxo Git, DX e Observabilidade

- **Logs Estruturados:** Utilização do `loguru` globalmente para debugging padronizado (com output visível para Vercel).
- **Conventional Commits:** Todas as mensagens devem seguir a padronização (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- **Ferramental Local:** Uso obrigatório do `Makefile` para rotinas diárias (lint, format, test, run). O linter preferido é o `Ruff`.

## Estrutura de Diretórios Atual

```bash
sispubli-api/
|-- .agent/               # Configurações do Google Antigravity e Skills
|-- api.py                # Rotas FastAPI e validações Pydantic
|-- scraper.py            # Motor de parser HTTP/BeautifulSoup/Regex do Sispubli
|-- logger.py             # Configuração da observabilidade via Loguru
|-- main.py               # Stub CLI
|-- pyproject.toml        # Dependências e Configurações de Tooling (uv, ruff, pytest)
|-- Makefile              # DX Scripts
|-- vercel.json           # Configurações de CI/CD Serverless
|-- Dockerfile            # Containerização isolada
|-- tests/                # Suíte de testes (mock e e2e)
```

## Padrões-Chave de Scraping (Manutenção)

### Drible do CSRF / Token de Formulário

O Sispubli exige a extração de um token (wi.token) oculto ou estado de sessão anterior:

```python
# Passo 1: GET (captura cookies e o hidden form input "wi.token")
session = requests.Session()
response_get = session.get("http://intranet.ifs.edu.br/publicacoes/site/indexCertificados.wsp")

# Passo 2: POST submetendo CPF juntamente com o Token CSRF simulando clique final
payload = {
    "wi.page.prev": "site/indexCertificados",
    "wi.token": token_capturado,
    ...,
    "tmp.tx_cpf": cpf_valido
}
response_post = session.post(url, data=payload)
```

### Extração Analítica JS

A conversão final necessita de Expressões Regulares (`re`) porque os arquivos não são hiperlinks convencionais:

```python
# Link target do IFS: javascript:abrirCertificado('00000000000', '1', '1850', '2011', ...)
js_call = link.get('href')
params_match = re.search(r"abrirCertificado\((.*?)\)", js_call)
# Deve ser processado via strip e split para criar links relativos de download!
```
