---
name: django-tdd
description: Estratégias de teste Django com pytest-django, metodologia TDD, factory_boy, mocking, cobertura e testes de APIs Django REST Framework.
---

# Testes Django com TDD

Desenvolvimento orientado a testes (TDD) para aplicações Django usando pytest, factory_boy e Django REST Framework.

## Quando Ativar

- Escrevendo novas aplicações Django
- Implementando APIs Django REST Framework
- Testando modelos, views e serializadores Django
- Configurando infraestrutura de testes para projetos Django

## Fluxo de Trabalho TDD para Django

### Ciclo Red-Green-Refactor

```python
# Passo 1: RED - Escreva um teste que falha
def test_user_creation():
    user = User.objects.create_user(email='test@example.com', password='testpass123')
    assert user.email == 'test@example.com'
    assert user.check_password('testpass123')
    assert not user.is_staff

# Passo 2: GREEN - Faça o teste passar
# Crie o modelo User ou factory

# Passo 3: REFACTOR - Melhore mantendo os testes verdes
```

## Melhores Práticas de Teste

- **Use factories**: Em vez de criação manual de objetos.
- **Uma asserção por teste**: Mantenha os testes focados.
- **Nomes descritivos**: `test_user_cannot_delete_others_post`.
- **Teste casos de borda**: Entradas vazias, valores None, condições de limite.
- **Mock de serviços externos**: Não dependa de APIs externas.
- **Mantenha os testes rápidos**: Use `--reuse-db` e `--nomigrations`.
