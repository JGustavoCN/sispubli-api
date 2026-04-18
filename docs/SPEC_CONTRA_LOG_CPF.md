# 📄 Especificação Técnica: Mitigação de Vazamento de PII (Zero CPF Leak) - V2 (Definitiva)

## 🎯 Objetivo

Garantir total conformidade com a LGPD implementando uma arquitetura de "Zero Leak" resiliente e rastreável. O sistema deve impedir proativamente que CPFs completos (11 dígitos) sejam registrados no `stdout`, em arquivos de log, painéis de infraestrutura (Vercel) ou em tracebacks de erro.

**Decisão de Arquitetura (Trade-offs aplicados):** 1. Manteremos os logs do `httpx` no nível `INFO` para garantir a observabilidade do sistema, mas mascarando os dados sensíveis via Interceptor/Regex.
2. Usaremos mascaramento parcial (exibindo os 3 primeiros dígitos) para permitir o debug e suporte ao usuário sem comprometer a LGPD.
3. Desativaremos diagnósticos locais do Loguru que poderiam vazar variáveis do ambiente em caso de falhas críticas.

---

## 🛡️ Ameaças Mitigadas (Threat Model)

1. **Vazamento via Bibliotecas de Rede (HTTPX):** O `httpx` loga URLs completas. A API legada exige o CPF como query parameter (`?tmp.tx_cpf=74839210055`), o que vazaria na Vercel.
2. **Vazamento via Tracebacks e Variáveis Locais:** Erros de rede (`str(e)`) frequentemente expõem a URL. Além disso, falhas críticas (crash) no Loguru com `diagnose=True` expõem o conteúdo exato das variáveis locais (como a variável `cpf`).
3. **Crash do Sistema de Logs (Type Error):** Tentativas de rodar expressões regulares em objetos não-string dentro dos metadados extras de log.
4. **Fator Humano (Debug Prints):** Uso acidental de `print(url)` ou `print(cpf)` durante o desenvolvimento.

---

## 🛠️ Plano de Implementação (Ações Requeridas)

A IA deve modificar os seguintes arquivos para implementar a solução:

### Tarefa 1: Camada 1 e 2 - Patcher Resiliente e Interceptor (Arquivo: `logger.py`)

**Objetivo:** Substituir o log padrão e criar o middleware de censura parcial seguro.

1. **Configurações Globais:**
   - **Mocks obrigatórios**: Usar `74839210055` em toda documentação e testes offline.
   - **Limite Dinâmico**: O tamanho máximo de tickets/tokens é **2048 caracteres**.
   - **Proteção de Integridade**: O campo `id_unico` (SHA-256) é ignorado pela regex de sanitização.

1. **Expressão Regular de Mascaramento Parcial:**
   Adicionar a regex focada em 11 dígitos, capturando os 3 primeiros para rastreabilidade:
   `CPF_PATTERN = re.compile(r'(?<!\d)(\d{3})\d{8}(?!\d)')`
2. **Criar o Sanitizador Seguro (Loguru Patcher):**
   Criar a função `sanitizador_lgpd(record)` aplicando `.sub(r"\g<1>********", string)`:
   - Validar estritamente o tipo da mensagem: `if isinstance(record["message"], str):`
   - Validar estritamente os campos extras: iterar sobre `record["extra"].items()` e aplicar o `re.sub` apenas `if isinstance(value, str):`.
   - Aplicar globalmente via `logger = logger.patch(sanitizador_lgpd)`.
3. **Ajustar a Configuração do SINK (Loguru):**
   Nas chamadas `logger.add()`, garantir que **`diagnose=False`** esteja configurado explicitamente tanto para produção quanto para desenvolvimento. Isso impede que o Loguru imprima o valor das variáveis sensíveis da stack trace durante um crash.
4. **Criar o Interceptor Handler (Sem silenciamento):**
   Criar a classe `InterceptHandler(logging.Handler)` que capture os logs do módulo `logging` padrão e os envie para o Loguru.
   Criar a função `aplicar_interceptor()` que defina o `InterceptHandler` como raiz para todos os loggers em `logging.root.manager.loggerDict.keys()`.
   *(Importante: NÃO redefinir o nível de log do `httpx` para `WARNING`. Manter no padrão para não perder a observabilidade das requisições).*

### Tarefa 2: Aplicação do Interceptor e Blindagem de Exceções (Arquivo: `api.py`)

**Objetivo:** Ativar o sistema de segurança e limpar strings de erro.

1. **Ativar o Interceptor:**
   No início do bloco `@asynccontextmanager async def lifespan(app: FastAPI):`, importar e chamar a função `aplicar_interceptor()` do `logger.py`.
2. **Sanitizar Tracebacks no Túnel de PDF:**
   Localizar a rota `tunnel_pdf` e o bloco `except Exception as e:` final.
   - **Ação:** Antes de logar, aplicar a regex de limpeza na string do erro convertendo os últimos 8 dígitos em asteriscos.
   - Exemplo: `safe_error_msg = re.sub(r'(?<!\d)(\d{3})\d{8}(?!\d)', r'\g<1>********', str(e))`
   - Atualizar o log para: `log.error(f"💥 [TUNEL CRASH] Erro inesperado no motor: {safe_error_msg}")`.

### Tarefa 3: Camada 3 - Shift-Left / Trava de Build (Arquivo: `pyproject.toml`)

**Objetivo:** Impedir o commit/deploy de código contendo `print()`.

