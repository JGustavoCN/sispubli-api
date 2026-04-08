---
name: backend-patterns
description: Padrões de arquitetura backend, design de API, otimização de banco de dados e melhores práticas de servidor para Node.js, Express e rotas de API Next.js.
---

# Padrões de Desenvolvimento Backend

Padrões de arquitetura backend e melhores práticas para aplicações escaláveis no lado do servidor.

## Quando Ativar

- Projetando endpoints de API REST ou GraphQL
- Implementando camadas de repositório, serviço ou controlador
- Otimizando consultas de banco de dados (N+1, indexação, pool de conexões)
- Adicionando cache (Redis, em memória, headers de cache HTTP)
- Configurando jobs de fundo ou processamento assíncrono
- Estruturando tratamento de erros e validação para APIs
- Construindo middlewares (autenticação, logging, rate limiting)

## Padrões de Design de API

### Repositório (Repository Pattern)

Abstração da lógica de acesso a dados para facilitar a manutenção e testes.

### Camada de Serviço (Service Layer)

Lógica de negócio separada do acesso a dados e dos controladores.

### Middleware

Pipeline de processamento de requisição/resposta.

## Otimização de Banco de Dados

- **Prevenção de N+1**: Use fetch em lote (*batch fetch*) ou JOINS adequados.
- **Transações**: Garanta a atomicidade em operações complexas.

## Gerenciamento de Erros e Logs

Implemente tratamento centralizado de erros e utilize logging estruturado para facilitar a observabilidade.
