import { queryAll } from "../core/dom.js";

export function initializeConfirmations() {
  queryAll("[data-confirm]").forEach((element) => {
    element.addEventListener("click", (event) => {
      const message = element.dataset.confirm || "¿Confirmar esta operación?";
      if (!window.confirm(message)) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    });
  });
}
