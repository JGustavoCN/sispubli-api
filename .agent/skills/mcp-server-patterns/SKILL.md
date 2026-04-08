---
name: mcp-server-patterns
description: Construa servidores MCP com SDK Node/TypeScript — ferramentas, recursos, prompts, validação Zod e transportes stdio/HTTP.
---

# Padrões de Servidor MCP

O Model Context Protocol (MCP) permite que assistentes de IA chamem ferramentas, leiam recursos e usem prompts do seu servidor.

## Conceitos Principais

- **Tools (Ferramentas)**: Ações que o modelo pode invocar (ex: pesquisar, executar comando).
- **Resources (Recursos)**: Dados somente leitura que o modelo pode buscar (ex: conteúdos de arquivos).
- **Prompts**: Modelos de prompt reutilizáveis e parametrizados.
- **Transport (Transporte)**: `stdio` para clientes locais ou HTTP/SSE para remotos.

## Melhores Práticas

- **Esquema Primeiro**: Defina esquemas de entrada para cada ferramenta; documente parâmetros claramente.
- **Erros Estruturados**: Retorne mensagens de erro que o modelo possa interpretar, evitando stack traces brutos.
- **Idempotência**: Prefira ferramentas idempotentes onde possível para que repetições sejam seguras.
- **Validação com Zod**: Use Zod para garantir que os dados de entrada correspondam ao esperado.
