// MEDBOT — Schedules page logic

function toggleDayPicker() {
  const mode = document.getElementById("schedule_days_mode").value;
  document.getElementById("dayPicker").classList.toggle("hidden", mode !== "custom");
}

function openAddScheduleModal() {
  document.getElementById("scheduleModalTitle").textContent = "Add Schedule";
  document.getElementById("scheduleForm").reset();
  document.getElementById("scheduleId").value = "";
  document.getElementById("dayPicker").classList.add("hidden");
  hideErrors("scheduleErrors");
  document.getElementById("scheduleModal").classList.remove("hidden");
}

function openEditScheduleModal(schedule) {
  document.getElementById("scheduleModalTitle").textContent = "Edit Schedule";
  document.getElementById("scheduleId").value = schedule.id;
  document.getElementById("schedule_medicine_id").value = schedule.medicine_id;
  document.getElementById("schedule_medicine_id").disabled = true;
  document.getElementById("schedule_time").value = schedule.schedule_time;

  if (schedule.schedule_days === "daily") {
    document.getElementById("schedule_days_mode").value = "daily";
    document.getElementById("dayPicker").classList.add("hidden");
  } else {
    document.getElementById("schedule_days_mode").value = "custom";
    document.getElementById("dayPicker").classList.remove("hidden");
    const days = schedule.schedule_days.split(",");
    document.querySelectorAll("#dayPicker input[type=checkbox]").forEach((cb) => {
      cb.checked = days.includes(cb.value);
    });
  }
  hideErrors("scheduleErrors");
  document.getElementById("scheduleModal").classList.remove("hidden");
}

function closeModal(id) {
  document.getElementById(id).classList.add("hidden");
  document.getElementById("schedule_medicine_id").disabled = false;
}

function showErrors(elementId, errors) {
  const el = document.getElementById(elementId);
  el.innerHTML = errors.map((e) => `<div>${e}</div>`).join("");
  el.classList.remove("hidden");
}
function hideErrors(elementId) {
  const el = document.getElementById(elementId);
  el.classList.add("hidden");
  el.innerHTML = "";
}

document.getElementById("scheduleForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("scheduleId").value;
  const mode = document.getElementById("schedule_days_mode").value;
  let schedule_days = "daily";
  if (mode === "custom") {
    const checked = Array.from(document.querySelectorAll("#dayPicker input:checked")).map((cb) => cb.value);
    if (checked.length === 0) {
      showErrors("scheduleErrors", ["Select at least one day, or choose 'Every day'."]);
      return;
    }
    schedule_days = checked.join(",");
  }

  const payload = {
    medicine_id: document.getElementById("schedule_medicine_id").value,
    schedule_time: document.getElementById("schedule_time").value,
    schedule_days,
  };

  const url = id ? `/api/schedules/${id}` : "/api/schedules";
  const method = id ? "PUT" : "POST";

  try {
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      showErrors("scheduleErrors", data.errors || [data.error || "Something went wrong."]);
      return;
    }
    window.location.reload();
  } catch (err) {
    showErrors("scheduleErrors", ["Network error. Please try again."]);
  }
});

async function toggleSchedule(id) {
  try {
    const res = await fetch(`/api/schedules/${id}/toggle`, { method: "POST" });
    if (!res.ok) { alert("Could not update schedule."); return; }
    window.location.reload();
  } catch (err) {
    alert("Network error. Please try again.");
  }
}

async function deleteSchedule(id) {
  if (!confirm("Delete this schedule?")) return;
  try {
    const res = await fetch(`/api/schedules/${id}`, { method: "DELETE" });
    if (!res.ok) { alert("Could not delete schedule."); return; }
    window.location.reload();
  } catch (err) {
    alert("Network error. Please try again.");
  }
}

// ---- Live countdown ----
function formatCountdown(ms) {
  if (ms <= 0) return "Due now";
  const totalSeconds = Math.floor(ms / 1000);
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  return `${h}h ${m}m ${s}s`;
}

function tickCountdowns() {
  document.querySelectorAll(".schedule-countdown[data-next-trigger]").forEach((el) => {
    const iso = el.getAttribute("data-next-trigger");
    if (!iso) return;
    const target = new Date(iso).getTime();
    const now = new Date().getTime();
    const valueEl = el.querySelector(".countdown-value");
    if (valueEl) valueEl.textContent = formatCountdown(target - now);
  });
}

setInterval(tickCountdowns, 1000);
tickCountdowns();
