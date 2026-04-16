# Limites do Plano Hobby da Vercel

## 📄 Contrato de Limites: Vercel Hobby Tier

### 1. Tráfego e Transferência de Dados (Networking)

A Vercel mede a quantidade de dados que seu site envia para os usuários.

* **Fast Data Transfer (Banda/Egress):** `100 GB por mês`. (Suficiente para dezenas de milhares de acessos mensais, dependendo do peso das imagens e recursos da sua aplicação).
* **Fast Origin Transfer:** `10 GB por mês`. (Dados trafegados entre a CDN da Vercel e o seu servidor/banco de dados de origem).
* **Tamanho do Payload (Request/Response):** O corpo de uma requisição (ex: um JSON enviado via POST ou retornado pela sua API) **não pode ultrapassar 4.5 MB**. Passar disso gera o erro `413: FUNCTION_PAYLOAD_TOO_LARGE`.

#### 2. Poder Computacional (Vercel Functions / Serverless)

Com a chegada da arquitetura *Fluid Compute*, a Vercel mudou a forma como aloca recursos, tornando o plano Hobby muito mais robusto.

* **Invocations (Execuções):** `1.000.000 de execuções por mês`.
* **Memória e CPU:** Fixado em **2 GB de RAM e 1 vCPU**. (Hobby não permite configuração desse valor, mas 2GB é o dobro do antigo padrão).
* **Tempo Máximo de Execução (Timeout):** **300 segundos (5 minutos)**. Tanto o padrão quanto o teto máximo agora são 5 minutos. Isso resolve o antigo problema de APIs que levavam mais de 10 segundos e sofriam *timeout*.
* **Teto de Consumo Mensal (Fluid Compute):**
  * *Active CPU:* `4 horas/mês` (Tempo em que a CPU está trabalhando ativamente).
  * *Provisioned Memory:* `360 GB-horas/mês`.
* **Tamanho do Pacote (Bundle Size):** Máximo de **250 MB descompactado** (ou 500 MB se for Python). Passar disso impede o deploy da função.

#### 3. Edge Functions e Streaming

* As Edge Functions têm regras diferentes. Elas **devem começar a responder em até 25 segundos** (enviar o primeiro byte).
* Após o início da resposta, o *streaming* de dados (ex: respostas de IA via OpenAI/Anthropic) pode durar até **300 segundos**.

#### 4. Regras de Build e Deploy

A Vercel impõe limites rígidos para evitar mineração de criptomoedas ou abusos nos servidores de Build.

* **Deploys por dia:** `100 deploys`.
* **Builds Simultâneos (Concurrency):** `1 por vez`. Se você "comitar" dois PRs ao mesmo tempo, o segundo ficará na fila aguardando o primeiro terminar.
* **Tempo máximo de Build:** `45 minutos por deploy`.
* **Tempo Total de Build:** `6.000 minutos por mês`.
* **Tamanho do Upload Fonte (CLI):** O código fonte enviado por linha de comando não pode exceder `100 MB`.

#### 5. Limites Adicionais de Arquitetura

* **Domínios Customizados:** Até `50 domínios` por projeto.
* **Variáveis de Ambiente:** O tamanho total de TODAS as variáveis de ambiente (nomes + valores combinados) não pode ultrapassar `64 KB` por deployment.
* **Logs de Runtime:** No plano Hobby, os logs de execução de funções ficam guardados e visíveis no painel por apenas `1 hora`. Se você precisa analisar erros do passado, precisará integrar uma ferramenta externa (como Datadog, Logtail ou Axiom).
* **Projetos Totais:** Você pode ter até `200 projetos` ativos na conta Hobby.
* **Rotas por Deploy:** Limite de `2.048 rotas/redirects/rewrites` por aplicação.

---

### ⚠️ O que acontece se você estourar o limite?

A grande vantagem do Vercel Hobby é a **ausência de cobrança surpresa ("Pay-as-you-go")**. Você não precisa inserir cartão de crédito. Se o seu projeto exceder:

1. **O limite de Banda (100GB) ou Invocations (1M):** A Vercel pausará temporariamente a sua aplicação e exibirá um erro de limite excedido. Ela enviará e-mails de alerta em 50%, 75% e 100% do consumo.
2. **O limite de Build ou Deploys:** Novos commits simplesmente falharão no terminal da Vercel e não subirão para produção até a janela de tempo "resetar".

**Dica de Arquitetura:** Se você planeja transacionar arquivos pesados (como uploads de vídeo ou PDF dos seus usuários), **não passe esses arquivos através da Vercel Function** (pois você vai esbarrar no limite de 4.5MB de payload e torrar sua banda de saída de 100GB). A solução correta é assinar *Presigned URLs* (ex: AWS S3 ou Supabase Storage) na Vercel e fazer o upload do lado do cliente direto para o serviço de armazenamento.
