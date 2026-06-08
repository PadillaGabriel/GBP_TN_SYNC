(() => {
  const modal = document.getElementById('confirm-modal');
  const title = document.getElementById('confirm-title');
  const text = document.getElementById('confirm-text');
  const submit = document.getElementById('confirm-submit');
  const progressModal = document.getElementById('progress-modal');
  const progressTitle = document.getElementById('progress-title');
  const progressStatus = document.getElementById('progress-status');
  const progressDetails = document.getElementById('progress-details');
  const progressSummary = document.getElementById('progress-summary');
  const progressPercent = document.getElementById('progress-percent');
  const progressBar = document.getElementById('progress-bar');
  const progressClose = document.getElementById('progress-close');
  const progressCancel = document.getElementById('progress-cancel');
  const refreshJobsButton = document.getElementById('refresh-jobs');
  const jobsList = document.getElementById('jobs-list');

  let pendingForm = null;
  let pollingTimer = null;
  let currentStatusUrl = null;
  let currentJobId = null;
  const terminalStates = new Set(['FINALIZADO', 'FINALIZADO_CON_ERRORES', 'ERROR', 'CANCELADO']);

  function showDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.showModal === 'function' && !dialog.open) dialog.showModal();
  }

  function stopPolling() {
    if (pollingTimer) {
      clearInterval(pollingTimer);
      pollingTimer = null;
    }
  }

  function escapeHtml(value) {
    return String(value ?? '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#039;');
  }

  function compactValue(value) {
    if (value === null || value === undefined || value === '') return '-';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  }

  function renderSummary(progreso) {
    if (!progressSummary) return;
    const keys = [
      ['procesados', 'Procesados'],
      ['pendientes', 'Pendientes'],
      ['publicables', 'Publicables'],
      ['bloqueados', 'Bloqueados'],
      ['creados', 'Creados'],
      ['actualizados', 'Actualizados'],
      ['sin_cambios', 'Sin cambios'],
      ['stock_no_consultable', 'Stock no consultable'],
      ['errores', 'Errores'],
    ];
    const cards = keys
      .filter(([key]) => progreso && progreso[key] !== undefined)
      .map(([key, label]) => `<article><span>${label}</span><strong>${escapeHtml(compactValue(progreso[key]))}</strong></article>`)
      .join('');

    const detalle = Array.isArray(progreso?.detalle_muestra) ? progreso.detalle_muestra.slice(0, 8) : [];
    const detalleHtml = detalle.length
      ? `<div class="job-sample"><h3>Muestra</h3>${detalle.map((item) => `<p>${escapeHtml(compactValue(item.sku || item.id || '-'))} · ${escapeHtml(compactValue(item.decision_nueva || item.estado || item.error || item.motivos || '-'))}</p>`).join('')}</div>`
      : '';

    progressSummary.innerHTML = `${cards ? `<div class="progress-cards">${cards}</div>` : ''}${detalleHtml}` || '<p class="muted-text">Sin métricas detalladas todavía.</p>';
  }

  function setProgress(data) {
    const job = data?.job || {};
    const progreso = job.progreso || {};
    const pct = Number(progreso.porcentaje ?? 0);
    const safePct = Math.max(0, Math.min(100, Number.isFinite(pct) ? pct : 0));
    currentJobId = job.id || currentJobId;
    progressTitle.textContent = `${job.tipo || 'Proceso'} #${job.id || ''}`;
    progressStatus.textContent = `${job.estado || 'SIN_ESTADO'} · ${progreso.mensaje || ''}`;
    if (progressBar) progressBar.style.width = `${safePct}%`;
    if (progressPercent) progressPercent.textContent = `${safePct}%`;
    if (progressDetails) progressDetails.textContent = JSON.stringify(progreso, null, 2);
    renderSummary(progreso);
    if (progressCancel) {
      progressCancel.disabled = terminalStates.has(job.estado) || job.estado === 'CANCELACION_SOLICITADA';
      progressCancel.textContent = job.estado === 'CANCELACION_SOLICITADA' ? 'Cancelación solicitada' : 'Cancelar proceso';
    }
  }

  async function pollJob(statusUrl) {
    try {
      const response = await fetch(statusUrl, { headers: { Accept: 'application/json' }, cache: 'no-store' });
      const data = await response.json();
      setProgress(data);
      const state = data?.job?.estado;
      if (terminalStates.has(state)) {
        stopPolling();
        await refreshJobs(false);
      }
    } catch (error) {
      progressStatus.textContent = `Error consultando progreso: ${error}`;
    }
  }

  async function openJob(statusUrl) {
    stopPolling();
    currentStatusUrl = statusUrl;
    showDialog(progressModal);
    progressTitle.textContent = 'Cargando proceso...';
    progressStatus.textContent = 'Consultando estado persistido.';
    if (progressBar) progressBar.style.width = '1%';
    if (progressPercent) progressPercent.textContent = '0%';
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
      showDialog(progressModal);
      return;
    }
    showDialog(progressModal);
    progressTitle.textContent = `${data.tipo || 'Proceso'} #${data.job_id}`;
    progressStatus.textContent = 'Proceso iniciado. Consultando progreso...';
    if (progressDetails) progressDetails.textContent = JSON.stringify(data, null, 2);
    if (progressBar) progressBar.style.width = '1%';
    await refreshJobs(false);
    await openJob(data.status_url);
  }

  async function refreshJobs(openFirstActive = false) {
    if (!jobsList) return;
    try {
      const response = await fetch('/admin/panel/jobs', { headers: { Accept: 'application/json' }, cache: 'no-store' });
      const data = await response.json();
      if (!data.ok) return;
      const seen = new Set();
      const jobs = [...(data.activos || []), ...(data.recientes || [])].filter((job) => {
        if (seen.has(job.id)) return false;
        seen.add(job.id);
        return true;
      });
      jobsList.innerHTML = jobs.map((job) => {
        const active = ['PENDIENTE', 'EN_PROCESO', 'CANCELACION_SOLICITADA'].includes(job.estado) ? ' active' : '';
        return `<button class="job-chip${active}" type="button" data-open-job="/admin/panel/jobs/${job.id}"><span>#${job.id}</span><strong>${escapeHtml(job.tipo)}</strong><em>${escapeHtml(job.estado)}</em></button>`;
      }).join('') || '<span class="muted-text">Sin procesos recientes.</span>';
      if (openFirstActive && data.activos && data.activos.length > 0) {
        await openJob(`/admin/panel/jobs/${data.activos[0].id}`);
      } else if (currentStatusUrl && progressModal?.open) {
        await pollJob(currentStatusUrl);
      }
    } catch (error) {
      if (jobsList) jobsList.innerHTML = `<span class="muted-text">No se pudo actualizar procesos: ${escapeHtml(error)}</span>`;
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
      showDialog(modal);
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

  refreshJobsButton?.addEventListener('click', async () => {
    await refreshJobs(true);
  });

  progressCancel?.addEventListener('click', async () => {
    if (!currentJobId) return;
    progressCancel.disabled = true;
    progressCancel.textContent = 'Solicitando cancelación...';
    try {
      const response = await fetch(`/admin/panel/jobs/${currentJobId}/cancel`, { method: 'POST', headers: { Accept: 'application/json' } });
      const data = await response.json();
      if (data.ok) {
        setProgress({ job: data.job });
        await refreshJobs(false);
      } else {
        progressStatus.textContent = data.error || 'No se pudo cancelar.';
      }
    } catch (error) {
      progressStatus.textContent = `Error solicitando cancelación: ${error}`;
    }
  });

  modal?.addEventListener('close', () => {
    pendingForm = null;
  });

  progressClose?.addEventListener('click', () => {
    stopPolling();
    currentStatusUrl = null;
    currentJobId = null;
    progressModal?.close();
  });

  refreshJobs(false);
})();
