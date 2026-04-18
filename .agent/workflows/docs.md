# Workflow: Documentação de Decisões Técnicas (ADR)

Este workflow define como devemos registrar decisões críticas no projeto Sispubli para garantir que o "porquê" das coisas nunca se perca.

## 📝 O Que Documentar?
- **Mudanças Arquiteturais**: Troca de bibliotecas, alteração no fluxo de dados.
- **Decisões de Segurança**: Escolha de algoritmos de hash (SHA-256 vs MD5), políticas de expiração de token.
- **Correções de Bugs "Estranhos"**: Explicação de bugs que fogem do óbvio (ex: corrupção de hash por regex).

## 📂 Onde Documentar?
1. **Documentos de Especificação**: Atualizar arquivos em `docs/` (ex: `SPEC_CONTRA_LOG_CPF.md`).
2. **Contexto no Código**: Usar comentários explicativos (não apenas o "o que", mas o "porquê").
3. **Walkthroughs**: Criar ou atualizar o `walkthrough.md` da tarefa atual.

## ✍️ Como Escrever uma Decisão
Ao documentar, tente seguir este padrão minimalista:

- **Contexto**: Qual era o problema? (Ex: Erro 400 no túnel de PDF).
- **Decisão**: O que foi feito? (Ex: Aumentado limite para 2048 caracteres).
- **Motivo**: Por que essa solução? (Ex: URLs reais do Sispubli infladas por Fernet excediam o limite de 500).
- **Consequências**: O que muda agora? (Ex: Maior flexibilidade para URLs longas, mas com proteção anti-DoS mantida).

## 🛠️ Ferramentas
- Use `make docs-check` para garantir que os arquivos fundamentais existem.
- Utilize alertas do GitHub (`> [!IMPORTANT]`) para destacar decisões críticas.
