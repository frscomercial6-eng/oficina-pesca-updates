import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js";
import { getDatabase, onValue, ref, set, update } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-database.js";

let initialized = false;
let database = null;
let syncChannel = "global";
let heartbeatId = null;
let versionCheckId = null;
let licenseCheckId = null;
let updateModalTimer = null;
let updateModalShown = false;
let bridgeLastSeenTs = "";
let statusBarTimer = null;
let statusBarState = "connecting";
let statusBarMessage = "Conectando";
let statusBarDotColor = "#F59E0B";

function logSyncError(context, error) {
  const msg = error && error.message ? error.message : String(error || "erro_desconhecido");
  console.error(`[ofp-webview] ${context}: ${msg}`, error);
}

function ensureConnectionBar() {
  let bar = document.getElementById("ofp-connection-bar");
  if (bar) return bar;

  bar = document.createElement("div");
  bar.id = "ofp-connection-bar";
  bar.style.cssText = [
    "position:fixed",
    "top:12px",
    "left:50%",
    "transform:translateX(-50%)",
    "z-index:2147483647",
    "display:flex",
    "align-items:center",
    "gap:8px",
    "padding:8px 12px",
    "border-radius:999px",
    "background:rgba(10,17,26,.82)",
    "backdrop-filter:blur(10px)",
    "box-shadow:0 8px 24px rgba(0,0,0,.22)",
    "border:1px solid rgba(255,255,255,.08)",
    "color:#f3f4f6",
    "font:600 12px/1.1 'Segoe UI',Tahoma,sans-serif",
    "letter-spacing:.01em",
    "pointer-events:none",
    "max-width:calc(100vw - 24px)",
    "white-space:nowrap",
  ].join(";");

  const dot = document.createElement("span");
  dot.id = "ofp-connection-bar-dot";
  dot.style.cssText = [
    "width:8px",
    "height:8px",
    "border-radius:999px",
    "background:#F59E0B",
    "box-shadow:0 0 0 4px rgba(245,158,11,.12)",
    "flex:0 0 auto",
  ].join(";");

  const text = document.createElement("span");
  text.id = "ofp-connection-bar-text";
  text.textContent = "Conectando";

  bar.appendChild(dot);
  bar.appendChild(text);
  document.body.appendChild(bar);
  return bar;
}

function applyConnectionBar(state, message, dotColor) {
  const safeState = String(state || "connecting").toLowerCase();
  const safeMessage = String(message || (safeState === "error" ? "Erro de Conexão" : "Conectado"));
  const safeDotColor = String(dotColor || (safeState === "error" ? "#EF4444" : "#22C55E"));

  statusBarState = safeState;
  statusBarMessage = safeMessage;
  statusBarDotColor = safeDotColor;

  const bar = ensureConnectionBar();
  const dot = document.getElementById("ofp-connection-bar-dot");
  const text = document.getElementById("ofp-connection-bar-text");

  if (dot) {
    dot.style.background = safeDotColor;
    dot.style.boxShadow = safeState === "error"
      ? "0 0 0 4px rgba(239,68,68,.12)"
      : "0 0 0 4px rgba(34,197,94,.12)";
  }

  if (text) {
    text.textContent = safeState === "error" ? "Erro de Conexão" : "Conectado";
  }

  bar.setAttribute("data-state", safeState);
  bar.title = safeMessage;
}

window.ofpApplyConnectionStatus = function ofpApplyConnectionStatus(payload = {}) {
  try {
    applyConnectionBar(payload.state, payload.text, payload.dotColor);
    return true;
  } catch (error) {
    logSyncError("Falha ao aplicar status de conexão", error);
    return false;
  }
};

function setConnectionState(state, message, dotColor) {
  applyConnectionBar(state, message, dotColor);

  if (window.OficinaBootstrap && typeof window.OficinaBootstrap.setStatus === "function") {
    try {
      window.OficinaBootstrap.setStatus(String(state || "connecting"), String(message || ""), String(dotColor || ""));
    } catch (error) {
      logSyncError("Falha ao notificar bridge nativa", error);
    }
  }
}

function redirectToBlockedPage() {
  console.warn("[ofp-webview] Licença bloqueada detectada. Redirecionando para tela de bloqueio.");
  if (window.location.pathname !== "/web/licenca-bloqueada") {
    window.location.replace("/web/licenca-bloqueada");
  }
}

function isCriticalInteractionActive() {
  const active = document.activeElement;
  const editing = active && ["INPUT", "TEXTAREA", "SELECT"].includes(active.tagName);
  const criticalPath = ["/web/os", "/web/financeiro"].some((path) => window.location.pathname.startsWith(path));
  return Boolean(editing || criticalPath);
}

