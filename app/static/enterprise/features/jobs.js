import { normalizeText, query, queryAll } from "../core/dom.js";
import { errorMessage, request } from "../core/http.js";
import { setButtonBusy, toast } from "../core/ui.js";

const TERMINAL_STATES = new Set([
  "FINALIZADO",
  "FINALIZADO_CON_ERRORES",
  "ERROR",
  "CANCELADO",
]);
const ACTIVE_POLL_INTERVAL_MS = 2000;
const IDLE_POLL_INTERVAL_MS = 60000;
const ERROR_POLL_INTERVAL_MS = 15000;

let pollTimer = null;
let polling = false;
let hasActiveJobs = false;

function prepareFormRequest(form) {
  const method = String(form.method || "POST").toUpperCase();
  const url = new URL(form.action, window.location.origin);
  const data = new FormData(form);

  if (method === "GET") {
    for (const [key, value] of data.entries()) url.searchParams.set(key, String(value));
    return { url: url.toString(), options: { method } };
  }
  if (form.enctype.includes("multipart/form-data") || form.action.endsWith("/panel/importar-sku")) {
    return { url: url.toString(), options: { method, body: data } };
  }
  for (const [key, value] of data.entries()) url.searchParams.set(key, String(value));
  return { url: url.toString(), options: { method } };
}

function percentage(job) {
  const value = Number(job?.progreso_porcentaje ?? job?.progreso?.porcentaje ?? 0);
  return Number.isFinite(value) ? Math.max(0, Math.min(100, Math.round(value))) : 0;
}

function message(job) {
  return String(job?.mensaje ?? job?.progreso?.mensaje ?? "");
}

function processedText(job) {
  const processed = Number(job?.procesados ?? job?.progreso?.procesados ?? 0) || 0;
  const total = Number(job?.total ?? job?.progreso?.total ?? job?.progreso?.seleccionados ?? 0) || 0;
  return total > 0 ? `${processed} / ${total}` : String(processed);
}

function statusClass(state) {
  if (state === "FINALIZADO") return "success";
  if (["ERROR", "FINALIZADO_CON_ERRORES"].includes(state)) return "danger";
  if (state === "CANCELADO") return "neutral";
  return "warning";
}

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = String(value ?? "");
  return element.innerHTML;
}

function activeRow(job) {
  const pct = percentage(job);
  const canCancel = !TERMINAL_STATES.has(job.estado);
  return `
    <div class="job-row" data-live-job-id="${job.id}">
      <span class="job-icon" aria-hidden="true">↻</span>
      <div class="job-copy">
        <strong>${escapeHtml(job.tipo || "Proceso")}</strong>
        <small>#${job.id} · ${escapeHtml(job.estado)} · <span data-job-message>${escapeHtml(message(job))}</span></small>
      </div>
      <div class="progress" role="progressbar" aria-label="Progreso del trabajo #${job.id}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}">
        <i style="width:${pct}%"></i>
      </div>
      <b data-job-percent>${pct}%</b>
      ${canCancel ? `<button class="more-btn cancel-job" type="button" data-job-id="${job.id}">Cancelar</button>` : ""}
    </div>`;
}

function recentRow(job) {
  const pct = percentage(job);
  return `
    <tr data-recent-job-id="${job.id}">
      <td>#${job.id}</td>
      <td>${escapeHtml(job.tipo || "—")}</td>
      <td><span class="badge ${statusClass(job.estado)}">${escapeHtml(job.estado)}</span></td>
      <td><div class="table-progress"><div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><i style="width:${pct}%"></i></div><b>${pct}%</b></div></td>
      <td>${escapeHtml(processedText(job))}</td>
      <td class="job-message-cell" title="${escapeHtml(message(job))}">${escapeHtml(message(job) || "—")}</td>
    </tr>`;
}

