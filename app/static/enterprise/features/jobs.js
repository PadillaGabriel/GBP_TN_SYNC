import { normalizeText, query, queryAll } from "../core/dom.js";
import { errorMessage, request } from "../core/http.js";
import { setButtonBusy, toast } from "../core/ui.js";

const TERMINAL_STATES = new Set(["FINALIZADO", "FINALIZADO_CON_ERRORES", "ERROR", "CANCELADO", "REQUIERE_REVISION"]);
const ACTIVE_POLL_INTERVAL_MS = 2000;
const IDLE_POLL_INTERVAL_MS = 60000;
const ERROR_POLL_INTERVAL_MS = 15000;
const STATE_LABELS = {
  PENDIENTE: "Pendiente", EN_PROCESO: "En proceso", CANCELACION_SOLICITADA: "Cancelación solicitada",
  FINALIZADO: "Finalizado", FINALIZADO_CON_ERRORES: "Finalizado con errores", ERROR: "Error",
  CANCELADO: "Cancelado", REQUIERE_REVISION: "Requiere revisión",
};

let pollTimer = null;
let polling = false;
let hasActiveJobs = false;
let recentJobs = [];
let activeJobs = [];
let detailJobId = null;

function escapeHtml(value) {
  const element = document.createElement("div");
  element.textContent = String(value ?? "");
  return element.innerHTML;
}

