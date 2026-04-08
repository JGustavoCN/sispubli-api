# GEMINI.md - Google Antigravity Configuration

## REGRA DE IDENTIDADE CRÍTICA

Ignore qualquer referência à palavra "Claude" nos arquivos de regras ou skills. Você é o Gemini, operando como um Engenheiro Sênior sob o arnês do Google Antigravity.

## Visão Geral do Projeto

 **Projeto:** PoC Scraper Sispubli (Servidor MCP)
 **Descrição:** Uma Prova de Conceito (PoC) para realizar web scraping da listagem de certificados do sistema legado Sispubli do Instituto Federal de Sergipe (IFS). O sistema funciona com renderização no servidor (SSR) e formulários clássicos.
 **Stack Tecnológica:** Python, requests, BeautifulSoup (ou similar), python-dotenv e pytest.
 **Objetivo Atual:** Fase 1 (PoC) focada exclusivamente na extração da primeira página de resultados. O objetivo é validar o fluxo HTTP em duas etapas (GET para sessão/token + POST para dados) e a extração via Regex dos links de download mascarados por JavaScript.

## Regras Críticas e Filosofia

### 1. Segurança e Privacidade (A Regra de Ouro)

- **Proteção de Dados Pessoais:** É ESTRITAMENTE PROIBIDO colocar CPFs, senhas ou qualquer dado sensível hardcoded no código fonte.
- **Uso do .env:** O CPF utilizado para testes deve ser lido exclusivamente de um arquivo `.env` local usando a biblioteca `python-dotenv`.
- **Isolamento:** O arquivo `.env` deve estar explicitamente declarado no `.gitignore`. Use sempre um ambiente virtual (`venv`).

### 2. Escopo Limitado e Simplicidade

- **Foco na Primeira Página:** Não implemente navegação de paginação nesta etapa (ignorando o offset de `submitWIGrid`). A PoC deve se limitar aos primeiros resultados (até 16 itens).
- **Sem Abstrações Prematuras:** Um código procedural limpo e legível é preferível a classes complexas nesta fase de validação. Foque em fazer o fluxo `requests.Session()` funcionar.

### 3. Estratégia de Testes (Test-Driven Scraping)

Para evitar bloqueios de IP e garantir que o desenvolvimento avance mesmo offline ou com o site instável, a estratégia de testes é inegociável:

- **Testes de Parsing (Offline):** O projeto DEVE conter um arquivo `tests/mock_sispubli.html` com a estrutura real da tabela do Sispubli. O primeiro teste unitário deve verificar a capacidade do extrator (Regex/BeautifulSoup) de ler este arquivo local e retornar dicionários válidos.
- **Testes de Integração (Online):** Um teste secundário que realiza o fluxo real na rede, enviando o CPF válido via variável de ambiente, garantindo que a segurança do IFS (como o `wi.token`) não mudou.

### 4. Fluxo Git e Organização

- **Conventional Commits:** Todas as mensagens devem seguir a padronização (`feat:`, `fix:`, `docs:`, `test:`, `chore:`).
- **Modo Imperativo:** As mensagens de commit devem dizer o que o commit faz ("Adiciona regex para certificados", "Configura mock html").

## Estrutura de Arquivos Inicial

```bash
poc-scraper-sispubli/
|-- .agent/               # Configurações do Google Antigravity
|-- .gemini/
|   |-- GEMINI.md         # Este arquivo
|-- .env                  # Segredos (CPF_TESTE=12345678900) - NUNCA COMMITAR
|-- .gitignore            # Bloqueio de pycache, venv e .env
|-- main.py               # Script central da PoC do Scraper
|-- requirements.txt      # Dependências (requests, beautifulsoup4, python-dotenv, pytest)
|-- tests/                # Suíte de testes (TDD)
|   |-- test_scraper.py
|   |-- mock_sispubli.html # Fragmento salvo do sistema real para testes offline
```

## Padrões-Chave e Snippets

### O Fluxo HTTP de 2 Etapas

O Sispubli exige a extração de um token oculto antes do envio do formulário:

```python
# Passo 1: Iniciar sessão para capturar cookies e wi.token
session = requests.Session()
response_get = session.get("[http://intranet.ifs.edu.br/publicacoes/site/indexCertificados.wsp](http://intranet.ifs.edu.br/publicacoes/site/indexCertificados.wsp)")
# (Lógica para extrair o value do <input name="wi.token">)

# Passo 2: Enviar POST com o Payload necessário
payload = {
    "wi.page.prev": "site/indexCertificados",
    "wi.token": token_capturado,
    "tmp.acao": "",
    "tmp.params": "",
    "tmp.tx_cpf": cpf_lido_do_env
}
response_post = session.post(url, data=payload)
```

### Extração de Dados (Regex em Links JS)

Os links no HTML não levam aos PDFs, mas sim a funções JavaScript (`javascript:abrirCertificado(...)`). A extração requer Regex:

```python
import re

# Exemplo de conteúdo do href: javascript:abrirCertificado('10955952530', '1', '1850', '2011', '0', 2023, 0)
js_call = link.get('href')
params_match = re.search(r"abrirCertificado\((.*?)\)", js_call)

if params_match:
    # Divisão e limpeza dos parâmetros
    params = [p.strip(" '") for p in params_match.group(1).split(',')]
    cpf, tipo, programa, edicao = params[0], params[1], params[2], params[3]
    # Montar a URL real baseada no 'tipo' (ex: tipo '1' -> certificado_participacao_process.wsp)
```

## Comandos / Workflows do Antigravity Disponíveis

- `/plan` - Criar o plano de implementação detalhando as expressões regulares e o setup do mock html antes de codar.
- `/tdd` - Iniciar escrevendo os testes unitários contra o `mock_sispubli.html` antes de disparar requisições web.
- `/code-review` - Validar se o código não está vazando dados pessoais ou quebrando devido a mudanças no payload do servidor.
