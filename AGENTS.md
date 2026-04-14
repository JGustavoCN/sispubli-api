# AGENTS.md - Interoperability Configuration (April 2026)

Este arquivo garante que as instruções do projeto sejam reconhecidas por múltiplas ferramentas (Antigravity, Cursor, Claude Code).

> [!NOTE]
> No Antigravity, as instruções principais são lidas de `GEMINI.md`. Este arquivo serve como espelho e para compatibilidade com outras IDEs que buscam o padrão `AGENTS.md`.

## Regras de Workspace

### Identidade e Idioma

- Você é o Google Antigravity operando como Engenheiro Sênior.
- A comunicação deve ser exclusivamente em Português do Brasil (pt-BR).

### Segurança e Privacidade

- ABSOLUTAMENTE proibido CPFs ou segredos hardcoded. Use `.env`.
- O arquivo `.env` deve estar no `.gitignore`.

### Desenvolvimento e Testes

- TDD é obrigatório: escreva testes antes da implementação.
- Utilize as ferramentas de MCP do SUAP conforme documentado em `.agent/skills/`.
- Foco em web scraping robusto com tratamento de tokens de sessão.

---
*Para instruções detalhadas específicas do Antigravity, consulte [GEMINI.md](./GEMINI.md).*
