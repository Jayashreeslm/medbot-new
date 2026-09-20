// MEDBOT — Face Recognition page logic

let mediaStream = null;
let angleQueue = Array.isArray(ANGLE_SEQUENCE) ? [...ANGLE_SEQUENCE] : [];

async function startCamera() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ video: true });
    document.getElementById("cameraFeed").srcObject = mediaStream;
    document.getElementById("startCameraBtn").disabled = true;
    document.getElementById("stopCameraBtn").disabled = false;
    document.getElementById("captureBtn").disabled = angleQueue.length === 0;
    document.getElementById("recognizeBtn").disabled = false;
    updateCaptureInstruction();
  } catch (err) {
    showError("registerErrors", "Could not access camera: " + err.message);
  }
}

function stopCamera() {
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }
  document.getElementById("cameraFeed").srcObject = null;
  document.getElementById("startCameraBtn").disabled = false;
  document.getElementById("stopCameraBtn").disabled = true;
  document.getElementById("captureBtn").disabled = true;
  document.getElementById("recognizeBtn").disabled = true;
}

function updateCaptureInstruction() {
  const el = document.getElementById("captureInstruction");
  if (angleQueue.length === 0) {
    el.textContent = "All angles registered. You can re-register by deleting existing face data first.";
    document.getElementById("captureBtn").disabled = true;
  } else {
    el.textContent = ANGLE_PROMPTS[angleQueue[0]] || `Capture angle: ${angleQueue[0]}`;
  }
}

function captureFrameAsBase64() {
  const video = document.getElementById("cameraFeed");
  const canvas = document.getElementById("captureCanvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.9);
}

function showError(elementId, message) {
  const el = document.getElementById(elementId);
  el.textContent = message;
  el.classList.remove("hidden");
}
function hideError(elementId) {
  document.getElementById(elementId).classList.add("hidden");
}

async function captureNextAngle() {
  hideError("registerErrors");
  if (!document.getElementById("consentCheckbox").checked) {
    showError("registerErrors", "You must give consent before registering face data.");
    return;
  }
  if (angleQueue.length === 0) return;

  const angle = angleQueue[0];
  const image = captureFrameAsBase64();

  try {
    const res = await fetch("/api/face/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image, angle, consent: true }),
    });
    const data = await res.json();
    if (!res.ok) {
      showError("registerErrors", data.error || "Registration failed.");
      return;
    }
    angleQueue.shift();
    updateCaptureInstruction();
    if (angleQueue.length === 0) {
      setTimeout(() => window.location.reload(), 800);
    }
  } catch (err) {
    showError("registerErrors", "Network error. Please try again.");
  }
}

async function runRecognition() {
  const image = captureFrameAsBase64();
  const resultEl = document.getElementById("recognitionResult");
  resultEl.classList.remove("hidden");
  resultEl.textContent = "Analyzing...";
  resultEl.className = "recognition-result";

  try {
    const res = await fetch("/api/face/recognize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image }),
    });
    const data = await res.json();
    if (!res.ok) {
      resultEl.textContent = data.error || "Recognition failed.";
      resultEl.classList.add("recognition-error");
      return;
    }
    const statusMap = {
      PATIENT_RECOGNIZED: ["PATIENT RECOGNIZED", "recognition-success"],
      WRONG_PATIENT_DETECTED: ["WRONG PATIENT DETECTED", "recognition-warning"],
      UNKNOWN_FACE: ["UNKNOWN FACE", "recognition-warning"],
      NO_FACE_DETECTED: ["NO FACE DETECTED", "recognition-warning"],
      MULTIPLE_FACES_DETECTED: ["MULTIPLE FACES DETECTED", "recognition-warning"],
    };
    const [label, cls] = statusMap[data.status] || [data.status, "recognition-warning"];
    resultEl.textContent = label + (data.patient_name ? ` — ${data.patient_name}` : "");
    resultEl.classList.add(cls);
  } catch (err) {
    resultEl.textContent = "Network error. Please try again.";
    resultEl.classList.add("recognition-error");
  }
}

async function deleteFaceData() {
  if (!confirm("Delete all registered face data? This cannot be undone.")) return;
  try {
    const res = await fetch("/api/face/delete", { method: "POST" });
    if (res.ok) window.location.reload();
  } catch (err) {
    alert("Network error. Please try again.");
  }
}