function ensureUpdateModal() {
  let modal = document.getElementById("ofp-update-modal");
  if (modal) return modal;

  modal = document.createElement("div");
  modal.id = "ofp-update-modal";
  modal.style.cssText = "position:fixed;inset:0;background:rgba(15,23,32,.78);display:none;align-items:center;justify-content:center;z-index:99999;padding:16px;";
  modal.innerHTML = [
    '<div style="max-width:520px;width:100%;background:#16202b;color:#ecf0f1;border-radius:18px;padding:24px;box-shadow:0 12px 40px rgba(0,0,0,.45);font-family:Segoe UI,Arial,sans-serif;">',
    '<div style="font-size:1.25rem;font-weight:700;color:#f39c12;margin-bottom:10px;">Atualização disponível</div>',
    '<div id="ofp-update-modal-text" style="font-size:0.98rem;color:#d6dde5;line-height:1.5;">Uma nova versão do sistema foi detectada.</div>',
    '<div id="ofp-update-modal-countdown" style="font-size:0.9rem;color:#93c5fd;margin-top:12px;"></div>',
    '<div style="display:flex;gap:10px;justify-content:flex-end;margin-top:18px;">',
    '<button id="ofp-update-modal-btn" style="background:#16a34a;color:#fff;border:0;border-radius:10px;padding:10px 16px;font-weight:600;cursor:pointer;">Atualizar agora</button>',
    '</div>',
    '</div>'
  ].join("");
  document.body.appendChild(modal);
  document.getElementById("ofp-update-modal-btn")?.addEventListener("click", () => window.location.reload());
  return modal;
}

function showUpdateModal(remoteVersion, localVersion, forceUpdate) {
  if (updateModalShown) return;
  updateModalShown = true;
  const modal = ensureUpdateModal();
  const text = document.getElementById("ofp-update-modal-text");
  const countdown = document.getElementById("ofp-update-modal-countdown");
  const critical = isCriticalInteractionActive();
  let seconds = forceUpdate ? 8 : (critical ? 20 : 5);

  if (text) {
    text.textContent = `Nova versão detectada (${remoteVersion} > ${localVersion || "em uso"}). A interface será recarregada para sincronizar com a atualização.`;
  }
  modal.style.display = "flex";

  if (updateModalTimer) {
    window.clearInterval(updateModalTimer);
  }

  if (countdown) {
    countdown.textContent = critical
      ? `Processo sensível detectado. Recarregando em ${seconds}s, ou clique em 'Atualizar agora'.`
      : `Recarregando automaticamente em ${seconds}s.`;
  }

  updateModalTimer = window.setInterval(() => {
    seconds -= 1;
    if (countdown) {
      countdown.textContent = critical
        ? `Processo sensível detectado. Recarregando em ${seconds}s, ou clique em 'Atualizar agora'.`
        : `Recarregando automaticamente em ${seconds}s.`;
    }
    if (seconds <= 0) {
      window.clearInterval(updateModalTimer);
      window.location.reload();
    }
  }, 1000);
}

function parseVersionTuple(value) {
  return String(value || "0")
    .split(".")
    .map((part) => Number.parseInt(part, 10) || 0);
}

function isRemoteVersionNewer(remoteVersion, localVersion) {
  const remote = parseVersionTuple(remoteVersion);
  const local = parseVersionTuple(localVersion);
  const size = Math.max(remote.length, local.length);
  while (remote.length < size) remote.push(0);
  while (local.length < size) local.push(0);
  for (let i = 0; i < size; i += 1) {
    if (remote[i] > local[i]) return true;
    if (remote[i] < local[i]) return false;
  }
  return false;
}

async function checkRemoteVersion() {
  try {
    console.debug("[ofp-webview] Iniciando checagem de versão remota.");
    const resp = await fetch("/version.json", { cache: "no-store" });
    const data = await resp.json();
    const remoteVersion = String((data && data.versao) || "").trim();
    const localVersion = String(document.body?.dataset?.appVersion || window.__OFP_RENDERED_VERSION__ || "").trim();
    const forceUpdate = Boolean(data && data.force_update);

    console.debug(
      `[ofp-webview] Version check -> local='${localVersion || "(vazio)"}', remote='${remoteVersion || "(vazio)"}', force=${forceUpdate}`
    );

    if (!localVersion && remoteVersion) {
      window.__OFP_RENDERED_VERSION__ = remoteVersion;
      if (document.body && document.body.dataset) {
        document.body.dataset.appVersion = remoteVersion;
      }
      console.info(`[ofp-webview] Versão local ausente. Usando versão remota '${remoteVersion}' como base inicial.`);
      return;
    }

    if (forceUpdate || (remoteVersion && localVersion && isRemoteVersionNewer(remoteVersion, localVersion))) {
      console.info(`[ofp-webview] Nova versão detectada (${remoteVersion} > ${localVersion}). Recarregando interface.`);
      showUpdateModal(remoteVersion, localVersion, forceUpdate);
      return;
    }
    console.debug("[ofp-webview] Nenhuma atualização obrigatória detectada.");
  } catch (error) {
    logSyncError("Falha na checagem de versão remota", error);
  }
}

