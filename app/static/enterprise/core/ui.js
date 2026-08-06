import { query } from "./dom.js";

export function toast(message, type = "info", durationMs = 4500) {
  const stack = query("#toastStack");
  if (!stack) {
    console[type === "error" ? "error" : "log"](message);
    return;
  }

  const element = document.createElement("div");
  element.className = `toast toast--${type}`;
  element.setAttribute("role", type === "error" ? "alert" : "status");
  element.textContent = message;
  stack.appendChild(element);
  window.setTimeout(() => element.remove(), durationMs);
}

export function setButtonBusy(button, busy, busyText = "Procesando…") {
  if (!button) return;
  if (busy) {
    button.dataset.originalText ||= button.textContent.trim();
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    button.textContent = busyText;
    return;
  }

  button.disabled = false;
  button.removeAttribute("aria-busy");
  button.textContent = button.dataset.originalText || "Continuar";
}
