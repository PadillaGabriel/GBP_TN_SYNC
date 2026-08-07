import { query, queryAll } from "../core/dom.js";
import { errorMessage, request } from "../core/http.js";
import { setButtonBusy, toast } from "../core/ui.js";

function initializeTypeSelector() {
  const type = query("#categoryType");
  const parent = query("#categoryParentField");
  const origin = query("#categoryOrigin");
  if (!type || !parent || !origin) return;
  const refresh = () => {
    const isChild = type.value === "subcategoria";
    parent.hidden = !isChild;
    origin.setAttribute("list", isChild ? "gbpSubcategoryOrigins" : "gbpCategoryOrigins");
  };
  type.addEventListener("change", refresh);
  refresh();
}

function initializeAliasForm() {
  const form = query("#categoryAliasForm");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    setButtonBusy(button, true, "Guardando…");
    try {
      const result = await request("/admin/categorias/normalizaciones", {
        method: "POST",
        body: new FormData(form),
      });
      if (result?.ok === false) throw new Error(result?.mensaje || "No se pudo guardar.");
      toast(result?.mensaje || "Equivalencia guardada.", "success");
      window.setTimeout(() => window.location.reload(), 500);
    } catch (error) {
      toast(errorMessage(error), "error", 7000);
      setButtonBusy(button, false);
    }
  });
}

function initializeDeleteActions() {
  queryAll("[data-category-alias-delete]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.dataset.categoryAliasDelete;
      if (!id || !window.confirm("¿Eliminar esta equivalencia? El dato original de GBP no se modifica.")) return;
      setButtonBusy(button, true, "…");
      try {
        const result = await request(`/admin/categorias/normalizaciones/${encodeURIComponent(id)}/eliminar`, { method: "POST" });
        if (result?.ok === false) throw new Error("No se encontró la equivalencia.");
        toast("Equivalencia eliminada.", "success");
        window.setTimeout(() => window.location.reload(), 450);
      } catch (error) {
        toast(errorMessage(error), "error", 7000);
        setButtonBusy(button, false);
      }
    });
  });
}

function initializeDedupeActions() {
  queryAll("[data-category-dedupe]").forEach((button) => {
    button.addEventListener("click", async () => {
      const confirmWrite = button.dataset.categoryDedupe === "true";
      if (confirmWrite && !window.confirm("Esto reasignará productos y eliminará categorías duplicadas en Tiendanube. ¿Continuar?")) return;
      setButtonBusy(button, true, confirmWrite ? "Iniciando…" : "Diagnosticando…");
      try {
        const result = await request(`/admin/panel/categorias/normalizar-duplicadas?confirm=${confirmWrite}`, { method: "POST" });
        if (result?.ok === false) throw new Error(result?.detalle || "No se pudo iniciar el trabajo.");
        toast(result?.job_id ? `Trabajo iniciado #${result.job_id}.` : "Trabajo iniciado.", "success");
        window.setTimeout(() => window.location.assign("/admin/panel/trabajos"), 600);
      } catch (error) {
        toast(errorMessage(error), "error", 7000);
        setButtonBusy(button, false);
      }
    });
  });
}

export function initializeCategories() {
  initializeTypeSelector();
  initializeAliasForm();
  initializeDeleteActions();
  initializeDedupeActions();
}
