const form = document.getElementById("monitor-form");
const platformSelect = document.getElementById("platform");
const customUrlWrap = document.getElementById("custom-url-wrap");
const customUrlInput = document.getElementById("custom_url");
const logBox = document.getElementById("event-log");

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
  room_url: document.getElementById("room_url"),
  stream_url: document.getElementById("stream_url"),
  last_frame_at: document.getElementById("last_frame_at"),
  last_error: document.getElementById("last_error"),
};

const startButton = document.getElementById("start-btn");
const stopButton = document.getElementById("stop-btn");
const refreshButton = document.getElementById("refresh-btn");

let ws = null;
let wsTimer = null;

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
  fields.room_url.textContent = textOrDash(status.room_url);
  fields.stream_url.textContent = textOrDash(status.stream_url);
  fields.last_frame_at.textContent = formatTime(status.last_frame_at);
  fields.last_error.textContent = textOrDash(status.last_error);
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
  const payload = {
    platform: formData.get("platform"),
    room_id: String(formData.get("room_id") || "").trim(),
    quality: String(formData.get("quality") || "best").trim() || "best",
    scan_interval_ms: Number(formData.get("scan_interval_ms") || 500),
    auto_stop_on_ticket: Boolean(formData.get("auto_stop_on_ticket")),
  };

  if (payload.platform === "custom") {
    payload.custom_url = String(formData.get("custom_url") || "").trim();
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
}

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

refreshButton.addEventListener("click", refreshStatus);
platformSelect.addEventListener("change", updateCustomUrlVisibility);

updateCustomUrlVisibility();
refreshStatus();
connectWs();
