import { request, errorMessage } from "../core/http.js";
import { toast, setButtonBusy } from "../core/ui.js";

const $ = (id) => document.getElementById(id);
const safe = (value) => String(value ?? "—").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const display = (value) => value === null || value === undefined || value === "" ? "—" : String(value);
function priceLabel(precio) {
  if (!precio || precio.monto === null || precio.monto === undefined) return "No informado";
  const amount = Number(precio.monto);
  if (!Number.isFinite(amount)) return "No informado";
  if (amount === 0) return "Consultar precio";
  return new Intl.NumberFormat("es-AR", { style: "currency", currency: precio.moneda === "USD" ? "USD" : "ARS", maximumFractionDigits: 2 }).format(amount);
}
function imageUrl(producto) {
  const image = Array.isArray(producto.imagenes) ? producto.imagenes.find((entry) => typeof entry?.url === "string" && /^https:\/\//i.test(entry.url.trim())) : null;
  return image?.url.trim() || null;
}
function previewHtml(producto, result) {
  const image = imageUrl(producto);
  const title = display(producto.titulo);
  const stock = producto.stock?.cantidad;
  const fields = [
    ["SKU", producto.sku ?? result.item_code],
    ["ID GBP", producto.id_sistema_gbp ?? result.item_id],
    ["Precio GBP", priceLabel(producto.precio_importado)],
    ["Stock disponible GBP", typeof stock === "number" && Number.isFinite(stock) ? stock : "No informado"],
    ["Publicable web", producto.publicable_web === true ? "Sí" : producto.publicable_web === false ? "No" : "Sin dato"],
    ["Categoría", producto.categoria_nombre],
    ["Marca", producto.marca_nombre],
  ];
  const imageHtml = image ? `<img class="imp-product-image" src="${safe(image)}" alt="Imagen del producto" loading="lazy" referrerpolicy="no-referrer">` : '<span class="imp-product-placeholder">Sin imagen disponible en GBP</span>';
  return `<div class="imp-product-preview"><div class="imp-product-visual">${imageHtml}</div><div class="imp-product-info"><h4>${safe(title)}</h4><dl class="imp-preview-grid">${fields.map(([label, value]) => `<div><dt>${safe(label)}</dt><dd>${safe(display(value))}</dd></div>`).join("")}</dl></div></div><p class="imp-note">Datos actuales de consulta GBP. La publicación aplica sus validaciones y puede requerir revisión.</p>`;
}

export function initializeImportaciones() {
  const form = $("impIndividualForm");
  if (!form) return;
  const input = $("impSku"), button = $("impPreviewButton"), publish = $("impPublishButton"), body = $("impPreviewBody"), status = $("impPreviewStatus");
  let validatedSku = "";
  function invalidate() {
    validatedSku = "";
    publish.disabled = true;
    status.textContent = "Sin consultar";
    body.innerHTML = '<p class="imp-empty">Consultá el artículo para verificar sus datos antes de publicar.</p>';
  }
  input.addEventListener("input", invalidate);
  button.addEventListener("click", async () => {
    const sku = input.value.trim();
    if (!sku) { input.focus(); return; }
    setButtonBusy(button, true, "Consultando…");
    status.textContent = "Consultando GBP…";
    try {
      const result = await request(`/admin/exportaciones/producto/${encodeURIComponent(sku)}`);
      if (result?.ok === false) throw new Error(result.detalle || result.error || "No se encontró el artículo.");
      const producto = result.producto || {};
      body.innerHTML = previewHtml(producto, result);
      validatedSku = sku;
      publish.disabled = false;
      status.textContent = "Artículo consultado";
      body.querySelector(".imp-product-image")?.addEventListener("error", (event) => {
        event.currentTarget.replaceWith(Object.assign(document.createElement("span"), { className: "imp-product-placeholder", textContent: "Imagen no disponible" }));
      }, { once: true });
    } catch (error) {
      validatedSku = "";
      publish.disabled = true;
      status.textContent = "Consulta fallida";
      body.textContent = errorMessage(error);
      toast(errorMessage(error), "error", 7000);
    } finally { setButtonBusy(button, false); }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const sku = input.value.trim();
    if (!sku || sku !== validatedSku) { toast("Consultá primero el artículo que querés importar.", "error"); return; }
    if (!window.confirm(`¿Crear o actualizar el artículo ${sku} en Tiendanube? Se aplicarán las reglas del importador.`)) return;
    setButtonBusy(publish, true, "Encolando…");
    try {
      const data = new FormData(form);
      data.set("sku", sku);
      const result = await request("/admin/panel/importar-sku", { method: "POST", body: data });
      if (result?.ok === false) throw new Error(result.detalle || result.error || "No se pudo registrar el trabajo.");
      toast(`Trabajo #${result.job_id} registrado.`, "success");
      window.location.assign(`/admin/panel/trabajos?focus=${encodeURIComponent(result.job_id)}`);
    } catch (error) {
      toast(errorMessage(error), "error", 7000);
      setButtonBusy(publish, false);
    }
  });
  document.querySelectorAll('[data-confirm-import-all="true"]').forEach((bulk) => bulk.addEventListener("submit", (event) => {
    if (!window.confirm("¿Iniciar la reimportación general? Puede crear o actualizar múltiples publicaciones.")) event.preventDefault();
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
