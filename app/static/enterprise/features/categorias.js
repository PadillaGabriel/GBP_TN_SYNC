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
      if (confirmWrite && !window.confirm("Confirmá solo después de revisar el diagnóstico en Trabajos. Esta operación reasignará productos y eliminará categorías duplicadas vacías en Tiendanube. ¿Ejecutar?")) return;
      setButtonBusy(button, true, confirmWrite ? "Iniciando…" : "Diagnosticando…");
      try {
        const result = await request(`/admin/panel/categorias/normalizar-duplicadas?confirm=${confirmWrite}`, { method: "POST" });
        if (result?.ok === false) throw new Error(result?.detalle || "No se pudo iniciar el trabajo.");
        toast(result?.job_id ? `Trabajo iniciado #${result.job_id}.` : "Trabajo iniciado.", "success");
        window.setTimeout(() => window.location.assign(result?.job_id ? `/admin/panel/trabajos?focus=${encodeURIComponent(result.job_id)}` : "/admin/panel/trabajos"), 600);
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
  initializeCategoryDashboard();
}

function initializeCategoryDashboard() {
  const rows = queryAll('[data-category-row]');
  const search = query('#categorySearch');
  const type = query('#categoryFilterType');
  const counter = query('#categoryTableCount');
  const label = query('#categoryPageLabel');
  const previous = query('#categoryPrev');
  const next = query('#categoryNext');
  const empty = query('#categoryNoResults');
  if (!search || !type || !counter) return;
  let page = 0;
  const size = 10;
  function render() {
    const term = search.value.trim().toLocaleLowerCase('es');
    const visible = rows.filter((row) => (!type.value || row.dataset.categoryType === type.value)
      && (row.dataset.categorySearch || '').includes(term));
    const pages = Math.max(1, Math.ceil(visible.length / size));
    page = Math.min(page, pages - 1);
    rows.forEach((row) => { row.hidden = true; });
    visible.slice(page * size, (page + 1) * size).forEach((row) => { row.hidden = false; });
    counter.textContent = `${visible.length} equivalencia${visible.length === 1 ? '' : 's'} encontrada${visible.length === 1 ? '' : 's'}`;
    label.textContent = `Página ${page + 1} de ${pages}`;
    previous.disabled = page === 0;
    next.disabled = page >= pages - 1;
    empty.hidden = visible.length !== 0 || rows.length === 0;
  }
  search.addEventListener('input', () => { page = 0; render(); });
  type.addEventListener('change', () => { page = 0; render(); });
  query('#categoryClearFilters')?.addEventListener('click', () => { search.value = ''; type.value = ''; page = 0; render(); });
  previous.addEventListener('click', () => { page--; render(); });
  next.addEventListener('click', () => { page++; render(); });
  render();

  const dialog = query('#categoryAliasDialog');
  const form = query('#categoryAliasForm');
  const heading = query('#categoryDialogTitle');
  if (!dialog || !form) return;
  const open = (button) => {
    form.reset();
    query('#categoryType').value = button?.dataset.tipo || 'categoria';
    query('#categoryOrigin').value = button?.dataset.origen || '';
    query('#categoryCanonical').value = button?.dataset.canonico || '';
    query('#categoryParent').value = button?.dataset.padre || '';
    query('#categoryObservation').value = button?.dataset.observacion || '';
    heading.textContent = button ? 'Editar equivalencia' : 'Nueva equivalencia';
    query('#categoryType').dispatchEvent(new Event('change'));
    dialog.showModal();
  };
  query('#categoryNewAlias')?.addEventListener('click', () => open(null));
  queryAll('[data-category-alias-edit]').forEach((button) => button.addEventListener('click', () => open(button)));
  const close = () => dialog.close();
  query('#categoryCloseDialog')?.addEventListener('click', close);
  query('#categoryCancelDialog')?.addEventListener('click', close);
  dialog.addEventListener('click', (event) => { if (event.target === dialog) close(); });
  query('#categoryPrimaryAction')?.addEventListener('click', () => {
    query('#categoryWorkflow')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  });
}
