const form = document.getElementById("monitor-form");
const platformSelect = document.getElementById("platform");
const customUrlWrap = document.getElementById("custom-url-wrap");
const customUrlInput = document.getElementById("custom_url");
const roomIdInput = document.getElementById("room_id");
const enableScanLoginInput = document.getElementById("enable_scan_login");
const serverTypeInput = document.getElementById("server_type");
const uidInput = document.getElementById("uid");
const tokenInput = document.getElementById("token");
const usernameInput = document.getElementById("username");
const serverTypeWrap = document.getElementById("server-type-wrap");
const uidWrap = document.getElementById("uid-wrap");
const tokenWrap = document.getElementById("token-wrap");
const usernameWrap = document.getElementById("username-wrap");
const liveFrameImage = document.getElementById("live-frame");
const frameStatus = document.getElementById("frame-status");
const logBox = document.getElementById("event-log");
const accountNameInput = document.getElementById("account_name");
const accountsTbody = document.getElementById("accounts-tbody");
const accountsEmptyTip = document.getElementById("accounts-empty-tip");

const fields = {
  runningBadge: document.getElementById("running-badge"),
  session_id: document.getElementById("session_id"),
  platform_text: document.getElementById("platform_text"),
  room_text: document.getElementById("room_text"),
  detections_count: document.getElementById("detections_count"),
  last_game_name: document.getElementById("last_game_name"),
  last_ticket: document.getElementById("last_ticket"),
  last_detection_at: document.getElementById("last_detection_at"),
  last_qr_text: document.getElementById("last_qr_text"),
  last_scan_login_ok: document.getElementById("last_scan_login_ok"),
  last_scan_login_stage: document.getElementById("last_scan_login_stage"),
  last_scan_login_message: document.getElementById("last_scan_login_message"),
  room_url: document.getElementById("room_url"),
  stream_url: document.getElementById("stream_url"),
  last_frame_at: document.getElementById("last_frame_at"),
  last_preview_at: document.getElementById("last_preview_at"),
  last_error: document.getElementById("last_error"),
};

const startButton = document.getElementById("start-btn");
const stopButton = document.getElementById("stop-btn");
const refreshButton = document.getElementById("refresh-btn");
const saveAccountButton = document.getElementById("save-account-btn");
const updateAccountButton = document.getElementById("update-account-btn");
const deleteAccountButton = document.getElementById("delete-account-btn");
const setDefaultAccountButton = document.getElementById("set-default-account-btn");
const reloadAccountsButton = document.getElementById("reload-accounts-btn");

let ws = null;
let wsTimer = null;
let frameTimer = null;
let accounts = [];
let defaultAccountId = null;
let selectedAccountId = null;

function textOrDash(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return String(value);
}

function formatTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString();
}

function appendLog(type, payload, time) {
  const row = document.createElement("div");
  row.className = "log-item";

  const meta = document.createElement("div");
  meta.className = "log-meta";
  meta.innerHTML = `<span class="log-type">${type}</span> · ${formatTime(time)}`;

  const text = document.createElement("div");
  text.className = "log-text";
  text.textContent = typeof payload === "string" ? payload : JSON.stringify(payload, null, 2);

  row.append(meta, text);
  logBox.prepend(row);

  const children = logBox.querySelectorAll(".log-item");
  for (let i = 80; i < children.length; i += 1) {
    children[i].remove();
  }
}

function applyStatus(status) {
  fields.runningBadge.textContent = status.running ? "RUNNING" : "IDLE";
  fields.runningBadge.className = status.running ? "badge badge-running" : "badge badge-idle";

  fields.session_id.textContent = textOrDash(status.session_id);
  fields.platform_text.textContent = textOrDash(status.platform);
  fields.room_text.textContent = textOrDash(status.room_id);
  fields.detections_count.textContent = textOrDash(status.detections_count ?? 0);
  fields.last_game_name.textContent = textOrDash(status.last_game_name);
  fields.last_ticket.textContent = textOrDash(status.last_ticket);
  fields.last_detection_at.textContent = formatTime(status.last_detection_at);
  fields.last_qr_text.textContent = textOrDash(status.last_qr_text);
  if (status.last_scan_login_ok === true) {
    fields.last_scan_login_ok.textContent = "SUCCESS";
  } else if (status.last_scan_login_ok === false) {
    fields.last_scan_login_ok.textContent = "FAILED";
  } else {
    fields.last_scan_login_ok.textContent = "-";
  }
  fields.last_scan_login_stage.textContent = textOrDash(status.last_scan_login_stage);
  fields.last_scan_login_message.textContent = textOrDash(status.last_scan_login_message);
  fields.room_url.textContent = textOrDash(status.room_url);
  fields.stream_url.textContent = textOrDash(status.stream_url);
  fields.last_frame_at.textContent = formatTime(status.last_frame_at);
  fields.last_preview_at.textContent = formatTime(status.last_preview_at);
  fields.last_error.textContent = textOrDash(status.last_error);

  if (status.running) {
    startFramePolling();
  } else {
    stopFramePolling("未开始监视");
  }
}

