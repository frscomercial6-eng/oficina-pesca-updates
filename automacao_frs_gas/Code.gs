/**
 * Hub de Automacao FRS Solutions (Google Apps Script)
 *
 * Escopo:
 * - Monitorar e-mails da InfinitePay no Gmail
 * - Garantir estrutura de pastas no Drive
 * - Registrar vendas na planilha central
 * - Gerar token de acesso temporário assinado
 * - Salvar resultado no log e no Firebase
 *
 * Configurar as propriedades em: Project Settings > Script properties
 */

const HUB_CONFIG = {
  ecosystemVersion: '1.0.34',
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
    tokenGerado: 'TOKEN_GERADO',
    erroGeracao: 'ERRO_GERACAO'
  }
};

const TOKEN_CONFIG = {
  fileName: 'acesso.token',
  daysValid: 30,
  signaturePrefix: 'OFP-TKN'
};
/**
 * Registro de adaptadores por programa.
 * Cada modulo aponta para o proprio endpoint de geracao.
 * Assim, a regra de licenca continua isolada por app.
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
  const userId = normalizeUserId_(sale);

  const baseRow = {
    data: now,
    cliente: sale.cliente || sale.email || 'NAO_IDENTIFICADO',
    hwid: hwid,
    programa: programa,
    statusLicenca: userId ? HUB_CONFIG.status.novo : HUB_CONFIG.status.aguardandoHwid,
    tokenGerado: '',
    transacao: sale.transactionId || '',
    emailComprador: sale.email || '',
    origemEmailId: sale.messageId
  };

  if (!userId) {
    appendMasterRow_(sheet, baseRow);
    writeHubLog_(structure.rootFolderId, {
      ts: now.toISOString(),
      level: 'WARN',
      action: 'SALE_REGISTERED_WITHOUT_USERID',
      transactionId: sale.transactionId || '',
      programa: programa,
      cliente: baseRow.cliente
    });
    return;
  }

  const tokenRes = gerarEPublicarTokenViaHub_(programa, sale, structure, userId);
  baseRow.statusLicenca = tokenRes.ok ? HUB_CONFIG.status.tokenGerado : HUB_CONFIG.status.erroGeracao;
  baseRow.tokenGerado = tokenRes.tokenPreview || '';
  appendMasterRow_(sheet, baseRow);

  const saleFileMeta = saveSaleJsonInProgramFolder_(structure.programFolderIds[programa], {
    ecosystemVersion: HUB_CONFIG.ecosystemVersion,
    createdAt: now.toISOString(),
    programa: programa,
    cliente: baseRow.cliente,
    hwid: hwid,
    userId: userId,
    transactionId: baseRow.transacao,
    statusLicenca: baseRow.statusLicenca,
    tokenGerado: baseRow.tokenGerado,
    emailComprador: baseRow.emailComprador,
    origemEmailId: baseRow.origemEmailId,
    tokenFolderId: tokenRes.folderId || ''
  });

  const firebaseRes = saveLicenseFirebase_(programa, {
    ecosystemVersion: HUB_CONFIG.ecosystemVersion,
    createdAt: now.toISOString(),
    cliente: baseRow.cliente,
    hwid: hwid,
    userId: userId,
    programa: programa,
    statusLicenca: baseRow.statusLicenca,
    tokenGerado: baseRow.tokenGerado,
    transactionId: baseRow.transacao,
    emailComprador: baseRow.emailComprador,
    source: 'hub_gas'
  });

  writeHubLog_(structure.rootFolderId, {
    ts: now.toISOString(),
    level: tokenRes.ok ? 'INFO' : 'ERROR',
    action: 'SALE_TOKEN_PROCESSED',
    ecosystemVersion: HUB_CONFIG.ecosystemVersion,
    programa: programa,
    cliente: baseRow.cliente,
    userId: userId,
    hwid: hwid,
    transactionId: baseRow.transacao,
    statusLicenca: baseRow.statusLicenca,
    tokenPreview: tokenRes.tokenPreview || '',
    tokenFolderId: tokenRes.folderId || '',
    saleFileId: saleFileMeta.id,
    firebaseOk: firebaseRes.ok,
    firebaseStatus: firebaseRes.status,
    hubMensagem: tokenRes.message
  });
}

function normalizeUserId_(sale) {
  const fromEmail = String(sale.email || '').trim().toLowerCase();
  if (fromEmail) return fromEmail;
  const fromTx = String(sale.transactionId || '').trim().toUpperCase();
  if (fromTx) return 'tx:' + fromTx;
  const fromHwid = String(sale.hwid || '').trim().toUpperCase();
  if (fromHwid) return 'hwid:' + fromHwid;
  return '';
}

function gerarEPublicarTokenViaHub_(programa, sale, structure, userId) {
  const props = PropertiesService.getScriptProperties();
  const secret = (props.getProperty('TOKEN_SECRET') || props.getProperty('OFP_LICENCA_SECRET') || '').trim();
  if (!secret) {
    return { ok: false, message: 'TOKEN_SECRET não configurado no Hub.', tokenPreview: '', folderId: '' };
  }

  const token = gerarTokenAssinado_(userId, secret, TOKEN_CONFIG.daysValid);
  const folderInfo = resolverPastaDestinoToken_(programa, sale, structure);
  if (!folderInfo.ok) {
    return { ok: false, message: folderInfo.message, tokenPreview: '', folderId: '' };
  }

  const upload = upsertArquivoToken_(folderInfo.folderId, TOKEN_CONFIG.fileName, token);
  if (!upload.ok) {
    return { ok: false, message: upload.message, tokenPreview: '', folderId: folderInfo.folderId };
  }

  return {
    ok: true,
    message: 'Token gerado e enviado ao Drive do cliente.',
    tokenPreview: token.substring(0, 24) + '...',
    folderId: folderInfo.folderId
  };
}

function gerarTokenAssinado_(userId, secret, diasValidade) {
  const now = new Date();
  const exp = new Date(now.getTime() + (Math.max(1, Number(diasValidade || 30)) * 24 * 60 * 60 * 1000));
  const payload = {
    uid: String(userId || '').trim().toLowerCase(),
    iat: Utilities.formatDate(now, 'GMT', 'yyyy-MM-dd'),
    exp: Utilities.formatDate(exp, 'GMT', 'yyyy-MM-dd'),
    ver: 1
  };
  const payloadJson = JSON.stringify(payload);
  const payloadB64 = Utilities.base64EncodeWebSafe(payloadJson).replace(/=+$/g, '');
  const assinatura = assinarPayloadToken_(payloadB64, secret);
  return TOKEN_CONFIG.signaturePrefix + '-' + payloadB64 + '-' + assinatura;
}

function assinarPayloadToken_(payloadB64, secret) {
  const signature = Utilities.computeHmacSha256Signature(payloadB64, secret);
  const hex = signature.map(function(b) {
    const v = (b < 0 ? b + 256 : b).toString(16);
    return v.length === 1 ? '0' + v : v;
  }).join('').toUpperCase();
  return hex.substring(0, 20);
}

function resolverPastaDestinoToken_(programa, sale, structure) {
  // Prioridade: ID explícito no e-mail > mapa por e-mail em Script Properties > fallback pasta do programa.
  const explicitFolderId = String(sale.driveFolderId || '').trim();
  if (explicitFolderId) {
    try {
      DriveApp.getFolderById(explicitFolderId);
      return { ok: true, folderId: explicitFolderId, message: 'Usando pasta explícita no payload.' };
    } catch (err) {
      return { ok: false, folderId: '', message: 'driveFolderId informado é inválido ou sem permissão.' };
    }
  }

  const props = PropertiesService.getScriptProperties();
  const mapRaw = props.getProperty('DRIVE_CLIENT_FOLDER_MAP_JSON') || '{}';
  let folderMap = {};
  try {
    folderMap = JSON.parse(mapRaw);
  } catch (_err) {
    folderMap = {};
  }

  const email = String(sale.email || '').trim().toLowerCase();
  const mappedFolderId = email ? String(folderMap[email] || '').trim() : '';
  if (mappedFolderId) {
    try {
      DriveApp.getFolderById(mappedFolderId);
      return { ok: true, folderId: mappedFolderId, message: 'Usando pasta mapeada por e-mail.' };
    } catch (err2) {
      return { ok: false, folderId: '', message: 'Pasta mapeada no DRIVE_CLIENT_FOLDER_MAP_JSON é inválida.' };
    }
  }

  // Fallback operacional: mantém token na estrutura FRS_Solutions/<Programa>
  const folderId = structure.programFolderIds[programa];
  if (!folderId) {
    return { ok: false, folderId: '', message: 'Pasta de programa não encontrada para salvar token.' };
  }
  return { ok: true, folderId: folderId, message: 'Usando pasta padrão do programa no Hub.' };
}

function upsertArquivoToken_(folderId, fileName, content) {
  try {
    const folder = DriveApp.getFolderById(folderId);
    const existing = findFileByNameInsideFolder_(fileName, folderId, MimeType.PLAIN_TEXT);
    if (existing) {
      existing.setContent(content);
      return { ok: true, message: 'Token atualizado no Drive.' };
    }
    folder.createFile(fileName, content, MimeType.PLAIN_TEXT);
    return { ok: true, message: 'Token criado no Drive.' };
  } catch (err) {
    return { ok: false, message: String(err) };
  }
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

  const driveFolderId = firstMatch_(body, [
    /(?:drive[_\s-]*folder[_\s-]*id|pasta[_\s-]*drive[_\s-]*id)\s*[:\-]\s*([a-zA-Z0-9_-]{12,})/i
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
    driveFolderId: (driveFolderId || '').trim(),
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
    'Status do Token',
    'Token Gerado (preview)',
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
    row.tokenGerado,
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
