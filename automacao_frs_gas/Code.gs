/**
 * Hub de Automacao FRS Solutions (Google Apps Script)
 *
 * Escopo:
 * - Monitorar e-mails da InfinitePay no Gmail
 * - Garantir estrutura de pastas no Drive
 * - Registrar vendas na planilha central
 * - Chamar gerador de licenca por modulo (sem unificar regras)
 * - Salvar resultado no log e no Firebase
 *
 * Configurar as propriedades em: Project Settings > Script properties
 */

const HUB_CONFIG = {
  rootFolderName: 'FRS_Solutions',
  programs: ['Oficina_Pesca', 'Atlas', 'Mercado'],
  masterSheetName: 'FRS_Hub_Clientes',
  masterSheetTab: 'vendas',
  logFileName: 'hub_licencas_log.jsonl',
  gmailQuery: 'subject:("Pagamento Aprovado") from:(infinitepay OR @infinitepay.com.br OR @infinitepay.io) newer_than:30d',
  status: {
    novo: 'NOVA_VENDA',
    aguardandoHwid: 'AGUARDANDO_HWID',
    licencaGerada: 'LICENCA_GERADA',
    erroGeracao: 'ERRO_GERACAO'
  }
};

/**
 * Registro de adaptadores por programa.
 * Cada modulo aponta para o proprio endpoint de geracao.
 * Assim, a regra de licenca continua isolada por app.
 */
const MODULE_REGISTRY = {
  Oficina_Pesca: {
    endpointProp: 'LICENSE_ENDPOINT_OFICINA_PESCA',
    tokenProp: 'LICENSE_TOKEN_OFICINA_PESCA',
    timeoutMs: 20000
  },
  Atlas: {
    endpointProp: 'LICENSE_ENDPOINT_ATLAS',
    tokenProp: 'LICENSE_TOKEN_ATLAS',
    timeoutMs: 20000
  },
  Mercado: {
    endpointProp: 'LICENSE_ENDPOINT_MERCADO',
    tokenProp: 'LICENSE_TOKEN_MERCADO',
    timeoutMs: 20000
  }
};

/**
 * Executar 1x para preparar Drive, planilha e trigger recorrente.
 */
function setupHubFRS() {
  const structure = ensureDriveStructure_();
  const sheet = getOrCreateMasterSheet_(structure.rootFolderId);
  ensureMasterHeader_(sheet);
  ensureGmailLabel_();
  installTimeTrigger_(10);
  Logger.log({ ok: true, rootFolderId: structure.rootFolderId, sheetId: sheet.getParent().getId() });
}

/**
 * Ponto de entrada agendado.
 */
function runHubMonitor() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(30000)) {
    Logger.log('Hub ocupado; execucao ignorada para evitar corrida.');
    return;
  }

  try {
    const structure = ensureDriveStructure_();
    const sheet = getOrCreateMasterSheet_(structure.rootFolderId);
    ensureMasterHeader_(sheet);

    const threads = GmailApp.search(HUB_CONFIG.gmailQuery, 0, 50);
    const stats = { totalMensagens: 0, novasVendas: 0, processadas: 0, erros: 0 };

    threads.forEach((thread) => {
      const messages = thread.getMessages();
      messages.forEach((msg) => {
        stats.totalMensagens += 1;
        if (!isMessageProcessed_(msg)) {
          const parsed = parseInfinitePayMessage_(msg);
          if (parsed.isSale) {
            stats.novasVendas += 1;
            try {
              processSale_(parsed, msg, sheet, structure);
              markMessageProcessed_(msg, parsed.transactionId || parsed.messageId);
              stats.processadas += 1;
            } catch (err) {
              stats.erros += 1;
              writeHubLog_(structure.rootFolderId, {
                ts: new Date().toISOString(),
                level: 'ERROR',
                messageId: parsed.messageId,
                transactionId: parsed.transactionId || '',
                error: String(err)
              });
            }
          }
        }
      });
    });

    Logger.log(stats);
  } finally {
    lock.releaseLock();
  }
}

