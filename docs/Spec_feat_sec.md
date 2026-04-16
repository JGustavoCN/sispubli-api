# 📘 Contrato de Arquitetura: Sispubli API (Vercel Serverless) - V5 (Produção Pragmática)

## 1. Objetivos e Trade-offs Assumidos

Este sistema opera sob a ótica de *Privacy by Design*, mitigando o vazamento de CPFs, enquanto atua como um "Proxy Limpador" e escudo de segurança para o sistema legado do Sispubli. O foco é segurança suficiente, baixo custo (Vercel Free Tier) e alta usabilidade, sem *overengineering*.

* **Regra de Ouro:** O CPF nunca deve aparecer em URLs, *query parameters* ou logs da infraestrutura. Seu trânsito ocorre exclusivamente no corpo (Body) de requisições POST, em Headers (`Authorization`) ou criptografado (AES-Fernet).
* **Trade-off de Infraestrutura (Autenticação):** Adoção de *Stateless Tokens* (Fernet) em Serverless, sem banco de dados. O risco da impossibilidade de revogação instantânea é mitigado por um Tempo de Vida (TTL) curto de 15 minutos.
* **Trade-off de Proxy Compartilhável (Link do PDF):** O ticket do PDF atuará como um "encurtador" sem TTL para permitir o compartilhamento. O risco de *Open Proxy Abuse*, viralização e esgotamento da franquia da Vercel é mitigado por limites combinados de requisição em memória (IP + Ticket) e controle de concorrência estrito.
* **Trade-off de Cache vs. Segurança (Listagem):** Headers de Autorização quebram o cache padrão da CDN. Contorna-se isso aplicando o padrão *Cache Key Derivation*, injetando um hash público na URL (isca) derivado do token + *pepper*.
* **Decisões Conscientes (Complexidades Descartadas):** As seguintes complexidades foram **explicitamente descartadas** para manter a viabilidade do MVP:
  * ❌ Rotação de `session_hash` por tempo (ex: `current_hour`), pois degrada o cache da CDN e afeta a performance.
  * ❌ Autenticação *stateful* com banco de dados (alto custo/complexidade).
  * ❌ Mecanismos de revogação de tokens (desnecessário para acesso a certificados públicos).
  * ❌ Criptografia assimétrica (*overkill* para o cenário).
  * ❌ Proteções avançadas e paranoicas de SSRF (ir além da validação rigorosa de `hostname` + `scheme`).
* **Limitação Aceita (Rate Limit em Serverless):** O Rate Limit em memória local (*in-memory*) é aceito para o MVP. Sabe-se que ele não é globalmente consistente entre múltiplas instâncias da Vercel e reseta em *cold starts*. Caso haja escala ou abuso sistêmico no futuro, a evolução oficial será a integração com **Upstash Redis** (Serverless Free Tier) para controle distribuído.

---

## 2. Contrato de Endpoints (Interface da API)

O sistema expõe estritamente 3 rotas de negócio.

### 🔐 Endpoint 1: Login / Geração de Sessão

* **Método/Rota:** `POST /api/auth/token`
* **Responsabilidade:** Receber o CPF de forma segura, gerar o token criptografado (TTL 15 min) e o hash público para cache.
* **Input (Body):** `{"cpf": "00000000000"}`
* **Output (Status 200 - JSON):** Retorna `access_token` e `session_hash`.
* **Mitigações de Segurança:**
  * Validar comprimento exato de 11 dígitos para o CPF.
  * **Rate Limit Anti-Enumeração:** Aplicar limite restrito (ex: máx. 5 requisições/minuto por IP).
  * **Hash com Pepper:** O `session_hash` DEVE ser gerado usando um segredo interno (`session_hash = sha256(token + SECRET_PEPPER)`) para impedir correlação de sessões ou ataques de dicionário via logs.

### 📄 Endpoint 2: Listagem de Certificados

* **Método/Rota:** `GET /api/certificados`
* **Responsabilidade:** Retornar a lista de certificados com URLs "mascaradas". A URL final deve ser gerada convertendo a URL original do Sispubli em um "Ticket Eterno" (sem TTL).
* **Input (Header Obrigatório):** `Authorization: Bearer <access_token>`
* **Mitigações de Segurança:**
  * Validar o TTL de 15 min do token via motor criptográfico. Retornar `401 Unauthorized` se expirado ou adulterado.
  * Emitir headers `Cache-Control: s-maxage=600` e `Vary: Authorization`.

### 📥 Endpoint 3: O Túnel de Download Seguro (Proxy Reverso)

