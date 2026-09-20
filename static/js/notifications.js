document.getElementById("testNotificationForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const channel = document.getElementById("test_channel").value;
  const message = document.getElementById("test_message").value;

  try {
    const res = await fetch("/api/notification/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel, message }),
    });
    const data = await res.json();
    const resultEl = document.getElementById("testResult");
    resultEl.textContent = res.ok
      ? `Result: ${data.status}`
      : (data.error || "Something went wrong.");
    resultEl.classList.remove("hidden");
    if (res.ok) setTimeout(() => window.location.reload(), 1200);
  } catch (err) {
    console.error(err);
  }
});
