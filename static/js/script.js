// MEDBOT frontend script — shared across all pages.

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("medbot_theme", next);
}

function formatDateTime(value) {
  if (!value) return "—";
  const text = String(value);
  const timeOnly = text.match(/^(\d{2}):(\d{2})$/);
  if (timeOnly) {
    const hour = Number(timeOnly[1]);
    const minute = timeOnly[2];
    return `${String(hour % 12 || 12).padStart(2, "0")}:${minute} ${hour < 12 ? "AM" : "PM"}`;
  }
  const dateOnly = text.match(/^\d{4}-\d{2}-\d{2}$/);
  const iso = text.replace(" ", "T");
  const hasZone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(iso);
  const date = new Date(dateOnly ? `${text}T00:00:00+05:30` : (hasZone ? iso : `${iso}+05:30`));
  if (Number.isNaN(date.getTime())) return text;
  return new Intl.DateTimeFormat("en-IN", {
    timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric",
    ...(dateOnly ? {} : { hour: "2-digit", minute: "2-digit", hour12: true }),
  }).format(date).replace(/\b(am|pm)\b/i, (marker) => marker.toUpperCase());
}

function showToast(message, kind = "success") {
  const container = document.getElementById("toastContainer");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast toast-${kind}`;
  toast.textContent = message;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("toast-visible"));
  setTimeout(() => {
    toast.classList.remove("toast-visible");
    setTimeout(() => toast.remove(), 200);
  }, 3200);
}

function reloadWithToast(message) {
  sessionStorage.setItem("medbot_next_toast", message);
  window.location.reload();
}

document.addEventListener("DOMContentLoaded", () => {
  const appShell = document.querySelector(".app-shell");
  const sidebarToggle = document.getElementById("sidebarToggle");
  const notificationBell = document.getElementById("notificationBell");
  const notificationPanel = document.getElementById("notificationPanel");
  const themeToggle = document.getElementById("themeToggle");

  sidebarToggle?.addEventListener("click", () => {
    const isOpen = appShell.classList.toggle("sidebar-open");
    sidebarToggle.setAttribute("aria-expanded", String(isOpen));
  });
  appShell?.addEventListener("click", (event) => {
    if (event.target === appShell && appShell.classList.contains("sidebar-open")) {
      appShell.classList.remove("sidebar-open");
      sidebarToggle?.setAttribute("aria-expanded", "false");
    }
  });
  notificationBell?.addEventListener("click", () => {
    const isOpen = notificationPanel.classList.toggle("hidden") === false;
    notificationBell.setAttribute("aria-expanded", String(isOpen));
  });
  themeToggle?.addEventListener("click", toggleTheme);
  document.querySelectorAll(".notification-item[data-notification-id]").forEach((item) => {
    item.addEventListener("click", async () => {
      try {
        await fetch(`/api/notifications/${item.dataset.notificationId}/read`, { method: "POST" });
      } catch (error) {
        showToast("Could not update notification status.", "error");
      } finally {
        window.location.href = "/notifications";
      }
    });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    notificationPanel?.classList.add("hidden");
    notificationBell?.setAttribute("aria-expanded", "false");
    appShell?.classList.remove("sidebar-open");
    sidebarToggle?.setAttribute("aria-expanded", "false");
  });

  const nextToast = sessionStorage.getItem("medbot_next_toast");
  if (nextToast) {
    sessionStorage.removeItem("medbot_next_toast");
    showToast(nextToast);
  }
  const flashes = document.querySelectorAll(".flash");
  flashes.forEach((el) => {
    setTimeout(() => {
      el.style.transition = "opacity 0.4s ease";
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 400);
    }, 4000);
  });
});
