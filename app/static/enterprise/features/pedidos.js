import { normalizeText, query, renderResult, requireElement } from "../core/dom.js";
import { errorMessage, request } from "../core/http.js";
import { setButtonBusy, toast } from "../core/ui.js";

export function initializeOrders() {
  const form = query("#orderImportForm");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = requireElement("#orderId", "el campo ID de orden");
    const output = requireElement("#orderResult", "el resultado del pedido");
    const button = form.querySelector('button[type="submit"]');
    const orderId = normalizeText(input.value);

    if (!orderId) {
      renderResult(output, { ok: false, error: "ORDER_ID_REQUERIDO" });
      return;
    }

    setButtonBusy(button, true, "Importando…");
    renderResult(output, "Importando orden…");
    try {
      const result = await request(
        `/pedidos/tienda-nube/${encodeURIComponent(orderId)}/importar`,
        { method: "POST" },
      );
      renderResult(output, result);
      toast("Orden importada correctamente.", "success");
    } catch (error) {
      renderResult(output, { ok: false, error: error.name, detalle: errorMessage(error) });
      toast(errorMessage(error), "error", 7000);
    } finally {
      setButtonBusy(button, false);
    }
  });
}
