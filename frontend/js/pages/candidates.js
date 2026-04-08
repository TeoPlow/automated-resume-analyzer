/**
 * Candidates list & detail pages
 */
const CandidatesPage = (() => {
  let currentOffset = 0;
  const limit = 20;

  async function load() {
    currentOffset = 0;
    await fetchList();
  }

  async function fetchList() {
    const q = document.getElementById('candidates-search').value;
    const grade = document.getElementById('candidates-grade-filter').value;
    const query = { limit, offset: currentOffset };
    if (q) query.q = q;
    if (grade) query.grade = grade;

    try {
      const data = await API.get('/search/candidates', query);
      renderTable(data.data || []);
      renderPagination('candidates-pagination', data.pagination, (offset) => {
        currentOffset = offset;
        fetchList();
      });
    } catch (e) {
      App.toast(e.message, 'error');
    }
  }

  function renderTable(items) {
    const tbody = document.getElementById('candidates-tbody');
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="7"><div class="empty-state">Кандидаты не найдены</div></td></tr>';
      return;
    }
    tbody.innerHTML = items.map(c => `
      <tr>
        <td><strong>${escapeHtml(c.full_name || '—')}</strong></td>
        <td>${escapeHtml(c.email || '—')}</td>
        <td>${c.grade ? `<span class="badge badge-primary">${c.grade}</span>` : '—'}</td>
        <td>${c.experience_years ?? '—'}</td>
        <td>${(c.skills || []).slice(0, 4).map(s => `<span class="tag">${escapeHtml(s)}</span>`).join('')}${(c.skills || []).length > 4 ? `<span class="tag tag-gray">+${c.skills.length - 4}</span>` : ''}</td>
        <td>${escapeHtml(c.location || '—')}</td>
        <td class="actions">
          <button class="btn btn-sm btn-outline" onclick="CandidatesPage.showDetail('${c.id}')">Открыть</button>
        </td>
      </tr>
    `).join('');
  }

  async function showDetail(candidateId) {
    App.navigate('candidate-detail');
    const infoEl = document.getElementById('candidate-info');
    infoEl.innerHTML = '<div class="loading-overlay"><span class="spinner"></span> Загрузка...</div>';

    try {
      const data = await API.get(`/profiles/candidates/${candidateId}`);
      const c = data.data;
      document.getElementById('candidate-name').textContent = c.full_name || 'Кандидат';

      const profile = c.profile || {};
      infoEl.innerHTML = `
        <h3>Профиль</h3>
        <div class="info-grid">
          <div class="info-item"><span class="info-label">ФИО</span><span class="info-value">${escapeHtml(c.full_name || '—')}</span></div>
          <div class="info-item"><span class="info-label">Email</span><span class="info-value">${escapeHtml(c.email || '—')}</span></div>
          <div class="info-item"><span class="info-label">Телефон</span><span class="info-value">${escapeHtml(c.phone || '—')}</span></div>
          <div class="info-item"><span class="info-label">Грейд</span><span class="info-value">${profile.grade ? `<span class="badge badge-primary">${profile.grade}</span>` : '—'}</span></div>
          <div class="info-item"><span class="info-label">Опыт</span><span class="info-value">${profile.experience_years ?? '—'} лет</span></div>
          <div class="info-item"><span class="info-label">Локация</span><span class="info-value">${escapeHtml(profile.location || '—')}</span></div>
          <div class="info-item"><span class="info-label">Зарплата</span><span class="info-value">${profile.salary_expectation ? formatSalary(profile.salary_expectation) : '—'}</span></div>
        </div>
        <div style="margin-top:1rem">
          <span class="info-label">Навыки</span>
          <div style="margin-top:0.25rem">${(profile.skills || []).map(s => `<span class="tag">${escapeHtml(s)}</span>`).join('') || '—'}</div>
        </div>`;

      // Load resumes
      await loadResumes(candidateId);
      // Load matching results
      await loadCandidateMatches(candidateId);
    } catch (e) {
      infoEl.innerHTML = `<div class="error-text">${escapeHtml(e.message)}</div>`;
    }
  }

  async function loadResumes(candidateId) {
    const container = document.getElementById('resumes-list');
    try {
      const data = await API.get(`/profiles/candidates/${candidateId}/resumes`);
      const resumes = data.data || [];
      if (!resumes.length) {
        container.innerHTML = '<div class="empty-state">Нет резюме</div>';
        return;
      }
      container.innerHTML = resumes.map(r => `
        <div class="result-card">
          <div class="result-header">
            <span class="badge ${statusBadge(r.status)}">${r.status}</span>
            <span class="text-muted">${formatDate(r.created_at)}</span>
          </div>
          <div class="info-grid">
            <div class="info-item"><span class="info-label">Источник</span><span class="info-value">${r.source || '—'}</span></div>
            <div class="info-item"><span class="info-label">ID</span><span class="info-value" style="font-size:0.75rem">${r.id}</span></div>
          </div>
        </div>
      `).join('');
    } catch (e) {
      container.innerHTML = `<div class="error-text">${escapeHtml(e.message)}</div>`;
    }
  }

  async function loadCandidateMatches(candidateId) {
    const container = document.getElementById('candidate-matches-list');
    try {
      const data = await API.get(`/matching/candidates/${candidateId}/vacancies`);
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

  function init() {
    document.getElementById('candidates-search').addEventListener('input', debounce(fetchList, 400));
    document.getElementById('candidates-grade-filter').addEventListener('change', fetchList);
  }

  return { load, init, showDetail };
})();
