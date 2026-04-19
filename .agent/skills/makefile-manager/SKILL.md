---
name: makefile-manager
description: Especialista em manutenção e expansão de Makefiles para automação de DX (Developer Experience).
---

# Makefile Manager Skill

Esta skill ensina a manter o `Makefile` como o registro central de comandos do projeto, garantindo consistência e facilidade de uso.

## Quando Ativar
- Sempre que criar um novo script ou fluxo de comando complexo (ex: auditoria, deploy, limpeza).
- Ao introduzir novas ferramentas de linting, testes ou documentação.
- Ao notar que comandos repetitivos estão sendo executados manualmente no terminal.

## Instruções Centrais

1. **Registro Central**: Todo comando útil para o desenvolvedor deve ter um alvo correspondente no `Makefile`.
2. **Auto-Documentação**: Sempre mantenha o alvo `help` atualizado com a descrição de cada comando.
3. **Gerenciamento de Dependências**: Utilize `uv run` para garantir que os comandos rodem no ambiente virtual correto.
4. **Alvos PHONY**: Sempre declare novos comandos como `.PHONY` para evitar conflitos com nomes de arquivos.
5. **Portabilidade**: Evite comandos Linux-only (como `rm -rf`) se o projeto rodar em Windows; use lógica condicional ou comandos compatíveis (como `uv run python -c "..."`).

## Exemplo de Estrutura

```makefile
.PHONY: audit
audit:
	@echo "Iniciando Auditoria LGPD..."
	uv run python scripts/audit_logs.py
```

## Benefícios
- Facilita o onboarding de novos desenvolvedores.
- Garante conformidade no CI/CD (o CI deve usar os mesmos comandos do Makefile).
- Reduz erros humanos na execução de tarefas complexas.
