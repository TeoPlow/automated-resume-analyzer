/**
 * Integrations page — API key management (admin only)
 */
const IntegrationsPage = (() => {
  async function load() {
    try {
      const data = await API.get('/integrations/keys');
      const keys = data.data || [];
      renderTable(keys);
    } catch (e) {
      App.toast(e.message, 'error');
    }
  }

  function renderTable(keys) {
    const tbody = document.getElementById('keys-tbody');
    if (!keys.length) {
      tbody.innerHTML = '<tr><td colspan="5"><div class="empty-state">Нет API-ключей</div></td></tr>';
      return;
    }
    tbody.innerHTML = keys.map(k => `
      <tr>
        <td><strong>${escapeHtml(k.name)}</strong></td>
        <td>${(k.permissions || []).map(p => `<span class="tag">${escapeHtml(p)}</span>`).join('')}</td>
        <td>${formatDate(k.created_at)}</td>
        <td>${k.is_active ? '<span class="badge badge-success">Да</span>' : '<span class="badge badge-danger">Нет</span>'}</td>
        <td class="actions">
          <button class="btn btn-sm btn-outline" onclick="IntegrationsPage.rotateKey('${k.key_id}')">Ротация</button>
          <button class="btn btn-sm btn-danger" onclick="IntegrationsPage.revokeKey('${k.key_id}')">Отозвать</button>
        </td>
      </tr>
    `).join('');
  }

  function showCreateForm() {
    document.getElementById('key-form').reset();
    App.openModal('key-modal');
  }

  async function submitForm(e) {
    e.preventDefault();
    const form = e.target;
    const name = form.querySelector('[name=name]').value;
    const checks = form.querySelectorAll('[name=permissions]:checked');
    const permissions = Array.from(checks).map(c => c.value);

    try {
      const data = await API.post('/integrations/keys', { name, permissions });
      App.closeModal('key-modal');
      // Show the key
      document.getElementById('created-key-value').textContent = data.data.api_key;
      App.openModal('key-created-modal');
      await load();
    } catch (e) {
      App.toast(e.message, 'error');
    }
  }

  async function rotateKey(keyId) {
    if (!confirm('Текущий ключ будет отозван. Продолжить?')) return;
    try {
      const data = await API.post(`/integrations/keys/${keyId}/rotate`);
      document.getElementById('created-key-value').textContent = data.data.api_key;
      App.openModal('key-created-modal');
      await load();
    } catch (e) {
      App.toast(e.message, 'error');
    }
  }

  async function revokeKey(keyId) {
    if (!confirm('Отозвать API-ключ? Это действие необратимо.')) return;
    try {
      await API.del(`/integrations/keys/${keyId}`);
      App.toast('Ключ отозван', 'success');
      await load();
    } catch (e) {
      App.toast(e.message, 'error');
    }
  }

  function copyKey() {
    const val = document.getElementById('created-key-value').textContent;
    navigator.clipboard.writeText(val).then(() => App.toast('Скопировано', 'success'));
  }

  function init() {
    document.getElementById('key-form').addEventListener('submit', submitForm);
  }

  return { load, init, showCreateForm, rotateKey, revokeKey, copyKey };
})();
