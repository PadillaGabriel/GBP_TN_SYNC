/** Keeps the single-SKU workflow bound to the existing stock/full-import endpoints. */
export function initializeSyncControls() {
  const form = document.querySelector('.sync-page form[action="/admin/panel/stock/run-sku"]');
  const lastSync = document.querySelector('[data-sync-timestamp]');
  if (lastSync) {
    const raw = lastSync.dataset.syncTimestamp?.trim();
    if (raw) {
      // Backend timestamps without a timezone represent UTC, as in jobs.js.
      const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw) ? raw : `${raw}Z`;
      const date = new Date(normalized);
      if (Number.isFinite(date.getTime())) {
        lastSync.textContent = new Intl.DateTimeFormat('es-AR', {
          day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
        }).format(date);
        lastSync.title = new Intl.DateTimeFormat('es-AR', {
          dateStyle: 'full', timeStyle: 'long',
        }).format(date);
      } else {
        lastSync.textContent = 'Fecha no disponible';
      }
    }
  }
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
