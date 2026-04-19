# 📄 Especificação Arquitetural: Políticas de Cache e Segurança (Zero Leak)

## 🎯 Objetivo

Implementar e validar as políticas estritas de `Cache-Control` para os 4 endpoints principais da API. Esta arquitetura foi desenhada para otimizar o consumo da Vercel (plano Hobby), proteger o upstream legado (Sispubli) contra *spam*, e garantir que Dados Pessoais (PII) nunca sejam cacheados em CDNs públicas.

---

## 1. Especificação dos Endpoints

### Endpoint 1: `GET /` (Health Check)

- **Objetivo:** Retornar o estado atual da API e conectividade com o upstream.
- **Política de Cache:** PROIBIDO. Diagnósticos têm de ser em tempo real.
- **Headers Exigidos:**

  ```http
  Cache-Control: no-store, no-cache, must-revalidate, max-age=0
  ```

### Endpoint 2: `POST /api/auth/token` (Auth Token)

- **Objetivo:** Gerar o token criptografado (Fernet) de sessão.
- **Política de Cache:** PROIBIDO EXTREMO. O token é único por requisição de login. Cachear isto comprometeria a segurança de todos os utilizadores.
- **Headers Exigidos:**

  ```http
  Cache-Control: no-store, no-cache, must-revalidate, max-age=0
  ```

### Endpoint 3: `GET /api/certificados` (Listar Certificados)

- **Objetivo:** Devolver a lista de certificados (JSON) associada ao token.
- **Ajustes de Código Obrigatórios:**
  - Remover totalmente o parâmetro `session` da query URL. A rota deve usar exclusivamente o header `Authorization: Bearer <token>`.
- **Política de Cache:** CACHE PRIVADO (CLIENT-SIDE).
- **Justificação:** Protege PII. O cache fica retido apenas na RAM/disco do telemóvel (App Flutter) ou navegador do utilizador. A Vercel (CDN) não armazena nada.
- **Headers Exigidos:**

  ```http
  Cache-Control: private, max-age=300, must-revalidate
  X-Content-Type-Options: nosniff
  ```

### Endpoint 4: `GET /api/pdf/{ticket}` (Tunnel Pdf)

- **Objetivo:** Fazer o streaming do ficheiro PDF imutável.
- **Política de Cache:** CACHE PÚBLICO (CDN EDGE).
- **Justificação:** PDFs são binários pesados, imutáveis e já estão protegidos pelo `ticket` criptografado na URL (Capability-URL). A Vercel deve cachear agressivamente para poupar tempo de computação.
- **Headers Exigidos:**

  ```http
  Cache-Control: public, s-maxage=86400, stale-while-revalidate=86400
  Content-Disposition: inline; filename="certificado.pdf"
  X-Content-Type-Options: nosniff
  ```

---

## 2. Implementação de Testes Automatizados (Compliance)

Para garantir que estas políticas nunca sofram regressões, deves criar um novo ficheiro de testes dedicado: `tests/test_cache_policies.py`.

Este teste fará pedidos à API e garantirá que os cabeçalhos de resposta correspondem exatamente à especificação acima.

**Tarefa para a IA:** Implementa a lógica no `api.py` conforme a Spec acima e cria o seguinte ficheiro de testes usando `pytest` e `TestClient`:

```python
# tests/test_cache_policies.py
import pytest
from fastapi.testclient import TestClient
from api import app

client = TestClient(app)

def test_cache_policy_health_check():
    response = client.get("/")
    assert response.status_code == 200
    assert "no-store" in response.headers.get("Cache-Control", "")

def test_cache_policy_auth_token():
    # Enviar um payload invalido propositadamente apenas para capturar os headers
    response = client.post("/api/auth/token", json={"cpf": "74839210055"})
    assert "no-store" in response.headers.get("Cache-Control", "")

def test_cache_policy_certificados(mocker):
    # Mock da dependencia de autenticacao para focar apenas nos headers de resposta
    mocker.patch("api.HTTPBearer", return_value="mock_token")
    mocker.patch("api.ler_token_sessao", return_value={"cpf": "74839210055", "session_hash": "abc"})
    mocker.patch("api.derivar_session_hash", return_value="abc")
    mocker.patch("scraper.fetch_all_certificates", return_value={"usuario_id": "123", "total": 0, "certificados": []})

    response = client.get("/api/certificados", headers={"Authorization": "Bearer mock_token"})

    assert response.status_code == 200
    cache_control = response.headers.get("Cache-Control", "")
    assert "private" in cache_control
    assert "max-age=300" in cache_control
    assert "s-maxage" not in cache_control # Garante que nao vai para a CDN

def test_cache_policy_pdf_tunnel(mocker):
    # Mock da descriptografia do ticket e do streaming httpx
    mocker.patch("security.descriptografar_ticket_pdf", return_value="[http://mock.url](http://mock.url)")

    # Simular uma resposta vazia do httpx apenas para capturar os headers do FastAPI
    async def mock_stream(*args, **kwargs):
        yield b"pdf_content"

    mocker.patch("api.httpx.AsyncClient.stream", return_value=mock_stream())

    response = client.get("/api/pdf/mock_ticket_string")

    cache_control = response.headers.get("Cache-Control", "")
    assert "public" in cache_control
    assert "s-maxage=86400" in cache_control
```

**Output Esperado:**

1. Altera os endpoints no `api.py`.
2. Cria o ficheiro de testes `test_cache_policies.py`.
3. Corre `pytest tests/test_cache_policies.py` e garante que os 4 testes passam.

### 💡 Porquê criar Testes Automatizados para Cache?

Os testes incluídos no *prompt* acima usam um conceito chamado **"Compliance Testing" (Testes de Conformidade)**.

No futuro, se estiveres a adicionar uma nova funcionalidade ou a atualizar a biblioteca do FastAPI e, sem querer, apagares a vírgula do `max-age=300` ou colocares um `s-maxage` onde não devias, o GitHub Actions (CI) vai gritar um erro e vai impedir o teu *commit* de ir para a Vercel. Isto dá-te uma "paz de espírito" absoluta.