function processSale_(sale, msg, sheet, structure) {
  const now = new Date();
  const programa = normalizeProgram_(sale.programa);
  const hwid = (sale.hwid || '').trim();

  const baseRow = {
    data: now,
    cliente: sale.cliente || sale.email || 'NAO_IDENTIFICADO',
    hwid: hwid,
    programa: programa,
    statusLicenca: hwid ? HUB_CONFIG.status.novo : HUB_CONFIG.status.aguardandoHwid,
    chaveGerada: '',
    transacao: sale.transactionId || '',
    emailComprador: sale.email || '',
    origemEmailId: sale.messageId
  };

  if (!hwid) {
    appendMasterRow_(sheet, baseRow);
    writeHubLog_(structure.rootFolderId, {
      ts: now.toISOString(),
      level: 'WARN',
      action: 'SALE_REGISTERED_WITHOUT_HWID',
      transactionId: sale.transactionId || '',
      programa: programa,
      cliente: baseRow.cliente
    });
    return;
  }

  const licenseResult = gerarLicencaPorModulo_(programa, {
    cliente: baseRow.cliente,
    hwid: hwid,
    programa: programa,
    transactionId: sale.transactionId || '',
    email: baseRow.emailComprador,
    source: 'GMAIL_INFINITEPAY'
  });

  baseRow.statusLicenca = licenseResult.ok
    ? HUB_CONFIG.status.licencaGerada
    : HUB_CONFIG.status.erroGeracao;
  baseRow.chaveGerada = licenseResult.chave || '';

  appendMasterRow_(sheet, baseRow);

  const saleFileMeta = saveSaleJsonInProgramFolder_(structure.programFolderIds[programa], {
    createdAt: now.toISOString(),
    programa: programa,
    cliente: baseRow.cliente,
    hwid: hwid,
    transactionId: baseRow.transacao,
    statusLicenca: baseRow.statusLicenca,
    chaveGerada: baseRow.chaveGerada,
    emailComprador: baseRow.emailComprador,
    origemEmailId: baseRow.origemEmailId
  });

  const firebaseRes = saveLicenseFirebase_(programa, {
    createdAt: now.toISOString(),
    cliente: baseRow.cliente,
    hwid: hwid,
    programa: programa,
    statusLicenca: baseRow.statusLicenca,
    chaveGerada: baseRow.chaveGerada,
    transactionId: baseRow.transacao,
    emailComprador: baseRow.emailComprador,
    source: 'hub_gas'
  });

  writeHubLog_(structure.rootFolderId, {
    ts: now.toISOString(),
    level: licenseResult.ok ? 'INFO' : 'ERROR',
    action: 'SALE_PROCESSED',
    programa: programa,
    cliente: baseRow.cliente,
    hwid: hwid,
    transactionId: baseRow.transacao,
    statusLicenca: baseRow.statusLicenca,
    chaveGerada: baseRow.chaveGerada,
    saleFileId: saleFileMeta.id,
    firebaseOk: firebaseRes.ok,
    firebaseStatus: firebaseRes.status,
    moduloMensagem: licenseResult.message
  });
}

/**
 * Parse basico de e-mail da InfinitePay.
 * Ajuste regexes conforme o formato exato que chega na caixa.
 */
