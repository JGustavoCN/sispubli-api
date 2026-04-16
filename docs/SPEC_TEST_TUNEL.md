# 📑 Estratégia de Qualidade e Testes: Túnel Seguro Sispubli

## 1. Critérios de Aceite Absolutos (O que define o "Sucesso")

Para que a funcionalidade do Túnel de PDF seja considerada apta para produção, ela deve garantir matematicamente os seguintes pontos:

* **Bloqueio de "Falsos PDFs" (Garantia de Integridade):** A API jamais pode entregar um arquivo ao usuário se ele não for legitimamente um PDF. A validação não pode confiar apenas no cabeçalho HTTP (`Content-Type`) retornado pela faculdade, mas deve obrigatoriamente inspecionar os primeiros bytes do arquivo (Magic Bytes: `%PDF-`).
* **Fidelidade do Contrato de Proxy:** A API deve ocultar a identidade do usuário final (limpando cookies e headers originais), mas deve **obrigatoriamente forjar e enviar** os cabeçalhos que o Sispubli exige para funcionar (ex: o `Referer` apontando para a página anterior e um `User-Agent` de navegador comum).
* **Blindagem de Recursos (Rate Limit & SSRF):** Requisições com tickets adulterados, apontando para domínios externos à faculdade, ou que excedam o limite de cliques por minuto devem ser derrubadas antes mesmo de abrir conexão com a internet.

---

## 2. A Matriz de Testes (As 4 Camadas de Defesa)

Para que você saiba exatamente onde o erro ocorreu (se foi erro no seu código ou se a faculdade mudou o sistema), os testes devem ser divididos nestas 4 categorias:

### Camada 1: Testes Unitários (A Lógica Interna)

* **O que validam:** As regras de negócio puras (Motor de Criptografia e Rate Limiter).
* **O que deve ser testado:**
  * Se um token expirado (TTL > 15 min) é rejeitado.
  * Se tickets com mais de 500 caracteres disparam erro (evitando estouro de memória).
  * Se o limitador de IP bloqueia a 21ª requisição no mesmo minuto.
* **O Alarme:** Se falhar aqui, o problema é puramente lógico no seu código. A segurança estrutural foi comprometida.

### Camada 2: Testes de Contrato de API (Mockando o Sispubli)

* **O que validam:** O comportamento do seu Túnel de PDF (FastAPI + HTTPx) diante de respostas falsas ou instabilidades.
* **O que deve ser testado:**
  * **A Armadilha do HTML:** Simular o Sispubli retornando Status 200, dizendo ser um PDF, mas entregando um texto HTML de erro. **Comportamento esperado:** Sua API deve interceptar, interromper o stream e retornar Erro 502 (Bad Gateway).
  * **Timeout do Upstream:** Simular a intranet da faculdade demorando 20 segundos para responder. **Comportamento esperado:** Sua API deve cancelar a operação em 10 segundos e retornar erro, evitando que a Vercel trave.
  * **Verificação de Headers:** Interceptar a requisição que o seu Python tenta fazer e conferir se o header `Referer` está lá.
* **O Alarme:** Se falhar aqui, significa que alguém alterou o código do seu Túnel e removeu alguma trava de segurança (ex: esqueceu de enviar o Referer ou tirou a checagem dos Magic Bytes).

### Camada 3: Testes de Sanidade do Scraper (Offline)

* **O que validam:** A resiliência do seu extrator HTML (`BeautifulSoup`).
* **O que deve ser testado:**
  * Você deve salvar um arquivo HTML real do Sispubli (uma página de sucesso com certificados) dentro da pasta do projeto.
  * O teste deve mandar o scraper ler esse arquivo salvo e garantir que ele encontra os títulos, URLs e anos corretamente.
* **O Alarme:** Se esse teste quebrar, significa que sua expressão regular (Regex) ou a lógica de busca de tags do BeautifulSoup foi quebrada por uma refatoração no seu código.

### Camada 4: Testes End-to-End (E2E) (O Mundo Real)

* **O que validam:** A comunicação viva entre a sua máquina e o servidor da faculdade.
* **O que deve ser testado:**
  * Usando um CPF real configurado no ambiente, o teste faz o fluxo completo: Autentica -> Lista Certificados -> Descriptografa o primeiro Ticket -> Baixa o PDF real.
  * O teste deve validar se o arquivo recebido da internet é, de fato, um PDF válido.
* **O Alarme Supremo (Isolamento de Falhas):** Se as Camadas 1, 2 e 3 passarem com sucesso (verde), mas a Camada 4 (E2E) falhar (vermelho), você tem **100% de certeza de que o Sispubli mudou as regras**. Pode ser que eles adicionaram um Captcha, mudaram o fluxo de telas ou alteraram a URL final do `ReportConnector.wsp`. O teste E2E deve ser instruído a imprimir os primeiros 200 bytes do erro retornado para você diagnosticar a mudança na hora.

---

## 3. Plano de Observabilidade (Como debugar em Produção)

Além dos testes rodando na sua máquina ou no GitHub Actions, a API em produção precisa "falar" com você através de logs inteligentes. As orientações de implementação para observabilidade são:

1. **Logue a Mentira:** Sempre que a validação dos *Magic Bytes* falhar (ou seja, quando o Sispubli mandar um Falso PDF), o seu sistema não deve apenas retornar erro 502 ao usuário. Ele deve gerar um log de nível `ERROR` imprimindo os 200 primeiros caracteres do lixo que a faculdade mandou. Isso permite que você leia o log na Vercel e veja: `"Ah, eles retornaram <html>Sessão expirada</html>"`.
2. **Alerta de Tamanho Anômalo:** Se um PDF for validado com sucesso, mas o tamanho final for menor que 5 KB, gere um log de nível `WARNING`. Pode ser um certificado corrompido gerado pelo próprio JasperReports da faculdade.
3. **Auditoria de SSRF:** Se o módulo de segurança rejeitar uma URL forjada, o log deve registrar qual foi o domínio malicioso tentado (ex: `SSRF Blocked: tentativa de acessar evil.com`), para você saber se está sofrendo ataques de exploração.

---

## 4. Resumo de Ação para a Equipe de Desenvolvimento

Entregue estas diretrizes para quem for programar:

* **Regra 1:** Nunca confie no `Content-Type` do Sispubli. Inspecione o conteúdo.
* **Regra 2:** Testes mockados garantem que nosso código não regrediu. Testes E2E garantem que o mundo lá fora não mudou.
* **Regra 3:** O Túnel exige persistência de sessão. A requisição "Gatilho" (A) e a requisição "Download" (B) precisam compartilhar os mesmos cookies temporários gerados pelo cliente HTTP no backend.
* **Regra 4:** O header `Referer` é a chave mestra para o Sispubli liberar o PDF. Sem ele mockado e forjado na etapa B apontando para a etapa A, a faculdade retornará erro.