function renderJobs(payload) {
  const activeContainer = query("#liveActiveJobs");
  const recentBody = query("#liveRecentJobs");
  if (!activeContainer || !recentBody) return 0;

  const active = Array.isArray(payload?.activos) ? payload.activos : [];
  const recent = Array.isArray(payload?.recientes) ? payload.recientes : [];
  const counts = payload?.conteos && typeof payload.conteos === "object" ? payload.conteos : {};

  queryAll("[data-job-state-metric]").forEach((metric) => {
    const state = metric.dataset.jobStateMetric;
    const value = metric.querySelector("strong");
    if (value && state) value.textContent = String(counts[state] ?? 0);
  });

  activeContainer.innerHTML = active.length
    ? active.map(activeRow).join("")
    : '<div class="empty"><strong>No hay trabajos activos</strong><p>La cola se encuentra libre.</p></div>';
  recentBody.innerHTML = recent.map(recentRow).join("");
  initializeJobCancellation(activeContainer);

  const liveStatus = query("#jobsLiveStatus");
  if (liveStatus) {
    liveStatus.textContent = active.length ? `En vivo · ${active.length} activo${active.length === 1 ? "" : "s"}` : "En vivo · cola libre";
  }

  return active.length;
}

function clearPollTimer() {
  if (pollTimer !== null) {
    window.clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function scheduleNextPoll(delayMs) {
  clearPollTimer();
  if (document.hidden || !query("#liveActiveJobs")) return;
  pollTimer = window.setTimeout(() => {
    refreshJobs();
  }, delayMs);
}

async function refreshJobs({ silent = true, scheduleNext = true } = {}) {
  if (polling || document.hidden) return;
  polling = true;
  let nextDelay = hasActiveJobs ? ACTIVE_POLL_INTERVAL_MS : IDLE_POLL_INTERVAL_MS;

  try {
    const payload = await request("/admin/panel/jobs");
    hasActiveJobs = renderJobs(payload) > 0;
    nextDelay = hasActiveJobs ? ACTIVE_POLL_INTERVAL_MS : IDLE_POLL_INTERVAL_MS;
  } catch (error) {
    const liveStatus = query("#jobsLiveStatus");
    if (liveStatus) liveStatus.textContent = "Sin conexión de seguimiento";
    nextDelay = ERROR_POLL_INTERVAL_MS;
    if (!silent) toast(errorMessage(error), "error", 7000);
  } finally {
    polling = false;
    if (scheduleNext) scheduleNextPoll(nextDelay);
  }
}

function schedulePolling() {
  if (!query("#liveActiveJobs")) return;

  clearPollTimer();
  refreshJobs();

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      clearPollTimer();
      return;
    }
    refreshJobs();
  });
}

function initializeJobForms() {
  queryAll("[data-job-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector('button[type="submit"], button:not([type])');
      setButtonBusy(button, true, "Iniciando…");
      try {
        const { url, options } = prepareFormRequest(form);
        const result = await request(url, options);
        if (result?.ok === false) throw new Error(result.error || result.detalle || "No se pudo iniciar.");
        toast(result?.job_id ? `Trabajo iniciado #${result.job_id}.` : "Trabajo iniciado.", "success");
        if (result?.job_id) {
          window.location.assign(`/admin/panel/trabajos?focus=${encodeURIComponent(result.job_id)}`);
        } else {
          window.setTimeout(() => window.location.assign("/admin/panel/trabajos"), 350);
        }
      } catch (error) {
        toast(errorMessage(error), "error", 7000);
        setButtonBusy(button, false);
      }
    });
  });
}

function initializeJobCancellation(root = document) {
  queryAll(".cancel-job", root).forEach((button) => {
    if (button.dataset.boundCancel === "true") return;
    button.dataset.boundCancel = "true";
    button.addEventListener("click", async () => {
      const jobId = normalizeText(button.dataset.jobId);
      if (!jobId || !window.confirm(`¿Cancelar el trabajo #${jobId}?`)) return;
      setButtonBusy(button, true, "Cancelando…");
      try {
        await request(`/admin/panel/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
        toast("Cancelación solicitada.", "success");
        await refreshJobs({ scheduleNext: true });
      } catch (error) {
        toast(errorMessage(error), "error", 7000);
        setButtonBusy(button, false);
      }
    });
  });
}

function initializeManualRefresh() {
  const button = query("#refreshJobsNow");
  if (!button) return;
  button.addEventListener("click", async () => {
    setButtonBusy(button, true, "Actualizando…");
    clearPollTimer();
    await refreshJobs({ silent: false, scheduleNext: true });
    setButtonBusy(button, false);
  });
}

export function initializeJobs() {
  initializeJobForms();
  initializeJobCancellation();
  initializeManualRefresh();
  schedulePolling();
}