function safeId(job) {
  const id = Number(job?.id);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

function stateLabel(value) { return STATE_LABELS[value] || String(value || "Desconocido").replaceAll("_", " "); }
function number(value) { const n = Number(value); return Number.isFinite(n) && n >= 0 ? n : 0; }
function percentage(job) { return Math.min(100, Math.round(number(job?.progreso_porcentaje ?? job?.progreso?.porcentaje))); }
function message(job) { return String(job?.mensaje ?? job?.progreso?.mensaje ?? ""); }
function processedText(job) {
  const processed = number(job?.procesados ?? job?.progreso?.procesados);
  const total = number(job?.total ?? job?.progreso?.total ?? job?.progreso?.seleccionados);
  return total ? `${processed} / ${total}` : String(processed);
}
function statusClass(state) {
  if (state === "FINALIZADO") return "success";
  if (["ERROR", "FINALIZADO_CON_ERRORES", "REQUIERE_REVISION"].includes(state)) return "danger";
  if (state === "CANCELADO") return "neutral";
  return "warning";
}
function formatDate(value) {
  if (!value) return "—";
  const timestamp = String(value);
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(timestamp) ? timestamp : `${timestamp}Z`;
  const date = new Date(normalized);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" });
}
function progressHtml(job) {
  const pct = percentage(job);
  return `<div class="table-progress"><div class="progress" role="progressbar" aria-label="Avance del trabajo" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><i style="width:${pct}%"></i></div><b>${pct}%</b></div>`;
}
function activeRow(job) {
  const id = safeId(job);
  if (!id) return "";
  return `<div class="job-row" data-live-job-id="${id}">
    <span class="job-icon" aria-hidden="true">↻</span>
    <div class="job-copy"><strong>${escapeHtml(stateLabel(job.tipo))}</strong>
    <small>#${id} · ${escapeHtml(stateLabel(job.estado))} · ${escapeHtml(message(job) || "Sin novedades")}</small></div>
    <div class="progress" role="progressbar" aria-label="Progreso #${id}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${percentage(job)}"><i style="width:${percentage(job)}%"></i></div>
    <b>${percentage(job)}%</b>
    <div class="job-actions"><button class="btn subtle" type="button" data-job-detail="${id}">Detalle</button>
    ${!TERMINAL_STATES.has(job.estado) && job.estado !== "CANCELACION_SOLICITADA" ? `<button class="btn danger-outline cancel-job" type="button" data-job-id="${id}">Cancelar</button>` : ""}</div>
  </div>`;
}
function recentRow(job) {
  const id = safeId(job);
  if (!id) return "";
  return `<tr data-recent-job-id="${id}" data-state="${escapeHtml(job.estado)}">
    <td data-label="Trabajo"><strong>#${id}</strong><small class="block">${escapeHtml(stateLabel(job.tipo))}</small></td>
    <td data-label="Estado"><span class="badge ${statusClass(job.estado)}">${escapeHtml(stateLabel(job.estado))}</span></td>
    <td data-label="Progreso">${progressHtml(job)}</td><td data-label="Procesados">${escapeHtml(processedText(job))}</td>
    <td data-label="Actualizado">${escapeHtml(formatDate(job.updated_at || job.finished_at || job.created_at))}</td>
    <td data-label="Inspección"><button class="btn subtle" type="button" data-job-detail="${id}">Ver detalle</button></td></tr>`;
}
function filterRecentJobs() {
  const target = query("#liveRecentJobs");
  if (!target) return;
  const needle = normalizeText(query("#jobSearch")?.value).toLocaleLowerCase("es");
  const state = query("#jobStateFilter")?.value || "";
  const filtered = recentJobs.filter((job) => {
    if (state && job.estado !== state) return false;
    return !needle || [job.id, job.tipo, job.estado, job.sku, message(job), job.error_codigo]
      .some((part) => String(part ?? "").toLocaleLowerCase("es").includes(needle));
  });
  target.innerHTML = filtered.map(recentRow).join("");
  const empty = query("#jobFilterEmpty");
  if (empty) empty.hidden = filtered.length > 0;
  const count = query("#jobResultsCount");
  if (count) count.textContent = `${filtered.length} de ${recentJobs.length} registros cargados`;
}
function renderJobs(payload) {
  const activeContainer = query("#liveActiveJobs");
  if (!activeContainer || !query("#liveRecentJobs")) return 0;
  activeJobs = Array.isArray(payload?.activos) ? payload.activos : [];
  recentJobs = Array.isArray(payload?.recientes) ? payload.recientes : [];
  const counts = payload?.conteos && typeof payload.conteos === "object" ? payload.conteos : {};

  queryAll("[data-job-state-metric]").forEach((metric) => {
    const value = metric.querySelector("strong");
    if (value) value.textContent = String(number(counts[metric.dataset.jobStateMetric]));
  });
  activeContainer.innerHTML = activeJobs.length ? activeJobs.map(activeRow).join("")
    : '<div class="empty"><strong>No hay trabajos activos</strong><p>Las nuevas solicitudes aparecerán aquí.</p></div>';
  filterRecentJobs();
  const liveStatus = query("#jobsLiveStatus");
  if (liveStatus) {
    liveStatus.classList.remove("offline");
    liveStatus.textContent = `Actualizado ${new Date().toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })} · ${activeJobs.length} activo${activeJobs.length === 1 ? "" : "s"}`;
  }
  return activeJobs.length;
}
function clearPollTimer() {
  if (pollTimer !== null) { window.clearTimeout(pollTimer); pollTimer = null; }
}
function scheduleNextPoll(delayMs) {
  clearPollTimer();
  if (document.hidden || !query("#liveActiveJobs")) return;
  pollTimer = window.setTimeout(() => { refreshJobs(); }, delayMs);
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
    const status = query("#jobsLiveStatus");
    if (status) { status.textContent = "Seguimiento sin conexión · reintentando"; status.classList.add("offline"); }
    nextDelay = ERROR_POLL_INTERVAL_MS;
    if (!silent) toast(errorMessage(error), "error", 7000);
  } finally {
    polling = false;
    if (scheduleNext) scheduleNextPoll(nextDelay);
  }
}
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
function initializeJobForms() {
  queryAll("[data-job-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector('button[type="submit"], button:not([type])');
      setButtonBusy(button, true, "Encolando…");
      try {
        const { url, options } = prepareFormRequest(form);
        const result = await request(url, options);
        if (result?.ok === false) throw new Error(result.error || result.detalle || "No se pudo iniciar.");
        toast(result?.job_id ? `Trabajo #${result.job_id} registrado en la cola.` : "Solicitud registrada.", "success");
        const target = result?.job_id ? `?focus=${encodeURIComponent(result.job_id)}` : "";
        window.location.assign(`/admin/panel/trabajos${target}`);
      } catch (error) { toast(errorMessage(error), "error", 7000); setButtonBusy(button, false); }
    });
  });
}
async function cancelJob(button) {
  const jobId = normalizeText(button.dataset.jobId);
  if (!/^\d+$/.test(jobId) || !window.confirm(`¿Solicitar la cancelación del trabajo #${jobId}? Puede finalizar antes de que el worker procese la solicitud.`)) return;
  setButtonBusy(button, true, "Solicitando…");
  try {
    await request(`/admin/panel/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
    toast("Solicitud de cancelación registrada.", "success");
    await refreshJobs({ silent: false });
  } catch (error) { toast(errorMessage(error), "error", 7000); setButtonBusy(button, false); }
}
function detailRow(label, value) {
  return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value === null || value === undefined || value === "" ? "—" : value)}</dd></div>`;
}
function jobDetailHtml(job) {
  const rows = [
    ["ID", `#${job.id}`], ["Tipo", stateLabel(job.tipo)], ["Estado", stateLabel(job.estado)],
    ["SKU", job.sku], ["Producto GBP", job.id_sistema_gbp], ["Avance informado", `${percentage(job)}%`],
    ["Procesados", processedText(job)], ["Errores reportados", number(job.errores)],
    ["Intentos", number(job.intentos)], ["Worker", job.worker_id],
    ["Creado", formatDate(job.created_at)], ["Iniciado", formatDate(job.started_at)],
    ["Actualizado", formatDate(job.updated_at)], ["Finalizado", formatDate(job.finished_at)],
    ["Último heartbeat", formatDate(job.heartbeat_at)], ["Lease hasta", formatDate(job.lease_until)],
    ["Código de error", job.error_codigo],
  ];
  return `<div class="detail-status"><span class="badge ${statusClass(job.estado)}">${escapeHtml(stateLabel(job.estado))}</span>${progressHtml(job)}</div>
    <dl class="job-detail-grid">${rows.map(([name, value]) => detailRow(name, value)).join("")}</dl>
    <div class="detail-message"><strong>Último mensaje</strong><p>${escapeHtml(message(job) || "No se registró un mensaje.")}</p></div>
    ${job.error_detalle ? `<div class="callout warning"><strong>Detalle del error</strong><p>${escapeHtml(job.error_detalle)}</p></div>` : ""}
    ${job.estado === "REQUIERE_REVISION" ? '<div class="callout warning"><strong>Intervención requerida</strong><p>Verificá en GBP y Tiendanube los efectos externos antes de crear otro trabajo. No hay reintento automático.</p></div>' : ""}`;
}
async function openJobDetail(jobId) {
  const dialog = query("#jobDetailDialog");
  const content = query("#jobDetailContent");
  if (!dialog || !content || !/^\d+$/.test(String(jobId))) return;
  detailJobId = String(jobId);
  content.textContent = "Cargando detalle…";
  if (!dialog.open) dialog.showModal();
  try {
    const response = await request(`/admin/panel/jobs/${encodeURIComponent(jobId)}`);
    if (detailJobId !== String(jobId) || !dialog.open) return;
    if (!response?.job) throw new Error("El trabajo no está disponible.");
    content.innerHTML = jobDetailHtml(response.job);
    query("#jobDialogTitle").textContent = `Trabajo #${jobId}`;
  } catch (error) {
    if (dialog.open) content.textContent = `No se pudo cargar el detalle: ${errorMessage(error)}`;
  }
}
function initializeJobMonitoring() {
  if (!query("#liveActiveJobs")) return;
  query("#jobSearch")?.addEventListener("input", filterRecentJobs);
  query("#jobStateFilter")?.addEventListener("change", filterRecentJobs);
  const refresh = query("#refreshJobsNow");
  refresh?.addEventListener("click", async () => {
    setButtonBusy(refresh, true, "Actualizando…"); clearPollTimer();
    await refreshJobs({ silent: false }); setButtonBusy(refresh, false);
  });
  document.addEventListener("click", (event) => {
    const detail = event.target.closest("[data-job-detail]");
    if (detail) openJobDetail(detail.dataset.jobDetail);
    const cancel = event.target.closest(".cancel-job");
    if (cancel) cancelJob(cancel);
  });
  const dialog = query("#jobDetailDialog");
  ["#closeJobDetail", "#closeJobDetailFooter"].forEach((selector) => query(selector)?.addEventListener("click", () => dialog?.close()));
  dialog?.addEventListener("close", () => { detailJobId = null; });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { clearPollTimer(); return; }
    refreshJobs();
  });
  refreshJobs().then(() => {
    const focus = new URLSearchParams(window.location.search).get("focus");
    if (focus && /^\d+$/.test(focus)) openJobDetail(focus);
  });
}
export function initializeJobs() { initializeJobForms(); initializeJobMonitoring(); }
