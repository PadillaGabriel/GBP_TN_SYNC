import { normalizeText, queryAll } from "../core/dom.js";
import { errorMessage, request } from "../core/http.js";
import { setButtonBusy, toast } from "../core/ui.js";

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
      setButtonBusy(button, true, "Iniciando…");
      try {
        const { url, options } = prepareFormRequest(form);
        const result = await request(url, options);
        if (result?.ok === false) throw new Error(result.error || result.detalle || "No se pudo iniciar.");
        toast(result?.job_id ? `Trabajo iniciado #${result.job_id}.` : "Trabajo iniciado.", "success");
        window.setTimeout(() => window.location.assign("/admin/panel/trabajos"), 700);
      } catch (error) {
        toast(errorMessage(error), "error", 7000);
      } finally {
        setButtonBusy(button, false);
      }
    });
  });
}

function initializeJobCancellation() {
  queryAll(".cancel-job").forEach((button) => {
    button.addEventListener("click", async () => {
      const jobId = normalizeText(button.dataset.jobId);
      if (!jobId || !window.confirm(`¿Cancelar el trabajo #${jobId}?`)) return;
      setButtonBusy(button, true, "Cancelando…");
      try {
        await request(`/admin/panel/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST" });
        toast("Cancelación solicitada.", "success");
        window.setTimeout(() => window.location.reload(), 700);
      } catch (error) {
        toast(errorMessage(error), "error", 7000);
        setButtonBusy(button, false);
      }
    });
  });
}

export function initializeJobs() {
  initializeJobForms();
  initializeJobCancellation();
}
