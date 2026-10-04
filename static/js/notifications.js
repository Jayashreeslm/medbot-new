const testNotificationForm = document.getElementById("testNotificationForm");

testNotificationForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const button = document.getElementById("sendTestButton");
  const resultEl = document.getElementById("testResult");
  button.disabled = true;
  button.classList.add("is-loading");
  button.textContent = "Sending…";
  resultEl.textContent = "Sending notification…";
  resultEl.classList.remove("hidden");

  try {
    const res = await fetch("/api/notifications/test-telegram", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    resultEl.textContent = data.message || data.error || "Notification request completed.";
    resultEl.classList.remove("hidden");
    if (res.ok) showToast(data.message || "Telegram notification request processed.");
    if (res.ok) setTimeout(() => reloadWithToast(data.message || "Telegram notification request processed."), 900);
    else showToast(data.message || data.error || "Telegram notification failed.", "error");
  } catch (err) {
    resultEl.textContent = "Network error. Please try again.";
  } finally {
    button.disabled = false;
    button.classList.remove("is-loading");
    button.textContent = "Send Test Telegram";
  }
});

document.querySelectorAll(".resend-notification").forEach((button) => {
  button.addEventListener("click", async () => {
    button.disabled = true;
    button.classList.add("is-loading");
    button.textContent = "Sending…";
    try {
      const response = await fetch(`/api/notifications/${button.dataset.id}/resend`, { method: "POST" });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Could not resend notification.");
      reloadWithToast("Notification resent.");
    } catch (error) {
      button.disabled = false;
      button.classList.remove("is-loading");
      button.textContent = "Resend";
      showToast(error.message, "error");
    }
  });
});
