/** Keeps the single-SKU workflow bound to the existing stock/full-import endpoints. */
export function initializeSyncControls() {
  const form = document.querySelector('.sync-page form[action="/admin/panel/stock/run-sku"]');
  if (!form) return;
  const submit = form.querySelector('[data-sync-individual-submit]');
  const modes = form.querySelectorAll('input[name="sync_mode_ui"]');
  if (!submit || !modes.length) return;
  const refresh = () => {
    const integral = form.querySelector('input[name="sync_mode_ui"]:checked')?.value === 'full';
    submit.setAttribute('formaction', integral ? '/admin/panel/importar-sku' : '/admin/panel/stock/run-sku');
    if (integral) submit.dataset.confirmFull = 'true';
    else delete submit.dataset.confirmFull;
    submit.textContent = integral ? '▷ Sincronizar artículo completo' : '↻ Actualizar sólo stock';
  };
  modes.forEach((mode) => mode.addEventListener('change', refresh));
  refresh();
}
