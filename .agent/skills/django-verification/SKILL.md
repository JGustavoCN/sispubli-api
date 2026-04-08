---
name: django-verification
description: "Loop de verificação para projetos Django: migrações, linting, testes com cobertura, varreduras de segurança e verificações de prontidão para implantação antes do release ou PR."
---

# Loop de Verificação Django

Execute antes de PRs, após mudanças importantes e antes do deploy para garantir a qualidade e segurança da aplicação Django.

## Quando Ativar

- Antes de abrir um Pull Request em um projeto Django
- Após mudanças profundas em modelos ou atualizações de dependências
- Verificação pré-implantação para staging ou produção
- Validar segurança de migrações e cobertura de testes

## Fases de Verificação

### Fase 1: Verificação de Ambiente
Valide versões de Python e variáveis de ambiente críticas (`DJANGO_SECRET_KEY`).

### Fase 2: Qualidade de Código e Formatação
Use `ruff`, `black` e `mypy` para garantir que o código segue os padrões do projeto.

### Fase 3: Migrações
Sempre verifique se há migrações não aplicadas ou conflitos:
`python manage.py makemigrations --check`

### Fase 4: Testes + Cobertura
Mantenha a cobertura acima de 80% no total.

### Fase 5: Varredura de Segurança
Use `pip-audit` e `python manage.py check --deploy`.
