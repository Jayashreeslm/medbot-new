// MEDBOT — Medicines page logic

function openAddModal() {
  document.getElementById("modalTitle").textContent = "Add Medicine";
  document.getElementById("medicineForm").reset();
  document.getElementById("medicineId").value = "";
  hideErrors("formErrors");
  document.getElementById("medicineModal").classList.remove("hidden");
}

function openEditModal(medicine) {
  document.getElementById("modalTitle").textContent = "Edit Medicine";
  document.getElementById("medicineId").value = medicine.id;
  document.getElementById("medicine_name").value = medicine.medicine_name;
  document.getElementById("dosage").value = medicine.dosage;
  document.getElementById("quantity").value = medicine.quantity;
  document.getElementById("quantity").disabled = true; // quantity only changes via dispense/refill
  document.getElementById("compartment_number").value = medicine.compartment_number;
  document.getElementById("refill_threshold").value = medicine.refill_threshold;
  document.getElementById("description").value = medicine.description || "";
  document.getElementById("batch_no").value = medicine.batch_no || "";
  document.getElementById("expiry_date").value = medicine.expiry_date || "";
  document.getElementById("price").value = medicine.price || 0;
  document.getElementById("refill_due_date").value = medicine.refill_due_date || "";
  hideErrors("formErrors");
  document.getElementById("medicineModal").classList.remove("hidden");
}

function openRefillModal(id, name) {
  document.getElementById("refillMedicineId").value = id;
  document.getElementById("refillMedicineName").textContent = name;
  document.getElementById("refillForm").reset();
  hideErrors("refillErrors");
  document.getElementById("refillModal").classList.remove("hidden");
}

function openDispenseModal(id, name, available) {
  document.getElementById("dispenseForm").reset();
  document.getElementById("dispenseMedicineId").value = id;
  document.getElementById("dispenseMedicineName").textContent = `${name} · ${available} available`;
  document.getElementById("dispenseQuantity").max = available;
  hideErrors("dispenseErrors");
  document.getElementById("dispenseModal").classList.remove("hidden");
}

function closeModal(id) {
  document.getElementById(id).classList.add("hidden");
  if (id === "medicineModal") {
    document.getElementById("quantity").disabled = false;
  }
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

document.getElementById("medicineForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("medicineId").value;
  const payload = {
    medicine_name: document.getElementById("medicine_name").value,
    dosage: document.getElementById("dosage").value,
    quantity: document.getElementById("quantity").value,
    compartment_number: document.getElementById("compartment_number").value,
    refill_threshold: document.getElementById("refill_threshold").value,
    description: document.getElementById("description").value,
    batch_no: document.getElementById("batch_no").value,
    expiry_date: document.getElementById("expiry_date").value,
    price: document.getElementById("price").value,
    refill_due_date: document.getElementById("refill_due_date").value,
  };

  const url = id ? `/api/medicines/${id}` : "/api/medicines";
  const method = id ? "PUT" : "POST";

  try {
    const res = await fetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      showErrors("formErrors", data.errors || [data.error || "Something went wrong."]);
      return;
    }
    reloadWithToast(id ? "Medicine updated." : "Medicine added.");
  } catch (err) {
    showErrors("formErrors", ["Network error. Please try again."]);
  }
});

document.getElementById("refillForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("refillMedicineId").value;
  const quantity_added = document.getElementById("quantity_added").value;

  try {
    const res = await fetch(`/api/medicines/${id}/refill`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quantity_added }),
    });
    const data = await res.json();
    if (!res.ok) {
      showErrors("refillErrors", data.errors || [data.error || "Something went wrong."]);
      return;
    }
    reloadWithToast("Medicine refilled.");
  } catch (err) {
    showErrors("refillErrors", ["Network error. Please try again."]);
  }
});

document.getElementById("dispenseForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("dispenseMedicineId").value;
  const quantity = document.getElementById("dispenseQuantity").value;
  try {
    const res = await fetch(`/api/medicines/${id}/dispense`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quantity }),
    });
    const data = await res.json();
    if (!res.ok) {
      showErrors("dispenseErrors", data.errors || [data.error || "Could not dispense medicine."]);
      return;
    }
    reloadWithToast(`Dispensed ${data.quantity}; ${data.new_quantity} remaining.`);
  } catch (err) {
    showErrors("dispenseErrors", ["Network error. Please try again."]);
  }
});

async function toggleActive(id, isActive) {
  try {
    const res = await fetch(`/api/medicines/${id}/toggle`, { method: "POST" });
    if (!res.ok) {
      alert("Could not update medicine status.");
      return;
    }
    reloadWithToast("Medicine status updated.");
  } catch (err) {
    alert("Network error. Please try again.");
  }
}

async function deleteMedicine(id, name) {
  if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
  try {
    const res = await fetch(`/api/medicines/${id}`, { method: "DELETE" });
    if (!res.ok) {
      alert("Could not delete medicine.");
      return;
    }
    reloadWithToast("Medicine deleted.");
  } catch (err) {
    alert("Network error. Please try again.");
  }
}
