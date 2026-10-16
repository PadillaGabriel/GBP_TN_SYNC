import { request, errorMessage } from "../core/http.js";
import { toast, setButtonBusy } from "../core/ui.js";

const $ = (id) => document.getElementById(id);
const safe = (value) => String(value ?? "—").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const display = (value) => value === null || value === undefined || value === "" ? "—" : String(value);
const money = (value) => value === null || value === undefined || value === "" ? "—" : typeof value === "number" ? value.toLocaleString("es-AR", { maximumFractionDigits: 2 }) : typeof value === "object" ? "Verificar en GBP" : String(value);

export function initializeImportaciones() {
  const form = $("impIndividualForm");
  if (!form) return;
  const input = $("impSku"), button = $("impPreviewButton"), publish = $("impPublishButton"), body = $("impPreviewBody"), status = $("impPreviewStatus");
  let validatedSku = "";
  function invalidate() { validatedSku = ""; publish.disabled = true; status.textContent = "Sin consultar"; body.innerHTML = '<p class="imp-empty">Consultá el artículo para verificar su información antes de publicar.</p>'; }
  input.addEventListener("input", invalidate);
  button.addEventListener("click", async () => {
    const sku = input.value.trim();
    if (!sku) { input.focus(); return; }
    setButtonBusy(button, true, "Consultando…");
    status.textContent = "Consultando GBP…";
    try {
      const result = await request(`/admin/exportaciones/producto/${encodeURIComponent(sku)}`);
      if (result?.ok === false) throw new Error(result.detalle || result.error || "No se encontró el artículo.");
      const p = result.producto || {};
      // The preview is informational; it does not constitute a publication guarantee.
      const values = [
        ["SKU", p.sku ?? result.item_code],
        ["ID GBP", p.id_sistema_gbp ?? result.item_id],
        ["Nombre", p.titulo],
        ["Precio GBP", money(p.precio_importado)],
        ["Stock GBP", typeof p.stock === "object" ? JSON.stringify(p.stock) : p.stock],
        ["Publicable web", p.publicable_web === true ? "Sí" : p.publicable_web === false ? "No" : "—"],
      ];
      body.innerHTML = `<dl class="imp-preview-grid">${values.map(([label, value]) => `<div><dt>${safe(label)}</dt><dd>${safe(display(value))}</dd></div>`).join("")}</dl><p class="imp-note">Datos de consulta GBP. La importación aplica sus validaciones y puede requerir revisión.</p>`;
      validatedSku = sku;
      publish.disabled = false;
      status.textContent = "Artículo consultado";
    } catch (error) {
      validatedSku = "";
      publish.disabled = true;
      status.textContent = "Consulta fallida";
      body.textContent = errorMessage(error);
      toast(errorMessage(error), "error", 7000);
    } finally { setButtonBusy(button, false); }
  });
  form.addEventListener("submit", (event) => {
    if (input.value.trim() !== validatedSku || !validatedSku) { event.preventDefault(); toast("Consultá primero la ficha actual del artículo.", "error"); return; }
    if (!window.confirm(`¿Crear o actualizar el artículo ${validatedSku} en Tiendanube? Se aplicarán las reglas de validación del importador.`)) event.preventDefault();
  }, { capture: true });
  document.querySelectorAll('[data-confirm-import-all="true"]').forEach((bulk) => bulk.addEventListener("submit", (event) => {
    if (!window.confirm("¿Iniciar la reimportación general del catálogo? La operación puede crear o actualizar múltiples publicaciones.")) event.preventDefault();
  }, { capture: true }));
  loadRecentImports();
}

async function loadRecentImports() {
  const target = $("impRecentJobs");
  if (!target) return;
  try {
    const payload = await request("/admin/panel/jobs");
    const all = [...(Array.isArray(payload?.activos) ? payload.activos : []), ...(Array.isArray(payload?.recientes) ? payload.recientes : [])];
    const jobs = [...new Map(all.filter((job) => String(job.tipo || "").startsWith("IMPORTAR_")).map((job) => [job.id, job])).values()]
      .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0)).slice(0, 5);
    target.innerHTML = jobs.length ? jobs.map((j) => `<tr><td>#${safe(j.id)}</td><td>${safe(j.tipo === "IMPORTAR_SKU_TN" ? "Individual" : "Masiva")}</td><td>${safe(j.sku || "Catálogo")}</td><td>${safe(j.estado)}</td><td>${safe(j.created_at ? new Date(j.created_at).toLocaleString("es-AR") : "—")}</td><td><a href="/admin/panel/trabajos?focus=${encodeURIComponent(j.id)}">Ver</a></td></tr>`).join("") : '<tr><td colspan="6" class="imp-empty">No hay importaciones recientes.</td></tr>';
  } catch (error) { target.innerHTML = `<tr><td colspan="6" class="imp-empty">No fue posible cargar el historial: ${safe(errorMessage(error))}</td></tr>`; }
}
