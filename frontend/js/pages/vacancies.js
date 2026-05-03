/**
 * Vacancies list & detail pages, create/edit vacancy
 */
const VacanciesPage = (() => {
  let currentOffset = 0;
  const limit = 20;
  let editingId = null;

  async function load() {
    currentOffset = 0;
    await fetchList();
  }

  async function fetchList() {
    const status = document.getElementById('vacancies-status-filter').value;
    const query = { limit, offset: currentOffset };
    if (status) query.status = status;

    try {
      const data = await API.get('/search/vacancies', query);
      renderTable(data.data || []);
      renderPagination('vacancies-pagination', data.pagination, (offset) => {
        currentOffset = offset;
        fetchList();
      });
    } catch (e) {
      App.toast(e.message, 'error');
    }
  }

  function renderTable(items) {
    const tbody = document.getElementById('vacancies-tbody');
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="7"><div class="empty-state">Вакансии не найдены</div></td></tr>';
      return;
    }
    tbody.innerHTML = items.map(v => `
      <tr>
        <td><strong>${escapeHtml(v.title || '—')}</strong></td>
        <td>${escapeHtml(v.department || '—')}</td>
        <td>${(v.grade || []).map(g => `<span class="badge badge-primary">${g}</span>`).join(' ') || '—'}</td>
        <td>${escapeHtml(v.location || '—')}</td>
        <td>${formatSalaryRange(v.salary_min, v.salary_max)}</td>
        <td><span class="badge ${statusBadgeVacancy(v.status)}">${v.status}</span></td>
        <td class="actions">
          <button class="btn btn-sm btn-outline" onclick="VacanciesPage.showDetail('${v.id}')">Открыть</button>
          ${Auth.isAdmin() ? `<button class="btn btn-sm btn-danger" onclick="VacanciesPage.deleteVacancy('${v.id}')">Удалить</button>` : ''}
        </td>
      </tr>
    `).join('');
  }

  async function showDetail(vacancyId) {
    App.navigate('vacancy-detail');
    const infoEl = document.getElementById('vacancy-info');
    infoEl.innerHTML = '<div class="loading-overlay"><span class="spinner"></span> Загрузка...</div>';

    try {
      const data = await API.get(`/vacancies/${vacancyId}`);
      const v = data.data;
      document.getElementById('vacancy-title').textContent = v.title || 'Вакансия';

      // Status change buttons
      const statusActions = getStatusActions(v.status, vacancyId);

      infoEl.innerHTML = `
        <h3>Информация</h3>
        <div class="info-grid">
          <div class="info-item"><span class="info-label">Название</span><span class="info-value">${escapeHtml(v.title || '—')}</span></div>
          <div class="info-item"><span class="info-label">Отдел</span><span class="info-value">${escapeHtml(v.department || '—')}</span></div>
          <div class="info-item"><span class="info-label">Локация</span><span class="info-value">${escapeHtml(v.location || '—')}</span></div>
          <div class="info-item"><span class="info-label">Грейд</span><span class="info-value">${(v.grade || []).map(g => `<span class="badge badge-primary">${g}</span>`).join(' ') || '—'}</span></div>
          <div class="info-item"><span class="info-label">Зарплата</span><span class="info-value">${formatSalaryRange(v.salary_min, v.salary_max)}</span></div>
          <div class="info-item"><span class="info-label">Статус</span><span class="info-value"><span class="badge ${statusBadgeVacancy(v.status)}">${v.status}</span></span></div>
        </div>
        ${v.description ? `<div style="margin-top:1rem"><span class="info-label">Описание</span><p style="margin-top:0.25rem;font-size:0.9rem">${escapeHtml(v.description)}</p></div>` : ''}
        <div style="margin-top:1rem;display:flex;gap:0.5rem">
          ${statusActions}
          <button class="btn btn-sm btn-outline" onclick="VacanciesPage.editVacancy('${vacancyId}')">Редактировать</button>
          ${Auth.isAdmin() ? `<button class="btn btn-sm btn-danger" onclick="VacanciesPage.deleteVacancy('${vacancyId}', true)">Удалить</button>` : ''}
        </div>`;

      // Requirements
      const reqList = document.getElementById('vacancy-requirements-list');
      const reqs = v.requirements || [];
      if (reqs.length) {
        reqList.innerHTML = reqs.map(r => `
          <div class="result-card" style="padding:0.5rem 0.75rem">
            <div style="display:flex;align-items:center;justify-content:space-between">
              <span><strong>${escapeHtml(r.skill)}</strong></span>
              <div>
                <span class="badge badge-gray">${r.category || 'hard'}</span>
                <span class="badge ${r.priority === 'required' ? 'badge-danger' : r.priority === 'preferred' ? 'badge-warning' : 'badge-gray'}">${r.priority || 'required'}</span>
                ${r.min_experience_years ? `<span class="text-muted">${r.min_experience_years}+ лет</span>` : ''}
              </div>
            </div>
          </div>
        `).join('');
      } else {
        reqList.innerHTML = '<div class="empty-state">Нет требований</div>';
      }

      // Matching results
      const matchBtn = document.getElementById('run-matching-vacancy-btn');
      matchBtn.onclick = () => runMatchingForVacancy(vacancyId);
      await loadVacancyMatches(vacancyId);
    } catch (e) {
      infoEl.innerHTML = `<div class="error-text">${escapeHtml(e.message)}</div>`;
    }
  }

  function getStatusActions(status, vacancyId) {
    const actions = [];
    if (status === 'draft') {
      actions.push(`<button class="btn btn-sm btn-success" onclick="VacanciesPage.changeStatus('${vacancyId}','open')">→ Open</button>`);
    } else if (status === 'open') {
      actions.push(`<button class="btn btn-sm btn-danger" onclick="VacanciesPage.changeStatus('${vacancyId}','closed')">→ Closed</button>`);
    } else if (status === 'closed') {
      actions.push(`<button class="btn btn-sm btn-success" onclick="VacanciesPage.changeStatus('${vacancyId}','open')">→ Open</button>`);
      actions.push(`<button class="btn btn-sm btn-outline" onclick="VacanciesPage.changeStatus('${vacancyId}','archived')">→ Archived</button>`);
    } else if (status === 'archived') {
      actions.push(`<button class="btn btn-sm btn-outline" onclick="VacanciesPage.changeStatus('${vacancyId}','draft')">→ Draft</button>`);
    }
    return actions.join('');
  }

  async function changeStatus(vacancyId, newStatus) {
    try {
      await API.patch(`/vacancies/${vacancyId}`, { status: newStatus });
      App.toast(`Статус изменён на ${newStatus}`, 'success');
      // Refresh current view
      const detailPage = document.getElementById('page-vacancy-detail');
      if (detailPage && detailPage.classList.contains('active')) {
        await showDetail(vacancyId);
      } else {
        await fetchList();
      }
    } catch (e) {
      App.toast(e.message, 'error');
    }
  }

  async function loadVacancyMatches(vacancyId) {
    const container = document.getElementById('vacancy-matches-list');
    try {
      const data = await API.get(`/matching/vacancies/${vacancyId}`);
      const results = data.data || [];
      if (!results.length) {
        container.innerHTML = '<div class="empty-state">Нет результатов матчинга</div>';
        return;
      }
      container.innerHTML = results.map(r => renderMatchResult(r)).join('');
    } catch (e) {
      container.innerHTML = '<div class="empty-state">Нет результатов матчинга</div>';
    }
  }

  async function runMatchingForVacancy(vacancyId) {
    const btn = document.getElementById('run-matching-vacancy-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>';
    try {
      await API.post('/matching/run', { vacancy_id: vacancyId });
      App.toast('Матчинг запущен', 'success');
      // Wait a moment and refresh
      setTimeout(() => loadVacancyMatches(vacancyId), 2000);
    } catch (e) {
      App.toast(e.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Запустить матчинг';
    }
  }

  async function deleteVacancy(vacancyId, fromDetail = false) {
    if (!Auth.isAdmin()) {
      App.toast('Удаление доступно только администратору', 'warning');
      return;
    }
    if (!confirm('Удалить вакансию? Это действие необратимо.')) return;

    try {
      await API.del(`/vacancies/${vacancyId}`);
      App.toast('Вакансия удалена', 'success');
      if (fromDetail) {
        App.navigate('vacancies');
      }
      await fetchList();
    } catch (e) {
      App.toast(e.message, 'error');
    }
  }

  function showCreateForm() {
    editingId = null;
    document.getElementById('vacancy-modal-title').textContent = 'Создать вакансию';
    document.getElementById('vacancy-form').reset();
    // Reset requirements to 1 empty row
    const editor = document.getElementById('requirements-editor');
    editor.innerHTML = createRequirementRow();
    App.openModal('vacancy-modal');
  }

  async function editVacancy(vacancyId) {
    editingId = vacancyId;
    document.getElementById('vacancy-modal-title').textContent = 'Редактировать вакансию';

    try {
      const data = await API.get(`/vacancies/${vacancyId}`);
      const v = data.data;
      const form = document.getElementById('vacancy-form');
      form.querySelector('[name=title]').value = v.title || '';
      form.querySelector('[name=department]').value = v.department || '';
      form.querySelector('[name=description]').value = v.description || '';
      form.querySelector('[name=location]').value = v.location || '';
      form.querySelector('[name=grade]').value = (v.grade || []).join(', ');
      form.querySelector('[name=salary_min]').value = v.salary_min || '';
      form.querySelector('[name=salary_max]').value = v.salary_max || '';

      const editor = document.getElementById('requirements-editor');
      const reqs = v.requirements || [];
      if (reqs.length) {
        editor.innerHTML = reqs.map(r => createRequirementRow(r.skill, r.category, r.priority)).join('');
      } else {
        editor.innerHTML = createRequirementRow();
      }

      App.openModal('vacancy-modal');
    } catch (e) {
      App.toast(e.message, 'error');
    }
  }

  async function submitForm(e) {
    e.preventDefault();
    const form = document.getElementById('vacancy-form');
    const body = {
      title: form.querySelector('[name=title]').value,
      department: form.querySelector('[name=department]').value || null,
      description: form.querySelector('[name=description]').value || null,
      location: form.querySelector('[name=location]').value || null,
      grade: form.querySelector('[name=grade]').value.split(',').map(s => s.trim()).filter(Boolean),
      salary_min: parseInt(form.querySelector('[name=salary_min]').value) || null,
      salary_max: parseInt(form.querySelector('[name=salary_max]').value) || null,
    };

    // Gather requirements
    const reqRows = document.querySelectorAll('#requirements-editor .requirement-row');
    const requirements = [];
    reqRows.forEach(row => {
      const skill = row.querySelector('.req-skill').value.trim();
      if (skill) {
        requirements.push({
          skill,
          category: row.querySelector('.req-category').value,
          priority: row.querySelector('.req-priority').value,
        });
      }
    });
    body.requirements = requirements;

    try {
      if (editingId) {
        await API.patch(`/vacancies/${editingId}`, body);
        App.toast('Вакансия обновлена', 'success');
        App.closeModal('vacancy-modal');
        showDetail(editingId);
      } else {
        const data = await API.post('/vacancies', body);
        App.toast('Вакансия создана', 'success');
        App.closeModal('vacancy-modal');
        showDetail(data.data.id);
      }
    } catch (e) {
      App.toast(e.message, 'error');
    }
  }

  function createRequirementRow(skill = '', category = 'hard', priority = 'required') {
    return `
      <div class="requirement-row">
        <input type="text" placeholder="Навык" class="req-skill" value="${escapeHtml(skill)}">
        <select class="req-category">
          <option value="hard" ${category === 'hard' ? 'selected' : ''}>Hard</option>
          <option value="soft" ${category === 'soft' ? 'selected' : ''}>Soft</option>
          <option value="tool" ${category === 'tool' ? 'selected' : ''}>Tool</option>
          <option value="language" ${category === 'language' ? 'selected' : ''}>Language</option>
        </select>
        <select class="req-priority">
          <option value="required" ${priority === 'required' ? 'selected' : ''}>Required</option>
          <option value="preferred" ${priority === 'preferred' ? 'selected' : ''}>Preferred</option>
          <option value="nice_to_have" ${priority === 'nice_to_have' ? 'selected' : ''}>Nice to have</option>
        </select>
        <button type="button" class="btn btn-sm btn-danger remove-req" onclick="this.closest('.requirement-row').remove()">✕</button>
      </div>`;
  }

  function addRequirementRow() {
    const editor = document.getElementById('requirements-editor');
    editor.insertAdjacentHTML('beforeend', createRequirementRow());
  }

  function init() {
    document.getElementById('vacancies-status-filter').addEventListener('change', fetchList);
    document.getElementById('vacancy-form').addEventListener('submit', submitForm);
    document.getElementById('add-requirement-btn').addEventListener('click', addRequirementRow);
  }

  return {
    load,
    init,
    showDetail,
    showCreateForm,
    editVacancy,
    changeStatus,
    deleteVacancy,
  };
})();
