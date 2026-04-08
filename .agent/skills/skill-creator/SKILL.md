---
name: skill-creator
description: Guia para criação de novas skills no formato moderno do Antigravity, garantindo organização e extensibilidade.
---

# Guia de Criação de Skills (Formato Moderno)

Este guia define o padrão para extender as capacidades da IA através de "Skills" organizadas em pastas.

## Estrutura da Skill

Uma skill deve residir em seu próprio diretório dentro de `.agent/skills/`.

```text
.agent/skills/[skill-name]/
├── SKILL.md          # Arquivo obrigatório com instruções
├── scripts/           # (Opcional) Scripts auxiliares (Python, JS, Shell)
├── resources/         # (Opcional) Templates, arquivos de dados, etc.
└── examples/          # (Opcional) Referências de implementações reais
```

## O Arquivo SKILL.md

O arquivo `SKILL.md` deve conter um YAML frontmatter no topo e instruções claras em Markdown.

### YAML Frontmatter

```yaml
---
name: [identificador-da-skill]
description: [Descrição breve em Português do Brasil]
---
```

### Seções Recomendadas

1. **Visão Geral**: O que a skill resolve.
2. **Quando Ativar**: Gatilhos mentais para eu (IA) saber quando usar esta skill.
3. **Instruções Centrais**: Passo a passo ou diretrizes técnicas.
4. **Exemplos de Código**: Snippets prontos para uso.

## Melhores Práticas

- **Tradução**: Mantenha a `description` sempre em Português (pt-BR).
- **Agnóstico de Modelo**: Evite citar nomes de modelos específicos (Claude, Opus). Prefira termos como "Agente", "IA" ou "Gemini".
- **Modularidade**: Se a lógica for complexa, mova-a para um script em `scripts/` e use o `SKILL.md` para me ensinar como rodar esse script.
