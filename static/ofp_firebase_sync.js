import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js";
import { getDatabase, onValue, ref, set, update } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-database.js";

let initialized = false;
let database = null;
let syncChannel = "global";
let heartbeatId = null;
let versionCheckId = null;
let licenseCheckId = null;

function redirectToBlockedPage() {
  if (window.location.pathname !== "/web/licenca-bloqueada") {
    window.location.replace("/web/licenca-bloqueada");
  }
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
    const resp = await fetch("/version.json", { cache: "no-store" });
    const data = await resp.json();
    const remoteVersion = String((data && data.versao) || "").trim();
    const localVersion = String(document.body?.dataset?.appVersion || window.__OFP_RENDERED_VERSION__ || "").trim();
    const forceUpdate = Boolean(data && data.force_update);

    if (!localVersion && remoteVersion) {
      window.__OFP_RENDERED_VERSION__ = remoteVersion;
      if (document.body && document.body.dataset) {
        document.body.dataset.appVersion = remoteVersion;
      }
      return;
    }

    if (forceUpdate || (remoteVersion && localVersion && isRemoteVersionNewer(remoteVersion, localVersion))) {
      window.location.reload();
    }
  } catch (_) {
  }
}

async function checkLicenseStatus() {
  try {
    const resp = await fetch("/api/licenca-status", { cache: "no-store" });
    const data = await resp.json();
    if (data && data.bloqueada) {
      redirectToBlockedPage();
    }
  } catch (_) {
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
      return data.config;
    }
  } catch (_) {
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
  } catch (_) {
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
    } catch (_) {
    }
  }, 25000);
}

async function initFirebaseSync() {
  if (initialized) {
    return;
  }

  const cfg = await loadFirebaseConfig();
  if (!cfg || !cfg.apiKey || !cfg.databaseURL) {
    return;
  }

  syncChannel = String(cfg.syncChannel || "global").trim() || "global";
  const app = initializeApp(cfg);
  database = getDatabase(app);
  initialized = true;

  const desktopRef = ref(database, `sync_nodes/${syncChannel}/desktop`);
  const clientRef = ref(database, `sync_nodes/${syncChannel}/apk`);

  await startHeartbeat(clientRef);

  onValue(desktopRef, (snap) => {
    const val = snap.val() || {};
    window.__OFP_DESKTOP_SYNC_STATE__ = val;
    const lic = val.license || val.licenca || {};
    if (lic && lic.blocked) {
      redirectToBlockedPage();
    }
  });
}

window.ofpRequestDesktopSync = async function ofpRequestDesktopSync(reason = "sync_now") {
  if (!initialized || !database) {
    return false;
  }
  try {
    const cmdRef = ref(database, `sync_nodes/${syncChannel}/commands`);
    await set(cmdRef, {
      acao: reason,
      source: isWebViewRuntime() ? "apk_webview" : "web_browser",
      path: window.location.pathname,
      ts: new Date().toISOString(),
    });
    return true;
  } catch (_) {
    return false;
  }
};

initFirebaseSync().catch(() => {});

checkRemoteVersion().catch(() => {});
if (versionCheckId) {
  window.clearInterval(versionCheckId);
}
versionCheckId = window.setInterval(() => {
  checkRemoteVersion().catch(() => {});
}, 60000);

checkLicenseStatus().catch(() => {});
if (licenseCheckId) {
  window.clearInterval(licenseCheckId);
}
licenseCheckId = window.setInterval(() => {
  checkLicenseStatus().catch(() => {});
}, 30000);
