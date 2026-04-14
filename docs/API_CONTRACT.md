# Sispubli API — Contrato e Documentação

> **API REST de Extração de Certificados Acadêmicos**
> Instituto Federal de Sergipe (IFS) — Sistema Sispubli

---

## Sumário

- [Visão Geral](#visão-geral)
- [Base URL](#base-url)
- [Endpoints](#endpoints)
  - [Health Check](#get-)
  - [Buscar Certificados](#get-apicertificadoscpf)
- [Fluxo do CPF (Ciclo de Vida Seguro)](#fluxo-do-cpf-ciclo-de-vida-seguro)
- [Regras de Segurança (LGPD)](#regras-de-segurança-lgpd)
- [Padrão URL Template](#padrão-url-template)
- [Códigos de Erro](#códigos-de-erro)
- [Tipos de Certificado](#tipos-de-certificado)
- [Exemplos de Uso](#exemplos-de-uso)

---

## Visão Geral

A Sispubli API é um gateway REST que abstrai o sistema legado de certificados do IFS (Sispubli). Ela realiza web scraping automatizado com tratamento de CSRF tokens, paginação e sessões, entregando os resultados em JSON padronizado.

**Características principais:**
- Nenhuma autenticação é necessária (o sistema Sispubli é público)
- O CPF é o único dado pessoal manipulado
- Conformidade LGPD: CPF **nunca** aparece em texto claro nas respostas
- Cache em memória (`lru_cache`) para evitar requisições repetidas

---

## Base URL

| Ambiente       | URL                                          |
| -------------- | -------------------------------------------- |
| Local          | `http://localhost:8000`                      |
| Produção       | Configurável (Vercel / Docker)               |
| Documentação   | `{BASE_URL}/docs` (Swagger UI automático)    |

---

## Endpoints

### `GET /`

**Health Check** — Verifica se a API está no ar.

**Resposta `200 OK`:**
```json
{
  "status": "API do Sispubli rodando"
}
```

---

### `GET /api/certificados/{cpf}`

**Busca todos os certificados disponíveis para um CPF.**

#### Parâmetros

| Parâmetro | Tipo     | Local | Obrigatório | Descrição                              |
| --------- | -------- | ----- | ----------- | -------------------------------------- |
| `cpf`     | `string` | Path  | ✅ Sim       | CPF do titular (apenas números, 11 dígitos) |

#### Validação

O CPF é validado antes de qualquer processamento:

```
1. cpf.isdigit() → deve conter apenas números
2. len(cpf) == 11 → exatamente 11 caracteres
```

> **Nota:** Validação de dígitos verificadores do CPF (módulo 11) **não é feita** — o sistema Sispubli aceita qualquer sequência de 11 dígitos e simplesmente retorna uma lista vazia se não houver certificados.

#### Resposta de Sucesso `200 OK`

```json
{
  "data": {
    "usuario_id": "***.456.789-**",
    "total": 2,
    "certificados": [
      {
        "id_unico": "a3f8c2d1e4b7091f6e2a5d8c3b1f4e7a9d2c5b8e1f4a7c0d3b6e9f2a5c8b1e4",
        "titulo": "Participacao no(a) SEPEX 2023",
        "url_download": "http://intranet.ifs.edu.br/publicacoes/relat/certificado_participacao_process.wsp?tmp.tx_cpf={cpf}&tmp.id_programa=1850&tmp.id_edicao=2011",
        "ano": 2023,
        "tipo_codigo": 1,
        "tipo_descricao": "Participacao"
      },
      {
        "id_unico": "b7c2e8f4a1d3096e5f2a8d7c4b1e3f6a0d9c2b5e8f1a4c7d0b3e6f9a2c5b8e1",
        "titulo": "Participacao no(a) SNCT 2021",
        "url_download": "http://intranet.ifs.edu.br/publicacoes/relat/certificado_participacao_process.wsp?tmp.tx_cpf={cpf}&tmp.id_programa=6&tmp.id_edicao=1472",
        "ano": 2021,
        "tipo_codigo": 1,
        "tipo_descricao": "Participacao"
      }
    ]
  }
}
```

#### Campos do Certificado

| Campo            | Tipo        | Descrição                                                                 |
| ---------------- | ----------- | ------------------------------------------------------------------------- |
| `id_unico`       | `string`    | Hash SHA-256 (64 chars hex) gerado com SALT secreto. Identificador LGPD. |
| `titulo`         | `string`    | Título do evento conforme registrado no Sispubli.                        |
| `url_download`   | `string?`   | URL Template para download. Contém `{cpf}` como placeholder.             |
| `ano`            | `int`       | Ano de realização do evento.                                              |
| `tipo_codigo`    | `int`       | Código numérico do tipo (1-11).                                           |
| `tipo_descricao` | `string`    | Descrição legível do tipo de certificado.                                 |

---

## Fluxo do CPF (Ciclo de Vida Seguro)

O diagrama abaixo ilustra **exatamente onde** o CPF do titular é utilizado em cada etapa do processamento:

```
Cliente (Flutter / MCP / curl)
│
│  GET /api/certificados/{cpf}
│  ← CPF viaja na URL (HTTPS criptografado)
│
▼
┌─────────────────────────────────────────────────────────┐
│  api.py — Camada de Validação                           │
│                                                         │
│  1. Valida: cpf.isdigit() AND len(cpf) == 11            │
│  2. Log: "Requisicao recebida: GET .../cpf[:3]***"      │
│     └─ Apenas os 3 primeiros dígitos são logados        │
│  3. Chama: fetch_all_certificates(cpf)                  │
│     └─ lru_cache: se mesmo CPF, retorna do cache        │
└─────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────┐
│  scraper.py — Motor de Extração                         │
│                                                         │
│  [PASSO 1] GET → Sispubli (CSRF)                        │
│     └─ Captura: wi.token + cookies de sessão            │
│     └─ CPF NÃO é enviado neste passo                    │
│                                                         │
│  [PASSO 2] POST → Sispubli                              │
│     └─ Payload: { "tmp.tx_cpf": cpf }  ← CPF real      │
│     └─ Conexão: HTTP (rede interna IFS)                 │
│     └─ Log: mask_cpf(cpf) → "***.456.789-**"            │
│                                                         │
│  [LOOP] Para cada certificado extraído do HTML:         │
│     ├─ id_unico = SHA256(HASH_SALT + cpf + tipo +       │
│     │                     programa + edicao)             │
│     │   └─ CPF hasheado — irreversível com SALT         │
│     │                                                   │
│     ├─ url_download = "...?tmp.tx_cpf={cpf}&..."        │
│     │   └─ {cpf} literal (placeholder, NÃO o CPF real)  │
│     │                                                   │
│     ├─ titulo, ano, tipo_codigo, tipo_descricao         │
│     │   └─ Metadata pura — sem dados pessoais           │
│     │                                                   │
│     └─ CPF NUNCA entra no objeto de retorno em          │
│        texto claro                                      │
└─────────────────────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────────────────┐
│  Resposta JSON Final                                    │
│                                                         │
│  {                                                      │
│    "data": {                                            │
│      "usuario_id": "***.456.789-**",  ← mascarado       │
│      "total": 16,                                       │
│      "certificados": [{                                 │
│        "id_unico": "sha256...",       ← hash LGPD       │
│        "url_download": "...{cpf}...", ← template        │
│        "ano": 2023,                                     │
│        "tipo_codigo": 1,                                │
│        "tipo_descricao": "Participacao"                 │
│      }]                                                 │
│    }                                                    │
│  }                                                      │
└─────────────────────────────────────────────────────────┘
│
▼
Cliente faz: url_download.replace("{cpf}", cpf_real)
e acessa diretamente o PDF do Sispubli.
```

---

## Regras de Segurança (LGPD)

### 1. Mascaramento do CPF nos Logs

Toda aparição do CPF nos logs passa obrigatoriamente pela função `mask_cpf()`:

```
mask_cpf("12345678900") → "***.456.789-**"
```

| Posição  | Tratamento     |
| -------- | -------------- |
| `[0:3]`  | `***` (oculto) |
| `[3:6]`  | Visível        |
| `[6:9]`  | Visível        |
| `[9:11]` | `**` (oculto)  |

**Garantia:** Nenhum log em qualquer nível (DEBUG, INFO, WARNING, ERROR) contém o CPF completo.

### 2. Geração do Hash SHA-256 (id_unico)

Cada certificado recebe um identificador único gerado por:

```
id_unico = SHA256(HASH_SALT + cpf + tipo + programa + edicao)
```

| Propriedade       | Valor                                              |
| ----------------- | -------------------------------------------------- |
| Algoritmo         | SHA-256                                            |
| Tamanho           | 64 caracteres hexadecimais                         |
| SALT              | Variável de ambiente `HASH_SALT`                   |
| Determinístico    | Sim — mesmos inputs geram o mesmo hash             |
| Reversível        | Não — computacionalmente inviável com SALT secreto |

**Fail Fast:** Em ambiente de produção (`ENVIRONMENT=production`), se `HASH_SALT` não estiver definido, o servidor **não sobe** — `RuntimeError` no lifespan.

### 3. URL Template (Padrão `{cpf}`)

As URLs de download retornadas pela API contêm o placeholder literal `{cpf}` em vez do CPF real:

```
http://intranet.ifs.edu.br/.../certificado_participacao_process.wsp?tmp.tx_cpf={cpf}&tmp.id_programa=1850&tmp.id_edicao=2011
```

O **cliente** é responsável por substituir `{cpf}` pelo CPF real antes de acessar:

```python
# Python
url_final = cert["url_download"].replace("{cpf}", cpf_do_usuario)

// JavaScript / Flutter
urlFinal = cert.url_download.replaceAll("{cpf}", cpfDoUsuario);
```

**Motivo:** Evitar o tráfego do CPF em texto claro no JSON de resposta. O CPF só viaja na URL de download quando o próprio titular decide baixar o certificado.

---

## Códigos de Erro

Todas as respostas de erro seguem o envelope:

```json
{
  "error": {
    "code": "codigo_snake_case",
    "message": "Descrição legível em português."
  }
}
```

| HTTP | `code`           | Causa                                               |
| ---- | ---------------- | --------------------------------------------------- |
| 400  | `invalid_cpf`    | CPF não é numérico ou não tem 11 dígitos.           |
| 502  | `upstream_error`  | O Sispubli está fora do ar, retornou erro ou timeout. |
| 500  | `internal_error`  | Erro inesperado no processamento interno.           |

### Padrões de erro reconhecidos como `upstream_error`:

- `"Erro ao acessar"`
- `"Erro ao enviar POST"`
- `"Erro ao buscar pagina"`
- `"Token nao encontrado"`

---

## Tipos de Certificado

O Sispubli classifica certificados por um código numérico (1-11). A API enriquece o retorno com a descrição legível:

| `tipo_codigo` | `tipo_descricao`            | Endpoint Sispubli                                      | CPF na URL? |
| ------------- | --------------------------- | ------------------------------------------------------ | ----------- |
| 1             | Participação                | `certificado_participacao_process.wsp`                 | ✅ `{cpf}`   |
| 2             | Autor                       | `certificado_autor_process.wsp`                        | ✅ `{cpf}`   |
| 3             | Mini-Curso                  | `certificado_participacao_sub_evento_process.wsp`      | ✅ `{cpf}`   |
| 4             | Avaliação                   | `certificado_avaliacao_process.wsp`                    | ✅ `{cpf}`   |
| 5             | Avaliação de Programa       | `certificado_avaliacao_programa_process.wsp`           | ✅ `{cpf}`   |
| 6             | Certificado Interno         | `certificado_process.wsp`                              | ❌ Não       |
| 7             | Orientação                  | `certificado_orientador_process.wsp`                   | ✅ `{cpf}`   |
| 8             | Aluno Voluntário            | `certificado_aluno_voluntario_process.wsp`             | ✅ `{cpf}`   |
| 9             | Aluno Bolsista              | `certificado_aluno_bolsista_process.wsp`               | ✅ `{cpf}`   |
| 10            | Ministrante de Sub-Evento   | `certificado_ministrante_sub_evento_process.wsp`       | ❌ Não       |
| 11            | Coorientação                | `certificado_coorientador_process.wsp`                 | ✅ `{cpf}`   |

---

## Exemplos de Uso

### curl

```bash
# Buscar certificados
curl -s http://localhost:8000/api/certificados/12345678900 | jq .

# Health check
curl http://localhost:8000/
```

### Python (requests)

```python
import requests

cpf = "12345678900"
resp = requests.get(f"http://localhost:8000/api/certificados/{cpf}")
data = resp.json()["data"]

print(f"Total: {data['total']} certificados")
for cert in data["certificados"]:
    # Substituir template pelo CPF real para download
    url = cert["url_download"].replace("{cpf}", cpf)
    print(f"  - {cert['titulo']} ({cert['ano']}) → {url}")
```

### JavaScript (fetch)

```javascript
const cpf = "12345678900";
const resp = await fetch(`/api/certificados/${cpf}`);
const { data } = await resp.json();

data.certificados.forEach(cert => {
  const downloadUrl = cert.url_download.replace("{cpf}", cpf);
  console.log(`${cert.titulo} → ${downloadUrl}`);
});
```

---

## Cache

A função `fetch_all_certificates()` utiliza `lru_cache(maxsize=128)`:

- **Mesma requisição** (mesmo CPF) dentro do ciclo de vida do servidor retorna instantaneamente do cache
- O cache é invalidado automaticamente ao reiniciar o servidor
- Para invalidar manualmente: `fetch_all_certificates.cache_clear()`

> **Nota:** O cache é in-memory. Em ambientes serverless (Vercel), cada cold start começa com cache vazio.

---

## Variáveis de Ambiente

| Variável      | Obrigatória    | Padrão                   | Descrição                                      |
| ------------- | -------------- | ------------------------ | ---------------------------------------------- |
| `HASH_SALT`   | Em produção ✅  | `chave_secreta_padrao`   | Salt para SHA-256. Fail Fast se ausente em prod. |
| `ENVIRONMENT` | Não            | `development`            | Define modo de execução (`development`/`production`). |
| `CPF_TESTE`   | Apenas E2E     | —                        | CPF real para testes de integração.             |

---

*Documento gerado automaticamente — Sispubli API v1.1.0*