1. Localizar a configuração do linter (Ruff) na seção `[tool.ruff.lint]`.
2. Adicionar a regra `T201` (flake8-print) à lista de regras selecionadas.
   - **Ação:** Modificar adicionando `"T201"` no array `select` (ex: `select = ["E", "F", "T201", ...]`).

### Tarefa 4: Malha de Validação e Testes de Segurança (Zero Leak Testing)

**Objetivo:** Criar testes automatizados e regras de CI/CD que garantam que a proteção de LGPD nunca sofra regressão no futuro.

A IA deve criar ou atualizar os arquivos de teste correspondentes e o pipeline de CI/CD conforme detalhado abaixo:

#### 4.1. Testes Unitários do Sanitizador (Arquivo: `tests/test_logger.py`)

Criar uma suíte de testes dedicada (`test_logger.py`) para validar o comportamento da função `sanitizador_lgpd` e da Regex `CPF_PATTERN`.

- **Cenário 1 (Sucesso):** Simular um log contendo um CPF de 11 dígitos e afirmar (assert) que a saída contém apenas os 3 primeiros dígitos seguidos de asteriscos (`123********`).
- **Cenário 2 (Edge Cases - Falso Positivos):** Simular logs com números de 10 dígitos, 12 dígitos, e números formatados (`123.456.789-00`). O sanitizador **não deve** mascarar esses valores (a regra foca apenas nos 11 dígitos puros do Sispubli).
- **Cenário 3 (Resiliência de Tipagem):** Passar um dicionário, uma lista e um número inteiro no campo `extra` (metadados do log). O teste deve passar sem levantar exceções (`TypeError`), validando a proteção `isinstance(value, str)`.
- **Cenário 4 (Crash Fatal/Diagnóstico):** Simular uma exceção não tratada e capturar o log para garantir que as variáveis de escopo local (que poderiam conter o CPF) não estão presentes no Traceback (validando o `diagnose=False`).

#### 4.2. Testes de Integração de Interceptação e Túnel (Arquivos: `tests/test_logger.py` e `tests/test_tunnel.py`)

- **Ação em `test_logger.py`:** Forçar uma emissão de log utilizando a biblioteca padrão do Python (`logging.getLogger("httpx").info("URL: ?tmp.tx_cpf=74839210055")`). Validar se o log final capturado contém a versão mascarada, provando que o `InterceptHandler` funciona.
- **Ação em `test_tunnel.py`:** Criar um mock da chamada `httpx.AsyncClient.get` (gatilho ou captura) para que ela lance um erro contendo o CPF na mensagem da exceção. Validar se a resposta JSON e o log do erro não contêm o CPF literal, provando que a variável `safe_error_msg` está limpando a string antes do envio.

#### 4.3. Teste de Vazamento em Response/Payload (Arquivo: `tests/test_api.py`)

- **Ação:** Fazer uma requisição `GET /api/certificados/{cpf}` simulando que o `scraper.py` ou o Sispubli upstream devolveu uma mensagem de erro que acidentalmente incluiu o CPF enviado (ex: `"Erro ao buscar pagina para o cpf 74839210055"`).
- **Critério:** O JSON de erro devolvido (HTTP 502/500) **não deve** conter o CPF numérico completo no campo `message`, validando a higiene do payload para o front-end.

#### 4.4. A "Rede de Arrastão" no Pipeline de CI/CD (Arquivo: `.github/workflows/ci.yml`)

**Objetivo:** Garantir uma varredura de força bruta em todos os logs gerados durante os testes do GitHub Actions.

1. Localizar a etapa (step) onde o `pytest` é executado no `ci.yml`.
2. Alterar a execução do pytest para jogar toda a saída do terminal (stdout e stderr) em um arquivo de texto. Exemplo: `pytest > test_execution.log 2>&1` (ou ferramenta similar que permita preservar o log e o exit code).
3. **Adicionar um novo Step (Auditoria LGPD):** Adicionar um comando `grep` logo após os testes.
   - O `grep` deve procurar pelas variáveis de ambiente do CPF de teste (ex: `CPF_TESTE` presente no `.env.example` ou Secrets) dentro do arquivo `test_execution.log`.
   - **Critério de Falha:** Se o `grep` encontrar a sequência exata de 11 dígitos do CPF de teste no arquivo de logs, o step deve falhar (`exit 1`) e quebrar o build, indicando que ocorreu um vazamento de dados durante a execução. Se não encontrar (exit code 1 do grep), o script deve considerar como sucesso (`exit 0`).

---

## ✅ Critérios de Aceite (Como a IA deve validar o sucesso)

1. **Observabilidade Segura:** O `httpx` continua a registrar requisições de sucesso (`INFO`), mas as URLs que contêm CPF aparecerão mascaradas mantendo apenas os 3 primeiros dígitos (ex: `?tmp.tx_cpf=109********`).
2. **Resiliência:** O uso de `log.info("Teste", extra={"user": 123})` não causa crash na aplicação (a tipagem previne que a Regex tente atuar sobre o inteiro `123`).
3. **Privacidade no Crash:** Falhas não tratadas na aplicação mostrarão a linha do erro no console, mas não as variáveis (`diagnose=False`).
4. **Qualidade de Código:** O projeto falhará na etapa do linter (Ruff) caso algum arquivo contenha o comando `print()`.

---
**Nota para a IA Agente:** Implemente estas alterações mantendo o estilo de código existente, incluindo tipagem estática do Python e docstrings. Modifique `logger.py`, seguido de `api.py` e finalize com `pyproject.toml`.
