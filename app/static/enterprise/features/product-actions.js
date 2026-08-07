import { queryAll } from "../core/dom.js";
import { errorMessage, request } from "../core/http.js";
import { setButtonBusy, toast } from "../core/ui.js";

function closeMenus(except = null) {
  queryAll("[data-product-menu]").forEach((menu) => {
    if (menu !== except) menu.hidden = true;
  });
  queryAll("[data-product-menu-button]").forEach((button) => {
    const controls = button.getAttribute("aria-controls");
    const menu = controls ? document.getElementById(controls) : null;
    button.setAttribute("aria-expanded", String(menu && !menu.hidden));
  });
}

async function runFormJob(url, fields, button) {
  const body = new FormData();
  Object.entries(fields).forEach(([key, value]) => body.append(key, String(value)));
  setButtonBusy(button, true, "Iniciando…");
  try {
    const result = await request(url, { method: "POST", body });
    if (result?.ok === false) throw new Error(result.error || result.detalle || "No se pudo iniciar.");
    toast(result?.job_id ? `Trabajo iniciado #${result.job_id}.` : "Trabajo iniciado.", "success");
    window.setTimeout(() => window.location.assign("/admin/panel/trabajos"), 650);
  } catch (error) {
    toast(errorMessage(error), "error", 7000);
    setButtonBusy(button, false);
  }
}

async function runDirectAction(url, button, confirmation) {
  if (confirmation && !window.confirm(confirmation)) return;
  setButtonBusy(button, true, "Procesando…");
  try {
    const result = await request(url, { method: "POST" });
    if (result?.ok === false) throw new Error(result.error || result.detalle || "La operación no pudo completarse.");
    toast(result?.mensaje || result?.estado || "Operación completada.", "success");
    window.setTimeout(() => window.location.reload(), 650);
  } catch (error) {
    toast(errorMessage(error), "error", 7000);
    setButtonBusy(button, false);
  }
}

export function initializeProductActions() {
  queryAll("[data-product-menu-button]").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const menu = document.getElementById(button.getAttribute("aria-controls"));
      if (!menu) return;
      const willOpen = menu.hidden;
      closeMenus(menu);
      menu.hidden = !willOpen;
      button.setAttribute("aria-expanded", String(willOpen));
      if (willOpen) {
        const rect = button.getBoundingClientRect();
        const menuWidth = menu.offsetWidth || 210;
        const left = Math.max(8, Math.min(window.innerWidth - menuWidth - 8, rect.right - menuWidth));
        menu.style.left = `${left}px`;
        menu.style.top = `${Math.min(window.innerHeight - menu.offsetHeight - 8, rect.bottom + 7)}px`;
      }
    });
  });

  document.addEventListener("click", () => closeMenus());
  window.addEventListener("resize", () => closeMenus());
  window.addEventListener("scroll", () => closeMenus(), true);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeMenus();
  });

  queryAll("[data-product-action]").forEach((button) => {
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const action = button.dataset.productAction;
      const sku = button.dataset.sku || "";
      if (!sku) return;
      closeMenus();

      if (action === "stock") {
        await runFormJob("/admin/panel/stock/run-sku", { sku }, button);
        return;
      }
      if (action === "import") {
        const forzar = button.dataset.force === "true";
        if (forzar && !window.confirm(`El SKU ${sku} está bloqueado. ¿Importarlo de forma forzada?`)) return;
        await runFormJob("/admin/panel/importar-sku", { sku, forzar }, button);
        return;
      }
      if (action === "hide") {
        await runDirectAction(
          `/admin/decisiones/productos/${encodeURIComponent(sku)}/ocultar-tn?confirm=true`,
          button,
          `¿Ocultar el SKU ${sku} en Tiendanube?`,
        );
        return;
      }
      if (action === "delete") {
        await runDirectAction(
          `/admin/decisiones/productos/${encodeURIComponent(sku)}/eliminar-tn?confirm=true`,
          button,
          `¿Eliminar el SKU ${sku} de Tiendanube? Esta acción es destructiva.`,
        );
      }
    });
  });
}
