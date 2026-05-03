/**
 * Search page — candidates, vacancies, matches
 */
const SearchPage = (() => {
  function init() {
    // Tabs
    document.querySelectorAll('.search-tabs .tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.search-tabs .tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.search-tab-content').forEach(t => {
          t.classList.remove('active');
          t.classList.add('hidden');
        });
        btn.classList.add('active');
        const targetTab = document.getElementById(btn.dataset.tab);
        targetTab.classList.remove('hidden');
        targetTab.classList.add('active');
      });
    });

    document.getElementById('search-candidates-form').addEventListener('submit', searchCandidates);
    document.getElementById('search-vacancies-form').addEventListener('submit', searchVacancies);
    document.getElementById('search-matches-form').addEventListener('submit', searchMatches);
  }

  async function searchCandidates(e) {
    e.preventDefault();
    const form = e.target;
    const query = {};
    const q = form.querySelector('[name=q]').value;
    if (q) query.q = q;
    const skills = form.querySelector('[name=skills]').value;
    if (skills) query.skills = skills;
    const grade = form.querySelector('[name=grade]').value;
    if (grade) query.grade = grade;
    const location = form.querySelector('[name=location]').value;
    if (location) query.location = location;
    const expMin = form.querySelector('[name=experience_years_min]').value;
    if (expMin) query.experience_years_min = expMin;
    const expMax = form.querySelector('[name=experience_years_max]').value;
    if (expMax) query.experience_years_max = expMax;

    const container = document.getElementById('search-candidates-results');
    container.innerHTML = '<div class="loading-overlay"><span class="spinner"></span></div>';

    try {
      const data = await API.get('/search/candidates', query);
      const items = data.data || [];
      if (!items.length) {
        container.innerHTML = '<div class="empty-state">Ничего не найдено</div>';
        return;
      }
      container.innerHTML = items.map(c => `
        <div class="result-card" style="cursor:pointer" onclick="CandidatesPage.showDetail('${c.id}')">
          <div class="result-header">
            <h4>${escapeHtml(c.full_name || '—')}</h4>
            <div>
              ${c.grade ? `<span class="badge badge-primary">${c.grade}</span>` : ''}
              ${c.experience_years ? `<span class="text-muted">${c.experience_years} лет</span>` : ''}
            </div>
          </div>
          <div>${(c.skills || []).slice(0, 8).map(s => `<span class="tag">${escapeHtml(s)}</span>`).join('')}</div>
        </div>
      `).join('');
    } catch (e) {
      container.innerHTML = `<div class="error-text">${escapeHtml(e.message)}</div>`;
    }
  }

  async function searchVacancies(e) {
    e.preventDefault();
    const form = e.target;
    const query = {};
    const status = form.querySelector('[name=status]').value;
    if (status) query.status = status;
    const dept = form.querySelector('[name=department]').value;
    if (dept) query.department = dept;
    const loc = form.querySelector('[name=location]').value;
    if (loc) query.location = loc;

    const container = document.getElementById('search-vacancies-results');
    container.innerHTML = '<div class="loading-overlay"><span class="spinner"></span></div>';

    try {
      const data = await API.get('/search/vacancies', query);
      const items = data.data || [];
      if (!items.length) {
        container.innerHTML = '<div class="empty-state">Ничего не найдено</div>';
        return;
      }
      container.innerHTML = items.map(v => `
        <div class="result-card" style="cursor:pointer" onclick="VacanciesPage.showDetail('${v.id}')">
          <div class="result-header">
            <h4>${escapeHtml(v.title || '—')}</h4>
            <span class="badge ${statusBadgeVacancy(v.status)}">${v.status}</span>
          </div>
          <div class="info-grid">
            <div class="info-item"><span class="info-label">Отдел</span><span class="info-value">${escapeHtml(v.department || '—')}</span></div>
            <div class="info-item"><span class="info-label">Локация</span><span class="info-value">${escapeHtml(v.location || '—')}</span></div>
            <div class="info-item"><span class="info-label">Зарплата</span><span class="info-value">${formatSalaryRange(v.salary_min, v.salary_max)}</span></div>
          </div>
        </div>
      `).join('');
    } catch (e) {
      container.innerHTML = `<div class="error-text">${escapeHtml(e.message)}</div>`;
    }
  }

  async function searchMatches(e) {
    e.preventDefault();
    const form = e.target;
    const query = {};
    const vid = form.querySelector('[name=vacancy_id]').value;
    if (vid) query.vacancy_id = vid;
    const minScore = form.querySelector('[name=min_score]').value;
    if (minScore) query.min_score = minScore;
    const grade = form.querySelector('[name=grade]').value;
    if (grade) query.grade = grade;

    const container = document.getElementById('search-matches-results');
    container.innerHTML = '<div class="loading-overlay"><span class="spinner"></span></div>';

    try {
      const data = await API.get('/search/matches', query);
      const items = data.data || [];
      if (!items.length) {
        container.innerHTML = '<div class="empty-state">Ничего не найдено</div>';
        return;
      }
      container.innerHTML = items.map(r => renderMatchResult(r)).join('');
    } catch (e) {
      container.innerHTML = `<div class="error-text">${escapeHtml(e.message)}</div>`;
    }
  }

  return { init };
})();
