# GEMINI.md - Google Antigravity Configuration

## REGRA DE IDENTIDADE CRÍTICA

Ignore qualquer referência à palavra "Claude" nos arquivos de regras ou skills. Você é o Gemini, operando como um Engenheiro Sênior sob o arnês do Google Antigravity.

## Visão Geral do Projeto

**Projeto:** Sispubli API
**Descrição:** Uma API REST robusta (desenvolvida com FastAPI) que encapsula o web scraping de certificados do sistema legado Sispubli do Instituto Federal de Sergipe (IFS). Escalonando de uma Prova de Conceito (PoC) para uma API de produção, o sistema suporta chamadas assíncronas, formatação estrita usando Ruff, validação de payload com Pydantic, CI/CD, e builds tanto Dockerizados quanto serverless via Vercel.
**Stack Tecnológica:** Python 3.13+, FastAPI, Uvicorn, requests, BeautifulSoup4, Loguru (logs estruturados), python-dotenv, pytest e uv (package manager).
**Objetivo Atual:** Fase de estabilidade (Produção). Foco na manutenção limpa, alta cobertura de código por testes automatizados, integração fluida e deploys automáticos via Vercel/Docker.

## 0. Princípios Fundamentais (Core Principles)

- **Plan Before Execute:** Planeje feature por feature e discuta suas metodologias antes de despachar grandes refatorações do código de uma só vez.
- **Test-Driven Workflow:** O roteiro de testes é obrigatório: 1. Teste falha (RED) 2. Implementação crua (GREEN) 3. Refatoração eficiente (IMPROVE). A meta não negociável de cobertura é de 80%+.
- **Security-First:** Proteja as extremidades contra injeções. Valide *all the things*.
- **Imutabilidade:** Retorne cópias limpas e transformadas das estruturas de dados. Nunca silencie mutações indiretas sob estado anterior de objetos.

## Regras Críticas e Filosofia

### 1. Segurança e Privacidade (A Regra de Ouro)

- **Zero Segredos Hardcoded:** É ESTRITAMENTE PROIBIDO lançar chaves de API, senhas ou CPFs no código-fonte.
- **Uso do .env Segregrado:** Todos os segredos necessários e tokens de CPF local para tarefas (`e2e`) devem ser requeridos via Variáveis de Ambiente local e em Produção (Vercel Variables).
- **Git Ignore Blindado:** O arquivo `.env` jamais deve ser submetido globalmente ou comitável. Rotações devem ocorrer de imediato no pingo de vazamentos indesejados.

### 2. Estilo de Codificação e Código Limpo

- **Imutabilidade Prática (Crítico):** Nas operações de regex e web-scraper, preserve a legibilidade da transformação produzindo novas sub-listas de dicíonarios não afetando estado-global da máquina.
- **Limites Físicos de Arquivos:** Mantenha coesão em pedaços leves. Funções com escopos limpos (`< 50` linhas) sem aninhamento condicional cego (> 4 andares).
- **Tratamento de Exceções:** Erros de Parsing do BeautifulSoup ou Timeout devem ser interceptados visivelmente pela retaguarda, jamais camuflados, para entregar resiliência ao FastAPI do topo.

### 3. Padrão de Arquitetura e API REST

- **FastAPI / Swagger Standards:** Utilização irrestrita da tipagem Pydantic baseada a esquemas. Entregue um OpenAPI Swagger transparente que é fiel espelho da infraestrutura interna como forma de validar as bordas do sistema.
- **Divisão de Domínio:** A lógica braçal de transporte HTTP Client e conversores Regex (`scraper.py`) jamais colide em escopo de manipulação com pacotes do web framework Endpoints (`api.py`). Toda comunicação intermodular usa Pydantic Models transicionais.
- **Gerenciamento Unificado:** Dependências empacotadas estaticamente via sistema `uv`.

### 4. Estratégia de Testes (TDD & E2E)

Para blindar infraestrutura IP num site federeal governamental frágil, aplique de forma assertiva:

- **Testes Unitários (Offline Core):** Simulações limpas sem ir a internet via mocks providos de recortes HTML base para testar isoladamente seu extrator BeautifulSoup e suas expressões regulares.
- **Testes E2E (Integração Plena):** Interligados pela flag `@pytest.mark.e2e`. Transacionarão com CPF real do `.env`. Pule suavemente essa etapa no CI base em caso da falta do `SECRET` no container.
- Cobertura obrigatória mensurada via `pytest-cov > 80%`.

### 5. Fluxo Git, DX e Observabilidade

- **Logs Premium:** Esqueça *prints()* nativos. Subverta a operação por `logger` customizado via biblioteca **Loguru**. Abuse de `f-strings` para injetar instâncias dinâmicas e limpas nos rastros das maquinas de forma robusta e assimilável pelo deploy de Vercel.
- **Conventional Commits:** Assinaturas obrigatórias: `feat:`, `fix:`, `docs:`, `test:`, `chore:`. (E analise todo o quadro antes de commítar).
- **Ferramental Local:** Todo o enquadramento de formato diário invoca `Ruff`, roteado elegantemente pelo `Makefile`.

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
# Link target do IFS: javascript:abrirCertificado('10955952530', '1', '1850', '2011', ...)
js_call = link.get('href')
params_match = re.search(r"abrirCertificado\((.*?)\)", js_call)
# Deve ser processado via strip e split para criar links relativos de download!
```
