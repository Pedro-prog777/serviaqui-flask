window.ServiAI = (() => {
  function normalizeText(value) {
    return String(value ?? '')
      .replace(/\s+/g, ' ')
      .trim();
  }

  async function postJson(url, payload) {
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(payload || {}),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || data.message || 'Não foi possível concluir a solicitação.');
    }
    return data;
  }

  async function askAssistant(message, pageContext = '') {
    return postJson('/api/assistant', {
      message: normalizeText(message),
      page_context: normalizeText(pageContext),
    });
  }

  async function improveAnnouncement(payload = {}) {
    return postJson('/api/announcements/improve', {
      name: normalizeText(payload.name),
      category: normalizeText(payload.category),
      neighborhood: normalizeText(payload.neighborhood),
      price: normalizeText(payload.price),
      contact: normalizeText(payload.contact),
      description: normalizeText(payload.description),
      accessibility: normalizeText(payload.accessibility),
    });
  }

  return { normalizeText, askAssistant, improveAnnouncement };
})();
