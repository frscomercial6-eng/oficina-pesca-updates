# Hub de Automacao FRS Solutions (Google Apps Script)

Este pacote inicia o Hub para monitorar e-mails da InfinitePay e registrar vendas/licencas por modulo:
- Oficina_Pesca
- Atlas
- Mercado

## 1) O que o script faz

1. Le e-mails no Gmail via filtro configuravel.
2. Garante a estrutura no Google Drive:
- FRS_Solutions
- FRS_Solutions/Oficina_Pesca
- FRS_Solutions/Atlas
- FRS_Solutions/Mercado
3. Garante uma planilha central e adiciona cada venda com campos:
- Data
- Cliente
- HWID
- Programa
- Status da Licenca
- Chave Gerada
- Transacao
- Email Comprador
- Origem Email ID
4. Chama o endpoint de geracao de licenca de cada modulo, preservando a logica de negocio separada.
5. Salva log JSONL no Drive e replica o resultado no Firebase Realtime Database.

## 2) Arquivo principal

- Code.gs

## 3) Script Properties obrigatorias

Configure em Apps Script > Project Settings > Script properties:

- LICENSE_ENDPOINT_OFICINA_PESCA
- LICENSE_TOKEN_OFICINA_PESCA
- LICENSE_ENDPOINT_ATLAS
- LICENSE_TOKEN_ATLAS
- LICENSE_ENDPOINT_MERCADO
- LICENSE_TOKEN_MERCADO
- HUB_API_KEY
- FIREBASE_DATABASE_URL
- FIREBASE_DB_SECRET (ou FIREBASE_AUTH)

Observacoes:
- Os tokens de modulo sao opcionais, mas recomendados.
- HUB_API_KEY protege o endpoint FastAPI de geracao de licenca para uso exclusivo do Hub.
- Se FIREBASE_DB_SECRET nao for usado, ajuste a regra do seu Firebase para aceitar o metodo escolhido.

## 4) Deploy e autorizacao segura

1. Acesse https://script.google.com com a conta frs.suporte.oficina@gmail.com.
2. Crie um projeto e cole o conteudo de Code.gs.
3. Defina as Script Properties acima.
4. Execute setupHubFRS manualmente (primeira vez).
5. Conceda os escopos solicitados:
- Gmail (leitura)
- Drive (criar pastas/arquivos)
- Sheets (escrita na planilha)
- UrlFetch (chamar endpoint de modulo e Firebase REST)
- Triggers (execucao agendada)

## 5) Boas praticas de seguranca

- Nunca gravar tokens no codigo-fonte.
- Guardar segredo apenas em Script Properties.
- Restringir os endpoints de geracao para aceitar somente origem autenticada (Bearer + allowlist por IP/proxy quando possivel).
- Usar conta dedicada de automacao (frs.suporte.oficina@gmail.com) sem credenciais compartilhadas.
- Revisar periodicamente a lista de escopos e revogar apps nao usados em https://myaccount.google.com/permissions.
- Ativar verificacao em duas etapas na conta.

## 6) Operacao

- setupHubFRS: prepara estrutura e instala trigger.
- runHubMonitor: monitor principal.
- resetProcessedCache: limpa cache de deduplicacao (use com cautela).

## 7) Ajustes necessarios no seu ambiente

- Regex de parse do e-mail da InfinitePay pode variar por template. Ajuste parseInfinitePayMessage_ conforme seu e-mail real.
- Se o HWID nao vier no e-mail, o script grava AGUARDANDO_HWID e nao gera licenca.
- Para gerar automaticamente sem HWID no e-mail, inclua esse campo no checkout/comprovante da InfinitePay.