async function checkLicenseStatus() {
  try {
    console.debug("[ofp-webview] Iniciando checagem de status de licença.");
    const resp = await fetch("/api/licenca-status", { cache: "no-store" });
    const data = await resp.json();
    const ativa = Boolean(data && (data.ativa || data.licenca_ativa));
    const bloqueada = Boolean(data && data.bloqueada);
    console.debug(`[ofp-webview] Licença -> ativa=${ativa}, bloqueada=${bloqueada}`);
    if (data && data.bloqueada) {
      console.warn("[ofp-webview] Endpoint de licença retornou bloqueio.");
      redirectToBlockedPage();
    }
  } catch (error) {
    logSyncError("Falha na checagem de licença", error);
  }
}

async function isLicenseActiveForSync() {
  try {
    const resp = await fetch("/api/licenca-status", { cache: "no-store" });
    const data = await resp.json();
    const ativa = Boolean(data && (data.ativa || data.licenca_ativa));
    const bloqueada = Boolean(data && data.bloqueada);
    console.debug(`[ofp-webview] Permissão para sync Firebase -> ativa=${ativa}, bloqueada=${bloqueada}`);
    return ativa && !bloqueada;
  } catch (error) {
    logSyncError("Falha ao avaliar licença para sync", error);
    return false;
  }
}

async function loadFirebaseConfig() {
  if (window.__OFP_FIREBASE_CONFIG__) {
    return window.__OFP_FIREBASE_CONFIG__;
  }
  try {
    const resp = await fetch("/api/firebase-config", { cache: "no-store" });
    const data = await resp.json();
    if (data && data.ok && data.config) {
      window.__OFP_FIREBASE_CONFIG__ = data.config;
      console.info("[ofp-webview] Config Firebase carregada via /api/firebase-config.");
      return data.config;
    }
    console.warn("[ofp-webview] /api/firebase-config retornou payload inválido ou incompleto.");
  } catch (error) {
    logSyncError("Falha ao carregar configuração Firebase", error);
  }
  return null;
}

function isWebViewRuntime() {
  return typeof window.OficinaFirebase !== "undefined" || /wv|Android/i.test(navigator.userAgent || "");
}

async function startHeartbeat(apkRef) {
  try {
    await set(apkRef, {
      status: "online",
      opened_at: new Date().toISOString(),
      platform: isWebViewRuntime() ? "apk_webview" : "web_browser",
      current_path: window.location.pathname,
    });
    console.debug("[ofp-webview] Heartbeat inicial enviado.");
    setConnectionState("ok", "Conectado", "#22C55E");
  } catch (error) {
    logSyncError("Falha no heartbeat inicial", error);
    setConnectionState("error", "Erro de Conexão", "#EF4444");
  }

  if (heartbeatId) {
    window.clearInterval(heartbeatId);
  }

  heartbeatId = window.setInterval(async () => {
    try {
      await update(apkRef, {
        last_seen: new Date().toISOString(),
        current_path: window.location.pathname,
        status: "online",
      });
    } catch (error) {
      logSyncError("Falha no heartbeat periódico", error);
      setConnectionState("error", "Erro de Conexão", "#EF4444");
    }
  }, 25000);
}

