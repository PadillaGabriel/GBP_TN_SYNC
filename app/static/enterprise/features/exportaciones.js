import { query, queryAll, renderResult, requireElement } from "../core/dom.js";
import { errorMessage, request } from "../core/http.js";
import { setButtonBusy, toast } from "../core/ui.js";

const routes = {
  status: "/admin/exportaciones",
  movements: "/admin/exportaciones/movimientos",
};

function setCardState(card, { status, ok = null, rows = "—", duration = "—", error = "" }) {
  const statusElement = query(".export-status", card);
  const rowsElement = query('[data-field="rows"]', card);
  const timeElement = query('[data-field="time"]', card);
  const errorElement = query('[data-field="error"]', card);

  if (statusElement) {
    statusElement.textContent = status;
    statusElement.classList.toggle("status-ok", ok === true);
    statusElement.classList.toggle("status-error", ok === false);
    statusElement.classList.toggle("status-neutral", ok === null);
  }
  if (rowsElement) rowsElement.textContent = rows;
  if (timeElement) timeElement.textContent = duration;
  if (errorElement) {
    errorElement.textContent = error;
    errorElement.hidden = !error;
  }
  card.classList.toggle("export-card--ok", ok === true);
  card.classList.toggle("export-card--error", ok === false);
}

function updateCard(item) {
  const card = query(`[data-export="${String(item.export_id)}"]`);
  if (!card) return;

  if (item.omitida) {
    setCardState(card, {
      status: "Uso manual GBP",
      ok: null,
      error: item.detalle || "No ejecutable mediante wsExportDataById.",
    });
    return;
  }

  const duration = item.duracion_ms == null ? "—" : `${item.duracion_ms} ms`;
  setCardState(card, {
    status: item.ok ? "Operativa" : "Error",
    ok: Boolean(item.ok),
    rows: item.filas ?? "—",
    duration,
    error: item.ok ? "" : item.error || item.detalle || "Error sin detalle.",
  });
}

function initializeExportTests() {
  const button = query("#testExports");
  if (!button) return;

  button.addEventListener("click", async () => {
    setButtonBusy(button, true, "Probando…");
    queryAll('[data-export][data-compatible-ws="true"]').forEach((card) => {
      setCardState(card, { status: "Probando…", ok: null });
    });

    try {
      const data = await request(routes.status);
      (data.items || []).forEach(updateCard);
      toast(
        data.ok
          ? "Exportaciones compatibles validadas."
          : "Una o más exportaciones requieren revisión.",
        data.ok ? "success" : "warning",
        6500,
      );
    } catch (error) {
      toast(errorMessage(error), "error", 7000);
    } finally {
      setButtonBusy(button, false);
    }
  });
}

function initializeMovementsLookup() {
  const button = query("#testMovements");
  if (!button) return;
  const output = requireElement("#exportMovementsResult", "el resultado de movimientos");

  button.addEventListener("click", async () => {
    setButtonBusy(button, true, "Consultando…");
    renderResult(output, "Consultando exportación 15 en GBP…");
    try {
      const result = await request(routes.movements);
      renderResult(output, result);
      toast(
        result.ok
          ? result.total_filas === 0
            ? "Exportación 15 operativa: sin movimientos recientes."
            : `Exportación 15: ${result.total_filas} filas detectadas.`
          : result.detalle || result.error || "Error en consulta GBP.",
        result.ok ? "success" : "warning",
        6500,
      );
    } catch (error) {
      renderResult(output, {
        ok: false,
        error: error.name || "ERROR_CONSULTA_MOVIMIENTOS",
        detalle: errorMessage(error),
        status: error.status,
      });
      toast(errorMessage(error), "error", 7000);
    } finally {
      setButtonBusy(button, false);
    }
  });
}

export function initializeExports() {
  initializeExportTests();
  initializeMovementsLookup();
}
