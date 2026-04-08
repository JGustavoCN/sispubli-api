---
name: django-patterns
description: Padrões de arquitetura Django, design de API REST com DRF, melhores práticas de ORM, cache, signals, middleware e apps Django de nível de produção.
---

# Padrões de Desenvolvimento Django

Padrões de arquitetura Django de nível de produção para aplicações escaláveis e sustentáveis.

## Quando Ativar

- Construindo aplicações web Django
- Projetando APIs com Django REST Framework (DRF)
- Trabalhando com Django ORM e modelos
- Configurando a estrutura do projeto Django
- Implementando cache, signals ou middleware

## Padrões de Design de Modelos

- **Custom User Model**: Estenda `AbstractUser` desde o início do projeto.
- **QuerySet Customizados**: Use `models.QuerySet` para encapsular lógica de consulta reutilizável.
- **Manager Customizados**: Use para lógica de criação complexa.
- **Indexação**: Use `Meta.indexes` para otimizar buscas frequentes.

## Django REST Framework (DRF)

- **Serializers**: Use para validação de entrada e transformação de saída.
- **ViewSets**: Prefira `ModelViewSet` para operações CRUD padrão.
- **Ações Customizadas**: Use o decorador `@action` para comportamentos fora do CRUD.

## Otimização de Performance

- **Prevenção de N+1**: Use `select_related` para chaves estrangeiras e `prefetch_related` para ManyToMany/Reverse FK.
- **Operações em Lote**: Use `bulk_create`, `bulk_update` e `delete()` em QuerySets sempre que possível.
- **Cache**: Implemente cache em nível de visão (`cache_page`), fragmento de template ou cache de baixo nível.

## Estrutura de Projeto Recomendada

Separe as configurações (`settings/base.py`, `development.py`, `production.py`) e organize os aplicativos em uma pasta `apps/`.
