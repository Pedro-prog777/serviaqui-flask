window.ServiUI = (() => {
  function escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function setFeedback(target, message, type = 'info') {
    if (!target) return;
    target.textContent = message || '';
    target.dataset.type = type;
  }

  function toast(message, title = 'ServiAqui') {
    const toastEl = document.getElementById('siteToast');
    if (!toastEl || !window.bootstrap) return;
    const titleNode = toastEl.querySelector('.toast-title');
    const bodyNode = toastEl.querySelector('.toast-body');
    if (titleNode) titleNode.textContent = title;
    if (bodyNode) bodyNode.textContent = message;
    window.bootstrap.Toast.getOrCreateInstance(toastEl).show();
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, {
      headers: {
        Accept: 'application/json',
        ...(options.headers || {}),
      },
      ...options,
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || data.message || 'Ocorreu um erro inesperado.');
    }
    return data;
  }

  function readQueryParam(name) {
    return new URLSearchParams(window.location.search).get(name) || '';
  }

  function renderList(items, mapper, emptyText = 'Nenhum registro disponível.') {
    if (!Array.isArray(items) || !items.length) {
      return `<p class="mb-0 text-body-secondary">${escapeHtml(emptyText)}</p>`;
    }
    return `<section class="list-clean">${items.map(mapper).join('')}</section>`;
  }

  function setYears() {
    document.querySelectorAll('[data-current-year]').forEach((node) => {
      node.textContent = new Date().getFullYear();
    });
  }

  return { escapeHtml, setFeedback, toast, fetchJson, readQueryParam, renderList, setYears };
})();
