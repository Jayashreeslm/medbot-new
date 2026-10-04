// MEDBOT — Reminder popup, polled on every protected page

let activeReminderId = null;

async function pollReminders() {
  try {
    const res = await fetch("/api/reminders/pending");
    if (!res.ok) return;
    const data = await res.json();
    if (data.reminders && data.reminders.length > 0) {
      showReminderPopup(data.reminders[0]);
    } else if (activeReminderId !== null) {
      hideReminderPopup();
    }
  } catch (err) {
    // Silently ignore network hiccups during polling
  }
}

function showReminderPopup(reminder) {
  activeReminderId = reminder.id;
  document.getElementById("reminderPatient").textContent = MEDBOT_PATIENT_NAME;
  document.getElementById("reminderMedicine").textContent = reminder.medicine_name;
  document.getElementById("reminderDosage").textContent = reminder.dosage;
  document.getElementById("reminderCompartment").textContent = reminder.compartment_number;
  document.getElementById("reminderTime").textContent = formatDateTime(reminder.scheduled_time);
  document.getElementById("reminderErrors").classList.add("hidden");
  document.getElementById("reminderPopup").classList.remove("hidden");
}

function hideReminderPopup() {
  activeReminderId = null;
  document.getElementById("reminderPopup").classList.add("hidden");
}

async function dispenseReminder() {
  if (!activeReminderId) return;
  try {
    const res = await fetch("/api/medicine/dispense", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reminder_id: activeReminderId }),
    });
    const data = await res.json();
    if (!res.ok) {
      const errEl = document.getElementById("reminderErrors");
      errEl.textContent = data.error || "Could not dispense.";
      errEl.classList.remove("hidden");
      return;
    }
    showToast("Medicine dispensed successfully.");
    pollReminders();
  } catch (err) {
    console.error(err);
  }
}

async function collectReminder() {
  if (!activeReminderId) return;
  try {
    const res = await fetch("/api/medicine/collect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reminder_id: activeReminderId }),
    });
    if (res.ok) {
      hideReminderPopup();
      pollReminders();
    }
  } catch (err) {
    console.error(err);
  }
}

setInterval(pollReminders, 8000);
pollReminders();
