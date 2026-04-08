---
name: python-patterns
description: Idiomas Pythonic, padrões PEP 8, type hints e melhores práticas para construir aplicações Python robustas, eficientes e sustentáveis.
---

# Padrões de Desenvolvimento Python

Padrões idiomáticos do Python e melhores práticas para construir aplicações robustas e eficientes.

## Quando Ativar

- Escrevendo novo código Python
- Revisando código Python
- Refatorando código Python existente
- Projetando pacotes/módulos Python

## Princípios Core

### 1. Legibilidade Conta
O código deve ser óbvio e fácil de entender.

### 2. Explícito é melhor que Implícito
Evite "mágica"; seja claro sobre o que seu código faz.

### 3. EAFP (Mais fácil pedir perdão do que permissão)
Python prefere o tratamento de exceções em vez de verificar condições antecipadamente (LBYL).

## Type Hints (Dicas de Tipo)
Use anotações de tipo para melhorar a legibilidade e permitir análise estática.
A partir do Python 3.9+, use tipos embutidos como `list[str]` e `dict[str, int]`.

## Padrões de Tratamento de Erros
- Capture exceções específicas.
- Evite `except: pass`.
- Use encadeamento de exceções (`raise ... from e`) para preservar o traceback.

## Gerenciamento de Recursos
Sempre prefira gerenciadores de contexto (`with statement`) para lidar com arquivos, conexões de rede e locks.
