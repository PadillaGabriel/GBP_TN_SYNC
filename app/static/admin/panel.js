(() => {
  const modal = document.getElementById('confirm-modal');
  const title = document.getElementById('confirm-title');
  const text = document.getElementById('confirm-text');
  const submit = document.getElementById('confirm-submit');
  const progressModal = document.getElementById('progress-modal');
  const progressTitle = document.getElementById('progress-title');
  const progressStatus = document.getElementById('progress-status');
  const progressDetails = document.getElementById('progress-details');
  const progressBar = document.getElementById('progress-bar');
  const progressClose = document.getElementById('progress-close');
  const refreshJobsButton = document.getElementById('refresh-jobs');
  const jobsList = document.getElementById('jobs-list');

  let pendingForm = null;
  let pollingTimer = null;
  let currentStatusUrl = null;
  const terminalStates = new Set(['FINALIZADO', 'FINALIZADO_CON_ERRORES', 'ERROR', 'CANCELADO']);

  function showProgress() {
    if (progressModal && typeof progressModal.showModal === 'function' && !progressModal.open) {
      progressModal.showModal();
    }
  }

  function stopPolling() {
    if (pollingTimer) {
      clearInterval(pollingTimer);
      pollingTimer = null;
    }
  }

  function setProgress(data) {
    const job = data?.job || {};
    const progreso = job.progreso || {};
    const pct = Number(progreso.porcentaje ?? 0);
    progressTitle.textContent = `${job.tipo || 'Job'} #${job.id || ''}`;
    progressStatus.textContent = `${job.estado || 'SIN_ESTADO'} · ${progreso.mensaje || ''}`;
    progressBar.style.width = `${Math.max(0, Math.min(100, pct))}%`;
    progressDetails.textContent = JSON.stringify(progreso, null, 2);
  }

  async function pollJob(statusUrl) {
    try {
      const response = await fetch(statusUrl, { headers: { Accept: 'application/json' } });
      const data = await response.json();
      setProgress(data);
      const state = data?.job?.estado;
      if (terminalStates.has(state)) {
        stopPolling();
        await refreshJobs();
        return;
      }
    } catch (error) {
      progressStatus.textContent = `Error consultando progreso: ${error}`;
    }
  }

  async function openJob(statusUrl) {
    stopPolling();
    currentStatusUrl = statusUrl;
    showProgress();
    progressTitle.textContent = 'Cargando proceso...';
    progressStatus.textContent = 'Consultando estado persistido.';
    progressBar.style.width = '1%';
    await pollJob(statusUrl);
    pollingTimer = setInterval(() => pollJob(statusUrl), 2500);
  }

  async function startAsyncJob(form) {
    stopPolling();
    const body = new FormData(form);
    const response = await fetch(form.action, {
      method: 'POST',
      headers: { Accept: 'application/json' },
      body,
    });
    const data = await response.json();
    if (!data.ok) {
      progressTitle.textContent = 'No se pudo iniciar el proceso';
      progressStatus.textContent = data.error || 'Respuesta inválida';
      progressDetails.textContent = JSON.stringify(data, null, 2);
      showProgress();
      return;
    }
    progressTitle.textContent = `${data.tipo || 'Job'} #${data.job_id}`;
    progressStatus.textContent = 'Proceso iniciado en segundo plano. Consultando progreso...';
    progressDetails.textContent = JSON.stringify(data, null, 2);
    progressBar.style.width = '1%';
    showProgress();
    await refreshJobs();
    await openJob(data.status_url);
  }

  async function refreshJobs() {
    if (!jobsList) return;
    try {
      const response = await fetch('/admin/panel/jobs', { headers: { Accept: 'application/json' } });
      const data = await response.json();
      if (!data.ok) return;
      const seen = new Set();
      const jobs = [...(data.activos || []), ...(data.recientes || [])].filter((job) => {
        if (seen.has(job.id)) return false;
        seen.add(job.id);
        return true;
      });
      jobsList.innerHTML = jobs.map((job) => {
        const active = ['PENDIENTE', 'EN_PROCESO'].includes(job.estado) ? ' active' : '';
        return `<button class="job-chip${active}" type="button" data-open-job="/admin/panel/jobs/${job.id}">#${job.id} · ${job.tipo} · ${job.estado}</button>`;
      }).join('') || '<span class="muted-text">Sin procesos recientes.</span>';
    } catch (_error) {
      // El panel no debe romperse por no poder refrescar la lista de jobs.
    }
  }

  document.querySelectorAll('form[data-confirm-title]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!modal || typeof modal.showModal !== 'function') return;
      event.preventDefault();
      pendingForm = form;
      title.textContent = form.dataset.confirmTitle || 'Confirmar acción';
      text.textContent = form.dataset.confirmText || 'Confirmar ejecución.';
      submit.className = 'btn ' + (form.dataset.confirmKind || 'primary');
      modal.showModal();
    });
  });

  submit?.addEventListener('click', async (event) => {
    event.preventDefault();
    if (!pendingForm) return;
    const form = pendingForm;
    pendingForm = null;
    modal.close();
    if (form.dataset.asyncJob === 'true') {
      await startAsyncJob(form);
      return;
    }
    form.submit();
  });

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-open-job]');
    if (!button) return;
    event.preventDefault();
    await openJob(button.dataset.openJob);
  });

  refreshJobsButton?.addEventListener('click', refreshJobs);

  modal?.addEventListener('close', () => {
    pendingForm = null;
  });

  progressClose?.addEventListener('click', () => {
    stopPolling();
    currentStatusUrl = null;
    progressModal?.close();
  });

  // Si hay procesos activos al abrir el panel, refrescar la lista sin tocar el popup.
  refreshJobs();
})();
