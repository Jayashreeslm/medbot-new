// MEDBOT — Hardware page logic

function showResult(text, isError) {
  const el = document.getElementById("commandResult");
  el.textContent = text;
  el.classList.remove("hidden");
  el.classList.toggle("is-error", Boolean(isError));
}

function updateConnectionUI(mode, lastSeen) {
  const connected = mode === "HARDWARE_CONNECTED";
  document.getElementById("connectionStatusText").textContent = connected ? "Connected" : "Simulation Mode";
  const badge = document.getElementById("connectionBadge");
  badge.textContent = connected ? "HARDWARE CONNECTED" : "HARDWARE SIMULATION MODE ACTIVE";
  badge.className = "status-badge " + (connected ? "status-excellent" : "status-unknown");
  if (lastSeen) document.getElementById("lastSeenText").textContent = lastSeen;
}

async function testConnection() {
  try {
    const res = await fetch("/api/hardware/test", { method: "POST" });
    const data = await res.json();
    updateConnectionUI(data.mode, formatDateTime(new Date().toISOString()));
    showResult(data.connected ? "ESP32 responded successfully." : `Simulation mode: ${data.note || "ESP32 not reachable."}`, !data.connected);
  } catch (err) {
    showResult("Network error while testing connection.", true);
  }
}

async function saveConfig() {
  const esp32_ip = document.getElementById("esp32_ip").value.trim();
  const port = document.getElementById("esp32_port").value;
  const errEl = document.getElementById("configErrors");
  errEl.classList.add("hidden");

  try {
    const res = await fetch("/api/hardware/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ esp32_ip, port }),
    });
    const data = await res.json();
    if (!res.ok) {
      errEl.innerHTML = (data.errors || [data.error]).map((e) => `<div>${e}</div>`).join("");
      errEl.classList.remove("hidden");
      return;
    }
    showResult("Configuration saved.", false);
  } catch (err) {
    errEl.textContent = "Network error. Please try again.";
    errEl.classList.remove("hidden");
  }
}

async function sendCommand(command) {
  try {
    const res = await fetch("/api/hardware/command", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command }),
    });
    const data = await res.json();
    updateConnectionUI(data.mode);
    showResult(`${command}: ${data.status} (${data.mode.replace(/_/g, " ")})`, false);
  } catch (err) {
    showResult("Network error sending command.", true);
  }
}

async function sendMovement(direction) {
  try {
    const res = await fetch("/api/movement", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ direction }),
    });
    const data = await res.json();
    if (!res.ok) {
      showResult(data.error || "Movement blocked.", true);
      return;
    }
    updateConnectionUI(data.mode);
    showResult(`Movement (${direction}): ${data.status}`, false);
  } catch (err) {
    showResult("Network error sending movement command.", true);
  }
}

async function searchStart() {
  try {
    const res = await fetch("/api/search/start", { method: "POST" });
    const data = await res.json();
    if (!res.ok) { showResult(data.error || "Could not start search.", true); return; }
    showResult(`Search started: ${data.status}`, false);
  } catch (err) {
    showResult("Network error.", true);
  }
}

async function searchStop() {
  try {
    const res = await fetch("/api/search/stop", { method: "POST" });
    const data = await res.json();
    showResult(`Search stopped: ${data.status}`, false);
  } catch (err) {
    showResult("Network error.", true);
  }
}

async function switchMode(mode) {
  const label = mode === "fixed" ? "Fixed Position Mode" : "Move Mode";
  if (!confirm(`Switch to ${label}? This will change how MEDBOT operates.`)) return;

  try {
    const res = await fetch("/api/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, confirm: true }),
    });
    const data = await res.json();
    const resultEl = document.getElementById("modeResult");
    resultEl.classList.remove("hidden");
    if (!res.ok) {
      resultEl.textContent = data.error;
      resultEl.style.background = "#fee2e2";
      return;
    }
    resultEl.textContent = data.message;
    resultEl.style.background = "var(--primary-light)";
    setTimeout(() => window.location.reload(), 900);
  } catch (err) {
    showToast("Network error switching mode.", "error");
  }
}

async function simulateBattery() {
  const voltage = document.getElementById("sim_voltage").value;
  const charging = document.getElementById("sim_charging").value === "true";

  try {
    const res = await fetch("/api/battery/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ voltage, charging }),
    });
    const data = await res.json();
    const resultEl = document.getElementById("batteryResult");
    resultEl.classList.remove("hidden");
    if (!res.ok) {
      resultEl.textContent = data.error || "Could not update battery.";
      resultEl.style.background = "#fee2e2";
      return;
    }
    document.getElementById("batteryPercentage").textContent = data.percentage + "%";
    document.getElementById("batteryVoltage").textContent = data.voltage + "V";
    document.getElementById("batteryCharging").textContent = data.charging ? "Yes" : "No";
    const badge = document.getElementById("batteryStatusBadge");
    badge.textContent = data.status;
    badge.className = "status-badge status-" + data.status.toLowerCase();
    const percentage = Math.max(0, Math.min(100, Number(data.percentage) || 0));
    const progress = document.getElementById("batteryProgress");
    progress.setAttribute("aria-valuenow", String(percentage));
    progress.classList.toggle("is-critical", percentage < 20);
    progress.classList.toggle("is-low", percentage >= 20 && percentage < 30);
    document.getElementById("batteryProgressFill").style.width = `${percentage}%`;
    document.getElementById("batteryMeterValue").textContent = `${percentage}%`;

    let actionsText = `Status: ${data.status}`;
    if (data.safety && data.safety.actions && data.safety.actions.length > 0) {
      actionsText += ` — Actions: ${data.safety.actions.join(", ")}`;
    }
    resultEl.textContent = actionsText;
    resultEl.style.background = "var(--primary-light)";

    if (data.safety && data.safety.actions && data.safety.actions.includes("MOVE_MODE_DISABLED")) {
      setTimeout(() => window.location.reload(), 1200);
    }
  } catch (err) {
    showToast("Network error updating battery.", "error");
  }
}