async function callApi(path, init) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
    },
    ...init,
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return data;
}

function requireValue(value, label) {
  const result = String(value || "").trim();
  if (!result) {
    throw new Error(`${label}不能为空`);
  }
  return result;
}

function collectAccountPayload() {
  const payload = {
    name: requireValue(accountNameInput.value, "账号备注"),
    server_type: String(serverTypeInput.value || "official").trim(),
    uid: requireValue(uidInput.value, "UID"),
    token: requireValue(tokenInput.value, "Token"),
  };

  const username = String(usernameInput.value || "").trim();
  if (payload.server_type === "bh3_bilibili") {
    payload.username = requireValue(username, "用户名");
  } else if (username) {
    payload.username = username;
  }

  return payload;
}

function applyAccountToForm(account) {
  accountNameInput.value = account.name || "";
  enableScanLoginInput.checked = true;
  serverTypeInput.value = account.server_type || "official";
  uidInput.value = account.uid || "";
  tokenInput.value = account.token || "";
  usernameInput.value = account.username || "";
  updateScanLoginVisibility();
}

function setSelectedAccount(accountId, { apply = true } = {}) {
  selectedAccountId = accountId;
  renderAccounts();
  const account = accounts.find((item) => item.id === accountId);
  if (apply && account) {
    applyAccountToForm(account);
  }
}

function renderAccounts() {
  accountsTbody.innerHTML = "";

  if (!accounts.length) {
    accountsEmptyTip.style.display = "block";
    return;
  }

  accountsEmptyTip.style.display = "none";
  for (const account of accounts) {
    const tr = document.createElement("tr");
    tr.className = "account-row";
    if (account.id === selectedAccountId) {
      tr.classList.add("selected");
    }

    const defaultCell = document.createElement("td");
    defaultCell.textContent = account.id === defaultAccountId ? "是" : "";

    const nameCell = document.createElement("td");
    nameCell.textContent = account.name || "-";

    const typeCell = document.createElement("td");
    typeCell.textContent = account.server_type === "bh3_bilibili" ? "崩坏3 B服" : "官服";

    const uidCell = document.createElement("td");
    uidCell.textContent = account.uid || "-";

    const updatedCell = document.createElement("td");
    updatedCell.textContent = formatTime(account.updated_at);

    tr.append(defaultCell, nameCell, typeCell, uidCell, updatedCell);
    tr.addEventListener("click", () => {
      setSelectedAccount(account.id, { apply: true });
    });
    accountsTbody.append(tr);
  }
}

async function refreshAccounts({ autoApplyDefault = true } = {}) {
  const data = await callApi("/api/accounts", { method: "GET" });
  accounts = Array.isArray(data.accounts) ? data.accounts : [];
  defaultAccountId = data.default_account_id || null;

  if (selectedAccountId && !accounts.some((item) => item.id === selectedAccountId)) {
    selectedAccountId = null;
  }

  if (!selectedAccountId && autoApplyDefault && defaultAccountId) {
    selectedAccountId = defaultAccountId;
    const defaultAccount = accounts.find((item) => item.id === defaultAccountId);
    if (defaultAccount) {
      applyAccountToForm(defaultAccount);
      accountNameInput.value = defaultAccount.name || "";
    }
  }

  renderAccounts();
}

async function refreshStatus() {
  try {
    const status = await callApi("/api/monitor/status", { method: "GET" });
    applyStatus(status);
  } catch (error) {
    appendLog("status_error", String(error), new Date().toISOString());
  }
}

