(() => {
  const { escapeHtml, setFeedback, toast, fetchJson, readQueryParam, renderList, setYears } = window.ServiUI;
  const { normalizeText, askAssistant, improveAnnouncement } = window.ServiAI;

  let currentUser = null;
  const settingsKey = 'serviaqui.preferences.v3';
  const defaultSettings = {
    theme: 'dark',
    fontScale: 1,
    contrast: false,
    motion: false,
  };
  let siteSettings = { ...defaultSettings };

  function speakText(text) {
    const status = document.getElementById('speechStatus');
    if (!('speechSynthesis' in window)) {
      if (status) status.textContent = 'Seu navegador não oferece leitura em voz alta.';
      return;
    }
    const content = normalizeText(text);
    if (!content) {
      if (status) status.textContent = 'Não há conteúdo para leitura.';
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(content);
    utterance.lang = 'pt-BR';
    utterance.onstart = () => {
      if (status) status.textContent = 'Leitura iniciada.';
    };
    utterance.onend = () => {
      if (status) status.textContent = 'Leitura concluída.';
    };
    utterance.onerror = () => {
      if (status) status.textContent = 'Não foi possível concluir a leitura.';
    };
    window.speechSynthesis.speak(utterance);
  }

  function loadStoredSettings() {
    try {
      const raw = window.localStorage.getItem(settingsKey);
      if (!raw) return;
      siteSettings = { ...defaultSettings, ...JSON.parse(raw) };
    } catch {
      siteSettings = { ...defaultSettings };
    }
  }

  function saveSettings() {
    try {
      window.localStorage.setItem(settingsKey, JSON.stringify(siteSettings));
    } catch {
      // noop
    }
  }

  function applySettings() {
    document.body.dataset.theme = siteSettings.theme;
    document.body.classList.toggle('is-contrast', Boolean(siteSettings.contrast));
    document.body.classList.toggle('reduce-motion', Boolean(siteSettings.motion));
    document.documentElement.style.setProperty('--font-scale', String(siteSettings.fontScale));
    document.querySelectorAll('[data-theme-choice]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.getAttribute('data-theme-choice') === siteSettings.theme));
    });
    saveSettings();
  }

  function toggleDock(force) {
    const panel = document.getElementById('sitePreferencesPanel');
    const toggle = document.querySelector('[data-dock-toggle]');
    if (!panel || !toggle) return;
    const shouldOpen = typeof force === 'boolean' ? force : panel.hidden;
    panel.hidden = !shouldOpen;
    toggle.setAttribute('aria-expanded', String(shouldOpen));
  }

  async function loadSession() {
    try {
      const data = await fetchJson('/api/me');
      currentUser = data.user || null;
    } catch {
      currentUser = null;
    }

    document.querySelectorAll('[data-auth-link]').forEach((link) => {
      if (!currentUser) {
        link.textContent = 'Entrar';
        link.setAttribute('href', '/login');
      } else {
        link.textContent = 'Sair';
        link.setAttribute('href', '#logout');
      }
    });

    document.querySelectorAll('[data-user-only]').forEach((node) => {
      node.hidden = !currentUser;
    });

    document.querySelectorAll('[data-admin-only]').forEach((node) => {
      node.hidden = !(currentUser && currentUser.role === 'admin');
    });
  }

  function initGlobalActions() {
    document.addEventListener('click', async (event) => {
      const authLink = event.target.closest('[data-auth-link]');
      if (authLink && authLink.getAttribute('href') === '#logout') {
        event.preventDefault();
        try {
          await fetchJson('/api/logout', { method: 'POST' });
          toast('Sessão encerrada.');
          window.location.href = '/';
        } catch (error) {
          toast(error.message, 'Erro');
        }
      }

      const dockToggle = event.target.closest('[data-dock-toggle]');
      if (dockToggle) {
        toggleDock();
      }

      if (!event.target.closest('.utility-dock') && !document.getElementById('sitePreferencesPanel')?.hidden) {
        toggleDock(false);
      }

      const speakButton = event.target.closest('[data-speak-target]');
      if (speakButton) {
        const selector = speakButton.getAttribute('data-speak-target');
        const target = document.querySelector(selector);
        speakText(target ? target.textContent : '');
      }

      const chip = event.target.closest('.filter-chip');
      if (chip) {
        document.querySelectorAll('.filter-chip').forEach((node) => {
          node.classList.toggle('active', node === chip);
        });
        filterServices();
      }

      const themeButton = event.target.closest('[data-theme-choice]');
      if (themeButton) {
        siteSettings.theme = themeButton.getAttribute('data-theme-choice') || defaultSettings.theme;
        applySettings();
      }

      const toggleSetting = event.target.closest('[data-toggle-setting]');
      if (toggleSetting) {
        const key = toggleSetting.getAttribute('data-toggle-setting');
        if (key) {
          siteSettings[key] = !siteSettings[key];
          toggleSetting.classList.toggle('is-active', Boolean(siteSettings[key]));
          applySettings();
        }
      }

      const fontStep = event.target.closest('[data-font-step]');
      if (fontStep) {
        const direction = fontStep.getAttribute('data-font-step');
        const delta = direction === 'up' ? 0.1 : -0.1;
        siteSettings.fontScale = Math.min(1.35, Math.max(0.92, Number((siteSettings.fontScale + delta).toFixed(2))));
        applySettings();
      }

      const resetPrefs = event.target.closest('[data-reset-preferences]');
      if (resetPrefs) {
        siteSettings = { ...defaultSettings };
        applySettings();
      }
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') toggleDock(false);
    });
  }

  function filterServices() {
    const input = document.getElementById('serviceSearch');
    const term = normalizeText(input?.value || '').toLowerCase();
    const activeChip = document.querySelector('.filter-chip.active');
    const category = activeChip?.dataset.filter || 'todos';
    const items = Array.from(document.querySelectorAll('.service-item'));
    let count = 0;

    items.forEach((item) => {
      const haystack = String(item.dataset.search || '').toLowerCase();
      const okText = !term || haystack.includes(term);
      const okCategory = category === 'todos' || item.dataset.category === category;
      const visible = okText && okCategory;
      item.hidden = !visible;
      if (visible) count += 1;
    });

    const counter = document.getElementById('resultsCount');
    if (counter) counter.textContent = `${count} serviço(s) encontrado(s)`;
  }

  async function loadMarketplace() {
    const grids = document.querySelectorAll('#marketplaceGrid');
    if (!grids.length) return;
    grids.forEach((grid) => {
      grid.innerHTML = '<article class="placeholder-card">Carregando anúncios aprovados...</article>';
    });

    try {
      const data = await fetchJson('/api/announcements?status=aprovado&limit=8');
      const items = data.items || [];
      const html = items.length
        ? items
            .map(
              (item) => `
              <article class="surface-card marketplace-card">
                ${item.image_url ? `<img src="${escapeHtml(item.image_url)}" alt="Imagem do anúncio ${escapeHtml(item.name)}" loading="lazy">` : '<section class="placeholder-card">Sem imagem</section>'}
                <section class="card-body-flow">
                  <h3>${escapeHtml(item.name)}</h3>
                  <p>${escapeHtml(item.description)}</p>
                  <p class="card-meta">${escapeHtml(item.category)}${item.neighborhood ? ' · ' + escapeHtml(item.neighborhood) : ''}</p>
                  <p class="card-meta">Contato: ${escapeHtml(item.contact)}</p>
                </section>
              </article>
            `
            )
            .join('')
        : '<article class="placeholder-card">Nenhum anúncio aprovado disponível no momento.</article>';
      grids.forEach((grid) => {
        grid.innerHTML = html;
      });
    } catch (error) {
      grids.forEach((grid) => {
        grid.innerHTML = `<article class="placeholder-card">${escapeHtml(error.message)}</article>`;
      });
    }
  }

  function syncAnnouncementPreview() {
    const mappings = [
      ['serviceName', 'previewServiceName', 'Serviço não informado'],
      ['serviceCategory', 'previewCategory', 'Categoria não informada'],
      ['serviceNeighborhood', 'previewNeighborhood', 'Bairro não informado'],
      ['servicePrice', 'previewPrice', 'A combinar'],
      ['serviceContact', 'previewContact', 'Contato não informado'],
      ['serviceDescription', 'previewDescription', 'Descreva o serviço oferecido, seu diferencial e sua forma de atendimento.'],
      ['serviceAccessibility', 'previewAccessibility', 'Informe recursos e diferenciais de atendimento.'],
    ];

    mappings.forEach(([sourceId, targetId, fallback]) => {
      const source = document.getElementById(sourceId);
      const target = document.getElementById(targetId);
      if (!source || !target) return;
      const value = normalizeText(source.value);
      target.textContent = value || fallback;
    });

    const fileInput = document.getElementById('serviceImage');
    const image = document.getElementById('previewImage');
    const empty = document.getElementById('previewImageEmpty');
    const file = fileInput?.files?.[0];

    if (!image || !empty) return;
    if (!file) {
      image.hidden = true;
      image.removeAttribute('src');
      empty.hidden = false;
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      image.src = String(reader.result || '');
      image.hidden = false;
      empty.hidden = true;
    };
    reader.readAsDataURL(file);
  }

  function initAnnouncementPage() {
    const form = document.getElementById('announcementForm');
    if (!form) return;
    const feedback = document.getElementById('announcementFeedback');

    form.addEventListener('input', syncAnnouncementPreview);
    form.addEventListener('change', syncAnnouncementPreview);
    syncAnnouncementPreview();

    document.getElementById('improveAnnouncementBtn')?.addEventListener('click', async () => {
      const payload = {
        name: document.getElementById('serviceName')?.value || '',
        category: document.getElementById('serviceCategory')?.value || '',
        neighborhood: document.getElementById('serviceNeighborhood')?.value || '',
        price: document.getElementById('servicePrice')?.value || '',
        contact: document.getElementById('serviceContact')?.value || '',
        description: document.getElementById('serviceDescription')?.value || '',
        accessibility: document.getElementById('serviceAccessibility')?.value || '',
      };

      setFeedback(feedback, 'Gerando melhoria de texto...', 'info');
      try {
        const data = await improveAnnouncement(payload);
        const descriptionField = document.getElementById('serviceDescription');
        const accessibilityField = document.getElementById('serviceAccessibility');
        if (descriptionField) descriptionField.value = data.improved_description;
        if (accessibilityField && data.accessibility_text) {
          accessibilityField.value = data.accessibility_text;
        }
        syncAnnouncementPreview();
        setFeedback(feedback, 'Descrição atualizada com sucesso.', 'success');
        toast('Copy aprimorada pela assistente.');
      } catch (error) {
        setFeedback(feedback, error.message, 'error');
      }
    });

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const formData = new FormData(form);
      setFeedback(feedback, 'Enviando anúncio...', 'info');

      try {
        const response = await fetch('/api/announcements', {
          method: 'POST',
          body: formData,
          headers: { Accept: 'application/json' },
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(data.error || 'Falha ao enviar anúncio.');
        }
        setFeedback(feedback, data.message || 'Anúncio enviado com sucesso.', 'success');
        toast('Anúncio enviado para moderação.');
        form.reset();
        syncAnnouncementPreview();
      } catch (error) {
        setFeedback(feedback, error.message, 'error');
      }
    });
  }

  function initAssistantPage() {
    const form = document.getElementById('assistantForm');
    if (!form) return;

    const input = document.getElementById('assistantInput') || document.getElementById('assistantMessage');
    const pageInput = document.getElementById('assistantPage');
    const feedback = document.getElementById('assistantStatus') || document.getElementById('assistantFeedback');
    const reply = document.getElementById('assistantReply');
    const meta = document.getElementById('assistantMeta');
    const submitButton = form.querySelector('button[type="submit"]');

    if (!input || !reply || !meta) return;

    form.addEventListener('submit', async (event) => {
      event.preventDefault();

      const message = String(input.value || '').trim();
      const page = String(
        pageInput?.value || document.body.dataset.page || window.location.pathname || ''
      ).trim();

      if (message.length < 3) {
        setFeedback(feedback, 'Digite uma mensagem um pouco mais detalhada para eu conseguir ajudar.', 'error');
        return;
      }

      if (submitButton) {
        submitButton.disabled = true;
        submitButton.innerHTML = '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>Consultando assistente...';
      }

      setFeedback(feedback, 'Consultando assistente...', 'info');

      try {
        const data = await askAssistant(message, page);

        const provider = String(data?.provider || 'indefinido').toLowerCase();
        const providerLabel = provider === 'openai' ? 'IA OpenAI' : 'Modo local';

        const actions = Array.isArray(data?.quick_actions)
          ? data.quick_actions.map((item) => String(item || '').trim()).filter(Boolean)
          : [];

        const services = Array.isArray(data?.recommended_services)
          ? data.recommended_services.map((item) => String(item || '').trim()).filter(Boolean)
          : [];

        const urgency = String(data?.urgency || '').trim();
        const neighborhood = String(data?.neighborhood || '').trim();
        const intent = String(data?.intent || '').trim();
        const accessibilityTip = String(data?.accessibility_tip || '').trim();

        reply.innerHTML = `
          <div class="assistant-response card border-0 shadow-sm">
            <div class="card-body">
              <div class="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
                <h3 class="h5 mb-0">Resposta da assistente</h3>
                <span class="badge rounded-pill badge-soft">${escapeHtml(providerLabel)}</span>
              </div>
              <p class="mb-3">${escapeHtml(data?.reply || 'Sem resposta no momento.')}</p>

              ${services.length ? `
                <div class="mt-4">
                  <h4 class="h6 mb-2">Serviços sugeridos</h4>
                  <ul class="list-group list-group-flush">
                    ${services.map((item) => `<li class="list-group-item px-0">${escapeHtml(item)}</li>`).join('')}
                  </ul>
                </div>
              ` : ''}
            </div>
          </div>
        `;

        meta.innerHTML = `
          ${actions.length ? `
            <div class="mb-3">
              <h4 class="h6 mb-2">Ações rápidas</h4>
              <div class="d-flex flex-wrap gap-2">
                ${actions.map((action) => `<span class="badge text-bg-light border">${escapeHtml(action)}</span>`).join('')}
              </div>
            </div>
          ` : ''}

          ${(urgency || neighborhood || intent) ? `
            <div class="mb-3 small text-body-secondary">
              ${intent ? `<div><strong>Intenção:</strong> ${escapeHtml(intent)}</div>` : ''}
              ${urgency ? `<div><strong>Urgência:</strong> ${escapeHtml(urgency)}</div>` : ''}
              ${neighborhood ? `<div><strong>Região:</strong> ${escapeHtml(neighborhood)}</div>` : ''}
            </div>
          ` : ''}

          ${accessibilityTip ? `
            <div class="small">
              <strong>Dica de acessibilidade:</strong> ${escapeHtml(accessibilityTip)}
            </div>
          ` : ''}
        `;

        setFeedback(feedback, 'Resposta pronta.', 'success');
      } catch (error) {
        reply.innerHTML = `
          <div class="alert alert-danger mb-0" role="alert">
            ${escapeHtml(error.message || 'Erro ao consultar a assistente.')}
          </div>
        `;
        meta.innerHTML = '';
        setFeedback(feedback, error.message || 'Erro ao consultar a assistente.', 'error');
      } finally {
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.innerHTML = 'Consultar assistente';
        }
      }
    });
  }

  function initContactPage() {
    const form = document.getElementById('contactForm');
    if (!form) return;
    const feedback = document.getElementById('contactFeedback');

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const payload = {
        name: document.getElementById('contactName')?.value || '',
        email: document.getElementById('contactEmail')?.value || '',
        subject: document.getElementById('contactSubject')?.value || '',
        channel: document.getElementById('contactChannel')?.value || '',
        message: document.getElementById('contactMessage')?.value || '',
      };

      setFeedback(feedback, 'Enviando mensagem...', 'info');
      try {
        const data = await fetchJson('/api/contact', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        setFeedback(feedback, data.message || 'Mensagem enviada.', 'success');
        toast('Contato enviado com sucesso.');
        form.reset();
      } catch (error) {
        setFeedback(feedback, error.message, 'error');
      }
    });
  }

  // Referência equivalente ao cadastro com bcrypt + insertOne em um backend Node/Mongo.
  // Mantido apenas como anotação técnica, sem substituir o fluxo real deste projeto,
  // que já cria usuários com hash de senha no backend Flask (/api/register).
  //
  // try {
  //   const passwordHash = await bcrypt.hash(senha, 10);
  //   await db.collection('users').insertOne({
  //     email,
  //     passwordHash,
  //     createdAt: new Date(),
  //   });
  // } catch (error) {
  //   console.error('Erro ao cadastrar usuário:', error);
  // }

  function initAuthPage() {
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');

    if (loginForm) {
      const feedback = document.getElementById('loginFeedback');
      loginForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        try {
          const data = await fetchJson('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              email: document.getElementById('loginEmail')?.value || '',
              password: document.getElementById('loginPassword')?.value || '',
            }),
          });
          setFeedback(feedback, data.message || 'Login realizado.', 'success');
          window.location.href = '/painel';
        } catch (error) {
          setFeedback(feedback, error.message, 'error');
        }
      });
    }

    if (registerForm) {
      const feedback = document.getElementById('registerFeedback');
      registerForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        try {
          const data = await fetchJson('/api/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              name: document.getElementById('registerName')?.value || '',
              email: document.getElementById('registerEmail')?.value || '',
              password: document.getElementById('registerPassword')?.value || '',
            }),
          });
          setFeedback(feedback, data.message || 'Conta criada.', 'success');
          window.location.href = '/painel';
        } catch (error) {
          setFeedback(feedback, error.message, 'error');
        }
      });
    }
  }

  function renderStatCards(targetId, items) {
    const target = document.getElementById(targetId);
    if (!target) return;
    target.innerHTML = items
      .map(
        (item) => `
        <article class="surface-card stat-card">
          <span>${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(item.value)}</strong>
        </article>
      `
      )
      .join('');
  }

  async function initDashboardPage() {
    const root = document.getElementById('dashboardStats');
    if (!root) return;

    try {
      const data = await fetchJson('/api/dashboard');
      renderStatCards('dashboardStats', [
        { label: 'Anúncios', value: data.stats.announcements },
        { label: 'Contatos', value: data.stats.contacts },
        { label: 'Conversas', value: data.stats.chats },
      ]);

      document.getElementById('dashboardAnnouncements').innerHTML = renderList(
        data.latest_announcements,
        (item) => `<article class="list-row"><strong>${escapeHtml(item.name)}</strong><p class="mb-0">${escapeHtml(item.category)} · ${escapeHtml(item.status)}</p></article>`
      );

      document.getElementById('dashboardContacts').innerHTML = renderList(
        data.latest_contacts,
        (item) => `<article class="list-row"><strong>${escapeHtml(item.subject)}</strong><p class="mb-0">${escapeHtml(item.channel)} · ${escapeHtml(item.status)}</p></article>`
      );

      document.getElementById('dashboardChats').innerHTML = renderList(
        data.latest_chats,
        (item) => `<article class="list-row"><strong>${escapeHtml(item.message)}</strong><p class="mb-0">${escapeHtml(item.provider)}</p></article>`
      );
    } catch (error) {
      root.innerHTML = `<article class="placeholder-card">${escapeHtml(error.message)}</article>`;
    }
  }

  async function initAdminPage() {
    const root = document.getElementById('adminCounts');
    if (!root) return;

    try {
      const data = await fetchJson('/api/admin/overview');
      renderStatCards('adminCounts', [
        { label: 'Usuários', value: data.counts.users },
        { label: 'Anúncios', value: data.counts.announcements },
        { label: 'Contatos', value: data.counts.contacts },
        { label: 'Pendentes', value: data.counts.pending_announcements },
      ]);

      document.getElementById('adminAnnouncements').innerHTML = renderList(
        data.recent_announcements,
        (item) => `<article class="list-row"><strong>${escapeHtml(item.name)}</strong><p class="mb-0">${escapeHtml(item.category)} · ${escapeHtml(item.status)}</p></article>`
      );

      document.getElementById('adminContacts').innerHTML = renderList(
        data.recent_contacts,
        (item) => `<article class="list-row"><strong>${escapeHtml(item.name)}</strong><p class="mb-0">${escapeHtml(item.subject)}</p></article>`
      );

      document.getElementById('adminUsers').innerHTML = renderList(
        data.recent_users,
        (item) => `<article class="list-row"><strong>${escapeHtml(item.name)}</strong><p class="mb-0">${escapeHtml(item.email)}</p></article>`
      );
    } catch (error) {
      root.innerHTML = `<article class="placeholder-card">${escapeHtml(error.message)}</article>`;
    }
  }

  function initPasswordRequestPage() {
    const form = document.getElementById('passwordRequestForm');
    if (!form) return;
    const feedback = document.getElementById('passwordRequestFeedback');

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      try {
        const data = await fetchJson('/api/password-reset-request', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: document.getElementById('passwordRequestName')?.value || '',
            email: document.getElementById('passwordRequestEmail')?.value || '',
            note: document.getElementById('passwordRequestNote')?.value || '',
          }),
        });
        const extra = data.debug_reset_link ? ` Link de teste: ${data.debug_reset_link}` : '';
        setFeedback(feedback, (data.message || 'Solicitação enviada.') + extra, 'success');
      } catch (error) {
        setFeedback(feedback, error.message, 'error');
      }
    });
  }

  async function initPasswordResetPage() {
    const form = document.getElementById('passwordResetForm');
    if (!form) return;
    const token = readQueryParam('token');
    const status = document.getElementById('passwordResetStatus');
    const feedback = document.getElementById('passwordResetFeedback');
    let valid = false;

    try {
      const data = await fetchJson(`/api/password-reset/validate?token=${encodeURIComponent(token)}`);
      valid = Boolean(data.valid);
      status.textContent = valid ? `Link válido para ${data.email}.` : 'Link inválido.';
    } catch (error) {
      status.textContent = error.message;
    }

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!valid) {
        setFeedback(feedback, 'O link não está válido para uso.', 'error');
        return;
      }

      try {
        const data = await fetchJson('/api/password-reset/confirm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            token,
            password: document.getElementById('passwordResetPassword')?.value || '',
          }),
        });
        setFeedback(feedback, data.message || 'Senha atualizada.', 'success');
      } catch (error) {
        setFeedback(feedback, error.message, 'error');
      }
    });
  }

  function initCounters() {
    document.querySelectorAll('[data-count-to]').forEach((node) => {
      const target = Number(node.getAttribute('data-count-to'));
      if (!Number.isFinite(target)) return;

      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches || siteSettings.motion) {
        node.textContent = String(target);
        return;
      }

      let current = 0;
      const step = Math.max(1, Math.ceil(target / 30));
      const timer = window.setInterval(() => {
        current += step;
        if (current >= target) {
          current = target;
          window.clearInterval(timer);
        }
        node.textContent = String(current);
      }, 28);
    });
  }

  document.addEventListener('DOMContentLoaded', async () => {
    loadStoredSettings();
    applySettings();
    setYears();
    initGlobalActions();
    await loadSession();
    initCounters();

    document.getElementById('serviceSearch')?.addEventListener('input', filterServices);
    filterServices();
    loadMarketplace();

    initAnnouncementPage();
    initAssistantPage();
    initContactPage();
    initAuthPage();
    initDashboardPage();
    initAdminPage();
    initPasswordRequestPage();
    initPasswordResetPage();
  });
})();