async function initFirebaseSync() {
  if (initialized) {
    console.debug("[ofp-webview] initFirebaseSync ignorado: já inicializado.");
    return true;
  }

  setConnectionState("connecting", "Conectando", "#F59E0B");

  const licencaAtiva = await isLicenseActiveForSync();
  if (!licencaAtiva) {
    console.warn("[ofp-webview] Comunicação Firebase bloqueada: licença inativa.");
    setConnectionState("error", "Erro de Conexão", "#EF4444");
    return false;
  }

  const cfg = await loadFirebaseConfig();
  if (!cfg || !cfg.apiKey || !cfg.databaseURL) {
    console.error("[ofp-webview] Configuração Firebase inválida. apiKey/databaseURL ausentes.", cfg);
    setConnectionState("error", "Erro de Conexão", "#EF4444");
    return false;
  }

  syncChannel = String(cfg.syncChannel || "global").trim() || "global";
  console.info(`[ofp-webview] Inicializando Firebase sync. channel='${syncChannel}'.`);
  const app = initializeApp(cfg);
  database = getDatabase(app);
  initialized = true;

  if (statusBarTimer) {
    window.clearInterval(statusBarTimer);
  }
  statusBarTimer = window.setInterval(() => {
    applyConnectionBar(statusBarState, statusBarMessage, statusBarDotColor);
  }, 60000);

  const desktopRef = ref(database, `sync_nodes/${syncChannel}/desktop`);
  const clientRef = ref(database, `sync_nodes/${syncChannel}/apk`);
  const bridgeRef = ref(database, `sync_nodes/${syncChannel}/bridge`);

  await startHeartbeat(clientRef);

  onValue(desktopRef, (snap) => {
    const val = snap.val() || {};
    window.__OFP_DESKTOP_SYNC_STATE__ = val;
    console.debug("[ofp-webview] Snapshot desktop recebido.", val);
    const lic = val.license || val.licenca || {};
    if ((lic && lic.blocked) || Boolean(val.license_bloqueada)) {
      console.warn("[ofp-webview] Bloqueio de licença recebido via Firebase.");
      redirectToBlockedPage();
    }
  });

  onValue(bridgeRef, (snap) => {
    const val = snap.val() || {};
    if (!val || typeof val !== "object") return;

    for (const key of Object.keys(val)) {
      const item = val[key] || {};
      const source = String(item.source || "").toLowerCase();
      const action = String(item.acao || "").toLowerCase();
      const ts = String(item.ts || "").trim();

      if (!source.startsWith("desktop")) continue;
      if (ts && ts === bridgeLastSeenTs) continue;

      if (action === "desktop_drive_synced") {
        bridgeLastSeenTs = ts;
        console.info("[ofp-webview] Evento Desktop recebido: banco sincronizado no Drive.");
      }
    }
  });

  console.info("[ofp-webview] Firebase sync inicializado com sucesso.");
  setConnectionState("ok", "Conectado", "#22C55E");
  return true;
}

function nextBridgeId(prefix = "apk") {
  const rnd = Math.random().toString(36).slice(2, 10);
  return `${prefix}_${Date.now()}_${rnd}`;
}

window.ofpRequestDesktopSync = async function ofpRequestDesktopSync(reason = "sync_now") {
  if (!initialized || !database) {
    console.warn("[ofp-webview] ofpRequestDesktopSync ignorado: Firebase não inicializado.");
    return false;
  }
  try {
    const eventId = nextBridgeId("apk_sync");
    const cmdRef = ref(database, `sync_nodes/${syncChannel}/bridge/${eventId}`);
    await set(cmdRef, {
      acao: reason,
      source: isWebViewRuntime() ? "apk_webview" : "web_browser",
      path: window.location.pathname,
      ts: new Date().toISOString(),
    });
    console.info(`[ofp-webview] Solicitação de sync enviada. reason='${reason}', channel='${syncChannel}'.`);
    return true;
  } catch (error) {
    logSyncError("Falha ao solicitar sync do desktop", error);
    return false;
  }
};

window.ofpPushBridgePayload = async function ofpPushBridgePayload(payload = {}, reason = "apk_data_push") {
  if (!initialized || !database) {
    console.warn("[ofp-webview] ofpPushBridgePayload ignorado: Firebase não inicializado.");
    return false;
  }
  try {
    const eventId = nextBridgeId("apk_data");
    const cmdRef = ref(database, `sync_nodes/${syncChannel}/bridge/${eventId}`);
    await set(cmdRef, {
      acao: reason,
      source: isWebViewRuntime() ? "apk_webview" : "web_browser",
      path: window.location.pathname,
      ts: new Date().toISOString(),
      dados: payload || {},
    });
    console.info(`[ofp-webview] Payload bridge enviado. reason='${reason}', channel='${syncChannel}'.`);
    return true;
  } catch (error) {
    logSyncError("Falha ao enviar payload bridge", error);
    return false;
  }
};

initFirebaseSync().catch((error) => {
  logSyncError("Falha fatal no initFirebaseSync", error);
  setConnectionState("error", "Erro de Conexão", "#EF4444");
});

checkRemoteVersion().catch((error) => {
  logSyncError("Falha fatal no checkRemoteVersion inicial", error);
});
if (versionCheckId) {
  window.clearInterval(versionCheckId);
}
versionCheckId = window.setInterval(() => {
  checkRemoteVersion().catch((error) => {
    logSyncError("Falha no checkRemoteVersion periódico", error);
  });
}, 60000);

checkLicenseStatus().catch((error) => {
  logSyncError("Falha fatal no checkLicenseStatus inicial", error);
});
if (licenseCheckId) {
  window.clearInterval(licenseCheckId);
}
licenseCheckId = window.setInterval(() => {
  checkLicenseStatus().catch((error) => {
    logSyncError("Falha no checkLicenseStatus periódico", error);
  });
}, 30000);