function parseInfinitePayMessage_(msg) {
  const plainBody = msg.getPlainBody() || '';
  const subject = msg.getSubject() || '';
  const body = [subject, plainBody].join('\n');

  const transactionId = firstMatch_(body, [
    /(?:id\s*da\s*transa[cç][aã]o|transa[cç][aã]o|pedido)\s*[:#]?\s*([A-Z0-9\-]{6,})/i,
    /(?:txid|transaction id)\s*[:#]?\s*([A-Z0-9\-]{6,})/i
  ]);

  const email = firstMatch_(body, [
    /([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})/i
  ]);

  const cliente = firstMatch_(body, [
    /(?:cliente|comprador|nome)\s*[:\-]\s*([^\n\r]+)/i
  ]) || msg.getFrom();

  const hwid = firstMatch_(body, [
    /(OFP-INST-[A-Z0-9]{8,})/i,
    /(ATL-INST-[A-Z0-9]{8,})/i,
    /(MRC-INST-[A-Z0-9]{8,})/i,
    /(?:hwid|hardware\s*id|id\s*instala[cç][aã]o)\s*[:\-]\s*([A-Z0-9\-]{8,})/i
  ]);

  const programa = detectProgram_(body);

  const subjectAprovado = /pagamento\s+aprovado/i.test(subject);
  const saleKeywords = /(compra\s+confirmada|recebimento|venda\s+confirmada|infinitepay)/i;
  const isSale = subjectAprovado || saleKeywords.test(body);

  return {
    isSale: isSale,
    messageId: msg.getId(),
    threadId: msg.getThread().getId(),
    transactionId: transactionId,
    email: email,
    cliente: sanitizeText_(cliente),
    hwid: (hwid || '').toUpperCase(),
    programa: programa
  };
}

function detectProgram_(text) {
  const raw = (text || '').toLowerCase();
  if (raw.indexOf('oficina') >= 0 && raw.indexOf('pesca') >= 0) return 'Oficina_Pesca';
  if (raw.indexOf('atlas') >= 0) return 'Atlas';
  if (raw.indexOf('mercado') >= 0) return 'Mercado';
  return 'Oficina_Pesca';
}

function normalizeProgram_(programa) {
  if (HUB_CONFIG.programs.indexOf(programa) >= 0) return programa;
  return 'Oficina_Pesca';
}

function gerarLicencaPorModulo_(programa, payload) {
  const mod = MODULE_REGISTRY[programa];
  if (!mod) {
    return { ok: false, message: 'Modulo nao cadastrado', chave: '' };
  }

  const props = PropertiesService.getScriptProperties();
  const endpoint = props.getProperty(mod.endpointProp) || '';
  const token = props.getProperty(mod.tokenProp) || '';
  const hubApiKey = props.getProperty('HUB_API_KEY') || '';

  if (!endpoint) {
    return {
      ok: false,
      message: 'Endpoint do modulo nao configurado em Script Properties',
      chave: ''
    };
  }

  const headers = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = 'Bearer ' + token;
  if (hubApiKey) headers['X-OFP-Hub-Key'] = hubApiKey;

  const req = {
    method: 'post',
    contentType: 'application/json',
    muteHttpExceptions: true,
    payload: JSON.stringify(payload),
    headers: headers
  };

  try {
    const res = UrlFetchApp.fetch(endpoint, req);
    const status = res.getResponseCode();
    const text = res.getContentText() || '{}';
    let json;

    try {
      json = JSON.parse(text);
    } catch (parseErr) {
      json = { raw: text };
    }

    const chave = (json.chave || json.license_key || json.licenca || '').toString();
    const ok = status >= 200 && status < 300 && !!chave;

    return {
      ok: ok,
      message: json.message || ('HTTP ' + status),
      chave: chave,
      raw: json
    };
  } catch (err) {
    return { ok: false, message: String(err), chave: '' };
  }
}

function saveLicenseFirebase_(programa, saleData) {
  const props = PropertiesService.getScriptProperties();
  const dbUrl = (props.getProperty('FIREBASE_DATABASE_URL') || '').replace(/\/$/, '');
  const auth = props.getProperty('FIREBASE_DB_SECRET') || props.getProperty('FIREBASE_AUTH') || '';

  if (!dbUrl) {
    return { ok: false, status: 'FIREBASE_DATABASE_URL nao configurado' };
  }

  const tx = saleData.transactionId || Utilities.getUuid();
  const path = '/hub_licencas/' + encodeURIComponent(programa) + '/' + encodeURIComponent(tx) + '.json';
  const url = dbUrl + path + (auth ? ('?auth=' + encodeURIComponent(auth)) : '');

  const req = {
    method: 'put',
    contentType: 'application/json',
    muteHttpExceptions: true,
    payload: JSON.stringify(saleData)
  };

  try {
    const res = UrlFetchApp.fetch(url, req);
    const status = res.getResponseCode();
    return { ok: status >= 200 && status < 300, status: status };
  } catch (err) {
    return { ok: false, status: String(err) };
  }
}

function ensureDriveStructure_() {
  const root = getOrCreateFolderByName_(HUB_CONFIG.rootFolderName, null);
  const programFolderIds = {};
  HUB_CONFIG.programs.forEach((program) => {
    const sub = getOrCreateFolderByName_(program, root.getId());
    programFolderIds[program] = sub.getId();
  });

  return {
    rootFolderId: root.getId(),
    programFolderIds: programFolderIds
  };
}

function getOrCreateMasterSheet_(rootFolderId) {
  const existingFile = findFileByNameInsideFolder_(HUB_CONFIG.masterSheetName, rootFolderId, MimeType.GOOGLE_SHEETS);
  let ss;

  if (existingFile) {
    ss = SpreadsheetApp.openById(existingFile.getId());
  } else {
    ss = SpreadsheetApp.create(HUB_CONFIG.masterSheetName);
    const file = DriveApp.getFileById(ss.getId());
    const rootFolder = DriveApp.getFolderById(rootFolderId);
    rootFolder.addFile(file);
    DriveApp.getRootFolder().removeFile(file);
  }

  let sheet = ss.getSheetByName(HUB_CONFIG.masterSheetTab);
  if (!sheet) sheet = ss.insertSheet(HUB_CONFIG.masterSheetTab);

  return sheet;
}

function ensureMasterHeader_(sheet) {
  const headers = [
    'Data',
    'Cliente',
    'HWID',
    'Programa',
    'Status da Licenca',
    'Chave Gerada',
    'Transacao',
    'Email Comprador',
    'Origem Email ID'
  ];

  const current = sheet.getRange(1, 1, 1, headers.length).getValues()[0];
  const same = headers.join('|') === current.join('|');

  if (!same) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    sheet.setFrozenRows(1);
  }
}

function appendMasterRow_(sheet, row) {
  sheet.appendRow([
    row.data,
    row.cliente,
    row.hwid,
    row.programa,
    row.statusLicenca,
    row.chaveGerada,
    row.transacao,
    row.emailComprador,
    row.origemEmailId
  ]);
}

function saveSaleJsonInProgramFolder_(folderId, payload) {
  const tx = payload.transactionId || Utilities.getUuid();
  const name = 'sale_' + tx + '.json';
  const json = JSON.stringify(payload, null, 2);

  const folder = DriveApp.getFolderById(folderId);
  const existing = findFileByNameInsideFolder_(name, folderId, MimeType.PLAIN_TEXT);
  if (existing) {
    existing.setContent(json);
    return { id: existing.getId(), updated: true };
  }

  const file = folder.createFile(name, json, MimeType.PLAIN_TEXT);
  return { id: file.getId(), updated: false };
}

function writeHubLog_(rootFolderId, payload) {
  const rootFolder = DriveApp.getFolderById(rootFolderId);
  const logFile = findFileByNameInsideFolder_(HUB_CONFIG.logFileName, rootFolderId, MimeType.PLAIN_TEXT)
    || rootFolder.createFile(HUB_CONFIG.logFileName, '', MimeType.PLAIN_TEXT);

  const line = JSON.stringify(payload) + '\n';
  const current = logFile.getBlob().getDataAsString('UTF-8');
  logFile.setContent(current + line);
}

function ensureGmailLabel_() {
  const labelName = 'FRS/InfinitePay/Processado';
  const existing = GmailApp.getUserLabelByName(labelName);
  if (!existing) GmailApp.createLabel(labelName);
}

function isMessageProcessed_(msg) {
  const props = PropertiesService.getScriptProperties();
  const key = 'msg_' + msg.getId();
  return props.getProperty(key) === '1';
}

function markMessageProcessed_(msg, transactionId) {
  const props = PropertiesService.getScriptProperties();
  const key = 'msg_' + msg.getId();
  props.setProperty(key, '1');

  if (transactionId) {
    props.setProperty('tx_' + transactionId, msg.getId());
  }

  const label = GmailApp.getUserLabelByName('FRS/InfinitePay/Processado');
  if (label) msg.getThread().addLabel(label);
}

function installTimeTrigger_(minutes) {
  const fn = 'runHubMonitor';
  const triggers = ScriptApp.getProjectTriggers();
  const exists = triggers.some((t) => t.getHandlerFunction() === fn);
  if (!exists) {
    ScriptApp.newTrigger(fn).timeBased().everyMinutes(minutes).create();
  }
}

function getOrCreateFolderByName_(name, parentId) {
  let folders;
  if (parentId) {
    const parent = DriveApp.getFolderById(parentId);
    folders = parent.getFoldersByName(name);
    if (folders.hasNext()) return folders.next();
    return parent.createFolder(name);
  }

  folders = DriveApp.getFoldersByName(name);
  if (folders.hasNext()) return folders.next();
  return DriveApp.createFolder(name);
}

function findFileByNameInsideFolder_(name, folderId, mimeType) {
  const folder = DriveApp.getFolderById(folderId);
  const files = folder.getFilesByName(name);
  while (files.hasNext()) {
    const file = files.next();
    if (!mimeType || file.getMimeType() === mimeType) return file;
  }
  return null;
}

function firstMatch_(text, regexList) {
  for (var i = 0; i < regexList.length; i += 1) {
    const m = (text || '').match(regexList[i]);
    if (m && m[1]) return m[1].trim();
  }
  return '';
}

function sanitizeText_(value) {
  return String(value || '')
    .replace(/[\u0000-\u001F\u007F]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Utilitario para limpar dedupe antigo de mensagens processadas.
 * Execute manualmente quando quiser resetar todo estado.
 */
function resetProcessedCache() {
  const props = PropertiesService.getScriptProperties();
  const all = props.getProperties();
  const keys = Object.keys(all).filter((k) => /^msg_|^tx_/i.test(k));
  if (!keys.length) return;
  props.deleteProperty(keys[0]);
  for (var i = 1; i < keys.length; i += 1) {
    props.deleteProperty(keys[i]);
  }
  Logger.log('Cache de deduplicacao limpo. Configuracoes do projeto foram preservadas.');
}
