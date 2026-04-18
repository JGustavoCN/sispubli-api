# Sispubli API

> **API REST de Extração de Certificados Acadêmicos do Sispubli / IFS**

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/release/python-3130/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135.3+-00a393.svg)](https://fastapi.tiangolo.com)
[![uv](https://img.shields.io/badge/uv-Package%20Manager-purple.svg)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Pytest](https://img.shields.io/badge/Tested%20with-Pytest-yellow.svg)](https://docs.pytest.org/)

Esta API permite a busca automatizada e extração de certificados armazenados no sistema acadêmico legado **Sispubli** do Instituto Federal de Sergipe (IFS). Através de uma requisição simples via HTTP, o sistema resolve nativamente os cookies, as validações de input (`wi.token`) e faz o bypass do renderizador JavaScript para entregar a lista direta em JSON.

---

## 🚀 Tecnologias e DX (Developer Experience)

O projeto foi refatorado a partir de uma PoC simples para um ecossistema pronto para produção e serverless.

- **FastAPI / Uvicorn** — Servidor web assíncrono superrápido.
- **Pydantic** — Para a validação estrita dos contratos de dados (Schemas/Swagger).
- **uv** — O package manager desenvolvido em Rust, incrivelmente rápido (`pyproject.toml`).
- **Ruff** — Linter e Formatter central usando as regras rigorosas PEP-8.
- **Loguru** — Formatação customizada para outputs profissionais no console e deploys.
- **Vercel Serverless / Docker** — Múltiplos ambientes de deployment.

---

## 🛠️ Como Iniciar Localmente

Para começar a desenvolver ou testar o projeto, você precisará do pacote `uv` instalado na máquina (`pip install uv` ou baixe via brew/curl).

### 1. Clonar e Instalar as Dependências

Não se preocupe com `virtualenv` ou `pip install`, o `uv` lidará com tudo dentro do seu cache global:

```bash
# Clone o repositório
git clone https://github.com/JGustavoCN/sispubli-api.git
cd sispubli-api

# Execute a instalação sincronizada
make install
```

### 2. Configure Suas Variáveis de Ambiente

Copie o arquivo de exemplo e preencha com seus dados locais:

```bash
cp .env.example .env
```

```ini
# .env
CPF_TESTE=74839210055   # Substitua pelo seu CPF real (apenas para testes E2E)
HASH_SALT=seu_salt_secreto_aqui
```

> [!CAUTION]
> O CPF real é necessário **apenas** para testes E2E (`make test-e2e`). Para testes unitários (`make test`) e desenvolvimento local (`make serve`), nenhum CPF real é necessário.
> **NUNCA** insira seu CPF diretamente no código-fonte. Use exclusivamente o `.env`.

### 3. Rodando o Servidor Localmente

Basta usar a cadeia do Uvicorn já abstraída:

```bash
make serve
```

A API subirá na porta 8000: `http://localhost:8000`. Teste o acesso ao `/docs` para ver o esquema Swagger.

---

## ⚙️ Scripts Disponíveis (Makefile)

O projeto foi idealizado para conter todas as complexidades encapsuladas no `Makefile`. Use o comando puramente como listado:

| Comando | Descrição Completa |
| --------- | -------------------- |
| `make install` | Sincroniza e trava as dependências limpas do ambiente com o `uv sync`. |
| `make format` | Roda o formatador Python do pacote *Ruff* de forma agressiva nos padrões. |
| `make lint` | Executa o linter *Ruff* apontando vulnerabilidades, complexidade e typehints. |
| `make test` | Roda a suíte do `pytest-cov`, mas isolada sem atingir a máquina do Sispubli. |
| `make test-v` | Mesma função do testamento, adicionando níveis de debug com o `loguru`. |
| `make test-e2e` | Ousado. Roda a API *Scraper* real. Conecta e valida o servidor upstream real. |
| `make serve` | Bota no ar o Uvicorn na sua máquina pronta com recarga on the fly. |
| `make docker-build` | Executa a compilação do `Dockerfile` criando dependências fixas do Unix. |
| `make docker-run` | Sobe o container, expondo a porta `8000` em um shell limpo. |
| `make check` | Agrega `make lint` e `make test`. Executa tudo o que as GitHub Actions fariam. |
| `make clean` | Expurga `__pycache__`, `pytest_cache`, e diretórios de relatórios temporários. |

---

## 📡 Referência Rápida da API (Endpoints)

### `GET /` (Health Check)

Garante a conectividade imediata do container e instâncias Serverless, como a Vercel.

- **Response HTTP 200**: `{"status": "API do Sispubli rodando"}`

### `GET /api/certificados/{cpf}`

Extrai os relatórios atestando o número único, título, e URLs montados de extração pro documento .wsp .

Ao requerer com dados válidos, eis o retorno esperado via Pydantic:

```json
{
  "data": {
    "usuario_id": "109*********0",
    "total": 3,
    "certificados": [
      {
         "id_unico": "hash_secreto_7020fb4532c",
         "titulo": "Monitoria da Disciplina Estrutura de Dados 2011.1",
         "url": "http://intranet.ifs.edu.br/publicacoes/download..."
      }
    ]
  }
}
```

---

## 🔒 Segurança e Blindagem PII (Zero Trust)

O projeto prioriza a segurança dos dados dos usuários (LGPD) através de uma arquitetura "Zero PII Leak":

- **Validação Matemática (Módulo 11)**: Todo CPF é validado matematicamente. Entradas inválidas retornam `422 Unprocessable Entity` imediatamente.
- **Sanitização de Mocks (VCR)**: Hooks de filtragem garantem que CPFs (em URIs, Bodies ou Headers como `Referer`) nunca sejam persistidos nos cassettes de teste.
- **Auditoria Dinâmica**: Script `make audit` integrado ao `pre-commit` que bloqueia o fluxo caso detecte segredos ou CPFs reais no repositório.
- **Anti-Enumeração**: Rate limiting agressivo na autenticação para mitigar ataques de força bruta.

---

## 📦 Implantação e Deployment (Serverless / Docker)

### Via Vercel

O projeto acompanha nativamente o config `vercel.json` o que aciona o Builder Python da Vercel (FastAPI Serverless).

Para mandar este projeto ao ar, desde que a CLI do *Vercel* esteja logada:

```bash
vercel --prod
```

### Via Containerization (Docker)

Criamos imagens superfinas baseadas no `python:3.13-slim` para hospedagem pura na AWS / Digital Ocean ou servidores corporativos on premise.

```bash
# Buildando a API sem a bagagem de desenvolvimento
make docker-build

# Rodando com Bind das variáveis secretas do desenvolvedor para porta 8000
make docker-run
```

O container contém `HEALTHCHECKS` lógicos nativos e retries contínuos, preparado para o ambiente kubernetes / docker swarm.

---

**Google Antigravity Harness Powered**
Criado como automação autônoma - Abril/2026.
