# Sispubli API — Contrato e Documentação (v1.1.0)

> **API REST de Extração de Certificados Acadêmicos**
> Instituto Federal de Sergipe (IFS) — Sistema Sispubli
> **Fase: Estabilidade (Milestone 2 - Secure Tunnel & Bearer Auth)**

---

## Sumário

- [Sispubli API — Contrato e Documentação (v1.1.0)](#sispubli-api--contrato-e-documentação-v110)
  - [Sumário](#sumário)
  - [Visão Geral](#visão-geral)
  - [Base URL](#base-url)
  - [Fluxo de Autenticação e Acesso](#fluxo-de-autenticação-e-acesso)
  - [Endpoints](#endpoints)
    - [`GET /`](#get-)
    - [`POST /api/auth/token`](#post-apiauthtoken)
      - [Payload](#payload)
      - [Respostas](#respostas)
    - [`GET /api/certificados`](#get-apicertificados)
      - [Headers](#headers)
      - [Resposta `200 OK`](#resposta-200-ok)
    - [`GET /api/pdf/{ticket}`](#get-apipdfticket)
      - [Comportamento de Segurança](#comportamento-de-segurança)
  - [Segurança e LGPD](#segurança-e-lgpd)
    - [1. Mascaramento de CPF](#1-mascaramento-de-cpf)
    - [2. Tokens Auto-contidos](#2-tokens-auto-contidos)
    - [3. Tickets de Download](#3-tickets-de-download)
  - [Códigos de Erro](#códigos-de-erro)
  - [Variáveis de Ambiente](#variáveis-de-ambiente)

---

## Visão Geral

A Sispubli API v1.1.0 é um gateway REST que abstrai o sistema legado de certificados do IFS. Esta versão introduz o **Secure Tunneling**, onde os arquivos PDF não são mais acessados via link direto do Sispubli, mas através de um proxy seguro que protege o CPF do usuário e previne bloqueios de rede (CORS/WAF).

---

## Base URL

| Ambiente | URL |
| :--- | :--- |
| Local | `http://localhost:8000` |
| Produção | `{BASE_URL}` (Vercel/Docker) |

---

## Fluxo de Autenticação e Acesso

A API utiliza uma jornada de 3 etapas para garantir a privacidade dos dados:

1. **Identificação:** O cliente envia o CPF para `/api/auth/token`.
2. **Autorização:** A API retorna um `access_token` (Fernet) válido por 15 minutos.
3. **Consumo:** O cliente usa o token no header `Authorization: Bearer` para listar certificados e obter os tickets de download tunelados.

---

## Endpoints

### `GET /`

**Health Check** — Verifica se a API está operacional.

**Resposta `200 OK`:**

```json
{ "status": "API do Sispubli rodando" }
```

---

### `POST /api/auth/token`

**Gera um token de sessão para um CPF.**

#### Payload

```json
{
  "cpf": "12345678900"
}
```

#### Respostas

- **200 OK:** Sucesso.

  ```json
  {
    "access_token": "gAAAAABp...",
    "session_hash": "64_chars_hex_hash"
  }
  ```

- **400 Bad Request:** CPF inválido.
- **429 Too Many Requests:** Rate limit atingido.

---

### `GET /api/certificados`

**Lista todos os certificados do usuário autenticado.**

#### Headers

| Header | Valor | Obrigatório |
| :--- | :--- | :--- |
| `Authorization` | `Bearer <access_token>` | ✅ Sim |

#### Resposta `200 OK`

```json
{
  "data": {
    "usuario_id": "***.456.789-**",
    "total": 1,
    "certificados": [
      {
        "id_unico": "sha256_hash",
        "titulo": "Monitoria de Algoritmos",
        "url_download": "/api/pdf/ticket_fernet_id",
        "ano": 2023,
        "tipo_codigo": 1,
        "tipo_descricao": "Participação"
      }
    ]
  }
}
```

---

### `GET /api/pdf/{ticket}`

**Túnel de download seguro para o binário PDF.**

Este endpoint não requer header de autenticação, pois o `ticket` já possui a URL e o CPF criptografados.

#### Comportamento de Segurança

- **Anti-Fake PDF:** A API valida se o Sispubli retornou um PDF legítimo (`%PDF-`). Se retornar HTML (erro do sistema legado), a API aborta e retorna `502`.
- **Referer Forger:** Simula o acesso vindo da intranet do IFS para evitar bloqueios.
- **SSRF Protection:** Valida se a URL interna pertence ao domínio autorizado.

---

## Segurança e LGPD

### 1. Mascaramento de CPF

O CPF real nunca é exibido de forma completa. Nas respostas JSON e nos logs, ele é sempre mascarado como `***.456.789-**`.

### 2. Tokens Auto-contidos

O `access_token` carrega o CPF criptografado com Fernet. A chave secreta nunca sai do servidor.

### 3. Tickets de Download

A `url_download` retornada na listagem é um caminho relativo para o túnel da própria API, impedindo que o CPF do usuário seja exposto em parâmetros de URL em logs de proxies externos.

---

## Códigos de Erro

| HTTP | Código | Descrição |
| :--- | :--- | :--- |
| 400 | `invalid_cpf` | O CPF informado não possui 11 dígitos numéricos. |
| 401 | `unauthorized` | Token ausente, inválido ou expirado. |
| 403 | `ssrf_blocked` | Tentativa de acessar host não autorizado. |
| 502 | `upstream_error` | O Sispubli retornou um erro ou está inacessível. |
| 502 | `fake_pdf` | O motor detectou que o arquivo original não é um PDF. |
| 504 | `gateway_timeout` | O Sispubli demorou mais de 20s para responder. |

---

## Variáveis de Ambiente

| Variável | Descrição |
| :--- | :--- |
| `FERNET_SECRET_KEY` | Chave para criptografia dos tokens e tickets (32 bytes base64). |
| `HASH_SALT` | Salt para gerar os `id_unico` dos certificados. |
| `SECRET_PEPPER` | Usado na derivação do `session_hash`. |

---

**Documento gerado automaticamente — Sispubli API Stable v1.1.0**
BSI - 2026.1
