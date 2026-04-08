---
name: python-testing
description: Estratégias de teste Python usando pytest, metodologia TDD, fixtures, mocking, parametrização e requisitos de cobertura.
---

# Padrões de Teste em Python

Estratégias abrangentes de teste para aplicações Python usando pytest e metodologia TDD.

## Quando Ativar

- Escrevendo novo código Python (seguindo TDD)
- Projetando suítes de teste
- Revisando cobertura de código
- Configurando infraestrutura de testes

## Filosofia de Teste

### Test-Driven Development (TDD)
1. **RED**: Escreva um teste que falha.
2. **GREEN**: Escreva o código mínimo para passar.
3. **REFACTOR**: Melhore o código mantendo o teste verde.

### Requisitos de Cobertura
- **Alvo**: 80%+ de cobertura.
- **Caminhos críticos**: 100% de cobertura obrigatória.

## pytest Fundamentals

### Fixtures
Use fixtures para preparar dados e recursos de forma reutilizável.
```python
@pytest.fixture
def user():
    return User(name="Alice")
```

### Parametrização
Teste múltiplos cenários com um único teste.
```python
@pytest.mark.parametrize("a,b,expected", [(1,2,3), (4,5,9)])
def test_add(a, b, expected):
    assert add(a, b) == expected
```

### Mocking
Use `unittest.mock` para isolar o código de dependências externas.