* **Método/Rota:** `GET /api/pdf/{ticket}`
* **Responsabilidade:** Receber o ticket compartilhável, validar limites, descriptografar, executar o bypass em duas etapas no Sispubli (ignorando o frameset legado) e repassar o arquivo bruto via streaming.
* **Mecânica Exigida (O Bypass):**
  * **Etapa A:** Abrir sessão HTTP persistente com o cliente (`httpx.AsyncClient`).
  * **Etapa B:** Fazer um GET na URL 1 (descriptografada) para forçar a geração no servidor legado. Ignorar o HTML de resposta.
  * **Etapa C:** Fazer um GET na URL 2 (`ReportConnector.wsp?tmp.reportShow=true`) usando a mesma sessão para capturar os bytes do PDF.
* **As 7 Camadas de Defesa (Implementação Obrigatória):**
  * **Defesa 1: Validação de Tamanho do Ticket:** Rejeitar imediatamente tickets maiores que 500 caracteres (`if len(ticket) > 500: raise 400`). Impede consumo de memória malicioso.
  * **Defesa 2: Resolução de IP Real:** O identificador de IP para o Rate Limit DEVE ler os headers da Vercel (`x-forwarded-for` ou `x-real-ip`) antes de fazer *fallback* para `request.client.host`.
  * **Defesa 3: Rate Limit por IP (Anti-Bot):** Implementar *sliding window* em memória local com hash de IP. Retornar `429` após limite atingido (ex: 20 req/min).
  * **Defesa 4: Rate Limit por Ticket (Anti-Viral):** Criar uma limitação focada no documento (ex: 100 requisições por hora por ticket). Protege contra *scraping* massivo ou viralização no Twitter sem impedir o compartilhamento comum do usuário.
  * **Defesa 5: Controle de Concorrência (Anti-Sobrecarga):** Envolver as requisições `httpx` em um `asyncio.Semaphore(10)` para impedir que picos de acesso travem a *serverless function* ou derrubem a infraestrutura da faculdade.
  * **Defesa 6: Timeout e Isolamento de Headers:** Configurar `httpx.AsyncClient(timeout=10)`. Substituir integralmente os headers originais do cliente por um `User-Agent` genérico. Nunca repassar `Referer` ou `Cookies` do usuário para o Sispubli.
  * **Defesa 7: Validação SSRF Pragmática:** Descriptografar o ticket e validar via `urlparse` com regra estrita. Bloqueia bypasses clássicos (ex: `.evil.com` ou `@evil.com`).

        ```python
        if parsed.scheme not in ["http", "https"]: reject()
        if parsed.hostname != "intranet.ifs.edu.br": reject()
        ```

* **Apresentação Final:** Injetar os headers `Cache-Control: no-store, no-cache` e `Content-Disposition: inline; filename="certificado.pdf"` na resposta de *Streaming*.

---

## 3. Roteiro de Implementação TDD (Red-Green-Refactor)

* **Fase 1: Motor de Criptografia (`security.py`)**
  * Escrever testes para `gerar_token_sessao`/`ler_token_sessao` provando bloqueio após TTL.
  * Escrever testes provando que `gerar_ticket_pdf`/`ler_ticket_pdf` ignora a ausência de TTL.
  * Escrever testes para a derivação do hash exigindo a presença do `SECRET_PEPPER`.

* **Fase 2: Motor de Rate Limit e Concorrência (`rate_limit.py`)**
  * Criar testes de extração de IP garantindo que a string de `x-forwarded-for` (mesmo quando vier em formato de lista separada por vírgula) seja capturada corretamente.
  * Testar bloqueio HTTP 429 simulando limites excedidos na janela de IP.
  * Testar bloqueio HTTP 429 simulando limites excedidos no escopo do Ticket (Ex: 101 requisições no mesmo ticket).

* **Fase 3: Rota de Autenticação (`api.py`)**
  * Testes validando rejeição de CPFs com letras, CPFs com menos ou mais de 11 caracteres e requisições não-POST.

* **Fase 4: Rota de Listagem (`api.py` e `scraper.py`)**
  * Testes verificando o comportamento da API na ausência do Header `Authorization` (deve ser 401).
  * Confirmar se a geração da resposta JSON contém os certificados apontando estritamente para o túnel `/api/pdf/`.

* **Fase 5: O Túnel de Download Seguro (`api.py`)**
  * **Teste Crítico SSRF:** Passar tickets forjados apontando para `http://intranet.ifs.edu.br.meusite.com` e `ftp://intranet.ifs.edu.br`. Ambos DEVEM retornar erro.
  * **Teste Crítico Tamanho:** Enviar uma string aleatória de 600+ caracteres no parâmetro `{ticket}` e garantir rejeição imediata.
  * Implementar a lógica com `asyncio.Semaphore` e garantir via logs (durante o teste) que a camada HTTPx não vazou o header `Referer` original.

* **validação de estrutura do token antes de decrypt**

  * **Hoje você faz:**

```python
    fernet.decrypt(token)
```

* **Problema - Payload malicioso:**

```python
    token = "A"*10000
```

* **pode causar:**

```python
overhead de CPU
exceções repetidas
micro-DoS
```

* **Solução simples:**

```python
if len(token) > 500:
    raise HTTPException(400, "Invalid token")
```