function getFormPayload() {
  const formData = new FormData(form);
  const enableScanLogin = Boolean(formData.get("enable_scan_login"));
  const payload = {
    platform: formData.get("platform"),
    room_id: String(formData.get("room_id") || "").trim(),
    quality: String(formData.get("quality") || "best").trim() || "best",
    scan_interval_ms: Number(formData.get("scan_interval_ms") || 500),
    auto_stop_on_ticket: Boolean(formData.get("auto_stop_on_ticket")),
    enable_scan_login: enableScanLogin,
  };

  if (payload.platform === "custom") {
    payload.custom_url = String(formData.get("custom_url") || "").trim();
  }

  if (enableScanLogin) {
    payload.server_type = String(formData.get("server_type") || "").trim();
    payload.uid = String(formData.get("uid") || "").trim();
    payload.token = String(formData.get("token") || "").trim();
    const username = String(formData.get("username") || "").trim();
    if (username) {
      payload.username = username;
    }
  }

  return payload;
}

async function startMonitor() {
  const payload = getFormPayload();
  const status = await callApi("/api/monitor/start", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  applyStatus(status);
  appendLog("start_ok", payload, new Date().toISOString());
}

async function stopMonitor() {
  const status = await callApi("/api/monitor/stop", { method: "POST" });
  applyStatus(status);
  appendLog("stop_ok", "monitor stop requested", new Date().toISOString());
}

function connectWs() {
  if (ws) {
    ws.close();
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${protocol}://${window.location.host}/ws/events`);

  ws.onopen = () => {
    appendLog("ws_connected", "websocket connected", new Date().toISOString());
    if (wsTimer) {
      clearInterval(wsTimer);
    }
    wsTimer = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send("ping");
      }
    }, 15000);
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      appendLog(data.type || "event", data.payload || {}, data.time || new Date().toISOString());
      if (data.payload && data.payload.status) {
        applyStatus(data.payload.status);
      }

      if (data.type === "qr_detected" || data.type === "ticket_detected") {
        refreshStatus();
      }

      if (data.type === "monitor_stopped" || data.type === "monitor_error") {
        refreshStatus();
      }
    } catch (error) {
      appendLog("ws_parse_error", String(error), new Date().toISOString());
    }
  };

  ws.onclose = () => {
    appendLog("ws_closed", "websocket disconnected, retry in 2s", new Date().toISOString());
    if (wsTimer) {
      clearInterval(wsTimer);
    }
    setTimeout(connectWs, 2000);
  };

  ws.onerror = () => {
    appendLog("ws_error", "websocket error", new Date().toISOString());
  };
}

function updateCustomUrlVisibility() {
  const isCustom = platformSelect.value === "custom";
  customUrlWrap.classList.toggle("hidden", !isCustom);
  customUrlInput.required = isCustom;
  roomIdInput.required = !isCustom;
  if (isCustom) {
    roomIdInput.placeholder = "自定义URL模式下可留空";
  } else {
    roomIdInput.placeholder = "例如 6 或 262229562462";
  }
}

function updateScanLoginVisibility() {
  const enabled = enableScanLoginInput.checked;
  const isBh3 = serverTypeInput.value === "bh3_bilibili";

  serverTypeWrap.classList.toggle("hidden", !enabled);
  uidWrap.classList.toggle("hidden", !enabled);
  tokenWrap.classList.toggle("hidden", !enabled);
  usernameWrap.classList.toggle("hidden", !(enabled && isBh3));

  uidInput.required = enabled;
  tokenInput.required = enabled;
  usernameInput.required = enabled && isBh3;
}

