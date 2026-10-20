import { normalizeText, query, renderResult } from "../core/dom.js";
import { errorMessage, request } from "../core/http.js";
import { setButtonBusy, toast } from "../core/ui.js";

const PAGE_SIZE = 25;
let offset = 0;
let total = 0;

function esc(value) {
  const div = document.createElement("div");
  div.textContent = String(value ?? "");
  return div.innerHTML;
}
function fecha(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("es-AR", { dateStyle: "short", timeStyle: "short" });
}
function estatus(estado) {
  if (estado === "CONFIRMADO") return "success";
  if (String(estado).includes("ERROR") || String(estado).includes("REVISION")) return "danger";
  return "warning";
}
function fila(p) {
  return `<tr><td><strong>#${esc(p.numero_pedido || p.external_order_id)}</strong><small class="block">ID TN: ${esc(p.external_order_id)}</small></td>
  <td>${esc(fecha(p.created_at))}</td><td>${esc(p.etapa || "—")}</td>
  <td><span class="badge ${estatus(p.estado_integracion)}">${esc(p.estado_integracion)}</span></td>
  <td>${p.confirmado_gbp ? `<strong>#${esc(p.gbp_order_id)}</strong>` : "Sin confirmación"}</td>
  <td><button type="button" class="btn subtle" data-order-detail="${Number(p.id)}">Detalle</button></td></tr>`;
}
async function actualizarHistorial() {
  const status = query("#ordersLiveStatus");
  status.textContent = "Consultando pedidos registrados…";
  const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  const busqueda = normalizeText(query("#ordersSearch")?.value);
  const estado = query("#ordersStatus")?.value || "";
  if (busqueda) params.set("busqueda", busqueda);
  if (estado) params.set("estado", estado);
  try {
    const result = await request(`/pedidos/operaciones/historial?${params}`);
    total = Number(result.total || 0);
    const items = Array.isArray(result.items) ? result.items : [];
    query("#ordersHistoryRows").innerHTML = items.length ? items.map(fila).join("")
      : '<tr><td colspan="6">No se encontraron pedidos con los filtros seleccionados.</td></tr>';
    query("#ordersMetricTotal").textContent = !busqueda && !estado ? String(total) : "—";
    query("#ordersPageStatus").textContent = `${total ? offset + 1 : 0}–${Math.min(total, offset + PAGE_SIZE)} de ${total}`;
    query("#ordersPrevious").disabled = offset === 0;
    query("#ordersNext").disabled = offset + PAGE_SIZE >= total;
    status.textContent = `${items.length} pedidos en esta página · ${new Date().toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" })}`;
    // Esta búsqueda se basa en confirmaciones persistidas, no en pedidos simplemente recibidos.
    if (offset === 0 && !busqueda && !estado) {
      const confirmed = result.ultimo_confirmado;
      query("#ordersMetricLatest").textContent = confirmed ? `TN #${confirmed.numero_pedido || confirmed.external_order_id} → GBP #${confirmed.gbp_order_id}` : "Sin confirmaciones";
      query("#ordersMetricLatestDate").textContent = confirmed ? fecha(confirmed.updated_at) : "No hay confirmaciones GBP persistidas";
    }
  } catch (error) {
    status.textContent = `Error consultando historial: ${errorMessage(error)}`;
    toast(errorMessage(error), "error", 7000);
  }
}
async function abrirDetalle(id) {
  if (!/^\d+$/.test(String(id))) return;
  const dialog = query("#orderDetailDialog");
  const content = query("#orderDetailContent");
  content.textContent = "Cargando detalle…";
  dialog.showModal();
  try {
    const response = await request(`/pedidos/operaciones/${encodeURIComponent(id)}/detalle`);
    if (!dialog.open) return;
    const p = response.pedido;
    query("#orderDetailTitle").textContent = `Orden TN #${p.numero_pedido || p.external_order_id}`;
    const fields = [
      ["Orden TN", p.external_order_id], ["Estado integración", p.estado_integracion],
      ["Etapa", p.etapa], ["Pedido GBP", p.gbp_order_id || "No confirmado"],
      ["Cliente GBP", p.gbp_customer_id || "Sin vincular"], ["Total", `${p.moneda} ${p.total}`],
      ["Fecha recepción", fecha(p.created_at)], ["Última modificación", fecha(p.updated_at)],
      ["Correlation ID", p.correlation_id],
    ];
    const timeline = (p.historial || []).map((event) => `<li><strong>${esc(event.etapa)} · ${esc(event.estado_integracion)}</strong><small>${esc(fecha(event.created_at))}</small><p>${esc(event.motivo)}</p></li>`).join("");
    const items = (p.items || []).map((item) => `<tr><td>${esc(item.sku)}</td><td>${esc(item.titulo)}</td><td>${esc(item.cantidad)}</td><td>${esc(item.precio_unitario)}</td></tr>`).join("");
    content.innerHTML = `<dl class="orders-detail-grid">${fields.map(([label, value]) => `<div><dt>${esc(label)}</dt><dd>${esc(value || "—")}</dd></div>`).join("")}</dl>
      ${p.confirmation_error ? `<div class="callout warning"><strong>Error de confirmación</strong><p>${esc(p.confirmation_error)}</p></div>` : ""}
      <h3>Historial de etapas</h3><ol class="orders-timeline">${timeline || "<li>Sin eventos registrados.</li>"}</ol>
      <h3>Artículos</h3><div class="table-wrap"><table class="orders-detail-table"><thead><tr><th>SKU</th><th>Descripción</th><th>Cantidad</th><th>Precio</th></tr></thead><tbody>${items}</tbody></table></div>`;
  } catch (error) {
    content.textContent = `No se pudo cargar el detalle: ${errorMessage(error)}`;
  }
}
export function initializeOrders() {
  const form = query("#orderImportForm");
  if (!form) return;
  const output = query("#orderResult");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const action = event.submitter?.dataset.orderAction || "receive";
    const id = normalizeText(query("#orderId").value);
    if (!id) return;
    if (action === "complete" && !window.confirm(`¿Encolar el procesamiento de la orden TN #${id} hasta GBP? La operación puede crear un cliente y confirmar un pedido real si las escrituras están habilitadas.`)) return;
    const button = event.submitter;
    setButtonBusy(button, true, "Solicitando…");
    output.hidden = false;
    renderResult(output, "Procesando solicitud…");
    try {
      const endpoint = action === "complete" ? "procesar-gbp" : "importar";
      const result = await request(`/pedidos/tienda-nube/${encodeURIComponent(id)}/${endpoint}`, { method: "POST" });
      renderResult(output, result);
      toast(action === "complete" ? `Trabajo #${result.job_id}: ${result.mensaje || "Solicitud registrada"}` : "Orden recibida en el integrador. Pendiente de procesamiento GBP.", "success");
      await actualizarHistorial();
    } catch (error) {
      renderResult(output, { ok: false, detalle: errorMessage(error) });
      toast(errorMessage(error), "error", 7000);
    } finally { setButtonBusy(button, false); }
  });
  query("#ordersFilterForm")?.addEventListener("submit", (event) => { event.preventDefault(); offset = 0; actualizarHistorial(); });
  query("#ordersRefresh")?.addEventListener("click", actualizarHistorial);
  query("#ordersPrevious")?.addEventListener("click", () => { offset = Math.max(0, offset - PAGE_SIZE); actualizarHistorial(); });
  query("#ordersNext")?.addEventListener("click", () => { if (offset + PAGE_SIZE < total) { offset += PAGE_SIZE; actualizarHistorial(); } });
  query("#ordersHistoryRows")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-order-detail]");
    if (button) abrirDetalle(button.dataset.orderDetail);
  });
  const dialog = query("#orderDetailDialog");
  query("#orderDetailClose")?.addEventListener("click", () => dialog.close());
  query("#orderDetailCloseFooter")?.addEventListener("click", () => dialog.close());
  actualizarHistorial();
}
