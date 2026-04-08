---
name: api-design
description: Padrões de design de API REST, incluindo nomeação de recursos, códigos de status, paginação, filtragem, respostas de erro, versionamento e limites de taxa para APIs de produção.
---

# Padrões de Design de API

Convenções e melhores práticas para projetar APIs REST consistentes e amigáveis ao desenvolvedor.

## Quando Ativar

- Projetando novos endpoints de API
- Revisando contratos de API existentes
- Adicionando paginação, filtragem ou ordenação
- Implementando tratamento de erros para APIs
- Planejando estratégia de versionamento de API
- Construindo APIs públicas ou voltadas para parceiros

## Design de Recursos

### Estrutura de URL

```bash
# Recursos são substantivos, no plural, minúsculos, kebab-case
GET    /api/v1/users
GET    /api/v1/users/:id
POST   /api/v1/users
PUT    /api/v1/users/:id
PATCH  /api/v1/users/:id
DELETE /api/v1/users/:id

# Sub-recursos para relacionamentos
GET    /api/v1/users/:id/orders
POST   /api/v1/users/:id/orders

# Ações que não mapeiam para CRUD (use verbos com moderação)
POST   /api/v1/orders/:id/cancel
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
```

### Regras de Nomeação

```bash
# BOM
/api/v1/team-members          # kebab-case para recursos de múltiplas palavras
/api/v1/orders?status=active  # query params para filtragem
/api/v1/users/123/orders      # recursos aninhados para propriedade

# RUIM
/api/v1/getUsers              # verbo na URL
/api/v1/user                  # singular (use plural)
/api/v1/team_members          # snake_case em URLs
/api/v1/users/123/getOrders   # verbo em recurso aninhado
```

## Métodos HTTP e Códigos de Status

### Semântica de Métodos

| Método | Idempotente | Seguro | Uso Para |
| -------- | ----------- | ------ | -------- |
| GET | Sim | Sim | Recuperar recursos |
| POST | Não | Não | Criar recursos, disparar ações |
| PUT | Sim | Não | Substituição total de um recurso |
| PATCH | Não* | Não | Atualização parcial de um recurso |
| DELETE | Sim | Não | Remover um recurso |

*PATCH pode ser feito idempotente com implementação adequada

### Referência de Códigos de Status

```bash
# Sucesso
200 OK                    — GET, PUT, PATCH (com corpo de resposta)
201 Created               — POST (incluir header Location)
204 No Content            — DELETE, PUT (sem corpo de resposta)

# Erros do Cliente
400 Bad Request           — Falha de validação, JSON malformado
401 Unauthorized          — Autenticação ausente ou inválida
403 Forbidden             — Autenticado mas não autorizado
404 Not Found             — Recurso não existe
409 Conflict              — Entrada duplicada, conflito de estado
422 Unprocessable Entity  — Semânticamente inválido (JSON válido, dados ruins)
429 Too Many Requests     — Limite de taxa excedido

# Erros do Servidor
500 Internal Server Error — Falha inesperada (nunca exponha detalhes)
502 Bad Gateway           — Falha no serviço de upstream
503 Service Unavailable   — Sobrecarga temporária, incluir Retry-After
```

## Formato de Resposta

### Resposta de Sucesso

```json
{
  "data": {
    "id": "abc-123",
    "email": "alice@example.com",
    "name": "Alice",
    "created_at": "2025-01-15T10:30:00Z"
  }
}
```

### Resposta de Erro

```json
{
  "error": {
    "code": "validation_error",
    "message": "A validação da requisição falhou",
    "details": [
      {
        "field": "email",
        "message": "Deve ser um endereço de e-mail válido",
        "code": "invalid_format"
      }
    ]
  }
}
```

## Paginação

### Baseada em Cursor (Escalável - Recomendado)

```json
{
  "data": [...],
  "meta": {
    "has_next": true,
    "next_cursor": "eyJpZCI6MTQzfQ"
  }
}
```

## Checklist de Design de API

Antes de publicar um novo endpoint:

- [ ] URL segue convenções (plural, kebab-case, sem verbos)
- [ ] Método HTTP correto utilizado
- [ ] Códigos de status apropriados retornados
- [ ] Entrada validada com esquema (Zod, Pydantic, etc.)
- [ ] Respostas de erro seguem o padrão
- [ ] Paginação implementada para listagens
- [ ] Autenticação e Autorização verificadas
- [ ] Documentação atualizada (OpenAPI/Swagger)