async function createAccount() {
  const payload = collectAccountPayload();
  const data = await callApi("/api/accounts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  accounts = Array.isArray(data.accounts) ? data.accounts : [];
  defaultAccountId = data.default_account_id || null;
  if (data.account && data.account.id) {
    selectedAccountId = data.account.id;
  }
  renderAccounts();
  appendLog("account_saved", { name: payload.name }, new Date().toISOString());
}

async function updateSelectedAccount() {
  if (!selectedAccountId) {
    throw new Error("请先在账号列表中选择要更新的账号");
  }
  const payload = collectAccountPayload();
  const data = await callApi(`/api/accounts/${selectedAccountId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  accounts = Array.isArray(data.accounts) ? data.accounts : [];
  defaultAccountId = data.default_account_id || null;
  renderAccounts();
  appendLog("account_updated", { name: payload.name }, new Date().toISOString());
}

async function deleteSelectedAccount() {
  if (!selectedAccountId) {
    throw new Error("请先在账号列表中选择要删除的账号");
  }
  const currentId = selectedAccountId;
  await callApi(`/api/accounts/${currentId}`, { method: "DELETE" });
  if (selectedAccountId === currentId) {
    selectedAccountId = null;
  }
  await refreshAccounts({ autoApplyDefault: false });
  appendLog("account_deleted", { id: currentId }, new Date().toISOString());
}

async function setSelectedAsDefault() {
  if (!selectedAccountId) {
    throw new Error("请先在账号列表中选择默认账号");
  }
  const data = await callApi(`/api/accounts/${selectedAccountId}/default`, {
    method: "POST",
  });
  accounts = Array.isArray(data.accounts) ? data.accounts : [];
  defaultAccountId = data.default_account_id || null;
  renderAccounts();
  appendLog("account_default_set", { id: selectedAccountId }, new Date().toISOString());
}

function refreshFrame() {
  const ts = Date.now();
  liveFrameImage.src = `/api/monitor/frame?ts=${ts}`;
}

function startFramePolling() {
  if (frameTimer) {
    return;
  }
  frameStatus.textContent = "正在拉取实时画面...";
  refreshFrame();
  frameTimer = setInterval(refreshFrame, 450);
}

function stopFramePolling(message) {
  if (frameTimer) {
    clearInterval(frameTimer);
    frameTimer = null;
  }
  liveFrameImage.removeAttribute("src");
  frameStatus.textContent = message;
}

liveFrameImage.addEventListener("load", () => {
  if (liveFrameImage.naturalWidth > 0 && liveFrameImage.naturalHeight > 0) {
    liveFrameImage.style.aspectRatio = `${liveFrameImage.naturalWidth} / ${liveFrameImage.naturalHeight}`;
  }
  frameStatus.textContent = "实时画面正常";
});

liveFrameImage.addEventListener("error", () => {
  frameStatus.textContent = "等待首帧...";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  startButton.disabled = true;
  try {
    await startMonitor();
  } catch (error) {
    appendLog("start_error", String(error), new Date().toISOString());
  } finally {
    startButton.disabled = false;
  }
});

stopButton.addEventListener("click", async () => {
  stopButton.disabled = true;
  try {
    await stopMonitor();
  } catch (error) {
    appendLog("stop_error", String(error), new Date().toISOString());
  } finally {
    stopButton.disabled = false;
  }
});

saveAccountButton.addEventListener("click", async () => {
  saveAccountButton.disabled = true;
  try {
    await createAccount();
  } catch (error) {
    appendLog("account_save_error", String(error), new Date().toISOString());
  } finally {
    saveAccountButton.disabled = false;
  }
});

updateAccountButton.addEventListener("click", async () => {
  updateAccountButton.disabled = true;
  try {
    await updateSelectedAccount();
  } catch (error) {
    appendLog("account_update_error", String(error), new Date().toISOString());
  } finally {
    updateAccountButton.disabled = false;
  }
});

deleteAccountButton.addEventListener("click", async () => {
  deleteAccountButton.disabled = true;
  try {
    await deleteSelectedAccount();
  } catch (error) {
    appendLog("account_delete_error", String(error), new Date().toISOString());
  } finally {
    deleteAccountButton.disabled = false;
  }
});

setDefaultAccountButton.addEventListener("click", async () => {
  setDefaultAccountButton.disabled = true;
  try {
    await setSelectedAsDefault();
  } catch (error) {
    appendLog("account_default_error", String(error), new Date().toISOString());
  } finally {
    setDefaultAccountButton.disabled = false;
  }
});

reloadAccountsButton.addEventListener("click", async () => {
  reloadAccountsButton.disabled = true;
  try {
    await refreshAccounts({ autoApplyDefault: false });
  } catch (error) {
    appendLog("account_reload_error", String(error), new Date().toISOString());
  } finally {
    reloadAccountsButton.disabled = false;
  }
});

refreshButton.addEventListener("click", refreshStatus);
platformSelect.addEventListener("change", updateCustomUrlVisibility);
enableScanLoginInput.addEventListener("change", updateScanLoginVisibility);
serverTypeInput.addEventListener("change", updateScanLoginVisibility);

updateCustomUrlVisibility();
updateScanLoginVisibility();
refreshStatus();
refreshAccounts().catch((error) => {
  appendLog("account_init_error", String(error), new Date().toISOString());
});
connectWs();
