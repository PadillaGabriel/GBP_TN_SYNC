(() => {
  const modal = document.getElementById('confirm-modal');
  const title = document.getElementById('confirm-title');
  const text = document.getElementById('confirm-text');
  const submit = document.getElementById('confirm-submit');
  let pendingForm = null;

  document.querySelectorAll('form[data-confirm-title]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!modal || typeof modal.showModal !== 'function') {
        return;
      }
      event.preventDefault();
      pendingForm = form;
      title.textContent = form.dataset.confirmTitle || 'Confirmar acción';
      text.textContent = form.dataset.confirmText || 'Confirmar ejecución.';
      submit.className = 'btn ' + (form.dataset.confirmKind || 'primary');
      modal.showModal();
    });
  });

  submit?.addEventListener('click', (event) => {
    event.preventDefault();
    if (pendingForm) {
      const form = pendingForm;
      pendingForm = null;
      modal.close();
      form.submit();
    }
  });

  modal?.addEventListener('close', () => {
    pendingForm = null;
  });
})();
