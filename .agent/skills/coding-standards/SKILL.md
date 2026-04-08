---
name: coding-standards
description: Padrões universais de codificação, melhores práticas e convenções para desenvolvimento de software de alta qualidade.
---

# Padrões de Codificação e Melhores Práticas

Padrões universais aplicáveis em todos os projetos de desenvolvimento.

## Princípios de Qualidade de Código

1. **Legibilidade Primeiro**: O código é lido mais do que escrito.
2. **KISS (Mantenha Simples)**: A solução mais simples que funciona é geralmente a melhor.
3. **DRY (Não se Repita)**: Extraia lógica comum para funções ou utilitários.
4. **YAGNI (Você não vai precisar disso)**: Não construa funcionalidades antes que sejam necessárias.

## Padrões Técnicos

- **Nomenclatura**: Use nomes descritivos para variáveis e o padrão "verbo-substantivo" para funções.
- **Imutabilidade**: Prefira sempre operações imutáveis (como o operador spread `...`).
- **Tratamento de Erros**: Garanta tratamento abrangente com try/catch e validação de entradas.
- **Async/Await**: Execute operações em paralelo quando possível usando `Promise.all`.
- **Segurança de Tipos**: Evite o uso de `any`; defina interfaces e tipos claros.

## Organização de Arquivos

Mantenha uma estrutura de diretórios clara (`src/`, `components/`, `lib/`, `types/`) e use convenções de nomes de arquivos consistentes (PascalCase para componentes, camelCase para utilitários).

## Documentação

Comente o **PORQUÊ**, não o "o quê". Use JSDoc para documentar APIs públicas com exemplos de uso.
